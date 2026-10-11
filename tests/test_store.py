import tempfile
import unittest
from pathlib import Path
from job_radar_ai.store import Store, normalize_weights


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_weights_are_normalized_and_zero_refused(self):
        self.assertAlmostEqual(sum(normalize_weights({'a': 2, 'b': 3}).values()), 100)
        with self.assertRaises(ValueError):
            normalize_weights({'a': 0})

    def test_identity_and_application_history_survive_rediscovery_and_restart(self):
        job = {'id': 'linkedin:123456789', 'title': 'Synthetic lead', 'url': 'https://www.linkedin.com/jobs/view/123456789', 'company': 'Example', 'description': 'Synthetic job'}
        self.assertTrue(self.store.upsert_job(job))
        for status in ['saved', 'applied', 'rejected']:
            self.store.application(job['id'], status)
        self.assertFalse(self.store.upsert_job({**job, 'title': 'Updated'}))
        reopened = Store(self.path)
        found = reopened.jobs()[0]
        self.assertEqual(found['application_status'], 'rejected')
        self.assertEqual([e['status'] for e in found['events']], ['saved', 'applied', 'rejected'])
        self.assertEqual(reopened.feedback(), [])

    def test_multiple_feedback_reasons_are_separate_from_application_outcomes(self):
        self.store.upsert_job({'id': 'linkedin:123456', 'title': 'Synthetic', 'url': 'https://www.linkedin.com/jobs/view/123456'})
        self.store.add_feedback('linkedin:123456', 'dislike', ['too junior', 'wrong sector'], 'One-off')
        self.store.application('linkedin:123456', 'rejected')
        self.assertEqual(self.store.feedback()[0]['reasons'], ['too junior', 'wrong sector'])
        self.assertEqual(len(self.store.feedback()), 1)

    def test_corrupt_established_database_is_not_replaced(self):
        bad = Path(self.temp.name) / 'bad.sqlite3'
        bad.write_bytes(b'not a database')
        with self.assertRaises(Exception):
            Store(bad)
        self.assertEqual(bad.read_bytes(), b'not a database')

    def test_run_overlap_has_persisted_skipped_outcome(self):
        first = self.store.start_run('codex')
        self.assertIsNotNone(first)
        self.assertIsNone(self.store.start_run('codex'))
        self.assertEqual(self.store.runs()[0]['status'], 'skipped')
