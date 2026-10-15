"""Offline workload admission with measured latency, no live inference."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import test_clean_search as fixtures
from test_review_pipeline import ReviewAI
from job_radar_ai import session_search
from job_radar_ai.providers import Provider,ProviderError
from job_radar_ai.recommendations import private_profile
from job_radar_ai.verification import triage_batches,triage_output_size


class ProviderLatencyTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def test_combined_private_input_and_output_bounds_shrink_a_heavy_packet(self):
        jobs=[dict(id=str(i),title='Systems owner',source_observations=[{'text':'Observed duties. '*30}]) for i in range(8)]
        groups=list(triage_batches(jobs,shared_chars=27000))
        self.assertTrue(all(len(g)<=2 for g in groups))
        self.assertEqual([j['id'] for g in groups for j in g],[str(i) for i in range(8)])
        self.assertTrue(all(27000+len(json.dumps(g))+2*triage_output_size(g)<=35000 for g in groups))

    def test_measured_two_job_latency_reaches_sources_and_assessment_without_short_calls(self):
        profile=copy.deepcopy(fixtures.PROFILE);profile['markets']=fixtures.MARKETS[:1]
        profile['objectives']=''
        brief=dict(background=['Electrical systems architecture and team leadership'],direction='Broader technical ownership',country_preferences=[])
        overhead=len(json.dumps({'profile':private_profile(profile),'background':brief,'jobs':[]}))+len(session_search.ENRICH)+2000
        profile['objectives']='x'*(26000-overhead)
        self.store.set('profile',profile)
        clock=[0.0];packets=[];limits=[];source_seconds=[0.0]
        class LatencyAI(ReviewAI):
            def run(inner,kind,task,context,**opts):
                if kind=='enrichment':
                    packets.append(tuple(j['id'] for j in context['jobs']));limits.append(opts['timeout'])
                    # The one private probe completed two jobs in 15.39 seconds.
                    # Larger packets model the retained 30-second failures.
                    delay=15.39 if len(context['jobs'])<=2 else 45.39
                    clock[0]+=min(delay,opts['timeout'])
                    if delay>opts['timeout']:
                        raise ProviderError('Controlled provider latency.','time_window')
                elif kind=='priority_v52':clock[0]+=4
                return super().run(kind,task,context,**opts)
        actual=session_search.recover_page
        def recover(*args,**kwargs):
            clock[0]+=4;source_seconds[0]+=4
            return actual(*args,**kwargs)
        run=self.store.start_run('codex');ai=LatencyAI()
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]),patch('job_radar_ai.session_search.recover_page',side_effect=recover):
            session_search.SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
                fetcher=session_search.PublicFetcher(self.store,request=lambda _:self.fail('No live publisher')))
        jobs=self.store.jobs();d=self.store.runs()[0]['payload']['diagnostics']
        self.assertTrue(any(j.get('evaluation_status')=='assessed' for j in jobs))
        self.assertTrue(all(len(p)<=2 for p in packets))
        self.assertTrue(all(20<=v<=30 for v in limits),'Do not launch a window shorter than the measured response envelope')
        self.assertEqual(len(packets),len(set(packets)),'No retry of an unchanged packet')
        self.assertEqual(len(jobs),24)
        self.assertGreater(source_seconds[0],0)
        self.assertLessEqual(d['phase_spent']['enrichment']-source_seconds[0],90)
        self.assertLessEqual(d['phase_spent']['enrichment'],150)
        self.assertLessEqual(clock[0],900)
        self.assertEqual(self.store.runs()[0]['status'],'partial','Deferred candidates remain visible')

    def test_guidance_uses_prior_capability_brief_without_repeating_raw_cv(self):
        class AI(fixtures.VerifiedScriptedAI):
            def run(inner,kind,task,context,**opts):
                if kind=='research_guidance':
                    self.assertNotIn('cv_text',context['profile'])
                    self.assertTrue(context['background']['background'])
                    self.assertTrue(context['findings'])
                if kind in ('enrichment','priority_v52'):
                    self.assertEqual(context['profile']['cv_text'],fixtures.CV)
                return super().run(kind,task,context,**opts)
        ai=AI();run=self.store.start_run('codex')
        session_search.SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
            fetcher=session_search.PublicFetcher(self.store,request=lambda _:self.fail('No live publisher')))
        self.assertEqual([k for k,_,_,_ in ai.calls].count('research_v5'),2)

    def test_guidance_bounds_findings_and_reports_whole_round_coverage(self):
        seen=[]
        class AI(ReviewAI):
            def run(inner,kind,task,context,**opts):
                if kind=='research_guidance':
                    seen.append(context)
                result=super().run(kind,task,context,**opts)
                if kind=='research_v5':
                    result['jobs']=result['jobs'][:12]
                    inner.telemetry['observations']=inner.telemetry['observations'][:12]
                return result
        ai=AI();run=self.store.start_run('codex')
        session_search.SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
            fetcher=session_search.PublicFetcher(self.store,request=lambda _:self.fail('No live publisher')))
        self.assertTrue(seen)
        self.assertLessEqual(len(seen[0]['findings']),8)
        self.assertEqual(seen[0]['round_summary']['candidates'],12)
        self.assertEqual(seen[0]['round_summary']['assessed'],12)
        self.assertNotIn('cv_text',seen[0]['profile'])

    def test_timeout_telemetry_reports_stage_and_safe_wire_sizes_without_content(self):
        secret='Synthetic private CV and prompt must not be logged.'
        def stalled(argv,prompt,**opts):
            opts['on_started']();opts['on_line'](json.dumps({'type':'thread.started'}))
            opts['on_line'](json.dumps({'type':'turn.started'}))
            raise ProviderError('Controlled timeout','time_window')
        with tempfile.TemporaryDirectory() as temp,patch('job_radar_ai.providers.executable',return_value=['codex.exe']),patch.object(Provider,'status',return_value={'authenticated':True}),patch('job_radar_ai.providers.bounded_process',side_effect=stalled):
            provider=Provider('codex',Path(temp))
            with self.assertRaises(ProviderError):provider.run('enrichment',secret,{'jobs':[]},timeout=30)
            d=provider.telemetry
            self.assertEqual(d.get('stage'),'awaiting_response')
            self.assertGreater(d['wire']['prompt_utf8_bytes'],len(secret))
            self.assertEqual(d['wire']['reasoning_requested'],'low')
            self.assertEqual(d['wire']['model_requested'],'cli_default_unrecorded')
            self.assertNotIn(secret,json.dumps(d))
            self.assertEqual([v['type'] for v in d['timeline']],['thread.started','turn.started'])

    def test_guidance_reasoning_is_explicit_and_output_validation_has_its_own_stage(self):
        commands=[]
        def invalid(argv,*args,**kwargs):
            commands.append(argv)
            Path(argv[argv.index('-o')+1]).write_text('{}',encoding='utf-8')
            return 0,'',''
        with tempfile.TemporaryDirectory() as temp,patch('job_radar_ai.providers.executable',return_value=['codex.exe']),patch.object(Provider,'status',return_value={'authenticated':True}),patch('job_radar_ai.providers.bounded_process',side_effect=invalid):
            provider=Provider('codex',Path(temp))
            with self.assertRaises(ProviderError):provider.run('research_guidance','Synthetic private direction',{})
            self.assertIn('model_reasoning_effort="low"',commands[0])
            self.assertEqual(provider.telemetry.get('stage'),'output_validation')

    def test_deferred_unattempted_packets_resume_in_next_country_without_retrying_failed_ids(self):
        profile=copy.deepcopy(fixtures.PROFILE);profile['objectives']=''
        brief=dict(background=['Electrical systems architecture and team leadership'],direction='Broader technical ownership',country_preferences=[])
        overhead=len(json.dumps({'profile':private_profile(profile),'background':brief,'jobs':[]}))+len(session_search.ENRICH)+2000
        profile['objectives']='x'*(26000-overhead);self.store.set('profile',profile)
        clock=[0.0];packets=[];countries=[]
        class AI(ReviewAI):
            def run(inner,kind,task,context,**opts):
                if kind=='research_v5':
                    countries.append(context['market']['id'])
                    if len(countries)>1:
                        inner.calls.append((kind,task,context,opts));inner.telemetry={'web_calls':1,'observations':[]}
                        return dict(jobs=[],summary='No new fixture jobs',limitations=[],continue_research=False,next_avenues=[])
                if kind=='enrichment':
                    packets.append(tuple(j['id'] for j in context['jobs']))
                    if len(packets)==1:
                        clock[0]+=opts['timeout'];raise ProviderError('First packet timeout','time_window')
                    clock[0]+=15.39
                return super().run(kind,task,context,**opts)
        run=self.store.start_run('codex');ai=AI()
        with patch('job_radar_ai.session_search.time.monotonic',side_effect=lambda:clock[0]):
            session_search.SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,
                fetcher=session_search.PublicFetcher(self.store,request=lambda _:self.fail('No live publisher')))
        jobs=self.store.jobs()
        self.assertEqual(countries,['DE','NL'])
        self.assertGreater(len(packets),1)
        self.assertEqual(packets.count(packets[0]),1)
        self.assertTrue(all(j.get('triage_review',{}).get('reason')=='triage_timeout' for j in jobs if j['id'] in packets[0]))
        self.assertTrue(any(j.get('evaluation_status')=='assessed' for j in jobs))
        self.assertEqual(len(jobs),24)

    def test_cli_error_notice_retains_only_safe_category_and_never_private_text(self):
        secret='Synthetic private provider text'
        def process(argv,*args,**opts):
            opts['on_started']()
            opts['on_line'](json.dumps({'type':'item.completed','item':{'type':'error','message':'HTTP 429 rate_limit_exceeded '+secret}}))
            Path(argv[argv.index('-o')+1]).write_text(json.dumps({'status':'ready','message':'Synthetic'}),encoding='utf-8')
            return 0,'',''
        with tempfile.TemporaryDirectory() as temp,patch('job_radar_ai.providers.executable',return_value=['codex.exe']),patch.object(Provider,'status',return_value={'authenticated':True}),patch('job_radar_ai.providers.bounded_process',side_effect=process):
            provider=Provider('codex',Path(temp));provider.run('probe','Synthetic',{})
            self.assertEqual(provider.telemetry['cli_notices'][0]['category'],'provider_rate_limit')
            self.assertEqual(provider.telemetry['cli_notices'][0]['http_status'],429)
            self.assertNotIn(secret,json.dumps(provider.telemetry))
            self.assertEqual(provider.telemetry['stage'],'validated','A nonfatal startup notice is distinct from an unsuccessful result')


if __name__=='__main__':unittest.main()
