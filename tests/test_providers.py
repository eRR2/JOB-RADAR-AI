import json
import os
import tempfile
import threading
import unittest
import time
from unittest.mock import patch
from pathlib import Path
from job_radar_ai.providers import Provider, ProviderError, bounded_process
from job_radar_ai.contracts import SCHEMAS, validate


class ProviderTests(unittest.TestCase):
    @patch('job_radar_ai.providers.executable',return_value=['claude.exe'])
    def test_claude_subscription_auth_is_required_and_default_status_is_json(self,binary):
        with tempfile.TemporaryDirectory() as temp:
            provider=Provider('claude',Path(temp))
            for method,expected in [('claude.ai',True),('api_key',False),('api_key_helper',False),('third_party',False),('oauth_token',False),('unknown',False)]:
                with patch('job_radar_ai.providers.bounded_process',return_value=(0,json.dumps({'loggedIn':True,'authMethod':method}),'')) as process:
                    self.assertEqual(provider.status()['authenticated'],expected)
                    self.assertEqual(process.call_args.args[0],['claude.exe','auth','status'])
    @patch('job_radar_ai.providers.executable',return_value=['codex.exe'])
    @patch.object(Provider,'status',return_value={'authenticated':False,'status':'Subscription login required'})
    @patch('job_radar_ai.providers.bounded_process')
    def test_persisted_api_key_or_unknown_auth_never_starts_inference(self,process,status,binary):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ProviderError):
                Provider('codex',Path(temp)).run('probe','Ready?',{})
        process.assert_not_called()
    def test_plan_rejects_extra_fields_and_excessive_queries(self):
        with self.assertRaises(ValueError):
            validate('plan', {'shell': 'rm -rf'})

    def test_codex_restricted_command_has_no_browser_supplied_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Provider('codex', Path(temp))
            command = p.command(['codex.exe'], Path(temp)/'schema.json', False)
            self.assertIn('read-only', command)
            self.assertIn('--ignore-user-config', command)
            self.assertIn('features.shell_tool=false', command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)

    def test_claude_tools_are_explicitly_restricted(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Provider('claude', Path(temp))
            command = p.command(['claude.exe'], Path(temp)/'schema.json', True, SCHEMAS['plan'])
            self.assertEqual(command[command.index('--tools')+1], 'WebSearch,WebFetch')
            self.assertIn('--strict-mcp-config', command)
            self.assertNotIn('--dangerously-skip-permissions', command)

    def test_process_timeout_and_cancel(self):
        import sys
        launched=[]
        with self.assertRaises(ProviderError):
            bounded_process([sys.executable, '-c', 'import time; time.sleep(5)'], timeout=.1,on_started=lambda:launched.append(True))
        self.assertEqual(launched,[True])
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ProviderError):
            bounded_process([sys.executable, '-c', 'print(1)'], cancel=stop,on_started=lambda:launched.append(True))
        self.assertEqual(launched,[True])

    def test_cancel_terminates_an_already_running_process(self):
        import sys
        stop=threading.Event();timer=threading.Timer(.15,stop.set);timer.start()
        started=time.monotonic()
        try:
            with self.assertRaisesRegex(ProviderError,'Canceled'):
                bounded_process([sys.executable,'-c','import time;time.sleep(20)'],cancel=stop)
            self.assertLess(time.monotonic()-started,3)
        finally:
            timer.join()

    @unittest.skipUnless(os.name == 'nt', 'Windows process termination')
    def test_denied_tree_termination_still_cancels_owned_process(self):
        import sys
        import subprocess
        stop=threading.Event()
        with patch('job_radar_ai.providers.subprocess.run',return_value=subprocess.CompletedProcess([],1)):
            started=time.monotonic()
            with self.assertRaisesRegex(ProviderError,'Canceled'):
                bounded_process([sys.executable,'-c','import time;time.sleep(20)'],cancel=stop,
                                on_started=lambda:stop.set())
            self.assertLess(time.monotonic()-started,3)

    def test_claude_error_is_not_success(self):
        with self.assertRaises(ProviderError):
            Provider.parse_claude(json.dumps({'is_error': True, 'result': 'usage limit'}))

    def test_malformed_and_missing_structured_output_are_refused(self):
        with self.assertRaises(ProviderError):
            Provider.parse_claude(json.dumps({'result': 'I did the work'}))

