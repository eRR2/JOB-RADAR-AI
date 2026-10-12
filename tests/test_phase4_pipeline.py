"""Synthetic full workflow; no provider tools or live publisher requests."""
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.store import Store
from job_radar_ai.hunter import Hunter
from job_radar_ai.intent import confirm_intent
from job_radar_ai.sources import PublicFetcher,RetrievalError
from test_intent import proposal
from test_hunter import assessment
from test_recovery import page,TEXT


class IndependentPipelineTests(unittest.TestCase):
    def test_linkedin_stop_does_not_disable_ats_and_invalid_region_corrects_before_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'state.sqlite3')
            profile=confirm_intent(proposal(),{},'Actual career evidence. Led a systems team','Explore near Toronto, Canada')
            profile.update(provider='codex',consent=True,linkedin_consent=True,secondary=True)
            store.set('profile',profile);store.set('linkedin_stop','Synthetic persisted stop')
            calls=[]
            class AI:
                telemetry={}
                def run(self,kind,task,context,**kwargs):
                    calls.append(kind)
                    if kind=='plan':
                        return {'strategy':'Synthetic','role_families':['Process'],'queries':[{'query':'process','location':'Canada' if calls.count('plan')==1 else 'Toronto, Canada','remote':'any','reason':'Synthetic'}],'supplementary_research':False,'research_queries':[]}
                    if kind=='boards':
                        self_context=context
                        assert 'quote' not in self_context['scope']
                        return {'boards':[{'provider':'greenhouse','url':'https://boards.greenhouse.io/synthetic','employer_url':'','query':''}],'limitations':[]}
                    if kind=='triage':return {'detail_ids':[j['id'] for j in context['candidates']],'rationale':'Synthetic','expand_queries':[]}
                    if kind=='evaluation':return {'evaluations':[assessment(j['id']) for j in context['jobs']],'report':'Synthetic source-backed review'}
                    raise AssertionError(kind)
            class Source:
                requests=cache_hits=0
                def search(self,*args):raise AssertionError('LinkedIn must not be called')
                def detail(self,*args):raise AssertionError('LinkedIn must not be called')
            def request(url):
                assert calls.count('plan')==2,'Correction must precede source access'
                if url.endswith('/jobs/42'):data={'id':42,'title':'Process lead','company_name':'Synthetic Employer','location':{'name':'Toronto, Canada'},'content':TEXT}
                elif url.endswith('/jobs'):data={'jobs':[{'id':42,'internal_job_id':42,'title':'Process lead','location':{'name':'Toronto, Canada'},'absolute_url':'https://boards.greenhouse.io/synthetic/jobs/42'}]}
                else:data={'name':'Synthetic Employer'}
                return page(json.dumps(data),url)
            fetcher=PublicFetcher(store,budget=8,request=request,publisher_budget=4)
            with patch('job_radar_ai.hunter.PublicFetcher',return_value=fetcher):
                run=store.start_run('codex');Hunter(folder,store).execute(run,threading.Event(),ai=AI(),source=Source())
            payload=store.runs()[0]['payload']
            self.assertEqual(payload['evaluated'],1);self.assertEqual(payload['linkedin_requests'],0)
            self.assertEqual(payload['public_requests'],3);self.assertEqual(payload['requests'],3)
            self.assertTrue(store.jobs()[0]['market_evaluations']['CA']['evaluation']['recommend'])
            self.assertEqual(store.get('linkedin_stop'),'Synthetic persisted stop')
            self.assertEqual(store.runs()[0]['status'],'partial')

    def test_per_publisher_budget_and_cancellation_do_not_make_extra_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'state.sqlite3');cancel=threading.Event();requests=[]
            def request(url):requests.append(url);return page('{}',url)
            fetch=PublicFetcher(store,cancel,budget=8,request=request,publisher_budget=1)
            fetch.get('https://boards-api.greenhouse.io/first',api=True)
            with self.assertRaises(RetrievalError) as error:fetch.get('https://boards-api.greenhouse.io/second',api=True)
            self.assertEqual(error.exception.status,'budget_deferred');self.assertEqual(len(requests),1)
            cancel.set()
            with self.assertRaises(RetrievalError):fetch.get('https://api.lever.co/first',api=True)
            self.assertEqual(len(requests),1)
