"""Offline coordinator regressions for bounded, independent triage calls."""
import copy
import json
import threading
import unittest
from unittest.mock import patch
import test_clean_search as fixtures
from test_review_pipeline import ReviewAI
from job_radar_ai.contracts import provider_schema,validate
from job_radar_ai.providers import ProviderError
from job_radar_ai.session_search import SessionSearch,initial_plan
from job_radar_ai.sources import PublicFetcher
from job_radar_ai.verification import triage_batches,triage_output_size
from job_radar_ai.reporting import review_state


class TriageTimeoutTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def test_batches_bound_input_and_expected_decision_output(self):
        jobs=[{'id':str(i),'title':'Systems owner','source_observations':[{'text':'Actual duties. '*50}]} for i in range(45)]
        batches=list(triage_batches(jobs))
        self.assertGreater(len(batches),1)
        self.assertTrue(all(len(b)<=8 for b in batches))
        self.assertEqual([j['id'] for b in batches for j in b],[str(i) for i in range(45)])
        short=list(triage_batches([{'id':str(i),'title':'Short'} for i in range(45)]))
        self.assertTrue(all(len(b)<=8 for b in short),'Output cost matters even when inputs are short')
        self.assertTrue(all(triage_output_size(b)<=14000 for b in short))
        constrained=list(triage_batches(jobs,shared_chars=39000))
        self.assertTrue(all(39000+len(json.dumps(b))<=40000 for b in constrained))

    def test_timeout_is_local_and_other_batches_reach_source_and_assessment(self):
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.MARKETS[:1]})
        class AI(ReviewAI):
            def __init__(self):super().__init__();self.triages=[];self.failed=[]
            def run(self,kind,task,context,**kwargs):
                if kind=='enrichment':
                    self.triages.append([j['id'] for j in context['jobs']])
                    if len(self.triages)==2:
                        self.failed=self.triages[-1]
                        raise ProviderError('Controlled triage timeout','time_window')
                return super().run(kind,task,context,**kwargs)
        ai=AI();run=self.store.start_run('codex')
        fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live publisher requests'))
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,fetcher=fetcher)
        jobs=self.store.jobs();payload=self.store.runs()[0]['payload'];d=payload['diagnostics']
        self.assertGreater(len(ai.triages),2)
        self.assertTrue(any(j.get('preliminary',{}).get('recommend') for j in jobs))
        first=set(ai.triages[0]);later=set(ai.triages[-1])
        self.assertTrue(all(j.get('description') and j.get('preliminary') for j in jobs if j['id'] in first|later))
        self.assertTrue(all(j['review_state']=={'status':'pending','reason':'triage_timeout'} for j in jobs if j['id'] in ai.failed))
        self.assertNotIn('enrichment',d['completed_phases'])
        self.assertEqual(self.store.runs()[0]['status'],'partial')
        self.assertEqual(len(jobs),24)
        self.assertEqual(fetcher.requests,0)
        self.assertEqual(sum(ids==ai.failed for ids in ai.triages),1,'No automatic retry of a failed batch')

    def test_time_consuming_first_timeout_leaves_source_and_assessment_budget(self):
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.MARKETS[:1]})
        clock=[0.0];limits=[]
        class AI(ReviewAI):
            count=0
            def run(self,kind,task,context,**kwargs):
                if kind=='enrichment':
                    self.count+=1
                    limits.append(kwargs['timeout'])
                    if self.count==1:
                        clock[0]+=kwargs['timeout']
                        raise ProviderError('Controlled first batch timeout','time_window')
                return super().run(kind,task,context,**kwargs)
        run=self.store.start_run('codex');ai=AI()
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]):
            SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
                fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live source')))
        self.assertGreater(ai.count,1)
        self.assertGreater(sum(bool(j.get('preliminary')) for j in self.store.jobs()),0)
        self.assertEqual(clock[0],30)
        self.assertTrue(all(limit<=30 for limit in limits))

    def test_compound_seniority_sentence_does_not_turn_into_chief_query(self):
        profile={**copy.deepcopy(fixtures.PROFILE),'intent':{'preferences':[
            {'topic':'career_direction','value':'Senior, Lead, Principal or Chief architecture; systems engineering leadership; technical lead',
             'origin':'explicit','scope':''}]}}
        before=copy.deepcopy(profile);plan=initial_plan(profile,profile['markets'])
        queries=[q['query'] for m in plan['markets'] for q in m['linkedin_queries']]
        self.assertNotIn('Chief architecture',queries)
        self.assertIn('systems engineering leadership',queries)
        self.assertEqual(profile,before)

    def test_new_wire_decisions_are_compact_but_old_saved_reasons_remain_valid(self):
        schema=provider_schema('enrichment');props=schema['properties']['decisions']['items']['properties']
        self.assertLessEqual(schema['properties']['decisions']['maxItems'],8)
        self.assertLessEqual(props['reason']['maxLength'],300)
        validate('enrichment',{'candidate_ids':[],'reason':'Old envelope'})

    def test_saved_failed_call_projects_timeout_without_rewriting_old_records(self):
        diagnostics={'stop':{'phase':'enrichment','reason':'time_window'},'ai_calls':[
            {'kind':'enrichment','status':'failed','category':'time_window','job_ids':['one']}]}
        self.assertEqual(review_state({'id':'one'},diagnostics),{'status':'pending','reason':'triage_timeout'})
        self.assertEqual(review_state({'id':'other'},diagnostics),{'status':'pending','reason':'triage_not_reached'})

    def test_exact_rediscovery_retains_historical_requisition_and_application(self):
        job={'id':'linkedin:123456','url':'https://www.linkedin.com/jobs/view/123456',
            'title':'Systems owner','company':'Synthetic','requisition_id':'REQ-42'}
        self.store.upsert_job(job);self.store.application(job['id'],'applied');self.store.fresh_session()
        self.store.upsert_job({k:v for k,v in job.items() if k!='requisition_id'})
        current=self.store.jobs()[0]
        self.assertEqual(current.get('requisition_id'),'REQ-42')
        self.assertEqual(current['application_status'],'applied')
        self.store.upsert_job({**job,'id':'linkedin:123457','url':'https://www.linkedin.com/jobs/view/123457','requisition_id':''})
        different=next(j for j in self.store.jobs() if j['id']=='linkedin:123457')
        self.assertFalse(different.get('requisition_id'))
        self.assertEqual(different['application_status'],'none')


if __name__=='__main__':unittest.main()
