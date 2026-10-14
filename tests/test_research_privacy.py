"""Public research receives anonymous capabilities, never the original private request."""
import threading
import unittest
from job_radar_ai.session_search import SessionSearch, initial_plan
from job_radar_ai.sources import PublicFetcher
import test_clean_search as fixtures


class ResearchPrivacyTests(unittest.TestCase):
    setUp = fixtures.CleanSessionTests.setUp

    def test_private_career_text_and_cv_experience_do_not_enter_public_call(self):
        private = 'I am Synthetic Person. Contact personal@example.invalid. I work at Private Employer.'
        profile = {**fixtures.PROFILE, 'looking_for':private,
                   'intent':{'experience':[{'text':'Confidential employer project X'}], 'preferences':[]}}
        self.store.set('profile',profile)
        ai = fixtures.ScriptedAI()
        for _ in range(2):
            token,_ = self.store.fresh_session()
            store = self.store.bound(token)
            run = store.start_run('codex')
            fetcher = PublicFetcher(store,request=lambda _:self.fail('No live publisher calls'))
            SessionSearch(self.root,store).execute(run,threading.Event(),ai=ai,fetcher=fetcher)
        public = [c for k,_,c,opts in ai.calls if opts.get('research')]
        self.assertTrue(public)
        for context in public:
            self.assertNotIn(private,str(context))
            self.assertNotIn('personal@example.invalid',str(context))
            self.assertNotIn('Confidential employer project X',str(context))
            self.assertNotIn(fixtures.CV,str(context))
            self.assertTrue(context['background'])
        self.assertEqual(sum(k=='session_brief' for k,_,_,_ in ai.calls),1)

    def test_uninterpreted_private_prose_is_not_a_direct_transport_query(self):
        profile = {**fixtures.PROFILE, 'looking_for':'I am Synthetic Person; contact personal@example.invalid'}
        plan = initial_plan(profile,profile['markets'])
        self.assertTrue(all(not m['linkedin_queries'] for m in plan['markets']))
