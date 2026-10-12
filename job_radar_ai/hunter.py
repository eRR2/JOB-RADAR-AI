"""Bounded AI-owned search workflow. Transport and safety are deterministic."""
import hashlib
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit
from .contracts import validate
from .linkedin import LinkedIn, SourceError
from .providers import Provider, ProviderError
from .store import now
from .markets import market_profile, query_locations, validate_queries, country_of
from .sources import PublicFetcher, retrieve_candidates, match_identity, verified_matches, RetrievalError
from .geography import bounded_plan, valid_query, scope_for, location_status
from .ats import PublicBoards, sampled, observe, STATUS as ATS_STATUS

DEFAULT_BUDGETS = {'searches': 3, 'pages': 1, 'details': 5, 'requests': 8, 'spacing': 5}


def profile_signature(profile):
    import json
    keys = ['cv_text', 'objectives', 'seniority', 'leadership', 'industries', 'strengths', 'city', 'region',
            'commute', 'relocation', 'workplace', 'salary', 'hours', 'unwanted', 'hard_requirements', 'followup_answers', 'interpreted', 'intent', 'looking_for', 'market', '_market_revision', '_preference_revision']
    return hashlib.sha256(json.dumps({k:profile.get(k,0 if k=='_preference_revision' else None) for k in keys},sort_keys=True).encode()).hexdigest()


EVALUATION_TASK = ('Analyze EVERY supplied full description, not titles. Score each preference dimension from 0 to 100, or null when unknown. '
    'Produce separate ATS readiness and HR assessment, exact quotes from original CV and job text, truthful CV changes. '
    'The hard_requirements array refers ONLY to nonempty lines in profile.hard_requirements: copy each exact line once; '
    'if that field is empty return hard_requirements: []. Do NOT put employer job qualifications in that array: assess those in ATS/HR and evidence. '
    'Unknown salary and working arrangements have null scores and require verification. Never claim a proprietary ATS score. '
    'Distinguish domain, transferable and stretch fit. CV quotes must be exact substrings of cv_text; use an empty cv_quote where evidence is missing. '
    'Your prose and recommendation must agree with the structured evidence. All jobs remain visible.')


def folded(text):
    return ' '.join(str(text).casefold().split())


def source_context(job):
    # Stored jobs also contain all-market assessments, feedback and application
    # outcomes. Only source facts cross into triage/evaluation; explicit learning
    # arrives through the separately scoped feedback channel.
    fields=('id','source_id','source','title','company','location','country_id','url','description','availability','evidence','description_obtained','description_source_url','description_status','workplace','remote_verified','location_status')
    return {key:job[key] for key in fields if key in job}


def prepare_evaluation(value, job, profile):
    # Validate quotes against actual source/CV, not against the model's interpretation.
    validate('evaluation', {'evaluations': [value], 'report': ''})
    if value['job_id'] != job['id']:
        raise ValueError('AI evaluation identity mismatch.')
    description = folded(job.get('description', ''))
    cv = folded(profile.get('cv_text', ''))
    for item in value['evidence']:
        if not item['job_quote'].strip() or folded(item['job_quote']) not in description:
            raise ValueError('AI job evidence quote was not found in the retrieved description.')
        if item['cv_quote'].strip() and folded(item['cv_quote']) not in cv:
            raise ValueError('AI CV evidence quote was not found in the actual CV.')
    required = [line.strip() for line in profile.get('hard_requirements', '').splitlines() if line.strip()]
    if sorted(required) != sorted(item['requirement'] for item in value['hard_requirements']):
        raise ValueError('AI must assess every unchanged hard requirement exactly once.')
    for item in value['hard_requirements']:
        if item['status'] != 'unknown' and (not item['job_quote'].strip() or folded(item['job_quote']) not in description):
            raise ValueError('Hard-constraint claim lacks exact source evidence.')
    value = dict(value)
    value['assessment_version'] = 2
    value['evaluated_at'] = now()
    value['profile_signature'] = profile_signature(profile)
    value['recommend'] = value['recommend'] and value['category'] != 'unrelated' and bool(value['evidence']) and not any(item['status'] == 'violated' for item in value['hard_requirements']) and job.get('availability') != 'closed_banner_observed'
    if profile.get('market'):
        # An explicit different country is never eligible in this market.
        known=job.get('country_id')
        if known and known!=profile['market']['id']:
            value['recommend']=False
        value['location_status']=location_status(job,profile,profile['market'])
        if value['location_status']=='outside_preferred':
            value['recommend']=False
    return value


