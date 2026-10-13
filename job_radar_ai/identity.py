"""Normalize transport noise only; retain requisition-bearing paths/query fields."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def normalized_url(url):
    p = urlsplit(url)
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('trk','trackingid')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(sorted(query)), ''))
