"""Evidence labels for visibility; inferred geography never scopes learning."""
import re,unicodedata
from .markets import country_of


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold()) if not unicodedata.combining(c))


def geography(job,markets):
    explicit=country_of(job,markets)
    if explicit:return {'status':'verified','country_id':explicit,'basis':'explicit_vacancy_location','evidence':job.get('country') or job.get('location','')}
    retained=job.get('geography') or {}
    if retained.get('status')=='inferred' and retained.get('country_id') in {m['id'] for m in markets}:return retained
    location=normalized(job.get('location',''))
    found=[];places=[]
    for market in markets:
        # Match an actually stated locality to a user-established city-country
        # pair, not the search's target, employer HQ or web domain.
        local=[p for p in market.get('locations',[]) if normalized(p)!=normalized(market['country']) and re.search(r'(?<!\w)'+re.escape(normalized(p))+r'(?!\w)',location)]
        if local:found.append(market['id']);places.extend(local)
    if len(set(found))==1:
        return {'status':'inferred','country_id':found[0],'basis':'user_supported_city_country_mapping','evidence':job.get('location',''),'places':places}
    return {'status':'unknown','country_id':None,'basis':'insufficient_or_conflicting_location_evidence','evidence':''}
