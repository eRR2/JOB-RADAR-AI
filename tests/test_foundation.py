"""Synthetic regressions for identity, durable state and decision evidence."""
import copy
import tempfile
import unittest
from pathlib import Path

from job_radar_ai.history import same_posting
from job_radar_ai.outlook_history import match_outlook_messages
from job_radar_ai.store import Store
from job_radar_ai.recommendations import assess, prepare, context
from job_radar_ai.observations import observed_job

CV = 'Led electrical architecture and technical integration.'
JOB = dict(id='web:first', url='https://careers.example/jobs/101', company='Company Alpha',
           title='Lead Systems Architect', location='City A', requisition_id='101',
           source='Public web research', description='Own system architecture. Work 35 hours per week.')
DECISION = dict(job_id=JOB['id'], category='direct', recommend=True, priority='strong',
                next_step='System ownership builds on demonstrated architecture experience.',
                critical_gap=False, gaps=[], evidence=[dict(requirement='Architecture',
                job_quote='Own system architecture.', cv_quote='Led electrical architecture',
                assessment='Direct responsibility evidence')])


class IdentityRegressions(unittest.TestCase):
    def test_observed_requisition_is_retained_only_with_exact_source_support(self):
        candidate = dict(url=JOB['url'], title=JOB['title'], company=JOB['company'], location=JOB['location'],
                         country='', country_quote='', description_sources=[], requisition_id='REQ-101')
        source = dict(url=JOB['url'],title=JOB['title'],snippet='Company Alpha, City A. Requisition REQ-101.')
        self.assertEqual(observed_job(candidate,[source])['requisition_id'],'REQ-101')
        candidate['requisition_id']='REQ-102'
        self.assertEqual(observed_job(candidate,[source]).get('requisition_id',''),'')

    def test_republished_linkedin_id_keeps_same_employer_requisition(self):
        a = {**JOB, 'url': 'https://linkedin.com/jobs/view/123456'}
        b = {**JOB, 'url': 'https://linkedin.com/jobs/view/654321'}
        self.assertTrue(same_posting(a, b))

    def test_same_title_and_city_without_content_cannot_prove_identity(self):
        a = {**JOB, 'requisition_id': '', 'description': ''}
        b = {**a, 'url': 'https://careers.example/jobs/other'}
        self.assertFalse(same_posting(a, b))

    def test_short_conflicting_content_cannot_merge_same_title(self):
        a = {**JOB, 'requisition_id': '', 'description': 'Own embedded vehicle network safety.'}
        b = {**a, 'url': 'https://careers.example/jobs/other', 'description': 'Design optical lenses.'}
        self.assertFalse(same_posting(a, b))


class HistoryRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'state.sqlite3', v5=True)
        self.store.upsert_job(JOB)

    def test_mail_requisition_requires_employer_corroboration(self):
        message = dict(subject='Company Beta - application 101', bodyPreview='We regret to inform you.')
        match_outlook_messages(self.store, [message])
        self.assertEqual(self.store.jobs()[0]['application_status'], 'none')

    def test_later_discovery_cannot_match_foreign_employers_rejection(self):
        self.store.fresh_session()
        match_outlook_messages(self.store, [dict(subject='Company Beta - 101', bodyPreview='We regret to inform you.')])
        self.store.upsert_job(JOB)
        self.assertEqual(self.store.jobs()[0]['application_status'], 'none')

    def test_repeated_import_is_idempotent_and_does_not_replace_manual_decision(self):
        message = dict(id='synthetic-mail', subject='Company Alpha - 101',
                       bodyPreview='We regret to inform you.', receivedDateTime='2026-10-10T10:00:00Z')
        match_outlook_messages(self.store, [message])
        self.store.application(JOB['id'], 'interview')
        match_outlook_messages(self.store, [message])
        self.assertEqual(self.store.jobs()[0]['application_status'], 'interview')

    def test_saved_status_and_event_timeline_survive_search_and_rediscovery(self):
        self.store.application(JOB['id'], 'saved')
        self.store.application(JOB['id'], 'applied')
        self.store.application(JOB['id'], 'rejected')
        self.store.fresh_session()
        self.store.upsert_job(JOB)
        item = self.store.jobs()[0]
        self.assertEqual([e['status'] for e in item['events']], ['saved', 'applied', 'rejected'])
        self.assertEqual(item['application_status'], 'rejected')
        self.store.application(JOB['id'], 'saved')
        self.store.fresh_session()
        self.store.upsert_job(JOB)
        self.assertEqual(self.store.jobs()[0]['application_status'], 'saved')

    def test_mail_provenance_survives_session_reset(self):
        match_outlook_messages(self.store, [dict(subject='Company Alpha - 101', bodyPreview='We regret to inform you.')])
        self.store.fresh_session()
        self.store.upsert_job(JOB)
        self.assertEqual(self.store.jobs()[0]['historical_status_source'], 'outlook_read_only')

    def test_explicit_manual_clear_is_not_undone_by_old_mail_on_rediscovery(self):
        match_outlook_messages(self.store, [dict(subject='Company Alpha - 101', bodyPreview='We regret to inform you.')])
        self.store.application(JOB['id'], 'none')
        self.store.fresh_session()
        self.store.upsert_job(JOB)
        self.assertEqual(self.store.jobs()[0]['application_status'], 'none')

    def test_export_includes_durable_history_and_imported_evidence(self):
        match_outlook_messages(self.store, [dict(subject='Company Alpha - 101', bodyPreview='We regret to inform you.')])
        self.store.fresh_session()
        exported = self.store.export()
        self.assertEqual(exported['job_history'][0]['application_status'], 'rejected')
        self.assertEqual(len(exported['outlook_evidence']), 1)


class EvidenceRegressions(unittest.TestCase):
    def test_partial_source_is_available_to_the_assessor_and_quote_validator(self):
        job = {**JOB, 'description': '', 'source_observations': [],
               'partial_source_text': {'text': 'Own system architecture.'}}
        self.assertIn('Own system architecture.', str(context(job)))
        result=prepare(copy.deepcopy(DECISION), job, {'cv_text': CV}, [])
        self.assertFalse(result['recommend'])
        self.assertEqual(result['evidence'][0]['job_quote'],'Own system architecture.')

    def test_ruling_keyword_alone_does_not_prove_employer_support(self):
        job = {**JOB, 'description': JOB['description'] + ' We do not support the 30% ruling.'}
        decision = {**copy.deepcopy(DECISION), 'ruling_employer_support': 'stated'}
        self.assertEqual(prepare(decision, job, {'cv_text': CV}, [])['ruling_employer_support'], 'unknown')

    def test_failed_reassessment_cannot_leave_old_recommendation_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state.sqlite3', v5=True)
            store.upsert_job({**JOB, 'preliminary': {**DECISION, 'signature': 'old'}})
            class InvalidAI:
                def run(self, *args, **kwargs):
                    return {'assessments': [{**copy.deepcopy(DECISION), 'evidence': [dict(
                        requirement='Architecture', job_quote='Fabricated requirement',
                        cv_quote='Led electrical architecture', assessment='Unsupported')]}]}
            stats = assess(InvalidAI(), store, store.jobs(), {'cv_text': CV}, [])
            self.assertEqual(stats['invalid_evidence'], 1)
            self.assertFalse(store.jobs()[0]['preliminary']['recommend'])
