"""Focused regressions for the observed bad-request/fallback defect."""
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from job_radar_ai.sources import PublicFetcher,RetrievalError,request_public
from job_radar_ai.store import Store
from job_radar_ai.hunter import Hunter
from job_radar_ai.intent import confirm_intent
from test_intent import proposal
from test_recovery import page,TEXT
from test_hunter import assessment


class SearchFixTests(unittest.TestCase):
    def test_http400_keeps_numeric_status_and_is_not_a_publisher_stop(self):
        response=MagicMock();response.status=400
        with patch('job_radar_ai.sources.PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value=response
            with self.assertRaises(RetrievalError) as error:request_public('https://api.smartrecruiters.com/v1/companies/Synthetic/postings')
        self.assertEqual(error.exception.http_status,400)
        self.assertEqual(error.exception.status,'failed')

    def test_confirmed_intent_bad_board_and_denied_publisher_allow_independent_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'synthetic.sqlite3')
            profile=confirm_intent(proposal(),{},'Actual career evidence. Led a systems team','Explore near Toronto, Canada')
            profile.update(provider='codex',consent=True,secondary=True,linkedin_consent=True)
            store.set('profile',profile);store.set('linkedin_stop','Keep this stop')
            calls=[]
            url='https://boards.greenhouse.io/synthetic/jobs/42'
            class AI:
                telemetry={}
                def run(self,kind,*args,**kwargs):
                    calls.append(kind)
                    if kind=='plan':return {'strategy':'Synthetic','role_families':['Process'],'queries':[{'query':'Process','location':'Toronto, Canada','remote':'any','reason':'Synthetic'}],'supplementary_research':False,'research_queries':[]}
                    if kind=='boards':return {'boards':[{'provider':'smartrecruiters','url':'https://careers.smartrecruiters.com/Synthetic','employer_url':'','query':'Process'}],'limitations':[]}
                    if kind=='research':return {'jobs':[{'url':'https://denied.example/job','employer_url':'','title':'Process lead','company':'Synthetic Employer','location':'Toronto, Canada','requisition_id':'','description':TEXT,'evidence_quote':'Lead systems team.'},{'url':url,'employer_url':'','title':'Process lead','company':'Synthetic Employer','location':'Toronto, Canada','requisition_id':'','description':TEXT,'evidence_quote':'Lead systems team.'}],'summary':'Independent source','limitations':[]}
                    if kind=='evaluation':return {'evaluations':[assessment(j['id']) for j in args[1]['jobs']],'report':'Source-backed assessment'}
                    raise AssertionError(kind)
            class Source:
                requests=cache_hits=0
                def search(self,*args):raise AssertionError('No LinkedIn request allowed')
                def detail(self,*args):raise AssertionError('No LinkedIn request allowed')
            def request(endpoint):
                if 'smartrecruiters' in endpoint:raise RetrievalError('failed','HTTP 400',400)
                return page(json.dumps({'id':42,'title':'Process lead','company_name':'Synthetic Employer','location':{'name':'Toronto, Canada'},'content':TEXT}),endpoint)
            store.set('public:stop:denied.example','Preserved denial')
            fetch=PublicFetcher(store,request=request,budget=8,publisher_budget=4)
            with patch('job_radar_ai.hunter.PublicFetcher',return_value=fetch):
                run=store.start_run('codex');Hunter(folder,store).execute(run,threading.Event(),ai=AI(),source=Source())
            result=store.runs()[0]
            self.assertIn('research',calls);self.assertEqual(result['payload']['evaluated'],1)
            self.assertEqual(fetch.requests,2);self.assertEqual(result['payload']['linkedin_requests'],0)
            failed=result['payload']['sources'][0]
            self.assertEqual(failed['http_status'],400);self.assertEqual(failed['identity'],'not_verified')
            self.assertEqual(failed['diagnostics'][0]['parameters']['country'],['ca'])
            self.assertEqual(store.get('linkedin_stop'),'Keep this stop');self.assertEqual(store.get('public:stop:denied.example'),'Preserved denial')
