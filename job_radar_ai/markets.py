"""Market boundaries and conservative migration; career judgments belong to AI."""
import copy
import re

REGIONAL = ('city', 'region', 'commute', 'relocation', 'workplace', 'salary', 'hours')


def defaults():
    return [dict(id='DE', country='Germany', locations=['Germany'], languages='German / English', conditions='', hard_requirements=''),
            dict(id='NL', country='Netherlands', locations=['Netherlands'], languages='Dutch / English', conditions='', hard_requirements='')]


def validate_markets(markets):
    if not isinstance(markets, list) or not 1 <= len(markets) <= 6:
        raise ValueError('Configure one to six independent markets.')
    result = []
    for market in markets:
        if not isinstance(market, dict) or set(market) != {'id', 'country', 'locations', 'languages', 'conditions', 'hard_requirements'}:
            raise ValueError('Invalid market fields.')
        if not isinstance(market['id'], str) or not re.fullmatch('[A-Z]{2}', market['id']):
            raise ValueError('Use a two-letter country code for each market.')
        for key in ('country', 'languages', 'conditions', 'hard_requirements'):
            if not isinstance(market[key], str) or len(market[key]) > 4000:
                raise ValueError('Market fields must be text up to 4,000 characters.')
        if not market['country'].strip() or len(market['country']) > 100:
            raise ValueError('Supply a country name.')
        if not isinstance(market['locations'], list) or not 1 <= len(market['locations']) <= 10 or any(not isinstance(x, str) or not x.strip() or len(x) > 100 for x in market['locations']):
            raise ValueError('Supply one to ten market locations.')
        result.append(copy.deepcopy(market))
        if any(len(x)>160 for x in query_locations(market)):
            raise ValueError('Country-qualified search locations must fit 160 characters.')
    if len({m['id'] for m in result}) != len(result) or len({m['country'].casefold() for m in result}) != len(result):
        raise ValueError('Markets must have unique country codes and names.')
    return result


def country_of(job, markets):
    """Only explicit country fields or a complete country location token count.

    A query's country is provenance, never evidence of the listing's country.
    Cities, language and employers cannot prove a country.
    """
    tokens = {str(job.get('country', '')).strip().casefold()}
    tokens.update(x.strip().casefold() for x in str(job.get('location', '')).split(','))
    aliases = {'DE': {'germany', 'deutschland','deu'}, 'NL': {'netherlands', 'nederland', 'the netherlands','nld'},
               'US':{'usa','united states of america'},'GB':{'uk','gbr','great britain'},'CA':{'can'},
               'AU':{'aus'},'IN':{'ind'},'BR':{'bra'},'FR':{'fra'}}
    found = [m['id'] for m in markets if tokens & ({m['country'].casefold(), m['id'].casefold()} | aliases.get(m['id'], set()))]
    return found[0] if len(found) == 1 else None


def migrated_profile(profile):
    value = copy.deepcopy(profile)
    value['markets'] = defaults()
    geography = {k: value.get(k, '') for k in REGIONAL}
    # Only a standalone country preference has an unambiguous destination.
    country = country_of({'country': geography['region']}, value['markets'])
    if country:
        market = next(m for m in value['markets'] if m['id'] == country)
        market['conditions'] = '\n'.join(f'{k}: {v}' for k, v in geography.items() if v)
    value['market_migration'] = {'review_required': bool(any(geography.values()) and not country),
                                 'legacy_geography': geography, 'legacy_feedback_review': True}
    value['assessment_policy'] = 'evidence-v2'
    return value


def market_profile(profile, market, store):
    value = {k: v for k, v in profile.items() if k not in REGIONAL and k not in ('weights', 'markets', 'market_migration','legacy_profile','intent_review_edits','intent_summary_edit')}
    value['market'] = market
    if profile.get('intent'):
        value['intent']={**profile['intent'],'markets':[m for m in profile['intent']['markets'] if m['id']==market['id']],
                         'preferences':[p for p in profile['intent']['preferences'] if not p['scope'] or p['scope']==market['id']]}
        # Raw multi-country prose and archived settings stay in local storage.
        # Only the reviewed, scoped intent is authoritative for new inference.
        if profile.get('intent_confirmed'):
            for key in ('objectives','seniority','leadership','industries','strengths','followup_answers','looking_for'):
                value.pop(key,None)
    value['region'] = market['country']
    value['hard_requirements'] = '\n'.join(filter(None, [profile.get('hard_requirements', ''), market['hard_requirements']]))
    value['_preference_revision'] = store.preference_revision()
    value['_market_revision'] = store.preference_revision(market_id=market['id'])
    return value


def query_locations(market):
    country = market['country']
    return [x if x.casefold() == country.casefold() or x.casefold().endswith(', '+country.casefold()) else x+', '+country for x in market['locations']]


def validate_queries(queries, market):
    allowed = {x.casefold() for x in query_locations(market)}
    if any(q['location'].casefold() not in allowed for q in queries):
        raise ValueError('AI search location escaped the selected market; no query was sent.')
