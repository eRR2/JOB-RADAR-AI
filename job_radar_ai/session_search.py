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
from .history import same_posting
from .sources import PublicFetcher, RetrievalError
from .completion import recover, freshness, vacancy_html
from .linkedin import LinkedIn, SourceError
from .access import linkedin_state
from .contracts import validate

PHASE_SECONDS = {'discovery':600,'enrichment':150,'evaluation':150}
MAX_AI_CALLS = 16
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
Return a relevant role ONLY if there is a credible path from the supplied real
professional background and next-career request to the core responsibilities;
do not return unrelated specialist work just because its title is Architect,
Lead or Manager. Explore cross-sector careers when capabilities transfer.
This is generic reasoning, not an industry blacklist. Use varied role/level
and employer-specific queries, beginning with explicitly prioritized employers.
Do not search with entire goal paragraphs or generic single-word titles.
No private CV text, names, contacts or identifying history in public queries.'''
ENRICH = '''First apply a strict but fair relevance triage. Select potentially strong candidates worth enriching from this batch of actual
observed source evidence and the actual CV/next-career direction. Prioritize demonstrated
responsibilities, credible progression and leadership; do not choose title-only specialist
mismatches. Missing description is uncertainty, not automatic rejection. Exclude clear
specialist-domain mismatches, unrelated roles, implausible seniority or geographic
mismatches, but preserve credible stretch roles and cross-sector leadership.
Select only evidence-backed credible next moves; do not fill a quota.
Return exact supplied candidate_ids in priority order. This is relevance
selection, NOT a final recommendation. No tools.'''


def initial_plan(profile,markets,brief=None):
    """Concise transport seeds from user intent, not fixed company/job dictionaries.

    Never pass a full career paragraph to direct LinkedIn. Indexed discovery can
    expand the complete next-move request semantically inside its own research call.
    """
    intent=profile.get('intent') or {}
    entries=intent.get('preferences',[])
    plans=[];families=[]
    def concise(value):
        value=str(value or '')
        places={place for m in profile['markets'] for place in [m['country'],*m['locations']]}
        for place in sorted(places,key=len,reverse=True):
            value=re.sub(r'(?<!\w)'+re.escape(place)+r'(?!\w)',' ',value,flags=re.I)
        pieces=re.split(r'[,;/\n]|\s+(?:or|oder|und|and)\s+',value,flags=re.I)
        out=[]
        for piece in pieces:
            piece=re.sub(r'https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|(?<!\w)\+?\d[\d ()-]{7,}\d',' ',piece)
            piece=re.sub(r'^(?:next|goal|ziel|hedef)\s*:\s*','',piece,flags=re.I)
            piece=' '.join(piece.split()).strip(' ,-.:')
            piece=re.sub(r'\s+(?:in|at|near|im|bei)
    for market in markets:
        values=[p.get('value','') for p in entries
                if p.get('topic') in ('target_roles','role_families','career_direction','management_progression')
                and p.get('scope','') in ('',market['id']) and p.get('origin') in ('explicit','cv_evidenced')]
        values += [(brief or {}).get('direction',''), intent.get('summary',''), profile.get('looking_for','')]
        terms=[]
        places={place for m in profile['markets'] for place in [m['country'],*m['locations']]}
        for value in values:
            for term in concise(value):
                for place in sorted(places,key=len,reverse=True):
                    term=re.sub(r'(?<!\w)'+re.escape(place)+r'(?!\w)',' ',term,flags=re.I)
                term=' '.join(term.split()).strip(' ,-.')
                if 2<=len(term.split())<=7 and term not in terms:terms.append(term)
        locations=query_locations(market)
        # Interleave role families and towns rather than using up every source
        # request on one generic term in three towns.
        queries=[dict(query=terms[i % len(terms)],location=locations[i % len(locations)],
                      remote='any',reason='Explicit career-goal role phrase')
                 for i in range(min(8,len(terms)*len(locations)))] if terms and locations else []
        plans.append({'market_id':market['id'],'linkedin_queries':queries,'web_queries':terms[:7]})
        families.extend(term for term in terms if term not in families)
    return {'strategy':'Explore true responsibility matches, credible leadership progression, confirmed location and source freshness using the saved career request.',
            'role_families':families[:12],'markets':plans}


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
        d={'started_at':now(),'elapsed_seconds':0,'total_budget_seconds':duration,'phase':'discovery',
           'completed_phases':[],'country':'','phase_budgets':{k:round(v*duration/900,2) for k,v in PHASE_SECONDS.items()},
           'queries':[],'linkedin_direct':[],'employer_requests':[],'ai_calls':[],
           'counts':{'discovered':0,'accepted':0,'duplicates':0,'discarded':0,'evaluated':0},
            'discarded_candidates':[],'market_outcomes':{},'descriptions':{},'linkedin_permission':bool(self.store.get('profile').get('linkedin_consent'))}
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
                record['cli_events']={k:telemetry[k] for k in ('cli_started','event_count','event_types','item_types','first_event_seconds','last_event_seconds') if k in telemetry}
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
            if not old:
                old=next((prior for prior in known.values()
                          if same_posting(prior,job)),None)
            if old:
                d['counts']['duplicates']+=1
                incoming_url=job['url']
                job['id']=old['id']
                job['alternate_urls']=sorted(set(old.get('alternate_urls',[])+
                                                  [old.get('url',''),incoming_url])-{''})
                # Preserve stable source identity, especially a LinkedIn job ID,
                # while still retaining official employer source observations.
                job['url']=old.get('url',job['url'])
                job['source_id']=old.get('source_id',job.get('source_id'))
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
            return job['id']

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
                saved_id=save(job)
                links.setdefault(saved_id,[]).extend(candidate.get('description_sources',[]))

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
            global_learning=(self.store.get('learned:global',[]) or [])+(self.store.get('learned',[]) or [])
            knowledge={'cv_text':profile['cv_text'],'original_request':profile.get('looking_for',''),'intent':profile.get('intent'),'markets':all_markets,
                       'learned':{m['id']:self.store.get('learned:'+m['id'],[]) for m in all_markets},'global_learned':global_learning,'feedback':self.store.get('persistent_feedback',[])}
            signature=hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
            brief=self.store.get('professional_background') if self.store.get('knowledge_signature')==signature else None
            strategy=initial_plan(profile,markets,brief)
            plans={v['market_id']:v for v in strategy['markets']}
            if len(plans)!=len(strategy['markets']) or set(plans)!={m['id'] for m in markets}:raise ValueError('Research strategy must cover every selected market exactly once.')
            for m in markets:
                for q in plans[m['id']]['linkedin_queries']:
                    if not q['query'].strip() or q['query'].startswith('-') or not valid_query(q,m,scope_for(profile,m)):raise ValueError('Strategy query/location invalid or outside saved preferences; no source request sent.')
            phase('discovery')
            # Every consented market gets its first direct attempt before ANY inference.
            linkedin.deadline=phase_end-45*len(markets)
            for m in markets:
                d['country']=m['country']
                if plans[m['id']]['linkedin_queries'] and available():direct(plans[m['id']]['linkedin_queries'][0],m)
            if not brief:
                brief={'background':[],'direction':'; '.join(strategy['role_families']),'country_preferences':[]}
                payload['warnings'].append('No current anonymous background cached; web discovery uses saved intent seeds. CV suitability is assessed privately later.')
            pending=list(markets);passes={m['id']:0 for m in markets};avenues={m['id']:[] for m in markets}
            while pending and available():
                m=pending.pop(0);d['country']=m['country'];plan=plans[m['id']];n=passes[m['id']];passes[m['id']]+=1
                visit_end=min(phase_end,time.monotonic()+(phase_end-time.monotonic())/(len(pending)+1))
                linkedin.deadline=visit_end-45  # Reserve indexed discovery for this market too.
                if n+1<len(plan['linkedin_queries']) and linkedin.deadline-time.monotonic()>1:direct(plan['linkedin_queries'][n+1],m)
                before=d['counts']['accepted'];previous_queries=set(queries)
                try:
                    result=call('research_v5',RESEARCH,{'background':brief['background'],'career_direction':brief['direction'],'strategy':strategy['strategy'],'role_families':strategy['role_families'],
                        'market':{k:m[k] for k in ('id','country','locations','scope_type','remote','relocation') if k in m},'planned_queries':plan['web_queries'],'country_preferences':[v for v in brief['country_preferences'] if v['country_id']==m['id']],
                        'career_goals':profile.get('looking_for','')[:2000],
                        'career_evidence':[x.get('text','')[:500] for x in (profile.get('intent') or {}).get('experience',[])[:8]],
                        'priority_employers':[p.get('value','') for p in (profile.get('intent') or {}).get('preferences',[])
                                              if p.get('topic') in ('target_employers','employer_priority') and p.get('origin')=='explicit'][:8],
                        'previous_queries':sorted(queries),'known_postings':[{'id':j['id'],'url':j['url']} for j in self.store.jobs()],
                        'next_avenues':avenues[m['id']],'restricted_publishers':self.store.access_restrictions(),'linkedin_access':linkedin_state(self.store),'linkedin_stop':self.store.get('linkedin_stop')},True,max(1,visit_end-time.monotonic()))
                    telemetry=ai.telemetry
                    if not telemetry.get('web_calls') or telemetry.get('research_unverified'):raise ProviderError('No genuine web-tool observations; model-only discoveries refused.','unverified_research')
                    indexed(result,telemetry)
                    payload['warnings'].extend(safe_text(v) for v in result['limitations'])
                    new_avenues=result['next_avenues'];new=d['counts']['accepted']-before
                    expand=result['continue_research'] and new_avenues and passes[m['id']]<2 and new>0 and (queries!=previous_queries or new_avenues!=avenues[m['id']])
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
                    if exc.category in ('execution_error','subscription_usage_limit','provider_rate_limit','model_access'):
                        raise  # Provider-wide failure is not another market's search avenue.
                progress('Discovery coverage saved · '+m['country'])
            if pending:payload['warnings'].append('Discovery phase budget reached; saved findings retained.')
            if not self.store.jobs() and d.get('failures') and all(v['status'] not in ('avenues_exhausted','more_avenues') for v in d['market_outcomes'].values()):
                raise ProviderError('Indexed discovery failed: '+'; '.join(f['country']+': '+f['reason'] for f in d['failures'])+'. No automatic retry.','discovery_failed')
            phase('enrichment')
            jobs=self.store.jobs()
            shortlisted=set()
            for start in range(0,len(jobs),40):
                if not available():payload['warnings'].append('Enrichment phase budget reached.');break
                batch=jobs[start:start+40]
                # Triage uses compact verified snippets, not every entire source
                # observation from every model web search.
                lean=[{'id':j['id'],'title':j.get('title',''),'company':j.get('company',''),
                       'location':j.get('location',''),'country':j.get('country',''),
                       'workplace':j.get('workplace',''),
                       'source_excerpt':(j.get('description') or ' '.join(
                            x.get('text','') for x in j.get('source_observations',[])[:2]))[:1050]}
                      for j in batch]
                selection=call('enrichment',ENRICH,
                               {'profile':private_profile(profile),'background':brief,'jobs':lean})
                validate('enrichment',selection)
                chosen=selection['candidate_ids'];by_id={j['id']:j for j in batch}
                if len(set(chosen))!=len(chosen) or not set(chosen)<=set(by_id):raise ValueError('Enrichment selection identity mismatch.')
                shortlisted.update(chosen)
                for considered in batch:
                    self.store.upsert_job({'id':considered['id'],
                        'shortlist_status':'selected' if considered['id'] in chosen else 'low_relevance'})
                d.setdefault('triage',{'selected':0,'low_relevance':0})
                d['triage']['selected']+=len(chosen)
                d['triage']['low_relevance']+=len(batch)-len(chosen)
                progress('Shortlisted credible candidates · '+str(len(shortlisted)))
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
            jobs=[j for j in self.store.jobs() if j['id'] in shortlisted];groups=[]
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
                try:
                    stats=assess(PrivateCalls(),self.store,group,scoped,feedback)
                    payload['usage']['cached_assessments']+=stats['cached']
                    d.setdefault('evaluation_quality',{'valid':0,'needs_verification':0})
                    d['evaluation_quality']['valid']+=stats['assessed']
                    d['evaluation_quality']['needs_verification']+=stats.get('invalid_evidence',0)
                except (ValueError,ProviderError) as exc:
                    # Validation mistakes cannot erase independent groups.
                    d.setdefault('failures',[]).append({'phase':'evaluation',
                        'country':d['country'],'reason':getattr(exc,'category','validation_error'),
                        'stage':'Batch withheld; valid earlier groups retained'})
                    payload['warnings'].append('Evaluation incomplete for '+d['country'])
                    if getattr(exc,'category','') in ('subscription_usage_limit','model_access','provider_rate_limit'):
                        break
                progress('Batched career suitability saved · '+d['country'])
            d['completed_phases'].append('evaluation')
            if not shortlisted and self.store.jobs():
                payload['warnings'].append('No vacancies passed evidence-aware career triage; research findings remain available.')
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
,'',piece,flags=re.I)
            words=piece.split()
            if 2<=len(words)<=7 and len(piece)<=75 and not piece.endswith(('.', '?', '!')):
                if piece not in out:out.append(piece)
        return out[:7]
    for market in markets:
        values=[p.get('value','') for p in entries
                if p.get('topic') in ('target_roles','role_families','career_direction','management_progression')
                and p.get('scope','') in ('',market['id']) and p.get('origin') in ('explicit','cv_evidenced')]
        values += [(brief or {}).get('direction',''), intent.get('summary',''), profile.get('looking_for','')]
        terms=[]
        places={place for m in profile['markets'] for place in [m['country'],*m['locations']]}
        for value in values:
            for term in concise(value):
                for place in sorted(places,key=len,reverse=True):
                    term=re.sub(r'(?<!\w)'+re.escape(place)+r'(?!\w)',' ',term,flags=re.I)
                term=' '.join(term.split()).strip(' ,-.')
                if 2<=len(term.split())<=7 and term not in terms:terms.append(term)
        locations=query_locations(market)[:3]
        # Interleave role families and towns rather than using up every source
        # request on one generic term in three towns.
        queries=[dict(query=terms[i % len(terms)],location=locations[i % len(locations)],
                      remote='any',reason='Explicit career-goal role phrase')
                 for i in range(min(8,len(terms)*len(locations)))] if terms and locations else []
        plans.append({'market_id':market['id'],'linkedin_queries':queries,'web_queries':terms[:7]})
        families.extend(term for term in terms if term not in families)
    return {'strategy':'Explore true responsibility matches, credible leadership progression, confirmed location and source freshness using the saved career request.',
            'role_families':families[:12],'markets':plans}


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
        d={'started_at':now(),'elapsed_seconds':0,'total_budget_seconds':duration,'phase':'discovery',
           'completed_phases':[],'country':'','phase_budgets':{k:round(v*duration/900,2) for k,v in PHASE_SECONDS.items()},
           'queries':[],'linkedin_direct':[],'employer_requests':[],'ai_calls':[],
           'counts':{'discovered':0,'accepted':0,'duplicates':0,'discarded':0,'evaluated':0},
            'discarded_candidates':[],'market_outcomes':{},'descriptions':{},'linkedin_permission':bool(self.store.get('profile').get('linkedin_consent'))}
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
                record['cli_events']={k:telemetry[k] for k in ('cli_started','event_count','event_types','item_types','first_event_seconds','last_event_seconds') if k in telemetry}
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
            if not old:
                old=next((prior for prior in known.values()
                          if same_posting(prior,job)),None)
            if old:
                d['counts']['duplicates']+=1
                incoming_url=job['url']
                job['id']=old['id']
                job['alternate_urls']=sorted(set(old.get('alternate_urls',[])+
                                                  [old.get('url',''),incoming_url])-{''})
                # Preserve stable source identity, especially a LinkedIn job ID,
                # while still retaining official employer source observations.
                job['url']=old.get('url',job['url'])
                job['source_id']=old.get('source_id',job.get('source_id'))
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
            return job['id']

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
                saved_id=save(job)
                links.setdefault(saved_id,[]).extend(candidate.get('description_sources',[]))

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
            global_learning=(self.store.get('learned:global',[]) or [])+(self.store.get('learned',[]) or [])
            knowledge={'cv_text':profile['cv_text'],'original_request':profile.get('looking_for',''),'intent':profile.get('intent'),'markets':all_markets,
                       'learned':{m['id']:self.store.get('learned:'+m['id'],[]) for m in all_markets},'global_learned':global_learning,'feedback':self.store.get('persistent_feedback',[])}
            signature=hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
            brief=self.store.get('professional_background') if self.store.get('knowledge_signature')==signature else None
            strategy=initial_plan(profile,markets,brief)
            plans={v['market_id']:v for v in strategy['markets']}
            if len(plans)!=len(strategy['markets']) or set(plans)!={m['id'] for m in markets}:raise ValueError('Research strategy must cover every selected market exactly once.')
            for m in markets:
                for q in plans[m['id']]['linkedin_queries']:
                    if not q['query'].strip() or q['query'].startswith('-') or not valid_query(q,m,scope_for(profile,m)):raise ValueError('Strategy query/location invalid or outside saved preferences; no source request sent.')
            phase('discovery')
            # Every consented market gets its first direct attempt before ANY inference.
            linkedin.deadline=phase_end-45*len(markets)
            for m in markets:
                d['country']=m['country']
                if plans[m['id']]['linkedin_queries'] and available():direct(plans[m['id']]['linkedin_queries'][0],m)
            if not brief:
                brief={'background':[],'direction':'; '.join(strategy['role_families']),'country_preferences':[]}
                payload['warnings'].append('No current anonymous background cached; web discovery uses saved intent seeds. CV suitability is assessed privately later.')
            pending=list(markets);passes={m['id']:0 for m in markets};avenues={m['id']:[] for m in markets}
            while pending and available():
                m=pending.pop(0);d['country']=m['country'];plan=plans[m['id']];n=passes[m['id']];passes[m['id']]+=1
                visit_end=min(phase_end,time.monotonic()+(phase_end-time.monotonic())/(len(pending)+1))
                linkedin.deadline=visit_end-45  # Reserve indexed discovery for this market too.
                if n+1<len(plan['linkedin_queries']) and linkedin.deadline-time.monotonic()>1:direct(plan['linkedin_queries'][n+1],m)
                before=d['counts']['accepted'];previous_queries=set(queries)
                try:
                    result=call('research_v5',RESEARCH,{'background':brief['background'],'career_direction':brief['direction'],'strategy':strategy['strategy'],'role_families':strategy['role_families'],
                        'market':{k:m[k] for k in ('id','country','locations','scope_type','remote','relocation') if k in m},'planned_queries':plan['web_queries'],'country_preferences':[v for v in brief['country_preferences'] if v['country_id']==m['id']],
                        'career_goals':profile.get('looking_for','')[:2000],
                        'career_evidence':[x.get('text','')[:500] for x in (profile.get('intent') or {}).get('experience',[])[:8]],
                        'priority_employers':[p.get('value','') for p in (profile.get('intent') or {}).get('preferences',[])
                                              if p.get('topic') in ('target_employers','employer_priority') and p.get('origin')=='explicit'][:8],
                        'previous_queries':sorted(queries),'known_postings':[{'id':j['id'],'url':j['url']} for j in self.store.jobs()],
                        'next_avenues':avenues[m['id']],'restricted_publishers':self.store.access_restrictions(),'linkedin_access':linkedin_state(self.store),'linkedin_stop':self.store.get('linkedin_stop')},True,max(1,visit_end-time.monotonic()))
                    telemetry=ai.telemetry
                    if not telemetry.get('web_calls') or telemetry.get('research_unverified'):raise ProviderError('No genuine web-tool observations; model-only discoveries refused.','unverified_research')
                    indexed(result,telemetry)
                    payload['warnings'].extend(safe_text(v) for v in result['limitations'])
                    new_avenues=result['next_avenues'];new=d['counts']['accepted']-before
                    expand=result['continue_research'] and new_avenues and passes[m['id']]<2 and new>0 and (queries!=previous_queries or new_avenues!=avenues[m['id']])
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
                    if exc.category in ('execution_error','subscription_usage_limit','provider_rate_limit','model_access'):
                        raise  # Provider-wide failure is not another market's search avenue.
                progress('Discovery coverage saved · '+m['country'])
            if pending:payload['warnings'].append('Discovery phase budget reached; saved findings retained.')
            if not self.store.jobs() and d.get('failures') and all(v['status'] not in ('avenues_exhausted','more_avenues') for v in d['market_outcomes'].values()):
                raise ProviderError('Indexed discovery failed: '+'; '.join(f['country']+': '+f['reason'] for f in d['failures'])+'. No automatic retry.','discovery_failed')
            phase('enrichment')
            jobs=self.store.jobs()
            shortlisted=set()
            for start in range(0,len(jobs),40):
                if not available():payload['warnings'].append('Enrichment phase budget reached.');break
                batch=jobs[start:start+40]
                # Triage uses compact verified snippets, not every entire source
                # observation from every model web search.
                lean=[{'id':j['id'],'title':j.get('title',''),'company':j.get('company',''),
                       'location':j.get('location',''),'country':j.get('country',''),
                       'workplace':j.get('workplace',''),
                       'source_excerpt':(j.get('description') or ' '.join(
                            x.get('text','') for x in j.get('source_observations',[])[:2]))[:1050]}
                      for j in batch]
                selection=call('enrichment',ENRICH,
                               {'profile':private_profile(profile),'background':brief,'jobs':lean})
                validate('enrichment',selection)
                chosen=selection['candidate_ids'];by_id={j['id']:j for j in batch}
                if len(set(chosen))!=len(chosen) or not set(chosen)<=set(by_id):raise ValueError('Enrichment selection identity mismatch.')
                shortlisted.update(chosen)
                for considered in batch:
                    self.store.upsert_job({'id':considered['id'],
                        'shortlist_status':'selected' if considered['id'] in chosen else 'low_relevance'})
                d.setdefault('triage',{'selected':0,'low_relevance':0})
                d['triage']['selected']+=len(chosen)
                d['triage']['low_relevance']+=len(batch)-len(chosen)
                progress('Shortlisted credible candidates · '+str(len(shortlisted)))
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
            jobs=[j for j in self.store.jobs() if j['id'] in shortlisted];groups=[]
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
                try:
                    stats=assess(PrivateCalls(),self.store,group,scoped,feedback)
                    payload['usage']['cached_assessments']+=stats['cached']
                    d.setdefault('evaluation_quality',{'valid':0,'needs_verification':0})
                    d['evaluation_quality']['valid']+=stats['assessed']
                    d['evaluation_quality']['needs_verification']+=stats.get('invalid_evidence',0)
                except (ValueError,ProviderError) as exc:
                    # Validation mistakes cannot erase independent groups.
                    d.setdefault('failures',[]).append({'phase':'evaluation',
                        'country':d['country'],'reason':getattr(exc,'category','validation_error'),
                        'stage':'Batch withheld; valid earlier groups retained'})
                    payload['warnings'].append('Evaluation incomplete for '+d['country'])
                    if getattr(exc,'category','') in ('subscription_usage_limit','model_access','provider_rate_limit'):
                        break
                progress('Batched career suitability saved · '+d['country'])
            d['completed_phases'].append('evaluation')
            if not shortlisted and self.store.jobs():
                payload['warnings'].append('No vacancies passed evidence-aware career triage; research findings remain available.')
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
