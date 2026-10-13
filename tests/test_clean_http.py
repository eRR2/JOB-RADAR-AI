import json
import unittest
import urllib.error
from unittest.mock import patch
import test_server
from test_clean_search import PROFILE,CV
from test_intent_evidence import multi_country,TEXT as INTENT_TEXT,CV as INTENT_CV
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.store import SessionExpired


class CleanHTTPTests(unittest.TestCase):
    generation='5.3.0-preview'
    setUp=test_server.HTTPTests.setUp
    tearDown=test_server.HTTPTests.tearDown
    request=test_server.HTTPTests.request

    def seed(self):
        app=self.server.app
        app.store.set('profile',{**PROFILE,'intent_confirmed':True});app.store.set('cv_text',CV)
        app.store.upsert_job({'id':'old','url':'https://example.org/old','title':'Old discovery'})
        return app,{'X-Radar-CSRF':app.csrf,'Origin':self.url}

    def test_new_search_resets_actual_database_before_worker_start(self):
        app,headers=self.seed();old_worker=app.hunter.store
        app.store.start_run('codex');app.store.set('linkedin_pending',True)
        with patch.object(SessionSearch,'start',return_value=42):
            self.request('/api/search',{},headers).close()
        self.assertEqual(app.store.jobs(),[]);self.assertEqual(app.store.runs(),[])
        self.assertIsNone(app.store.get('linkedin_pending'));self.assertEqual(app.store.get('profile')['markets'],PROFILE['markets'])
        with self.assertRaises(SessionExpired):old_worker.upsert_job({'id':'stale'})

    def test_removed_actions_cannot_invoke_old_research_path(self):
        app,headers=self.seed()
        for route in ('/api/reprioritize','/api/complete-descriptions','/api/application','/api/obsolete','/api/intent-accept'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(route,{},headers)
            self.assertEqual(error.exception.code,422)
        self.assertEqual(app.store.jobs()[0]['id'],'old')

    def test_unchanged_goal_reuses_confirmed_intent_without_model_invocation(self):
        app,headers=self.seed()
        profile={**PROFILE,'looking_for':INTENT_TEXT,'cv_text':INTENT_CV,'intent':multi_country(),'intent_confirmed':True}
        app.store.set('profile',profile);app.store.set('cv_text',INTENT_CV)
        with patch('job_radar_ai.server.Provider') as provider,patch.object(SessionSearch,'start',return_value=7):
            self.request('/api/career-search',dict(looking_for=INTENT_TEXT,provider='codex',consent=True,secondary=True,linkedin_consent=False),headers).close()
            provider.return_value.run.assert_not_called()
        self.assertIsNone(app.operation)
        self.assertEqual(app.store.jobs(),[])
        self.assertEqual(app.store.get('profile')['looking_for'],INTENT_TEXT)

    def test_new_uploaded_cv_is_used_instead_of_previous_profile_cv(self):
        app,headers=self.seed()
        profile={**PROFILE,'looking_for':INTENT_TEXT,'cv_text':INTENT_CV,'intent':multi_country(),'intent_confirmed':True}
        app.store.set('profile',profile)
        current=INTENT_CV+' New demonstrated capability.';app.store.set('cv_text',current)
        with patch('job_radar_ai.server.Provider') as provider,patch.object(SessionSearch,'start',return_value=7):
            provider.return_value.run.return_value=multi_country()
            self.request('/api/search',{},headers).close()
            provider.return_value.run.assert_not_called()
        self.assertIsNone(app.operation)
        self.assertEqual(app.store.get('profile')['cv_text'],current)
        self.assertEqual(app.store.get('profile')['markets'],profile['markets'])

    test_cross_origin_wrong_host_and_missing_csrf_writes_are_refused=test_server.HTTPTests.test_cross_origin_wrong_host_and_missing_csrf_writes_are_refused
    test_dashboard_loads_and_private_files_are_not_served=test_server.HTTPTests.test_dashboard_loads_and_private_files_are_not_served
