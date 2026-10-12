import json
import unittest
import urllib.error
from unittest.mock import patch
import test_server
from test_intent_evidence import multi_country, TEXT, CV
from job_radar_ai.research import ResearchHunter
from job_radar_ai.server import Application


class V5HTTPTests(unittest.TestCase):
    generation='5.0.0-preview'
    setUp=test_server.HTTPTests.setUp
    tearDown=test_server.HTTPTests.tearDown
    request=test_server.HTTPTests.request

    def test_fresh_onboarding_review_routine_and_same_user_reopen(self):
        app=self.server.app;store=app.store
        self.assertTrue(store.v5);self.assertIsInstance(app.hunter,ResearchHunter)
        with patch.object(Application,'providers',return_value={}):state=app.state()
        self.assertEqual(state['cv']['text'],'');self.assertEqual(state['jobs'],[])
        self.assertIsNone(state['profile']);self.assertEqual(state['runs'],[])
        store.set('cv_text',CV)
        headers={'X-Radar-CSRF':app.csrf,'Origin':self.url}
        data=dict(looking_for=TEXT,provider='codex',consent=True,secondary=True,linkedin_consent=False)
        with patch('job_radar_ai.server.Provider') as ai:
            ai.return_value.run.return_value=multi_country()
            self.request('/api/intent-analysis',data,headers).close();app.operation_thread.join(3)
        self.assertIsNone(store.get('profile'));self.assertEqual(store.runs(),[])
        self.request('/api/intent-accept',{'confirm':'CONFIRM SEARCH INTENT'},headers).close()
        self.assertEqual([m['id'] for m in store.get('profile')['markets']],['DE','NL'])
        self.request('/api/routine',dict(frequency='weekly',time='10:30',weekday=2),headers).close()
        original=store.get('profile')
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/profile',{},headers)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/source-reset',{'confirm':'REVIEWED SOURCE STOP'},headers)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/routine',dict(frequency='daily',time='25:00',weekday=2),headers)
        reopened=Application(app.root,store.path,skill_mode=True)
        self.assertEqual(reopened.store.get('profile'),original)
        self.assertEqual(reopened.store.get('cv_text'),CV)
        self.assertEqual(reopened.store.jobs(),[])

    def test_country_feedback_application_history_and_unknown_country(self):
        store=self.server.app.store
        store.set('profile',{'markets':[{'id':'FR','country':'France'},{'id':'CH','country':'Switzerland'}]})
        for identity,country in [('one','France'),('two','Switzerland'),('unknown','')]:store.upsert_job({'id':identity,'country':country,'title':'Synthetic opportunity'})
        store.add_feedback('one','dislike',[],'Different career direction')
        store.add_feedback('unknown','like',[],'Worth investigating')
        self.assertEqual(len(store.feedback('FR')),1);self.assertEqual(store.feedback('CH'),[])
        store.application('two','saved');store.application('two','applied');store.application('two','rejected')
        self.assertEqual(store.feedback('CH'),[])
        self.assertEqual(len(next(j for j in store.jobs() if j['id']=='two')['events']),3)
