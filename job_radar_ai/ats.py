"""Small, independent public employer-board adapters. No model-created records."""
import json
import re
from urllib.parse import urljoin,urlsplit,urlencode
from .sources import public_url,publisher_group,RetrievalError,TextParser,json_objects,plain,exact
from .geography import location_status
from .markets import country_of
from .store import now

PROVIDERS={'greenhouse':{'boards.greenhouse.io','job-boards.greenhouse.io'},'lever':{'jobs.lever.co','jobs.eu.lever.co'},
           'ashby':{'jobs.ashbyhq.com'},'smartrecruiters':{'careers.smartrecruiters.com'},'workable':{'apply.workable.com'}}
STATUS={p:'experimental' for p in PROVIDERS}
STATUS['smartrecruiters']='live_verified'


def board_identity(board):
    p=public_url(board['url']);parts=p.path.strip('/').split('/')
    if p.hostname not in PROVIDERS.get(board['provider'],set()) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',parts[0]) or len(parts)!=1 or p.query:
        raise RetrievalError('unverified','Use an exact published employer board root, not an invented endpoint.')
    return p.hostname,parts[0]


def ownership(board,fetcher):
    if not board.get('employer_url'):raise RetrievalError('unverified','Official employer ownership URL is required.')
    page=fetcher.get(board['employer_url']);parser=TextParser();parser.feed(page['text'])
    urls=[urljoin(page['url'],link).rstrip('/') for link in parser.links]
    root=board['url'].rstrip('/')
    if not any(url==root or url.startswith(root+'/') for url in urls):
        raise RetrievalError('unverified','Employer page does not link the exact published board.')
    names=set()
    for script in parser.scripts:
        try:
            for obj in json_objects(json.loads(script)):
                if obj.get('@type')=='Organization' and urlsplit(str(obj.get('url',''))).hostname==urlsplit(page['url']).hostname and isinstance(obj.get('name'),str):names.add(obj['name'])
        except (ValueError,TypeError,RecursionError):pass
    if len(names)!=1 or not next(iter(names)):
        raise RetrievalError('unverified','Independent employer ownership evidence is unavailable.')
    return next(iter(names))


def read_json(fetcher,url):
    page=fetcher.get(url,api=True)
    try:return json.loads(page['text']),page
    except (ValueError,TypeError) as exc:raise RetrievalError('incomplete','Public ATS did not return its documented JSON schema.') from exc


def normalized(provider,token,raw_id,title,company,location,url,page,description='',country='',requisition='',date='',remote=False,date_kind='published'):
    if isinstance(raw_id,bool) or not isinstance(raw_id,(str,int)) or not all(isinstance(v,str) and v.strip() for v in (str(raw_id),title,company,location,url)) or not re.fullmatch('[A-Za-z0-9_-]{1,200}',str(raw_id)):
        raise RetrievalError('unverified','ATS posting identity or required fields are incomplete.')
    public_url(url)
    if not isinstance(description,str):raise RetrievalError('incomplete','ATS description schema is invalid.')
    full=100<=len(description)<=60000
    return {'id':f'ats:{provider}:{token}:{raw_id}','source':provider,'integration':STATUS[provider],'source_id':str(raw_id),'title':title,'company':company,'location':location,
        'country':country,'requisition_id':str(requisition or ''),'published_at':date if date_kind=='published' else '', 'updated_at':date if date_kind=='updated' else '', 'url':url,'availability':'unknown',
        'workplace':'remote' if remote else 'unknown','remote_verified':remote is True,
        'description':description if full else '', 'description_status':'public_verified' if full else 'incomplete' if description else 'not_attempted',
        'description_source_url':url if full else '', 'description_source':{'kind':'public_verified','posting_url':url,**{k:page[k] for k in ('url','sha256','bytes','at')}},
        'source_observations':[{'provider':provider,'posting_id':str(raw_id),'url':url,**{k:page[k] for k in ('sha256','bytes','at')}}]}


