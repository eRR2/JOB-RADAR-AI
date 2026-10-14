import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.store import Store,SessionExpired
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.server import Application
from job_radar_ai.sources import PublicFetcher
from job_radar_ai.access import restriction

CV='Led electrical system architecture and technical teams.'
TEXT='Next: system ownership and technical leadership in Berlin, Germany; Eindhoven, Netherlands.'
MARKETS=[dict(id='DE',country='Germany',locations=['Berlin'],hard_requirements=''),dict(id='NL',country='Netherlands',locations=['Eindhoven'],hard_requirements='')]
PROFILE=dict(provider='codex',consent=True,secondary=True,cv_text=CV,looking_for=TEXT,markets=MARKETS,hard_requirements='')


def candidate(n,domain='systems'):
    return dict(url='https://www.linkedin.com/jobs/view/'+str(n),title='Architecture Lead',company='Synthetic',location='Berlin, Germany',country='Germany',country_quote='Berlin, Germany',description_sources=[])


class ScriptedAI:
    def __init__(self):self.calls=[];self.telemetry={};self.researches=0
    def run(self,kind,task,context,**kwargs):
        self.calls.append((kind,task,context,kwargs))
        self.telemetry={}
        if kind=='session_brief':return dict(background=['Electrical systems architecture and team leadership'],direction='Broader technical ownership',country_preferences=[])
        if kind=='session_strategy':return dict(strategy='Actual capabilities and credible progression',role_families=['Technical ownership'],markets=[dict(market_id=m['id'],linkedin_queries=[],web_queries=['Systems ownership '+m['country']]) for m in context['markets']])
        if kind=='enrichment':return dict(candidate_ids=[j['id'] for j in context['jobs']],reason='Observed ownership evidence')
        if kind=='research_v5':
            self.researches+=1
            cs=[candidate(123456),candidate(123457)]
            self.telemetry=dict(web_calls=1,observations=[dict(url=c['url'],title=c['title'],snippet='Synthetic Berlin, Germany. '+('Own electrical system architecture.' if i==0 else 'Main responsibility: optical lens design requiring specialist optics experience.')) for i,c in enumerate(cs)],actions=[{'queries':['Fresh systems responsibility query']}])
            return dict(jobs=cs,summary='Observed fixtures',limitations=[],continue_research=self.researches<3,next_avenues=['Same avenue'])
        if kind=='priority_v52':
            assert CV==context['profile']['cv_text']
            return dict(assessments=[dict(job_id=j['id'],category='direct' if j['id']=='linkedin:123456' else 'unrelated',recommend=j['id']=='linkedin:123456',priority='strong' if j['id']=='linkedin:123456' else 'unsuitable',next_step='Credible system-level ownership' if j['id']=='linkedin:123456' else 'Optical specialist duties lack demonstrated capability',critical_gap=j['id']!='linkedin:123456',gaps=['Actual full description unavailable'],evidence=[dict(requirement='System architecture',job_quote='Own electrical system architecture.',cv_quote='Led electrical system architecture',assessment='Direct capability evidence')] if j['id']=='linkedin:123456' else []) for j in context['jobs']])
        raise AssertionError(kind)


class VerifiedScriptedAI(ScriptedAI):
    """Publisher HTML fixture for tests that require completed assessments."""
    def run(self,kind,task,context,**kwargs):
        value=super().run(kind,task,context,**kwargs)
        if kind=='research_v5':
            for observation in self.telemetry['observations']:
                observation['text']='<link rel="canonical" href="'+observation['url']+'"><h1>'+observation['title']+'</h1><main><p>'+observation['snippet']+' '+('Actual job requirements and technical responsibilities. '*6)+'</p></main>'
                observation['observation_kind']='page_read'
        return value


class CleanSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'state.sqlite3',v5=True)
        self.store.set('profile',PROFILE);self.store.set('cv_text',CV);self.store.set('cv_filename','Synthetic CV.pdf')

    def populate_old(self):
        self.store.set('learned:DE',[{'text':'Technical ownership preferred','confidence':'explicit','feedback_ids':[1]}])
        self.store.upsert_job(dict(id='old',country='Germany',title='Historical vacancy',url='https://example.org/old',description='Old text',obsolete=True))
        self.store.application('old','rejected');self.store.add_feedback('old','irrelevant',['Specialist mismatch'],'Prefer system ownership')
        self.store.start_run('codex');self.store.cache('failed:url',{'status':'failed'})
        for key in ('research_next:DE','linkedin_pending','proposed_intent','provider_verified:codex','linkedin_stop','obsolete_trigger','retry_counter'):
            self.store.set(key,True)

    def test_real_reset_preserves_exact_knowledge_and_detaches_feedback(self):
        self.populate_old();self.store.set('linkedin_access',restriction(429,clock=datetime.now(timezone.utc)-timedelta(days=2)))
        token,backup=self.store.fresh_session()
        self.assertEqual(self.store.get('profile'),PROFILE);self.assertEqual(self.store.get('cv_text'),CV)
        self.assertEqual(self.store.get('profile')['looking_for'],TEXT)
        self.assertTrue(self.store.get('learned:DE'));self.assertEqual(self.store.get('persistent_feedback')[0]['note'],'Prefer system ownership')
        self.assertEqual(self.store.get('persistent_feedback')[0]['country'],'DE')
        for table in ('jobs','runs','cache','feedback','application_events','market_evaluations','observations'):
            with self.store.db() as db:self.assertEqual(db.execute('select count(*) from '+table).fetchone()[0],0)
        self.assertIsNone(self.store.get('retry_counter'));self.assertIsNone(self.store.get('linkedin_pending'));self.assertIsNone(self.store.get('linkedin_stop'))
        self.assertIsNone(self.store.get('provider_verified:codex'))
        b=sqlite3.connect(backup);self.addCleanup(b.close);self.assertEqual(b.execute('select count(*) from jobs').fetchone()[0],1)
        self.assertEqual(b.execute('pragma integrity_check').fetchone()[0],'ok')

    def test_stale_worker_cannot_write_any_new_session_state(self):
        token,_=self.store.fresh_session();old=self.store.bound(token)
        old.upsert_job({'id':'first'});run=old.start_run('codex')
        new,_=self.store.fresh_session()
        for action in (lambda:old.upsert_job({'id':'stale'}),lambda:old.set('linkedin_pending',True),lambda:old.cache('stale',{}),lambda:old.update_run(run,'Stale write')):
            with self.assertRaises(SessionExpired):action()
        self.assertEqual(self.store.jobs(),[]);self.assertNotEqual(token,new)
        self.store.bound(new).upsert_job({'id':'current'})
        self.assertEqual(self.store.jobs()[0]['id'],'current')

    def test_active_external_restrictions_survive_expired_internal_states_do_not(self):
        active=restriction(429,'3600');expired=restriction(429,clock=datetime.now(timezone.utc)-timedelta(days=2))
        self.store.set('linkedin_access',active);self.store.set('linkedin_pending',True)
        self.store.set('public:access:expired.example',expired);self.store.set('public:stop:expired.example','HTTP 429')
        self.store.set('public:access:denied.example',restriction(403))
        self.store.set('public:stop:robots.example','Publisher robots disallow')
        self.store.fresh_session()
        self.assertEqual(self.store.get('linkedin_access'),active)
        self.assertTrue(self.store.get('public:access:denied.example'))
        self.assertTrue(self.store.get('public:stop:robots.example'))
        self.assertIsNone(self.store.get('public:access:expired.example'))
        self.assertIsNone(self.store.get('public:stop:expired.example'))
        self.assertIsNone(self.store.get('linkedin_pending'))

    def test_late_genuine_denial_is_preserved_without_allowing_late_results(self):
        token,_=self.store.fresh_session();old=self.store.bound(token)
        self.store.fresh_session()
        stop=restriction(429,'3600');old.set('public:access:publisher.example',stop)
        self.assertEqual(self.store.get('public:access:publisher.example'),stop)
        shorter=restriction(429,'60');old.set('public:access:publisher.example',shorter)
        self.assertEqual(self.store.get('public:access:publisher.example'),stop)
        with self.assertRaises(SessionExpired):old.upsert_job({'id':'not-allowed'})

    def test_backup_failure_does_not_reset_user_or_research_data(self):
        self.store.upsert_job({'id':'old'})
        with patch.object(self.store,'backup',side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError):self.store.fresh_session()
        self.assertEqual(self.store.jobs()[0]['id'],'old');self.assertEqual(self.store.get('cv_text'),CV)

    def test_current_discovery_batch_cautious_recommendations_and_finite_research(self):
        self.store.set('profile',{**PROFILE,'markets':MARKETS[:1]})
        token,_=self.store.fresh_session();store=self.store.bound(token);run=store.start_run('codex');ai=ScriptedAI()
        fetch=PublicFetcher(store,request=lambda _:self.fail('No live request in this test'))
        SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai,fetcher=fetch)
        jobs={j['id']:j for j in self.store.jobs()}
        self.assertFalse(jobs['linkedin:123456'].get('preliminary',{}).get('recommend',False));self.assertNotIn('description',jobs['linkedin:123456'])
        self.assertEqual(jobs['linkedin:123456']['review_state']['reason'],'full_source_required')
        self.assertFalse(any(k=='priority_v52' for k,_,_,_ in ai.calls))
        self.assertFalse(jobs['linkedin:123457'].get('preliminary',{}).get('recommend',False))
        self.assertIn('optical',jobs['linkedin:123457']['source_observations'][0]['text'].lower())
        self.assertEqual(sum(k=='priority_v52' for k,_,_,_ in ai.calls),0)
        self.assertEqual(ai.researches,1)
        self.assertIn('DE',self.store.runs()[0]['payload']['diagnostics']['deferred_discovery'])
        self.assertTrue(all(o['timeout']<=90 for _,_,_,o in ai.calls))
        for kind,_,context,opts in ai.calls:
            if opts.get('research'):self.assertNotIn(CV,json.dumps(context))
        self.assertTrue(any('Titles alone' in task for _,task,_,_ in ai.calls))

    def test_restart_after_reset_does_not_reintroduce_old_jobs(self):
        (self.root/'version.json').write_text(json.dumps({'version':'5.3.0-preview'}))
        self.populate_old()
        first=Application(self.root,self.store.path,skill_mode=True)
        self.assertEqual(first.store.jobs(),[])
        second=Application(self.root,self.store.path,skill_mode=True)
        self.assertEqual(second.store.get('profile'),PROFILE)
        self.assertEqual(second.store.get('search_session'),first.store.get('search_session'))
        self.assertEqual(second.store.runs(),[])

    def test_running_worker_returning_after_reset_cannot_repopulate_results(self):
        token,_=self.store.fresh_session();store=self.store.bound(token);run=store.start_run('codex')
        entered=threading.Event();release=threading.Event()
        class LateAI(ScriptedAI):
            def run(self,kind,*args,**kwargs):
                if kind=='research_v5':entered.set();release.wait(3)
                return super().run(kind,*args,**kwargs)
        ai=LateAI();worker=threading.Thread(target=SessionSearch(self.root,store).execute,args=(run,threading.Event()),kwargs={'ai':ai})
        worker.start();self.assertTrue(entered.wait(2))
        self.store.fresh_session();release.set();worker.join(4)
        self.assertFalse(worker.is_alive());self.assertEqual(self.store.jobs(),[]);self.assertEqual(self.store.runs(),[])

    def test_native_source_html_is_reused_without_extra_request_or_per_job_ai(self):
        self.store.set('profile',{**PROFILE,'markets':MARKETS[:1]})
        token,_=self.store.fresh_session();store=self.store.bound(token);run=store.start_run('codex')
        description='Own electrical system architecture. '+('Actual source responsibilities and technical ownership. '*6)
        url='https://employer.example/jobs/REQ-1'
        class NativeAI(ScriptedAI):
            def run(self,kind,task,context,**kwargs):
                if kind=='research_v5':
                    c=candidate(123456);c['url']=url
                    html='<link rel="canonical" href="'+url+'"><h1>Architecture Lead</h1><div class="article-mainbody">Synthetic Berlin, Germany. '+description+'</div>'
                    self.telemetry={'web_calls':1,'observations':[dict(url=url,title=c['title'],text=html,observation_kind='page_read')],'actions':[{'type':'open','url':url}]}
                    return dict(jobs=[c],summary='Actual source fixture',limitations=[],continue_research=False,next_avenues=[])
                if kind=='priority_v52':
                    self.assertion=context['jobs'][0].get('description')
                    value=super().run(kind,task,context,**kwargs)
                    value['assessments'][0].update(recommend=True,critical_gap=False,priority='strong',category='direct',evidence=[dict(requirement='Architecture',job_quote='Own electrical system architecture.',cv_quote='Led electrical system architecture',assessment='Actual text supports responsibilities')])
                    return value
                return super().run(kind,task,context,**kwargs)
        ai=NativeAI();fetch=PublicFetcher(store,request=lambda _:self.fail('Native text should require no new request'))
        SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai,fetcher=fetch)
        retained=self.store.jobs()[0]
        self.assertIn(description.strip(),retained['description']);self.assertEqual(fetch.requests,0)
        self.assertEqual(retained['description_source']['kind'],'public_verified')
        self.assertTrue(retained['preliminary']['recommend']);self.assertTrue(ai.assertion)

    def test_same_unknown_country_job_is_not_evaluated_twice_for_two_markets(self):
        self.store.set('learned',[{'text':'Global demonstrated ownership preference'}])
        self.store.set('learned:DE',[{'text':'Germany-only preference'}])
        token,_=self.store.fresh_session();store=self.store.bound(token);run=store.start_run('codex')
        class UnknownAI(ScriptedAI):
            def run(self,kind,task,context,**kwargs):
                if kind=='research_v5':
                    self.calls.append((kind,task,context,kwargs))
                    c=candidate(123456);c.update(country='',country_quote='',location='Unverified locality')
                    html='<link rel="canonical" href="'+c['url']+'"><h1>'+c['title']+'</h1><main><p>Synthetic Unverified locality. Own electrical system architecture. '+('Actual job requirements. '*8)+'</p></main>'
                    self.telemetry={'web_calls':1,'observations':[dict(url=c['url'],title=c['title'],text=html,observation_kind='page_read')],'actions':[{'queries':[context['market']['country']]}]}
                    return dict(jobs=[c],summary='Same exact observed identity',limitations=[],continue_research=False,next_avenues=[])
                return super().run(kind,task,context,**kwargs)
        ai=UnknownAI();SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai)
        calls=[c for k,_,c,_ in ai.calls if k=='priority_v52']
        self.assertEqual(len(calls),1);self.assertEqual(calls[0]['feedback'],[])
        self.assertNotIn('market',calls[0]['profile'])
        self.assertEqual(calls[0]['profile']['learned_preferences'],[{'text':'Global demonstrated ownership preference'}])
        self.assertEqual(len(self.store.jobs()),1);self.assertEqual(self.store.jobs()[0]['country'],'')
