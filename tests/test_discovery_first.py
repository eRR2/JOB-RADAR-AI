import copy,json,threading,unittest
from unittest.mock import patch
import test_clean_search as fixtures
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.sources import PublicFetcher
from job_radar_ai.providers import ProviderError
from job_radar_ai.markets import query_locations
from job_radar_ai.linkedin import LinkedIn,SourceError
from job_radar_ai.session_search import initial_plan

ScriptedAI=fixtures.ScriptedAI
PROFILE,CV=fixtures.PROFILE,fixtures.CV


class DiscoveryFirstTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def run_search(self,ai,market='all'):
        token,_=self.store.fresh_session();store=self.store.bound(token);run=store.start_run('codex')
        store.set('budgets',{'spacing':0})  # Synthetic transport responses never need wall-clock waits.
        fetch=PublicFetcher(store,request=lambda _:self.fail('Unexpected source request'))
        SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai,fetcher=fetch,market_id=market)
        return self.store.runs()[0]['payload']

    def test_all_markets_discovery_precedes_enrichment_and_evaluation(self):
        ai=ScriptedAI();payload=self.run_search(ai)
        stages=[k for k,_,_,_ in ai.calls]
        discoveries=[i for i,k in enumerate(stages) if k=='research_v5']
        self.assertLess(max(discoveries),stages.index('enrichment'))
        self.assertLess(max(discoveries),stages.index('priority_v52'))
        self.assertEqual({c['market']['id'] for k,_,c,_ in ai.calls if k=='research_v5'},{'DE','NL'})
        self.assertNotIn('session_strategy',stages)
        self.assertEqual(stages.count('session_brief'),1)
        self.assertLess(stages.index('session_brief'),min(discoveries))
        self.assertGreater(payload['diagnostics']['counts']['duplicates'],0)

    def test_selected_market_only_and_start_forwards_selection(self):
        ai=ScriptedAI();self.run_search(ai,'DE')
        self.assertEqual({c['market']['id'] for k,_,c,_ in ai.calls if k=='research_v5'},{'DE'})
        token,_=self.store.fresh_session()
        with patch('job_radar_ai.session_search.threading.Thread') as thread:
            SessionSearch(self.root,self.store.bound(token)).start('NL')
            self.assertEqual(thread.call_args.kwargs['kwargs']['market_id'],'NL')

    def test_direct_linkedin_is_invoked_and_429_does_not_stop_indexed_research(self):
        self.store.set('profile',{**copy.deepcopy(PROFILE),'linkedin_consent':True})
        ai=ScriptedAI()
        failure=json.dumps({'error':'ACCESS_RESTRICTED HTTP 429','http_status':429})
        with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']),patch('job_radar_ai.linkedin.bounded_process',return_value=(1,'',failure)) as transport:
            payload=self.run_search(ai)
        transport.assert_called_once()
        self.assertEqual(payload['diagnostics']['linkedin_direct'][0]['http_status'],429)
        self.assertEqual({c['market']['id'] for k,_,c,_ in ai.calls if k=='research_v5'},{'DE','NL'})
        self.assertTrue(self.store.jobs())

    def test_timeout_retains_discoveries_and_call_diagnostics(self):
        class TimeoutAI(ScriptedAI):
            def run(self,kind,task,context,**opts):
                if kind=='priority_v52':
                    self.telemetry={}
                    raise ProviderError('AI/tool time limit reached; no automatic retry.','time_window')
                return super().run(kind,task,context,**opts)
        payload=self.run_search(TimeoutAI())
        self.assertEqual(len(self.store.jobs()),2)
        d=payload['diagnostics'];self.assertEqual(d['stop']['phase'],'evaluation')
        self.assertEqual(d['ai_calls'][-1]['timeout_category'],'provider_call_timeout')
        self.assertNotIn(CV,json.dumps(d));self.assertGreaterEqual(d['elapsed_seconds'],0)

    def test_brief_reused_when_knowledge_unchanged(self):
        self.run_search(ScriptedAI());ai=ScriptedAI();self.run_search(ai)
        self.assertFalse(any(k=='session_brief' for k,_,_,_ in ai.calls))
        self.assertEqual(self.store.get('profile'),PROFILE);self.assertEqual(self.store.get('cv_text'),CV)

    def test_direct_success_details_and_exact_metadata_are_saved(self):
        self.store.set('profile',{**copy.deepcopy(PROFILE),'linkedin_consent':True})
        class PlannedAI(ScriptedAI):
            def run(self,kind,task,context,**opts):
                if kind=='session_strategy':
                    self.telemetry={}
                    return dict(strategy='Actual capabilities',role_families=['Systems ownership'],markets=[dict(market_id=m['id'],linkedin_queries=[dict(query='technical ownership',location=query_locations(m)[0],remote='any',reason='Evidence')],web_queries=['Employer careers '+m['country']]) for m in context['markets']])
                if kind=='enrichment':return dict(candidate_ids=[j['id'] for j in context['jobs'] if j['id']=='linkedin:123456'],reason='Source responsibilities support actual capabilities')
                return super().run(kind,task,context,**opts)
        def response(argv,**opts):
            if 'search' in argv:
                location=argv[argv.index('--location')+1];germany='Germany' in location
                return 0,json.dumps({'results':[dict(id='123456' if germany else '123458',title='Architecture Lead',company='Synthetic',location=location)]}),''
            self.assertIn('123456',argv)
            return 0,json.dumps(dict(id='123456',title='Architecture Lead',company='Synthetic',location='Berlin, Germany',description='Own electrical system architecture. '+('Actual responsibilities and ownership. '*8))),''
        with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']),patch('job_radar_ai.linkedin.bounded_process',side_effect=response) as transport:
            payload=self.run_search(PlannedAI())
        jobs={j['id']:j for j in self.store.jobs()}
        self.assertEqual(jobs['linkedin:123458']['country'],'Netherlands')
        self.assertEqual(jobs['linkedin:123456']['description_source']['kind'],'linkedin')
        self.assertEqual(jobs['linkedin:123457'].get('shortlist_status'),'low_relevance')
        self.assertFalse(jobs['linkedin:123457'].get('preliminary',{}).get('recommend',False))
        self.assertFalse(any(r.get('job_id')=='linkedin:123457' for r in payload['diagnostics']['linkedin_direct']))
        self.assertEqual(transport.call_count,3)
        self.assertEqual(payload['requests'],3)

    def test_discovery_timeout_keeps_actual_tool_evidence_and_other_market_runs(self):
        class TimeoutDiscovery(ScriptedAI):
            def run(self,kind,task,context,**opts):
                if kind=='research_v5' and context['market']['id']=='DE':
                    self.calls.append((kind,task,context,opts))
                    self.telemetry={'web_calls':1,'observations':[dict(url='https://linkedin.com/jobs/view/123450?trk=search',title='Observed architecture opportunity',snippet='Actual indexed vacancy evidence')],'actions':[{'queries':['Systems leadership Germany']}],'usage':{'input_tokens':42}}
                    raise ProviderError('AI/tool time limit reached.','time_window')
                return super().run(kind,task,context,**opts)
        ai=TimeoutDiscovery();payload=self.run_search(ai)
        self.assertIn('linkedin:123450',[j['id'] for j in self.store.jobs()])
        self.assertEqual(sum(k=='research_v5' and c['market']['id']=='DE' for k,_,c,_ in ai.calls),1)
        self.assertTrue(any(k=='research_v5' and c['market']['id']=='NL' for k,_,c,_ in ai.calls))
        self.assertEqual(payload['usage']['reported_tokens']['input_tokens'],42)
        self.assertEqual(payload['diagnostics']['failures'][0]['phase'],'discovery')

    def test_linkedin_phase_deadline_never_starts_late_request(self):
        source=LinkedIn(self.root,self.store,threading.Event(),{'requests':8,'spacing':0})
        source.deadline=0
        with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']),patch('job_radar_ai.linkedin.bounded_process') as process:
            with self.assertRaisesRegex(SourceError,'phase budget'):source.invoke(['search'],'synthetic',0)
            process.assert_not_called()
        self.assertIsNone(self.store.get('linkedin_pending'))

    def test_direct_discoveries_exist_before_first_ai_call_and_survive_failure(self):
        profile={**copy.deepcopy(PROFILE),'linkedin_consent':True,'intent':{'summary':'Technical ownership','preferences':[dict(topic='career_direction',value='Systems leadership',scope='',origin='explicit')]}}
        self.store.set('profile',profile)
        class FailedAI(ScriptedAI):
            def run(inner,kind,task,context,**opts):
                self.assertEqual(kind,'session_brief')
                self.assertEqual(len(self.store.jobs()),1)
                inner.telemetry={'cli_started':True,'event_count':2,'event_types':{'thread.started':1,'turn.started':1}}
                raise ProviderError('CLI execution failed.','execution_error')
        failure=FailedAI()
        result=json.dumps({'results':[dict(id='123460',title='Observed role',company='Synthetic',location='Berlin, Germany')]})
        with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']),patch('job_radar_ai.linkedin.bounded_process',return_value=(0,result,'')):
            payload=self.run_search(failure)
        self.assertEqual(len(self.store.jobs()),1)
        self.assertEqual(payload['diagnostics']['stop']['phase'],'discovery')
        self.assertEqual(payload['diagnostics']['ai_calls'][0]['cli_events']['event_types']['turn.started'],1)
        self.assertEqual(payload['usage']['ai_invocations'],1)
        self.assertEqual(self.store.get('profile'),profile)

    def test_initial_queries_use_saved_intent_and_exact_confirmed_locations(self):
        profile={**copy.deepcopy(PROFILE),'intent':{'summary':'Unused summary','preferences':[dict(topic='career_direction',value='Systems ownership; Technical leadership',scope='',origin='explicit'),dict(topic='management_progression',value='Architecture team leadership',scope='NL',origin='explicit')]}}
        plan=initial_plan(profile,profile['markets'])
        de,nl=plan['markets']
        self.assertEqual({q['query'] for q in de['linkedin_queries']},{'Systems ownership','Technical leadership'})
        self.assertIn('Architecture team leadership',{q['query'] for q in nl['linkedin_queries']})
        for m,p in zip(profile['markets'],plan['markets']):self.assertEqual({q['location'] for q in p['linkedin_queries']},set(query_locations(m)))

