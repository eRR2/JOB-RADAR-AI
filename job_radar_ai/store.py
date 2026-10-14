"""Transactional local state. No provider intelligence belongs in this module."""
import json
import math
import sqlite3
import secrets
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from .markets import country_of, migrated_profile, defaults
from .history import create_history_table, match_history, keep_history, historical_opportunities, keep_application_event


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SessionExpired(ValueError):
    """An old worker must never read or mutate the replacement session."""


def normalize_weights(weights):
    if not weights or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Weights must be finite nonnegative numbers.')
    total = sum(weights.values())
    if total <= 0:
        raise ValueError('Choose at least one preference with positive importance.')
    return {k: round(v / total * 100, 6) for k, v in weights.items()}


class Store:
    def __init__(self, path, v5=False):
        self.session_token = None
        self.path = Path(path)
        self.v5 = v5
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Established database failed integrity check. Restore a backup explicitly.')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in ((0, 5) if v5 else (0, 1, 2)):
                raise RuntimeError('Unsupported database version; do not replace it.')
            if v5 and version==0 and db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise RuntimeError('V5 requires empty new storage; historical unversioned tables are not imported.')
            if version == 1:
                # SQLite backup is consistent even in WAL mode. Fail closed before DDL.
                folder = self.path.parent/'backups'
                folder.mkdir(exist_ok=True)
                destination = folder/('migration-'+secrets.token_hex(6)+'.sqlite3')
                with closing(sqlite3.connect(destination)) as backup:
                    db.backup(backup)
                    if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Migration backup verification failed.')
                    for table in ('settings','jobs','feedback','application_events','runs','observations','cache'):
                        original = [tuple(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                        if original != backup.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall():
                            raise RuntimeError('Migration backup differs; database unchanged.')
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
            ''')
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            create_history_table(db)
            db.execute('CREATE TABLE IF NOT EXISTS job_markets(job_id TEXT NOT NULL REFERENCES jobs(id), market_id TEXT NOT NULL, PRIMARY KEY(job_id,market_id))')
            db.execute('CREATE TABLE IF NOT EXISTS market_evaluations(job_id TEXT NOT NULL REFERENCES jobs(id), market_id TEXT NOT NULL, evaluation TEXT NOT NULL, content_stale INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(job_id,market_id))')
            db.execute('CREATE TABLE IF NOT EXISTS feedback_scopes(feedback_id INTEGER PRIMARY KEY REFERENCES feedback(id), scope TEXT NOT NULL)')
            if version == 1:
                row = db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
                profile = json.loads(row[0]) if row else {}
                profile = profile if profile.get('markets') else migrated_profile(profile)
                if row:
                    db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),))
                markets = profile.get('markets', defaults())
                for job in db.execute('SELECT id,payload,evaluation FROM jobs').fetchall():
                    country = country_of(json.loads(job['payload']), markets)
                    if country:
                        db.execute('INSERT OR IGNORE INTO job_markets VALUES (?,?)', (job['id'],country))
                    if job['evaluation']:
                        db.execute('INSERT OR IGNORE INTO market_evaluations VALUES (?,?,?,1)', (job['id'],country or 'unclassified',job['evaluation']))
                    db.execute('INSERT OR IGNORE INTO feedback_scopes SELECT id,? FROM feedback WHERE job_id=?', (country or 'unclassified',job['id']))
            db.execute('PRAGMA user_version='+('5' if v5 else '2'))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                if self.session_token is not None:
                    if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
                    row = db.execute("SELECT value FROM settings WHERE key='search_session'").fetchone()
                    if not row or json.loads(row[0]) != self.session_token:
                        raise SessionExpired('This search session has ended; stale results were refused.')
                yield db
        finally:
            db.close()

    def bound(self, token):
        worker = object.__new__(Store)
        worker.path, worker.v5, worker.session_token = self.path, self.v5, token
        return worker

    def fresh_session(self):
        """Verified backup, knowledge snapshot, then an atomic disposable-state reset."""
        from .access import active, durable_restriction, linkedin_key, explicit_denial
        folder = self.path.parent / 'backups'
        folder.mkdir(exist_ok=True)
        backup_path = folder / ('before-search-' + secrets.token_hex(8) + '.sqlite3')
        self.backup(backup_path)
        with closing(sqlite3.connect(backup_path)) as backup:
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Search backup failed verification; existing data retained.')
            tables = [r[0] for r in backup.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            snapshot = {t:backup.execute('SELECT * FROM "'+t+'" ORDER BY rowid').fetchall() for t in tables}
        with self.db() as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if any([tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')] != rows for t,rows in snapshot.items()):
                raise ValueError('Workspace changed during backup; existing session retained. Try again when idle.')
            settings = {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
            knowledge = {k:v for k,v in settings.items() if k in ('profile','cv_text','cv_filename','persistent_feedback','professional_background','knowledge_signature','learning_paused','preference_revision') or k.startswith(('learned','learning_explanation','preference_revision:'))}
            retained = knowledge.setdefault('persistent_feedback', [])
            for r in db.execute('SELECT f.*,s.scope,j.payload FROM feedback f JOIN jobs j ON j.id=f.job_id LEFT JOIN feedback_scopes s ON s.feedback_id=f.id'):
                job = json.loads(r['payload'])
                fact = {'feedback_id':r['id'],'session':settings.get('search_session','imported_knowledge'),'job_id':r['job_id'],'title':job.get('title',''),'country':r['scope'] or 'unclassified','kind':r['kind'],'reasons':json.loads(r['reasons']),'note':r['note'],'at':r['at']}
                if fact not in retained:retained.append(fact)
            # Genuine third-party denials live outside the disposable session.
            for k,v in settings.items():
                if k == 'linkedin_access' or k.startswith('public:access:'):
                    if durable_restriction(k,v):knowledge[k]=v
                elif k.startswith('public:stop:'):
                    access = settings.get('public:access:' + k.removeprefix('public:stop:'))
                    if linkedin_key(k):
                        if explicit_denial(v) or durable_restriction(k,access):knowledge[k]=v
                    elif not access or active(access):knowledge[k]=v
                elif k == 'linkedin_stop' and explicit_denial(v):
                    knowledge[k]=v
            # A fresh search starts with an empty current view, NOT amnesia.
            # Save previous vacancies and manually recorded application outcomes.
            for r in db.execute('SELECT id,payload,last_seen,application_status FROM jobs').fetchall():
                job = json.loads(r['payload'])
                job['id'] = r['id']
                found = match_history(db, job)
                saved = keep_history(db, job, r['last_seen'],
                                     status=r['application_status'],
                                     source=found['status_source'] if found else 'manual')
                for event in db.execute('SELECT * FROM application_events WHERE job_id=? ORDER BY id', (r['id'],)):
                    key = 'manual:' + str(settings.get('search_session', 'legacy')) + ':' + str(event['id'])
                    keep_application_event(db, saved['identity'], r['id'], event['status'], event['at'], 'manual', key)
            token = secrets.token_hex(16)
            knowledge['search_session'] = token
            for table in ('market_evaluations','job_markets','feedback_scopes','observations','feedback','application_events','jobs','runs','cache','settings'):
                db.execute('DELETE FROM '+table)
            db.executemany('INSERT INTO settings VALUES (?,?)', [(k,json.dumps(v)) for k,v in knowledge.items()])
        return token, backup_path

    def get(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def stop_keys(self):
        with self.db() as db:
            return [row[0] for row in db.execute("SELECT key FROM settings WHERE key LIKE 'public:stop:%'")]

    def access_restrictions(self):
        from .access import active
        with self.db() as db:
            rows=db.execute("SELECT key,value FROM settings WHERE key LIKE 'public:access:%'").fetchall()
        return [r['key'].removeprefix('public:access:') for r in rows if active(json.loads(r['value']))]

    def set(self, key, value):
        from .access import durable_restriction
        if self.session_token is not None and (key == 'linkedin_access' or key.startswith('public:access:')) and isinstance(value,dict) and value.get('http_status') and durable_restriction(key,value):
            # A late real denial is safety knowledge, never a stale job result.
            unbound = self.bound(None)
            with unbound.db() as db:
                if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
                from .access import active
                prior = json.loads(old[0]) if old else None
                if prior and active(prior) and (prior.get('state')=='restricted' or (value.get('state')=='cooling_down' and prior.get('until','')>=value.get('until',''))):
                    return
                db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
            return
        with self.db() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

    def upsert_job(self, job, run_id=None, market_id=None):
        timestamp = now()
        with self.db() as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT payload FROM jobs WHERE id=?', (job['id'],)).fetchone()
            merged = json.loads(old[0]) if old else {}
            merged.update({k: v for k, v in job.items() if v is not None})
            old_payload=json.loads(old[0]) if old else {}
            historical = match_history(db, merged)
            from .availability import merge_states
            history_payload=json.loads(historical['payload']) if historical else {}
            states=merge_states(history_payload.get('source_availability'),old_payload.get('source_availability'),job.get('source_availability'))
            if states:merged['source_availability']=states
            if old is None:
                merged['previously_seen'] = bool(historical)
                if historical:
                    merged['historical_first_seen'] = historical['first_seen']
                    merged['historical_status_source'] = historical['status_source']
            else:
                merged['previously_seen'] = old_payload.get('previously_seen',False)
            # A search observation cannot erase positive evidence from a detail.
            if old_payload.get('availability')=='closed_banner_observed' and job.get('availability')=='unknown' and not job.get('description_obtained'):
                merged['availability']='closed_banner_observed'
                merged['evidence']=old_payload.get('evidence','Closed banner previously observed')
            changed=bool(old and any(merged.get(key)!=old_payload.get(key) for key in ('description','title','company','location','availability')))
            carried_status = historical['application_status'] if historical else 'none'
            mail_status = None
            if carried_status in ('none','saved') and (not historical or historical['status_source']!='manual'):
                from .outlook_history import recorded_decision_for
                mail_status = recorded_decision_for(db,merged)
                if mail_status:
                    carried_status = mail_status
            db.execute('''INSERT INTO jobs(id,payload,first_seen,last_seen,application_status)
                VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                payload=excluded.payload,last_seen=excluded.last_seen''',
                (job['id'], json.dumps(merged), timestamp, timestamp, carried_status))
            if old is not None and mail_status:
                db.execute("UPDATE jobs SET application_status=? WHERE id=? AND application_status IN ('none','saved')",(mail_status,job['id']))
            keep_history(db,merged,timestamp,status=mail_status,source='outlook_read_only' if mail_status else None)
            if changed:
                db.execute('UPDATE market_evaluations SET content_stale=1 WHERE job_id=?',(job['id'],))
            if market_id:
                db.execute('INSERT OR IGNORE INTO job_markets VALUES (?,?)',(job['id'],market_id))
            if run_id:
                db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?)', (run_id, job['id'], int(old is None)))
        return old is None

    def jobs(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM jobs ORDER BY first_seen DESC,id').fetchall()
            events = db.execute('SELECT job_id,status,at FROM application_events ORDER BY id').fetchall()
            feedback = db.execute('SELECT * FROM feedback ORDER BY id').fetchall()
            scopes = dict(db.execute('SELECT feedback_id,scope FROM feedback_scopes').fetchall())
            market_rows = db.execute('SELECT * FROM market_evaluations').fetchall()
            memberships = db.execute('SELECT * FROM job_markets').fetchall()
            durable = {}
            history_checks = {}
            for row in rows:
                history = match_history(db, json.loads(row['payload']))
                if history:
                    durable[row['id']] = [dict(e) for e in db.execute(
                        'SELECT job_id,status,at,source,event_key FROM history_application_events WHERE identity=? ORDER BY rowid',
                        (history['identity'],))]
                historical_payload=json.loads(history['payload']) if history else {}
                confirmation=historical_payload.get('application_status_confirmation',{})
                local_events=durable.get(row['id'],[]) or [dict(e) for e in events if e['job_id']==row['id']]
                recorded = row['application_status'] != 'none' or confirmation.get('status')==row['application_status'] or any(e['status']=='none' for e in local_events)
                history_checks[row['id']] = {'status':'recorded' if recorded else 'unverified',
                    'scope':'local_records_only', 'matched_identity':history['identity'] if history else None,
                    'reason':'recorded_decision' if recorded else 'no_recorded_application_decision'}
        result = []
        for row in rows:
            job = json.loads(row['payload'])
            job.update({k: row[k] for k in ('first_seen', 'last_seen', 'application_status')})
            job['evaluation'] = json.loads(row['evaluation']) if row['evaluation'] else None
            job['events'] = durable.get(row['id']) or [dict(e) for e in events if e['job_id'] == row['id']]
            job['application_history_check'] = history_checks[row['id']]
            job['feedback'] = [{**dict(f), 'scope':scopes.get(f['id'],'unclassified'), 'reasons': json.loads(f['reasons'])} for f in feedback if f['job_id'] == row['id']]
            job['market_ids'] = [m['market_id'] for m in memberships if m['job_id']==row['id']]
            job['market_evaluations'] = {m['market_id']:{'evaluation':json.loads(m['evaluation']),'content_stale':bool(m['content_stale'])} for m in market_rows if m['job_id']==row['id']}
            result.append(job)
        return result

    def historical_opportunities(self, limit=12):
        from .history import same_posting
        with self.db() as db:
            active = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM jobs')]
            previous = historical_opportunities(db,{r.get('id') for r in active},limit=limit*4)
        return [j for j in previous
                if not any(same_posting(j,current) for current in active)][:limit]

    def evaluate(self, job_id, evaluation, market_id=None):
        with self.db() as db:
            if market_id:
                db.execute('INSERT INTO market_evaluations VALUES (?,?,?,0) ON CONFLICT(job_id,market_id) DO UPDATE SET evaluation=excluded.evaluation,content_stale=0', (job_id,market_id,json.dumps(evaluation)))
                return
            if db.execute('UPDATE jobs SET evaluation=? WHERE id=?', (json.dumps(evaluation), job_id)).rowcount != 1:
                raise ValueError('Unknown job identity.')

    def application(self, job_id, status):
        if status not in ('none', 'saved', 'applied', 'interview', 'offer', 'rejected', 'dismissed'):
            raise ValueError('Unknown application status.')
        with self.db() as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT application_status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise ValueError('Unknown job identity.')
            if row[0] != status:
                db.execute('UPDATE jobs SET application_status=? WHERE id=?', (status, job_id))
                timestamp = now()
                event = db.execute('INSERT INTO application_events(job_id,status,at) VALUES (?,?,?)', (job_id, status, timestamp))
                stored = db.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()
                history = keep_history(db,json.loads(stored['payload']),timestamp,status=status,source='manual')
                session = db.execute("SELECT value FROM settings WHERE key='search_session'").fetchone()
                key = 'manual:' + str(json.loads(session[0]) if session else 'legacy') + ':' + str(event.lastrowid)
                keep_application_event(db, history['identity'], job_id, status, timestamp, 'manual', key)
            # Explicit confirmation is distinct from a legacy/default "none".
            # Reconfirming a status does not fabricate another timeline event.
            stored=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()[0])
            stored['application_status_confirmation']={'status':status,'at':now()}
            db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(stored),job_id))
            keep_history(db,stored,now(),status=status,source='manual')

    def add_feedback(self, job_id, kind, reasons, note, scope=None):
        if kind not in ('like', 'dislike', 'irrelevant') or not isinstance(reasons, list) or len(reasons) > 10 or any(not isinstance(r, str) or len(r) > 100 for r in reasons) or not isinstance(note, str) or len(note) > 1000:
            raise ValueError('Invalid feedback.')
        with self.db() as db:
            row=db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise ValueError('Unknown job identity.')
            profile_row=db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
            markets=(json.loads(profile_row[0]) if profile_row else {}).get('markets',defaults())
            country=country_of(json.loads(row[0]),markets)
            scope = scope or country or 'unclassified'
            if self.v5 and scope != (country or 'unclassified'):
                raise ValueError('Feedback belongs to the verified vacancy country; express broader preferences in your next-move text.')
            if scope not in ('global','unclassified') and scope != country:
                raise ValueError('Regional feedback must match the verified listing country. Use global explicitly for all markets.')
            cursor=db.execute('INSERT INTO feedback(job_id,kind,reasons,note,at) VALUES (?,?,?,?,?)', (job_id, kind, json.dumps(reasons), note, now()))
            db.execute('INSERT INTO feedback_scopes VALUES (?,?)',(cursor.lastrowid,scope))
            key='preference_revision' if scope=='global' else 'preference_revision:'+scope
            db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)',(key,'1'))

    def feedback(self, market_id=None):
        with self.db() as db:
            rows = db.execute("SELECT f.*,j.payload,COALESCE(s.scope,'unclassified') AS scope FROM feedback f JOIN jobs j ON j.id=f.job_id LEFT JOIN feedback_scopes s ON s.feedback_id=f.id WHERE ? IS NULL OR s.scope IN (?, 'global') ORDER BY f.id DESC LIMIT 100",(market_id,market_id)).fetchall()
        from .hunter import source_context
        return [{**dict(r), 'reasons': json.loads(r['reasons']), 'job': source_context(json.loads(r['payload'])), 'payload': None} for r in rows]

    def start_run(self, provider):
        with self.db() as db:
            try:
                cursor = db.execute("INSERT INTO runs(provider,status,started,stage) VALUES (?,'running',?,'Starting')", (provider, now()))
            except sqlite3.IntegrityError:
                db.execute("INSERT INTO runs(provider,status,started,finished,stage) VALUES (?,'skipped',?,?,'Another run is active')", (provider, now(), now()))
                return None
            return cursor.lastrowid

    def record_skipped(self, reason):
        with self.db() as db:
            db.execute("INSERT INTO runs(provider,status,started,finished,stage) VALUES ('local','skipped',?,?,?)",(now(),now(),reason))

    def preference_revision(self, bump=False, market_id=None):
        key='preference_revision'+(':'+market_id if market_id else '')
        with self.db() as db:
            if bump:
                db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)',(key,'1'))
            row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return int(row[0]) if row else 0

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
        if self.v5 and self.get('linkedin_pending'):
            from .access import restriction
            if not self.get('linkedin_access'):
                self.set('linkedin_access',restriction(None,interrupted=True,session_only=True))
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
        profile=self.get('profile')
        with self.db() as db:
            history = [{**dict(r), 'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM job_history ORDER BY first_seen,identity')]
            mail = [{**dict(r), 'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM outlook_evidence ORDER BY received_at,evidence_id')]
            events = [dict(r) for r in db.execute('SELECT * FROM history_application_events ORDER BY rowid')]
        return {'profile':profile, 'learned':self.get('learned', []), 'global_learned':self.get('learned:global',[]),
                'market_learning':{m['id']:self.get('learned:'+m['id'],[]) for m in (profile or {}).get('markets',[])},
                'jobs':self.jobs(), 'feedback':self.feedback(), 'runs':self.runs(),
                'job_history':history, 'outlook_evidence':mail, 'application_history':events,
                'persistent_feedback':self.get('persistent_feedback', [])}

    def backup(self, destination):
        backup=sqlite3.connect(destination)
        try:
            with self.db() as db:
                db.backup(backup)
        finally:
            backup.close()

    def erase(self):
        with self.db() as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            for table in ('market_evaluations','job_markets','feedback_scopes','observations', 'feedback', 'application_events', 'jobs', 'runs', 'cache', 'settings', 'history_application_events', 'job_history', 'outlook_evidence'):
                db.execute('DELETE FROM ' + table)
        with self.db() as db:
            db.execute('VACUUM')

