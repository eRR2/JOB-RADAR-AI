import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.location import geography
from job_radar_ai.providers import execution_error,ProviderError
from job_radar_ai.completion import vacancy_html,freshness,CompletionResolver,recover
from job_radar_ai.research import ResearchHunter
from job_radar_ai.store import Store
from job_radar_ai.sources import PublicFetcher,RetrievalError
from job_radar_ai.markets import market_profile
import test_hunter
import test_server
from test_intent_evidence import multi_country,TEXT,CV
from job_radar_ai.intent import validate_with_evidence_correction


class FunctionalTests(unittest.TestCase):
    def test_quote_correction_subscription_failure_is_not_hidden_as_provenance_only(self):
        value=multi_country();value['markets'][0]['quote']='Paraphrased Germany evidence'
        count=[]
        def correction(*args):
            count.append(1);raise ProviderError('Subscription usage exhausted','subscription_usage_limit')
        with self.assertRaises(ProviderError) as error:validate_with_evidence_correction(value,CV,TEXT,correction)
        self.assertEqual(error.exception.category,'subscription_usage_limit');self.assertEqual(count,[1])
        self.assertIn('Germany',str(error.exception));self.assertNotIn('PRIVATE_CV_MARKER',str(error.exception))
    def test_same_original_url_requires_exact_title_and_source_backed_employer_brand(self):
        job={'id':'web:synthetic','url':'https://employer.example/vacancy/123','title':'Systems Lead','company':'Synthetic Brand','location':'Lyon'}
        posting={'title':'Systems Lead','company':'Synthetic Subsidiary','location':'Lyon, France','description':'Actual responsibilities. '*10,'source_url':job['url'],'evidence':{'text':'Work with Synthetic Brand; hiring organization Synthetic Subsidiary'}}
        with patch('job_radar_ai.completion.retrieve_candidates',return_value=[posting]):
            full=recover(job,job['url'],'',None,[{'id':'FR','country':'France'}]);self.assertEqual(full['observed_company'],'Synthetic Brand')
        with patch('job_radar_ai.completion.retrieve_candidates',return_value=[{**posting,'title':'Unrelated leadership role'}]):
            with self.assertRaises(RetrievalError):recover(job,job['url'],'',None,[])
        with patch('job_radar_ai.completion.retrieve_candidates',return_value=[{**posting,'evidence':{'text':'Other employer only'}}]):
            with self.assertRaises(RetrievalError):recover(job,job['url'],'',None,[])
    def test_generic_city_inference_does_not_create_verified_country_feedback(self):
        markets=[dict(id='FR',country='France',locations=['Lyon']),dict(id='CH',country='Switzerland',locations=['Geneva'])]
        self.assertEqual(geography({'location':'Lyon Area'},markets)['status'],'inferred')
        self.assertEqual(geography({'location':'Geneva, Switzerland'},markets)['status'],'verified')
        self.assertEqual(geography({'company':'France headquarters','url':'https://fr.example/job'},markets)['status'],'unknown')
        conflict=markets+[dict(id='XX',country='Other country',locations=['Lyon'])]
        self.assertEqual(geography({'location':'Lyon'},conflict)['status'],'unknown')
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'v5.sqlite3',v5=True);s.set('profile',{'markets':markets})
            s.upsert_job({'id':'one','location':'Lyon','country':'','geography':geography({'location':'Lyon'},markets)})
            s.add_feedback('one','like',[],'Promising')
            self.assertEqual(s.feedback('FR'),[]);self.assertEqual(s.feedback()[0]['scope'],'unclassified')

    def test_freshness_publication_is_not_discovery_and_errors_remain_separate(self):
        for raw,category in [('You have hit your usage limit','subscription_usage_limit'),('Model foo not supported','model_access'),('rate limit reached','provider_rate_limit'),('Connection failed','execution_error')]:self.assertEqual(execution_error(raw).category,category)
        base={'source_url':'https://employer.example/job','first_seen':'2099-01-01','description':'Actual role'}
        self.assertEqual(freshness(base)['status'],'unknown');self.assertIsNone(freshness(base)['published_at'])
        self.assertEqual(freshness({**base,'valid_through':'2000-01-01'})['status'],'confirmed_closed')
        self.assertEqual(freshness({**base,'date_text':'Closing date: 31 December 2099','apply_urls':['https://employer.example/job/apply']})['status'],'confirmed_open')

    def test_real_html_container_identity_and_metadata_not_another_role(self):
        text='Lead systems team. '+('Synthetic source responsibility. '*10)
        page={'url':'https://employer.example/job','text':'<link rel="canonical" href="https://employer.example/job"><h1>Systems Lead</h1><div class="location">Lyon</div><div class="country">France</div><div class="article-mainbody">Synthetic Employer '+text+'</div>','sha256':'synthetic','at':'2026-01-01'}
        job={'title':'Systems Lead','company':'Synthetic Employer','location':'Lyon'}
        full=vacancy_html(job,page);self.assertIn(text.strip(),full['description']);self.assertEqual(full['country'],'France')
        with self.assertRaises(RetrievalError):vacancy_html({**job,'title':'Different management vacancy'},page)

    def test_completion_failure_retains_description_and_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            market=dict(id='FR',country='France',locations=['Lyon'],hard_requirements='')
            profile={'provider':'codex','consent':True,'secondary':True,'cv_text':'Led a systems team','looking_for':'Original country-specific career text','hard_requirements':'','markets':[market]};store.set('profile',profile)
            job={'id':'linkedin:123456','url':'https://www.linkedin.com/jobs/view/123456','title':'Systems Lead','company':'Synthetic Employer','location':'Lyon','description_sources':[{'url':'https://employer.example/job','employer_url':''}]};store.upsert_job(job)
            full={'title':'Systems Lead','company':'Synthetic Employer','location':'Lyon, France','country':'France','description':'Lead systems team. '+('Actual source responsibilities. '*8),'source_url':'https://employer.example/job','evidence':{'sha256':'synthetic'}}
            class AI:
                def run(self,*args,**kwargs):raise ProviderError('Subscription limit','subscription_usage_limit')
            run=store.start_run('codex')
            with patch('job_radar_ai.completion.recover',return_value=full):CompletionResolver(ResearchHunter(tmp,store),ai=AI()).execute(run,[job],threading.Event())
            saved=store.jobs()[0];self.assertTrue(saved['description']);self.assertEqual(saved['url'],job['url'])
            self.assertEqual(store.runs()[0]['payload']['provider_errors'][0]['category'],'subscription_usage_limit')
            self.assertEqual(store.get('profile'),profile)
            self.assertEqual(market_profile(profile,market,store)['authoritative_request'],profile['looking_for'])


class DirectCareerFlowTests(unittest.TestCase):
    generation='5.1.0-preview'
    setUp=test_server.HTTPTests.setUp
    tearDown=test_server.HTTPTests.tearDown
    request=test_server.HTTPTests.request
    def test_one_input_starts_internal_interpretation_without_summary_approval(self):
        app=self.server.app;app.store.set('cv_text',CV)
        app.store.set('profile',{'looking_for':'Old excluded location text','markets':[]})
        headers={'X-Radar-CSRF':app.csrf,'Origin':self.url}
        with patch('job_radar_ai.server.Provider') as ai,patch.object(app.hunter,'start',return_value=1) as search:
            ai.return_value.run.return_value=multi_country()
            self.request('/api/career-search',dict(looking_for=TEXT,provider='codex',consent=True,secondary=True),headers).close()
            app.operation_thread.join(3)
            self.assertEqual(app.operation['status'],'completed');search.assert_called_once()
            self.assertEqual(app.store.get('profile')['looking_for'],TEXT)
            self.assertIsNone(app.store.get('proposed_intent'))
            self.assertEqual(ai.return_value.run.call_args.args[2]['legacy_texts'],'')
            self.assertEqual(app.store.get('cv_text'),CV)
