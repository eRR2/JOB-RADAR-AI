"""Offline checks of the actual CLI request boundary, using synthetic data only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from job_radar_ai.contracts import SCHEMAS, validate
from job_radar_ai.providers import Provider, ProviderError, execution_error


def example(schema):
    if 'enum' in schema:
        return schema['enum'][0]
    kind = schema['type']
    if kind == 'object':
        return {key: example(schema['properties'][key]) for key in schema['required']}
    if kind == 'array':
        return []
    if kind == 'boolean':
        return False
    if isinstance(kind, list) and 'null' in kind:
        return None
    return 'DE' if schema.get('pattern') else ''


class ProviderContractTests(unittest.TestCase):
    def assert_strict(self, schema, path='$'):
        if isinstance(schema, dict):
            if schema.get('type') == 'object':
                self.assertEqual(set(schema['properties']), set(schema['required']), path)
                self.assertEqual(len(schema['required']), len(set(schema['required'])), path)
                self.assertIs(schema['additionalProperties'], False, path)
            for key, value in schema.items():
                self.assert_strict(value, path + '.' + key)
        elif isinstance(schema, list):
            for index, value in enumerate(schema):
                self.assert_strict(value, path + f'[{index}]')

    def test_every_nested_schema_sent_to_both_clis_is_strict(self):
        original = copy.deepcopy(SCHEMAS)
        with tempfile.TemporaryDirectory() as temp:
            for name in ('codex', 'claude'):
                for kind, local_schema in SCHEMAS.items():
                    with self.subTest(provider=name, contract=kind):
                        value = example(local_schema)

                        def process(command, *args, **kwargs):
                            if name == 'codex':
                                path = Path(command[command.index('--output-schema') + 1])
                                sent = json.loads(path.read_text(encoding='utf-8'))
                                result = Path(command[command.index('-o') + 1])
                                result.write_text(json.dumps(value), encoding='utf-8')
                            else:
                                sent = json.loads(command[command.index('--json-schema') + 1])
                            jsonschema.Draft202012Validator.check_schema(sent)
                            self.assertEqual(sent['type'], 'object')
                            self.assertNotIn('anyOf', sent)
                            self.assert_strict(sent)
                            return 0, json.dumps({'structured_output': value}), ''

                        with patch('job_radar_ai.providers.executable', return_value=[name + '.exe']), \
                             patch.object(Provider, 'status', return_value={'authenticated': True}), \
                             patch('job_radar_ai.providers.bounded_process', side_effect=process) as call:
                            self.assertEqual(Provider(name, Path(temp)).run(kind, 'Synthetic contract check', {}), value)
                            self.assertEqual(call.call_count, 1)
        self.assertEqual(SCHEMAS, original, 'Provider schemas must not mutate legacy validation')

    def test_saved_records_can_still_omit_new_findings_but_bad_values_fail(self):
        for kind, collection in [('research_v5', 'jobs'), ('priority_v52', 'assessments')]:
            value = example(SCHEMAS[kind])
            value[collection] = [example(SCHEMAS[kind]['properties'][collection]['items'])]
            self.assertEqual(validate(kind, value), value)
            invalid = copy.deepcopy(value)
            invalid[collection][0]['requisition_id' if kind == 'research_v5' else 'ruling_employer_support'] = 42
            with self.assertRaises(ValueError):
                validate(kind, invalid)

    def test_failed_cli_preserves_exit_and_safe_schema_details_without_retry(self):
        message = ("Invalid schema for response_format 'career': In context=('properties', 'jobs', 'items'), "
                   "'required' is required to be supplied and to be an array including every key in properties. "
                   "Missing 'requisition_id'.")
        output = '\n'.join([
            json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'PRIVATE_CV_MARKER'}}),
            json.dumps({'type': 'turn.failed', 'error': {'message': message}}),
        ])
        stderr = 'HTTP 400 Bad Request: invalid_json_schema\nPRIVATE_PROMPT_MARKER user@example.invalid token=secret-marker'
        with tempfile.TemporaryDirectory() as temp, \
             patch('job_radar_ai.providers.executable', return_value=['codex.exe']), \
             patch.object(Provider, 'status', return_value={'authenticated': True}), \
             patch('job_radar_ai.providers.bounded_process', return_value=(1, output, stderr)) as call:
            with self.assertRaises(ProviderError) as caught:
                Provider('codex', Path(temp)).run('research_v5', 'PRIVATE_PROMPT_MARKER', {'cv': 'PRIVATE_CV_MARKER'})
            error = caught.exception
            self.assertEqual(error.exit_code, 1)
            self.assertEqual(error.category, 'execution_error')
            self.assertIn('invalid_json_schema', str(error))
            self.assertIn('400', str(error))
            self.assertIn('properties.jobs.items', str(error))
            self.assertIn('requisition_id', str(error))
            for secret in ('PRIVATE_CV_MARKER', 'PRIVATE_PROMPT_MARKER', 'user@example.invalid', 'secret-marker'):
                self.assertNotIn(secret, str(error))
                self.assertNotIn(secret, repr(error.__dict__))
            self.assertEqual(call.call_count, 1)

    def test_unrecognized_output_is_withheld_and_agent_text_cannot_classify_errors(self):
        output = json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'usage limit PRIVATE_MARKER'}})
        error = execution_error(output, exit_code=7)
        self.assertEqual(error.category, 'execution_error')
        self.assertEqual(error.exit_code, 7)
        self.assertIn('exit code 7', str(error))
        self.assertNotIn('PRIVATE_MARKER', str(error))

    def test_schema_failure_details_are_detected_in_either_stream(self):
        for raw in [
            "HTTP 400 invalid_json_schema: In context=('properties', 'assessments', 'items'), Missing 'authority'.",
            json.dumps({'type': 'error', 'message': "Invalid schema: In context=('properties', 'assessments', 'items'), Missing 'authority'."}),
            json.dumps({'type': 'turn.failed', 'error': {'message': "invalid_json_schema: Missing 'ruling_quote'."}}),
        ]:
            with self.subTest(raw=raw):
                error = execution_error(raw, exit_code=1)
                self.assertEqual(error.category, 'execution_error')
                self.assertIn('Invalid Structured Outputs schema', str(error))
                self.assertIn(error.diagnostics['missing_required'], ('authority', 'ruling_quote'))

    def test_existing_failure_categories_keep_exit_code_and_never_echo_output(self):
        for raw, category in [('usage limit', 'subscription_usage_limit'), ('unsupported_model', 'model_access'),
                              ('rate_limit_exceeded', 'provider_rate_limit'), ('Connection failed', 'execution_error')]:
            with self.subTest(category=category):
                error = execution_error(raw + '\nPRIVATE_MARKER', exit_code=2)
                self.assertEqual(error.category, category)
                self.assertEqual(error.exit_code, 2)
                self.assertNotIn('PRIVATE_MARKER', str(error))

    def test_schema_diagnostics_only_expose_known_contract_fields(self):
        raw = ("invalid_json_schema In context=('properties', 'PRIVATE_NAME'), Missing 'PRIVATE_CONTACT'. "
               'https://private.example/?token=secret')
        error = execution_error(raw, exit_code=1)
        self.assertIn('invalid_json_schema', str(error))
        for secret in ('PRIVATE_NAME', 'PRIVATE_CONTACT', 'private.example', 'secret'):
            self.assertNotIn(secret, str(error))
            self.assertNotIn(secret, repr(error.__dict__))
