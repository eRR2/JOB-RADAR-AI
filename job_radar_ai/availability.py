"""Source-scoped publication evidence; transport failures never prove closure."""
from .identity import normalized_url,linkedin_job_id
from urllib.parse import urlsplit


def observation(job,url,status,quote='',checked_at=None,provenance='publisher_observed',http_status=None,reported_at=None):
    source=normalized_url(url)
    parsed=urlsplit(source)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Publication evidence requires a safe HTTPS source.')
    identity=linkedin_job_id(source)
    if identity and identity!=linkedin_job_id(job.get('url','')):
        raise ValueError('Availability evidence refers to another LinkedIn identity.')
    if status not in ('open','closed','unknown') or (status!='unknown' and not quote.strip()):
        raise ValueError('Publication state requires literal evidence.')
    if http_status in (401,403,404,406,410,429,999) and status!='unknown':
        raise ValueError('Access or missing-address status cannot prove publication closure.')
    return {'url':source,'channel':'linkedin' if identity else 'publisher','status':status,
        'quote':quote[:1500],'checked_at':checked_at,'reported_at':reported_at,
        'provenance':provenance,'http_status':http_status,
        'access_status':'missing_or_moved' if http_status in (404,410) else 'restricted' if http_status in (401,403,406,429,999) else 'observed'}


def merge_states(*collections):
    result={}
    for collection in collections:
        for url,item in (collection or {}).items():
            previous=result.get(url)
            if previous and previous.get('status') in ('closed','open') and item.get('status')=='unknown':
                result[url]={**previous,'last_access':item}
            else:result[url]=item
    return result


def closed_for_review(job):
    source=(job.get('description_source') or {}).get('url')
    states=job.get('source_availability',{})
    if source and normalized_url(source) in states:
        state=states[normalized_url(source)]
        if state['status']=='closed':return True
        if state['status']=='open':return False
        original=job.get('freshness',{}).get('source_url') or job.get('url','')
        if original and normalized_url(source)!=normalized_url(original) and state.get('provenance')=='publisher_observed' and state.get('access_status')=='observed':return False
    return job.get('availability')=='closed_banner_observed' or job.get('freshness',{}).get('status')=='confirmed_closed'
