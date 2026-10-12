"""Three focused multi-country evidence regressions; providers are fully mocked."""
import copy,json,unittest,urllib.error
from unittest.mock import patch
import test_server
from test_intent import proposal
from job_radar_ai.intent import validate_intent,EvidenceError

TEXT='Explore Germany near Nuremberg; Netherlands near Eindhoven.'
CV='Actual career evidence. PRIVATE_CV_MARKER synthetic experience only.'


def multi_country():
    value=proposal('Germany','DE','Nuremberg')
    value['markets'].append(proposal('Netherlands','NL','Eindhoven')['markets'][0])
    value['markets'][0]['quote']='Germany near Nuremberg'
    value['markets'][1]['quote']='Netherlands near Eindhoven'
    return value


class EvidenceTests(unittest.TestCase):
    setUp=test_server.HTTPTests.setUp
    tearDown=test_server.HTTPTests.tearDown
    request=test_server.HTTPTests.request

    def seed(self):
        store=self.server.app.store
        store.set('cv_text',CV)
        old={'objectives':'Original text','provider':'codex','consent':True,'markets':[]}
        store.set('profile',old);store.set('linkedin_stop','Keep restriction')
        store.set('public:stop:restricted.example','Keep publisher restriction')
        store.upsert_job({'id':'old','title':'Retained','url':'https://employer.example/job'})
        store.application('old','saved');store.add_feedback('old','like',[],'Retained')
        headers={'X-Radar-CSRF':json.load(self.request('/api/state'))['csrf'],'Origin':self.url}
        return store,old,store.jobs(),headers

    def test_paraphrased_multi_country_quotes_receive_exactly_one_quote_only_correction(self):
        store,old,jobs,headers=self.seed()
        correct=multi_country();bad=copy.deepcopy(correct)
        bad['markets'][0]['quote']='Nuremberg area in Germany'
        bad['markets'][1]['quote']='Around Eindhoven in the Netherlands'
        data={'looking_for':TEXT,'provider':'codex','consent':True,'secondary':True,'linkedin_consent':False}
        with patch('job_radar_ai.server.Provider') as ai:
            ai.return_value.run.side_effect=[bad,correct]
            self.request('/api/intent-analysis',data,headers).close()
            self.server.app.operation_thread.join(3)
            self.assertEqual(ai.return_value.run.call_count,2)
            correction=ai.return_value.run.call_args
            self.assertFalse(correction.kwargs['research'])
            self.assertEqual(correction.args[2]['user_text'],TEXT)
            self.assertEqual({i['country'] for i in correction.args[2]['invalid_evidence_fields']},{'DE','NL'})
        self.assertEqual(self.server.app.operation['status'],'completed')
        self.assertEqual(store.get('proposed_intent')['intent'],correct)
        self.assertEqual(store.get('proposed_intent')['input'],data)
        self.assertEqual(store.get('profile'),old);self.assertEqual(store.jobs(),jobs)
        self.assertEqual(store.get('cv_text'),CV);self.assertEqual(store.get('linkedin_stop'),'Keep restriction')
        self.assertEqual(store.get('public:stop:restricted.example'),'Keep publisher restriction');self.assertEqual(store.runs(),[])

    def test_country_quote_cannot_justify_invented_secondary_or_swapped_cities(self):
        validate_intent(multi_country(),CV,TEXT)
        for variant in ('country_only','invented_secondary','swapped_city'):
            with self.subTest(variant=variant):
                bad=multi_country()
                if variant=='country_only':bad['markets'][0]['quote']='Germany'
                elif variant=='invented_secondary':bad['markets'][0]['secondary']=['Berlin']
                else:
                    bad['markets'][0]['preferred']=['Eindhoven'];bad['markets'][0]['quote']=TEXT
                with self.assertRaises(EvidenceError) as error:validate_intent(bad,CV,TEXT)
                self.assertIn('Germany (DE)',str(error.exception))
                self.assertNotIn('PRIVATE_CV_MARKER',str(error.exception))

    def test_second_invalid_quote_or_origin_downgrade_stops_without_applying_profile(self):
        store,old,jobs,headers=self.seed()
        for downgrade in (False,True):
            with self.subTest(downgrade=downgrade),patch('job_radar_ai.server.Provider') as ai:
                bad=multi_country();bad['markets'][0]['quote']='Near Nuremberg in Germany'
                corrected=copy.deepcopy(bad)
                if downgrade:corrected['markets'][0].update(origin='inferred',quote='Germany near Nuremberg')
                ai.return_value.run.side_effect=[bad,corrected]
                self.request('/api/intent-analysis',{'looking_for':TEXT,'provider':'codex','consent':True},headers).close()
                self.server.app.operation_thread.join(3)
                self.assertEqual(ai.return_value.run.call_count,2)
                self.assertEqual(self.server.app.operation['status'],'failed')
                message=self.server.app.operation['message']
                self.assertIn('Germany (DE)',message);self.assertIn('geographic_quote_not_verbatim',message)
                self.assertIn('next-move text',message);self.assertNotIn('PRIVATE_CV_MARKER',message)
        self.assertIsNone(store.get('proposed_intent'))
        self.assertEqual(store.get('profile'),old);self.assertEqual(store.jobs(),jobs)
        self.assertEqual(store.get('cv_text'),CV);self.assertEqual(store.get('linkedin_stop'),'Keep restriction')
        self.assertEqual(store.get('public:stop:restricted.example'),'Keep publisher restriction');self.assertEqual(store.runs(),[])
