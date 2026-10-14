"""Targeted investigation of retained identities; no rediscovery or raw-CV web queries."""
import re,time,threading
from datetime import datetime,timezone
from urllib.parse import urlsplit,urljoin
from html.parser import HTMLParser
from .recovery import DescriptionResolver
from .sources import PublicFetcher,RetrievalError,retrieve_candidates,structured_jobs,match_identity,plain,exact,public_url
from .identity import normalized_url,linkedin_job_id
from .html_posting import JobMain
from .providers import Provider,ProviderError
from .markets import country_of,market_profile
from .location import geography
from .hunter import EVALUATION_TASK,prepare_evaluation,source_context
from .store import now
from .access import linkedin_state


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__();self.depth=0;self.capture=[];self.fields={};self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag not in ('br','img','input','meta','link','hr'):self.depth+=1
        if tag=='a':self.links.append((attrs.get('href',''),attrs.get('class','')))
        for key in set(attrs.get('class','').split()) & {'location','country','date'}:self.capture.append((key,self.depth,[]))
    def handle_endtag(self,tag):
        for key,depth,parts in list(self.capture):
            if depth==self.depth:
                self.fields.setdefault(key,[]).append(''.join(parts).strip());self.capture.remove((key,depth,parts))
        if tag not in ('br','img','input','meta','link','hr'):self.depth=max(0,self.depth-1)
    def handle_data(self,data):
        for _,_,parts in self.capture:parts.append(data)


def vacancy_html(job,page):
    parser=JobMain();parser.feed(page['text']);text=''.join(parser.parts).strip();title=''.join(parser.title).strip()
    if parser.count!=1 or not parser.canonical:
        raise RetrievalError('unverified','A unique job description region and published canonical URL are required.',stage='parsing')
    if normalized_url(urljoin(page['url'],parser.canonical))!=normalized_url(page['url']) or exact(title)!=exact(job['title']):
        raise RetrievalError('unverified','Published title or canonical URL conflicts with the retained vacancy.',stage='identity')
    if not job.get('company') or not re.search(r'(?<!\w)'+re.escape(job['company'])+r'(?!\w)',plain(page['text']),re.I):
        raise RetrievalError('unverified','Employer is not established in the actual publisher page.')
    requisition=job.get('requisition_id','')
    if requisition and not re.search(r'(?<!\w)'+re.escape(requisition)+r'(?!\w)',plain(page['text']),re.I):
        raise RetrievalError('unverified','Known requisition is not stated by the publisher page.')
    if not 100<=len(text)<=60000:raise RetrievalError('incomplete','Full job text is outside supported size bounds.')
    metadata=Metadata();metadata.feed(page['text'])
    location=next(iter(metadata.fields.get('location',[])),'').strip(', ')
    country=next(iter(metadata.fields.get('country',[])),'')
    if job.get('location') and location and exact(job['location'].split(',')[0])!=exact(location.split(',')[0]):
        raise RetrievalError('unverified','Original vacancy locality conflicts with publisher job location.')
    apply_urls=[]
    for href,_ in metadata.links:
        link=urljoin(page['url'],href);parsed=urlsplit(link)
        if '/apply' in parsed.path and parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:apply_urls.append(link)
    return {'title':title,'company':job['company'],'location':', '.join(filter(None,[location or job.get('location',''),country])),'country':country,'description':text,'source_url':page['url'],'requisition_id':job.get('requisition_id',''),'evidence':page,'date_text':'; '.join(metadata.fields.get('date',[])),'apply_urls':apply_urls}


def freshness(posting):
    result={'status':'unknown','checked_at':posting.get('evidence',{}).get('at') or now(),'published_at':posting.get('date_posted') or None,'source_url':posting['source_url'],'evidence':''}
    through=posting.get('valid_through')
    if through:
        try:
            expiry=datetime.fromisoformat(through.replace('Z','+00:00'))
            if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
            result.update(status='confirmed_closed' if expiry<datetime.now(timezone.utc) else 'confirmed_open' if posting.get('apply_urls') else 'unknown',evidence='Publisher validThrough: '+through)
        except ValueError:pass
    # An actual publisher closing date plus job-specific application URL is
    # evidence; generic links, crawl dates and first_seen are never availability.
    match=re.search(r'Closing date:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})',posting.get('date_text',''))
    if match:
        try:
            expiry=datetime.strptime(' '.join(match.groups()),'%d %B %Y').replace(tzinfo=timezone.utc)
            result.update(status='confirmed_closed' if expiry<datetime.now(timezone.utc) else 'confirmed_open' if posting.get('apply_urls') else 'unknown',evidence=match.group(0))
        except ValueError:pass
    return result


def recover(job,url,employer_url,fetcher,markets):
    options=retrieve_candidates(url,fetcher,employer_url)
    if not options:
        page=fetcher.get(url)
        return recover_page(job,page,markets)
    return matched_posting(job,url,options,markets)


