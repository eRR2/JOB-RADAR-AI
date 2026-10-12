import tempfile
import threading
import unittest
from pathlib import Path
from job_radar_ai.hunter import Hunter, prepare_evaluation
from job_radar_ai.store import Store
from job_radar_ai.contracts import WEIGHTS


def assessment(job_id='linkedin:123456'):
    return {'job_id': job_id, 'category': 'transferable', 'recommend': True, 'summary': 'Synthetic match',
            'scores': {k: 80 if k != 'salary' else None for k in WEIGHTS}, 'hard_requirements': [],
            'evidence': [{'requirement': 'Lead team', 'job_quote': 'Lead systems team', 'cv_quote': 'Led a systems team', 'assessment': 'Transferable'}],
            'missing_information': ['Salary unknown'], 'ats': {'readiness': 'tailoring_needed', 'explanation': 'Synthetic', 'truthful_cv_changes': ['Describe actual team scope']},
            'hr': {'assessment': 'Synthetic', 'strengths': ['Leadership'], 'gaps': [], 'interview_risks': []}}


class HunterTests(unittest.TestCase):
    def test_unknown_salary_is_unscored_and_does_not_reject(self):
        result = prepare_evaluation(assessment(), {'id': 'linkedin:123456', 'description': 'Lead systems team'}, {'cv_text': 'Led a systems team', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': ''})
        self.assertTrue(result['recommend'])
        self.assertIsNone(result['scores']['salary'])
        self.assertNotIn('weighted_score',result)
        self.assertEqual(result['assessment_version'],2)

    def test_fabricated_job_and_cv_quotes_are_refused(self):
        with self.assertRaises(ValueError):
            prepare_evaluation(assessment(), {'id': 'linkedin:123456', 'description': 'Unrelated'}, {'cv_text': 'Led a systems team', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': ''})
        with self.assertRaises(ValueError):
            prepare_evaluation(assessment(), {'id': 'linkedin:123456', 'description': 'Lead systems team'}, {'cv_text': 'No leadership', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': ''})

    def test_confirmed_hard_violation_prevents_recommendation_but_preserves_job(self):
        value = assessment()
        value['hard_requirements'] = [{'requirement': 'No onsite-only', 'status': 'violated', 'job_quote': 'Onsite only', 'reason': 'Explicitly onsite'}]
        result = prepare_evaluation(value, {'id': 'linkedin:123456', 'description': 'Lead systems team. Onsite only'}, {'cv_text': 'Led a systems team', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': 'No onsite-only'})
        self.assertFalse(result['recommend'])

    def test_ai_cannot_silently_omit_a_hard_requirement(self):
        with self.assertRaises(ValueError):
            prepare_evaluation(assessment(), {'id': 'linkedin:123456', 'description': 'Lead systems team'}, {'cv_text': 'Led a systems team', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': 'Minimum salary'})

    def test_repeat_search_deduplicates_and_feedback_is_supplied_to_ai(self):
        class AI:
            telemetry = {}
            contexts = []
            def run(self, kind, task, context, **kwargs):
                self.contexts.append((kind, context))
                return {'plan': {'strategy': 'Synthetic', 'role_families': ['Systems leadership'], 'queries': [{'query': 'AI invented lead query', 'location': 'Example region', 'remote': 'any', 'reason': 'Synthetic'}], 'supplementary_research': False, 'research_queries': []},
                        'triage': {'detail_ids': ['linkedin:123456'], 'rationale': 'Synthetic', 'expand_queries': []},
                        'evaluation': {'evaluations': [assessment()], 'report': 'Synthetic report'},
                        'learning': {'preferences': [], 'explanation': 'No persistent inference from one dislike'}}[kind]
        class Source:
            requests = cache_hits = 0
            def search(self, query, page):
                return [{'id': 'linkedin:123456', 'source_id': '123456', 'title': 'Synthetic lead', 'url': 'https://www.linkedin.com/jobs/view/123456'}]
            def detail(self, job_id):
                return {'id': 'linkedin:123456', 'description': 'Lead systems team'}
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'db.sqlite3')
            profile = {'provider': 'codex', 'cv_text': 'Led a systems team', 'weights': {k: 1 for k in WEIGHTS}, 'hard_requirements': '', 'consent': True, 'linkedin_consent': True, 'secondary': False}
            store.set('profile', profile)
            ai = AI()
            hunter = Hunter(Path(temp), store)
            for attempt in range(2):
                run_id = store.start_run('codex')
                hunter.execute(run_id, threading.Event(), ai=ai, source=Source())
                if attempt == 0:
                    store.add_feedback('linkedin:123456', 'dislike', ['Too junior'], '')
            self.assertEqual(len(store.jobs()), 1)
            self.assertEqual(store.runs()[0]['payload']['new_jobs'], 0)
            second_plan = [c for k,c in ai.contexts if k == 'plan'][-1]
            self.assertEqual(second_plan['feedback'][0]['kind'], 'dislike')
