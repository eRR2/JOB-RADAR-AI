"""Read-only Outlook message evidence matcher for externally authorized Graph data.

This module cannot send, modify, or delete mail. Message bodies are data,
never executable instructions. Only unique vacancy identities update history.
A Graph/Outlook connector must be explicitly authorized outside this module.
"""
import hashlib
import json
import re
from .history import folded, same_posting, keep_application_event


_REJECT = re.compile(r'(unfortunately.{0,120}(?:not|cannot|unable|won.t)|'
                     r'not (?:be )?moving forward|regret to inform|'
                     r'leider.{0,120}(?:nicht|absage|anderen)|'
                     r'absage (?:ihrer|zur)|'
                     r'we will not proceed)', re.I | re.S)
_APPLIED = re.compile(r'(thank you for (?:your|applying)|application (?:received|submitted)|'
                      r'we (?:have )?received your application|'
                      r'vielen dank f.r ihre bewerbung|'
                      r'wir haben ihre bewerbung erhalten|'
                      r'bewerbungseingang)',re.I|re.S)


def email_decision(message):
    text = ' '.join(str(message.get(k,'') or '')[:1800]
                    for k in ('subject','bodyPreview','body_preview'))
    if _REJECT.search(text):
        return 'rejected'
    if _APPLIED.search(text):
        return 'applied'
    return None


def _matches(message, job):
    """Never infer identity from company alone."""
    parts = [str(message.get(k,'') or '')[:3000] for k in ('subject','bodyPreview','body_preview')]
    text = folded(' '.join(parts))
    company = folded(job.get('company'))
    if not company or not re.search(r'(?<!\w)' + re.escape(company) + r'(?!\w)', text):
        return False
    req = folded(job.get('requisition_id') or job.get('job_requisition_id'))
    if req:
        return bool(re.search(r'(?<!\w)' + re.escape(req) + r'(?!\w)', text))
    title = folded(job.get('title'))
    return bool(title and len(title)>8 and re.search(r'(?<!\w)' + re.escape(title) + r'(?!\w)', text))


def match_outlook_messages(store, messages, folder_name='Job Radar'):
    """Apply only unique, explicit application/decline evidence to saved jobs.

    Designed for message metadata obtained by an approved read-only Outlook
    connector or user-controlled JSON export. No model or email instructions.
    """
    if folder_name.casefold().strip() != 'job radar':
        raise ValueError('Only the explicitly selected Job Radar folder is accepted.')
    if not isinstance(messages,list) or len(messages)>500 or any(not isinstance(m,dict) for m in messages):
        raise ValueError('Outlook evidence must contain at most 500 messages.')
    metrics={'inspected':0,'matched':0,'ambiguous':0,'unclassified':0}
    with store.db() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM job_history')]
        for message in sorted(messages,key=lambda m: str(m.get('receivedDateTime',''))):
            if not isinstance(message,dict):
                raise ValueError('Invalid message record.')
            metrics['inspected']+=1
            status=email_decision(message)
            if not status:
                metrics['unclassified']+=1
                continue
            # Save a bounded, private copy of classification evidence so the
            # mailbox can be imported BEFORE a future vacancy is discovered.
            # No full body, sender credentials, HTML or commands are stored.
            evidence={'subject':str(message.get('subject',''))[:400],
                      'bodyPreview':str(message.get('bodyPreview') or message.get('body_preview') or '')[:2000]}
            mail_key=hashlib.sha256((str(message.get('id',''))+
                          evidence['subject']+str(message.get('receivedDateTime',''))).encode()).hexdigest()
            inserted = db.execute('''INSERT INTO outlook_evidence(evidence_id,payload,decision,received_at)
                VALUES (?,?,?,?) ON CONFLICT(evidence_id) DO NOTHING''',
                (mail_key,json.dumps(evidence),status,str(message.get('receivedDateTime',''))[:60]))
            if not inserted.rowcount:
                continue  # Reimporting evidence cannot overwrite a later manual correction.
            matches=[r for r in rows if _matches(message,json.loads(r['payload']))]
            if len(matches)!=1:
                metrics['ambiguous']+=1
                continue
            record=matches[0]
            if record['status_source']=='manual' and record['application_status'] not in ('none','saved'):
                continue
            if record['application_status']=='rejected' and status=='applied':
                # An older acknowledgement must never undo a rejection.
                continue
            db.execute('UPDATE job_history SET application_status=?,status_source=? WHERE identity=?',
                       (status,'outlook_read_only',record['identity']))
            record['application_status']=status
            record['status_source']='outlook_read_only'
            job=json.loads(record['payload'])
            keep_application_event(db, record['identity'], job['id'], status,
                                   str(message.get('receivedDateTime','')), 'outlook_read_only', 'mail:'+mail_key)
            for current in db.execute('SELECT id,payload FROM jobs').fetchall():
                if same_posting(job,json.loads(current['payload'])):
                    db.execute('UPDATE jobs SET application_status=? WHERE id=?',(status,current['id']))
            metrics['matched']+=1
    return metrics


def recorded_decision_for(db, job):
    """Use earlier folder evidence only if it uniquely identifies this posting."""
    records=[dict(r) for r in db.execute(
        'SELECT payload,decision,received_at FROM outlook_evidence ORDER BY received_at')]
    historical=[json.loads(row['payload']) for row in
                db.execute('SELECT payload FROM job_history')]
    result=None
    for record in records:
        message=json.loads(record['payload'])
        if not _matches(message,job):
            continue
        competitors=[old for old in historical
                     if not same_posting(old,job) and _matches(message,old)]
        if competitors:
            continue  # Ambiguous email cannot suppress another vacancy.
        if result=='rejected' and record['decision']=='applied':
            continue
        result=record['decision']
    return result

