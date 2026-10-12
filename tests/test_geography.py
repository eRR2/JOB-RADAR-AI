import unittest
from job_radar_ai.geography import bounded_plan,location_status,valid_query
from job_radar_ai.intent import confirm_intent
from job_radar_ai.providers import ProviderError
from test_intent import proposal


class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.profile=confirm_intent(proposal(),{},'Actual career evidence','Explore near Toronto, Canada')
        self.market=self.profile['markets'][0]
    def test_country_broadening_is_corrected_once_and_valid_queries_survive_failure(self):
        valid={'query':'Explore','location':'Toronto, Canada','remote':'any','reason':'Confirmed'}
        invalid={**valid,'location':'Canada'}
        calls=[]
        def fail():calls.append(1);raise ProviderError('Synthetic unavailable AI')
        result=bounded_plan({'queries':[valid,invalid]},self.market,self.profile,fail)
        self.assertEqual(result['queries'],[valid]);self.assertEqual(calls,[1])
        corrected=bounded_plan({'queries':[invalid]},self.market,self.profile,lambda:{'queries':[valid]})
        self.assertEqual(corrected['queries'],[valid])
    def test_remote_country_exception_requires_explicit_intent_and_remote_query(self):
        q={'query':'Explore','location':'Canada','remote':'remote'}
        scope=self.profile['intent']['markets'][0]
        self.assertFalse(valid_query(q,self.market,scope))
        scope['remote']='within_country';self.assertTrue(valid_query(q,self.market,scope))
        self.assertFalse(valid_query({**q,'remote':'any'},self.market,scope))
    def test_scoped_country_only_unknown_and_relocation_is_conditional_not_foreign(self):
        from job_radar_ai.markets import market_profile
        from unittest.mock import Mock
        scoped=market_profile(self.profile,self.market,Mock(preference_revision=lambda **kwargs:0))
        self.assertEqual(location_status({'location':'Canada'},scoped,self.market),'location_unknown')
        self.profile['intent']['markets'][0]['relocation']=True
        self.assertEqual(location_status({'location':'Vancouver, Canada'},self.profile,self.market),'secondary_conditional')
        self.assertEqual(location_status({'location':'Paris, France','country_id':'FR'},self.profile,self.market),'outside_preferred')
    def test_confirmed_market_context_excludes_archived_and_unscoped_country_conditions(self):
        from job_radar_ai.markets import market_profile
        from unittest.mock import Mock
        self.profile['legacy_profile']={'markets':[{'country':'Other','conditions':'Other salary'}]}
        self.profile['intent_review_edits']='Other-country private settings'
        self.profile['looking_for']='Raw multi-country compensation conditions'
        self.profile['intent']['preferences'].append({'scope':'IN','value':'Other salary','origin':'explicit','quote':'Other salary','topic':'salary','hard':False})
        scoped=market_profile(self.profile,self.market,Mock(preference_revision=lambda **kwargs:0))
        for key in ('legacy_profile','intent_review_edits','looking_for'):self.assertNotIn(key,scoped)
        self.assertTrue(all(p['scope'] in ('','CA') for p in scoped['intent']['preferences']))
        self.assertIn('looking_for',self.profile)
    def test_actual_location_not_query_provenance_and_no_invented_remote_or_commute(self):
        status=lambda job:location_status(job,self.profile,self.market)
        self.assertEqual(status({'location':'Toronto, Canada','query_location':'Elsewhere'}),'preferred')
        self.assertEqual(status({'location':'Vancouver, Canada','query_location':'Toronto, Canada'}),'outside_preferred')
        self.assertEqual(status({'location':'Toronto','query_country':'CA'}),'location_unknown')
        self.assertEqual(status({'location':'Canada'}),'location_unknown')
        self.profile['intent']['markets'][0]['secondary']=['Ottawa']
        self.assertEqual(status({'location':'Ottawa, Canada'}),'secondary_conditional')
        self.profile['intent']['markets'][0]['secondary']=['Ottawa, Canada']
        self.assertEqual(status({'location':'Ottawa, Ontario, Canada'}),'secondary_conditional')
        self.profile['intent']['markets'][0]['remote']='within_country'
        self.assertEqual(status({'location':'Vancouver, Canada','workplace':'remote'}),'outside_preferred')
        self.assertEqual(status({'location':'Vancouver, Canada','workplace':'remote','remote_verified':True}),'verified_remote')
    def test_region_membership_is_not_guessed_from_a_city_name(self):
        scope=self.profile['intent']['markets'][0]
        scope.update(scope_type='region',preferred=['Ontario'])
        self.assertEqual(location_status({'location':'Toronto, Canada'},self.profile,self.market),'location_unknown')
        self.assertEqual(location_status({'location':'Toronto, Ontario, Canada'},self.profile,self.market),'preferred')
        scope.update(scope_type='city',preferred=['Toronto, Canada'])
        self.assertEqual(location_status({'location':'Toronto','country':'CA'},self.profile,self.market),'preferred')
