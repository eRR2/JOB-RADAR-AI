"""Offline regressions for honest coverage of retained research findings."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from job_radar_ai.providers import ProviderError
from job_radar_ai.recommendations import assess
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.sources import PublicFetcher
from job_radar_ai.store import Store
from test_clean_search import CV, MARKETS, PROFILE, ScriptedAI, candidate


class ReviewAI(ScriptedAI):
    """All discoveries and source quotations are deliberately synthetic."""
    def __init__(self, fail_second=False, invalid_first=False, snippets_only=False):
        super().__init__()
        self.fail_second = fail_second
        self.invalid_first = invalid_first
        self.snippets_only = snippets_only
        self.assessment_calls = 0

    def run(self, kind, task, context, **kwargs):
        if kind == 'research_v5':
            self.calls.append((kind, task, context, kwargs))
            jobs = [candidate(123456 + i) for i in range(24)]
            observations = []
            for index, job in enumerate(jobs):
                if self.snippets_only:
                    observations.append(dict(url=job['url'], title=job['title'],
                                             snippet='Synthetic Berlin, Germany. Own electrical system architecture.'))
                else:
                    job['url'] = f'https://employer.example/jobs/synthetic-{index}'
                    html = (
                        f'<link rel="canonical" href="{job["url"]}">'
                        '<header>Synthetic</header><div class="article-wrapper">'
                        '<h1>Architecture Lead</h1><div class="location">Berlin, Germany</div>'
                        '<p>Own electrical system architecture. Define system requirements, '
                        'coordinate interface decisions and verify integration evidence. '
                        'Requirements: architecture experience, requirements management and '
                        'clear communication with engineering and validation teams.</p></div>'
                    )
                    observations.append(dict(url=job['url'], title=job['title'],
                                             text=html, observation_kind='page_read'))
            self.telemetry = {
                'web_calls': 1,
                'observations': observations,
                'actions': [{'queries': ['Synthetic technical ownership']}],
            }
            return dict(jobs=jobs, summary='Synthetic observed fixtures', limitations=[],
                        continue_research=False, next_avenues=[])
        if kind == 'priority_v52':
            self.calls.append((kind, task, context, kwargs))
            self.assessment_calls += 1
            self.telemetry = {}
            if self.fail_second and self.assessment_calls == 2:
                raise ProviderError('Synthetic evaluation call timed out.', 'time_window')
            items = [dict(job_id=j['id'], category='direct', recommend=True,
                          priority='strong', next_step='Observed system ownership matches demonstrated architecture experience.',
                          critical_gap=False, gaps=[],
                          evidence=[dict(requirement='Electrical architecture',
                                         job_quote='Own electrical system architecture.',
                                         cv_quote='Led electrical system architecture',
                                         assessment='Direct observed capability evidence')])
                     for j in context['jobs']]
            if self.invalid_first and self.assessment_calls == 1:
                items[0]['evidence'][0]['job_quote'] = 'Unsupported invented source quote'
            return {'assessments': items}
        return super().run(kind, task, context, **kwargs)


class ReviewPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state.sqlite3', v5=True)
        self.store.set('profile', {**PROFILE, 'markets': MARKETS[:1]})
        self.store.set('cv_text', CV)

    def execute(self, ai):
        run = self.store.start_run('codex')
        fetcher = PublicFetcher(self.store, request=lambda _: self.fail('No live publisher requests allowed'))
        SessionSearch(self.root, self.store).execute(run, threading.Event(), ai=ai, fetcher=fetcher)
        return self.store.jobs(), self.store.runs()[0]

    def test_closed_job_is_excluded_and_never_counted_as_cached_assessment(self):
        closed = dict(id='closed', title='Synthetic closed role',
                      availability='closed_banner_observed', freshness={'status': 'confirmed_closed'})
        self.store.upsert_job(closed)
        ai = ReviewAI()
        stats = assess(ai, self.store, self.store.jobs(), PROFILE, [])
        self.assertEqual(stats['cached'], 0)
        self.assertEqual(stats['assessed'], 0)
        self.assertEqual(ai.assessment_calls, 0)
        from job_radar_ai.reporting import review_state
        state = review_state(self.store.jobs()[0])
        self.assertEqual(state['status'], 'excluded')
        self.assertEqual(state['reason'], 'confirmed_closed')

    def test_timeout_keeps_first_batch_and_labels_every_remaining_selected_job(self):
        ai = ReviewAI(fail_second=True)
        jobs, run = self.execute(ai)
        self.assertEqual(len(jobs), 24)
        self.assertEqual(sum(bool(j.get('preliminary', {}).get('signature')) for j in jobs), 2)
        self.assertTrue(all(j.get('description_source', {}).get('kind') == 'public_verified' for j in jobs))
        self.assertEqual(ai.assessment_calls, 2, 'A timeout must stop assessment calls in this run')
        self.assertEqual(run['status'], 'partial')
        diagnostics = run['payload']['diagnostics']
        self.assertNotIn('evaluation', diagnostics['completed_phases'])
        pending = [j for j in jobs if not j.get('preliminary', {}).get('signature')]
        self.assertTrue(all(j.get('review_state', {}).get('status') == 'pending' for j in pending))
        self.assertTrue(all(j['review_state']['reason'] == 'evaluation_timeout' for j in pending))
        from job_radar_ai.reporting import coverage
        result = coverage(jobs, diagnostics)
        self.assertEqual(result['selected'], 24)
        self.assertEqual(result['assessed'], 2)
        self.assertEqual(result['pending'], 22)

    def test_invocation_budget_reports_incomplete_coverage_without_losing_valid_batch(self):
        ai = ReviewAI()
        # Brief, discovery, triage, then exactly one successful assessment batch.
        with patch('job_radar_ai.session_search.MAX_AI_CALLS', 4):
            jobs, run = self.execute(ai)
        self.assertEqual(ai.assessment_calls, 1)
        self.assertEqual(len(jobs), 24)
        self.assertEqual(sum(bool(j.get('preliminary', {}).get('signature')) for j in jobs), 2)
        self.assertTrue(all(j.get('description_source', {}).get('kind') == 'public_verified' for j in jobs))
        self.assertEqual(run['status'], 'partial')
        diagnostics = run['payload']['diagnostics']
        self.assertNotIn('evaluation', diagnostics['completed_phases'])
        pending = [j for j in jobs if not j.get('preliminary', {}).get('signature')]
        self.assertTrue(all(j.get('review_state', {}).get('reason') == 'evaluation_budget' for j in pending))
        from job_radar_ai.reporting import coverage
        result = coverage(jobs, diagnostics)
        self.assertEqual(result['assessed'], 2)
        self.assertEqual(result['pending'], 22)

    def test_one_invalid_quote_keeps_other_assessments_and_is_not_counted_as_assessed(self):
        ai = ReviewAI(invalid_first=True)
        jobs, run = self.execute(ai)
        self.assertEqual(len(jobs), 24)
        self.assertEqual(sum(bool(j.get('preliminary', {}).get('signature')) for j in jobs), 23)
        from job_radar_ai.reporting import coverage, review_state
        invalid = next(j for j in jobs if j.get('evaluation_status') == 'needs_verification')
        self.assertEqual(review_state(invalid)['status'], 'needs_verification')
        result = coverage(jobs, run['payload']['diagnostics'])
        self.assertEqual(result['assessed'], 23)
        self.assertEqual(result['needs_verification'], 1)
        self.assertEqual(result['pending'], 0)
        self.assertEqual(run['status'], 'partial')

    def test_snippets_remain_source_pending_without_final_assessment_calls(self):
        ai = ReviewAI(snippets_only=True)
        jobs,run=self.execute(ai)
        self.assertEqual(len(jobs), 24)
        self.assertEqual(sum(bool(j.get('preliminary',{}).get('signature')) for j in jobs),0)
        self.assertEqual(ai.assessment_calls, 0)
        self.assertEqual(run['status'],'partial')
        self.assertNotIn('evaluation', run['payload']['diagnostics']['completed_phases'])
        self.assertTrue(any('full description' in w for w in run['payload']['warnings']))
        self.assertTrue(all(j['description_review']['reason']=='no_observed_description_source' for j in jobs))
        self.assertTrue(all(j['review_state'] == {'status': 'pending', 'reason': 'full_source_required'} for j in jobs))
        from job_radar_ai.reporting import coverage
        result = coverage(jobs, run['payload']['diagnostics'])
        self.assertEqual(result['assessed'], 0)
        self.assertEqual(result['pending'], 24)


if __name__ == '__main__':
    unittest.main()
