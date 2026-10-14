"""Read-only Outlook message evidence matcher for externally authorized Graph data.

This module cannot send, modify, or delete mail. Message bodies are data,
never executable instructions. Only unique vacancy identities update history.
A Graph/Outlook connector must be explicitly authorized outside this module.
"""
import hashlib
import json
import re
from .history import folded, request_id, same_posting


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
    req = request_id(job)
    if req and re.search(r'(?<!\w)' + re.escape(req) + r'(?!\w)',text):
        return True
    company = folded(job.get('company'))
    title = folded(job.get('title'))
    return bool(company and title and len(title)>8 and company in text and title in text)


def match_outlook_messages(store, messages, folder_name='Job Radar'):
    """Apply only unique, explicit application/decline evidence to saved jobs.

    Designed for message metadata obtained by an approved read-only Outlook
    connector or user-controlled JSON export. No model or email instructions.
    """
    if folder_name.casefold().strip() != 'job radar':
        raise ValueError('Only the explicitly selected Job Radar folder is accepted.')
    if not isinstance(messages,list) or len(messages)>500:
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
            matches=[r for r in rows if _matches(message,json.loads(r['payload']))]
            if len(matches)!=1:
                metrics['ambiguous']+=1
                continue
            record=matches[0]
            if record['application_status']=='rejected' and status=='applied':
                # An older acknowledgement must never undo a rejection.
                continue
            db.execute('UPDATE job_history SET application_status=?,status_source=? WHERE identity=?',
                       (status,'outlook_read_only',record['identity']))
            record['application_status']=status
            job=json.loads(record['payload'])
            db.execute('UPDATE jobs SET application_status=? WHERE id=?',(status,job['id']))
            metrics['matched']+=1
    return metrics
