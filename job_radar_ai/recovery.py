"""Description recovery for existing identities, sharing the Hunter run gate."""
import threading
from .sources import PublicFetcher, RetrievalError, verified_matches, match_identity
from .linkedin import LinkedIn, SourceError
from .providers import Provider, ProviderError
from .markets import country_of, market_profile
from .hunter import EVALUATION_TASK, prepare_evaluation, source_context, DEFAULT_BUDGETS
from .store import now
import hashlib
import re
import time
from .access import linkedin_state


def description_state(job, store):
    if job.get('description'):
        return job.get('description_status', 'available')
    if job.get('description_status'):
        return job['description_status']
    # Recover the distinction for pre-Phase-3 databases without migrating rows.
    for run in store.runs():
        outcomes = [run['payload']] + list(run['payload'].get('markets', {}).values())
        for outcome in outcomes:
            for failure in outcome.get('description_failures', []):
                if failure.get('job_id') == job['id']:
                    reason = failure.get('reason', '').lower()
                    if any(s in reason for s in ('restricted', 'access', 'stopped', '403', '429', '401')):
                        return 'blocked'
                    if 'budget' in reason:
                        return 'budget_deferred'
                    if 'incomplete' in reason or 'full job description' in reason:
                        return 'incomplete'
                    return 'failed'
    return 'not_attempted'


