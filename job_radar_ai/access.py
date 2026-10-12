"""Source access state: finite 429 cooldowns, explicit denials, no in-run retries."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


def restriction(status, retry_after=None, previous=None, clock=None, interrupted=False):
    clock = clock or datetime.now(timezone.utc)
    attempts = (previous or {}).get('attempts', 0) + 1
    if status == 429 or interrupted:
        # No-header 429: 1h, 2h, 4h ... up to a day. A valid publisher value
        # is authoritative even if longer; never shorten its Retry-After.
        until = clock + timedelta(seconds=min(86400, 3600 * 2 ** min(attempts-1, 5)))
        if retry_after:
            try:
                if str(retry_after).strip().isdigit():
                    until = clock + timedelta(seconds=int(retry_after))
                else:
                    until = parsedate_to_datetime(retry_after)
                    if until.tzinfo is None: until = until.replace(tzinfo=timezone.utc)
                until = max(until, clock + timedelta(seconds=60))
            except (ValueError, TypeError, OverflowError):
                pass
        return {'state': 'cooling_down', 'until': until.isoformat(), 'http_status': status,
                'attempts': attempts, 'interrupted': interrupted}
    return {'state': 'restricted', 'until': None, 'http_status': status, 'attempts': attempts}


def active(state, clock=None):
    if not state: return False
    if state['state'] == 'available': return False
    if state['state'] == 'request_in_progress': return True
    if state['state'] == 'restricted': return True
    return datetime.fromisoformat(state['until']) > (clock or datetime.now(timezone.utc))


def linkedin_state(store):
    state = store.get('linkedin_access')
    if store.get('linkedin_pending') and not state:
        return {'state':'request_in_progress','until':None}
    if state and active(state): return state
    return {**(state or {}), 'state': 'available', 'until': None}
