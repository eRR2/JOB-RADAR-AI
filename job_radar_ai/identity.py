"""Normalize transport noise only; retain requisition-bearing paths/query fields."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re


def linkedin_job_id(url):
    p=urlsplit(url)
    if p.scheme.lower()!='https' or p.username or p.password or p.port not in (None,443):return None
    if p.hostname!='linkedin.com' and not (p.hostname or '').endswith('.linkedin.com'):return None
    match=re.fullmatch(r'/jobs/view/(?:[^/]*-)?(\d{6,15})/?',p.path)
    return match[1] if match else None


def normalized_url(url):
    p = urlsplit(url)
    job_id=linkedin_job_id(url)
    if job_id:return 'https://www.linkedin.com/jobs/view/'+job_id
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('trk','trackingid')]
    host=p.netloc.lower()
    if p.scheme.lower()=='https' and p.port==443:host=host.removesuffix(':443')
    return urlunsplit((p.scheme.lower(), host, p.path, urlencode(sorted(query)), ''))
