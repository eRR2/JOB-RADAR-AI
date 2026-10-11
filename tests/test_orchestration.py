import tempfile
import threading
import unittest
from pathlib import Path
from job_radar_ai.hunter import Hunter
from job_radar_ai.store import Store
from job_radar_ai.linkedin import SourceError
from job_radar_ai.contracts import WEIGHTS
from test_hunter import assessment


class ScriptedAI:
    def __init__(self,research=False):
        self.calls=[];self.research=research;self.telemetry={'web_calls':1,'observed_urls':['https://example.invalid/jobs/1']}

    def run(self,kind,task,context,**options):
        self.calls.append((kind,context))
        if kind=='plan':
            return {'strategy':'Synthetic responsibility-driven exploration','role_families':['Synthetic team leadership'],
                    'queries':[{'query':q,'location':'Example region','remote':'any','reason':'Synthetic'} for q in ['first','second']],
                    'supplementary_research':self.research,'research_queries':['Synthetic official vacancies'] if self.research else []}
        if kind=='triage':
            return {'detail_ids':[context['candidates'][-1]['id']],'rationale':'Select newest candidate','expand_queries':[]}
        if kind=='evaluation':
            return {'evaluations':[assessment(j['id']) for j in context['jobs']],'report':'Synthetic evidence-backed review'}
        if kind=='research':
            return {'jobs':[{'url':'https://example.invalid/jobs/1','title':'Invented','company':'Synthetic','location':'Example',
                             'requisition_id':'','description':'Lead systems team','evidence_quote':'Lead systems team'}],
                    'limitations':[],'summary':'Model claims are not retrieval evidence'}
        raise AssertionError(kind)


class ScriptedSource:
    requests=cache_hits=0
    def search(self,query,page):
        identity='111111' if query['query']=='first' else '222222'
        return [{'id':'linkedin:'+identity,'source_id':identity,'title':'Synthetic lead'}]
    def detail(self,identity):
        return {'id':'linkedin:'+identity,'description':'Lead systems team'}


class OrchestrationTests(unittest.TestCase):
    def run_hunter(self,source,ai,budgets=None):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        store=Store(Path(temporary.name)/'state.sqlite3')
        store.set('profile',{'provider':'codex','cv_text':'Led a systems team','weights':{k:1 for k in WEIGHTS},
                             'hard_requirements':'','secondary':True,'consent':True,'linkedin_consent':True})
        store.set('budgets',budgets or {'searches':2,'pages':1,'details':1,'requests':3,'spacing':5})
        run=store.start_run('codex');Hunter(Path(temporary.name),store).execute(run,threading.Event(),ai=ai,source=source)
        return store

    def test_expanded_candidates_receive_second_selection_and_full_review(self):
        ai=ScriptedAI();store=self.run_hunter(ScriptedSource(),ai)
        selections=[context for kind,context in ai.calls if kind=='triage']
        self.assertEqual(len(selections),2)
        self.assertEqual(len(selections[-1]['candidates']),2)
        jobs={job['id']:job for job in store.jobs()}
        self.assertIsNotNone(jobs['linkedin:222222']['evaluation'])
        self.assertIsNone(jobs['linkedin:111111']['evaluation'])

    def test_search_url_telemetry_cannot_prove_a_fabricated_description(self):
        store=self.run_hunter(ScriptedSource(),ScriptedAI(research=True))
        self.assertEqual(len(store.jobs()),2)
        self.assertEqual(store.runs()[0]['status'],'partial')
        self.assertTrue(any('complete source text' in warning for warning in store.runs()[0]['payload']['warnings']))

    def test_partial_pagination_keeps_first_page_and_separate_failure(self):
        class Source(ScriptedSource):
            def search(self,query,page):
                if page==2:raise SourceError('Second page unavailable')
                return [{'id':'linkedin:'+str(111111+i),'source_id':str(111111+i),'title':'Synthetic'} for i in range(10)]
        store=self.run_hunter(Source(),ScriptedAI(),{'searches':1,'pages':2,'details':1,'requests':3,'spacing':5})
        self.assertEqual(len(store.jobs()),10)
        self.assertEqual(store.runs()[0]['status'],'partial')
        self.assertEqual([source['status'] for source in store.runs()[0]['payload']['sources']],['success','failed'])

    def test_valid_empty_search_finishes_without_fabricated_jobs(self):
        class Source(ScriptedSource):
            def search(self,query,page):return []
        store=self.run_hunter(Source(),ScriptedAI())
        self.assertEqual(store.jobs(),[])
        self.assertEqual(store.runs()[0]['status'],'completed')
        self.assertEqual(store.runs()[0]['payload']['evaluated'],0)
