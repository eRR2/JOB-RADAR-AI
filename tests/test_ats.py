import json
import tempfile
import unittest
from pathlib import Path
from job_radar_ai.ats import PublicBoards,board_identity,observe
from job_radar_ai.sources import RetrievalError
from job_radar_ai.store import Store
from test_recovery import FixtureFetcher,page,TEXT


class ATSTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.store=Store(Path(t.name)/'state.sqlite3')
    def test_greenhouse_metadata_discovery_small_detail_actual_text_and_identity(self):
        base='https://boards-api.greenhouse.io/v1/boards/synthetic'
        board={'provider':'greenhouse','url':'https://boards.greenhouse.io/synthetic','employer_url':'','query':''}
        card={'id':42,'internal_job_id':42,'title':'Systems Lead','absolute_url':board['url']+'/jobs/42','location':{'name':'Berlin, Germany'},'requisition_id':'REQ-42'}
        fixture={base:page(json.dumps({'name':'Synthetic Employer'}),base),base+'/jobs':page(json.dumps({'jobs':[card]}),base+'/jobs'),
                 base+'/jobs/42':page(json.dumps({**card,'company_name':'Synthetic Employer','content':TEXT}),base+'/jobs/42')}
        api=PublicBoards(FixtureFetcher(self.store,fixture));job=api.listing(board)[0]
        self.assertEqual(job['description'],'');full=api.complete(job)
        self.assertEqual(full['description'],TEXT.strip());self.assertEqual(full['id'],job['id'])
        fixture[base+'/jobs/42']=page(json.dumps({**card,'id':99,'company_name':'Synthetic Employer','content':TEXT}))
        with self.assertRaisesRegex(RetrievalError,'conflicts'):api.complete(job)
    def test_lever_eu_ownership_and_full_description(self):
        board={'provider':'lever','url':'https://jobs.eu.lever.co/synthetic','employer_url':'https://employer.example/careers','query':''}
        employer='<script type="application/ld+json">'+json.dumps({'@type':'Organization','name':'Synthetic Employer','url':'https://employer.example'})+'</script><a href="'+board['url']+'">Jobs</a>'
        endpoint='https://api.eu.lever.co/v0/postings/synthetic?mode=json&limit=20&skip=0'
        card={'id':'uuid-1','text':'Systems Lead','categories':{'location':'Berlin, Germany'},'hostedUrl':board['url']+'/uuid-1','descriptionPlain':TEXT,'workplaceType':'remote'}
        api=PublicBoards(FixtureFetcher(self.store,{board['employer_url']:page(employer,board['employer_url']),endpoint:page(json.dumps([card]),endpoint)}))
        result=api.listing(board)[0];self.assertTrue(result['remote_verified']);self.assertEqual(result['source'],'lever')
        board['employer_url']=''
        with self.assertRaisesRegex(RetrievalError,'ownership'):api.listing(board)
    def test_publisher_stop_before_any_route_and_board_schema_validation(self):
        board={'provider':'greenhouse','url':'https://boards.greenhouse.io/synthetic','employer_url':'','query':''}
        self.store.set('public:stop:greenhouse.io','Denied once')
        fetch=FixtureFetcher(self.store,{})
        with self.assertRaisesRegex(RetrievalError,'already stopped'):PublicBoards(fetch).listing(board)
        self.assertEqual(fetch.requests,0)
        for url in ('https://evil.example/synthetic','https://boards.greenhouse.io/synthetic/jobs/42','http://boards.greenhouse.io/synthetic'):
            with self.assertRaises(RetrievalError):board_identity({**board,'url':url})
    def test_ashby_listing_schema_explicit_country_and_full_text(self):
        board={'provider':'ashby','url':'https://jobs.ashbyhq.com/synthetic','employer_url':'https://employer.example/careers','query':''}
        html='<script type="application/ld+json">'+json.dumps({'@type':'Organization','name':'Synthetic Employer','url':'https://employer.example'})+'</script><a href="'+board['url']+'">Careers</a>'
        endpoint='https://api.ashbyhq.com/posting-api/job-board/synthetic'
        data={'jobs':[{'title':'Junior specialist','location':'Pune, India','jobUrl':board['url']+'/id-1','isListed':True,'isRemote':False,'descriptionPlain':TEXT,'address':{'postalAddress':{'addressCountry':'India'}}}]}
        api=PublicBoards(FixtureFetcher(self.store,{board['employer_url']:page(html,board['employer_url']),endpoint:page(json.dumps(data),endpoint)}))
        job=api.listing(board)[0];self.assertEqual(job['country'],'India');self.assertEqual(job['description'],TEXT)
        self.assertFalse(job['remote_verified'])
    def test_smartrecruiters_bounded_list_and_identity_verified_small_detail(self):
        board={'provider':'smartrecruiters','url':'https://careers.smartrecruiters.com/Synthetic','employer_url':'','query':'consultant','country':'CA'}
        base='https://api.smartrecruiters.com/v1/companies/Synthetic/postings'
        card={'id':'42','name':'Process Consultant','company':{'identifier':'Synthetic','name':'Synthetic Employer'},'location':{'city':'Toronto','country':'CA','remote':True},'ref':base+'/42'}
        data={**card,'jobAd':{'sections':{'jobDescription':{'title':'Responsibilities','text':TEXT}}}}
        data['jobAd']['sections']['videos']={'urls':[]}
        api=PublicBoards(FixtureFetcher(self.store,{base+'?limit=20&offset=0&q=consultant&country=ca':page(json.dumps({'content':[card]}),base),base+'/42':page(json.dumps(data),base+'/42')}))
        job=api.listing(board)[0];self.assertEqual(job['url'],card['ref']);full=api.complete(job)
        self.assertIn(TEXT.strip(),full['description']);self.assertTrue(full['remote_verified'])
    def test_workable_documented_public_endpoint_and_no_invented_schema(self):
        board={'provider':'workable','url':'https://apply.workable.com/synthetic','employer_url':'','query':''}
        endpoint='https://www.workable.com/api/accounts/synthetic?details=true'
        data={'name':'Synthetic Employer','jobs':[{'shortcode':'ABCD','title':'Junior Specialist','location':{'city':'Perth','country':'Australia'},'url':board['url']+'/j/ABCD','description':TEXT}]}
        fetch=FixtureFetcher(self.store,{endpoint:page(json.dumps(data),endpoint)});api=PublicBoards(fetch)
        self.assertEqual(api.listing(board)[0]['description'],TEXT.strip())
        fetch.pages[endpoint]=page(json.dumps({'name':'Synthetic Employer','jobs':[{'invented':True}]}),endpoint)
        with self.assertRaisesRegex(RetrievalError,'documented'):api.listing(board)
    def test_cross_platform_dedup_requires_exact_proven_identity_and_retains_history_observations(self):
        from job_radar_ai.ats import normalized
        url='https://employer.example/req-1'
        self.store.upsert_job({'id':'linkedin:111111','url':'https://www.linkedin.com/jobs/view/111111','description_source_url':url,'company':'Synthetic Employer','title':'Systems Lead','location':'Berlin, Germany'})
        self.store.application('linkedin:111111','interview');self.store.add_feedback('linkedin:111111','like',[],'Retain')
        job=normalized('greenhouse','synthetic',42,'Systems Lead','Synthetic Employer','Berlin, Germany',url,page(TEXT,url),TEXT)
        market={'id':'DE','country':'Germany'}
        stored,new=observe(self.store,job,None,market)
        self.assertFalse(new);self.assertEqual(stored['id'],'linkedin:111111');self.assertIn('linkedin.com',stored['url'])
        self.assertEqual(stored['application_status'],'interview');self.assertEqual(len(stored['feedback']),1);self.assertEqual(len(stored['source_observations']),1)
        other={**job,'id':'ats:greenhouse:synthetic:43','url':'https://employer.example/req-2','requisition_id':'REQ-2'}
        stored,new=observe(self.store,other,None,market)
        self.assertTrue(new);self.assertEqual(len(self.store.jobs()),2)
    def test_ambiguous_cross_platform_identity_keeps_raw_records_without_auto_merge(self):
        from job_radar_ai.ats import normalized
        url='https://employer.example/req-1'
        for identity in ('linkedin:1','linkedin:2'):
            self.store.upsert_job({'id':identity,'url':url,'company':'Synthetic Employer','title':'Systems Lead','location':'Berlin, Germany'})
        job=normalized('greenhouse','synthetic',42,'Systems Lead','Synthetic Employer','Berlin, Germany',url,page(TEXT,url),TEXT)
        stored,new=observe(self.store,job,None,{'id':'DE','country':'Germany'})
        self.assertTrue(new);self.assertTrue(stored['identity_review_required'])
        self.assertEqual(len(self.store.jobs()),3)
    def test_smartrecruiters_recovery_uses_documented_detail_once_and_exact_canonical_identity(self):
        from job_radar_ai.sources import PublicFetcher,retrieve_candidates
        url='https://jobs.smartrecruiters.com/Synthetic/42-process-lead'
        endpoint='https://api.smartrecruiters.com/v1/companies/Synthetic/postings/42'
        data={'id':'42','name':'Process lead','company':{'identifier':'Synthetic','name':'Synthetic Employer'},'location':{'city':'Toronto','country':'ca'},'postingUrl':url,'jobAd':{'sections':{'jobDescription':{'title':'Responsibilities','text':TEXT},'videos':{'urls':[]}}}}
        fetch=PublicFetcher(self.store,request=lambda u:page(json.dumps(data),u))
        posting=retrieve_candidates(url,fetch)[0]
        self.assertEqual(fetch.requests,1);self.assertEqual(fetch.cache_hits,1)
        self.assertEqual(posting['source_url'],url);self.assertIn(TEXT.strip(),posting['description'])
        self.assertEqual(posting['evidence']['url'],endpoint)
