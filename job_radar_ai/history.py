"""Conservative, persistent vacancy identity and application history.

Only normalized, corroborated job facts are used for matching. Unknown data is
not negative evidence. Matching across different requisitions is prohibited.
Mail content is never executed or treated as instructions.
"""
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from .identity import normalized_url, linkedin_job_id


def folded(value):
    raw = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ' '.join(re.findall(r'\w+', raw))


def request_id(job):
    value = str(job.get('requisition_id') or job.get('job_requisition_id') or '').strip()
    if value:
        return folded(value)
    source = str(job.get('source_id') or '')
    if source.isdigit() and len(source) >= 6:
        return source
    return ''


def same_posting(a, b):
    """Require an identity or a conservative same-employer/role/locality match."""
    la, lb = linkedin_job_id(a.get('url', '')), linkedin_job_id(b.get('url', ''))
    if la and lb:
        return la == lb
    ca, cb = folded(a.get('company')), folded(b.get('company'))
    if ca and cb and ca != cb:
        return False
    ra, rb = request_id(a), request_id(b)
    if ra and rb and ca and cb:
        return ra == rb
    try:
        if normalized_url(a.get('url', '')) == normalized_url(b.get('url', '')) and a.get('url') and b.get('url'):
            return True
    except ValueError:
        pass
    if not ca or not cb:
        return False
    if folded(a.get('title')) != folded(b.get('title')) or not folded(a.get('title')):
        return False
    if not folded(a.get('location')) or folded(a.get('location')) != folded(b.get('location')):
        return False
    da, db = a.get('description', ''), b.get('description', '')
    if da and db and len(da) > 250 and len(db) > 250:
        return SequenceMatcher(None, folded(da)[:5000], folded(db)[:5000], autojunk=True).ratio() >= 0.72
    return True


def historical_key(job):
    li = linkedin_job_id(job.get('url', ''))
    if li:
        return 'li:' + li
    company = folded(job.get('company'))
    req = request_id(job)
    if company and req:
        return 'req:' + hashlib.sha256((company + '|' + req).encode()).hexdigest()[:24]
    if company and folded(job.get('title')) and folded(job.get('location')):
        stem = '|'.join((company, folded(job.get('title')), folded(job.get('location'))))
        return 'role:' + hashlib.sha256(stem.encode()).hexdigest()[:24]
    return 'url:' + hashlib.sha256(normalized_url(job['url']).encode()).hexdigest()[:24]


def create_history_table(db):
    db.execute('''CREATE TABLE IF NOT EXISTS job_history (
        identity TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        application_status TEXT NOT NULL DEFAULT 'none',
        status_source TEXT NOT NULL DEFAULT 'unknown'
    )''')


def match_history(db, job):
    """Return exactly one confident match; ambiguous positions stay distinct."""
    import json
    matches = [dict(row) for row in db.execute('SELECT * FROM job_history')
               if same_posting(job, json.loads(row['payload']))]
    return matches[0] if len(matches) == 1 else None


def keep_history(db, job, timestamp, status=None, source=None):
    """Update the long-term catalogue without altering its application decision."""
    import json
    found = match_history(db, job)
    identity = found['identity'] if found else historical_key(job)
    old = json.loads(found['payload']) if found else {}
    merged = {**old, **job}
    first = found['first_seen'] if found else timestamp
    existing_status = found['application_status'] if found else 'none'
    existing_source = found['status_source'] if found else 'unknown'
    if status is not None:
        existing_status = status
        existing_source = source or 'manual'
    db.execute('''INSERT INTO job_history(identity,payload,first_seen,last_seen,application_status,status_source)
                  VALUES (?,?,?,?,?,?)
                  ON CONFLICT(identity) DO UPDATE SET payload=excluded.payload,
                  last_seen=excluded.last_seen,application_status=excluded.application_status,
                  status_source=excluded.status_source''',
               (identity, json.dumps(merged), first, timestamp, existing_status, existing_source))
    return {'identity': identity, 'first_seen': first, 'seen_before': bool(found),
            'application_status': existing_status, 'status_source': existing_source}


def historical_opportunities(db, active_ids, limit=12):
    """Old, previously promising, unapplied positions; never presented as fresh."""
    import json
    rows = db.execute('SELECT * FROM job_history ORDER BY last_seen DESC').fetchall()
    out = []
    for row in rows:
        if row['application_status'] in ('applied', 'interview', 'offer', 'rejected', 'dismissed'):
            continue
        job = json.loads(row['payload'])
        if job.get('id') in active_ids:
            continue
        evaluation = job.get('preliminary') or {}
        if not evaluation.get('recommend') or evaluation.get('critical_gap'):
            continue
        if job.get('availability') == 'closed_banner_observed':
            continue
        out.append({**job, 'historical': True, 'last_seen': row['last_seen'],
                    'application_status': row['application_status'],
                    'availability_note': 'Previously found; current availability not reverified'})
        if len(out) >= limit:
            break
    return out
