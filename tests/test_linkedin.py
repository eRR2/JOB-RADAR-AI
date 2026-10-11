import tempfile
import threading
from datetime import datetime, timezone
import unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.store import Store
from job_radar_ai.linkedin import LinkedIn, SourceError


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'state.sqlite3')
        self.source = LinkedIn(Path('.'), self.store, threading.Event(), {'requests': 3, 'spacing': 0})

    def tearDown(self):
        self.temp.cleanup()

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(1, '', '{"error":"ACCESS_RESTRICTED HTTP 429"}'))
    def test_restriction_latches_across_instances_without_retry(self, process, binary):
        with self.assertRaises(SourceError):
            self.source.search({'query': 'Synthetic', 'location': 'Example', 'remote': 'any'}, 1)
        other = LinkedIn(Path('.'), self.store, threading.Event(), {'requests': 3, 'spacing': 0})
        with self.assertRaises(SourceError):
            other.search({'query': 'Other', 'location': 'Example', 'remote': 'any'}, 1)
        self.assertEqual(process.call_count, 1)

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(0, '{"results":[],"meta":{"count":0,"page":1}}', ''))
    def test_valid_empty_is_cached_separately_from_failure(self, process, binary):
        query = {'query': 'Synthetic', 'location': 'Example', 'remote': 'any'}
        self.assertEqual(self.source.search(query, 1), [])
        self.assertEqual(self.source.search(query, 1), [])
        self.assertEqual(process.call_count, 1)
        self.assertEqual(self.source.cache_hits, 1)

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(0, '{"results":[]}', ''))
    def test_cache_read_does_not_extend_source_freshness(self, process, binary):
        query={'query':'Synthetic','location':'Example','remote':'any'}
        self.source.search(query)
        with self.store.db() as db:
            key=db.execute('SELECT key FROM cache').fetchone()[0]
            db.execute('UPDATE cache SET at=? WHERE key=?',('2099-01-01T00:00:00+00:00',key))
        self.source.search(query)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT at FROM cache WHERE key=?',(key,)).fetchone()[0],'2099-01-01T00:00:00+00:00')

    def test_pending_request_from_crashed_process_blocks_next_source(self):
        self.store.set('linkedin_pending', True)
        with self.assertRaises(SourceError):
            self.source.search({'query': 'Synthetic', 'location': 'Example', 'remote': 'any'}, 1)

    def test_untrusted_id_cannot_be_a_cli_flag_or_external_url(self):
        with self.assertRaises(ValueError):
            self.source.detail('https://evil.invalid/123456789')
        with self.assertRaises(ValueError):
            self.source.detail('--help')

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(0, '{"id":"123456","description":"Incomplete"}', ''))
    def test_incomplete_description_is_not_cached_as_success(self, process, binary):
        with self.assertRaises(SourceError):
            self.source.detail('123456')
        self.assertIsNone(self.store.cached('linkedin:detail:123456',86400))
        self.assertIsNone(self.store.get('linkedin_last_success'))

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(0, '{"results":[]}', ''))
    def test_minimum_spacing_survives_a_new_instance(self, process, binary):
        self.store.set('linkedin_last_attempt',datetime.now(timezone.utc).isoformat())
        source=LinkedIn(Path('.'),self.store,threading.Event(),{'requests':3,'spacing':5})
        with patch.object(source.cancel,'wait',return_value=False) as wait:
            source.search({'query':'Synthetic','location':'Example','remote':'any'})
        self.assertGreater(wait.call_args.args[0],4.5)
        self.assertLessEqual(wait.call_args.args[0],5)

    @patch('job_radar_ai.linkedin.executable', return_value=['bun.exe'])
    @patch('job_radar_ai.linkedin.bounded_process', return_value=(0, '{"results":[{"id":"--help","title":"Synthetic"}]}', ''))
    def test_invalid_search_identity_is_never_cached(self, process, binary):
        with self.assertRaises(SourceError):
            self.source.search({'query':'Synthetic','location':'Example','remote':'any'})
        self.assertIsNone(self.store.get('linkedin_last_success'))
        with self.store.db() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM cache').fetchone()[0],0)
