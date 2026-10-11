"""Budgeted transport to the attributed upstream CLI, never career matching."""
import hashlib
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from .providers import executable, bounded_process, ProviderError
from .store import now


class SourceError(RuntimeError):
    pass


class LinkedIn:
    def __init__(self, root, store, cancel, budgets):
        self.cli = Path(root).resolve() / 'integrations/linkedin/cli/src/cli.ts'
        self.store, self.cancel, self.budgets = store, cancel, budgets
        self.requests = self.cache_hits = 0
        self.last_request = 0
        self.last_cached = False

    def invoke(self, args, key, ttl):
        self.last_cached = False
        cached = self.store.cached(key, ttl)
        if cached is not None:
            self.last_cached = True
            self.cache_hits += 1
            return cached
        stop = self.store.get('linkedin_stop')
        if stop or self.store.get('linkedin_pending'):
            raise SourceError(stop or 'A previous request was interrupted; request extent is unknown. Review the source stop before continuing.')
        if self.requests >= self.budgets['requests']:
            raise SourceError('LinkedIn request budget reached.')
        binary = executable('bun')
        if not binary:
            raise SourceError('Bun is not installed. LinkedIn source unavailable.')
        previous=self.store.get('linkedin_last_attempt')
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(previous)).total_seconds() if previous else float('inf')
        delay = max(0, self.budgets['spacing']-elapsed)
        if self.cancel.wait(delay):
            raise ProviderError('Canceled by user.')
        self.store.set('linkedin_pending', True)
        self.store.set('linkedin_last_attempt',datetime.now(timezone.utc).isoformat())
        self.requests += 1
        self.last_request = time.monotonic()
        try:
            code, output, error = bounded_process(binary + ['run', str(self.cli)] + args + ['--format', 'json'],
                timeout=30, cancel=self.cancel)
        except ProviderError:
            self.store.set('linkedin_stop', 'Interrupted/timed-out LinkedIn request; request extent is unknown. No automatic retry.')
            raise
        self.store.set('linkedin_pending', False)
        if code:
            try:
                message = json.loads(error.strip().splitlines()[-1]).get('error', 'LinkedIn CLI failed')
            except (ValueError, IndexError):
                message = 'LinkedIn CLI failed'
            if any(flag in message.lower() for flag in ('access_restricted', '429', '403', '401', '999', 'captcha', 'authwall', 'redirect', 'checkpoint')):
                self.store.set('linkedin_stop', message[:500])
            raise SourceError(message[:500])
        try:
            result = json.loads(output)
        except ValueError as exc:
            raise SourceError('Malformed LinkedIn CLI response; not treated as empty results.') from exc
        return result

    def search(self, query, page=1):
        for key in ('query', 'location'):
            if not isinstance(query.get(key), str) or not query[key].strip() or len(query[key]) > 160 or query[key].startswith('-'):
                raise ValueError('Invalid AI search query/location.')
        if type(page) is not int or not 1 <= page <= 2 or query.get('remote') not in ('any', 'remote', 'hybrid', 'onsite'):
            raise ValueError('Invalid pagination/work arrangement.')
        args = ['search', '--query', query['query'], '--location', query['location'], '--page', str(page), '--limit', '10']
        if query['remote'] != 'any':
            args += ['--remote', query['remote']]
        key = 'linkedin:search:' + hashlib.sha256(json.dumps(args).encode()).hexdigest()
        result = self.invoke(args, key, 7200)
        if not isinstance(result, dict) or not isinstance(result.get('results'), list):
            raise SourceError('Invalid LinkedIn search response.')
        jobs = []
        for card in result['results']:
            if not isinstance(card, dict) or not re.fullmatch(r'\d{6,15}', str(card.get('id', ''))) or not isinstance(card.get('title'), str):
                raise SourceError('Invalid LinkedIn job identity.')
            job_id = str(card['id'])
            jobs.append({**card, 'id': 'linkedin:' + job_id, 'source_id': job_id, 'source': 'LinkedIn guest',
                         'url': f'https://www.linkedin.com/jobs/view/{job_id}', 'availability': 'unknown',
                         'evidence': 'Observed in guest search; availability unconfirmed'})
        if not self.last_cached:
            self.store.cache(key, result)
            self.store.set('linkedin_last_success', now())
        return jobs

    def detail(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'\d{6,15}', job_id):
            raise ValueError('Only verified numeric LinkedIn identities are accepted.')
        key = 'linkedin:detail:' + job_id
        result = self.invoke(['detail', job_id], key, 86400)
        if not isinstance(result, dict) or str(result.get('id')) != job_id:
            raise SourceError('Description identity mismatch.')
        description = result.get('description')
        if not isinstance(description, str) or len(description) < 100:
            raise SourceError('Full job description unavailable; not evaluated as complete.')
        if not self.last_cached:
            self.store.cache(key, result)
            self.store.set('linkedin_last_success', now())
        return {**result, 'id': 'linkedin:' + job_id, 'source_id': job_id, 'source': 'LinkedIn guest',
                'description': description[:60000], 'description_obtained': now(),
                'url': f'https://www.linkedin.com/jobs/view/{job_id}',
                'availability': 'closed_banner_observed' if result.get('isActive') is False else 'unknown',
                'evidence': 'Full guest description retrieved; absence of closed banner does not prove openness'}
