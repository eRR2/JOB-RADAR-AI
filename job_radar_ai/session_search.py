"""Small evidence-driven research rounds on one cumulative bounded coordinator."""
import hashlib
import json
import re
import time
import threading
from urllib.parse import urlsplit
from .hunter import Hunter, DEFAULT_BUDGETS
from .providers import Provider, ProviderError
from .observations import observed_job,retained_observation,observed_description_sources
from .store import SessionExpired, now
from .location import geography
from .markets import market_profile, country_of, query_locations
from .geography import valid_query, scope_for
from .recommendations import assess, private_profile, active, verified_description
from .identity import normalized_url, linkedin_job_id
from .history import same_posting
from .sources import PublicFetcher, RetrievalError
from .completion import recover, recover_page, freshness
from .linkedin import LinkedIn, SourceError
from .access import linkedin_state
from .contracts import validate
from .reporting import review_state, coverage, compared_opportunities
from .verification import triage_batches, ranked_candidates, assessment_batches, triage_decisions,triage_output_size,TRIAGE_INPUT_CHARS
from .availability import observation,merge_states

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
No private CV text, names, contacts or identifying history in public queries.
Copy requisition_id only when an employer requisition is literally observed;
do not substitute a LinkedIn listing ID for an employer requisition.'''
RESEARCH += ''' Interpret the requested leadership progression together with the
demonstrated technical background. Shared seniority or architecture titles do not
establish transferability into a different core discipline; actual responsibilities
must support that move. Preserve the user's technical scope without industry or
title blacklists.'''
RESEARCH += ''' Retain actually observed original employer posting URLs and alternate
canonical job URLs in description_sources, with employer requisition when observed.
A LinkedIn listing alone supplies no independent employer description access. Never
guess job slugs, use homepages as full postings or invent replacement URLs.'''
ENRICH = '''First apply a strict but fair relevance triage. Select potentially strong candidates worth enriching from this batch of actual
observed source evidence and the actual CV/next-career direction. Prioritize demonstrated
responsibilities, credible progression and leadership; do not choose title-only specialist
mismatches. Missing description is uncertainty, not automatic rejection. Exclude clear
specialist-domain mismatches, unrelated roles, implausible seniority or geographic
mismatches, but preserve credible stretch roles and cross-sector leadership.
Select only evidence-backed credible next moves; do not fill a quota.
Return exact supplied candidate_ids in priority order. This is relevance
selection, NOT a final recommendation. No tools.'''
ENRICH += ''' Return one decisions entry for EVERY supplied job. Preserve its individual
reason and SHORT source_quote; separate transferable system/leadership capability
from a demonstrated mandatory specialist gap. Missing duties or uncertain expertise
must use needs_evidence, never low_relevance. Only an observed, quoted mismatch may
use low_relevance. An application/rejection decision is workflow state, never evidence
of technical irrelevance. candidate_ids orders candidates worth verifying.'''
ENRICH += ''' Keep each reason under 300 characters, transferable fit and specialist
gap under 200 each, literal quote under 240, and at most two missing facts under 120
characters each. Judge the technical responsibility and leadership scope against the
actual CV and requested next move. A senior title alone neither proves progression
nor rules out transferable capability. No repetitive commentary.'''

GUIDANCE = '''Privately direct the NEXT small research round from the actual CV,
career request and observed findings. No tools. Distill transferable capabilities,
demonstrated specialist gaps, unsuccessful queries and missing publisher evidence.
An absent description is uncertainty, not unsuitability. Never turn application or
rejection state into career preference. Country-specific preferences apply ONLY to
next_market. Propose up to three concise new searches for that country, with credible
technical responsibility and progression; avoid already unsuccessful queries.
Output is public research context: anonymize ALL fields. No names, contacts, career
history employers, projects, CV quotations, private feedback or application history.
Use generic capability language rather than quoting private findings. Recommend
continuation only for a distinct useful avenue, not another attempt at a failed call.'''
RESEARCH += ''' This is ONE focused small round, with at most eight observed jobs.
Follow round_findings and planned_queries derived from prior verified findings.
Begin with employer_focus when supplied, then diversify; a productive employer must
not consume all rounds. Retain exact observed sources for this round's evidence review.'''
RESEARCH += ''' For source_gaps, seek the exact existing posting's observed original
publisher duties and requirements. You may return a known identity ONLY with new
observed source evidence, not another unchanged snippet. This is source recovery,
not permission to retry a denied publisher or guess an alternative endpoint.'''


def round_finding(job):
    """Bounded private evidence summary, never forwarded directly to web tools."""
    preliminary=job.get('preliminary') or {}
    return {'id':job['id'],'country':job.get('country',''),
        'triage_decision':job.get('triage_decision',{}),'triage_review':job.get('triage_review',{}),
        'description_review':job.get('description_review',{}),
        'source_complete':verified_description(job),
        'preliminary':{k:preliminary[k] for k in ('priority','category','next_step','gaps','critical_gap') if k in preliminary}}


