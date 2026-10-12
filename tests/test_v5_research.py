import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.research import ResearchHunter, observed_job
from job_radar_ai.store import Store
from job_radar_ai.sources import PublicFetcher
from job_radar_ai.access import restriction


def candidate(n=123456, country='France'):
    return dict(url=f'https://www.linkedin.com/jobs/view/{n}',title='Engineering Manager',company='Synthetic Employer',location='Lyon, '+country,country=country,country_quote='Lyon, '+country,description_sources=[])


def evidence(c):
    return dict(url=c['url'],title=c['title']+' at '+c['company'],snippet='Lead teams. '+c['location'])


class AI:
    def __init__(self):self.telemetry={};self.calls=[];self.batches=0
    def run(self,kind,task,context,**kwargs):
        self.calls.append((kind,context))
        if kind=='brief_v5':return {'professional_background':['Experienced technical professional'],'career_direction':'Leadership progression'}
        if kind=='research_v5':
            self.batches+=1
            country=context['profile']['market']['country'];c=candidate(123455+self.batches,country)
            self.telemetry={'web_calls':1,'observations':[evidence(c)],'observed_urls':[c['url']],'actions':[{'type':'search'}]}
            return dict(jobs=[c],summary='Real tool fixture, not a live search',limitations=[],continue_research=self.batches<=2,next_avenues=['Adjacent industries'])
        return {'assessments':[dict(job_id=j['id'],category='transferable',explanation='Preliminary leadership progression from actual snippet.',promising=True,gaps=['Full responsibilities unknown']) for j in context['jobs']]}


