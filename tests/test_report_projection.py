"""Synthetic report/metadata/history checks; never consult a real mailbox."""
import tempfile
import unittest
from pathlib import Path

from job_radar_ai.observations import observed_job
from job_radar_ai.store import Store


class ReportProjectionTests(unittest.TestCase):
    def test_timeout_title_metadata_is_literal_unverified_and_preserves_salary_ceiling(self):
        title = 'Technical Lead - Up to 123,000 EUR + equity bei Example Employer — Example City | LinkedIn Jobs'
        url = 'https://linkedin.com/jobs/view/123456'
        job = observed_job(dict(url=url,title=title,company='',location='',country='',country_quote='',description_sources=[]),
                           [dict(url=url,title=title,snippet='Observed vacancy')])
        fields = job['inferred_fields']
        self.assertEqual(fields['company']['value'], 'Example Employer')
        self.assertEqual(fields['location']['value'], 'Example City')
        self.assertEqual(fields['salary']['value'], 'Up to 123,000 EUR')
        self.assertEqual(fields['salary']['interpretation'], 'advertised_upper_bound')
        for field in fields.values():
            self.assertFalse(field['verified'])
            self.assertEqual(field['kind'], 'source_title')
            self.assertEqual(field['quote'], title)
            self.assertEqual(field['url'], job['url'])
        self.assertEqual(job['company'], '', 'Title hints must not change canonical identity facts')
        self.assertEqual(job['location'], '')
        self.assertEqual(job['country'], '')

    def test_local_status_none_is_not_proof_of_no_application(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'state.sqlite3',v5=True)
            job = dict(id='linkedin:123456',source_id='123456',url='https://linkedin.com/jobs/view/123456',
                       title='Technical Lead',company='Example Employer',location='Example City')
            store.upsert_job(job)
            self.assertEqual(store.jobs()[0]['application_history_check']['status'], 'unverified')
            store.application(job['id'], 'none')  # Explicit user confirmation of initial none.
            self.assertEqual(store.jobs()[0]['application_history_check']['status'], 'recorded')
            store.application(job['id'], 'rejected')
            store.fresh_session()
            store.upsert_job({**job,'url':job['url']+'?trk=changed'})
            result=store.jobs()[0]
            self.assertEqual(result['application_status'],'rejected')
            self.assertEqual(result['application_history_check']['status'],'recorded')
            store.upsert_job({**job,'id':'linkedin:123457','source_id':'123457','url':'https://linkedin.com/jobs/view/123457'})
            other=next(j for j in store.jobs() if j['id']=='linkedin:123457')
            self.assertEqual(other['application_status'],'none')
            self.assertEqual(other['application_history_check']['status'],'unverified')

    def test_legacy_manual_default_without_a_decision_does_not_confirm_no_application(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'state.sqlite3',v5=True)
            store.upsert_job(dict(id='linkedin:123456',url='https://linkedin.com/jobs/view/123456',title='Observed role'))
            with store.db() as db:db.execute("UPDATE job_history SET status_source='manual'")
            self.assertEqual(store.jobs()[0]['application_history_check']['status'],'unverified')

    def test_existing_records_are_projected_without_rewriting_source_facts(self):
        from job_radar_ai.listing_metadata import source_title_fields
        original = dict(title='Example Employer hiring System Owner in Example City, Germany | LinkedIn',
                        url='https://linkedin.com/jobs/view/123456',company='',location='',country='',
                        source_observations=[{'text':'Example Employer hiring System Owner in Example City, Germany | LinkedIn'}])
        projected = source_title_fields(original)
        self.assertEqual(projected['inferred_fields']['company']['value'], 'Example Employer')
        self.assertEqual(projected['inferred_fields']['location']['value'], 'Example City, Germany')
        self.assertNotIn('inferred_fields',original)
        self.assertEqual(projected['country'],'')

    def test_no_metadata_is_invented_from_role_words_or_model_only_title(self):
        from job_radar_ai.listing_metadata import source_title_fields
        for job in [dict(title='System owner at scale',url='https://example.org/1'),
                    dict(title='Example Employer hiring System Owner in Example City | LinkedIn',
                         url='https://example.org/2',source_observations=[{'text':'Different observed role'}])]:
            self.assertFalse(source_title_fields(job).get('inferred_fields'))

    def test_legacy_group_diagnostics_recover_timeout_budget_and_closure_reasons(self):
        from job_radar_ai.reporting import review_state,coverage
        d={'failures':[{'phase':'evaluation','country':'Country B','reason':'time_window'},
                       {'phase':'evaluation','country':'Location unverified','reason':'phase_budget'}]}
        jobs=[dict(id='done',shortlist_status='selected',preliminary={'recommend':True}),
              dict(id='timed',shortlist_status='selected',review_country='Country B'),
              dict(id='budget',shortlist_status='selected',review_country='Location unverified'),
              dict(id='closed',shortlist_status='selected',availability='closed_banner_observed')]
        self.assertEqual(review_state(jobs[1],d)['reason'],'evaluation_timeout')
        self.assertEqual(review_state(jobs[2],d)['reason'],'evaluation_budget')
        self.assertEqual(review_state(jobs[3],d)['reason'],'confirmed_closed')
        self.assertEqual(coverage(jobs,d)['selected'],4)
        self.assertEqual(coverage(jobs,d)['pending'],2)

    def test_provider_stop_before_triage_is_not_a_successful_assessment_phase(self):
        from job_radar_ai.reporting import review_state
        job=dict(id='observed')
        state=review_state(job,{'stop':{'phase':'discovery','reason':'execution_error'}})
        self.assertEqual(state['status'],'pending')
        self.assertEqual(state['reason'],'triage_not_reached')
