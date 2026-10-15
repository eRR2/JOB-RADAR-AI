"""Offline coordinator contract: each small round produces durable useful work."""
import copy
import json
import threading
import unittest
from unittest.mock import patch

import test_clean_search as fixtures
from test_review_pipeline import ReviewAI
from job_radar_ai.contracts import provider_schema
from job_radar_ai.providers import ProviderError
from job_radar_ai.session_search import SessionSearch, evidence_version
from job_radar_ai.sources import PublicFetcher


class RoundAI(ReviewAI):
    def __init__(self, store, fail_middle=False, clock=None, costs=None, private_echo=False):
        super().__init__()
        self.store=store;self.trace=[];self.rounds=0
        self.fail_middle=fail_middle;self.clock=clock
        self.costs=costs or {};self.private_echo=private_echo

    def run(self,kind,task,context,**opts):
        self.trace.append(kind)
        if self.clock is not None:
            cost=self.costs.get(kind,3)
            self.clock[0]+=min(cost,opts['timeout'])
            if cost>opts['timeout']:
                self.telemetry={}
                raise ProviderError('Controlled exhausted call window.','time_window')
        if kind=='research_guidance':
            self.calls.append((kind,task,context,opts));self.telemetry={}
            return dict(focus=fixtures.CV if self.private_echo else 'Verify integration ownership rather than specialist optics',
                transferable_capabilities=['System integration ownership'],specialist_gaps=['Optics expertise unproven'],
                unsuccessful_queries=['Generic architecture titles'],missing_sources=['Full employer requirements'],
                next_queries=['Integration ownership '+context['next_market']['country']],continue_research=True)
        if kind=='research_v5':
            self.rounds+=1
            if self.rounds>1:
                # This assertion runs INSIDE the next discovery, not after execute.
                assert any(j.get('evaluation_status')=='assessed' for j in self.store.jobs()), 'Previous round was not persisted before next discovery'
            result=super().run(kind,task,context,**opts)
            result['jobs']=result['jobs'][:1]
            old=result['jobs'][0]['url'];new=old+'-round-'+str(self.rounds)
            result['jobs'][0]['url']=new
            result['jobs'][0]['country']=context['market']['country']
            result['jobs'][0]['location']=context['market']['locations'][0]+', '+context['market']['country']
            result['jobs'][0]['country_quote']=result['jobs'][0]['location']
            observation=self.telemetry['observations'][0]
            observation['url']=new
            observation['text']=observation['text'].replace(old,new).replace('Berlin, Germany',result['jobs'][0]['location'])
            self.telemetry['observations']=[observation]
            result.update(continue_research=self.rounds<2,next_avenues=['Integration ownership'])
            return result
        if kind=='enrichment' and self.fail_middle and self.rounds==2:
            self.calls.append((kind,task,context,opts));self.telemetry={}
            raise ProviderError('Controlled middle timeout; no retry.','time_window')
        return super().run(kind,task,context,**opts)


class IterativeResearchTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def execute(self,duration=900,**kwargs):
        profile=copy.deepcopy(fixtures.PROFILE)
        profile['looking_for']='PRIVATE CAREER REQUEST personal@example.invalid'
        profile['intent']={'markets':[],'preferences':[dict(topic='employers',value=name,origin='explicit',scope=scope)
            for name,scope in (('Synthetic Alpha',''),('Synthetic Beta','DE'))]}
        self.store.set('profile',profile)
        ai=RoundAI(self.store,**kwargs)
        run=self.store.start_run('codex')
        fetcher=PublicFetcher(self.store,request=lambda _:self.fail('Live access forbidden'))
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,fetcher=fetcher,duration=duration)
        self.assertEqual(fetcher.requests,0)
        return ai,self.store.runs()[0]

    def test_first_assessment_is_saved_before_next_discovery_and_queries_use_findings(self):
        ai,run=self.execute()
        self.assertEqual(ai.trace[:8],['session_brief','research_v5','enrichment','priority_v52',
            'research_guidance','research_v5','enrichment','priority_v52'])
        public=[c for k,_,c,o in ai.calls if o.get('research')]
        self.assertEqual([c['market']['id'] for c in public],['DE','NL','DE'])
        self.assertEqual(public[1]['planned_queries'],['Integration ownership Netherlands'])
        self.assertIn('Optics expertise unproven',json.dumps(public[1]['round_findings']))
        private=[c for k,_,c,_ in ai.calls if k=='research_guidance']
        self.assertTrue(private[0]['findings'][0]['triage_decision'])
        self.assertTrue(private[0]['findings'][0]['preliminary'])
        for c in public:
            self.assertNotIn(fixtures.CV,json.dumps(c))
            self.assertNotIn('PRIVATE CAREER REQUEST',json.dumps(c))
            self.assertNotIn('personal@example.invalid',json.dumps(c))
            self.assertNotIn('application_status',json.dumps(c))
        self.assertEqual([c['employer_focus'] for c in public],['Synthetic Alpha','Synthetic Alpha','Synthetic Beta'])
        self.assertEqual(len(run['payload']['comparison']),3)
        self.assertTrue(all(row['evidence'] for row in run['payload']['comparison']))

    def test_middle_timeout_preserves_first_result_and_independent_round_advances(self):
        ai,run=self.execute(fail_middle=True)
        self.assertEqual(ai.rounds,3)
        self.assertEqual(ai.trace.count('priority_v52'),2)
        jobs=self.store.jobs()
        self.assertEqual(sum(j.get('evaluation_status')=='assessed' for j in jobs),2)
        self.assertEqual(sum(j.get('triage_review',{}).get('reason')=='triage_timeout' for j in jobs),1)
        self.assertEqual(run['status'],'partial')
        failed=[c for c in run['payload']['diagnostics']['ai_calls'] if c['status']=='failed']
        self.assertEqual(len(failed),1)
        self.assertEqual(len({tuple(c['job_ids']) for c in run['payload']['diagnostics']['ai_calls'] if c['kind']=='enrichment'}),3)

    def test_phase_reentry_consumes_one_shared_ledger_and_total_deadline(self):
        clock=[0.0]
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]):
            ai,run=self.execute(clock=clock)
        d=run['payload']['diagnostics']
        self.assertEqual(d['phase_spent']['discovery'],3*sum(k in ('session_brief','research_v5','research_guidance') for k in ai.trace))
        self.assertEqual(d['phase_spent']['enrichment'],3*ai.trace.count('enrichment'))
        self.assertEqual(d['phase_spent']['evaluation'],3*ai.trace.count('priority_v52'))
        self.assertEqual(sum(d['phase_spent'].values()),clock[0])
        self.assertTrue(all(d['phase_spent'][p]<=v for p,v in d['phase_budgets'].items()))

    def test_guidance_and_small_discovery_wire_schemas_are_strict_recursively(self):
        def strict(node):
            if isinstance(node,dict):
                if node.get('type')=='object':
                    self.assertEqual(set(node['required']),set(node['properties']))
                    self.assertIs(node['additionalProperties'],False)
                for value in node.values():strict(value)
            elif isinstance(node,list):
                for value in node:strict(value)
        strict(provider_schema('research_guidance'))
        strict(provider_schema('research_v5'))
        self.assertLessEqual(provider_schema('research_v5')['properties']['jobs']['maxItems'],8)

    def test_spent_evaluation_time_cannot_be_renewed_by_a_later_round(self):
        clock=[0.0]
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]):
            ai,run=self.execute(clock=clock,costs={'priority_v52':60})
        d=run['payload']['diagnostics']
        self.assertEqual(ai.rounds,3)
        self.assertEqual(d['phase_spent']['evaluation'],150)
        self.assertEqual(sum(j.get('evaluation_status')=='assessed' for j in self.store.jobs()),2)
        self.assertEqual(run['status'],'partial')
        self.assertLessEqual(clock[0],900)
        research=[c for k,_,c,o in ai.calls if o.get('research')]
        self.assertEqual({c['market']['id'] for c in research},{'DE','NL'})

    def test_final_country_discovery_slot_cannot_be_consumed_by_optional_guidance(self):
        with patch('job_radar_ai.session_search.MAX_AI_CALLS',5):
            ai,run=self.execute()
        public=[c for k,_,c,o in ai.calls if o.get('research')]
        self.assertEqual([c['market']['id'] for c in public],['DE','NL'])
        self.assertEqual(sum(j.get('evaluation_status')=='assessed' for j in self.store.jobs()),1)
        self.assertEqual(run['payload']['usage']['ai_invocations'],5)

    def test_exhausted_round_discovery_share_does_not_discard_next_countrys_reserved_time(self):
        clock=[0.0]
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]):
            ai,run=self.execute(clock=clock,costs={'research_v5':100},duration=120)
        self.assertEqual(ai.trace.count('research_v5'),2)
        d=run['payload']['diagnostics']
        self.assertEqual(d['market_outcomes']['NL']['indexed_passes'],1)
        self.assertLessEqual(d['phase_spent']['discovery'],80)
        self.assertLessEqual(clock[0],120)

    def test_one_productive_company_does_not_cancel_another_explicit_priority(self):
        class CompanyAI(RoundAI):
            def run(inner,kind,task,context,**opts):
                result=super().run(kind,task,context,**opts)
                if kind=='research_v5':result['continue_research']=False
                if kind=='research_guidance':result['continue_research']=False
                return result
        # Reuse the profile setup without any live provider, then run the stricter
        # provider which wants to stop after its first productive employer.
        self.execute()
        self.store.fresh_session()
        ai=CompanyAI(self.store);run=self.store.start_run('codex')
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
            fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live source')))
        public=[c for k,_,c,o in ai.calls if o.get('research')]
        self.assertEqual([(c['market']['id'],c['employer_focus']) for c in public],
            [('DE','Synthetic Alpha'),('NL','Synthetic Alpha'),('DE','Synthetic Beta')])

    def test_private_echo_in_guidance_is_withheld_without_losing_country_coverage(self):
        ai,run=self.execute(private_echo=True)
        research=[c for k,_,c,o in ai.calls if o.get('research')]
        self.assertEqual([c['market']['id'] for c in research],['DE','NL','DE'])
        self.assertTrue(all(fixtures.CV not in json.dumps(c) for c in research))
        self.assertTrue(all(not c['round_findings'] for c in research))
        self.assertTrue(any(f['stage']=='Private round guidance' for f in run['payload']['diagnostics']['failures']))
        self.assertEqual(sum(j.get('evaluation_status')=='assessed' for j in self.store.jobs()),3)

    def test_initial_brief_cannot_forward_or_cache_a_raw_cv_echo(self):
        class EchoAI(fixtures.ScriptedAI):
            def run(inner,kind,task,context,**opts):
                result=super().run(kind,task,context,**opts)
                if kind=='session_brief':result['background']=[fixtures.CV]
                return result
        ai=EchoAI();run=self.store.start_run('codex')
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
            fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live source')))
        self.assertFalse(any(opts.get('research') for _,_,_,opts in ai.calls))
        self.assertIsNone(self.store.get('professional_background'))
        self.assertEqual(self.store.runs()[0]['status'],'failed')

    def test_later_observed_page_can_complete_a_previous_snippet_without_repeating_unchanged_work(self):
        store=self.store
        class SourceAI(fixtures.VerifiedScriptedAI):
            count=0
            def run(inner,kind,task,context,**opts):
                if kind=='research_guidance':
                    inner.telemetry={}
                    return dict(focus='Find observed employer requirements',transferable_capabilities=[],specialist_gaps=[],
                        unsuccessful_queries=[],missing_sources=['Employer duties'],next_queries=['Observed role employer requirements'],continue_research=True)
                result=super().run(kind,task,context,**opts)
                if kind=='research_v5':
                    inner.count+=1
                    result['jobs']=result['jobs'][:1];inner.telemetry['observations']=inner.telemetry['observations'][:1]
                    if inner.count==1:
                        inner.telemetry['observations'][0].pop('text')
                        inner.telemetry['observations'][0]['observation_kind']='search_snippet'
                    else:
                        self.assertTrue(context['source_gaps'])
                        self.assertEqual(context['source_gaps'][0]['id'],'linkedin:123456')
                    result.update(continue_research=inner.count==1,next_avenues=['Employer requirements'])
                return result
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.MARKETS[:1]})
        ai=SourceAI();run=store.start_run('codex')
        SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai,
            fetcher=PublicFetcher(store,request=lambda _:self.fail('No live source')))
        self.assertEqual(ai.count,2)
        self.assertEqual(len(store.jobs()),1)
        self.assertEqual(store.jobs()[0].get('evaluation_status'),'assessed')
        self.assertEqual(sum(k=='priority_v52' for k,_,_,_ in ai.calls),1)
        d=store.runs()[0]['payload']['diagnostics']
        self.assertEqual(d['triage']['selected'],1,'Repeated evidence review must not inflate unique candidate counts')
        self.assertEqual(d['verification']['selected'],1)

    def test_timestamps_and_tracking_changes_do_not_repeat_a_failed_packet(self):
        original={'source_observations':[{'url':'https://www.linkedin.com/jobs/view/123456?trk=first',
            'text':'Actually observed duties','at':'2026-10-01'}]}
        repeated=copy.deepcopy(original)
        repeated['source_observations'][0].update(url='https://linkedin.com/jobs/view/123456?trk=later',at='2026-10-15')
        self.assertEqual(evidence_version(original),evidence_version(repeated))
        repeated['source_observations'][0]['text']='New observed mandatory requirements'
        self.assertNotEqual(evidence_version(original),evidence_version(repeated))

    def test_application_history_excludes_only_the_exact_rediscovered_identity(self):
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.MARKETS[:1]})
        self.store.upsert_job({'id':'linkedin:123456','url':'https://www.linkedin.com/jobs/view/123456',
            'source':'LinkedIn','source_id':'123456','company':'Synthetic','title':'Architecture Lead','requisition_id':'REQ-42'})
        self.store.application('linkedin:123456','applied');self.store.fresh_session()
        ai=fixtures.VerifiedScriptedAI();run=self.store.start_run('codex')
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
            fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live source')))
        jobs={j['id']:j for j in self.store.jobs()}
        self.assertEqual(jobs['linkedin:123456']['application_status'],'applied')
        self.assertEqual(jobs['linkedin:123456']['requisition_id'],'REQ-42')
        sent=[j['id'] for k,_,c,_ in ai.calls if k in ('enrichment','priority_v52') for j in c['jobs']]
        self.assertNotIn('linkedin:123456',sent)
        self.assertIn('linkedin:123457',sent)
        self.assertEqual(jobs['linkedin:123457']['application_status'],'none')


if __name__=='__main__':unittest.main()
