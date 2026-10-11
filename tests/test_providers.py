import json
import tempfile
import threading
import unittest
from pathlib import Path
from job_radar_ai.providers import Provider, ProviderError, bounded_process
from job_radar_ai.contracts import SCHEMAS, validate


class ProviderTests(unittest.TestCase):
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
        with self.assertRaises(ProviderError):
            bounded_process([sys.executable, '-c', 'import time; time.sleep(5)'], timeout=.1)
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ProviderError):
            bounded_process([sys.executable, '-c', 'print(1)'], cancel=stop)

    def test_claude_error_is_not_success(self):
        with self.assertRaises(ProviderError):
            Provider.parse_claude(json.dumps({'is_error': True, 'result': 'usage limit'}))

    def test_malformed_and_missing_structured_output_are_refused(self):
        with self.assertRaises(ProviderError):
            Provider.parse_claude(json.dumps({'result': 'I did the work'}))
