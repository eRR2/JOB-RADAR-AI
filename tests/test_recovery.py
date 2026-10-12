"""Offline source fixtures and existing-identity recovery regression."""
import hashlib
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.sources import (PublicFetcher, RetrievalError, public_url, public_addresses,
                                  structured_jobs, retrieve_candidates, match_identity, request_public)
from job_radar_ai.recovery import DescriptionResolver, description_state
from job_radar_ai.store import Store
from job_radar_ai.hunter import Hunter
from job_radar_ai.markets import defaults
from test_hunter import assessment

TEXT = 'Lead systems team. ' + 'Synthetic source responsibility and qualification evidence. ' * 5
URL = 'https://employer.example/careers/REQ-42'


def page(text, url=URL):
    return {'text': text, 'url': url, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'bytes': len(text.encode()), 'at': '2026-01-01T00:00:00+00:00'}


def posting(company='Synthetic Employer', title='Systems Lead', city='Berlin', country='Germany', req='REQ-42'):
    return {'@type': 'JobPosting', 'title': title, 'hiringOrganization': {'name': company}, 'description': '<p>' + TEXT + '</p>',
            'identifier': {'value': req}, 'jobLocation': {'address': {'addressLocality': city, 'addressCountry': country}}}


class FixtureFetcher:
    def __init__(self, store, pages):
        self.store, self.pages = store, pages
        self.requests = self.cache_hits = 0

    def get(self, url, **kwargs):
        self.requests += 1
        if url not in self.pages:
            raise AssertionError('Unexpected fixture URL')
        result = self.pages[url]
        if isinstance(result, Exception):
            raise result
        return result


class FixtureAI:
    def __init__(self, links=None):
        self.calls = []
        self.links = links or [{'url': URL, 'employer_url': ''}]

    def run(self, kind, task, context, **kwargs):
        self.calls.append((kind, context))
        if kind == 'resolve':
            return {'sources': self.links, 'limitations': []}
        return {'evaluations': [assessment(context['jobs'][0]['id'])], 'report': 'Synthetic verified evaluation'}


class NoDetail:
    requests = cache_hits = 0
    def detail(self, _):
        raise RetrievalError('budget_deferred', 'Detail not attempted: budget')


