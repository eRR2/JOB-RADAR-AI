"""Discovery first, then selective enrichment and batched career assessment."""
import hashlib
import json
import re
import time
import threading
from urllib.parse import urlsplit
from .hunter import Hunter, DEFAULT_BUDGETS
from .providers import Provider, ProviderError
from .observations import observed_job
from .store import SessionExpired, now
from .location import geography
from .markets import market_profile, country_of, query_locations
from .geography import valid_query, scope_for
from .recommendations import assess, context, private_profile
from .identity import normalized_url, linkedin_job_id
from .sources import PublicFetcher, RetrievalError
from .completion import recover, freshness, vacancy_html
from .linkedin import LinkedIn, SourceError
from .access import linkedin_state
from .contracts import validate

PHASE_SECONDS = {'strategy':120,'discovery':480,'enrichment':150,'evaluation':150}
MAX_AI_CALLS = 28
STRATEGY = '''Create ONE intelligent strategy covering EVERY supplied market independently.
Use actual demonstrated capabilities, seniority, responsibilities, desired career progression,
leadership potential and learned preferences. Explore adjacent industries and credible next
steps, not just current-title variants. Titles alone do not establish fit; specialist domains
need real evidence. Generate diverse useful LinkedIn keywords and indexed-web/employer-career
queries. Locations must be supplied confirmed locations; never broaden geography. No fixed
employer defaults, identifying history or personal data in queries. Return exactly one entry
per requested market. This private planning call uses no tools.'''
STRATEGY += ' When direct_linkedin_enabled is true, include useful LinkedIn queries for each market.'
RESEARCH = '''DISCOVERY ONLY: research real vacancies using supported web search, LinkedIn indexed
FIRST plus independent employer careers and indexed web. Follow the one supplied strategy and
cover its realistic role families and geography. Explore credible adjacent industries and
leadership opportunities; no fixed companies/titles/locations. Save broad, useful observed
vacancies; do NOT evaluate suitability or spend this call recovering each full description.
Titles alone do not establish fit. Never invent facts, source evidence or URLs. Unknown country
or description does not exclude an observed job. country_quote must literally support country
and locality; label city mapping separately. No headquarters/domain/search-market inference.
Do not repeat known postings, unsuccessful queries or unproductive avenues. Use empty strings
for unknown facts. Respect robots/authentication/publisher stops; no direct page opening of a
restricted LinkedIn publisher, retries or bypass. Independent indexed discovery remains allowed.
continue_research only for new worthwhile avenues. The response envelope is not a total quota.
No private CV text, names, contacts or identifying history in public queries.'''
ENRICH = '''Select potentially strong candidates worth enriching from this batch of actual
observed source evidence and the actual CV/next-career direction. Prioritize demonstrated
responsibilities, credible progression and leadership; do not choose title-only specialist
mismatches. Missing description is uncertainty, not automatic rejection. Return exact supplied
candidate_ids in priority order. This is enrichment selection, NOT a recommendation. No tools.'''