class PublicBoards:
    def __init__(self,fetcher):self.fetcher=fetcher
    def listing(self,board):
        host,token=board_identity(board);provider=board['provider']
        if self.fetcher.store.get('public:stop:'+publisher_group(host)) or self.fetcher.store.get('public:stop:'+host):
            raise RetrievalError('blocked_shared_stop','Publisher already stopped; no new HTTP denial/request.')
        try:
            if provider=='greenhouse':
                meta,_=read_json(self.fetcher,f'https://boards-api.greenhouse.io/v1/boards/{token}')
                company=meta['name'];data,page=read_json(self.fetcher,f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs')
                jobs=[normalized(provider,token,j['id'],j['title'],company,j['location']['name'],j['absolute_url'],page,requisition=j.get('requisition_id',''),date=j.get('updated_at',''),date_kind='updated') for j in data['jobs'] if j.get('internal_job_id') is not None]
            elif provider=='lever':
                company=ownership(board,self.fetcher);api='api.eu.lever.co' if host=='jobs.eu.lever.co' else 'api.lever.co'
                data,page=read_json(self.fetcher,f'https://{api}/v0/postings/{token}?mode=json&limit=20&skip=0')
                if not isinstance(data,list):raise ValueError()
                jobs=[]
                for j in data:
                    text=j.get('descriptionPlain') or plain(j.get('description',''))
                    text+='\n'+'\n'.join(s['text']+'\n'+plain(s['content']) for s in j.get('lists',[]))+'\n'+(j.get('additionalPlain') or plain(j.get('additional','')))
                    jobs.append(normalized(provider,token,j['id'],j['text'],company,j['categories']['location'],j['hostedUrl'],page,text.strip(),requisition=j.get('requisitionId',''),remote=j.get('workplaceType')=='remote'))
            else:
                return self.other_listing(board,host,token)
            return jobs
        except (KeyError,TypeError,ValueError) as exc:
            raise RetrievalError('incomplete','ATS response does not match the documented provider schema; no invented records.') from exc

    def complete(self,job):
        try:
            return self._complete(job)
        except (KeyError,TypeError,ValueError) as exc:
            raise RetrievalError('incomplete','ATS detail schema is incomplete; observed record retained.') from exc

    def _complete(self,job):
        if job.get('description'):return job
        parts=job['id'].split(':');provider,token,identity=parts[1:]
        if provider=='smartrecruiters':
            data,page=read_json(self.fetcher,f'https://api.smartrecruiters.com/v1/companies/{token}/postings/{identity}')
            if str(data.get('id'))!=identity or exact(data.get('name'))!=exact(job['title']) or exact(data.get('company',{}).get('name'))!=exact(job['company']):
                raise RetrievalError('unverified','SmartRecruiters detail conflicts with the observed identity.')
            sections=data['jobAd']['sections']
            text='\n'.join(plain(s.get('title',''))+'\n'+plain(s['text']) for key,s in sections.items() if key in ('companyDescription','jobDescription','qualifications','additionalInformation') and isinstance(s,dict))
            url=data.get('postingUrl') or job['url']
            parsed=public_url(url)
            if data.get('postingUrl') and (parsed.hostname!='jobs.smartrecruiters.com' or not parsed.path.startswith('/'+token+'/'+identity+'-')):
                raise RetrievalError('unverified','Canonical SmartRecruiters URL conflicts with the exact posting identity.')
            loc=data['location']
            if str(loc.get('country','')).casefold()!=str(job.get('country','')).casefold() or exact(loc.get('city',''))!=exact(job['location'].split(',')[0]):
                raise RetrievalError('unverified','ATS detail location conflicts with observed location.')
            return {**job,**normalized(provider,token,identity,job['title'],job['company'],job['location'],url,page,text,country=job['country'],requisition=data.get('jobAdId',''),date=data.get('releasedDate',''),remote=loc.get('remote') is True)}
        if provider!='greenhouse':return job
        data,page=read_json(self.fetcher,f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{identity}')
        if str(data.get('id'))!=identity or exact(data.get('title'))!=exact(job['title']) or exact(data.get('company_name'))!=exact(job['company']) or exact(data.get('location',{}).get('name'))!=exact(job['location']):
            raise RetrievalError('unverified','ATS detail conflicts with the observed posting identity.')
        return normalized(provider,token,identity,data['title'],data['company_name'],data['location']['name'],job['url'],page,plain(data['content']),requisition=data.get('requisition_id',''),date=data.get('updated_at',''),date_kind='updated')

    def other_listing(self,board,host,token):
        provider=board['provider'];jobs=[]
        if provider=='ashby':
            company=ownership(board,self.fetcher)
            data,page=read_json(self.fetcher,f'https://api.ashbyhq.com/posting-api/job-board/{token}')
            for j in data['jobs']:
                if j.get('isListed') is not True:continue
                url=j['jobUrl'];parts=urlsplit(url).path.strip('/').split('/')
                if urlsplit(url).hostname!=host or len(parts)!=2 or parts[0]!=token:raise ValueError()
                address=j.get('address',{}).get('postalAddress',{})
                jobs.append(normalized(provider,token,parts[1],j['title'],company,j['location'],url,page,j.get('descriptionPlain') or plain(j.get('descriptionHtml','')),country=address.get('addressCountry',''),date=j.get('publishedAt',''),remote=j.get('isRemote') is True))
        elif provider=='smartrecruiters':
            params={'limit':20,'offset':0}
            if board.get('query'):params['q']=board['query']
            if board.get('country'):params['country']=board['country'].lower()
            if board.get('city'):params['city']=board['city']
            data,page=read_json(self.fetcher,f'https://api.smartrecruiters.com/v1/companies/{token}/postings?'+urlencode(params))
            for j in data['content']:
                if j['company']['identifier'].casefold()!=token.casefold():raise ValueError()
                loc=j['location'];location=', '.join(loc[k] for k in ('city','region','country') if loc.get(k))
                ref=j['ref'];public_url(ref)
                if ref!=f'https://api.smartrecruiters.com/v1/companies/{token}/postings/{j["id"]}':raise ValueError()
                url=j.get('postingUrl') or ref
                # The canonical posting URL is verified by the full detail response.
                card=normalized(provider,token,j['id'],j['name'],j['company']['name'],location,url,page,country=loc.get('country',''),requisition=j.get('jobAdId',''),date=j.get('releasedDate',''),remote=loc.get('remote') is True)
                card['public_detail_ref']=ref;jobs.append(card)
        elif provider=='workable':
            data,page=read_json(self.fetcher,f'https://www.workable.com/api/accounts/{token}?details=true')
            company=data.get('name') or ownership(board,self.fetcher)
            for j in data['jobs']:
                loc=j['location'];location=', '.join(loc[k] for k in ('city','region','country') if loc.get(k))
                text=plain(j.get('description',''))+'\n'+plain(j.get('requirements',''))+'\n'+plain(j.get('benefits',''))
                jobs.append(normalized(provider,token,j['shortcode'],j['title'],company,location,j['url'],page,text.strip(),country=loc.get('country_code') or loc.get('country',''),date=j.get('published_on',''),remote=loc.get('telecommuting') is True))
        else:raise RetrievalError('unverified','Provider adapter is not enabled.')
        return jobs


def sampled(jobs,profile,market,limit=20):
    rank={'preferred':0,'verified_remote':1,'secondary_conditional':2,'location_unknown':3,'outside_preferred':4}
    return sorted(jobs,key=lambda j:rank[location_status(j,profile,market)])[:limit]


def observe(store,job,run_id,market):
    """Merge only independently proven identical openings; raw source observations survive."""
    existing=store.jobs();same=next((j for j in existing if j['id']==job['id']),None)
    if not same:
        exact_matches=[]
        for prior in existing:
            canonical=job['url']==prior.get('url') or job['url']==prior.get('description_source_url')
            req=bool(job.get('requisition_id') and job['requisition_id']==prior.get('requisition_id'))
            country=country_of(job,[market])
            identity=exact(job['company'])==exact(prior.get('company','')) and exact(job['title'])==exact(prior.get('title','')) and exact(job['location'])==exact(prior.get('location','')) and country and country==country_of(prior,[market])
            if (canonical or req) and identity:exact_matches.append(prior)
        if len(exact_matches)==1:same=exact_matches[0]
        elif len(exact_matches)>1:
            job={**job,'identity_review_required':True,'possible_duplicate_ids':[j['id'] for j in exact_matches]}
    if same:
        observations=same.get('source_observations',[])
        observations += [o for o in job['source_observations'] if o not in observations]
        update={'id':same['id'],'source_observations':observations}
        if job.get('description') and not same.get('description'):
            update.update({k:job[k] for k in ('description','description_status','description_source','description_source_url')})
        store.upsert_job(update,run_id,market['id'])
        return next(j for j in store.jobs() if j['id']==same['id']),False
    new=store.upsert_job(job,run_id,market['id'])
    return job,new