def recover_page(job,page,markets):
    """Parse already observed publisher bytes through the normal identity gate."""
    identity=linkedin_job_id(page['url'])
    if identity:
        if identity!=linkedin_job_id(job['url']):
            raise RetrievalError('unverified','Recorded page belongs to another LinkedIn listing identity.',stage='identity')
    else:public_url(page['url'])
    if not urlsplit(page['url']).path.strip('/'):
        raise RetrievalError('unverified','A homepage is not an exact vacancy publication.',stage='source_selection')
    options=structured_jobs(page) or [vacancy_html(job,page)]
    return matched_posting(job,page['url'],options,markets)


def matched_posting(job,url,options,markets):
    # Original observed employer/publication URL has a stable identity.
    # Alternative sites must state the same locality/title/employer too.
    matches=[];failures=[]
    for option in options:
        try:
            if normalized_url(url)==normalized_url(job['url']) and len(options)==1:
                if job.get('requisition_id') and exact(job['requisition_id'])!=exact(option.get('requisition_id','')):
                    raise RetrievalError('unverified','Original or redirected posting requisition conflicts with retained identity.')
                if job.get('title') and exact(job['title'])!=exact(option['title']):raise RetrievalError('unverified','Original posting title changed.')
                if job.get('company') and exact(job['company'])!=exact(option['company']):
                    actual=plain(option['evidence']['text'])
                    if exact(job['company']) not in exact(actual):raise RetrievalError('unverified','Original publisher does not corroborate the observed employer brand.')
                    option['observed_company']=job['company']
                    option['identity_note']='Same original vacancy URL and exact title; publisher states both observed employer brand and structured hiring organization.'
                if not 100<=len(option.get('description',''))<=60000:raise RetrievalError('incomplete','Full description missing.')
                matches.append(option)
            else:
                inferred=geography(job,markets)
                supported={**job}
                if not country_of(job,markets) and inferred['status']=='inferred':supported['country']=inferred['country_id']
                matches.append(match_identity(supported,option,markets))
        except RetrievalError as exc:failures.append(exc)
    if len(matches)!=1:
        cause=failures[0] if not matches and failures else None
        raise RetrievalError('unverified','No unique exact vacancy match; original observation retained.'+
            (' '+str(cause) if cause else ''),stage=cause.stage if cause else 'identity') from cause
    return matches[0]