class SessionSearch(Hunter):
    def start(self, market_id='all'):
        with self.lock:
            profile=self.store.get('profile') or {}
            if not profile.get('consent') or not profile.get('secondary') or len(profile.get('cv_text',''))<30:
                raise ValueError('Confirm CV processing and public research before starting.')
            if market_id!='all' and market_id not in {m['id'] for m in profile['markets']}:
                raise ValueError('Requested market is not in saved preferences.')
            run_id=self.store.start_run(profile['provider'])
            if run_id is None:return None
            self.thread=threading.Thread(target=self.execute,args=(run_id,self.cancel),kwargs={'market_id':market_id},daemon=True)
            self.thread.start()
            return run_id

    def execute(self, run_id, cancel, ai=None, fetcher=None, market_id='all', duration=900):
        started=time.monotonic();deadline=started+duration
        phase_end=deadline
        ai=ai or Provider(self.store.get('profile')['provider'],self.root/'.private/ai')
        fetcher=fetcher or PublicFetcher(self.store,cancel,budget=float('inf'),deadline=deadline,publisher_budget=3)
        self.public_fetcher=fetcher
        budgets={**DEFAULT_BUDGETS,**self.store.get('budgets',{})}
        linkedin=LinkedIn(self.root,self.store,cancel,budgets)
        d={'started_at':now(),'elapsed_seconds':0,'total_budget_seconds':duration,'phase':'strategy',
           'completed_phases':[],'country':'','phase_budgets':{k:round(v*duration/900,2) for k,v in PHASE_SECONDS.items()},
           'queries':[],'linkedin_direct':[],'employer_requests':[],'ai_calls':[],
           'counts':{'discovered':0,'accepted':0,'duplicates':0,'discarded':0,'evaluated':0},
           'discarded_candidates':[],'market_outcomes':{},'descriptions':{}}
        payload={'kind':'clean_search','job_ids':[],'warnings':[], 'diagnostics':d,
                 'usage':{'ai_invocations':0,'model_seconds':0,'web_actions':0,'cached_assessments':0},'requests':0}
        queries=set();unsuccessful=set();links={};native=[];observed_urls=set()
        known={j['id']:j for j in self.store.jobs()};url_index={normalized_url(j['url']):j for j in known.values()}
        profile=self.store.get('profile');all_markets=profile['markets']
        markets=[m for m in all_markets if market_id=='all' or m['id']==market_id]

        def safe_text(value):
            text=str(value)
            # No prompts/source text in diagnostics. Mask contact-shaped query values.
            text=re.sub(r'\b[^\s@]+@[^\s@]+\.[^\s@]+','[contact removed]',text)
            text=re.sub(r'(?<!\w)\+?\d[\d ()-]{7,}\d','[contact removed]',text)
            for line in profile.get('cv_text','').splitlines():
                line=line.strip()
                if len(line)>=8:text=re.sub(re.escape(line),'[CV text removed]',text,flags=re.I)
            return text[:500]

        def safe_url(value):
            try:
                p=urlsplit(value)
                return safe_text(p.scheme+'://'+(p.hostname or '')+p.path)
            except ValueError:return '[unsafe URL omitted]'

        def progress(stage):
            d['elapsed_seconds']=round(time.monotonic()-started,3)
            payload['requests']=fetcher.requests+linkedin.requests
            d['employer_requests']=[{**v,'endpoint':safe_url(v['endpoint']),'parameters':{k:[safe_text(x) for x in vals] for k,vals in v.get('parameters',{}).items()}} for v in getattr(fetcher,'diagnostics',[])]
            jobs=self.store.jobs();payload['job_ids']=[j['id'] for j in jobs]
            d['descriptions']={
                'full':sum(bool(j.get('description')) for j in jobs),
                'partial':sum(bool(j.get('partial_source_text')) and not j.get('description') for j in jobs),
                'snippet_only':sum(not j.get('description') and not j.get('partial_source_text') for j in jobs)}
            d['counts']['evaluated']=sum(bool(j.get('preliminary')) for j in jobs)
            self.store.update_run(run_id,stage,payload)

        def phase(name):
            nonlocal phase_end
            if cancel.is_set():raise ProviderError('Canceled by user.','canceled')
            if time.monotonic()>=deadline:raise ProviderError('Total research budget reached; saved findings retained.','total_budget')
            if d['phase']!=name:d['completed_phases'].append(d['phase'])
            d['phase']=name;d['country']=''
            phase_end=min(deadline,time.monotonic()+d['phase_budgets'][name])
            fetcher.deadline=phase_end
            linkedin.deadline=phase_end
            progress('Research phase: '+name)

        def available():return not cancel.is_set() and time.monotonic()<phase_end-1

        def call(kind,task,data,research=False,allowance=None):
            ai.telemetry={}
            if cancel.is_set():raise ProviderError('Canceled by user.','canceled')
            remaining=min(deadline,phase_end)-time.monotonic()
            if remaining<=1:raise ProviderError('Phase time budget reached; current results retained.','phase_budget')
            if payload['usage']['ai_invocations']>=MAX_AI_CALLS:raise ProviderError('Bounded AI invocation budget reached; current results retained.','invocation_budget')
            record={'kind':kind,'phase':d['phase'],'country':d['country'],'started_at':now(),'status':'running','seconds':0}
            d['ai_calls'].append(record);payload['usage']['ai_invocations']+=1
            progress('AI '+kind+' · '+d['country'])
            began=time.monotonic();ai.telemetry={}
            try:
                result=ai.run(kind,task,data,cancel=cancel,research=research,timeout=min(90 if research else 60,remaining,allowance or remaining))
                record['status']='completed'
                return result
            except Exception as exc:
                record['status']='failed';record['category']=getattr(exc,'category','validation_error')
                record['timeout_category']='provider_call_timeout' if record['category']=='time_window' else record['category']
                raise
            finally:
                record['seconds']=round(time.monotonic()-began,3)
                payload['usage']['model_seconds']+=record['seconds']
                telemetry=getattr(ai,'telemetry',{})
                if research:
                    payload['usage']['web_actions']+=telemetry.get('web_calls',0)
                    record['web_actions']=telemetry.get('web_calls',0)
                    for action in telemetry.get('actions',[]):
                        for value in action.get('queries',[]) or ([action['query']] if action.get('query') else []):
                            text=value if isinstance(value,str) else value.get('q','')
                            if text:
                                queries.add(safe_text(text))
                                d['queries'].append({'source':'AI indexed web','country':d['country'],'query':safe_text(text),'phase':d['phase']})
                for key,value in telemetry.get('usage',{}).items():
                    if key in ('input_tokens','cached_input_tokens','output_tokens') and type(value) is int and value>=0:
                        record.setdefault('reported_tokens',{})[key]=value
                        tokens=payload['usage'].setdefault('reported_tokens',{});tokens[key]=tokens.get(key,0)+value
                progress('AI '+kind+' '+record['status'])

        class PrivateCalls:
            def run(self,kind,task,data,**kwargs):return call(kind,task,data)

        def save(job):
            d['counts']['discovered']+=1
            old=known.get(job['id']) or url_index.get(normalized_url(job['url']))
            if old:
                d['counts']['duplicates']+=1;job['id']=old['id']
                seen={o['text'] for o in old.get('source_observations',[])}
                job['source_observations']=old.get('source_observations',[])+[o for o in job.get('source_observations',[]) if o['text'] not in seen]
                job['discovery_sources']=sorted(set(old.get('discovery_sources',[old['source']])+[job['source']]))
                for key in ('description_status','evaluation_status','availability'):job.pop(key,None)
                for key in ('title','company','location','country','country_evidence'):
                    if not job.get(key) and old.get(key):job[key]=old[key]
            else:
                d['counts']['accepted']+=1;job['discovery_sources']=[job['source']]
            self.store.upsert_job(job,run_id,country_of(job,all_markets))
            known[job['id']]={**(old or {}),**job};url_index[normalized_url(job['url'])]=known[job['id']]
            if d['counts']['accepted']%10==0:progress('Verified discoveries saved · '+d['country'])

        def indexed(result,telemetry):
            observations=telemetry.get('observations',[]);native.extend(observations)
            for o in observations:
                try:
                    if o.get('url'):observed_urls.add(normalized_url(o['url']))
                except ValueError:pass
            for url in telemetry.get('observed_urls',[]):
                try:observed_urls.add(normalized_url(url))
                except ValueError:pass
            for candidate in result['jobs']:
                rejected=[];job=observed_job(candidate,observations,rejected)
                if not job:
                    d['counts']['discovered']+=1;d['counts']['discarded']+=1
                    d['discarded_candidates'].extend({'url':safe_url(r['url']) if r['reason']!='unsafe_url' else '[unsafe URL omitted]','reason':r['reason'],'country':d['country']} for r in rejected)
                    continue
                links.setdefault(job['id'],[]).extend(candidate.get('description_sources',[]))
                save(job)

        def direct(query,market):
            if not profile.get('linkedin_consent') or linkedin_state(self.store)['state']!='available' or linkedin.denied_in_run:return
            if linkedin.requests>=budgets['requests'] or sum(r['operation']=='search' for r in d['linkedin_direct'])>=budgets['searches']:return
            record={'country':market['country'],'query':safe_text(query['query']),'location':safe_text(query['location']),'status':'running','operation':'search'}
            d['linkedin_direct'].append(record)
            d['queries'].append({'source':'LinkedIn direct','country':market['country'],'query':safe_text(query['query']),'location':safe_text(query['location'])})
            progress('LinkedIn direct discovery · '+market['country'])
            before_requests=linkedin.requests
            try:
                for job in linkedin.search(query):
                    text='\n'.join(str(job.get(k,'')) for k in ('title','company','location','description'))
                    country=country_of(job,all_markets)
                    job['country']=next((m['country'] for m in all_markets if m['id']==country),'')
                    job['country_evidence']=job.get('location','') if country else ''
                    job['source_observations']=[{'url':job['url'],'text':text,'kind':'linkedin_direct','at':now()}]
                    save(job)
                record.update(status='received',http_status=200)
            except (SourceError,ProviderError) as exc:
                state=linkedin_state(self.store)
                record.update(status=state['state'] if state['state']!='available' else 'source_failed',http_status=state.get('http_status'),reason=safe_text(str(exc)))
            finally:
                record['requests']=linkedin.requests-before_requests
                record['cache_hit']=linkedin.last_cached
                progress('LinkedIn direct discovery recorded')

        try:
            if not markets:raise ValueError('Requested market is not in saved preferences.')
            phase('strategy')
            global_learning=(self.store.get('learned:global',[]) or [])+(self.store.get('learned',[]) or [])
            knowledge={'cv_text':profile['cv_text'],'original_request':profile.get('looking_for',''),'intent':profile.get('intent'),'markets':all_markets,
                       'learned':{m['id']:self.store.get('learned:'+m['id'],[]) for m in all_markets},'global_learned':global_learning,'feedback':self.store.get('persistent_feedback',[])}
            signature=hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
            brief=self.store.get('professional_background') if self.store.get('knowledge_signature')==signature else None
            if not brief:
                brief=call('session_brief','Extract anonymous demonstrated capabilities, seniority and desired NEXT direction. No names, contacts, previous employers, copied CV passages or distinctive history. Preserve separate geographic/working conditions and scoped feedback. No tools.',knowledge)
                self.store.set('professional_background',brief);self.store.set('knowledge_signature',signature)
            strategy=call('session_strategy',STRATEGY,{'background':brief,'markets':[{**m,'allowed_linkedin_locations':query_locations(m)} for m in markets],'direct_linkedin_enabled':bool(profile.get('linkedin_consent'))})
            validate('session_strategy',strategy)
            plans={v['market_id']:v for v in strategy['markets']}
            if len(plans)!=len(strategy['markets']) or set(plans)!={m['id'] for m in markets}:raise ValueError('Research strategy must cover every selected market exactly once.')
            for m in markets:
                for q in plans[m['id']]['linkedin_queries']:
                    if not q['query'].strip() or q['query'].startswith('-') or not valid_query(q,m,scope_for(profile,m)):raise ValueError('Strategy query/location invalid or outside saved preferences; no source request sent.')
            phase('discovery')
            pending=list(markets);passes={m['id']:0 for m in markets};avenues={m['id']:[] for m in markets}
            while pending and available():
                m=pending.pop(0);d['country']=m['country'];plan=plans[m['id']];n=passes[m['id']];passes[m['id']]+=1
                visit_end=min(phase_end,time.monotonic()+(phase_end-time.monotonic())/(len(pending)+1))
                linkedin.deadline=visit_end-45  # Reserve indexed discovery for this market too.
                if n<len(plan['linkedin_queries']) and linkedin.deadline-time.monotonic()>1:direct(plan['linkedin_queries'][n],m)
                before=d['counts']['accepted'];previous_queries=set(queries)
                try:
                    result=call('research_v5',RESEARCH,{'background':brief['background'],'career_direction':brief['direction'],'strategy':strategy['strategy'],'role_families':strategy['role_families'],
                        'market':{k:m[k] for k in ('id','country','locations','scope_type','remote','relocation') if k in m},'planned_queries':plan['web_queries'],'country_preferences':[v for v in brief['country_preferences'] if v['country_id']==m['id']],
                        'previous_queries':sorted(queries),'known_postings':[{'id':j['id'],'url':j['url']} for j in self.store.jobs()],
                        'next_avenues':avenues[m['id']],'restricted_publishers':self.store.access_restrictions(),'linkedin_access':linkedin_state(self.store),'linkedin_stop':self.store.get('linkedin_stop')},True,max(1,visit_end-time.monotonic()))
                    telemetry=ai.telemetry
                    if not telemetry.get('web_calls') or telemetry.get('research_unverified'):raise ProviderError('No genuine web-tool observations; model-only discoveries refused.','unverified_research')
                    indexed(result,telemetry)
                    payload['warnings'].extend(safe_text(v) for v in result['limitations'])
                    new_avenues=result['next_avenues'];new=d['counts']['accepted']-before
                    expand=result['continue_research'] and new_avenues and passes[m['id']]<3 and (new or queries!=previous_queries or new_avenues!=avenues[m['id']])
                    if expand:pending.append(m)
                    d['market_outcomes'][m['id']]={'indexed_passes':passes[m['id']],'new_jobs':new,'status':'more_avenues' if expand else 'avenues_exhausted'}
                    avenues[m['id']]=new_avenues
                except ProviderError as exc:
                    # Never retry a failed call. Other markets still get their turn.
                    d['market_outcomes'][m['id']]={'indexed_passes':passes[m['id']],'status':getattr(exc,'category','execution_error')}
                    payload['warnings'].append(m['country']+': '+getattr(exc,'category','execution_error'))
                    d.setdefault('failures',[]).append({'phase':d['phase'],'country':m['country'],'reason':getattr(exc,'category','execution_error'),'stage':'AI indexed discovery'})
                    obs=getattr(ai,'telemetry',{}).get('observations',[]) if exc.category=='time_window' else []
                    candidates=[dict(url=o['url'],title=o.get('title',''),company='',location='',country='',country_quote='',description_sources=[]) for o in obs if o.get('url') and linkedin_job_id(o['url'])]
                    indexed({'jobs':candidates},getattr(ai,'telemetry',{}))
                progress('Discovery coverage saved · '+m['country'])
            if pending:payload['warnings'].append('Discovery phase budget reached; saved findings retained.')
            if not self.store.jobs() and d.get('failures') and all(v['status'] not in ('avenues_exhausted','more_avenues') for v in d['market_outcomes'].values()):
                raise ProviderError('Indexed discovery failed: '+'; '.join(f['country']+': '+f['reason'] for f in d['failures'])+'. No automatic retry.','discovery_failed')
            phase('enrichment')
            jobs=self.store.jobs()
            for start in range(0,len(jobs),40):
                if not available():payload['warnings'].append('Enrichment phase budget reached.');break
                batch=jobs[start:start+40]
                selection=call('enrichment',ENRICH,{'profile':private_profile(profile),'background':brief,'jobs':[context(j) for j in batch]})
                validate('enrichment',selection)
                chosen=selection['candidate_ids'];by_id={j['id']:j for j in batch}
                if len(set(chosen))!=len(chosen) or not set(chosen)<=set(by_id):raise ValueError('Enrichment selection identity mismatch.')
                for job_id in chosen:
                    if not available():break
                    job=by_id[job_id];d['country']=job.get('country','') or 'Location unverified'
                    if job.get('description'):continue
                    full=None
                    for o in native:
                        text=o.get('text') or o.get('content','')
                        if o.get('url') and normalized_url(o['url'])==normalized_url(job['url']) and o.get('observation_kind')=='page_read' and '<' in text:
                            page={'url':job['url'],'text':text,'at':now(),'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()}
                            try:full=vacancy_html(job,page)
                            except RetrievalError:pass
                    if not full and job['id'].startswith('linkedin:') and profile.get('linkedin_consent') and linkedin_state(self.store)['state']=='available' and not linkedin.denied_in_run and linkedin.requests<budgets['requests'] and sum(r['operation']=='detail' for r in d['linkedin_direct'])<budgets['details'] and phase_end-time.monotonic()>30:
                        record={'country':d['country'],'operation':'detail','job_id':job['id'],'status':'running'};d['linkedin_direct'].append(record)
                        before_requests=linkedin.requests
                        try:
                            detail=linkedin.detail(job['source_id']);self.store.upsert_job({**detail,'description_status':'full','description_source':{'kind':'linkedin','url':job['url'],'at':now()}})
                            record.update(status='received',http_status=200);progress('LinkedIn detail saved');continue
                        except (SourceError,ProviderError) as exc:
                            state=linkedin_state(self.store);record.update(status=state['state'] if state['state']!='available' else 'source_failed',http_status=state.get('http_status'),reason=safe_text(str(exc)))
                        finally:record.update(requests=linkedin.requests-before_requests,cache_hit=linkedin.last_cached)
                    source_links=list(links.get(job_id,[]))
                    host=urlsplit(job['url']).hostname or ''
                    if host!='linkedin.com' and not host.endswith('.linkedin.com'):source_links.insert(0,{'url':job['url'],'employer_url':''})
                    for link in source_links if not full else []:
                        if not available():break
                        url=link['url']
                        if normalized_url(url) not in observed_urls or normalized_url(url) in unsuccessful:continue
                        try:full=recover(job,url,link['employer_url'],fetcher,all_markets);break
                        except RetrievalError as exc:
                            unsuccessful.add(normalized_url(url));self.store.upsert_job({'id':job_id,'description_status':exc.status})
                    if full:
                        state=freshness(full)
                        self.store.upsert_job({'id':job_id,'description':full['description'],'description_status':'public_verified','location':full.get('location') or job.get('location',''),'country':full.get('country') or job.get('country',''),
                            'description_source':{'kind':'public_verified','url':full['source_url'],'sha256':full['evidence']['sha256'],'at':now()},'freshness':state,
                            'availability':'closed_banner_observed' if state['status']=='confirmed_closed' else 'open_publisher_observed' if state['status']=='confirmed_open' else 'unknown'})
                    progress('Candidate source enrichment recorded')
            phase('evaluation')
            jobs=self.store.jobs();groups=[]
            for m in markets:
                for verified in (True,False):
                    groups.append((m,verified,[j for j in jobs if geography(j,all_markets)['country_id']==m['id'] and (country_of(j,all_markets)==m['id'])==verified]))
            groups.append((None,False,[j for j in jobs if not geography(j,all_markets)['country_id']]))
            queue=[(m,v,g) for m,v,g in groups if g]
            while queue:
                m,verified,group=queue.pop(0)
                if not group:continue
                if len(group)>20:queue.append((m,verified,group[20:]))
                group=group[:20]
                d['country']=m['country'] if m else 'Location unverified'
                scoped=market_profile(profile,m,self.store) if m else {**profile,'authoritative_request':profile.get('looking_for','')}
                scoped['learned_preferences']=(self.store.get('learned:'+m['id'],[]) if verified else [])+global_learning
                feedback=[f for f in self.store.get('persistent_feedback',[]) if f['country'] in (m['id'],'global')] if verified else []
                stats=assess(PrivateCalls(),self.store,group,scoped,feedback)
                payload['usage']['cached_assessments']+=stats['cached'];progress('Batched career suitability saved · '+d['country'])
            d['completed_phases'].append('evaluation')
            status='canceled' if cancel.is_set() else 'partial' if payload['warnings'] else 'completed'
            d['stop']={'phase':d['phase'],'reason':'canceled' if cancel.is_set() else 'completed_with_limitations' if payload['warnings'] else 'completed'}
        except SessionExpired:return
        except Exception as exc:
            category=getattr(exc,'category','validation_error')
            message=str(exc) if isinstance(exc,(ValueError,ProviderError)) else 'Research interrupted; saved findings retained.'
            payload['provider_error']={'category':category,'message':safe_text(message)}
            d['stop']={'phase':d['phase'],'country':d['country'],'reason':category,'stage':self.store.runs()[0]['stage']}
            status='canceled' if cancel.is_set() else 'partial' if self.store.jobs() else 'failed'
        try:
            payload['warnings']=list(dict.fromkeys(payload['warnings']));progress('Search '+status)
            self.store.update_run(run_id,'Search '+status,payload,status)
        except SessionExpired:pass
