"""Confirmed scope and observed location gates, without commuting or career guesses."""
import re
from .markets import country_of,query_locations
from .providers import ProviderError


def scope_for(profile,market):
    return next((m for m in profile.get('intent',{}).get('markets',[]) if m['id']==market['id']),None)


def valid_query(query,market,scope=None):
    location=query['location'].strip().casefold()
    if location in {v.casefold() for v in query_locations(market)}:
        return True
    return bool(scope and scope['remote']!='none' and query['remote']=='remote' and location==market['country'].casefold())


def bounded_plan(plan,market,profile,correct):
    scope=scope_for(profile,market)
    valid=[q for q in plan['queries'] if valid_query(q,market,scope)]
    if len(valid)!=len(plan['queries']):
        try:
            fixed=correct()
            valid.extend(q for q in fixed['queries'] if valid_query(q,market,scope))
        except (ValueError,ProviderError):
            pass
    seen=set();queries=[]
    for q in valid:
        key=(q['query'].casefold(),q['location'].casefold(),q['remote'])
        if key not in seen:queries.append(q);seen.add(key)
    return {**plan,'queries':queries}


def location_status(job,profile,market):
    scope=scope_for(profile,market)
    if not scope:return 'location_unknown'
    country=country_of(job,profile.get('markets') or [market]) or job.get('country_id')
    location=str(job.get('location','')).casefold()
    tokens={s.strip() for s in re.split('[,;/]',location) if s.strip()}
    preferred=scope['preferred'] or [market['country']]
    preferred=[p.casefold().removesuffix(', '+market['country'].casefold()) for p in preferred]
    secondary=[p.casefold().removesuffix(', '+market['country'].casefold()) for p in scope['secondary']]
    if country==market['id'] and scope.get('scope_type')=='country':return 'preferred'
    if country==market['id'] and any(p.casefold() in tokens or p.casefold()==location for p in preferred):
        return 'preferred'
    if country==market['id'] and any(p in tokens or p==location for p in secondary):
        return 'secondary_conditional'
    if job.get('workplace')=='remote' and job.get('remote_verified') is True and scope['remote']!='none':
        if country==market['id'] or (scope['remote']=='anywhere' and job.get('remote_scope')=='worldwide'):
            return 'verified_remote'
    if not country:return 'location_unknown'
    if country==market['id'] and scope.get('scope_type','mixed') in ('region','mixed') and not scope.get('relocation'):
        return 'location_unknown'
    # Country-only or unknown city does not establish a clear regional conflict.
    markets=profile.get('markets') or [market]
    country_tokens={m['country'].casefold() for m in markets}|{m['id'].casefold() for m in markets}|{'remote','hybrid','onsite'}
    if country!=market['id'] or tokens-country_tokens:
        if country==market['id'] and scope.get('relocation'):
            return 'secondary_conditional'
        return 'outside_preferred'
    return 'location_unknown'
