import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from job_radar_ai.markets import defaults, market_profile, migrated_profile, country_of
from job_radar_ai.hunter import Hunter, profile_signature, prepare_evaluation
from job_radar_ai.server import Application
from job_radar_ai.store import Store
from job_radar_ai.linkedin import SourceError
from test_hunter import assessment


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root/'state.sqlite3')
        self.profile = {'provider':'codex', 'objectives':'Lead teams', 'cv_text':'Led a systems team',
                        'consent':True, 'linkedin_consent':True, 'markets':defaults(), 'hard_requirements':''}
        self.store.set('profile', self.profile)

    def seed(self):
        for market in defaults():
            job = {'id':'linkedin:'+market['id'], 'title':'Synthetic', 'location':market['country'], 'description':'Lead systems team'}
            self.store.upsert_job(job, market_id=market['id'])
            self.store.evaluate(job['id'], prepare_evaluation(assessment(job['id']),job,market_profile(self.profile,market,self.store)), market_id=market['id'])

    def test_review_cannot_label_a_verified_listing_as_another_country(self):
        self.seed()
        hunter=Hunter(self.root,self.store)
        with patch('job_radar_ai.hunter.threading.Thread.start'), self.assertRaisesRegex(ValueError,'verified listing country'):
            hunter.review('linkedin:NL','DE')
        self.assertEqual(self.store.runs(),[])
        job=next(j for j in self.store.jobs() if j['id']=='linkedin:NL')
        self.assertNotIn('DE',job['market_evaluations'])

    def test_local_like_preserves_recommendations_and_only_stales_its_market(self):
        self.seed()
        self.store.add_feedback('linkedin:NL','like',[], '')
        state = Application(self.root,self.store.path).state()
        jobs = {j['id']:j for j in state['jobs']}
        self.assertFalse(jobs['linkedin:DE']['market_evaluations']['DE']['assessment_stale'])
        self.assertTrue(jobs['linkedin:NL']['market_evaluations']['NL']['assessment_stale'])
        self.assertTrue(jobs['linkedin:NL']['market_evaluations']['NL']['evaluation']['recommend'])
        self.assertEqual(jobs['linkedin:NL']['feedback'][-1]['kind'],'like')
        self.assertEqual(jobs['linkedin:NL']['application_status'],'none')
        self.assertEqual(self.store.feedback('DE'),[])
        self.assertEqual(self.store.feedback('NL')[0]['scope'],'NL')

    def test_explicit_global_feedback_stales_both_markets(self):
        self.seed()
        self.store.add_feedback('linkedin:NL','like',[], 'Leadership everywhere',scope='global')
        state=Application(self.root,self.store.path).state()
        for job in state['jobs']:
            self.assertTrue(next(iter(job['market_evaluations'].values()))['assessment_stale'])
        self.assertEqual(self.store.feedback('DE')[0]['note'],'Leadership everywhere')

    def test_ambiguous_country_and_geography_are_not_guessed(self):
        self.assertIsNone(country_of({'location':'Amsterdam'}, defaults()))
        self.assertIsNone(country_of({'location':'Germany, Netherlands'},defaults()))
        profile=migrated_profile({'region':'Germany and Netherlands','city':'Example','cv_text':'Synthetic'})
        self.assertTrue(profile['market_migration']['review_required'])
        self.assertEqual(profile['market_migration']['legacy_geography']['city'],'Example')
        self.assertEqual(profile['markets'][0]['conditions'],'')
        self.assertFalse(migrated_profile({'region':'Germany'})['market_migration']['review_required'])

    def test_legacy_migration_backups_and_preserves_all_old_rows(self):
        path=self.root/'legacy.sqlite3'
        old=Store(path)
        old.set('profile',{'region':'ambiguous','cv_text':'Synthetic CV','weights':{'a':1}})
        old.set('linkedin_stop','Denied; never retry')
        old.upsert_job({'id':'legacy','location':'Netherlands','description':'Synthetic'})
        old.evaluate('legacy',{'recommend':True,'weighted_score':82})
        old.application('legacy','applied')
        old.add_feedback('legacy','like',[], 'Original')
        with old.db() as db:
            for table in ('market_evaluations','job_markets','feedback_scopes'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=1')
            before={t:[tuple(x) for x in db.execute('SELECT * FROM '+t)] for t in ('jobs','feedback','application_events','settings')}
        reopened=Store(path)
        with reopened.db() as db:
            for table in ('jobs','feedback','application_events'):
                self.assertEqual(before[table],[tuple(x) for x in db.execute('SELECT * FROM '+table)])
        self.assertEqual(reopened.get('linkedin_stop'),'Denied; never retry')
        self.assertEqual(reopened.feedback('NL')[0]['note'],'Original')
        self.assertEqual(reopened.jobs()[0]['evaluation']['weighted_score'],82)
        backups=list((self.root/'backups').glob('migration-*.sqlite3'))
        self.assertEqual(len(backups),1)
        backup=sqlite3.connect(backups[0])
        self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],1)
        # Exercise the down path on a separate synthetic file, never over user state.
        restored=sqlite3.connect(self.root/'restored-v1.sqlite3')
        backup.backup(restored)
        self.assertEqual(restored.execute('PRAGMA user_version').fetchone()[0],1)
        for table,rows in before.items():
            self.assertEqual(restored.execute('SELECT * FROM '+table).fetchall(),rows)
        restored.close()
        backup.close()
        Store(path)
        self.assertEqual(len(list((self.root/'backups').glob('migration-*.sqlite3'))),1)

    def run_search(self,selected='all',bad=None,stop=False):
        calls=[]
        class AI:
            telemetry={}
            def run(self,kind,task,context,**kw):
                market=context['profile']['market'];calls.append((kind,market['id'],context))
                if kind=='plan':
                    if bad==market['id']: raise ValueError('Country AI failed')
                    location=market['country'] if bad!='escape' else 'Netherlands'
                    return {'strategy':market['id']+' independent strategy','role_families':[], 'queries':[{'query':market['id']+' leadership','location':location,'remote':'any','reason':'Synthetic'}], 'supplementary_research':False,'research_queries':[]}
                if kind=='triage':return {'detail_ids':[j['id'] for j in context['candidates']],'expand_queries':[],'rationale':'Synthetic'}
                if kind=='evaluation':return {'evaluations':[assessment(j['id']) for j in context['jobs']],'report':'Synthetic'}
                if kind=='learning':return {'preferences':[], 'explanation':'Synthetic'}
                raise AssertionError(kind)
        store=self.store
        class Source:
            requests=cache_hits=0
            queries=[]
            def search(self,query,page):
                self.queries.append(query);self.requests+=1
                if stop:
                    store.set('linkedin_stop','Denied');raise SourceError('Denied')
                market='DE' if query['location']=='Germany' else 'NL'
                return [{'id':'linkedin:'+market,'source_id':market,'location':query['location']}]
            def detail(self,identity):
                self.requests+=1
                return {'id':'linkedin:'+identity,'description':'Lead systems team'}
        source=Source();run=self.store.start_run('codex')
        Hunter(self.root,self.store).execute(run,threading.Event(),AI(),source,selected)
        return self.store.runs()[0],calls,source

    def test_country_search_constrains_actual_queries(self):
        for market,country in [('DE','Germany'),('NL','Netherlands')]:
            run,calls,source=self.run_search(market)
            self.assertEqual([q['location'] for q in source.queries],[country])
            self.assertEqual({c[1] for c in calls},{market})
            self.assertEqual(run['status'],'completed')

    def test_wrong_market_plan_is_rejected_before_network(self):
        run,calls,source=self.run_search('DE','escape')
        self.assertEqual(source.requests,0)
        self.assertEqual(run['status'],'failed')

    def test_all_plans_are_independent_and_failure_is_isolated(self):
        run,calls,source=self.run_search(bad='DE')
        self.assertEqual({c[1] for c in calls if c[0]=='plan'},{'DE','NL'})
        self.assertEqual(run['payload']['markets']['DE']['status'],'failed')
        self.assertEqual(run['payload']['markets']['NL']['status'],'completed')
        self.assertEqual(run['status'],'partial')
        self.assertEqual(len(self.store.jobs()),1)

    def test_global_stop_forbids_later_market_requests(self):
        run,calls,source=self.run_search(stop=True)
        self.assertEqual(source.requests,1)
        self.assertEqual(self.store.get('linkedin_stop'),'Denied')
        self.assertEqual({c[1] for c in calls if c[0]=='plan'},{'DE','NL'})
        self.assertEqual(run['status'],'failed')

    def test_small_shared_budget_is_fair_and_never_multiplied(self):
        self.store.set('budgets',{'searches':2,'pages':1,'details':2,'requests':2,'spacing':5})
        run,calls,source=self.run_search()
        self.assertEqual(source.requests,2)
        self.assertEqual({q['location'] for q in source.queries},{'Germany','Netherlands'})
        self.assertEqual(run['status'],'partial')

    def test_failed_reassessment_and_changed_description_preserve_prior_evaluation(self):
        self.seed()
        self.store.upsert_job({'id':'linkedin:NL','description':'Changed duties'},market_id='NL')
        job=next(j for j in Application(self.root,self.store.path).state()['jobs'] if j['id']=='linkedin:NL')
        self.assertTrue(job['market_evaluations']['NL']['assessment_stale'])
        self.assertTrue(job['market_evaluations']['NL']['evaluation']['recommend'])

    def test_new_assessment_has_no_weighted_score(self):
        job={'id':'linkedin:NL','description':'Lead systems team'}
        result=prepare_evaluation(assessment(job['id']),job,self.profile)
        self.assertNotIn('weighted_score',result)
        self.assertEqual(result['assessment_version'],2)

    def test_each_all_plan_receives_only_its_market_feedback_and_conditions(self):
        self.profile['markets'][0]['conditions']='German commute preference'
        self.profile['markets'][1]['conditions']='Dutch leadership preference'
        self.store.set('profile',self.profile)
        self.seed()
        self.store.add_feedback('linkedin:NL','like',[],'Dutch only')
        run,calls,source=self.run_search()
        plans={country:context for kind,country,context in calls if kind=='plan'}
        self.assertEqual(plans['DE']['feedback'],[])
        self.assertEqual(plans['NL']['feedback'][0]['note'],'Dutch only')
        self.assertEqual(plans['DE']['profile']['market']['conditions'],'German commute preference')
        self.assertNotIn('markets',plans['DE']['profile'])
        self.assertNotIn('weights',plans['NL']['profile'])

    def test_global_feedback_reaches_both_independent_strategies(self):
        self.seed();self.store.add_feedback('linkedin:NL','like',[],'Leadership everywhere',scope='global')
        run,calls,source=self.run_search()
        plans=[context for kind,_,context in calls if kind=='plan']
        self.assertEqual(len(plans),2)
        self.assertTrue(all(p['feedback'][0]['note']=='Leadership everywhere' for p in plans))

    def test_warning_dedup_preserves_multiple_source_failures(self):
        class AI:
            def run(self,kind,task,context,**kw):
                return {'strategy':'Synthetic','role_families':[], 'queries':[{'query':str(i),'location':'Germany','remote':'any','reason':'Synthetic'} for i in range(2)],'supplementary_research':False,'research_queries':[]}
        class Source:
            requests=cache_hits=0
            def search(self,query,page):self.requests+=1;raise SourceError('Identical warning')
        self.store.set('budgets',{'searches':3,'pages':1,'details':1,'requests':3,'spacing':5})
        run=self.store.start_run('codex');Hunter(self.root,self.store).execute(run,threading.Event(),AI(),Source(),'DE')
        payload=self.store.runs()[0]['payload']['markets']['DE']
        self.assertEqual(payload['warnings'],['Identical warning'])
        self.assertEqual(len(payload['sources']),2)
        self.assertEqual(payload['status'],'failed')

    def test_catchup_all_outcomes_are_one_persistent_run(self):
        self.profile.update(frequency='daily',time='00:00')
        self.store.set('profile',self.profile)
        app=Application(self.root,self.store.path,skill_mode=True)
        slot=app.catchup()['slot']
        def start():
            run,calls,source=self.run_search()
            return run['id']
        with patch.object(app.hunter,'start',side_effect=start):
            app.catchup_action({'slot':slot,'action':'run'})
            with self.assertRaises(ValueError):app.catchup_action({'slot':slot,'action':'run'})
        self.assertEqual(len(self.store.runs()),1)
        self.assertEqual(set(self.store.runs()[0]['payload']['markets']),{'DE','NL'})
        self.assertIsNone(Application(self.root,self.store.path,skill_mode=True).catchup())

    def test_invalid_ai_reassessment_keeps_previous_validated_assessment(self):
        self.seed();before=self.store.jobs()[0]['market_evaluations']
        class AI:
            def run(self,kind,task,context,**kw):
                value=assessment(context['jobs'][0]['id'])
                value['evidence'][0]['job_quote']='Fabricated content'
                return {'evaluations':[value],'report':'Invalid'}
        hunter=Hunter(self.root,self.store)
        with patch('job_radar_ai.hunter.Provider',return_value=AI()):
            hunter.review(self.store.jobs()[0]['id'],next(iter(before)))
            hunter.thread.join(5)
        self.assertEqual(self.store.runs()[0]['status'],'failed')
        self.assertEqual(self.store.jobs()[0]['market_evaluations'],before)

    def test_new_country_configuration_is_not_limited_to_de_nl(self):
        from job_radar_ai.markets import validate_markets,validate_queries
        market={'id':'FR','country':'France','locations':['Paris'],'languages':'French','conditions':'Synthetic','hard_requirements':''}
        self.assertEqual(validate_markets([market]),[market])
        validate_queries([{'location':'Paris, France'}],market)
        self.assertEqual(country_of({'location':'Paris, France'},[market]),'FR')

    def test_backup_failure_refuses_migration_without_changing_original(self):
        path=self.root/'refused.sqlite3';old=Store(path)
        old.upsert_job({'id':'synthetic','title':'Preserve'})
        with old.db() as db:db.execute('PRAGMA user_version=1')
        original_connect=sqlite3.connect
        def connect(destination,*args,**kw):
            if Path(destination).name.startswith('migration-'):raise sqlite3.OperationalError('Synthetic backup failure')
            return original_connect(destination,*args,**kw)
        with patch('job_radar_ai.store.sqlite3.connect',side_effect=connect):
            with self.assertRaises(sqlite3.OperationalError):Store(path)
        with old.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_global_identity_and_application_history_are_never_duplicated(self):
        job={'id':'linkedin:123456','description':'Lead systems team','location':'Germany'}
        for market in defaults():
            self.store.upsert_job(job,market_id=market['id'])
            self.store.application(job['id'],'saved')
            self.store.evaluate(job['id'],prepare_evaluation(assessment(job['id']),job,market_profile(self.profile,market,self.store)),market_id=market['id'])
        jobs=self.store.jobs()
        self.assertEqual(len(jobs),1)
        self.assertEqual(len(jobs[0]['events']),1)
        self.assertEqual(set(jobs[0]['market_evaluations']),{'DE','NL'})

    def test_country_contradiction_cannot_be_recommended_in_selected_market(self):
        job={'id':'linkedin:NL','description':'Lead systems team','location':'Netherlands','country_id':'NL'}
        value=prepare_evaluation(assessment(job['id']),job,market_profile(self.profile,defaults()[0],self.store))
        self.assertFalse(value['recommend'])

    def test_ambiguous_migration_requires_review_before_search_and_keeps_reminder(self):
        self.profile.update(cv_text='Led a synthetic systems team delivering engineering projects.',frequency='daily',time='00:00',market_migration={'review_required':True})
        self.store.set('profile',self.profile)
        app=Application(self.root,self.store.path,skill_mode=True)
        slot=app.catchup()['slot']
        with self.assertRaisesRegex(ValueError,'legacy geography'):
            app.catchup_action({'slot':slot,'action':'run'})
        self.assertEqual(app.catchup()['slot'],slot)
        self.assertEqual(self.store.runs(),[])

    def test_cached_job_context_cannot_leak_other_market_feedback_or_rejections(self):
        self.seed();self.store.add_feedback('linkedin:NL','like',[],'Dutch regional teaching')
        self.store.application('linkedin:NL','rejected')
        calls=[]
        class AI:
            def run(self,kind,task,context,**kw):
                calls.append((kind,context))
                if kind=='plan':return {'strategy':'Synthetic','role_families':[],'queries':[{'query':'Leadership','location':'Germany','remote':'any','reason':'Synthetic'}],'supplementary_research':False,'research_queries':[]}
                if kind=='triage':return {'detail_ids':['linkedin:NL'],'expand_queries':[],'rationale':'Synthetic'}
                if kind=='evaluation':return {'evaluations':[assessment('linkedin:NL')],'report':'Synthetic'}
                raise AssertionError(kind)
        class Source:
            requests=cache_hits=0
            def search(self,query,page):return [{'id':'linkedin:NL','source_id':'NL','location':'Netherlands'}]
            def detail(self,identity):raise AssertionError('Use the stored full description')
        run=self.store.start_run('codex');Hunter(self.root,self.store).execute(run,threading.Event(),AI(),Source(),'DE')
        evaluation=next(context for kind,context in calls if kind=='evaluation')
        self.assertEqual(evaluation['feedback'],[])
        for field in ('feedback','market_evaluations','evaluation','events','application_status'):
            self.assertNotIn(field,evaluation['jobs'][0])
        job=next(j for j in self.store.jobs() if j['id']=='linkedin:NL')
        self.assertFalse(job['market_evaluations']['DE']['evaluation']['recommend'])


if __name__=='__main__':unittest.main()
