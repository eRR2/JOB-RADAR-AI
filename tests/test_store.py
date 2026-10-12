import tempfile
import unittest
import sqlite3
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

    def test_changed_description_retains_prior_assessment_until_replacement(self):
        job={'id':'linkedin:123456','title':'Synthetic','description':'Original responsibilities'}
        self.store.upsert_job(job)
        self.store.evaluate(job['id'],{'recommend':True,'summary':'Original analysis'})
        self.store.upsert_job({**job,'description':'Changed responsibilities'})
        self.assertEqual(self.store.jobs()[0]['evaluation']['summary'],'Original analysis')

    def test_search_only_rediscovery_preserves_closed_banner_evidence(self):
        self.store.upsert_job({'id':'linkedin:123456','title':'Synthetic','description':'Original responsibilities',
                               'description_obtained':'2026-01-01T00:00:00+00:00','availability':'closed_banner_observed','isActive':False,'evidence':'Closed banner in full description'})
        self.store.upsert_job({'id':'linkedin:123456','title':'Synthetic','availability':'unknown','evidence':'Observed in search'})
        job=Store(self.path).jobs()[0]
        self.assertEqual(job['availability'],'closed_banner_observed')
        self.assertEqual(job['evidence'],'Closed banner in full description')

    def test_fresh_description_can_replace_old_closed_observation_with_unknown(self):
        self.store.upsert_job({'id':'linkedin:123456','availability':'closed_banner_observed'})
        self.store.upsert_job({'id':'linkedin:123456','availability':'unknown','description':'Fresh description',
                               'description_obtained':'2026-01-02T00:00:00+00:00'})
        self.assertEqual(self.store.jobs()[0]['availability'],'unknown')

    def test_consistent_backup_restores_history(self):
        self.store.upsert_job({'id':'linkedin:123456','title':'Synthetic'})
        self.store.application('linkedin:123456','applied')
        path=Path(self.temp.name)/'backup.sqlite3'
        self.store.backup(path)
        self.assertEqual(Store(path).jobs()[0]['events'][0]['status'],'applied')

    def test_transaction_failure_rolls_back_partial_state(self):
        self.store.set('sentinel','before')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db() as db:
                db.execute('UPDATE settings SET value=? WHERE key=?',('"after"','sentinel'))
                db.execute("INSERT INTO application_events(job_id,status,at) VALUES ('missing','applied','synthetic')")
        self.assertEqual(Store(self.path).get('sentinel'),'before')
