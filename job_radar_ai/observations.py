"""Vacancy facts grounded in actual native tool observations, never model prose."""
import hashlib,re
from urllib.parse import urlsplit
from .identity import normalized_url, linkedin_job_id
from .store import now

def observed_job(candidate, observations, rejected=None):
    url=candidate['url']
    def discard(reason):
        if rejected is not None:rejected.append({'url':url,'reason':reason})
        return None
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):return discard('unsafe_url')
        canonical=normalized_url(url)
    except ValueError:return discard('unsafe_url')
    sources=[]
    for o in observations:
        try:
            if o.get('url') and normalized_url(o['url'])==canonical:sources.append(o)
        except ValueError:continue
    if not sources:return discard('identity_not_observed')
    # Keep the original tool text. Model-written evidence/descriptions never enter it.
    text='\n'.join(dict.fromkeys(str(o.get(k,'')) for o in sources for k in ('title','snippet','text','content') if o.get(k)))
    if not text.strip():return discard('observed_text_missing')
    def corroborated(value):return value if value.strip() and value.casefold() in text.casefold() else ''
    country=corroborated(candidate['country']) if candidate['country'].strip() and candidate['country_quote'].strip() and candidate['country_quote'] in text and re.search(r'(?<!\w)'+re.escape(candidate['country'])+r'(?!\w)',candidate['country_quote'],re.I) and (not candidate['location'].strip() or candidate['location'].casefold() in candidate['country_quote'].casefold()) else ''
    job_id=linkedin_job_id(url)
    identity='linkedin:'+job_id if job_id else 'web:'+hashlib.sha256(canonical.encode()).hexdigest()[:24]
    job={'id':identity,'source_id':job_id if job_id else identity,'source':'LinkedIn indexed web' if job_id else 'Public web research',
            'url':canonical,'title':corroborated(candidate['title']) or sources[0].get('title','Observed opportunity'),
            'company':corroborated(candidate['company']), 'location':corroborated(candidate['location']), 'country':country,
            'country_evidence':candidate['country_quote'] if country else '', 'availability':'unknown',
            'evidence':'Observed by Codex web tool; indexed evidence does not prove vacancy openness.',
            'source_observations':[{'url':o['url'],'text':'\n'.join(str(o[k]) for k in ('title','snippet','text','content') if o.get(k)),'kind':'web_tool_observation','at':now()} for o in sources],
            'description_status':'not_attempted','evaluation_status':'preliminary_pending'}
    requisition=candidate.get('requisition_id','').strip()
    if requisition and re.search(r'(?<!\w)'+re.escape(requisition)+r'(?!\w)',text,re.I):
        job['requisition_id']=requisition
    inferred=candidate.get('geography_inference',{})
    read_text='\n'.join(o.get('text') or o.get('content','') for o in sources if o.get('observation_kind')=='page_read')
    if read_text.strip():
        job['partial_source_text']={'text':read_text,'url':url,'at':now(),'kind':'partial_verified_text','completeness':'unverified'}
    if not country and job['location'] and inferred.get('basis')=='city_country_mapping' and inferred.get('confidence')=='strong' and re.fullmatch('[A-Z]{2}',inferred.get('country_id','')):
        job['geography']={'status':'inferred','country_id':inferred['country_id'],'basis':'ai_city_country_mapping','evidence':job['location'],'explanation':inferred.get('explanation','')}
    from .listing_metadata import source_title_fields
    return source_title_fields(job)

