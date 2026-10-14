"""Synthetic retained-page and source-selection regressions; no live transport."""
import json
import threading
import unittest
from unittest.mock import patch
import test_clean_search as fixtures
from test_recovery import FixtureFetcher,page
from test_verification_flow import decision,full_job
from job_radar_ai.observations import observed_job
from job_radar_ai.completion import recover_page
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.sources import RetrievalError

OFFICIAL='https://employer.example/jobs/REQ-42'
LINKEDIN='https://www.linkedin.com/jobs/view/123456'
TEXT=full_job()['description']+' Mandatory systems integration experience at the end.'


def structured_page(title='Architecture Lead',company='Synthetic',req='REQ-42'):
    posting={'@type':'JobPosting','title':title,'hiringOrganization':{'name':company},
        'identifier':{'value':req},'jobLocation':{'address':{'addressLocality':'Berlin','addressCountry':'Germany'}},
        'description':'<p>'+TEXT+'</p>'}
    # The visible title is deliberately decorated and there is no main region.
    return '<h1>Vacancy: '+title+' at '+company+'</h1><script type="application/ld+json">'+json.dumps(posting)+'</script>'


class SourceReuseTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def search(self,candidate,observations,pages=None):
        self.store.fresh_session()
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.PROFILE['markets'][:1],'linkedin_consent':True})
        class AI(fixtures.ScriptedAI):
            def run(self,kind,task,context,**kwargs):
                if kind=='research_v5':
                    self.calls.append((kind,task,context,kwargs))
                    self.telemetry={'web_calls':1,'observations':observations}
                    return dict(jobs=[candidate],summary='Retained synthetic evidence',limitations=[],continue_research=False,next_avenues=[])
                if kind=='priority_v52':
                    self.calls.append((kind,task,context,kwargs));self.telemetry={}
                    return {'assessments':[decision(j['id']) for j in context['jobs']]}
                return super().run(kind,task,context,**kwargs)
        fetcher=FixtureFetcher(self.store,pages or {});ai=AI()
        with patch('job_radar_ai.session_search.linkedin_state',return_value={'state':'restricted','http_status':429}),\
             patch('job_radar_ai.session_search.LinkedIn.search',side_effect=AssertionError('No LinkedIn request')),\
             patch('job_radar_ai.session_search.LinkedIn.detail',side_effect=AssertionError('No LinkedIn request')):
            run=self.store.start_run('codex')
            SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,fetcher=fetcher)
        return self.store.jobs()[0],self.store.runs()[0]['payload'],ai,fetcher

    def candidate(self,url=LINKEDIN,refs=None):
        return {**fixtures.candidate(123456),'url':url,'requisition_id':'REQ-42',
            'description_sources':refs or []}

    def snippet(self,url=LINKEDIN):
        return dict(url=url,title='Architecture Lead',snippet='Synthetic Berlin, Germany. REQ-42. Own electrical system architecture.',observation_kind='search_snippet')

    def test_native_jsonld_on_original_url_is_reused_without_a_fetch(self):
        html=structured_page()
        job,payload,ai,fetcher=self.search(self.candidate(OFFICIAL),[
            self.snippet(OFFICIAL),dict(url=OFFICIAL,title='Architecture Lead',text=html,observation_kind='page_read')])
        self.assertEqual(job.get('description'),TEXT)
        self.assertEqual(fetcher.requests,0)
        self.assertEqual(job['description_source']['url'],OFFICIAL)
        self.assertEqual(payload['diagnostics']['counts']['evaluated'],1)
        self.assertEqual(sum(k=='research_v5' for k,_,_,_ in ai.calls),1)

    def test_malformed_unrelated_observation_cannot_discard_valid_recorded_page(self):
        job,_,_,fetcher=self.search(self.candidate(OFFICIAL),[
            dict(url='https://[invalid/jobs/other',text='Unrelated invalid observation',observation_kind='page_read'),
            self.snippet(OFFICIAL),dict(url=OFFICIAL,title='Architecture Lead',text=structured_page(),observation_kind='page_read')])
        self.assertEqual(job.get('description'),TEXT)
        self.assertEqual(fetcher.requests,0)

    def test_observed_official_page_in_ownership_field_survives_linkedin_stop(self):
        html=structured_page()
        job,_,ai,fetcher=self.search(self.candidate(refs=[{'url':LINKEDIN,'employer_url':OFFICIAL}]),[
            self.snippet(),dict(url=OFFICIAL,title='Architecture Lead',text=html,observation_kind='page_read')])
        self.assertEqual(job.get('description'),TEXT)
        self.assertEqual(job['id'],'linkedin:123456');self.assertEqual(job['url'],LINKEDIN)
        self.assertEqual(job['description_source']['url'],OFFICIAL)
        self.assertEqual(fetcher.requests,0)
        self.assertTrue(job['preliminary']['recommend'])
        self.assertNotIn('resolve',[k for k,_,_,_ in ai.calls])

    def test_unsafe_observed_alternative_cannot_supply_verified_text(self):
        for url in ('http://employer.example/jobs/REQ-42','https://user:secret@employer.example/jobs/REQ-42'):
            with self.subTest(url=url):
                job,_,ai,fetcher=self.search(self.candidate(refs=[{'url':url,'employer_url':''}]),[
                    self.snippet(),dict(url=url,title='Architecture Lead',text=structured_page(),observation_kind='page_read')])
                self.assertFalse(job.get('description'))
                self.assertEqual(fetcher.requests,0)
                self.assertEqual(job['description_review']['reason'],'no_observed_description_source')
                self.assertNotIn('priority_v52',[k for k,_,_,_ in ai.calls])

    def test_homepage_jobposting_and_another_linkedin_identity_are_not_replacements(self):
        job={**self.candidate(),'id':'linkedin:123456'}
        for url in ('https://employer.example/','https://www.linkedin.com/jobs/view/123457'):
            with self.subTest(url=url):
                with self.assertRaises(RetrievalError):recover_page(job,page(structured_page(),url),fixtures.PROFILE['markets'])

    def test_unobserved_alternative_is_not_requested_and_missing_source_is_explicit(self):
        job,payload,ai,fetcher=self.search(self.candidate(refs=[{'url':LINKEDIN,'employer_url':OFFICIAL}]),[self.snippet()])
        self.assertEqual(fetcher.requests,0)
        self.assertFalse(job.get('description'))
        self.assertEqual(job['description_review']['reason'],'no_observed_description_source')
        self.assertEqual(job['description_review']['source_coverage']['independent_urls'],0)
        self.assertNotIn('enrichment',payload['diagnostics']['completed_phases'])
        self.assertEqual(payload['diagnostics']['phase_outcomes']['enrichment'],'partial')
        self.assertNotIn('priority_v52',[k for k,_,_,_ in ai.calls])

    def test_alternate_page_with_wrong_requisition_cannot_be_assessed(self):
        job,_,ai,fetcher=self.search(self.candidate(refs=[{'url':OFFICIAL,'employer_url':''}]),[
            self.snippet(),dict(url=OFFICIAL,title='Architecture Lead',text=structured_page(req='REQ-99'),observation_kind='page_read')],
            {OFFICIAL:RetrievalError('unavailable','Synthetic missing address',404)})
        self.assertFalse(job.get('description'))
        self.assertNotIn('priority_v52',[k for k,_,_,_ in ai.calls])
        attempts=job['description_review']['attempts']
        self.assertTrue(any(a.get('stage')=='identity' and 'requisition' in a['reason'].lower() for a in attempts))
        self.assertEqual(fetcher.requests,0, 'Rejected retained text must not cause a redundant fetch')

    def test_access_failure_and_parser_failure_keep_distinct_stages(self):
        cases=[(RetrievalError('unavailable','Synthetic missing address',404),'access','source_access_failed'),
            (page('<title>Architecture Lead</title><p>Only a site shell</p>',OFFICIAL),'parsing','source_parsing_failed'),
            (page(structured_page(title='Different role'),OFFICIAL),'identity','source_identity_unverified')]
        for index,(response,stage,reason) in enumerate(cases):
            with self.subTest(stage=stage):
                # Independent synthetic identities keep each retained outcome inspectable.
                url=OFFICIAL+str(index);candidate=self.candidate(url);candidate['requisition_id']=''
                if isinstance(response,dict):response={**response,'url':url}
                job,_,ai,_=self.search(candidate,[self.snippet(url)],{url:response})
                self.assertEqual(job['description_review']['reason'],reason)
                self.assertTrue(any(a.get('stage')==stage for a in job['description_review']['attempts']))
                self.assertEqual(job['availability'],'unknown')
                self.assertNotIn('priority_v52',[k for k,_,_,_ in ai.calls])

    def test_retained_observation_keeps_page_read_type_and_unmixed_page_body(self):
        html=structured_page()
        job=observed_job(self.candidate(OFFICIAL),[self.snippet(OFFICIAL),
            dict(url=OFFICIAL,title='Architecture Lead',text=html,observation_kind='page_read')])
        read=job['source_observations'][1]
        self.assertEqual(read.get('observation_kind'),'page_read')
        self.assertEqual(read.get('page_text'),html)

    def test_shared_linkedin_stop_keeps_exact_listing_url_in_diagnostics(self):
        url='https://www.linkedin.com/jobs/view/2345678912'
        job,_,_,_=self.search(self.candidate(url),[self.snippet(url)])
        note=next(a for a in job['description_review']['attempts'] if a['status']=='blocked_shared_stop')
        self.assertEqual(note['url'],url)
        self.assertFalse(note['attempted'])


if __name__=='__main__':unittest.main()
