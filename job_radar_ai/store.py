"""Transactional local state. No provider intelligence belongs in this module."""
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def normalize_weights(weights):
    if not weights or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Weights must be finite nonnegative numbers.')
    total = sum(weights.values())
    if total <= 0:
        raise ValueError('Choose at least one preference with positive importance.')
    return {k: round(v / total * 100, 6) for k, v in weights.items()}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Established database failed integrity check. Restore a backup explicitly.')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('Unsupported database version; do not replace it.')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, application_status TEXT NOT NULL DEFAULT 'none',
                    evaluation TEXT);
                CREATE TABLE IF NOT EXISTS application_events(id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    status TEXT NOT NULL, at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                    kind TEXT NOT NULL, reasons TEXT NOT NULL, note TEXT NOT NULL, at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, provider TEXT NOT NULL, status TEXT NOT NULL,
                    started TEXT NOT NULL, finished TEXT, stage TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}');
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs((1)) WHERE status='running';
                CREATE TABLE IF NOT EXISTS observations(run_id INTEGER NOT NULL REFERENCES runs(id),
                    job_id TEXT NOT NULL REFERENCES jobs(id), is_new INTEGER NOT NULL, PRIMARY KEY(run_id,job_id));
                CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, at TEXT NOT NULL, payload TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.db() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

    def upsert_job(self, job, run_id=None):
        timestamp = now()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT payload FROM jobs WHERE id=?', (job['id'],)).fetchone()
            merged = json.loads(old[0]) if old else {}
            merged.update({k: v for k, v in job.items() if v is not None})
            db.execute('''INSERT INTO jobs(id,payload,first_seen,last_seen) VALUES (?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen''',
                (job['id'], json.dumps(merged), timestamp, timestamp))
            if run_id:
                db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?)', (run_id, job['id'], int(old is None)))
        return old is None

    def jobs(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM jobs ORDER BY first_seen DESC,id').fetchall()
            events = db.execute('SELECT job_id,status,at FROM application_events ORDER BY id').fetchall()
            feedback = db.execute('SELECT * FROM feedback ORDER BY id').fetchall()
        result = []
        for row in rows:
            job = json.loads(row['payload'])
            job.update({k: row[k] for k in ('first_seen', 'last_seen', 'application_status')})
            job['evaluation'] = json.loads(row['evaluation']) if row['evaluation'] else None
            job['events'] = [dict(e) for e in events if e['job_id'] == row['id']]
            job['feedback'] = [{**dict(f), 'reasons': json.loads(f['reasons'])} for f in feedback if f['job_id'] == row['id']]
            result.append(job)
        return result

    def evaluate(self, job_id, evaluation):
        with self.db() as db:
            if db.execute('UPDATE jobs SET evaluation=? WHERE id=?', (json.dumps(evaluation), job_id)).rowcount != 1:
                raise ValueError('Unknown job identity.')

    def application(self, job_id, status):
        if status not in ('none', 'saved', 'applied', 'interview', 'offer', 'rejected', 'dismissed'):
            raise ValueError('Unknown application status.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT application_status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise ValueError('Unknown job identity.')
            if row[0] != status:
                db.execute('UPDATE jobs SET application_status=? WHERE id=?', (status, job_id))
                db.execute('INSERT INTO application_events(job_id,status,at) VALUES (?,?,?)', (job_id, status, now()))

    def add_feedback(self, job_id, kind, reasons, note):
        if kind not in ('like', 'dislike', 'irrelevant') or not isinstance(reasons, list) or len(reasons) > 10 or any(not isinstance(r, str) or len(r) > 100 for r in reasons) or not isinstance(note, str) or len(note) > 1000:
            raise ValueError('Invalid feedback.')
        with self.db() as db:
            if not db.execute('SELECT 1 FROM jobs WHERE id=?', (job_id,)).fetchone():
                raise ValueError('Unknown job identity.')
            db.execute('INSERT INTO feedback(job_id,kind,reasons,note,at) VALUES (?,?,?,?,?)', (job_id, kind, json.dumps(reasons), note, now()))

    def feedback(self):
        with self.db() as db:
            rows = db.execute('SELECT f.*,j.payload FROM feedback f JOIN jobs j ON j.id=f.job_id ORDER BY f.id DESC LIMIT 100').fetchall()
        return [{**dict(r), 'reasons': json.loads(r['reasons']), 'job': json.loads(r['payload']), 'payload': None} for r in rows]

    def start_run(self, provider):
        with self.db() as db:
            try:
                cursor = db.execute("INSERT INTO runs(provider,status,started,stage) VALUES (?,'running',?,'Starting')", (provider, now()))
            except sqlite3.IntegrityError:
                db.execute("INSERT INTO runs(provider,status,started,finished,stage) VALUES (?,'skipped',?,?,'Another run is active')", (provider, now(), now()))
                return None
            return cursor.lastrowid

    def update_run(self, run_id, stage, payload=None, status=None):
        with self.db() as db:
            row = db.execute('SELECT payload,status FROM runs WHERE id=?', (run_id,)).fetchone()
            content = json.loads(row['payload'])
            if payload:
                content.update(payload)
            final = status or row['status']
            db.execute('UPDATE runs SET stage=?,payload=?,status=?,finished=? WHERE id=?',
                (stage, json.dumps(content), final, now() if final != 'running' else None, run_id))

    def runs(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 100').fetchall()
        return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]

    def recover_runs(self):
        # Called only after taking the single application process lock.
        with self.db() as db:
            db.execute("UPDATE runs SET status='failed',finished=?,stage='Interrupted process; request extent may be unknown' WHERE status='running'", (now(),))

    def cached(self, key, max_age=86400):
        with self.db() as db:
            row = db.execute('SELECT at,payload FROM cache WHERE key=?', (key,)).fetchone()
        if row and (datetime.now(timezone.utc) - datetime.fromisoformat(row['at'])).total_seconds() < max_age:
            return json.loads(row['payload'])
        return None

    def cache(self, key, value):
        with self.db() as db:
            db.execute('INSERT INTO cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET at=excluded.at,payload=excluded.payload', (key, now(), json.dumps(value)))

    def export(self):
        return {'profile': self.get('profile'), 'learned': self.get('learned', []), 'jobs': self.jobs(), 'feedback': self.feedback(), 'runs': self.runs()}

    def backup(self, destination):
        with self.db() as db, sqlite3.connect(destination) as backup:
            db.backup(backup)

    def erase(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('observations', 'feedback', 'application_events', 'jobs', 'runs', 'cache', 'settings'):
                db.execute('DELETE FROM ' + table)
            db.execute('PRAGMA secure_delete=ON')
        with self.db() as db:
            db.execute('VACUUM')
