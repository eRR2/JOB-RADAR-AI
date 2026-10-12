"""V5 AI-led web research. Tool observations, not model prose, establish facts."""
import hashlib
import re
import time
from urllib.parse import urlsplit
from .hunter import Hunter, EVALUATION_TASK, prepare_evaluation, source_context, profile_signature
from .providers import Provider, ProviderError
from .markets import market_profile, country_of
from .sources import PublicFetcher, verified_matches, RetrievalError
from .access import linkedin_state
from .store import now
from .linkedin import LinkedIn, SourceError

TASK = '''You are the career researcher, not a fixed scraping plan. Use real web_search now.
Prioritize indexed LinkedIn vacancy URLs, with relevant employer careers and other public vacancy sources.
CV establishes background; confirmed intention establishes the desired NEXT move. Investigate credible progression,
transferable industries and promising stretch opportunities, not simply familiar titles. No universal employers or profession.
Research ONLY this market and its confirmed locations/remote exceptions. Never silently broaden a city to a country.
Search diverse useful role families and refine queries intelligently. Named employers are priorities only when requested.
Work in a meaningful research batch, then say whether further exploration is worthwhile and which avenues remain.
The 20-entry response envelope is a batch size, NOT a total discovery quota: continue with further batches when useful.
Use cached/supplied observations to avoid repeat work. No tools except web_search. No direct LinkedIn page opens.
Never open a restricted publisher, bypass robots/authentication or retry denied sources. Search indexed material instead.
Do not include personal names, CV passages, contacts or identifying career history in public queries.
Every returned job URL must have been actually observed by tools. Title/company/location/country must be copied from
available tool evidence, not guessed. Use empty strings for unknown fields. country_quote must be a verbatim source passage
containing the stated country; a search's market or an ambiguous city is not country evidence.
Find independent description_sources only when they are credible publications of the SAME vacancy; do not invent text.
Do not claim full descriptions, salaries, employer facts or availability from snippets. Report limitations honestly.'''


def observed_job(candidate, observations):
    url=candidate['url']
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):return None
    except ValueError:return None
    sources=[o for o in observations if o.get('url')==url]
    if not sources:return None
    # Keep the original tool text. Model-written evidence/descriptions never enter it.
    text='\n'.join(dict.fromkeys(str(o.get(k,'')) for o in sources for k in ('title','snippet','text','content') if o.get(k)))
    if not text.strip():return None
    def corroborated(value):return value if value.strip() and value.casefold() in text.casefold() else ''
    country=corroborated(candidate['country']) if candidate['country'].strip() and candidate['country_quote'].strip() and candidate['country_quote'] in text and re.search(r'(?<!\w)'+re.escape(candidate['country'])+r'(?!\w)',candidate['country_quote'],re.I) and (not candidate['location'].strip() or candidate['location'].casefold() in candidate['country_quote'].casefold()) else ''
    match=re.search(r'/jobs/view/(?:[^/]*-)?(\d{6,15})(?:/|$)',parsed.path) if parsed.hostname=='linkedin.com' or parsed.hostname.endswith('.linkedin.com') else None
    identity='linkedin:'+match[1] if match else 'web:'+hashlib.sha256(url.encode()).hexdigest()[:24]
    return {'id':identity,'source_id':match[1] if match else identity,'source':'LinkedIn indexed web' if match else 'Public web research',
            'url':url,'title':corroborated(candidate['title']) or sources[0].get('title','Observed opportunity'),
            'company':corroborated(candidate['company']), 'location':corroborated(candidate['location']), 'country':country,
            'country_evidence':candidate['country_quote'] if country else '', 'availability':'unknown',
            'evidence':'Observed by Codex web tool; indexed evidence does not prove vacancy openness.',
            'source_observations':[{'url':url,'text':text,'kind':'web_tool_observation','at':now()}],
            'description_status':'not_attempted','evaluation_status':'preliminary_pending'}