class ResearchTests(unittest.TestCase):
    def test_consented_direct_description_keeps_indexed_identity_and_actual_country(self):
        import test_hunter
        class DirectAI(AI):
            def run(self,kind,task,context,**kwargs):
                if kind=='evaluation':return {'evaluations':[test_hunter.assessment(context['jobs'][0]['id'])],'report':'Source fixture'}
                value=super().run(kind,task,context,**kwargs)
                if kind=='research_v5':value['continue_research']=False
                return value
        class Direct:
            requests=cache_hits=0;denied_in_run=False
            def detail(self,identity):
                self.requests+=1
                return dict(id='linkedin:'+identity,title='Engineering Manager',company='Synthetic Employer',location='Lyon, France',description='Lead systems team. '+('Source responsibilities. '*8),availability='unknown',url='https://www.linkedin.com/jobs/view/'+identity)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            store.set('profile',dict(provider='codex',consent=True,secondary=True,linkedin_consent=True,cv_text='Led a systems team',markets=[dict(id='FR',country='France',locations=['France'],hard_requirements='')],hard_requirements=''))
            run=store.start_run('codex');ResearchHunter(tmp,store).execute(run,threading.Event(),ai=DirectAI(),source=Direct())
            job=store.jobs()[0];self.assertEqual(job['source'],'LinkedIn indexed web')
            self.assertEqual(job['description_source']['kind'],'linkedin')
            self.assertEqual(store.runs()[0]['payload']['linkedin_requests'],1)
            self.assertEqual(store.runs()[0]['payload']['evaluated'],1)

    def test_exact_full_description_produces_full_evaluation_not_snippet_recommendation(self):
        import test_hunter
        class FullAI(AI):
            def run(self,kind,task,context,**kwargs):
                if kind=='evaluation':return {'evaluations':[test_hunter.assessment(context['jobs'][0]['id'])],'report':'Actual source fixture evaluated'}
                value=super().run(kind,task,context,**kwargs)
                if kind=='research_v5':
                    value['continue_research']=False
                    value['jobs'][0]['description_sources']=[dict(url='https://employer.example/role',employer_url='https://employer.example')]
                return value
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            store.set('profile',dict(provider='codex',consent=True,secondary=True,cv_text='Led a systems team',markets=[dict(id='FR',country='France',locations=['France'],hard_requirements='')],hard_requirements=''))
            run=store.start_run('codex');fetch=PublicFetcher(store,request=lambda _:self.fail('Mock description fetch only'))
            full=dict(description='Lead systems team. '+('Actual synthetic description. '*8),source_url='https://employer.example/role',evidence={'sha256':'synthetic'})
            with patch('job_radar_ai.completion.recover',return_value=full) as matches:
                ResearchHunter(tmp,store).execute(run,threading.Event(),ai=FullAI(),fetcher=fetch)
                self.assertEqual(matches.call_args.args[1],'https://employer.example/role')
                self.assertEqual(matches.call_args.args[2],'https://employer.example')
            result=store.runs()[0];job=store.jobs()[0]
            self.assertEqual(result['payload']['evaluated'],1)
            self.assertEqual(job['evaluation_status'],'fully_evaluated')
            self.assertTrue(job['market_evaluations']['FR']['evaluation']['recommend'])
            self.assertEqual(job['id'],'linkedin:123456');self.assertIn('linkedin.com',job['url'])

    def test_only_tool_observations_and_supported_fields_not_model_quotes(self):
        c=candidate();self.assertIsNone(observed_job(c,[]))
        c['country_quote']='AI paraphrased geographic evidence'
        job=observed_job(c,[evidence(c)])
        self.assertEqual(job['country'],'');self.assertNotIn('description',job)
        self.assertEqual(job['id'],'linkedin:123456')
        self.assertIn('Lead teams',job['source_observations'][0]['text'])
        c['company']='Invented Employer';self.assertEqual(observed_job(c,[evidence(candidate())])['company'],'')

    def test_batches_dynamic_markets_scoped_feedback_and_direct_stop_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            markets=[dict(id=code,country=country,locations=[country],languages='',conditions='',hard_requirements='') for code,country in [('FR','France'),('BE','Belgium'),('CH','Switzerland')]]
            store.set('profile',dict(provider='codex',consent=True,secondary=True,cv_text='Synthetic experienced professional seeking progression.',markets=markets,hard_requirements='',intent_confirmed=True))
            store.set('linkedin_access',restriction(403))
            ai=AI();run=store.start_run('codex');hunter=ResearchHunter(tmp,store)
            fetcher=PublicFetcher(store,request=lambda _:self.fail('No direct requests needed'))
            hunter.execute(run,threading.Event(),ai=ai,fetcher=fetcher)
            result=store.runs()[0]
            self.assertEqual(result['status'],'completed');self.assertEqual(result['payload']['discovered'],5)
            self.assertEqual(result['payload']['evaluated'],0);self.assertEqual(result['payload']['descriptions'],0)
            self.assertEqual(result['payload']['linkedin_requests'],0)
            for job in store.jobs():
                self.assertEqual(job['evaluation_status'],'preliminary');self.assertFalse(job['market_evaluations'])
            country=store.jobs()[0]['country'];job=store.jobs()[0]
            store.add_feedback(job['id'],'dislike',[],'Not my next move')
            market=next(m['id'] for m in markets if m['country']==country)
            self.assertEqual(len(store.feedback(market)),1)
            self.assertTrue(all(not store.feedback(m['id']) for m in markets if m['id']!=market))
            with self.assertRaises(ValueError):store.add_feedback(job['id'],'like',[],'','global')

    def test_unverified_tools_failure_and_cancel_preserve_observations(self):
        class Unverified(AI):
            def run(self,*args,**kwargs):
                value=super().run(*args,**kwargs);self.telemetry={};return value
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            store.set('profile',dict(provider='codex',secondary=True,markets=[dict(id='FR',country='France',locations=['France'],hard_requirements='')]))
            for ai,cancel in [(Unverified(),threading.Event()),(AI(),threading.Event())]:
                if type(ai)==AI:cancel.set()
                run=store.start_run('codex');ResearchHunter(tmp,store).execute(run,cancel,ai=ai)
                self.assertEqual(store.runs()[0]['status'],'failed' if isinstance(ai,Unverified) else 'canceled')
                self.assertEqual(store.jobs(),[])
