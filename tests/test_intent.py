import copy
import unittest
from job_radar_ai.intent import confirm_intent,validate_intent,legacy_text


def proposal(country='Canada',code='CA',city='Toronto',text='Explore near Toronto, Canada'):
    return {'summary':'Reviewed next move','experience':[{'text':'Transferable experience','quote':'Actual career evidence'}],
        'preferences':[{'topic':'direction','value':'Explore','scope':'','origin':'explicit','quote':'Explore','hard':False},
                       {'topic':'compensation','value':'','scope':'','origin':'unknown','quote':'','hard':False}],
        'markets':[{'id':code,'country':country,'scope_type':'city','preferred':[city],'secondary':[],'remote':'none','relocation':False,'origin':'explicit','quote':city}],
        'questions':[]}


class IntentTests(unittest.TestCase):
    def test_markedly_different_careers_geographies_without_salary_leadership_defaults(self):
        for career,country,code,city in [('Senior technical','Canada','CA','Toronto'),('SAP consultant','India','IN','Pune'),('Junior career changer','Australia','AU','Perth'),('Exploring possibilities','Brazil','BR','Recife')]:
            text=f'Explore {career} near {city}, {country}'
            profile=confirm_intent(proposal(country,code,city),{},'Actual career evidence',text)
            self.assertEqual(profile['markets'][0]['locations'],[city])
            self.assertEqual(profile['looking_for'],text)
            self.assertEqual(profile['hard_requirements'],'')
            self.assertNotIn('salary',profile)
            self.assertNotIn('leadership',profile)
            self.assertTrue(profile['intent_confirmed'])

    def test_exact_provenance_and_inferred_hard_constraint_rejected(self):
        p=proposal();p['preferences'][0].update(origin='inferred',hard=True,quote='')
        with self.assertRaisesRegex(ValueError,'cannot become'):validate_intent(p,'Actual career evidence','Explore near Toronto')
        p=proposal();p['experience'][0]['quote']='Invented qualification'
        with self.assertRaisesRegex(ValueError,'actual CV'):validate_intent(p,'Actual career evidence','Explore near Toronto')
        p=proposal();p['preferences'][0]['quote']='Must earn six figures'
        with self.assertRaisesRegex(ValueError,'provenance'):validate_intent(p,'Actual career evidence','Explore near Toronto')

    def test_missing_geography_keeps_proposal_unknown_and_requires_review_for_search(self):
        p=proposal();p['markets']=[];p['questions']=['Which geography is acceptable?']
        validate_intent(p,'Actual career evidence','Explore')
        with self.assertRaisesRegex(ValueError,'one to six'):confirm_intent(p,{},'Actual career evidence','Explore')

    def test_legacy_user_text_is_lossless_and_original_profile_unchanged(self):
        old={'objectives':'  Original text\nverbatim  ','salary':'User supplied text','markets':[{'country':'Canada','locations':['Toronto'],'conditions':'Original conditions','hard_requirements':''}]}
        snapshot=copy.deepcopy(old)
        self.assertIn(old['objectives'],legacy_text(old))
        p=confirm_intent(proposal(),old,'Actual career evidence','Explore near Toronto, Canada')
        self.assertEqual(p['legacy_profile'],snapshot)
        self.assertEqual(p['objectives'],snapshot['objectives'])
        self.assertEqual(old,snapshot)

    def test_unknown_values_and_more_than_two_questions_rejected(self):
        p=proposal();p['preferences'][1]['value']='Invented compensation'
        with self.assertRaisesRegex(ValueError,'Unknown'):validate_intent(p,'Actual career evidence','Explore near Toronto')
        p=proposal();p['questions']=['a','b','c']
        with self.assertRaises(ValueError):validate_intent(p,'Actual career evidence','Explore near Toronto')
