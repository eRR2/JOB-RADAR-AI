import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.providers import Provider, ProviderError


class ProviderObservationTests(unittest.TestCase):
    def test_timeout_preserves_observed_events_and_real_usage(self):
        def process(argv,*args,**kwargs):
            callback=kwargs['on_line']
            callback(json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'queries':['Synthetic leadership Germany']},'results':[{'url':'https://linkedin.com/jobs/view/123456','title':'Observed vacancy','snippet':'Actual source evidence'}]}}))
            callback(json.dumps({'type':'turn.completed','usage':{'input_tokens':42}}))
            raise ProviderError('AI/tool time limit reached.','time_window')
        with tempfile.TemporaryDirectory() as tmp,patch('job_radar_ai.providers.executable',return_value=['codex.exe']),patch.object(Provider,'status',return_value={'authenticated':True}),patch('job_radar_ai.providers.bounded_process',side_effect=process):
            provider=Provider('codex',tmp)
            with self.assertRaises(ProviderError):provider.run('research_v5','Discovery',{},research=True)
            self.assertEqual(provider.telemetry['observations'][0]['title'],'Observed vacancy')
            self.assertEqual(provider.telemetry['usage']['input_tokens'],42)

    def test_real_event_fields_are_retained_and_model_claims_are_separate(self):
        def process(argv,*args,**kwargs):
            callback=kwargs['on_line']
            callback(json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'type':'search','queries':['Synthetic roles France']},'results':[{'type':'text_result','url':'https://employer.example/job','title':'Synthetic role','snippet':'Actual tool snippet France','private_other_field':'not retained'}]}}))
            callback(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':40,'output_tokens':20,'invented_cost':99}}))
            schema=Path(argv[argv.index('--output-schema')+1])
            (schema.parent/'result.json').write_text(json.dumps({'jobs':[],'summary':'Model prose claiming imaginary work','limitations':[],'continue_research':False,'next_avenues':[]}),encoding='utf-8')
            return 0,'',''
        with tempfile.TemporaryDirectory() as tmp, patch('job_radar_ai.providers.executable',return_value=['codex.exe']),patch.object(Provider,'status',return_value={'authenticated':True}),patch('job_radar_ai.providers.bounded_process',side_effect=process):
            provider=Provider('codex',tmp)
            provider.run('research_v5','Research',{},research=True)
            self.assertEqual(provider.telemetry['web_calls'],1)
            self.assertEqual(provider.telemetry['observations'][0]['snippet'],'Actual tool snippet France')
            self.assertNotIn('private_other_field',provider.telemetry['observations'][0])
            self.assertNotIn('Model prose',str(provider.telemetry))
            self.assertEqual(provider.telemetry['usage'],{'input_tokens':100,'cached_input_tokens':40,'output_tokens':20})
            self.assertEqual(provider.telemetry['observations'][0]['observation_kind'],'search_snippet')
