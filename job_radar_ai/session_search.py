"""One disposable, bounded AI research session; persistent knowledge is separate."""
import hashlib
import json
import time
import threading
from urllib.parse import urlsplit
from .hunter import Hunter
from .providers import Provider, ProviderError
from .observations import observed_job
from .store import SessionExpired, now
from .location import geography
from .markets import market_profile, country_of
from .recommendations import assess
from .identity import normalized_url
from .sources import PublicFetcher, RetrievalError
from .completion import recover, freshness, vacancy_html

RESEARCH = '''Research real vacancies with supported web search/page reading, LinkedIn FIRST.
Choose useful queries for the anonymous professional background and intended next step.
Respect each supplied country's city, salary, workplace and employment preferences.
Titles alone do not establish fit. Explore credible progression and transferable industries,
but specialist responsibilities need actual supporting capability. Never invent facts or URLs.
Do not repeat previous queries, postings, unsuccessful pages or restricted publishers.
Use supported page reading to obtain actual job-specific text when allowed; summaries are
not retrieved descriptions. Return only observed vacancy URLs and verbatim supported fields.
country_quote must literally support both country and observed locality. Label city mapping
inferences separately. Never infer from employer headquarters, domain suffix or search market.
Use empty strings when unknown. Do not bypass robots/authentication/active publisher stops;
an active LinkedIn stop prohibits direct page opening; independent indexed discovery is allowed.
continue_research only when new worthwhile avenues remain, not merely more title matches.
The response envelope is a batch size, not a total job quota. No personal data in queries.'''