class CompletionResolver(DescriptionResolver):
    def execute(self,run_id,jobs,cancel,supplied=None,selection=None):
        try:return self._execute(run_id,jobs,cancel,supplied,selection)
        except Exception as exc:
            reason=str(exc) if isinstance(exc,(ValueError,ProviderError,RetrievalError)) else 'Targeted investigation failed; existing vacancies and user data retained.'
            self.store.update_run(run_id,reason,{'warnings':[reason],'provider_errors':[{'category':getattr(exc,'category','execution_error'),'message':reason}]},'canceled' if cancel.is_set() else 'partial')

    def _execute(self,run_id,jobs,cancel,supplied=None,selection=None):
        if supplied is not None or selection is not None:return super().execute(run_id,jobs,cancel,supplied,selection)
        profile=self.store.get('profile');markets=profile['markets'];deadline=time.monotonic()+900
        fetcher=self.fetcher or PublicFetcher(self.store,cancel,budget=float('inf'),deadline=deadline)
        ai=self.ai or Provider(profile['provider'],self.root/'.private/v5/ai')
        payload={'kind':'description_recovery','job_ids':[j['id'] for j in jobs],'metrics':{'attempted':0,'recovered':0,'evaluated':0,'blocked':0,'unavailable':0,'remaining':len(jobs)},'sources':[],'outcomes':[],'warnings':[],'provider_errors':[],'new_jobs':0}
        provider_blocked=False
        for job in sorted(jobs,key=lambda j:not j.get('preliminary',{}).get('promising')):
            if cancel.is_set() or time.monotonic()>=deadline:break
            payload['metrics']['attempted']+=1
            self.store.update_run(run_id,'Investigating retained opportunity: '+job['title'],payload)
            full=None;attempts=[]
            links=job.get('description_sources',[])
            if not job['id'].startswith('linkedin:') and '/posts/' not in job['url']:links=[{'url':job['url'],'employer_url':''}]+links
            if not links and not provider_blocked:
                try:
                    result=ai.run('resolve','Investigate this exact retained vacancy using supported public web search AND page opening, not snippets alone. Return sources.url as a job-specific original employer/public publication with full description; employer_url is ownership evidence. A LinkedIn discovery URL alone is not a controlled description source. Match title/employer/locality/requisition. Direct LinkedIn page opening is not permitted under an active LinkedIn restriction. Never use denied publishers or equivalent alternate routes. Do not claim same-company different-title postings are equivalent. Preserve original LinkedIn identity. No CV or private career context in public queries.',{'job':source_context(job),'restricted_publishers':self.store.access_restrictions(),'linkedin_direct':linkedin_state(self.store)},research=True,cancel=cancel,timeout=min(240,max(1,deadline-time.monotonic())))
                    links=result['sources']
                    self.store.upsert_job({'id':job['id'],'description_sources':links})
                    payload['sources'].append({'source':'Codex job-specific page investigation','job_id':job['id'],'status':'observed' if ai.telemetry.get('web_calls') else 'unverified','actions':ai.telemetry.get('actions',[])})
                except ProviderError as exc:
                    provider_blocked=True;payload['provider_errors'].append({'category':exc.category,'message':str(exc)})
            for link in links:
                if cancel.is_set() or time.monotonic()>=deadline:break
                try:
                    url=link['url'];employer_url=link['employer_url']
                    host=urlsplit(url).hostname or ''
                    employer=urlsplit(employer_url)
                    # Some providers put the located employer posting in the
                    # ownership field. Investigate that independent publication;
                    # it still must pass exact source identity validation.
                    if (host=='linkedin.com' or host.endswith('.linkedin.com')) and employer.hostname and not employer.hostname.endswith('linkedin.com') and len(employer.path.strip('/').split('/'))>=2:
                        url=employer_url
                    full=recover(job,url,employer_url,fetcher,markets);break
                except RetrievalError as exc:attempts.append({'source':link['url'],'status':exc.status,'http_status':exc.http_status,'reason':str(exc)})
            if full:
                evidence={'kind':'public_verified','url':full['source_url'],'at':now(),'sha256':full['evidence']['sha256'],'identity':'Exact retained vacancy identity validated against actual publisher text'}
                self.save_description(job,full['description'],evidence,run_id)
                state=freshness(full)
                self.store.upsert_job({'id':job['id'],'title':full['title'],'company':full['company'],'observed_company':full.get('observed_company',job.get('company')),'identity_note':full.get('identity_note',''),'location':full['location'],'country':full.get('country') or '', 'freshness':state,'availability':'closed_banner_observed' if state['status']=='confirmed_closed' else 'open_publisher_observed' if state['status']=='confirmed_open' else 'unknown','description_attempts':attempts,'evaluation_status':'full_description_pending_assessment'})
                payload['metrics']['recovered']+=1
                geo=geography(full,markets);country=geo['country_id'];market=next((m for m in markets if m['id']==country),None)
                if market and not provider_blocked:
                    try:
                        stored=next(j for j in self.store.jobs() if j['id']==job['id']);scoped=market_profile(profile,market,self.store)
                        result=ai.run('evaluation',EVALUATION_TASK+' The full original career text is authoritative. Availability and location uncertainty must remain explicit.',{'profile':scoped,'jobs':[source_context(stored)],'feedback':self.store.feedback(country) if geo['status']=='verified' else []},cancel=cancel,timeout=min(240,max(1,deadline-time.monotonic())))
                        if len(result['evaluations'])!=1:raise ValueError('One exact vacancy assessment required.')
                        self.store.evaluate(job['id'],prepare_evaluation(result['evaluations'][0],stored,scoped),country)
                        self.store.upsert_job({'id':job['id'],'evaluation_status':'fully_evaluated'});payload['metrics']['evaluated']+=1
                    except ProviderError as exc:
                        provider_blocked=True;payload['provider_errors'].append({'category':exc.category,'message':str(exc)})
                    except ValueError as exc:payload['warnings'].append(str(exc))
            elif not provider_blocked:payload['metrics']['unavailable']+=1
            payload['sources'].extend(attempts)
            payload['metrics']['blocked']+=int(not full and any(a['status'] in ('blocked','blocked_shared_stop') for a in attempts))
            if attempts and not full:self.store.upsert_job({'id':job['id'],'description_attempts':attempts,'description_status':attempts[-1]['status'],'description_checked':now()})
            payload['outcomes'].append({'job_id':job['id'],'country_id':geography(job,markets)['country_id'],'available':bool(full),'recovered':bool(full),'evaluated':bool(full and next(j for j in self.store.jobs() if j['id']==job['id'])['market_evaluations']),'status':'public_verified' if full else attempts[-1]['status'] if attempts else 'provider_deferred' if provider_blocked else 'not_found'})
            self.store.update_run(run_id,'Targeted investigation retained',payload)
        payload['metrics']['remaining']=sum(not j.get('description') for j in self.store.jobs() if j['id'] in payload['job_ids'])
        payload.update(descriptions=payload['metrics']['recovered'],evaluated=payload['metrics']['evaluated'],requests=fetcher.requests,cache_hits=fetcher.cache_hits)
        payload['warnings'].extend(e['message'] for e in payload['provider_errors'])
        if time.monotonic()>=deadline:payload['warnings'].append('Research time window expired; pending descriptions retained.')
        status='canceled' if cancel.is_set() else 'partial' if payload['metrics']['remaining'] or payload['warnings'] else 'completed'
        self.store.update_run(run_id,'Targeted investigation '+status,payload,status)
