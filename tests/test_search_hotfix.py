import copy
import json
import threading
import unittest
from unittest.mock import patch
import test_server
from test_clean_search import PROFILE
from test_intent_evidence import multi_country,TEXT,CV
from job_radar_ai.intent import validate_intent,EvidenceError
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.linkedin import LinkedIn,SourceError
from job_radar_ai.access import active


class SearchHotfixTests(unittest.TestCase):
    generation='5.3.0-preview'
    setUp=test_server.HTTPTests.setUp
    tearDown=test_server.HTTPTests.tearDown
    request=test_server.HTTPTests.request

    def seed(self):
        app=self.server.app
        profile={**copy.deepcopy(PROFILE),'looking_for':TEXT,'intent':multi_country(),'intent_confirmed':True,'cv_text':'Old CV professional evidence'}
        profile['intent']['markets'][0]['quote']='Previously saved formatted evidence'
        profile['markets'][0].update(conditions='Germany-only salary and office conditions',languages='German')
        profile['markets'][1].update(conditions='Netherlands-only hybrid preference',languages='Dutch / English')
        app.store.set('profile',profile);app.store.set('cv_text',CV)
        app.store.set('learned:DE',[{'text':'Country-specific ownership preference'}])
        app.store.upsert_job({'id':'old','title':'Previous result'})
        return app,profile,{'X-Radar-CSRF':app.csrf,'Origin':self.url}

    def test_both_buttons_use_saved_preferences_current_cv_and_exactly_one_reset(self):
        for route in ('/api/search','/api/career-search'):
            with self.subTest(route=route):
                app,profile,headers=self.seed()
                data={} if route=='/api/search' else dict(looking_for=TEXT,provider='codex',consent=True,secondary=True,linkedin_consent=False)
                with patch('job_radar_ai.server.Provider') as ai,patch.object(app.store,'fresh_session',wraps=app.store.fresh_session) as reset,patch.object(SessionSearch,'start',return_value=1) as start:
                    self.request(route,data,headers).close()
                    ai.assert_not_called();reset.assert_called_once();start.assert_called_once()
                current=app.store.get('profile')
                self.assertEqual(current['markets'],profile['markets'])
                self.assertEqual(current['intent'],profile['intent'])
                self.assertEqual(current['looking_for'],TEXT)
                self.assertEqual(current['cv_text'],CV)
                self.assertEqual(app.store.get('learned:DE'),[{'text':'Country-specific ownership preference'}])
                self.assertEqual(app.store.jobs(),[])

    def test_changed_valid_goals_interpret_before_reset_once(self):
        app,profile,headers=self.seed();text=TEXT+' Prefer broader technical ownership.'
        def interpret(*args,**kwargs):
            self.assertEqual(app.store.jobs()[0]['id'],'old')
            return multi_country()
        with patch('job_radar_ai.server.Provider') as ai,patch.object(app.store,'fresh_session',wraps=app.store.fresh_session) as reset,patch.object(SessionSearch,'start',return_value=1):
            ai.return_value.run.side_effect=interpret
            self.request('/api/career-search',dict(looking_for=text,provider='codex',consent=True,secondary=True),headers).close()
            app.operation_thread.join(2)
            self.assertEqual(ai.return_value.run.call_count,1);reset.assert_called_once()
        self.assertEqual(app.operation['status'],'completed')
        self.assertEqual(app.store.get('profile')['looking_for'],text)

    def test_invalid_changed_evidence_does_not_clear_existing_session(self):
        app,profile,headers=self.seed();bad=multi_country();bad['markets'][0]['preferred']=['Invented city']
        with patch('job_radar_ai.server.Provider') as ai,patch.object(app.store,'fresh_session',wraps=app.store.fresh_session) as reset:
            ai.return_value.run.return_value=bad
            self.request('/api/career-search',dict(looking_for=TEXT+' Changed goal.',provider='codex',consent=True,secondary=True),headers).close()
            app.operation_thread.join(2);reset.assert_not_called()
            self.assertEqual(ai.return_value.run.call_count,2)
        self.assertEqual(app.store.get('profile'),profile);self.assertEqual(app.store.jobs()[0]['id'],'old')
        self.assertIn('preferred_location_not_supported',app.operation['message'])
        self.assertNotIn('PRIVATE_CV_MARKER',app.operation['message'])

    def test_new_429_is_recorded_and_preserved_without_retry(self):
        app,profile,headers=self.seed()
        source=LinkedIn(app.root,app.store,threading.Event(),{'requests':10,'spacing':0})
        failure=json.dumps({'error':'HTTP 429 access_restricted','http_status':429,'retry_after':'3600'})
        with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']),patch('job_radar_ai.linkedin.bounded_process',return_value=(1,'',failure)) as request:
            with self.assertRaises(SourceError):source.invoke(['detail','123456'],'synthetic',0)
            self.assertTrue(active(app.store.get('linkedin_access')))
            app.store.fresh_session()
            fresh=LinkedIn(app.root,app.store,threading.Event(),{'requests':10,'spacing':0})
            with self.assertRaises(SourceError):fresh.invoke(['detail','123456'],'synthetic',0)
            request.assert_called_once()


class QuoteFormattingTests(unittest.TestCase):
    def test_original_multicountry_passage_with_wrapped_whitespace_is_valid(self):
        text='Germany:\n  Nuremberg\nNetherlands:\n  Eindhoven'
        value=multi_country();value['preferences']=[]
        for m in value['markets']:m['quote']='Germany: Nuremberg Netherlands: Eindhoven'
        validate_intent(value,CV,text)
        value['markets'][0]['preferred']=['Eindhoven']
        with self.assertRaises(EvidenceError):validate_intent(value,CV,text)

    def test_country_alone_and_paraphrase_still_cannot_invent_city(self):
        for quote in ('Germany','Near Nuremberg in Germany'):
            value=multi_country();value['markets'][0]['quote']=quote
            with self.assertRaises(EvidenceError):validate_intent(value,CV,TEXT)
        value=multi_country();value['preferences']=[]
        text='Germany near Nuremberg; Netherlands near Eindhoven.'
        for m in value['markets']:m['quote']=text
        validate_intent(value,CV,text)
        value['markets'][0]['preferred']=['Eindhoven']
        with self.assertRaises(EvidenceError):validate_intent(value,CV,text)
