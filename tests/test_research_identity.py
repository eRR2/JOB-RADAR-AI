import unittest
from job_radar_ai.observations import observed_job
from job_radar_ai.identity import normalized_url


class ResearchIdentityTests(unittest.TestCase):
    def candidate(self,url):
        return dict(url=url,title='System Lead',company='Synthetic',location='',country='',country_quote='')

    def test_linkedin_tracking_slug_and_host_variations_match_verified_id(self):
        observed='https://www.linkedin.com/jobs/view/system-lead-123456/?trackingId=abc&trk=search'
        job=observed_job(self.candidate('https://linkedin.com/jobs/view/123456'),[dict(url=observed,title='System Lead',snippet='Synthetic; actual responsibilities unknown')])
        self.assertIsNotNone(job);self.assertEqual(job['id'],'linkedin:123456')
        self.assertEqual(job['country'],'');self.assertNotIn('description',job)
        self.assertEqual(job['source_observations'][0]['url'],observed)

    def test_distinct_ids_and_requisition_queries_do_not_merge(self):
        rejected=[]
        job=observed_job(self.candidate('https://linkedin.com/jobs/view/123457'),[dict(url='https://linkedin.com/jobs/view/123456',title='System Lead')],rejected)
        self.assertIsNone(job);self.assertEqual(rejected[0]['reason'],'identity_not_observed')
        a='https://careers.example/job?req=1&utm_source=test'
        b='https://careers.example/job?req=2'
        self.assertNotEqual(normalized_url(a),normalized_url(b))
        self.assertIsNone(observed_job(self.candidate(b),[dict(url=a,title='System Lead')]))

    def test_canonical_public_url_matches_without_fabricating_fields(self):
        url='https://careers.example/job?req=1'
        job=observed_job(self.candidate(url),[dict(url=url+'&utm_source=search',title='System Lead')])
        self.assertIsNotNone(job);self.assertEqual(job['company'],'')