class Hunter:
    def __init__(self, root, store):
        self.root, self.store = Path(root), store
        self.cancel = threading.Event()
        self.thread = None
        self.lock = threading.Lock()
        self.public_fetcher = None

    def start(self, market_id='all'):
        with self.lock:
            profile = self.store.get('profile')
            if not profile or not profile.get('consent') or not (profile.get('linkedin_consent') or profile.get('secondary')):
                raise ValueError('Confirm provider processing and at least one permitted discovery source first.')
            if profile.get('intent') and not profile.get('intent_confirmed'):
                raise ValueError('Review the changed search intent before discovery.')
            if len(profile.get('cv_text', '')) < 30:
                raise ValueError('Upload a readable CV first.')
            if profile.get('market_migration',{}).get('review_required'):
                raise ValueError('Review preserved legacy geography in Preferences, save regional conditions, and confirm the review before searching.')
            if market_id != 'all' and market_id not in {m['id'] for m in profile.get('markets',[])}:
                raise ValueError('Unknown search market.')
            run_id = self.store.start_run(profile['provider'])
            if run_id is None:
                return None
            self.cancel = threading.Event()
            self.public_fetcher = None
            self.thread = threading.Thread(target=self.execute, args=(run_id, self.cancel), kwargs={'market_id':market_id}, daemon=True)
            self.thread.start()
            return run_id

    def review(self, job_id, market_id=None):
        with self.lock:
            original_profile = self.store.get('profile')
            profile = {**original_profile,'_preference_revision':self.store.preference_revision()} if original_profile else None
            job = next((j for j in self.store.jobs() if j['id']==job_id), None)
            if original_profile and original_profile.get('markets'):
                if job:
                    job['country_id']=country_of(job,original_profile['markets'])
                    if job['country_id'] and market_id and market_id!=job['country_id']:
                        raise ValueError('Reassessment must match the verified listing country.')
                market_id=market_id or country_of(job or {},original_profile['markets'])
                market=next((m for m in original_profile['markets'] if m['id']==market_id),None)
                if not market:
                    raise ValueError('Select a configured market for this reassessment; listing country remains unverified.')
                profile=market_profile(original_profile,market,self.store)
            if not profile or not profile.get('consent') or not job or not job.get('description'):
                raise ValueError('A stored full description and provider-processing consent are required.')
            run_id = self.store.start_run(profile['provider'])
            if run_id is None:
                return None
            self.cancel = threading.Event()
            def work():
                payload = {'new_jobs':0,'previously_seen':1,'descriptions':0,'evaluated':0,'requests':0,'cache_hits':1,
                           'job_ids':[job_id],'sources':[{'source':'Stored description','status':'success','count':1}],'warnings':[]}
                try:
                    self.store.update_run(run_id,'AI is reassessing a stored description',payload)
                    ai = Provider(profile['provider'],self.root/'.private/ai')
                    learned=self.store.get('learned:global',[])+self.store.get('learned:'+market_id,[]) if market_id else self.store.get('learned',[])
                    result = ai.run('evaluation',EVALUATION_TASK,{'profile':profile,'learned_preferences':learned,
                                   'feedback':self.store.feedback(market_id),'jobs':[source_context(job)]},cancel=self.cancel)
                    if len(result['evaluations']) != 1:
                        raise ValueError('AI must assess this one verified identity exactly once.')
                    self.store.evaluate(job_id,prepare_evaluation(result['evaluations'][0],job,profile),market_id)
                    payload['evaluated']=1
                    payload['report']=result['report']
                    self.store.update_run(run_id,'Stored description reviewed; no new source request',payload,'completed')
                    self.store.set('provider_verified:'+profile['provider'],{'at':now(),'inference':True})
                except Exception as exc:
                    reason = str(exc) if isinstance(exc,(ValueError,ProviderError)) else 'AI review failed; vacancy retained.'
                    payload['warnings'].append(reason)
                    self.store.update_run(run_id,reason,payload,'canceled' if self.cancel.is_set() else 'failed')
            self.thread = threading.Thread(target=work,daemon=True)
            self.thread.start()
            return run_id

    def execute(self, run_id, cancel, ai=None, source=None, market_id='all'):
        try:
            return self._execute_markets(run_id,cancel,ai,source,market_id)
        except Exception as exc:
            reason=str(exc) if isinstance(exc,(ProviderError,SourceError,ValueError)) else 'Local run initialization failed; private state preserved.'
            self.store.update_run(run_id,reason,{'warnings':[reason]},'canceled' if cancel.is_set() else 'failed')

    def _execute_markets(self, run_id, cancel, ai=None, source=None, market_id='all'):
        if self.public_fetcher is None:
            self.public_fetcher=PublicFetcher(self.store,cancel,budget=min(8,self.store.get('budgets',DEFAULT_BUDGETS)['requests']),publisher_budget=4)
        profile=self.store.get('profile')
        if not profile.get('markets'):
            return self._execute_market(run_id,cancel,ai,source)
        markets=[m for m in profile['markets'] if market_id=='all' or m['id']==market_id]
        if not markets:
            self.store.update_run(run_id,'Unknown search market',{'warnings':['Unknown search market']},'failed')
            return
        budgets=self.store.get('budgets',DEFAULT_BUDGETS)
        ai=ai or Provider(profile['provider'],self.root/'.private/ai')
        source=source or LinkedIn(self.root,self.store,cancel,budgets)
        outcomes={}
        # Rotate the remainder between runs. Quotas sum to the original global cap.
        offset=(run_id-1)%len(markets)
        ordered=markets[offset:]+markets[:offset]
        for index,market in enumerate(ordered):
            quota={key:(value//len(markets)+int(index<value%len(markets))) if key in ('searches','details','requests') else value for key,value in budgets.items()}
            bounded=MarketSource(source,self.store,quota['requests'])
            outcomes[market['id']]=self._execute_market(run_id,cancel,ai,bounded,market,quota)
            self.store.update_run(run_id,'Market outcome recorded',{'markets':outcomes})
        job_ids=list(dict.fromkeys(j for p in outcomes.values() for j in p['job_ids']))
        combined={'markets':outcomes,'job_ids':job_ids,'warnings':list(dict.fromkeys(w for p in outcomes.values() for w in p['warnings'])),
                  'requests':source.requests+(self.public_fetcher.requests if self.public_fetcher else 0),'linkedin_requests':source.requests,'public_requests':self.public_fetcher.requests if self.public_fetcher else 0,'cache_hits':source.cache_hits+(self.public_fetcher.cache_hits if self.public_fetcher else 0),
                  'sources':[{**s,'market_id':m} for m,p in outcomes.items() for s in p['sources']],
                  'description_failures':[{**f,'market_id':m} for m,p in outcomes.items() for f in p['description_failures']],
                  'report':'Independent market searches finished. Review each country outcome and remaining limitations.'}
        if outcomes and all(p['status']=='failed' for p in outcomes.values()):
            combined['report']='Source coverage is unavailable across the selected markets. This does not mean there are no relevant jobs. Review each country source failure.'
        for key in ('new_jobs','descriptions'):
            combined[key]=sum(p[key] for p in outcomes.values())
        combined['evaluated']=len({j for p in outcomes.values() for j in p['evaluated_ids']})
        combined['market_assessments']=sum(p['evaluated'] for p in outcomes.values())
        combined['available_descriptions']=len({j for p in outcomes.values() for j in p.get('description_ids',[])})
        combined['discovered']=len(job_ids)
        combined['previously_seen']=max(0,len(job_ids)-combined['new_jobs'])
        statuses=[p['status'] for p in outcomes.values()]
        status='canceled' if cancel.is_set() else 'completed' if all(s=='completed' for s in statuses) else 'failed' if all(s=='failed' for s in statuses) else 'partial'
        self.store.update_run(run_id,'Ready to review — country outcomes and limitations retained',combined,status)

    def _execute_market(self, run_id, cancel, ai=None, source=None, market=None, market_budgets=None):
        public_baseline=self.public_fetcher.requests if self.public_fetcher else 0
        counters = {'new_jobs': 0, 'previously_seen': 0, 'descriptions': 0, 'evaluated': 0,
                    'sources': [], 'warnings': [], 'job_ids': [], 'evaluated_ids': [], 'description_failures': [], 'evaluation_failures': []}
        def progress(stage):
            self.store.update_run(run_id,stage,{'current_market':market['id'],'current_outcome':counters} if market else counters)

        def finish(stage,status):
            counters['linkedin_requests']=source.requests if source else 0
            counters['public_requests']=(self.public_fetcher.requests-public_baseline) if self.public_fetcher else 0
            counters['requests']=counters['linkedin_requests']+counters['public_requests']
            counters['cache_hits']=source.cache_hits if source else 0
            counters['warnings']=list(dict.fromkeys(counters['warnings']))
            counters['status']=status
            counters['discovered']=len(counters['job_ids'])
            if not market:
                self.store.update_run(run_id,stage,counters,status)
            return counters

        try:
            original=self.store.get('profile')
            profile = market_profile(original,market,self.store) if market else {**original,'_preference_revision':self.store.preference_revision()}
            budgets = market_budgets or self.store.get('budgets', DEFAULT_BUDGETS)
            ai = ai or Provider(profile['provider'], self.root / '.private/ai')
            source = source or LinkedIn(self.root, self.store, cancel, budgets)
            feedback = [{'id': f['id'], 'kind': f['kind'], 'reasons': f['reasons'], 'note': f['note'],
                         'job': {k: f['job'].get(k) for k in ('title', 'company', 'description')}} for f in self.store.feedback(market['id'] if market else None)]
            learned_key='learned:'+market['id'] if market else 'learned'
            context = {'profile': profile, 'learned_preferences': self.store.get('learned:global',[])+self.store.get(learned_key, []), 'feedback': feedback}

            def call(kind, task, data, research=False):
                if cancel.is_set():
                    raise ProviderError('Canceled by user.')
                progress({'plan': 'AI is designing your search', 'triage': 'AI is selecting descriptions',
                    'evaluation': 'AI evaluating — career fit, ATS and HR', 'learning': 'AI is interpreting your explicit feedback',
                    'research': 'AI is researching official vacancy sources','resolve':'Verifying descriptions — locating independent publication','boards':'Discovering — locating independent official ATS boards'}[kind])
                return ai.run(kind, task, data, cancel=cancel, research=research)

            if feedback and not self.store.get('learning_paused', False):
                learning = call('learning', 'Create cautious, inspectable learned preferences only from explicit feedback. Cite feedback IDs. A single dislike is tentative. Preserve user-edited preferences. Never use application outcomes.', context)
                known = {f['id'] for f in feedback}
                for preference in learning['preferences']:
                    if not preference['feedback_ids'] or not set(preference['feedback_ids']) <= known:
                        raise ValueError('Learning referenced unknown feedback.')
                    jobs_behind_feedback={f['job']['id'] for f in self.store.feedback() if f['id'] in preference['feedback_ids']}
                    if len(jobs_behind_feedback) < 2 and preference['confidence'] == 'repeated':
                        preference['confidence'] = 'tentative'
                explicit=[p for p in self.store.get(learned_key,[]) if p.get('confidence')=='explicit' and not p.get('feedback_ids')]
                learned=(explicit+[p for p in learning['preferences'] if p['text'] not in {e['text'] for e in explicit}])[:20]
                if learned!=self.store.get(learned_key,[]):
                    self.store.preference_revision(bump=True,market_id=market['id'] if market else None)
                    profile['_market_revision' if market else '_preference_revision']=self.store.preference_revision(market_id=market['id'] if market else None)
                self.store.set(learned_key, learned)
                self.store.set('learning_explanation'+(':'+market['id'] if market else ''), learning['explanation'])
                context['learned_preferences'] = self.store.get('learned:global',[])+learned
            boundary = f' This is exclusively the {market["country"]} market. Every query location MUST be exactly one of {query_locations(market)}. Respect only this market\'s languages and conditions. No other country searches.' if market else ''
            scope=scope_for(original,market) if market else None
            if scope and scope['remote']!='none':
                boundary+=f' Explicit exception: a remote-only query may use {market["country"]}; ordinary onsite/any queries must retain the reviewed region.'
            strategy='multi-source' if original.get('intent_confirmed') else 'LinkedIn-first'
            plan = call('plan', f'Generate an independent dynamic {strategy} strategy, multiple role families including transferable/stretch options. No fixed title list. Provide up to {budgets["searches"]} concise natural-language queries under 100 characters and explain each; avoid long Boolean expressions. Region/language follow profile. Choose optional official web research only when valuable. Public queries must contain no personal identifiers.'+boundary, context)
            if market:
                plan=bounded_plan(plan,market,original,lambda:call('plan','Correct ONLY the invalid geographic plan once. Use exactly the confirmed regional locations, not the entire country. Retain valid queries; no source request has been sent.'+boundary,{**context,'invalid_plan':plan}))
                if not plan['queries']:
                    counters['warnings'].append('No valid regional LinkedIn queries after one bounded correction; country scope was not expanded.')
            counters['plan'] = plan
            progress('Discovering — permitted sources from the confirmed plan')
            candidates = {}
            used_queries = set()
            search_count = 0
            public_boards=PublicBoards(self.public_fetcher or PublicFetcher(self.store,cancel,budget=min(8,budgets['requests'])))
            if market and original.get('intent_confirmed') and profile.get('secondary'):
                try:
                    located=call('boards','Locate at most two independently published official employer boards suitable for these public role families and confirmed geography. Use a board root URL from Greenhouse, Lever (including EU), Ashby, SmartRecruiters or Workable. Supply the actual official employer page linking its board, never invent a slug or job record. No LinkedIn requests or denied publisher alternate routes.',
                        {'role_families':plan['role_families'],'country':market['country'],'locations':query_locations(market),'scope':{k:v for k,v in (scope_for(original,market) or {}).items() if k in ('preferred','secondary','remote','relocation')}},research=True)
                    for board in located['boards']:
                        before=public_boards.fetcher.requests
                        trace_start=len(getattr(public_boards.fetcher,'diagnostics',[]))
                        board_info={k:board.get(k,'') for k in ('url','employer_url','query')}
                        try:
                            city=scope['preferred'][0].removesuffix(', '+market['country']) if scope and scope.get('scope_type')=='city' and scope['preferred'] else ''
                            cards=sampled(public_boards.listing({**board,'country':market['id'],'city':city}),original,market)
                            prior_descriptions={j['id']:bool(j.get('description')) for j in self.store.jobs()}
                            for job in cards:
                                job['country_id']=country_of(job,original['markets'])
                                stored,new=observe(self.store,job,run_id,market)
                                counters['descriptions']+=int(bool(stored.get('description')) and not prior_descriptions.get(stored['id'],False))
                                prior_descriptions[stored['id']]=bool(stored.get('description'))
                                counters['new_jobs' if new else 'previously_seen']+=1
                                candidates[stored['id']]=stored
                            counters['sources'].append({'source':board['provider'],'status':'success','integration':ATS_STATUS[board['provider']],'count':len(cards),'requests':public_boards.fetcher.requests-before,'board':board_info,'identity':'response_verified' if cards else 'not_verified','diagnostics':getattr(public_boards.fetcher,'diagnostics',[])[trace_start:]})
                        except SourceError as exc:
                            counters['sources'].append({'source':board['provider'],'status':getattr(exc,'status','failed'),'http_status':getattr(exc,'http_status',None),'count':0,'reason':str(exc),'requests':public_boards.fetcher.requests-before,'integration':ATS_STATUS[board['provider']],'board':board_info,'identity':'not_verified','diagnostics':getattr(public_boards.fetcher,'diagnostics',[])[trace_start:]})
                            counters['warnings'].append(str(exc))
                except (ProviderError,ValueError) as exc:
                    counters['warnings'].append('Official board discovery unavailable: '+str(exc))

            def search_queries(queries):
                nonlocal search_count
                if market:
                    queries=[q for q in queries if valid_query(q,market,scope_for(original,market))]
                if not profile.get('linkedin_consent') or self.store.get('linkedin_stop') or self.store.get('linkedin_pending'):
                    if not any(s.get('status') in ('blocked_shared_stop','not_enabled') and s.get('source')=='LinkedIn guest' for s in counters['sources']):
                        counters['sources'].append({'source':'LinkedIn guest','status':'blocked_shared_stop' if self.store.get('linkedin_stop') or self.store.get('linkedin_pending') else 'not_enabled','count':0,'reason':'No LinkedIn request sent; independent official ATS sources remain permitted.'})
                    return
                for query in queries:
                    key = (query['query'].casefold(), query['location'].casefold(), query['remote'])
                    if key in used_queries or search_count >= budgets['searches']:
                        continue
                    used_queries.add(key)
                    search_count += 1
                    seen_pages = set()
                    for page in range(1, budgets['pages']+1):
                        if cancel.is_set():
                            raise ProviderError('Canceled by user.')
                        progress(f'LinkedIn search {search_count}/{budgets["searches"]} · page {page}')
                        try:
                            jobs = source.search(query, page)
                            counters['sources'].append({'source': 'LinkedIn guest', 'query': query['query'], 'location': query['location'], 'page': page, 'status': 'success', 'count': len(jobs), 'at': now()})
                        except SourceError as exc:
                            counters['sources'].append({'source': 'LinkedIn guest', 'query': query['query'], 'page': page, 'status': 'failed', 'reason': str(exc), 'at': now()})
                            counters['warnings'].append(str(exc))
                            # A persisted stop forbids all subsequent network attempts.
                            if self.store.get('linkedin_stop') or self.store.get('linkedin_pending'):
                                return
                            break
                        page_ids = tuple(job['id'] for job in jobs)
                        if page_ids in seen_pages:
                            break
                        seen_pages.add(page_ids)
                        for job in jobs:
                            if market:
                                job['country_id']=country_of(job,original['markets'])
                            if job['id'] not in candidates:
                                new = self.store.upsert_job(job, run_id,market['id'] if market else None)
                                counters['new_jobs' if new else 'previously_seen'] += 1
                                candidates[job['id']] = job
                        if len(jobs) < 10:
                            break

            # Leave room for content-driven exploration if AI provides alternatives.
            initial = plan['queries'][:max(1, budgets['searches']-1)]
            search_queries(initial)
            existing = {job['id']: job for job in self.store.jobs()}
            triage = None
            if candidates:
                triage = call('triage', f'Select at most {budgets["details"]} verified candidate IDs for deeper description review. You may propose exploratory searches within the remaining query budget. Never create job IDs.',
                              {**context, 'candidates': [source_context(j) for j in candidates.values()], 'remaining_searches': budgets['searches']-search_count})
                if triage['expand_queries']:
                    original_count=len(candidates)
                    search_queries(triage['expand_queries'])
                else:
                    original_count=len(candidates)
                    search_queries(plan['queries'][len(initial):])
                if len(candidates)>original_count:
                    triage=call('triage',f'Choose at most {budgets["details"]} detail IDs from ALL current candidates including new discoveries. No further search expansion is available; return expand_queries: [].',
                                {**context,'candidates':[source_context(j) for j in candidates.values()],'remaining_searches':0})
            selected = (triage['detail_ids'] if triage else [])[:budgets['details']]
            # Verified full text is already available: use the existing bounded
            # assessment quota without requiring a redundant detail request.
            if market and original.get('intent_confirmed'):
                ready=[j['id'] for j in sampled(list(candidates.values()),original,market)
                       if j.get('description') and j.get('description_status')=='public_verified'
                       and country_of(j,original['markets'])==market['id']]
                selected=list(dict.fromkeys(ready+selected))[:budgets['details']]
            if any(job_id not in candidates for job_id in selected):
                raise ValueError('AI selected an unknown job identity.')
            descriptions = {}
            progress('Verifying descriptions — exact identities and source text')
            for job_id in dict.fromkeys(selected):
                prior = existing.get(job_id, {})
                transport=source.source if isinstance(source,MarketSource) else source
                fresh = self.store.cached('linkedin:detail:' + prior.get('source_id', ''), 86400) is not None if isinstance(transport, LinkedIn) else True
                if prior.get('description') and fresh:
                    if market:
                        prior['country_id']=country_of(prior,original['markets'])
                    descriptions[job_id] = prior
                    continue
                try:
                    if candidates[job_id]['id'].startswith('ats:'):
                        detail=public_boards.complete(candidates[job_id])
                        if not detail.get('description'):
                            raise RetrievalError('incomplete','ATS posting retained but full description is incomplete.')
                        self.store.upsert_job(detail,run_id,market['id'] if market else None)
                        candidates[job_id].update(detail)
                        descriptions[job_id]=candidates[job_id]
                        counters['descriptions']+=int(not prior.get('description'))
                        continue
                    if candidates[job_id].get('description_status')=='public_verified' and candidates[job_id].get('description'):
                        descriptions[job_id]=candidates[job_id]
                        continue
                    detail = source.detail(candidates[job_id]['source_id'])
                    self.store.upsert_job(detail, run_id,market['id'] if market else None)
                    candidates[job_id].update(detail)
                    if market:
                        candidates[job_id]['country_id']=country_of(candidates[job_id],original['markets'])
                    descriptions[job_id] = candidates[job_id]
                    counters['descriptions'] += 1
                except SourceError as exc:
                    counters['description_failures'].append({'job_id': job_id, 'reason': str(exc)})
                    counters['warnings'].append(str(exc))
                    # A LinkedIn stop cannot interrupt later independent ATS
                    # candidates. The LinkedIn transport itself refuses retries.
                    if market and original.get('intent_confirmed') and profile.get('secondary') and public_boards.fetcher.requests<public_boards.fetcher.budget:
                        job=candidates[job_id]
                        try:
                            located=call('resolve','Locate up to two independently published official postings for this exact observed vacancy. Never invent text or bypass a denied publisher. Preserve exact employer/title/locality/country/requisition identity; no LinkedIn requests.',
                                         {'job':{k:job.get(k) for k in ('title','company','location','url','requisition_id')}},research=True)
                            for link in located['sources']:
                                matching=verified_matches(job,link['url'],public_boards.fetcher,link['employer_url'],original['markets'])
                                if len(matching)!=1:
                                    raise RetrievalError('unverified','Progressive recovery needs one exact match; ambiguous text is not associated. Use Find full description to review candidates.')
                                full=matching[0];ev=full['evidence']
                                update={'id':job_id,'description':full['description'],'description_status':'public_verified','description_source_url':full['source_url'],
                                        'description_source':{**{k:ev[k] for k in ('url','sha256','bytes','at')},'kind':'public_verified','posting_url':full['source_url']}}
                                self.store.upsert_job(update,run_id,market['id']);job.update(update)
                                descriptions[job_id]=job;counters['descriptions']+=1
                                counters['sources'].append({'source':'Independent official recovery','status':'success','count':1})
                                break
                        except (SourceError,ProviderError,ValueError) as recovery_error:
                            counters['sources'].append({'source':'Independent official recovery','status':getattr(recovery_error,'status','failed'),'count':0,'reason':str(recovery_error)})
            fetcher=self.public_fetcher or public_boards.fetcher
            if profile.get('secondary') and (plan['supplementary_research'] or not candidates or any(s.get('board') and s['status']!='success' for s in counters['sources'])) and fetcher.requests<fetcher.budget:
                # Only professional public search terms, no CV, contact details or feedback.
                research = call('research', 'Locate up to 3 independently published official job-specific employer/ATS postings within the confirmed country and locations. Prefer full descriptions. Do not revisit failed board endpoints or any stopped publisher. Direct LinkedIn fetching is not part of this legacy employer-source resolver. Preserve exact source URL, official employer ownership page when required, title, company, location, verified requisition ID or empty string. Quote actual evidence. If inaccessible or tools absent return no jobs and explain.',
                                {'queries': plan['research_queries'], 'role_families': plan['role_families'],'country':market['country'] if market else '', 'locations':query_locations(market) if market else [],'attempted_boards':[s.get('board',{}).get('url') for s in counters['sources'] if s.get('board')],'stopped_publishers':[k.removeprefix('public:stop:') for k in self.store.stop_keys()]}, research=True)
                telemetry = ai.telemetry
                counters['research'] = {'summary': research['summary'], 'limitations': research['limitations'], 'web_calls': telemetry.get('web_calls', 0)}
                accepted = 0
                research_trace_start=len(getattr(fetcher,'diagnostics',[]))
                for result in research['jobs']:
                    try:
                        matching=verified_matches(result,result['url'],fetcher,result.get('employer_url',''),original.get('markets'))
                        if len(matching)!=1:
                            raise RetrievalError('unverified','No unique verified public source identity.')
                        retrieved=matching[0]
                        if not result['evidence_quote'].strip() or folded(result['evidence_quote']) not in folded(retrieved['description']):
                            raise RetrievalError('unverified','AI research quote not found in fetched source text.')
                    except SourceError as exc:
                        counters['warnings'].append('Controlled retrieval could not verify complete source text; supplementary vacancy not imported. '+str(exc))
                        continue
                    canonical=retrieved['source_url']
                    evidence={key:retrieved['evidence'][key] for key in ('url','sha256','bytes','at')}
                    job = {**{key:retrieved[key] for key in ('title','company','location','requisition_id','description')},
                           'url':canonical, 'id': 'web:' + hashlib.sha256(canonical.encode()).hexdigest()[:24], 'source': 'Verified public source',
                           'description_source_url':canonical,'description_source':{**evidence,'kind':'public_verified'},'description_status':'public_verified',
                           'availability': 'unknown', 'description_obtained': now(), 'evidence': result['evidence_quote']}
                    if market:
                        job['country_id']=country_of(job,original['markets'])
                    new = self.store.upsert_job(job, run_id,market['id'] if market else None)
                    counters['new_jobs' if new else 'previously_seen'] += 1
                    candidates[job['id']] = descriptions[job['id']] = job
                    accepted += 1
                counters['sources'].append({'source': 'AI web research', 'status': 'success' if accepted else 'unverified', 'count': accepted, 'reason': '; '.join(research['limitations']) or 'Verified tool retrieval required', 'at': now(),'diagnostics':getattr(fetcher,'diagnostics',[])[research_trace_start:]})
                counters['controlled_source_requests']=fetcher.requests
            if descriptions:
                if market and original.get('intent_confirmed'):
                    wrong=[j for j in descriptions if country_of(descriptions[j],original['markets'])!=market['id']]
                    for j in wrong:
                        counters['warnings'].append('Description retained; no assessment under a different or unverified country: '+j)
                        descriptions.pop(j)
            if descriptions:
                counters['available_descriptions']=len(descriptions)
                counters['description_ids']=list(descriptions)
                analysis = call('evaluation', EVALUATION_TASK,
                                {**context, 'jobs': [source_context(j) for j in descriptions.values()]})
                evaluated_ids = [item['job_id'] for item in analysis['evaluations']]
                if len(set(evaluated_ids)) != len(evaluated_ids) or set(evaluated_ids) != set(descriptions):
                    raise ValueError('AI evaluation must cover each retrieved description exactly once.')
                for value in analysis['evaluations']:
                    try:
                        evaluation = prepare_evaluation(value, descriptions[value['job_id']], profile)
                        self.store.evaluate(value['job_id'], evaluation,market['id'] if market else None)
                        counters['evaluated'] += 1
                        counters['evaluated_ids'].append(value['job_id'])
                    except ValueError as exc:
                        counters['warnings'].append(str(exc))
                        counters['evaluation_failures'].append({'job_id':value['job_id'],'reason':str(exc)})
                counters['report'] = analysis['report']
            else:
                counters['report'] = 'No verified full descriptions were available for career/ATS/HR evaluation. All observations remain in Discover.'
            counters['job_ids'] = list(candidates)
            counters['requests'] = source.requests
            counters['cache_hits'] = source.cache_hits
            if cancel.is_set():
                raise ProviderError('Canceled by user.')
            success = any(item['status'] == 'success' for item in counters['sources'])
            limited=any(s['status'] not in ('success','not_enabled') for s in counters['sources'])
            status = 'partial' if limited or counters['warnings'] or (candidates and not counters['evaluated']) else 'completed'
            if not success:
                status = 'failed'
                counters['report']='Source coverage is unavailable for this search. No conclusion about relevant vacancies can be drawn. Review the recorded source limitations.'
            self.store.set('provider_verified:' + profile['provider'], {'at': now(), 'inference': True})
            return finish('Ready to review — evidence and missing information retained',status)
        except Exception as exc:
            counters['job_ids'] = list(locals().get('candidates', {}))
            reason = str(exc) if isinstance(exc, (ProviderError, SourceError, ValueError)) else 'Unexpected local error; run failed and collected jobs preserved.'
            counters['warnings'].append(reason)
            return finish(reason,'canceled' if cancel.is_set() else 'failed')


class MarketSource:
    """A quota over ONE shared source, retaining its persisted spacing and stop latch."""
    def __init__(self, source, store, quota):
        self.source,self.store,self.quota=source,store,quota
        self.baseline=source.requests
        self.cache_baseline=source.cache_hits

    @property
    def requests(self):
        return self.source.requests-self.baseline

    @property
    def cache_hits(self):
        return self.source.cache_hits-self.cache_baseline

    def check(self):
        if self.store.get('linkedin_stop') or self.store.get('linkedin_pending'):
            raise SourceError('LinkedIn access is stopped globally; no retry was attempted.')
        if self.requests>=self.quota:
            raise SourceError('This market exhausted its fair share of the global request budget.')

    def search(self,query,page):
        self.check()
        return self.source.search(query,page)

    def detail(self,identity):
        self.check()
        return self.source.detail(identity)