class ResearchHunter(Hunter):
    def execute(self, run_id, cancel, ai=None, source=None, market_id='all', duration=900, fetcher=None):
        profile=self.store.get('profile')
        markets=[m for m in profile['markets'] if market_id=='all' or m['id']==market_id]
        ai=ai or Provider(profile['provider'],self.root/'.private/v5/ai')
        deadline=time.monotonic()+duration
        # Bytes, subprocess time, publisher rules and total run time are bounds.
        # There is no division of a small request/job quota between countries.
        fetcher=fetcher or PublicFetcher(self.store,cancel,budget=float('inf'))
        fetcher.deadline=deadline
        self.public_fetcher=fetcher
        linkedin=source or LinkedIn(self.root,self.store,cancel,{'requests':float('inf'),'spacing':5})
        pending=list(markets)
        learned_markets=set()
        outcomes={m['id']:{'job_ids':[],'new_jobs':0,'previously_seen':0,'descriptions':0,'available_descriptions':0,'evaluated':0,'promising':0,'sources':[],'warnings':[],'batches':0,'duplicates':0,'status':'not_started','next_avenues':self.store.get('research_next:'+m['id'],[])} for m in markets}
        payload={'markets':outcomes,'warnings':[],'sources':[],'job_ids':[],'web_calls':0,'linkedin_requests':0,'kind':'v5_research','linkedin_direct':linkedin_state(self.store)}
        def progress(stage):
            payload.update(job_ids=list(dict.fromkeys(j for o in outcomes.values() for j in o['job_ids'])),public_requests=fetcher.requests,linkedin_requests=linkedin.requests,requests=fetcher.requests+linkedin.requests,cache_hits=fetcher.cache_hits+linkedin.cache_hits,linkedin_direct=linkedin_state(self.store))
            self.store.update_run(run_id,stage,payload)
        def call(kind,task,data,research=False):
            if cancel.is_set():raise ProviderError('Canceled by user.')
            remaining=deadline-time.monotonic()
            if remaining<1:raise ProviderError('Research time window reached; retained opportunities can be investigated in the next run.')
            return ai.run(kind,task,data,cancel=cancel,research=research,timeout=min(240,remaining))
        try:
            if not profile.get('secondary'):raise ValueError('Enable public AI web research in Privacy & connection before searching.')
            progress('AI preparing an anonymous professional research brief')
            brief=call('brief_v5','Prepare an anonymous public-research brief from CV and confirmed intent. Include profession, demonstrated skills, seniority, credible transferable strengths and the desired NEXT career step. No person names, contact information, previous employer names, dates, distinctive project history or copied CV passages. Requested target employers may remain in career direction. Do not search or use any tools.',{'cv_text':profile.get('cv_text',''),'intent':profile.get('intent'), 'direction':profile.get('looking_for','')})
            while pending and time.monotonic()<deadline and not cancel.is_set():
                market=pending.pop(0);outcome=outcomes[market['id']];outcome['status']='running'
                scoped=market_profile(profile,market,self.store)
                if market['id'] not in learned_markets:
                    feedback=self.store.feedback(market['id'])
                    if feedback and not self.store.get('learning_paused',False):
                        learned=call('learning','Interpret ONLY this market explicit vacancy feedback into cautious anonymous research preferences. Cite feedback IDs; one dislike is tentative. No personal identifiers or copied user notes. Never learn from employer rejection or application outcomes. Never broaden one country preference to another.',{'feedback':feedback,'market':market})
                        known={f['id'] for f in feedback}
                        for item in learned['preferences']:
                            if not item['feedback_ids'] or not set(item['feedback_ids'])<=known:raise ValueError('Learning referenced unknown feedback.')
                            jobs_behind_feedback={f['job_id'] for f in feedback if f['id'] in item['feedback_ids']}
                            if len(jobs_behind_feedback)<2 and item['confidence']=='repeated':item['confidence']='tentative'
                        self.store.set('learned:'+market['id'],learned['preferences'])
                    learned_markets.add(market['id'])
                existing=[source_context(j) for j in self.store.jobs() if country_of(j,profile['markets'])==market['id']]
                restrictions=self.store.access_restrictions()
                progress('AI researching '+market['country']+' · batch '+str(outcome['batches']+1))
                public_profile={'background':brief,'market':market,'intention':{k:scoped.get('intent',{}).get(k) for k in ('preferences','markets')}}
                # Original CV, quotes and verbatim user text never enter a web-enabled call.
                public_profile['intention']['preferences']=[{k:p[k] for k in ('topic','value','origin','hard')} for p in scoped.get('intent',{}).get('preferences',[])]
                public_profile['intention']['markets']=[{k:v for k,v in m.items() if k!='quote'} for m in scoped.get('intent',{}).get('markets',[])]
                result=call('research_v5',TASK,{'profile':public_profile,'country_specific_learning':self.store.get('learned:'+market['id'],[]),'already_observed':existing,'next_avenues':outcome['next_avenues'],'restricted_publishers':restrictions},True)
                telemetry=ai.telemetry
                if not telemetry.get('web_calls') or telemetry.get('research_unverified'):
                    raise ProviderError('Real web-tool observations unavailable; no model-asserted discoveries imported. Use an authenticated Codex CLI with web research enabled.')
                payload['web_calls']+=telemetry['web_calls'];outcome['batches']+=1
                outcome['sources'].append({'source':'Codex public web research','status':'observed','count':len(telemetry.get('observations',[])),'actions':telemetry.get('actions',[]),'observed_urls':telemetry.get('observed_urls',[])})
                outcome['warnings'].extend(result['limitations']);outcome['report']=result['summary'];outcome['next_avenues']=result['next_avenues']
                self.store.set('research_next:'+market['id'],result['next_avenues'] if result['continue_research'] else [])
                batch=[]
                for candidate in result['jobs']:
                    job=observed_job(candidate,telemetry.get('observations',[]))
                    if not job:
                        outcome['warnings'].append('Unobserved model-proposed vacancy refused.');continue
                    country=country_of(job,profile['markets'])
                    # A discovered country is evidence; the query country is not.
                    membership=country
                    previous=next((j for j in self.store.jobs() if j['id']==job['id']),None)
                    if previous:
                        job['source_observations']=previous.get('source_observations',[])+job['source_observations']
                        for key in ('company','location','country','country_evidence'):
                            if not job[key]:job.pop(key)
                        if previous.get('description'):
                            job.pop('description_status');job.pop('evaluation_status')
                    is_new=self.store.upsert_job(job,run_id,membership)
                    outcome['new_jobs']+=int(is_new);outcome['previously_seen']+=int(not is_new)
                    if job['id'] in outcome['job_ids']:outcome['duplicates']+=1
                    else:outcome['job_ids'].append(job['id'])
                    stored=next(j for j in self.store.jobs() if j['id']==job['id'])
                    batch.append((stored,candidate))
                progress('Observed vacancies saved; AI checking career direction in '+market['country'])
                eligible=[j for j,_ in batch if not country_of(j,profile['markets']) or country_of(j,profile['markets'])==market['id']]
                if eligible:
                    preliminary=call('preliminary_v5','Assess the supplied observed title/snippet ONLY, against confirmed NEXT career direction and this country feedback. Distinguish direct, transferable, stretch and unrelated. Explain surprising opportunities and gaps. No full ATS/HR assessment, invented source facts or recommendation based on missing descriptions. Unknown geography remains unverified. Employer rejections never teach preferences.',{'profile':scoped,'feedback':self.store.feedback(market['id']),'jobs':[{**source_context(j),'source_observations':j['source_observations']} for j in eligible]})
                    known={j['id'] for j in eligible}
                    if len({a['job_id'] for a in preliminary['assessments']})!=len(preliminary['assessments']) or any(a['job_id'] not in known for a in preliminary['assessments']):raise ValueError('Preliminary assessment referenced an unknown or duplicate vacancy identity.')
                    for item in preliminary['assessments']:
                        job=next(j for j in eligible if j['id']==item['job_id'])
                        # Unknown country stays unscoped; no cross-country learning.
                        preliminary_country=country_of(job,profile['markets'])
                        self.store.upsert_job({'id':job['id'],'preliminary':{**item,'market_id':preliminary_country,'at':now()},'evaluation_status':'preliminary'})
                        outcome['promising']+=int(item['promising'])
                for job,candidate in batch:
                    if time.monotonic()>=deadline or cancel.is_set():break
                    stored=next(j for j in self.store.jobs() if j['id']==job['id'])
                    if not stored.get('description') and stored['id'].startswith('linkedin:') and stored.get('preliminary',{}).get('promising') and profile.get('linkedin_consent') and linkedin_state(self.store)['state']=='available' and not linkedin.denied_in_run:
                        try:
                            detail=linkedin.detail(stored['source_id'])
                            if any(str(detail.get(k,'')).casefold()!=str(stored.get(k,'')).casefold() for k in ('company','title')):
                                raise SourceError('Exact LinkedIn description employer/title identity could not be verified.')
                            self.store.upsert_job({'id':stored['id'],'description':detail['description'],'description_obtained':now(),'description_status':'available','description_source_url':detail['url'],'description_source':{'kind':'linkedin','url':detail['url'],'at':now(),'identity':'Same verified numeric LinkedIn job identity and exact employer/title'},'location':detail.get('location') or stored.get('location'),'country':detail.get('country') or stored.get('country',''),'availability':detail['availability']})
                            outcome['descriptions']+=1
                            outcome['sources'].append({'source':'LinkedIn direct description','url':detail['url'],'status':'success','job_id':stored['id'],'count':1})
                            stored=next(j for j in self.store.jobs() if j['id']==job['id'])
                        except SourceError as exc:
                            outcome['sources'].append({'source':'LinkedIn direct description','status':linkedin_state(self.store)['state'],'reason':str(exc),'job_id':stored['id']})
                            outcome['warnings'].append('Direct LinkedIn description unavailable; indexed evidence retained.')
                    if country_of(stored,profile['markets'])!=market['id']:continue
                    if not stored.get('description') and stored.get('preliminary',{}).get('promising'):
                        for publication in candidate['description_sources']:
                            if time.monotonic()>=deadline or cancel.is_set():break
                            try:
                                matches=verified_matches(stored,publication['url'],fetcher,publication['employer_url'],profile['markets'])
                                if len(matches)!=1:continue
                                full=matches[0]
                                self.store.upsert_job({'id':stored['id'],'description':full['description'],'description_obtained':now(),'description_status':'available','description_source_url':full['source_url'],'description_source':{'kind':'public_verified','url':full['source_url'],'at':now(),'sha256':full['evidence']['sha256']}})
                                outcome['descriptions']+=1;break
                            except RetrievalError as exc:
                                outcome['warnings'].append('Description investigation: '+exc.status)
                    stored=next(j for j in self.store.jobs() if j['id']==job['id'])
                    if stored.get('description'):
                        outcome['available_descriptions']+=1
                        prior_assessment=stored['market_evaluations'].get(market['id'])
                        if prior_assessment and not prior_assessment['content_stale'] and prior_assessment['evaluation'].get('profile_signature')==profile_signature(scoped):continue
                        progress('AI evaluating verified full description · '+market['country'])
                        evaluation=call('evaluation',EVALUATION_TASK,{'profile':scoped,'feedback':self.store.feedback(market['id']),'jobs':[source_context(stored)]})
                        try:
                            if len(evaluation['evaluations'])!=1:raise ValueError('Expected one exact vacancy evaluation.')
                            self.store.evaluate(stored['id'],prepare_evaluation(evaluation['evaluations'][0],stored,scoped),market['id'])
                        except ValueError as exc:
                            outcome['warnings'].append('Full assessment refused: '+str(exc));continue
                        self.store.upsert_job({'id':stored['id'],'evaluation_status':'fully_evaluated'})
                        outcome['evaluated']+=1
                outcome['status']='partial' if result['continue_research'] else 'completed'
                if result['continue_research']:pending.append(market)
                progress('Research batch retained · '+market['country'])
            status='canceled' if cancel.is_set() else 'partial' if pending or any(o['warnings'] for o in outcomes.values()) else 'completed'
            if pending:payload['warnings'].append('Research incomplete; further avenues retained. Run again to continue with cached observations.')
        except Exception as exc:
            payload['warnings'].append(str(exc) if isinstance(exc,(ValueError,ProviderError)) else 'Research failed; observed vacancies retained.')
            status='canceled' if cancel.is_set() else 'partial' if payload['job_ids'] else 'failed'
        stored_jobs={j['id']:j for j in self.store.jobs()}
        for o in outcomes.values():
            if o['status'] in ('running','not_started'):o['status']='partial' if o['job_ids'] else 'failed'
            o['discovered']=len(o['job_ids']);o['warnings']=list(dict.fromkeys(o['warnings']))
            o['available_descriptions']=sum(bool(stored_jobs[j].get('description')) for j in o['job_ids'])
            o['promising']=sum(bool(stored_jobs[j].get('preliminary',{}).get('promising')) and not stored_jobs[j].get('description') for j in o['job_ids'])
        payload['sources']=[{**s,'market_id':m} for m,o in outcomes.items() for s in o['sources']]+[{'source':d['endpoint'],**d} for d in fetcher.diagnostics]
        for key in ('new_jobs','previously_seen','descriptions','available_descriptions','evaluated','duplicates','promising'):payload[key]=sum(o[key] for o in outcomes.values())
        progress('Research finished · opportunities and remaining evidence retained')
        payload['discovered']=len(payload['job_ids']);payload['report']='AI web research completed in batches. Indexed vacancies remain preliminary until a real full description and evidence-based review are available.'
        payload['available_descriptions']=sum(bool(stored_jobs[j].get('description')) for j in payload['job_ids'])
        self.store.update_run(run_id,'Research '+status,payload,status)