def public_guidance(value,profile,feedback):
    """Fail closed on obvious private echoes, not a career keyword classifier."""
    pending=[value];parts=[]
    while pending:
        item=pending.pop()
        if isinstance(item,dict):pending.extend(item.values())
        elif isinstance(item,list):pending.extend(item)
        elif isinstance(item,str):parts.append(' '.join(item.split()))
    text=' '.join(parts).casefold()
    private=[profile.get('looking_for',''),profile.get('authoritative_request',''),
             *profile.get('cv_text','').splitlines(),*[f.get('note','') for f in feedback],
             *[v.get('text','') for v in (profile.get('intent') or {}).get('experience',[])]]
    private=[' '.join(v.split()) for v in private]
    if re.search(r'\b[^\s@]+@[^\s@]+\.[^\s@]+|(?<!\w)\+?\d[\d ()-]{7,}\d',text) or any(
            len(v)>=12 and v.casefold() in text for v in private):
        raise ValueError('Round guidance contained private text; public transfer refused.')


def evidence_version(job):
    """Only changed observed bytes/URLs can reopen work, never timestamps alone."""
    observations=job.get('source_observations',[])+job.get('description_observations',[])
    pages=sorted({(normalized_url(o['url']) if o.get('url') else '',o.get('observation_kind',o.get('kind','')),
                   o.get('page_text') or o.get('text') or o.get('content','')) for o in observations})
    sources=sorted({normalized_url(s['url']) for s in job.get('description_sources',[])})
    return hashlib.sha256(json.dumps([pages,sources],sort_keys=True).encode()).hexdigest()


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
        # Semicolon-separated complete role phrases are transport seeds. Splitting
        # commas/conjunctions turns seniority prose into an unrelated title query.
        pieces=re.split(r'[;/\n]',value)
        out=[]
        for piece in pieces:
            piece=re.sub(r'https?://\S+|\b[^\s@]+@[^\s@]+\.[^\s@]+|(?<!\w)\+?\d[\d ()-]{7,}\d',' ',piece)
            piece=re.sub(r'^(?:next|goal|ziel|hedef)\s*:\s*','',piece,flags=re.I)
            piece=' '.join(piece.split()).strip(' ,-.:')
            piece=re.sub(r'\s+(?:in|at|near|im|bei)$','',piece,flags=re.I)
            words=piece.split()
            if ',' not in piece and 2<=len(words)<=7 and len(piece)<=75 and not piece.endswith(('.', '?', '!')):
                if piece not in out:out.append(piece)
        return out[:7]
    for market in markets:
        values=[p.get('value','') for p in entries
                if p.get('topic') in ('target_roles','role_families','career_direction','management_progression')
                and p.get('scope','') in ('',market['id']) and p.get('origin') in ('explicit','cv_evidenced')]
        if not values:
            values=[(brief or {}).get('direction','')]
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
        phase_started=started;current_phase=None
        spent={k:0.0 for k in PHASE_SECONDS};round_spent=spent.copy()
        round_caps={k:v*duration/900 for k,v in PHASE_SECONDS.items()}
        triage_spent=0.0
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
        queries=set();unsuccessful={};links={};native=[];observed_urls=set()
        call_limit=MAX_AI_CALLS
        known={j['id']:j for j in self.store.jobs()};url_index={normalized_url(j['url']):j for j in known.values()}
        profile=self.store.get('profile');all_markets=profile['markets']
        markets=[m for m in all_markets if market_id=='all' or m['id']==market_id]
        def employers_for(m):
            return list(dict.fromkeys(p.get('value','').strip() for p in (profile.get('intent') or {}).get('preferences',[])
                if p.get('topic') in ('employers','target_employers','employer_priority') and p.get('origin')=='explicit'
                and p.get('scope','') in ('',m['id']) and p.get('value','').strip()))

        required_visits={m['id']:max(1,len(employers_for(m))) for m in markets}

        def source_note(job,url,status='unknown',quote='',http_status=None,provenance='transport',checked_at=None):
            item=observation(job,url,status,quote,checked_at or now(),provenance,http_status)
            job['source_availability']=merge_states(job.get('source_availability'),{item['url']:item})
            self.store.upsert_job({'id':job['id'],'source_availability':job['source_availability']})

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
                if linkedin_job_id(value):return normalized_url(value)
                p=urlsplit(value)
                return safe_text(p.scheme+'://'+(p.hostname or '')+p.path)
            except ValueError:return '[unsafe URL omitted]'

        def progress(stage):
            tick=time.monotonic()
            d['elapsed_seconds']=round(tick-started,3)
            d['phase_spent']={k:round(v+(tick-phase_started if k==current_phase else 0),3) for k,v in spent.items()}
            payload['requests']=fetcher.requests+linkedin.requests
            d['employer_requests']=[{**v,'endpoint':safe_url(v['endpoint']),'parameters':{k:[safe_text(x) for x in vals] for k,vals in v.get('parameters',{}).items()}} for v in getattr(fetcher,'diagnostics',[])]
            jobs=self.store.jobs();payload['job_ids']=[j['id'] for j in jobs]
            d['descriptions']={
                'full':sum(verified_description(j) for j in jobs),
                'partial':sum(bool(j.get('partial_source_text') or j.get('description')) and not verified_description(j) for j in jobs),
                'snippet_only':sum(not j.get('description') and not j.get('partial_source_text') for j in jobs)}
            d['coverage']=coverage(jobs,d)
            selected=[j for j in jobs if j.get('shortlist_status')=='selected']
            triaged=[j for j in jobs if active(j)]
            d['triage']={
                'selected':sum(j.get('shortlist_status')=='selected' for j in triaged),
                'low_relevance':sum(j.get('shortlist_status')=='low_relevance' for j in triaged),
                'failed':sum(j.get('triage_review',{}).get('status')=='failed' for j in triaged),
                'pending':sum(j.get('triage_review',{}).get('status') not in ('completed','failed') for j in triaged),
                'reason_missing':sum(j.get('triage_decision',{}).get('action')=='not_selected' for j in triaged)}
            d['verification']={'selected':len(selected),
                'ready_for_assessment':sum(active(j) and verified_description(j) for j in selected),
                'source_pending':sum(active(j) and not verified_description(j) for j in selected)}
            d['source_recovery']={
                'reused_pages':sum(j.get('description_review',{}).get('source_coverage',{}).get('reused_page',False) for j in selected),
                'outcomes':{reason:sum(j.get('description_review',{}).get('reason')==reason for j in selected) for reason in
                    ('verified_source','no_observed_description_source','source_access_failed','source_parsing_failed','source_identity_unverified','enrichment_budget')}}
            d['counts']['evaluated']=d['coverage']['assessed']
            self.store.update_run(run_id,stage,payload)

        def settle():
            nonlocal phase_started
            tick=time.monotonic()
            if current_phase:
                elapsed=tick-phase_started
                spent[current_phase]+=elapsed;round_spent[current_phase]+=elapsed
            phase_started=tick

        def phase(name):
            nonlocal phase_end,current_phase
            settle()
            if cancel.is_set():raise ProviderError('Canceled by user.','canceled')
            if time.monotonic()>=deadline:raise ProviderError('Total research budget reached; saved findings retained.','total_budget')
            current_phase=name;d['phase']=name;d['country']=''
            remaining=min(d['phase_budgets'][name]-spent[name],round_caps[name]-round_spent[name])
            phase_end=min(deadline,time.monotonic()+max(0,remaining))
            fetcher.deadline=phase_end;linkedin.deadline=phase_end
            progress('Research phase: '+name)

        def available():return not cancel.is_set() and time.monotonic()<phase_end-1

        def call(kind,task,data,research=False,allowance=None):
            nonlocal triage_spent
            ai.telemetry={}
            if cancel.is_set():raise ProviderError('Canceled by user.','canceled')
            remaining=min(deadline,phase_end)-time.monotonic()
            if remaining<=1:raise ProviderError('Phase time budget reached; current results retained.','phase_budget')
            if payload['usage']['ai_invocations']>=call_limit:raise ProviderError('Bounded AI invocation budget reached; current results retained.','invocation_budget')
            record={'kind':kind,'phase':d['phase'],'country':d['country'],'started_at':now(),'status':'running','seconds':0}
            record['job_ids']=[j['id'] for j in data.get('jobs',[]) if j.get('id')]
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
                if kind=='enrichment':triage_spent+=time.monotonic()-began
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
            # URL/type metadata makes unassociated observations distinguishable
            # from a source never observed. Page bodies remain in private records.
            d.setdefault('observed_sources',[]).extend({'url':safe_url(o['url']),
                'kind':o.get('observation_kind','search_snippet')} for o in observations if o.get('url'))
            for candidate in result['jobs']:
                rejected=[];job=observed_job(candidate,observations,rejected)
                if not job:
                    d['counts']['discovered']+=1;d['counts']['discarded']+=1
                    d['discarded_candidates'].extend({'url':safe_url(r['url']) if r['reason']!='unsafe_url' else '[unsafe URL omitted]','reason':r['reason'],'country':d['country']} for r in rejected)
                    continue
                saved_id=save(job)
                source_refs=observed_description_sources(candidate.get('description_sources',[]),observed_urls)
                # A deduplicated employer observation must remain a source even
                # when the stable vacancy identity is the earlier LinkedIn URL.
                for url in known[saved_id].get('alternate_urls',[]):
                    if normalized_url(url) in observed_urls:source_refs.append({'url':url,'employer_url':''})
                links.setdefault(saved_id,[]).extend(source_refs)
                source_urls={normalized_url(ref['url']) for ref in links[saved_id]}
                descriptions=known[saved_id].get('description_observations',[])
                for o in observations:
                    try:
                        if o.get('url') and normalized_url(o['url']) in source_urls:
                            descriptions.append(retained_observation(o))
                    except ValueError:continue
                self.store.upsert_job({'id':saved_id,'description_sources':links[saved_id],
                    'description_observations':descriptions})
                known[saved_id]['description_observations']=descriptions

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

        shortlisted=set();processed={};provider_blocked=False;stop_reason=None;reserved_discovery=0
        d['triage']={'selected':0,'low_relevance':0,'failed':0,'pending':0}

        def process_candidates(jobs):
            nonlocal call_limit,provider_blocked,stop_reason
            if not jobs:return
            rank_offset=len(processed)
            processed.update((j['id'],evidence_version(j)) for j in jobs)
            triage_context={'profile':private_profile(profile),'background':brief}
            instruction_chars=len(ENRICH)+2000  # Reserve the private provider wrapper too.
            shared_chars=len(json.dumps({**triage_context,'jobs':[]}))+instruction_chars
            triage_groups=list(triage_batches(jobs,shared_chars))
            # Splitting one large triage call must not consume the allowance
            # reserved for assessments. Extra slots are bounded and reported.
            extra_triage_calls=min(max(0,len(triage_groups)-1),MAX_AI_CALLS-(call_limit-MAX_AI_CALLS))
            call_limit+=extra_triage_calls
            d['ai_call_budget']={'base':MAX_AI_CALLS,'additional_triage_slots':call_limit-MAX_AI_CALLS,'total':call_limit}
            for candidate in jobs:
                self.store.upsert_job({'id':candidate['id'],'triage_review':{'status':'pending','reason':'triage_budget'}})
            all_by_id={j['id']:j for j in jobs}
            for batch_index,lean in enumerate(triage_groups):
                phase('enrichment')
                triage_end=min(phase_end,time.monotonic()+max(0,d['phase_budgets']['enrichment']*.6-triage_spent))
                if payload['usage']['ai_invocations']>=call_limit-reserved_discovery:
                    payload['warnings'].append('Triage deferred to preserve first discovery coverage of selected countries.')
                    d.setdefault('phase_outcomes',{})['enrichment']='partial'
                    break
                if not available() or time.monotonic()>=triage_end-1:
                    payload['warnings'].append('Enrichment phase budget reached.')
                    d.setdefault('phase_outcomes',{})['enrichment']='partial'
                    break
                batch=[all_by_id[item['id']] for item in lean]
                data={**triage_context,'jobs':lean}
                record={'job_ids':[j['id'] for j in lean],'input_chars':len(json.dumps(data))+instruction_chars,
                    'expected_output_chars':triage_output_size(lean),'status':'running'}
                d.setdefault('triage_batches',[]).append(record)
                try:
                    if record['input_chars']>TRIAGE_INPUT_CHARS:
                        raise ValueError('Private triage input exceeds the bounded context; no call started.')
                    selection=call('enrichment',ENRICH,data,allowance=min(30,max(1,triage_end-time.monotonic())))
                    validate('enrichment',selection)
                    chosen,decisions=triage_decisions(selection,lean)
                except (ValueError,ProviderError) as exc:
                    category=getattr(exc,'category','validation_error')
                    reason='triage_timeout' if category=='time_window' else 'triage_error'
                    record.update(status='failed',reason=category)
                    d.setdefault('failures',[]).append({'phase':'enrichment','country':'','reason':category,
                        'stage':'Career triage batch','job_ids':record['job_ids']})
                    payload['warnings'].append('A relevance triage batch could not finish; its candidates remain unassessed.')
                    for candidate in batch:
                        self.store.upsert_job({'id':candidate['id'],'triage_review':{'status':'failed','reason':reason}})
                    progress('Triage batch retained; independent candidates continue')
                    if category in ('execution_error','subscription_usage_limit','provider_rate_limit','model_access','invocation_budget','total_budget','canceled'):
                        provider_blocked=True;break
                    if category=='phase_budget':break
                    continue
                record['status']='completed'
                shortlisted.update(chosen)
                for considered in batch:
                    self.store.upsert_job({'id':considered['id'],
                        'triage_decision':{**decisions[considered['id']],'at':now()},
                        'triage_review':{'status':'completed','reason':'source_based_triage'},
                        'shortlist_status':'selected' if considered['id'] in chosen else 'low_relevance' if decisions[considered['id']]['action']=='low_relevance' else 'not_selected',
                        'shortlist_rank':rank_offset+batch_index*8+chosen.index(considered['id']) if considered['id'] in chosen else None,
                        'description_review':{'status':'pending','reason':'enrichment_budget'} if considered['id'] in chosen else {'status':'not_selected','reason':'triage_not_selected' if decisions[considered['id']]['action']=='low_relevance' else 'triage_reason_missing'}})
                progress('Shortlisted credible candidates · '+str(len(shortlisted)))
                by_id={j['id']:j for j in self.store.jobs()}
                for candidate in ranked_candidates([j for j in by_id.values() if j['id'] in chosen]):
                    job_id=candidate['id']
                    if not available():break
                    job=by_id[job_id];d['country']=job.get('country','') or 'Location unverified'
                    if job.get('description'):
                        self.store.upsert_job({'id':job_id,'description_review':{'status':'available','reason':'existing_source_text'}})
                        continue
                    full=None
                    attempts=[];refused_pages=set();reused_page=False
                    source_links=list(links.get(job_id,[]))
                    host=urlsplit(job['url']).hostname or ''
                    if host!='linkedin.com' and not host.endswith('.linkedin.com'):source_links.insert(0,{'url':job['url'],'employer_url':''})
                    # Distinct observed publication URLs, not repeated references.
                    source_links=list({normalized_url(ref['url']):ref for ref in source_links}.values())
                    source_urls={normalized_url(ref['url']) for ref in source_links}|{normalized_url(job['url'])}
                    independent=sum(not linkedin_job_id(ref['url']) and bool(urlsplit(ref['url']).path.strip('/')) for ref in source_links)
                    reads=0;seen_pages=set()
                    for o in native+job.get('description_observations',[])+job.get('source_observations',[]):
                        text=o.get('page_text') or o.get('text') or o.get('content','')
                        url=o.get('url','')
                        try:key=(normalized_url(url),text) if url else None
                        except ValueError:continue
                        if not key or key in seen_pages or key[0] not in source_urls or o.get('observation_kind')!='page_read' or '<' not in text:continue
                        seen_pages.add(key);reads+=1
                        page={'url':url,'text':text,'at':o.get('at') or now(),'bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()}
                        try:
                            full=recover_page(job,page,all_markets);reused_page=True;break
                        except RetrievalError as exc:
                            if exc.stage=='identity':refused_pages.add(key[0])
                            attempts.append({'url':safe_url(url),'status':exc.status,'stage':exc.stage,
                                'checked_at':page['at'],'reuse':'recorded_page','reason':safe_text(str(exc))})
                    for link in source_links if not full else []:
                        if not available():break
                        url=link['url']
                        if linkedin_job_id(url) or not urlsplit(url).path.strip('/'):
                            attempts.append({'url':safe_url(url),'status':'not_a_controlled_job_source','stage':'source_selection','reason':'LinkedIn uses consented guest transport; a homepage is not a job-specific source.'})
                            continue
                        if normalized_url(url) in refused_pages:continue
                        if normalized_url(url) not in observed_urls:continue
                        if normalized_url(url) in unsuccessful:
                            attempts.append({**unsuccessful[normalized_url(url)],'attempted':False,'reuse':'run_failure'})
                            continue
                        try:full=recover(job,url,link['employer_url'],fetcher,all_markets);break
                        except RetrievalError as exc:
                            self.store.upsert_job({'id':job_id,'description_status':exc.status})
                            source_note(job,url,http_status=exc.http_status)
                            attempt={'url':safe_url(url),'status':exc.status,'stage':exc.stage,'http_status':exc.http_status,'checked_at':now(),'reason':safe_text(str(exc))}
                            attempts.append(attempt)
                            if exc.stage=='access':unsuccessful[normalized_url(url)]=attempt
                    if not full and job['id'].startswith('linkedin:') and profile.get('linkedin_consent') and linkedin_state(self.store)['state']=='available' and not linkedin.denied_in_run and linkedin.requests<budgets['requests'] and sum(r['operation']=='detail' for r in d['linkedin_direct'])<budgets['details'] and phase_end-time.monotonic()>30:
                        record={'country':d['country'],'operation':'detail','job_id':job['id'],'status':'running'};d['linkedin_direct'].append(record)
                        before_requests=linkedin.requests
                        try:
                            detail=linkedin.detail(job['source_id']);self.store.upsert_job({**detail,'description_status':'full','description_source':{'kind':'linkedin','url':job['url'],'at':now()},'description_review':{'status':'available','reason':'linkedin_detail','attempts':attempts}})
                            source_note(job,job['url'],'closed' if detail.get('availability')=='closed_banner_observed' else 'unknown',
                                'isActive: false (guest response)' if detail.get('availability')=='closed_banner_observed' else '',provenance='publisher_observed',checked_at=detail.get('description_obtained'))
                            record.update(status='received',http_status=200);progress('LinkedIn detail saved');continue
                        except (SourceError,ProviderError) as exc:
                            state=linkedin_state(self.store);record.update(status=state['state'] if state['state']!='available' else 'source_failed',http_status=state.get('http_status'),reason=safe_text(str(exc)))
                            attempts.append({'url':safe_url(job['url']),'status':record['status'],'stage':'access','reason':record['reason']})
                        finally:record.update(requests=linkedin.requests-before_requests,cache_hit=linkedin.last_cached)
                    elif not full and job['id'].startswith('linkedin:') and profile.get('linkedin_consent') and linkedin_state(self.store)['state']!='available':
                        state=linkedin_state(self.store)
                        source_note(job,job['url'],http_status=state.get('http_status'),provenance='access_policy')
                        attempts.append({'url':safe_url(job['url']),'status':'blocked_shared_stop','stage':'access','http_status':state.get('http_status'),'checked_at':now(),'attempted':False,'reason':'Direct publisher access stopped; no detail request.'})
                    if full:
                        state=freshness(full)
                        source_note(job,full['source_url'],'closed' if state['status']=='confirmed_closed' else 'open' if state['status']=='confirmed_open' else 'unknown',
                            state['evidence'],provenance='publisher_observed',checked_at=full['evidence'].get('at'))
                        self.store.upsert_job({'id':job_id,'description':full['description'],'description_status':'public_verified','location':full.get('location') or job.get('location',''),'country':full.get('country') or job.get('country',''),
                            'requisition_id':full.get('requisition_id') or job.get('requisition_id',''),
                            'description_source':{'kind':'public_verified','url':full['source_url'],'sha256':full['evidence']['sha256'],'at':full['evidence'].get('at') or now()},'freshness':state,
                            'availability':'closed_banner_observed' if state['status']=='confirmed_closed' else 'open_publisher_observed' if state['status']=='confirmed_open' else 'unknown'})
                    failure_stage=next((stage for stage in ('identity','parsing','access') if any(a.get('stage')==stage for a in attempts)),'source_selection')
                    reason='verified_source' if full else 'enrichment_budget' if not available() else 'no_observed_description_source' if not independent else {
                        'identity':'source_identity_unverified','parsing':'source_parsing_failed','access':'source_access_failed'}.get(failure_stage,'no_observed_description_source')
                    self.store.upsert_job({'id':job_id,'description_review':{
                        'status':'available' if full else 'incomplete',
                        'reason':reason,'source_coverage':{'independent_urls':independent,'recorded_page_reads':reads,'reused_page':reused_page},
                        'attempts':attempts}})
                    progress('Candidate source enrichment recorded')
                if any(j.get('shortlist_status')=='selected' and active(j) and not verified_description(j) for j in self.store.jobs()):
                    d.setdefault('phase_outcomes',{})['enrichment']='partial'
                phase('evaluation')
                selected_jobs=[j for j in self.store.jobs() if j['id'] in chosen]
                jobs=ranked_candidates([j for j in selected_jobs if active(j) and verified_description(j)]);groups=[]
                # Batch only adjacent jobs with the same country/learning scope.
                # Collecting each country's tail first would leapfrog global priority.
                for job in jobs:
                    country_id=geography(job,all_markets)['country_id']
                    m=next((m for m in markets if m['id']==country_id),None)
                    if country_id and m is None:continue
                    verified=bool(m and country_of(job,all_markets)==m['id'])
                    if groups and groups[-1][0]==m and groups[-1][1]==verified:
                        groups[-1][2].append(job)
                    else:
                        groups.append((m,verified,[job]))
                queue=[(m,v,b) for m,v,g in groups for b in assessment_batches(g)]
                while queue:
                    m,verified,group=queue.pop(0)
                    if not group:continue
                    if provider_blocked:
                        stop_reason='evaluation_error';break
                    if payload['usage']['ai_invocations']>=call_limit-reserved_discovery:
                        stop_reason='evaluation_budget'
                        payload['warnings'].append('Assessment deferred at the shared AI-call budget; independent country coverage retained.')
                        break
                    if phase_end-time.monotonic()<10:
                        stop_reason='evaluation_budget'
                        d.setdefault('failures',[]).append({'phase':'evaluation','country':m['country'] if m else 'Location unverified','reason':'phase_budget','stage':'Insufficient remaining window for another bounded assessment; no CLI call started'})
                        break
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
                            'stage':'Batch withheld; valid earlier groups retained','job_ids':[j['id'] for j in group]})
                        payload['warnings'].append('Evaluation incomplete for '+d['country'])
                        if isinstance(exc,ProviderError):
                            category=exc.category
                            stop_reason='evaluation_timeout' if category=='time_window' else 'evaluation_budget' if category in ('phase_budget','total_budget','invocation_budget') else 'evaluation_error'
                            for failed in group:
                                self.store.upsert_job({'id':failed['id'],'review_state':{'status':'pending','reason':stop_reason}})
                            if category in ('execution_error','subscription_usage_limit','provider_rate_limit','model_access','invocation_budget','total_budget','canceled'):
                                provider_blocked=True;break
                            if category=='phase_budget':break
                    progress('Batched career suitability saved · '+d['country'])

        try:
            if not markets:raise ValueError('Requested market is not in saved preferences.')
            global_learning=(self.store.get('learned:global',[]) or [])+(self.store.get('learned',[]) or [])
            knowledge={'cv_text':profile['cv_text'],'original_request':profile.get('looking_for',''),'intent':profile.get('intent'),'markets':all_markets,
                       'learned':{m['id']:self.store.get('learned:'+m['id'],[]) for m in all_markets},'global_learned':global_learning,'feedback':self.store.get('persistent_feedback',[])}
            signature=hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
            brief=self.store.get('professional_background') if self.store.get('knowledge_signature')==signature else None
            if brief:
                validate('session_brief',brief)
                public_guidance(brief,profile,self.store.get('persistent_feedback',[]))
            strategy=initial_plan(profile,markets,brief)
            plans={v['market_id']:v for v in strategy['markets']}
            if len(plans)!=len(strategy['markets']) or set(plans)!={m['id'] for m in markets}:raise ValueError('Research strategy must cover every selected market exactly once.')
            for m in markets:
                for q in plans[m['id']]['linkedin_queries']:
                    if not q['query'].strip() or q['query'].startswith('-') or not valid_query(q,m,scope_for(profile,m)):raise ValueError('Strategy query/location invalid or outside saved preferences; no source request sent.')
            phase('discovery')
            # Preserve immediate safe discovery before inference, without a country-wide barrier.
            linkedin.deadline=phase_end-45*len(markets)
            for m in markets[:1]:
                d['country']=m['country']
                if plans[m['id']]['linkedin_queries'] and available():direct(plans[m['id']]['linkedin_queries'][0],m)
            if not brief:
                brief=call('session_brief',
                    'Privately summarize demonstrated capabilities and the requested NEXT move for anonymous public vacancy research. '
                    'No tools. Exclude names, contacts, employers from career history, projects, identifying details and verbatim CV passages. '
                    'Preserve technical capability, honest leadership scope, transferable industries, target roles, salary/hours/flexibility preferences. '
                    'Never assume disciplinary management or deep software experience. Separate each country preference. '
                    'Employer search priorities come from explicit target-employer preferences separately.',
                    {'profile':private_profile(profile),'markets':all_markets})
                validate('session_brief',brief)
                public_guidance(brief,profile,self.store.get('persistent_feedback',[]))
                self.store.set('professional_background',brief)
                self.store.set('knowledge_signature',signature)
                previous_plans=plans
                strategy=initial_plan(profile,markets,brief)
                plans={v['market_id']:v for v in strategy['markets']}
                for m in markets[:1]:
                    # A profile without structured role intent gets its first
                    # transport seed only after private anonymization.
                    if not previous_plans[m['id']]['linkedin_queries'] and plans[m['id']]['linkedin_queries'] and available():
                        direct(plans[m['id']]['linkedin_queries'][0],m)
            guidance=None;guidance_market=None
            pending=list(markets);passes={m['id']:0 for m in markets};avenues={m['id']:[] for m in markets}
            while pending and time.monotonic()<deadline-1 and not provider_blocked and payload['usage']['ai_invocations']<call_limit:
                settle()
                round_spent={k:0.0 for k in PHASE_SECONDS}
                first_visits=sum(passes[m['id']]==0 for m in pending)
                share=max(1,first_visits)
                round_caps={k:max(0,d['phase_budgets'][k]-spent[k])/share for k in PHASE_SECONDS}
                phase('discovery')
                if not available():break
                m=pending.pop(0);d['country']=m['country'];plan=plans[m['id']];n=passes[m['id']];passes[m['id']]+=1
                reserved_discovery=sum(passes[v['id']]==0 for v in pending)
                visit_end=phase_end  # The cumulative ledger already reserves fair country shares.
                linkedin.deadline=visit_end-45  # Reserve indexed discovery for this market too.
                query_index=n if m!=markets[0] else n+1
                if guidance and guidance_market==m['id'] and guidance['next_queries']:
                    query={'query':guidance['next_queries'][0],'location':query_locations(m)[n%len(query_locations(m))],
                           'remote':'any','reason':'Anonymous AI direction from previous observed round'}
                    if valid_query(query,m,scope_for(profile,m)) and linkedin.deadline-time.monotonic()>1:direct(query,m)
                elif query_index<len(plan['linkedin_queries']) and linkedin.deadline-time.monotonic()>1:
                    direct(plan['linkedin_queries'][query_index],m)
                before=d['counts']['accepted'];previous_queries=set(queries);expand=False
                priorities=employers_for(m)
                employer_focus=priorities[n%len(priorities)] if priorities else ''
                try:
                    result=call('research_v5',RESEARCH,{'background':brief['background'],'career_direction':brief['direction'],'strategy':strategy['strategy'],'role_families':strategy['role_families'],
                        'market':{k:m[k] for k in ('id','country','locations','scope_type','remote','relocation') if k in m},'planned_queries':guidance['next_queries'] if guidance and guidance_market==m['id'] else plan['web_queries'],
                        'round_findings':guidance if guidance and guidance_market==m['id'] else {},'employer_focus':employer_focus,'country_preferences':[v for v in brief['country_preferences'] if v['country_id']==m['id']],
                        'priority_employers':(priorities[n:]+priorities[:n])[:8],
                        'previous_queries':sorted(queries),'known_postings':[{'id':j['id'],'url':j['url']} for j in self.store.jobs()],
                        'source_gaps':[{'id':j['id'],'url':j['url'],'description_sources':j.get('description_sources',[])}
                            for j in ranked_candidates([j for j in self.store.jobs()
                                if active(j) and j.get('shortlist_status')=='selected' and not verified_description(j)])][:8],
                        'next_avenues':avenues[m['id']],'restricted_publishers':self.store.access_restrictions(),'linkedin_access':linkedin_state(self.store),'linkedin_stop':self.store.get('linkedin_stop')},True,max(1,visit_end-time.monotonic()))
                    telemetry=ai.telemetry
                    if not telemetry.get('web_calls') or telemetry.get('research_unverified'):raise ProviderError('No genuine web-tool observations; model-only discoveries refused.','unverified_research')
                    indexed(result,telemetry)
                    payload['warnings'].extend(safe_text(v) for v in result['limitations'])
                    new_avenues=result['next_avenues'];new=d['counts']['accepted']-before
                    expand=result['continue_research'] and new_avenues and passes[m['id']]<max(2,required_visits[m['id']]) and new>0 and (queries!=previous_queries or new_avenues!=avenues[m['id']])
                    if expand:d.setdefault('deferred_discovery',[]).append(m['id'])
                    d['market_outcomes'][m['id']]={'indexed_passes':passes[m['id']],'new_jobs':new,'status':'verification_first' if expand else 'avenues_exhausted'}
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
                if priorities:
                    d.setdefault('employer_focus_requests',[]).append({'market_id':m['id'],'employer':safe_text(employer_focus),
                        'pass':passes[m['id']],'outcome':d['market_outcomes'][m['id']]['status']})
                # A bounded packet reaches validated durable assessment BEFORE
                # another discovery or another packet's triage is started.
                candidates=[j for j in self.store.jobs() if active(j) and processed.get(j['id'])!=evidence_version(j)]
                process_candidates(candidates)
                d.setdefault('rounds',[]).append({'market_id':m['id'],'pass':passes[m['id']],
                    'candidate_ids':[j['id'] for j in candidates],
                    'assessed_ids':[j['id'] for j in self.store.jobs() if j['id'] in {v['id'] for v in candidates} and review_state(j)['status']=='assessed']})
                if expand or passes[m['id']]<required_visits[m['id']]:pending.append(m)
                pending.sort(key=lambda v:passes[v['id']]>=required_visits[v['id']])
                guidance=None;guidance_market=None
                if pending and not provider_blocked and payload['usage']['ai_invocations']<call_limit-reserved_discovery:
                    phase('discovery')
                    if not available():continue  # Only this round's fair share expired.
                    target=pending[0]
                    try:
                        guidance=call('research_guidance',GUIDANCE,{
                            'profile':private_profile(market_profile(profile,target,self.store)),
                            'background':brief,'next_market':target,
                            'previous_market':m['id'],'previous_queries':sorted(queries),
                            'findings':[round_finding(j) for j in self.store.jobs() if j['id'] in {v['id'] for v in candidates}],
                            'failures':d.get('failures',[])[-5:]},allowance=20)
                        validate('research_guidance',guidance)
                        public_guidance(guidance,profile,self.store.get('persistent_feedback',[]))
                        guidance_market=target['id']
                        # Initial country coverage cannot be canceled by one
                        # productive employer or an AI continuation preference.
                        if not guidance['continue_research']:
                            pending=[v for v in pending if passes[v['id']]<required_visits[v['id']]]
                    except (ValueError,ProviderError) as exc:
                        guidance=None
                        category=getattr(exc,'category','validation_error')
                        d.setdefault('failures',[]).append({'phase':'discovery','country':target['country'],'reason':category,'stage':'Private round guidance'})
                        payload['warnings'].append('Next-round guidance incomplete; no retry. Initial country coverage retained.')
                        pending=[v for v in pending if passes[v['id']]<required_visits[v['id']]]
                        if category in ('execution_error','subscription_usage_limit','provider_rate_limit','model_access','invocation_budget','total_budget','canceled'):provider_blocked=True
            if pending:
                payload['warnings'].append('Research budget or provider limit reached; country/avenue coverage incomplete.')
                d.setdefault('phase_outcomes',{})['discovery']='partial'
            for m in markets:
                d['market_outcomes'].setdefault(m['id'],{'indexed_passes':0,'status':'not_reached'})
            d['unvisited_employer_focuses']={m['id']:employers_for(m)[passes[m['id']]:] for m in markets
                if passes[m['id']]<len(employers_for(m))}
            if not self.store.jobs() and d.get('failures'):
                raise ProviderError('Indexed discovery failed; no automatic retry.','discovery_failed')
            settle()
            states={}
            for job in self.store.jobs():
                state=review_state(job,d)
                if state['status']=='pending' and job['id'] in shortlisted and active(job) and not verified_description(job):
                    state={'status':'pending','reason':'full_source_required'}
                elif state['status']=='pending' and state['reason']=='not_started' and stop_reason and job['id'] in shortlisted and verified_description(job):
                    state={'status':'pending','reason':stop_reason}
                states[job['id']]=state
                self.store.upsert_job({'id':job['id'],'review_state':state})
            d['review_states']=states
            remaining=coverage(self.store.jobs(),d)
            incomplete=remaining['pending']+remaining['needs_verification']>0
            d.setdefault('phase_outcomes',{})['evaluation']='partial' if incomplete else 'finished'
            if incomplete:payload['warnings'].append('Assessment coverage incomplete; saved vacancies are retained with explicit review reasons.')
            else:d['completed_phases'].append('evaluation')
            for name in ('discovery','enrichment'):
                if d.get('phase_outcomes',{}).get(name)!='partial' and not any(f['phase']==name for f in d.get('failures',[])):
                    d['completed_phases'].append(name)
            if any(j['id'] in shortlisted and active(j) and not j.get('description') for j in self.store.jobs()):
                payload['warnings'].append('Some shortlisted vacancies lack a verified full description; final assessment awaits source verification.')
            if not shortlisted and self.store.jobs() and not d['triage']['failed'] and not d['triage']['pending']:
                payload['warnings'].append('No vacancies passed evidence-aware career triage; research findings remain available.')
            status='canceled' if cancel.is_set() else 'partial' if payload['warnings'] else 'completed'
            d['stop']={'phase':d['phase'],'reason':'canceled' if cancel.is_set() else stop_reason or ('completed_with_limitations' if payload['warnings'] else 'completed')}
        except SessionExpired:return
        except Exception as exc:
            category=getattr(exc,'category','validation_error')
            message=str(exc) if isinstance(exc,(ValueError,ProviderError)) else 'Research interrupted; saved findings retained.'
            payload['provider_error']={'category':category,'message':safe_text(message)}
            d['stop']={'phase':d['phase'],'country':d['country'],'reason':category,'stage':self.store.runs()[0]['stage']}
            status='canceled' if cancel.is_set() else 'partial' if self.store.jobs() else 'failed'
        try:
            payload['comparison']=compared_opportunities(self.store.jobs())
            payload['warnings']=list(dict.fromkeys(payload['warnings']));progress('Search '+status)
            self.store.update_run(run_id,'Search '+status,payload,status)
        except SessionExpired:pass

