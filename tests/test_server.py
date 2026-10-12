import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from pathlib import Path
from job_radar_ai.server import make_server
from job_radar_ai.contracts import WEIGHTS


class HTTPTests(unittest.TestCase):
    def test_one_text_interpretation_requires_explicit_review_and_preserves_existing_history(self):
        from test_intent import proposal
        store=self.server.app.store
        cv='Actual career evidence '+('Synthetic responsibilities. '*3)
        store.set('cv_text',cv)
        old={'objectives':'  Original goal\nverbatim  ','markets':[]}
        store.set('profile',old)
        store.upsert_job({'id':'synthetic-existing','title':'Existing','url':'https://employer.example/job'})
        store.application('synthetic-existing','saved')
        state=json.load(self.request('/api/state'))
        headers={'X-Radar-CSRF':state['csrf'],'Origin':self.url}
        data={'looking_for':'Explore near Toronto, Canada','provider':'codex','consent':True,'secondary':True}
        for route in ('/api/intent-analysis','/api/intent-accept','/api/confirm-description-source'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(route,data)
            self.assertEqual(error.exception.code,403)
        with patch('job_radar_ai.server.Provider') as provider:
            provider.return_value.run.return_value=proposal()
            self.request('/api/intent-analysis',data,headers).close()
            self.server.app.operation_thread.join(3)
            self.assertEqual(store.get('profile'),old)
            self.assertEqual(len(store.runs()),0)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/intent-accept',{},headers)
        for edited in ({**data,'linkedin_consent':False,'looking_for':'Changed request'},{**data,'linkedin_consent':False,'consent':False}):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/intent-accept',{'confirm':'CONFIRM SEARCH INTENT','input':edited},headers)
        reviewed=proposal();reviewed['markets'][0]['preferred']=['Toronto','Ottawa'];reviewed['markets'][0]['quote']='Toronto, Ottawa, Canada'
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/intent-accept',{'confirm':'CONFIRM SEARCH INTENT','intent':{**reviewed,'summary':'Changed meaning'}},headers)
        with patch('job_radar_ai.server.Provider') as provider:
            provider.return_value.run.return_value=proposal()
            self.request('/api/intent-analysis',{**data,'summary_edit':'Explore a different direction'},headers).close()
            self.server.app.operation_thread.join(3)
            self.assertEqual(provider.return_value.run.call_args.args[2]['edited_understanding'],'Explore a different direction')
            self.assertEqual(store.get('profile'),old)
        self.request('/api/intent-accept',{'confirm':'CONFIRM SEARCH INTENT','intent':reviewed,'review_edits':'Toronto, Ottawa, Canada'},headers).close()
        saved=store.get('profile')
        self.assertTrue(saved['intent_confirmed']);self.assertEqual(saved['looking_for'],data['looking_for'])
        self.assertEqual(saved['intent_summary_edit'],'Explore a different direction')
        self.assertEqual(saved['legacy_profile'],old)
        self.assertEqual(saved['markets'][0]['locations'],['Toronto','Ottawa'])
        self.assertEqual(store.jobs()[0]['application_status'],'saved')
        self.assertEqual(len(store.runs()),0)

    def test_recovery_and_update_routes_keep_csrf_running_and_input_guards(self):
        token=json.load(self.request('/api/state'))['csrf']
        headers={'X-Radar-CSRF':token,'Origin':self.url}
        for route in ('/api/resolve-description','/api/complete-descriptions','/api/supplied-description','/api/check-updates','/api/update-notifications'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(route,{}, {'Origin':'https://evil.invalid'})
            self.assertEqual(error.exception.code,403)
        with patch('job_radar_ai.server.DescriptionResolver') as resolver:
            resolver.return_value.start.return_value=7
            self.request('/api/resolve-description',{'job_id':'synthetic'},headers).close()
            resolver.return_value.start.assert_called_with('synthetic',None)
            self.request('/api/complete-descriptions',{},headers).close()
            resolver.return_value.start.assert_called_with(None,None)
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/supplied-description',{'job_id':'synthetic'},headers)
            self.server.app.store.start_run('codex')
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/resolve-description',{'job_id':'synthetic'},headers)
        with patch.object(self.server.app,'check_updates') as check:
            self.request('/api/check-updates',{},headers).close();check.assert_called_once()
        self.request('/api/update-notifications',{'enabled':True},headers).close()
        self.assertTrue(self.server.app.store.get('update_notifications'))
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/update-notifications',{'enabled':'yes'},headers)
    def test_scoped_feedback_and_market_search_use_guarded_endpoints(self):
        from job_radar_ai.markets import defaults
        self.server.app.store.set('profile',{'provider':'codex','markets':defaults()})
        for country in ('Germany','Netherlands'):
            self.server.app.store.upsert_job({'id':country,'location':country})
        token=json.load(self.request('/api/state'))['csrf']
        headers={'X-Radar-CSRF':token,'Origin':self.url}
        self.request('/api/feedback',{'job_id':'Netherlands','kind':'like'},headers).close()
        self.assertEqual(self.server.app.store.preference_revision(market_id='DE'),0)
        self.assertEqual(self.server.app.store.preference_revision(market_id='NL'),1)
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/feedback',{'job_id':'Netherlands','kind':'like','scope':'DE'},headers)
        self.request('/api/feedback',{'job_id':'Netherlands','kind':'like','scope':'global'},headers).close()
        self.assertEqual(self.server.app.store.preference_revision(),1)
        with patch.object(self.server.app.hunter,'start',return_value=42) as start:
            self.request('/api/search',{'market_id':'DE'},headers).close()
            start.assert_called_once_with('DE')
        for path,data in [('/api/feedback',{'job_id':'Netherlands','kind':'like','scope':'global'}),('/api/migration-review',{'confirm':'REVIEWED LEGACY GEOGRAPHY'})]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,data,{'Origin':'https://evil.invalid'})
            self.assertEqual(error.exception.code,403)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path.cwd(), Path(self.temp.name)/'state.sqlite3', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        request = urllib.request.Request(self.url+path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={'Content-Type':'application/json', **(headers or {})})
        return urllib.request.urlopen(request)

    def test_dashboard_loads_and_private_files_are_not_served(self):
        response = self.request('/')
        self.assertIn('JOB-RADAR', response.read().decode())
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        for path in ['/.private/state.sqlite3', '/AGENTS.md', '/../../LICENSE']:
            with self.assertRaises(urllib.error.HTTPError):
                self.request(path)

    def test_skill_health_and_catchup_use_guarded_persistent_bridge(self):
        self.server.app.skill_mode = True
        self.server.app.store.set('profile', {'frequency':'daily', 'time':'00:00'})
        state = json.load(self.request('/api/state'))
        health = json.load(self.request('/api/health'))
        self.assertTrue(health['skill_mode'])
        self.assertNotIn('profile', health)
        headers = {'X-Radar-CSRF':state['csrf'], 'Origin':self.url}
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/catchup', {'slot':state['catchup']['slot'], 'action':'skip'})
        self.assertEqual(error.exception.code, 403)
        self.request('/api/catchup', {'slot':state['catchup']['slot'], 'action':'skip'}, headers).close()
        self.assertIsNone(json.load(self.request('/api/state'))['catchup'])
        self.assertEqual(self.server.app.store.runs()[0]['status'], 'skipped')
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/native-task', {'confirm':'CREATE WINDOWS TASK'}, headers)

    def test_cross_origin_wrong_host_and_missing_csrf_writes_are_refused(self):
        for headers in [{}, {'Origin':'https://evil.invalid'}, {'Host':'evil.invalid'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/search', {}, headers)
            self.assertEqual(error.exception.code, 403)

    def test_profile_persists_and_invalid_fields_are_refused(self):
        token = json.load(self.request('/api/state'))['csrf']
        headers = {'X-Radar-CSRF': token, 'Origin':self.url}
        value = {'provider':'codex', 'objectives':'Lead a synthetic team', 'weights':{k:1 for k in WEIGHTS}, 'frequency':'manual','time':'09:00','weekday':0}
        self.request('/api/profile', value, headers).close()
        self.assertEqual(json.load(self.request('/api/state'))['profile']['objectives'], value['objectives'])
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/profile', {**value, 'shell':'evil'}, headers)

    def test_actions_update_only_intended_job_and_preserve_history(self):
        for job_id in ['linkedin:111111','linkedin:222222']:
            self.server.app.store.upsert_job({'id':job_id,'title':'Synthetic','url':'https://www.linkedin.com/jobs/view/'+job_id.split(':')[1]})
        token = json.load(self.request('/api/state'))['csrf']
        headers = {'X-Radar-CSRF':token,'Origin':self.url}
        for status in ['saved','applied','rejected']:
            self.request('/api/application', {'job_id':'linkedin:111111','status':status}, headers).close()
        self.request('/api/feedback', {'job_id':'linkedin:222222','kind':'dislike','reasons':['too junior','wrong sector'],'note':'<script>alert(1)</script>'}, headers).close()
        jobs = {j['id']:j for j in json.load(self.request('/api/state'))['jobs']}
        self.assertEqual(jobs['linkedin:111111']['application_status'],'rejected')
        self.assertEqual(len(jobs['linkedin:111111']['events']),3)
        self.assertEqual(jobs['linkedin:222222']['application_status'],'none')

    def test_erasure_requires_specific_confirmation(self):
        token = json.load(self.request('/api/state'))['csrf']
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/erase', {'confirm':True}, {'X-Radar-CSRF':token,'Origin':self.url})

    def test_accepting_profile_preserves_user_followup_answers(self):
        self.server.app.store.set('profile',{'objectives':'Synthetic leadership'})
        self.server.app.store.set('proposed_profile',{'summary':'Synthetic professional summary','strengths':[],'evidence':[],'gaps':[],'questions':['Desired team scope?']})
        token=json.load(self.request('/api/state'))['csrf']
        self.request('/api/profile-accept',{'summary':'Reviewed summary','followup_answers':'Lead a team from day one'},
                     {'X-Radar-CSRF':token,'Origin':self.url}).close()
        profile=self.server.app.store.get('profile')
        self.assertEqual(profile['followup_answers'],'Lead a team from day one')
        self.assertEqual(profile['interpreted']['summary'],'Reviewed summary')

    def test_learning_and_source_reset_are_refused_during_active_search(self):
        self.server.app.store.start_run('codex')
        token=json.load(self.request('/api/state'))['csrf']
        for path,data in [('/api/learning-reset',{'confirm':'RESET LEARNING'}),('/api/learned',{'preferences':['New'],'paused':True}),('/api/source-reset',{'confirm':'REVIEWED SOURCE STOP'})]:
            with self.assertRaises(urllib.error.HTTPError):
                self.request(path,data,{'X-Radar-CSRF':token,'Origin':self.url})
