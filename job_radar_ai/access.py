"""Publisher restrictions and session-only LinkedIn stops; no in-run retries."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


def restriction(status, retry_after=None, previous=None, clock=None, interrupted=False, session_only=False):
    clock = clock or datetime.now(timezone.utc)
    attempts = (previous or {}).get('attempts', 0) + 1
    if status == 429 or interrupted:
        publisher_retry_after = False
        # Only other publishers use an application-generated finite cooldown.
        # LinkedIn stops this session; a real future Retry-After remains authoritative.
        until = None if session_only else clock + timedelta(seconds=min(86400, 3600 * 2 ** min(attempts-1, 5)))
        if retry_after:
            try:
                if str(retry_after).strip().isdigit():
                    until = clock + timedelta(seconds=int(retry_after))
                else:
                    until = parsedate_to_datetime(retry_after)
                    if until.tzinfo is None: until = until.replace(tzinfo=timezone.utc)
                publisher_retry_after = until > clock
                if not session_only:until = max(until, clock + timedelta(seconds=60))
            except (ValueError, TypeError, OverflowError):
                pass
        if session_only and not publisher_retry_after:
            return {'state':'restricted','until':None,'http_status':status,
                    'session_only':True,'interrupted':interrupted}
        return {'state': 'cooling_down', 'until': until.isoformat(), 'http_status': status,
                'attempts': attempts, 'interrupted': interrupted,
                'publisher_retry_after':publisher_retry_after}
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
    if state and state.get('http_status') == 429:
        return {**state,'state':'restricted'}  # No second request in this session, even after expiry.
    if store.get('linkedin_stop'):
        return {'state':'restricted','until':None}
    return {**(state or {}), 'state': 'available', 'until': None}


def linkedin_key(key):
    if key.startswith('linkedin_'):return True
    host = key.removeprefix('public:access:').removeprefix('public:stop:')
    return host == 'linkedin.com' or host.endswith('.linkedin.com')


def durable_restriction(key, state):
    """Local LinkedIn 429/pending states never cross a manual search boundary."""
    if not state or state.get('session_only') or state.get('state') == 'request_in_progress':return False
    if linkedin_key(key) and (state.get('interrupted') or state.get('http_status') == 429):
        return bool(state.get('publisher_retry_after')) and active(state)
    return active(state)


def explicit_denial(value):
    # Legacy unstructured flags are disposable; recognizable publisher denials are not.
    text = str(value).lower()
    return any(word in text for word in ('401','403','406','999','robots','auth','captcha','checkpoint','redirect','publisher denial','publisher denied'))