class DescriptionResolver:
    def __init__(self, hunter, ai=None, linkedin=None, fetcher=None):
        self.hunter, self.store, self.root = hunter, hunter.store, hunter.root
        self.ai, self.linkedin, self.fetcher = ai, linkedin, fetcher

    def start(self, job_id=None, supplied=None, selection=None):
        with self.hunter.lock:
            profile = self.store.get('profile') or {}
            if not profile.get('consent'):
                raise ValueError('Provider-processing consent and a saved profile are required.')
            jobs = self.store.jobs()
            if job_id:
                jobs = [j for j in jobs if j['id'] == job_id]
                if not jobs:
                    raise ValueError('Unknown job identity.')
            else:
                jobs = [j for j in jobs if not j.get('description')]
                if not self.store.v5:jobs=jobs[:10]
            if not jobs:
                raise ValueError('No missing descriptions to complete.')
            if supplied is not None:
                if not job_id or not isinstance(supplied, str) or not 100 <= len(supplied.strip()) <= 60000:
                    raise ValueError('Supply 100–60,000 characters for one existing vacancy.')
            if selection is not None and (not job_id or not isinstance(selection,str) or selection not in {c['candidate_id'] for c in jobs[0].get('description_candidates',[])}):
                raise ValueError('Confirm a retained verified candidate for this exact vacancy.')
            run_id = self.store.start_run(profile['provider'])
            if run_id is None:
                return None
            self.hunter.cancel = threading.Event()
            self.hunter.thread = threading.Thread(target=self.execute, args=(run_id, jobs, self.hunter.cancel, supplied, selection), daemon=True)
            self.hunter.thread.start()
            return run_id

    def execute(self, run_id, jobs, cancel, supplied=None, selection=None):
        profile = self.store.get('profile') or {}
        budgets = self.store.get('budgets', DEFAULT_BUDGETS)
        if self.store.v5:budgets={**budgets,'requests':float('inf'),'details':float('inf')}
        source = self.linkedin or LinkedIn(self.root, self.store, cancel, budgets)
        fetcher = self.fetcher or PublicFetcher(self.store, cancel, budget=float('inf') if self.store.v5 else min(16, budgets['requests']),publisher_budget=None if self.store.v5 else 4)
        ai = self.ai
        metrics = {key: 0 for key in ('attempted', 'recovered', 'unavailable', 'blocked', 'evaluated', 'remaining')}
        metrics['remaining']=sum(not j.get('description') for j in jobs)
        payload = {'kind': 'description_recovery', 'job_ids': [j['id'] for j in jobs], 'metrics': metrics,
                   'warnings': [], 'sources': [], 'outcomes':[], 'new_jobs': 0, 'previously_seen': len(jobs), 'descriptions': 0}
        try:
            deadline=time.monotonic()+900
            if self.store.v5:fetcher.deadline=deadline
            for job in jobs if self.store.v5 else jobs[:10]:
                if time.monotonic()>=deadline:
                    payload['warnings'].append('Recovery time window reached; remaining opportunities retained.');break
                if cancel.is_set():
                    raise ProviderError('Canceled by user.')
                metrics['attempted'] += 1
                self.store.update_run(run_id, 'Finding full description', payload)
                candidate = None
                attempts = []
                evaluated=False
                if job.get('description'):
                    candidate = job
                elif selection is not None:
                    chosen=next(c for c in job.get('description_candidates',[]) if c['candidate_id']==selection)
                    full=match_identity(job,chosen['posting'],profile.get('markets'))
                    ev=full['evidence']
                    evidence={k:ev[k] for k in ('url','sha256','bytes','at')}
                    evidence.update({'kind':'public_verified','posting_url':full['source_url'],'identity':'User confirmed an ambiguous cross-source association; fetched source text retained.'})
                    self.save_description(job,full['description'],evidence,run_id)
                    self.store.upsert_job({'id':job['id'],'description_candidates':[]},run_id)
                    candidate=next(j for j in self.store.jobs() if j['id']==job['id'])
                elif supplied is not None:
                    self.save_description(job, supplied.strip(), {'kind': 'user_supplied', 'url': '', 'at': now(),
                                          'identity': 'User associated this text; publisher retrieval unverified.'}, run_id)
                    candidate = next(j for j in self.store.jobs() if j['id'] == job['id'])
                else:
                    cached = self.store.cached('linkedin:detail:' + job.get('source_id', ''), 86400)
                    li_stopped=linkedin_state(self.store)['state']!='available' if self.store.v5 else bool(self.store.get('linkedin_stop') or self.store.get('linkedin_pending') or (job['id'].startswith('linkedin:') and job.get('description_status')=='blocked'))
                    if job['id'].startswith('linkedin:') and job.get('source_id') and (cached or (profile.get('linkedin_consent') and not li_stopped)):
                        requests_before=source.requests
                        try:
                            if source.requests >= min(budgets['details'], budgets['requests']) and not cached:
                                raise RetrievalError('budget_deferred', 'LinkedIn detail budget reached; detail not attempted.')
                            detail = source.detail(job['source_id'])
                            # Preserve original card identity; do not attach a different employer's description.
                            if any(job.get(k) and detail.get(k) and str(job[k]).casefold() != str(detail[k]).casefold() for k in ('title', 'company')):
                                raise RetrievalError('unverified', 'LinkedIn employer/title mismatch.')
                            if len(detail.get('description', '')) < 100:
                                raise RetrievalError('incomplete', 'LinkedIn description incomplete.')
                            self.save_description(job, detail['description'], {'kind': 'linkedin', 'url': job['url'], 'at': now(),
                                                  'identity': 'Exact LinkedIn numeric job ID; observed employer/title retained.'}, run_id)
                            candidate = next(j for j in self.store.jobs() if j['id'] == job['id'])
                        except SourceError as exc:
                            status = getattr(exc, 'status', None) or ('blocked' if self.store.get('linkedin_stop') or self.store.get('linkedin_pending') else 'budget_deferred' if 'budget' in str(exc).lower() else 'incomplete' if 'description' in str(exc).lower() else 'failed')
                            sent=source.requests>requests_before
                            http=re.search(r'\b(401|403|406|429|999)\b',str(exc)) if sent else None
                            attempts.append({'source': 'LinkedIn', 'status': status, 'reason': str(exc),'request_sent':sent,'http_status':int(http.group(1)) if http else None})
                    if not candidate and li_stopped:
                        attempts.append({'source':'LinkedIn','status':'blocked_shared_stop','reason':'Persisted LinkedIn stop; no LinkedIn request sent. Independent official publication remains permitted.','request_sent':False})
                    if not candidate and profile.get('secondary'):
                        ai = ai or Provider(profile['provider'], self.root / '.private/ai')
                        try:
                            located = ai.run('resolve', 'Find up to two corresponding official employer posting URLs or documented Greenhouse/Lever/Ashby/SmartRecruiters/Workable postings. Never invent text. Exact employer, title, locality, country and requisition if known must correspond. Supply employer_url for public boards; do not retry denied sources.',
                                            {'job': {k: job.get(k) for k in ('title', 'company', 'location', 'url', 'requisition_id')},
                                             'stopped_hosts': [a['source'] for a in attempts if a['status'] == 'blocked']}, research=True, cancel=cancel)
                            for link in located['sources']:
                                requests_before=fetcher.requests
                                try:
                                    matching=verified_matches(job,link['url'],fetcher,link['employer_url'],profile.get('markets'))
                                    if len(matching)>1:
                                        self.store.upsert_job({'id':job['id'],'description_candidates':[{'candidate_id':hashlib.sha256((m['source_url']+'\n'+m.get('requisition_id','')+'\n'+m['description']).encode()).hexdigest(),'url':m['source_url'],'company':m['company'],'title':m['title'],'location':m['location'],'requisition_id':m.get('requisition_id',''),'posting':m} for m in matching[:2]]},run_id)
                                    if len(matching) != 1:
                                        raise RetrievalError('unverified', 'No unique verified employer/title/country/locality/requisition match; source text not associated.')
                                    full = matching[0]
                                    ev = full['evidence']
                                    evidence = {k: ev[k] for k in ('url', 'sha256', 'bytes', 'at')}
                                    evidence.update({'kind': 'public_verified', 'posting_url': full['source_url'], 'requisition_id': full['requisition_id'],
                                                     'identity': {k: full.get(k) for k in ('company', 'title', 'location', 'country')}})
                                    self.save_description(job, full['description'], evidence, run_id)
                                    candidate = next(j for j in self.store.jobs() if j['id'] == job['id'])
                                    break
                                except RetrievalError as exc:
                                    attempts.append({'source': link['url'], 'status': exc.status, 'reason': str(exc),'request_sent':fetcher.requests>requests_before,'http_status':exc.http_status})
                                    if exc.status == 'blocked':
                                        break
                        except (ProviderError,ValueError) as exc:
                            attempts.append({'source': 'AI source locator', 'status': 'failed', 'reason': str(exc)})
                if candidate:
                    metrics['recovered'] += int(not job.get('description'))
                    metrics['remaining'] -= int(not job.get('description'))
                    payload['sources'].append({'job_id':job['id'],'source':candidate.get('description_source_url') or 'Stored description',
                                               'status':'success','reason':candidate.get('description_status','available'),'count':1})
                    try:
                        country = country_of(candidate, profile.get('markets', []))
                        market = next((m for m in profile.get('markets', []) if m['id'] == country), None)
                        if not market:
                            raise ValueError('Description retained; configured verified country required for automatic assessment.')
                        candidate['country_id'] = country
                        ai = ai or Provider(profile['provider'], self.root / '.private/ai')
                        scoped = market_profile(profile, market, self.store)
                        result = ai.run('evaluation', EVALUATION_TASK, {'profile': scoped, 'jobs': [source_context(candidate)],
                                        'feedback': self.store.feedback(country), 'learned_preferences': self.store.get('learned:global', []) + self.store.get('learned:' + country, [])}, cancel=cancel)
                        if len(result['evaluations']) != 1:
                            raise ValueError('One verified existing identity must receive exactly one assessment.')
                        self.store.evaluate(job['id'], prepare_evaluation(result['evaluations'][0], candidate, scoped), country)
                        metrics['evaluated'] += 1
                        evaluated=True
                    except (ValueError, ProviderError) as exc:
                        payload['warnings'].append(str(exc))
                else:
                    states = [a['status'] for a in attempts]
                    status = next((s for s in ('blocked', 'incomplete', 'unavailable', 'unverified', 'failed', 'budget_deferred','blocked_shared_stop') if s in states), 'not_attempted')
                    self.store.upsert_job({'id': job['id'], 'description_status': status, 'description_attempts': attempts, 'description_checked': now()}, run_id)
                    metrics['blocked' if status in ('blocked','blocked_shared_stop') else 'unavailable'] += 1
                payload['outcomes'].append({'job_id':job['id'],'country_id':country_of(job,profile.get('markets',[])),
                                            'status':candidate.get('description_status','available') if candidate else status,
                                            'recovered':bool(candidate and not job.get('description')),'available':bool(candidate),'evaluated':evaluated})
                payload['sources'].extend({'job_id': job['id'], **a} for a in attempts)
                self.store.update_run(run_id, 'Description outcome recorded', payload)
        except Exception as exc:
            payload['warnings'].append(str(exc) if isinstance(exc, (ValueError, SourceError, ProviderError)) else 'Description recovery failed; original identities and history retained.')
        metrics['remaining'] = sum(not j.get('description') for j in self.store.jobs() if j['id'] in payload['job_ids'])
        payload.update({'descriptions': metrics['recovered'], 'evaluated': metrics['evaluated'], 'requests': source.requests + fetcher.requests,
                        'cache_hits': source.cache_hits + fetcher.cache_hits, 'report': 'Description recovery: verified retrieval and user-supplied text are labeled separately.'})
        payload['shared_stop_skips']=sum(a.get('status')=='blocked_shared_stop' for a in payload['sources'])
        payload['http_denials']=sum(a.get('http_status') in (401,403,406,429,999) for a in payload['sources'])
        payload['status_counts']={status:sum(o['status']==status for o in payload['outcomes']) for status in ('not_attempted','budget_deferred','blocked','blocked_shared_stop','unavailable','incomplete','unverified','public_verified','linkedin','user_supplied')}
        status = 'canceled' if cancel.is_set() else 'partial' if metrics['remaining'] or payload['warnings'] else 'completed'
        self.store.update_run(run_id, 'Description recovery finished', payload, status)

    def save_description(self, job, text, evidence, run_id):
        if not 100 <= len(text) <= 60000:
            raise RetrievalError('incomplete', 'Description outside full-text storage bounds.')
        self.store.upsert_job({'id': job['id'], 'description': text, 'description_obtained': now(),
                               'description_source': evidence, 'description_source_url': evidence.get('posting_url', evidence['url']),
                               'description_status': evidence['kind']}, run_id)
