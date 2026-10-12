"""Read-only public retrieval. Model prose is never a description source."""
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
from .linkedin import SourceError
from .providers import bounded_process, ProviderError
from .store import now
from .markets import country_of, defaults

MAX_BYTES = 1_000_000
AGENT = 'JOB-RADAR-AI/2.3 (+https://github.com/eRR2/JOB-RADAR-AI)'
DENIED = (401, 403, 406, 429, 999)


def publisher_group(host):
    for domain in ('greenhouse.io','lever.co','ashbyhq.com'):
        if host==domain or host.endswith('.'+domain):
            return domain
    return host


class RetrievalError(SourceError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def public_url(url):
    if not isinstance(url, str) or len(url) > 2000 or any(ord(c) <= 32 for c in url) or '\\' in url:
        raise RetrievalError('blocked', 'Unsafe public source URL.')
    try:
        p = urlsplit(url)
        host = p.hostname or ''
        if p.scheme != 'https' or not host or p.username or p.password or p.port not in (None, 443) or p.fragment:
            raise ValueError()
        if host.endswith('.') or host in ('localhost',) or '.' not in host or host.endswith(('.local', '.internal', '.localhost')):
            raise ValueError()
        # Never use this fetcher as a second route around LinkedIn's access policy.
        if host == 'linkedin.com' or host.endswith('.linkedin.com'):
            raise ValueError()
    except ValueError as exc:
        raise RetrievalError('blocked', 'Only public HTTPS sources on port 443 are permitted.') from exc
    return p


def public_addresses(host):
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not records or any(not ipaddress.ip_address(r[4][0]).is_global or ipaddress.ip_address(r[4][0]).is_multicast for r in records):
        raise RetrievalError('blocked', 'Source resolves to a private or reserved network; request refused.')
    return records


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Resolve once, validate EVERY answer, then connect to that exact numeric IP.
        # TLS still verifies the original hostname. No proxy, cookies or credentials.
        family, socktype, protocol, _, address = public_addresses(self.host)[0]
        raw = socket.socket(family, socktype, protocol)
        raw.settimeout(self.timeout)
        try:
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def request_public(url, max_bytes=MAX_BYTES):
    """Worker entry: one request, no automatic redirects/retries/decompression."""
    p = public_url(url)
    conn = PinnedHTTPS(p.hostname, timeout=8, context=ssl.create_default_context())
    try:
        conn.request('GET', p.path + ('?' + p.query if p.query else '') or '/', headers={
            'User-Agent': AGENT, 'Accept': 'application/json,text/html,text/plain', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        status = response.status
        if status in DENIED:
            raise RetrievalError('blocked', 'Publisher access restriction; no automatic retry.')
        if status in (301, 302, 303, 307, 308):
            return {'redirect': response.getheader('Location', ''), 'status': status}
        if status == 404 or status == 410:
            raise RetrievalError('unavailable', 'Verified source unavailable (HTTP ' + str(status) + ').')
        if status != 200:
            raise RetrievalError('failed', 'Public source request failed (HTTP ' + str(status) + '); no retry.')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise RetrievalError('incomplete', 'Compressed response refused; no retry.')
        length = response.getheader('Content-Length')
        if length and (not length.isdigit() or int(length) > max_bytes):
            raise RetrievalError('incomplete', 'Source exceeds response size limit.')
        content_type = response.getheader('Content-Type', '').lower()
        if not any(t in content_type for t in ('application/json', 'text/html', 'text/plain', 'application/ld+json')):
            raise RetrievalError('incomplete', 'Unsupported public source content type.')
        deadline = time.monotonic() + 15
        body = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise RetrievalError('failed', 'Public source deadline reached; no retry.')
            block = response.read1(min(16384, max_bytes + 1 - len(body)))
            if not block:
                break
            body.extend(block)
            if len(body) > max_bytes:
                raise RetrievalError('incomplete', 'Source exceeds response size limit.')
        text = bytes(body).decode('utf-8', errors='replace')
        if re.search(r'captcha|authwall|access denied|verify you are human|cf-chl-', text, re.I):
            raise RetrievalError('blocked', 'Publisher challenge/access restriction; no retry or alternate route.')
        return {'url': url, 'text': text, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'at': now()}
    finally:
        conn.close()


def worker_request(url, cancel=None):
    # The process bound also covers DNS and slow response reads.
    try:
        code, output, _ = bounded_process([sys.executable, '-m', 'job_radar_ai.source_worker', url],
                                         timeout=25, cancel=cancel, max_output=1_500_000)
        result = json.loads(output)
        if code:
            raise RetrievalError(result.get('status', 'failed'), result['error'])
        return result
    except (ProviderError, ValueError) as exc:
        raise RetrievalError('failed', 'Source worker stopped or timed out; no retry.') from exc


class PublicFetcher:
    def __init__(self, store, cancel=None, budget=12, request=None):
        self.store, self.cancel, self.budget = store, cancel, budget
        self.request = request or (lambda url: worker_request(url, cancel))
        self.requests = self.cache_hits = 0
        self.robots = {}

    def get(self, url, api=False):
        origin = public_url(url).hostname
        key = 'public:page:' + hashlib.sha256(url.encode()).hexdigest()
        cached = self.store.cached(key, 86400)
        if cached:
            self.cache_hits += 1
            return cached
        # Same publisher stop survives restarts and cannot be reset by this module.
        group=publisher_group(origin)
        if self.store.get('public:stop:' + origin) or self.store.get('public:stop:'+group):
            raise RetrievalError('blocked', 'Publisher access is stopped; no new request.')
        if not api:
            self.check_robots(url)
        current = url
        try:
            for _ in range(3):
                p = public_url(current)
                if p.hostname != origin:
                    raise RetrievalError('blocked', 'Cross-host redirect refused; no substitute route.')
                if self.cancel and self.cancel.is_set():
                    raise RetrievalError('failed', 'Canceled; no new source request.')
                if self.requests >= self.budget:
                    raise RetrievalError('budget_deferred', 'Public source request budget reached.')
                self.requests += 1
                result = self.request(current)
                if 'redirect' in result:
                    target = urljoin(current, result['redirect'])
                    parsed_target=public_url(target)
                    if parsed_target.hostname!=origin or re.search(r'/(login|signin|sign-in|authwall|checkpoint|captcha)(/|$)',parsed_target.path,re.I):
                        raise RetrievalError('blocked','Cross-host/auth redirect refused; no substitute request.')
                    if not api:
                        self.check_robots(target)
                    current = target
                    continue
                self.store.cache(key, result)
                return result
            raise RetrievalError('blocked', 'Redirect limit reached; no retry.')
        except RetrievalError as exc:
            if exc.status == 'blocked':
                self.store.set('public:stop:' + origin, str(exc))
                self.store.set('public:stop:' + group, str(exc))
            raise

    def check_robots(self, url):
        p = public_url(url)
        if p.hostname not in self.robots:
            robots_url = 'https://' + p.hostname + '/robots.txt'
            # This special API flag avoids recursively checking robots itself.
            try:
                page = self.get(robots_url, api=True)
                rules = RobotFileParser()
                rules.parse(page['text'].splitlines())
            except RetrievalError as exc:
                if exc.status != 'unavailable':
                    raise
                rules = RobotFileParser()
                rules.parse([])  # Missing robots, not denied robots.
            self.robots[p.hostname] = rules
        if not self.robots[p.hostname].can_fetch(AGENT, url):
            raise RetrievalError('blocked', 'Publisher robots policy forbids this source.')


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.scripts, self.links = [], [], []
        self.hidden = 0
        self.ld = False
        self.script = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.hidden += 1
            self.ld = tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json'
            self.script = []
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag in ('p', 'div', 'li', 'br', 'h1', 'h2', 'h3'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            if self.ld:
                self.scripts.append(''.join(self.script))
            self.ld = False
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.ld:
            self.script.append(data)
        if not self.hidden:
            self.parts.append(data)


def plain(text):
    parser = TextParser()
    parser.feed(unescape(unescape(str(text))))
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_objects(child)


def structured_jobs(page):
    parser = TextParser()
    parser.feed(page['text'])
    jobs = []
    for script in parser.scripts:
        try:
            values = list(json_objects(json.loads(script)))
        except (ValueError, RecursionError):
            continue
        for item in values:
            types = item.get('@type', [])
            types = types if isinstance(types, list) else [types]
            if 'JobPosting' not in types:
                continue
            org = item.get('hiringOrganization') or {}
            loc = item.get('jobLocation') or []
            loc = loc if isinstance(loc, list) else [loc]
            addresses = [v.get('address', {}) for v in loc if isinstance(v, dict)]
            locations = []
            for address in addresses:
                if not isinstance(address, dict):
                    continue
                country = address.get('addressCountry', '')
                country = country.get('name', '') if isinstance(country, dict) else country
                locations.append(', '.join(str(v) for v in (address.get('addressLocality'), address.get('addressRegion'), country) if v))
            identifier = item.get('identifier') or ''
            identifier = identifier.get('value', '') if isinstance(identifier, dict) else identifier
            jobs.append({'title': item.get('title', ''), 'company': org.get('name', '') if isinstance(org, dict) else org,
                         'location': '; '.join(locations), 'description': plain(item.get('description', '')),
                         'requisition_id': str(identifier), 'source_url': page['url'], 'evidence': page})
    return jobs


def exact(value):
    return ' '.join(str(value).casefold().split())


def match_identity(job, candidate, markets=None):
    """Conservative exact identity gate; no fuzzy title/city country inference."""
    for field in ('company', 'title'):
        if not job.get(field) or exact(job[field]) != exact(candidate.get(field, '')):
            raise RetrievalError('unverified', 'Alternative employer/title does not exactly match the observed vacancy.')
    markets = markets or defaults()
    original_country = country_of(job, markets)
    alternative_country = country_of(candidate, markets)
    if not original_country or original_country != alternative_country:
        raise RetrievalError('unverified', 'Country identity unverified or conflicting; no description associated.')
    requisition = job.get('requisition_id')
    if requisition and str(requisition) != str(candidate.get('requisition_id', '')):
        raise RetrievalError('unverified', 'Exact requisition identity mismatch.')
    city = exact(job.get('location', '').split(',')[0])
    cities = {exact(part) for part in re.split('[,;]', candidate.get('location', ''))}
    # Even without a known requisition, employer + exact title + city + explicit
    # country are all required. Ambiguous multiple matching postings are refused.
    if not city or city not in cities:
        raise RetrievalError('unverified', 'Exact locality identity missing or conflicting.')
    if len(candidate.get('description', '')) < 100:
        raise RetrievalError('incomplete', 'Full source description incomplete.')
    if len(candidate['description']) > 60000:
        raise RetrievalError('incomplete', 'Full source description exceeds storage bound; no truncation.')
    return candidate


def retrieve_candidates(url, fetcher, employer_url=''):
    """Three documented read-only ATS APIs, otherwise public JobPosting JSON-LD."""
    p = public_url(url)
    parts = p.path.strip('/').split('/')
    if fetcher.store.get('public:stop:' + p.hostname) or fetcher.store.get('public:stop:'+publisher_group(p.hostname)):
        raise RetrievalError('blocked', 'Publisher stopped; no alternate route attempted.')
    gh = p.hostname in ('boards.greenhouse.io', 'job-boards.greenhouse.io') and len(parts) == 3 and parts[1] == 'jobs' and parts[2].isdigit()
    lever = p.hostname in ('jobs.lever.co', 'jobs.eu.lever.co') and len(parts) == 2
    ashby = p.hostname == 'jobs.ashbyhq.com' and len(parts) == 2
    if not (gh or lever or ashby):
        return structured_jobs(fetcher.get(url))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', parts[0]) or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', parts[-1]):
        raise RetrievalError('blocked', 'Invalid public board identity.')
    company = ''
    if lever or ashby:
        # These feeds do not name the employer. A model-proposed board/company
        # association cannot prove ownership: require fetched Organization and
        # an exact posting link on its own HTTPS employer page.
        if not employer_url:
            raise RetrievalError('unverified', 'Employer ownership URL required for this public board.')
        employer = fetcher.get(employer_url)
        parser = TextParser(); parser.feed(employer['text'])
        if url not in [urljoin(employer['url'], link) for link in parser.links]:
            raise RetrievalError('unverified', 'Employer page does not link this exact posting.')
        names = set()
        for script in parser.scripts:
            try:
                for obj in json_objects(json.loads(script)):
                    if obj.get('@type') == 'Organization' and obj.get('url') and urlsplit(obj['url']).hostname == urlsplit(employer['url']).hostname:
                        names.add(obj.get('name', ''))
            except (ValueError, TypeError, RecursionError):
                continue
        if len(names) != 1 or not next(iter(names)):
            raise RetrievalError('unverified', 'Public employer ownership evidence unavailable.')
        company = next(iter(names))
    if gh:
        endpoint = f'https://boards-api.greenhouse.io/v1/boards/{parts[0]}/jobs/{parts[2]}'
    elif lever:
        host = 'api.eu.lever.co' if p.hostname == 'jobs.eu.lever.co' else 'api.lever.co'
        endpoint = f'https://{host}/v0/postings/{parts[0]}/{parts[1]}?mode=json'
    else:
        endpoint = f'https://api.ashbyhq.com/posting-api/job-board/{parts[0]}'
    # A denied hosted board must never be accessed through its API instead.
    if fetcher.store.get('public:stop:' + p.hostname) or fetcher.store.get('public:stop:'+publisher_group(p.hostname)):
        raise RetrievalError('blocked', 'Hosted publisher stopped; alternate API route refused.')
    page = fetcher.get(endpoint, api=True)
    try:
        data = json.loads(page['text'])
        if gh:
            if str(data['id']) != parts[2]:
                raise ValueError()
            return [{'title': data['title'], 'company': data.get('company_name', ''), 'location': data['location']['name'],
                     'requisition_id': str(data.get('requisition_id') or ''), 'description': plain(data['content']), 'source_url': url, 'evidence': page}]
        if lever:
            if str(data['id']) != parts[1]:
                raise ValueError()
            description = data.get('descriptionPlain') or plain(data.get('description', ''))
            for section in data.get('lists', []):
                description += '\n' + section.get('text', '') + '\n' + plain(section.get('content', ''))
            description += '\n' + (data.get('additionalPlain') or plain(data.get('additional', '')))
            return [{'title': data['text'], 'company': company, 'location': data['categories']['location'], 'requisition_id': str(data.get('requisitionId') or ''),
                     'description': description.strip(), 'source_url': url, 'evidence': page}]
        matches = [j for j in data['jobs'] if j.get('jobUrl', '').rstrip('/') == url.rstrip('/') and j.get('isListed', True)]
        return [{'title': j['title'], 'company': company, 'location': j['location'], 'country': j.get('address', {}).get('postalAddress', {}).get('addressCountry', ''),
                 'requisition_id': str(j.get('requisitionId') or ''), 'description': j.get('descriptionPlain') or plain(j.get('descriptionHtml', '')), 'source_url': url, 'evidence': page} for j in matches]
    except (ValueError, KeyError, TypeError) as exc:
        raise RetrievalError('unverified', 'Public API response/identity could not be verified.') from exc
