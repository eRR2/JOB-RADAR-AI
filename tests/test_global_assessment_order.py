"""Coordinator ordering and country-scope regressions; synthetic retained jobs only."""
import copy
import threading
import unittest

from job_radar_ai.providers import ProviderError
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.sources import PublicFetcher
import test_clean_search as fixtures
from test_clean_search import PROFILE, ScriptedAI
from test_verification_flow import full_job, decision


class GlobalAssessmentOrderTests(unittest.TestCase):
    setUp = fixtures.CleanSessionTests.setUp

    def execute(self, specifications, fail_second=False):
        profile = copy.deepcopy(PROFILE)
        profile['hard_requirements'] = 'Global requirement'
        for market in profile['markets']:
            market['hard_requirements'] = market['id'] + ' requirement'
            self.store.set('learned:' + market['id'], [{'text': market['id'] + ' learning'}])
        self.store.set('profile', profile)
        self.store.set('learned:global', [{'text': 'Global learning'}])
        self.store.set('persistent_feedback', [
            {'id': 1, 'country': 'DE', 'note': 'DE feedback'},
            {'id': 2, 'country': 'NL', 'note': 'NL feedback'},
            {'id': 3, 'country': 'global', 'note': 'Global feedback'},
        ])
        identities = [identity for identity, _, _ in specifications]
        for identity, market_id, verified in specifications:
            market = next((m for m in profile['markets'] if m['id'] == market_id), None)
            location = market['locations'][0] if market else 'Unverified locality'
            country = market['country'] if market and verified else ''
            self.store.upsert_job({**full_job(identity),
                'url': 'https://employer.example/jobs/' + identity,
                'source': 'Synthetic publisher', 'company': 'Example Employer',
                'location': location, 'country': country})

        class OrderedAI(ScriptedAI):
            def run(self, kind, task, context, **kwargs):
                if kind == 'research_v5':
                    self.calls.append((kind, task, context, kwargs))
                    self.telemetry = {'web_calls': 1, 'observations': []}
                    return dict(jobs=[], summary='Retained synthetic jobs', limitations=[],
                                continue_research=False, next_avenues=[])
                if kind == 'enrichment':
                    self.calls.append((kind, task, context, kwargs))
                    self.telemetry = {}
                    return dict(candidate_ids=identities, reason='Global AI priority order')
                if kind == 'priority_v52':
                    self.calls.append((kind, task, context, kwargs))
                    self.telemetry = {}
                    if fail_second and sum(k == kind for k, _, _, _ in self.calls) == 2:
                        raise ProviderError('Synthetic timeout; no retry.', 'time_window')
                    return {'assessments': [decision(j['id']) for j in context['jobs']]}
                return super().run(kind, task, context, **kwargs)

        ai = OrderedAI()
        fetcher = PublicFetcher(self.store, request=lambda _: self.fail('No publisher requests allowed'))
        run = self.store.start_run('codex')
        SessionSearch(self.root, self.store).execute(run, threading.Event(), ai=ai, fetcher=fetcher)
        calls = [context for kind, _, context, _ in ai.calls if kind == 'priority_v52']
        self.assertEqual(fetcher.requests, 0)
        return calls, self.store.jobs(), self.store.runs()[0]

    def assert_scope(self, context, market_id, verified=True):
        profile = context['profile']
        self.assertEqual(profile.get('market', {}).get('id'), market_id)
        expected_learning = ([{'text': market_id + ' learning'}] if verified and market_id else [])
        self.assertEqual(profile['learned_preferences'], expected_learning + [{'text': 'Global learning'}])
        self.assertEqual(context['feedback'], [f for f in self.store.get('persistent_feedback')
            if verified and market_id and f['country'] in (market_id, 'global')])
        self.assertEqual(profile['hard_requirements'], 'Global requirement' +
                         ('\n' + market_id + ' requirement' if market_id else ''))

    def test_interleaved_countries_preserve_global_priority_and_scoped_context(self):
        calls, jobs, run = self.execute([
            ('DE-1', 'DE', True), ('NL-2', 'NL', True),
            ('NL-3', 'NL', True), ('DE-4', 'DE', True)])
        self.assertEqual([j['id'] for c in calls for j in c['jobs']], ['DE-1', 'NL-2', 'NL-3', 'DE-4'])
        self.assertEqual([[j['id'] for j in c['jobs']] for c in calls], [['DE-1'], ['NL-2', 'NL-3'], ['DE-4']])
        for context, market in zip(calls, ['DE', 'NL', 'DE']):
            self.assert_scope(context, market)
        self.assertEqual(sum(j.get('evaluation_status') == 'assessed' for j in jobs), 4)
        self.assertEqual(run['status'], 'completed')

    def test_country_confidence_and_unknown_country_are_separate_contiguous_scopes(self):
        calls, _, _ = self.execute([
            ('DE-1', 'DE', True), ('inferred-2', 'DE', False),
            ('DE-3', 'DE', True), ('unknown-4', None, False), ('NL-5', 'NL', True)])
        self.assertEqual([[j['id'] for j in c['jobs']] for c in calls],
                         [['DE-1'], ['inferred-2'], ['DE-3'], ['unknown-4'], ['NL-5']])
        for context, market, verified in zip(calls, ['DE', 'DE', 'DE', None, 'NL'], [True, False, True, False, True]):
            self.assert_scope(context, market, verified)

    def test_timeout_cannot_assess_lower_ranked_country_tail_before_next_country(self):
        calls, jobs, run = self.execute([
            ('DE-1', 'DE', True), ('NL-2', 'NL', True),
            ('NL-3', 'NL', True), ('DE-4', 'DE', True)], fail_second=True)
        self.assertEqual([j['id'] for j in jobs if j.get('evaluation_status') == 'assessed'], ['DE-1','DE-4'])
        self.assertEqual([[j['id'] for j in c['jobs']] for c in calls], [['DE-1'], ['NL-2', 'NL-3'], ['DE-4']])
        self.assert_scope(calls[0], 'DE')
        self.assert_scope(calls[1], 'NL')
        self.assert_scope(calls[2], 'DE')
        self.assertEqual(run['status'], 'partial')
        pending = [j for j in jobs if j['id'] in ('NL-2','NL-3')]
        self.assertTrue(all(j['review_state'] == {'status': 'pending', 'reason': 'evaluation_timeout'} for j in pending))


if __name__ == '__main__':
    unittest.main()