class SessionSearch(Hunter):
    def start(self, market_id='all'):
        with self.lock:
            profile=self.store.get('profile') or {}
            if not profile.get('consent') or not profile.get('secondary') or len(profile.get('cv_text',''))<30:
                raise ValueError('Confirm CV processing and public research before starting.')
            run_id=self.store.start_run(profile['provider'])
            if run_id is None:return None
            self.thread=threading.Thread(target=self.execute,args=(run_id,self.cancel),daemon=True)
            self.thread.start()
            return run_id

    def execute(self, run_id, cancel, ai=None, fetcher=None, market_id='all', duration=300):
        ai = ai or Provider(self.store.get('profile')['provider'], self.root / '.private/ai')
        deadline = time.monotonic() + duration
        fetcher = fetcher or PublicFetcher(self.store, cancel, budget=float('inf'), deadline=deadline)
        self.public_fetcher = fetcher
        payload = {'kind':'clean_search','job_ids':[],'warnings':[], 'usage':{'ai_invocations':0,'model_seconds':0,'web_actions':0,'cached_assessments':0}, 'requests':0}
        queries, unsuccessful = set(), set()

        def progress(stage):
            payload['requests'] = fetcher.requests
            self.store.update_run(run_id, stage, payload)

        def call(kind, task, data, research=False):
            if cancel.is_set():raise ProviderError('Canceled by user.', 'canceled')
            remaining = deadline-time.monotonic()
            if remaining <= 1:raise ProviderError('Search time window reached; current results retained.', 'time_window')
            started = time.monotonic()
            payload['usage']['ai_invocations'] += 1
            try:
                return ai.run(kind,task,data,cancel=cancel,research=research,timeout=min(90 if research else 60, remaining))
            finally:
                payload['usage']['model_seconds'] += round(time.monotonic()-started,3)
                telemetry = getattr(ai,'telemetry',{})
                if research:payload['usage']['web_actions'] += telemetry.get('web_calls',0)
                for k,v in telemetry.get('usage',{}).items():
                    tokens = payload['usage'].setdefault('reported_tokens',{})
                    tokens[k] = tokens.get(k,0)+v

        class PrivateCalls:
            def run(self,kind,task,context,**kwargs):return call(kind,task,context)

        try:
            profile = self.store.get('profile')
            if not profile.get('secondary'):raise ValueError('Enable AI public web research before searching.')
            markets = profile['markets']
            global_learning = (self.store.get('learned:global',[]) or []) + (self.store.get('learned',[]) or [])
            knowledge = {'cv_text':profile['cv_text'],'original_request':profile.get('looking_for',''), 'intent':profile.get('intent'), 'markets':markets,
                         'learned':{m['id']:self.store.get('learned:'+m['id'],[]) for m in markets}, 'global_learned':global_learning,
                         'feedback':self.store.get('persistent_feedback',[])}
            signature = hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
            brief = self.store.get('professional_background') if self.store.get('knowledge_signature')==signature else None
            if not brief:
                progress('Preparing private professional background')
                brief = call('session_brief','Extract a concise anonymous professional background and desired NEXT career direction from the actual CV, original request and confirmed preferences. Produce separate country conditions and cautious explicit feedback learning. No names, contacts, prior employer identities, copied CV passages or distinctive project history. User-requested target employers may remain. Never treat employer rejection/Obsolete as feedback. Do not search or use tools.',knowledge)
                self.store.set('professional_background',brief)
                self.store.set('knowledge_signature',signature)
            pending = list(markets)
            stagnant = {m['id']:0 for m in markets}
            avenues = {m['id']:set() for m in markets}
            while pending and not cancel.is_set() and time.monotonic()<deadline:
                market = pending.pop(0)
                previous = {j['id']:j for j in self.store.jobs()}
                progress('Researching '+market['country'])
                result = call('research_v5',RESEARCH, {'background':brief['background'], 'career_direction':brief['direction'],
                    'market':{k:market[k] for k in ('id','country','locations','scope_type','remote','relocation') if k in market},
                    'country_preferences':[v for v in brief['country_preferences'] if v['country_id']==market['id']],
                    'previous_queries':sorted(queries),'known_postings':[{'id':j['id'],'url':j['url']} for j in previous.values()],
                    'unavailable_urls':sorted(unsuccessful),'next_avenues':sorted(avenues[market['id']]),
                    'restricted_publishers':self.store.access_restrictions(), 'linkedin_access':self.store.get('linkedin_access'), 'linkedin_stop':self.store.get('linkedin_stop')},True)
                telemetry = ai.telemetry
                if not telemetry.get('web_calls') or telemetry.get('research_unverified'):
                    raise ProviderError('No genuine web-tool observations returned; no invented discoveries were imported.')
                observed = telemetry.get('observations',[])
                previous_queries = set(queries)
                for action in telemetry.get('actions',[]):
                    values = action.get('queries',[]) or ([action['query']] if action.get('query') else [])
                    queries.update(v if isinstance(v,str) else v.get('q','') for v in values)
                real_urls = {normalized_url(o['url']) for o in observed if o.get('url')}
                real_urls.update(normalized_url(u) for u in telemetry.get('observed_urls',[]) if u.startswith('https://'))
                batch = {}
                for candidate in result['jobs']:
                    job = observed_job(candidate,observed)
                    if not job:continue
                    old = next((j for j in previous.values() if j['id']==job['id'] or normalized_url(j['url'])==normalized_url(job['url'])),None)
                    if old:
                        job['id'] = old['id']
                        texts = {o['text'] for o in old.get('source_observations',[])}
                        job['source_observations'] = old.get('source_observations',[])+[o for o in job['source_observations'] if o['text'] not in texts]
                        for key in ('description_status','evaluation_status','availability'):job.pop(key,None)
                    self.store.upsert_job(job,run_id,country_of(job,markets))
                    batch[job['id']] = next(j for j in self.store.jobs() if j['id']==job['id'])
                payload['job_ids'] = [j['id'] for j in self.store.jobs()]
                progress('Current discoveries saved; checking source evidence')
                recovered = 0
                for job in batch.values():
                    if job.get('description'):continue
                    full = None
                    # Actual HTML returned by a native page read can be parsed locally.
                    for o in observed:
                        text = o.get('text') or o.get('content','')
                        if o.get('url')==job['url'] and o.get('observation_kind')=='page_read' and '<' in text:
                            page = {'url':job['url'],'text':text,'at':now(),'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()}
                            try:full=vacancy_html(job,page)
                            except RetrievalError:pass
                    links = next((c['description_sources'] for c in result['jobs'] if normalized_url(c['url'])==normalized_url(job['url'])),[])
                    host = urlsplit(job['url']).hostname or ''
                    if not (host=='linkedin.com' or host.endswith('.linkedin.com')):links=[{'url':job['url'],'employer_url':''}]+links
                    for link in links if not full else []:
                        if cancel.is_set() or time.monotonic()>=deadline:break
                        url = link['url']
                        if normalized_url(url) not in real_urls or url in unsuccessful:continue
                        try:full=recover(job,url,link['employer_url'],fetcher,markets);break
                        except RetrievalError as exc:
                            unsuccessful.add(url)
                            self.store.upsert_job({'id':job['id'],'description_status':exc.status})
                    if full:
                        state = freshness(full)
                        self.store.upsert_job({'id':job['id'],'description':full['description'],'description_status':'public_verified',
                            'location':full.get('location') or job.get('location',''),'country':full.get('country') or job.get('country',''),
                            'description_source':{'kind':'public_verified','url':full['source_url'],'sha256':full['evidence']['sha256'],'at':now()},
                            'freshness':state,'availability':'closed_banner_observed' if state['status']=='confirmed_closed' else 'open_publisher_observed' if state['status']=='confirmed_open' else 'unknown'})
                        recovered += 1
                current = {j['id']:j for j in self.store.jobs()}
                eligible = [current[k] for k in batch if geography(current[k],markets)['country_id'] in (None,market['id'])]
                counts = {'assessed':0,'cached':0}
                for scope in ('verified','inferred','unknown'):
                    group = [j for j in eligible if ('verified' if country_of(j,markets)==market['id'] else 'inferred' if geography(j,markets)['country_id'] else 'unknown')==scope]
                    feedback = [f for f in self.store.get('persistent_feedback',[]) if f['country'] in (market['id'],'global')] if scope=='verified' else []
                    scoped = market_profile(profile,market,self.store) if scope!='unknown' else {**profile,'authoritative_request':profile.get('looking_for','')}
                    scoped['learned_preferences'] = (self.store.get('learned:'+market['id'],[]) if scope=='verified' else []) + global_learning
                    stats = assess(PrivateCalls(),self.store,group,scoped,feedback)
                    for k in counts:counts[k]+=stats[k]
                payload['usage']['cached_assessments'] += counts['cached']
                progress('Career suitability saved · '+market['country'])
                new = set(batch)-set(previous)
                decisions = [j.get('preliminary',{}) for j in self.store.jobs() if j['id'] in batch]
                valuable = any(d.get('priority') in ('exceptional','strong','consider') and not d.get('critical_gap') for d in decisions)
                useful = bool(recovered and valuable) or any(j.get('preliminary',{}).get('recommend') for j in self.store.jobs() if j['id'] in new)
                low_yield = not useful and (len(new)<=len(batch)*0.1 or not valuable)
                stagnant[market['id']] = stagnant[market['id']]+1 if low_yield else 0
                next_avenues = set(result['next_avenues'])
                no_new_avenues = next_avenues<=avenues[market['id']]
                no_new_queries = queries==previous_queries
                if result['continue_research'] and next_avenues and not (stagnant[market['id']]>=3 or (stagnant[market['id']]>=2 and (no_new_avenues or no_new_queries))):
                    pending.append(market)
                else:payload.setdefault('stop_reasons',{})[market['id']]='Useful avenues exhausted or diminishing returns.'
                avenues[market['id']] = next_avenues
                payload['warnings'].extend(result['limitations'])
            status = 'canceled' if cancel.is_set() else 'partial' if pending or payload['warnings'] else 'completed'
        except SessionExpired:
            return
        except Exception as exc:
            payload['provider_error'] = {'category':getattr(exc,'category','validation_error'), 'message':str(exc) if isinstance(exc,(ValueError,ProviderError)) else 'Research interrupted; current results retained.'}
            status = 'canceled' if cancel.is_set() else 'partial' if payload['job_ids'] else 'failed'
        try:
            payload['warnings'] = list(dict.fromkeys(payload['warnings']))
            progress('Search '+status)
            self.store.update_run(run_id,'Search '+status,payload,status)
        except SessionExpired:pass