class RecoveryTests(unittest.TestCase):
    def test_one_actual_linkedin_denial_is_separate_from_later_shared_stop_skips(self):
        from job_radar_ai.linkedin import SourceError
        class Denied:
            requests=cache_hits=0
            def detail(source,_):
                source.requests+=1
                self.store.set('linkedin_stop','HTTP 429 access_restricted')
                raise SourceError('HTTP 429 access_restricted')
        second={**self.job,'id':'linkedin:654321','source_id':'654321','url':'https://www.linkedin.com/jobs/view/654321'}
        self.store.upsert_job(second)
        profile=self.store.get('profile');profile['secondary']=False;self.store.set('profile',profile)
        run=self.store.start_run('codex')
        source=Denied()
        DescriptionResolver(Hunter(self.root,self.store),FixtureAI(),source,FixtureFetcher(self.store,{})).execute(run,self.store.jobs(),threading.Event())
        payload=self.store.runs()[0]['payload']
        self.assertEqual(source.requests,1);self.assertEqual(payload['http_denials'],1)
        self.assertEqual(payload['shared_stop_skips'],1)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = Store(self.root / 'state.sqlite3')
        self.job = {'id': 'linkedin:123456', 'source_id': '123456', 'url': 'https://www.linkedin.com/jobs/view/123456',
                    'title': 'Systems Lead', 'company': 'Synthetic Employer', 'location': 'Berlin, Germany', 'requisition_id': 'REQ-42'}
        self.store.upsert_job(self.job)
        self.store.set('profile', {'provider': 'codex', 'consent': True, 'linkedin_consent': True, 'secondary': True,
                                  'cv_text': 'Led a systems team', 'hard_requirements': '', 'markets': defaults()})
        self.store.application(self.job['id'], 'saved')
        self.store.add_feedback(self.job['id'], 'like', [], 'Synthetic feedback')

    def resolve(self, source=None, ai=None, supplied=None):
        ai = ai or FixtureAI()
        fetcher = source or FixtureFetcher(self.store, {URL: page('<script type="application/ld+json">' + json.dumps(posting()) + '</script>')})
        run = self.store.start_run('codex')
        DescriptionResolver(Hunter(self.root, self.store), ai, NoDetail(), fetcher).execute(run, self.store.jobs(), threading.Event(), supplied)
        return self.store.jobs()[0], self.store.runs()[0], ai, fetcher

    def test_verified_source_recovery_preserves_identity_feedback_and_application(self):
        original = self.store.jobs()[0]
        job, run, ai, _ = self.resolve()
        for key in ('id', 'source_id', 'url', 'events', 'feedback', 'application_status', 'first_seen'):
            self.assertEqual(job[key], original[key])
        self.assertEqual(len(self.store.jobs()), 1)
        self.assertEqual(job['description'], TEXT.strip())
        self.assertEqual(job['description_source_url'], URL)
        self.assertEqual(set(job['market_evaluations']), {'DE'})
        self.assertEqual(run['payload']['metrics'], {'attempted':1,'recovered':1,'unavailable':0,'blocked':0,'evaluated':1,'remaining':0})
        locator = ai.calls[0][1]
        self.assertNotIn('profile', locator); self.assertNotIn('cv_text', str(locator))
        self.assertEqual(ai.calls[-1][1]['profile']['market']['id'], 'DE')

    def test_country_and_exact_requisition_employer_title_locality_mismatch_rejected(self):
        original = structured_jobs(page('<script type="application/ld+json">' + json.dumps(posting()) + '</script>'))[0]
        match_identity(self.job, original)
        for field, value in [('company','Another Employer'),('title','Similar Systems Lead'),('location','Berlin, Netherlands'),('location','Munich, Germany'),('requisition_id','REQ-99')]:
            with self.subTest(field=field, value=value), self.assertRaises(RetrievalError):
                match_identity(self.job, {**original, field:value})
        with self.assertRaises(RetrievalError):
            match_identity({**self.job,'location':'Berlin'}, original)

    def test_similar_titles_without_employer_never_match(self):
        option = {'title':self.job['title'], 'company':'', 'location':self.job['location'], 'description':TEXT}
        with self.assertRaises(RetrievalError): match_identity(self.job, option)

    def test_multiple_matching_source_postings_are_ambiguous(self):
        body = '<script type="application/ld+json">' + json.dumps([posting(), posting()]) + '</script>'
        job, run, _, _ = self.resolve(FixtureFetcher(self.store, {URL:page(body)}))
        self.assertFalse(job.get('description')); self.assertEqual(job['description_status'], 'unverified')
        self.assertEqual(run['payload']['metrics']['remaining'],1)
        self.assertEqual(len(job['description_candidates']),2)
        selection=job['description_candidates'][0]['candidate_id']
        followup=self.store.start_run('codex');fetcher=FixtureFetcher(self.store,{})
        DescriptionResolver(Hunter(self.root,self.store),FixtureAI(),NoDetail(),fetcher).execute(followup,[job],threading.Event(),selection=selection)
        confirmed=self.store.jobs()[0]
        self.assertEqual(confirmed['description_status'],'public_verified');self.assertEqual(fetcher.requests,0)
        self.assertEqual(confirmed['url'],self.job['url']);self.assertEqual(confirmed['application_status'],'saved')

    def test_model_claim_without_real_source_description_cannot_be_imported(self):
        job, _, _, _ = self.resolve(FixtureFetcher(self.store,{URL:page('No structured source text')}))
        self.assertFalse(job.get('description')); self.assertFalse(job['market_evaluations'])

    def test_persisted_linkedin_stop_blocks_linkedin_but_permits_independent_employer(self):
        self.store.set('linkedin_stop','Synthetic access denial')
        job, run, ai, fetcher = self.resolve()
        self.assertEqual(fetcher.requests,1);self.assertEqual([k for k,_ in ai.calls],['resolve','evaluation'])
        self.assertEqual(job['description_status'],'public_verified');self.assertEqual(run['payload']['metrics']['recovered'],1)
        self.assertEqual(run['payload']['http_denials'],0);self.assertEqual(run['payload']['shared_stop_skips'],1)
        self.assertEqual(self.store.get('linkedin_stop'),'Synthetic access denial')

    def test_user_supplied_is_labeled_and_evaluated_without_source_fetch(self):
        self.store.set('linkedin_stop','Synthetic access denial')
        job, _, ai, fetcher = self.resolve(supplied=TEXT)
        self.assertEqual(job['description_status'],'user_supplied'); self.assertEqual(fetcher.requests,0)
        self.assertEqual([kind for kind, _ in ai.calls],['evaluation'])

    def test_prior_vacancy_access_denial_is_not_automatically_retried(self):
        self.store.upsert_job({'id':self.job['id'],'description_status':'blocked'})
        job, _, ai, fetcher=self.resolve()
        self.assertTrue(job.get('description'));self.assertEqual(fetcher.requests,1)
        self.assertEqual([k for k,_ in ai.calls],['resolve','evaluation'])
    def test_denied_employer_cannot_be_retried_when_linkedin_is_also_stopped(self):
        self.store.set('linkedin_stop','Synthetic denial');self.store.set('public:stop:employer.example','Synthetic employer denial')
        job,run,ai,fetcher=self.resolve()
        self.assertFalse(job.get('description'));self.assertEqual(fetcher.requests,0)
        self.assertEqual([k for k,_ in ai.calls],['resolve'])
        self.assertEqual(run['payload']['http_denials'],0);self.assertEqual(run['payload']['shared_stop_skips'],2)

    def test_netherlands_supplied_text_cannot_receive_german_evaluation(self):
        self.store.upsert_job({'id':self.job['id'],'location':'Amsterdam, Netherlands'})
        job, _, ai, _=self.resolve(supplied=TEXT)
        self.assertEqual(set(job['market_evaluations']),{'NL'})
        self.assertEqual(ai.calls[-1][1]['profile']['market']['id'],'NL')

    def test_cached_linkedin_description_used_even_when_source_stopped(self):
        from job_radar_ai.linkedin import LinkedIn
        self.store.cache('linkedin:detail:123456',{'id':'123456','title':self.job['title'],'company':self.job['company'],'description':TEXT})
        self.store.set('linkedin_stop','Synthetic access denial')
        ai = FixtureAI(); fetcher = FixtureFetcher(self.store,{})
        source = LinkedIn(self.root,self.store,threading.Event(),{'requests':0,'details':0,'spacing':5})
        run=self.store.start_run('codex')
        DescriptionResolver(Hunter(self.root,self.store),ai,source,fetcher).execute(run,self.store.jobs(),threading.Event())
        self.assertEqual(source.requests,0); self.assertEqual(source.cache_hits,1); self.assertEqual(fetcher.requests,0)
        self.assertEqual(self.store.jobs()[0]['description_status'],'linkedin')

    def test_legacy_never_attempted_and_budget_or_failed_are_distinct(self):
        self.assertEqual(description_state(self.job,self.store),'not_attempted')
        for reason, expected in [('request budget reached','budget_deferred'),('Synthetic failure','failed'),('Full job description unavailable','incomplete'),('access restricted 403','blocked')]:
            run=self.store.start_run('codex');self.store.update_run(run,'fixture',{'description_failures':[{'job_id':self.job['id'],'reason':reason}]},'failed')
            self.assertEqual(description_state(self.job,self.store),expected)

    def test_batch_is_bounded_to_ten_and_existing_run_blocks_overlap(self):
        for i in range(12): self.store.upsert_job({**self.job,'id':'linkedin:'+str(123457+i)})
        resolver=DescriptionResolver(Hunter(self.root,self.store))
        with patch.object(resolver,'execute') as execute:
            run=resolver.start();resolver.hunter.thread.join()
            self.assertEqual(len(execute.call_args.args[1]),10)
            self.assertIsNone(resolver.start())


class PublicSourceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Store(Path(temp.name)/'state.sqlite3')

    def test_https_credentials_ports_private_dns_and_linkedin_are_rejected(self):
        for url in ('http://example.com/job','https://u:p@example.com/job','https://example.com:444/job','https://localhost/job','https://www.linkedin.com/jobs/view/123456','https://example.com\\@127.0.0.1/job'):
            with self.subTest(url=url),self.assertRaises(RetrievalError):public_url(url)
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','100.64.0.1'):
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]),self.assertRaises(RetrievalError):public_addresses('public.example')
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('10.0.0.1',443))]),self.assertRaises(RetrievalError):public_addresses('public.example')

    def test_denial_is_persisted_and_never_retried_or_cross_host_redirected(self):
        calls=[]
        def denied(url):calls.append(url);raise RetrievalError('blocked','403 fixture')
        fetch=PublicFetcher(self.store,request=denied)
        for _ in range(2):
            with self.assertRaises(RetrievalError):fetch.get(URL,api=True)
        self.assertEqual(len(calls),1)
        other=PublicFetcher(self.store,request=lambda url:{'redirect':'https://other.example/jobs'})
        with self.assertRaises(RetrievalError):other.get('https://fresh.example/job',api=True)
        self.assertEqual(other.requests,1)

    def test_robots_disallow_and_cached_text_are_respected(self):
        calls=[]
        def fixture(url):calls.append(url);return page('User-agent: *\nDisallow: /careers',url)
        fetch=PublicFetcher(self.store,request=fixture)
        with self.assertRaises(RetrievalError):fetch.get(URL)
        self.assertEqual(calls,['https://employer.example/robots.txt'])
        self.store.cache('public:page:'+hashlib.sha256(URL.encode()).hexdigest(),page(TEXT))
        self.assertEqual(fetch.get(URL)['text'],TEXT);self.assertEqual(fetch.cache_hits,1)

    def test_html_cross_host_redirect_is_refused_before_requesting_target_robots(self):
        calls=[]
        def fixture(url):
            calls.append(url)
            return page('User-agent: *\nAllow: /',url) if url.endswith('/robots.txt') else {'redirect':'https://other.example/job'}
        fetch=PublicFetcher(self.store,request=fixture)
        with self.assertRaises(RetrievalError):fetch.get(URL)
        self.assertEqual(calls,['https://employer.example/robots.txt',URL])

    def test_greenhouse_public_api_exact_post_id_and_real_content(self):
        url='https://job-boards.greenhouse.io/synthetic/jobs/42'
        api='https://boards-api.greenhouse.io/v1/boards/synthetic/jobs/42'
        body={'id':42,'title':'Systems Lead','company_name':'Synthetic Employer','location':{'name':'Berlin, Germany'},'content':'&lt;p&gt;'+TEXT+'&lt;/p&gt;','requisition_id':'REQ-42'}
        fetch=FixtureFetcher(self.store,{api:page(json.dumps(body),api)})
        candidates=retrieve_candidates(url,fetch)
        self.assertEqual(candidates[0]['description'],TEXT.strip());self.assertEqual(candidates[0]['company'],'Synthetic Employer')
        body['id']=99;fetch.pages[api]=page(json.dumps(body),api)
        with self.assertRaises(RetrievalError):retrieve_candidates(url,fetch)

    def board_fixture(self, host):
        url='https://'+host+'/synthetic/42'
        employer=page('<script type="application/ld+json">'+json.dumps({'@type':'Organization','name':'Synthetic Employer','url':'https://employer.example'})+'</script><a href="'+url+'">Exact posting</a>')
        return url,employer

    def test_lever_public_api_requires_fetched_employer_ownership(self):
        url,employer=self.board_fixture('jobs.lever.co')
        api='https://api.lever.co/v0/postings/synthetic/42?mode=json'
        body={'id':'42','text':'Systems Lead','categories':{'location':'Berlin, Germany'},'descriptionPlain':TEXT,'lists':[{'text':'Requirements','content':'<p>Source requirement</p>'}]}
        fetch=FixtureFetcher(self.store,{URL:employer,api:page(json.dumps(body),api)})
        with self.assertRaises(RetrievalError):retrieve_candidates(url,fetch)
        result=retrieve_candidates(url,fetch,URL)[0]
        self.assertEqual(result['company'],'Synthetic Employer');self.assertIn('Source requirement',result['description'])
        fetch.pages[URL]=page('No employer evidence')
        with self.assertRaises(RetrievalError):retrieve_candidates(url,fetch,URL)

    def test_ashby_public_api_exact_posting_url_and_description(self):
        url,employer=self.board_fixture('jobs.ashbyhq.com')
        api='https://api.ashbyhq.com/posting-api/job-board/synthetic'
        body={'jobs':[{'title':'Systems Lead','location':'Berlin, Germany','jobUrl':url,'descriptionPlain':TEXT}]}
        fetch=FixtureFetcher(self.store,{URL:employer,api:page(json.dumps(body),api)})
        result=retrieve_candidates(url,fetch,URL)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['description'],TEXT)
        body['jobs'][0]['jobUrl']=url+'9';fetch.pages[api]=page(json.dumps(body),api)
        self.assertEqual(retrieve_candidates(url,fetch,URL),[])

    def test_hosted_source_stop_cannot_be_escaped_via_board_api(self):
        self.store.set('public:stop:job-boards.greenhouse.io','403 fixture')
        fetch=FixtureFetcher(self.store,{})
        with self.assertRaises(RetrievalError):retrieve_candidates('https://job-boards.greenhouse.io/synthetic/jobs/42',fetch)
        self.assertEqual(fetch.requests,0)

    def test_api_denial_stops_hosted_and_other_board_routes_of_same_publisher(self):
        def deny(url):raise RetrievalError('blocked','403 fixture')
        fetch=PublicFetcher(self.store,request=deny)
        with self.assertRaises(RetrievalError):fetch.get('https://boards-api.greenhouse.io/v1/boards/synthetic/jobs/42',api=True)
        fixture=FixtureFetcher(self.store,{})
        with self.assertRaises(RetrievalError):retrieve_candidates('https://boards.greenhouse.io/synthetic/jobs/42',fixture)
        self.assertEqual(fixture.requests,0)

    def test_request_size_denial_and_content_limits(self):
        class Response:
            status=200
            def getheader(self,name,default=None):return {'Content-Length':'1000001','Content-Type':'text/html'}.get(name,default)
            def read1(self,n):raise AssertionError('Oversize response must not be read')
        with patch('job_radar_ai.sources.PinnedHTTPS') as conn:
            conn.return_value.getresponse.return_value=Response()
            with self.assertRaises(RetrievalError) as error:request_public(URL)
            self.assertEqual(error.exception.status,'incomplete')
            conn.return_value.getresponse.return_value.status=403
            with self.assertRaises(RetrievalError) as error:request_public(URL)
            self.assertEqual(error.exception.status,'blocked')
