"""Synthetic coordinator, mailbox and source-identity regressions."""
import threading
import unittest
from unittest.mock import patch
import test_clean_search as fixtures
from job_radar_ai.contracts import provider_schema,validate
from job_radar_ai.completion import recover
from job_radar_ai.outlook_history import match_outlook_messages
from job_radar_ai.sources import PublicFetcher,RetrievalError
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.store import Store
from test_verification_flow import full_job,decision


class TriageSourceScopeTests(unittest.TestCase):
    setUp=fixtures.CleanSessionTests.setUp

    def test_missing_evidence_is_retained_with_individual_triage_reason(self):
        rationale={'job_id':'linkedin:123456','action':'low_relevance','basis':'missing_evidence',
            'reason':'Mandatory specialist depth has not been established.',
            'transferable_fit':'System architecture ownership may transfer.',
            'specialist_gap':'Specialist experience is unknown, not a proven unmet requirement.',
            'source_quote':'','missing_information':['Full duties and mandatory requirements']}
        class AI(fixtures.ScriptedAI):
            def run(self,kind,task,context,**kwargs):
                if kind=='enrichment':
                    self.telemetry={}
                    return {'candidate_ids':[],'reason':'Mixed source evidence',
                        'decisions':[rationale,{**rationale,'job_id':'linkedin:123457'}]}
                return super().run(kind,task,context,**kwargs)
        run=self.store.start_run('codex');ai=AI()
        fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live requests'))
        SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=ai,fetcher=fetcher)
        job=next(j for j in self.store.jobs() if j['id']=='linkedin:123456')
        self.assertEqual(job['shortlist_status'],'selected')
        self.assertEqual(job['triage_decision']['action'],'needs_evidence')
        self.assertEqual(job['triage_decision']['transferable_fit'],rationale['transferable_fit'])
        self.assertEqual(job['triage_decision']['specialist_gap'],rationale['specialist_gap'])
        self.assertEqual(job['review_state']['reason'],'full_source_required')
        self.assertFalse(any(k=='priority_v52' for k,_,_,_ in ai.calls))

    def test_applied_state_does_not_reclassify_technical_fit(self):
        from job_radar_ai.recommendations import prepare
        job={**full_job(),'application_status':'applied'}
        item=prepare(decision(),job,{'cv_text':fixtures.CV},[])
        self.assertEqual(item['category'],'direct')
        self.assertFalse(item['recommend'])

    def test_application_exclusion_is_not_counted_as_low_relevance(self):
        from job_radar_ai.reporting import coverage
        job=dict(id='one',shortlist_status='low_relevance',application_status='applied')
        result=coverage([job])
        self.assertEqual(result['excluded'],1)
        self.assertEqual(result['not_selected'],0)

    def test_sender_employer_corroborates_exact_acknowledgement_without_contact_storage(self):
        job=dict(id='linkedin:123456',url='https://linkedin.com/jobs/view/123456',
            title='Lead System Architect Expert',company='Example Employer',requisition_id='REQ-42')
        self.store.upsert_job(job)
        message={'subject':'Thanks for your application','bodyPreview':'Thank you for applying for our Lead System Architect Expert (REQ-42) position.',
            'sender':{'emailAddress':{'name':'Example Employer Talent Team','address':'private@example.test'}},
            'receivedDateTime':'2026-01-01T10:00:00Z'}
        self.assertEqual(match_outlook_messages(self.store,[message])['matched'],1)
        self.assertEqual(self.store.jobs()[0]['application_status'],'applied')
        with self.store.db() as db:
            saved=db.execute('select payload from outlook_evidence').fetchone()[0]
        self.assertNotIn('private@example.test',saved)
        self.assertNotIn('irrelevant',saved)

    def test_preimported_mail_is_rechecked_when_existing_job_gains_requisition(self):
        self.store.upsert_job(dict(id='web:one',url='https://employer.example/jobs/one',title='Systems Owner',company='Example Employer'))
        message={'subject':'Example Employer acknowledgement REQ-42','bodyPreview':'We received your application.', 'receivedDateTime':'2026-01-01T10:00:00Z'}
        self.assertEqual(match_outlook_messages(self.store,[message])['matched'],0)
        self.store.upsert_job({'id':'web:one','requisition_id':'REQ-42'})
        self.assertEqual(self.store.jobs()[0]['application_status'],'applied')

    def test_redirected_original_publisher_cannot_attach_a_different_requisition(self):
        job=dict(id='one',url='https://employer.example/jobs/one',title='Systems Owner',company='Example Employer',requisition_id='REQ-42')
        posting=dict(title=job['title'],company=job['company'],location='City A',requisition_id='REQ-99',
            description=full_job()['description'],source_url='https://employer.example/jobs/replacement',evidence={'text':'REQ-99'})
        with patch('job_radar_ai.completion.retrieve_candidates',return_value=[posting]):
            with self.assertRaises(RetrievalError):recover(job,job['url'],'',None,[])

    def test_manual_no_application_confirmation_survives_mail_import(self):
        job=dict(id='linkedin:123456',url='https://linkedin.com/jobs/view/123456',company='Example Employer',title='Systems Owner',requisition_id='REQ-42')
        self.store.upsert_job(job);self.store.application(job['id'],'none')
        match_outlook_messages(self.store,[{'subject':'Example Employer REQ-42','bodyPreview':'We received your application.','receivedDateTime':'2026-01-01T10:00:00Z'}])
        self.assertEqual(self.store.jobs()[0]['application_status'],'none')

    def test_same_requisition_moved_source_is_accepted_without_changing_original_identity(self):
        job=dict(id='one',url='https://employer.example/jobs/old',title='Systems Owner',company='Example Employer',requisition_id='REQ-42')
        moved='https://employer.example/jobs/moved'
        posting=dict(title=job['title'],company=job['company'],location='City A',requisition_id='REQ-42',description=full_job()['description'],source_url=moved,evidence={'text':'REQ-42'})
        with patch('job_radar_ai.completion.retrieve_candidates',return_value=[posting]):
            self.assertEqual(recover(job,job['url'],'',None,[])['source_url'],moved)
        self.assertEqual(job['url'],'https://employer.example/jobs/old')

    def test_unsupported_triage_quote_cannot_exclude_or_discard_other_decisions(self):
        from job_radar_ai.verification import triage_decisions
        jobs=[{'id':key,'title':'Systems Owner','source_excerpt':'Mandatory specialist optics experience.'} for key in ('one','two')]
        base={'action':'low_relevance','basis':'observed_mismatch','reason':'Specialist requirement not demonstrated',
            'transferable_fit':'System architecture capability','specialist_gap':'Specialist requirement',
            'source_quote':'Mandatory specialist optics experience.','missing_information':[]}
        ids,items=triage_decisions({'candidate_ids':[],'decisions':[{**base,'job_id':'one','source_quote':'Invented qualification'},{**base,'job_id':'two'}]},jobs)
        self.assertEqual(ids,['one']);self.assertEqual(items['two']['action'],'low_relevance')
        self.assertEqual(items['one']['action'],'needs_evidence')

    def test_a_specialist_title_alone_is_not_a_proven_mandatory_gap(self):
        from job_radar_ai.verification import triage_decisions
        title='Architecture Lead Specialist Domain'
        item={'job_id':'one','action':'low_relevance','basis':'observed_mismatch',
            'reason':'Specialist depth is not documented','transferable_fit':'Architecture ownership',
            'specialist_gap':'Mandatory depth unknown','source_quote':title,'missing_information':['Full requirements']}
        ids,items=triage_decisions({'candidate_ids':[],'decisions':[item]},[{'id':'one','title':title,'source_excerpt':title}])
        self.assertEqual(ids,['one']);self.assertEqual(items['one']['action'],'needs_evidence')

    def test_individual_triage_decisions_use_strict_nested_wire_schema_and_legacy_compatibility(self):
        schema=provider_schema('enrichment')
        self.assertIn('decisions',schema['required'])
        item=schema['properties']['decisions']['items']
        self.assertEqual(set(item['properties']),set(item['required']))
        self.assertFalse(item['additionalProperties'])
        validate('enrichment',{'candidate_ids':[],'reason':'Historical selection'})

    def test_channel_closure_preserves_source_and_report_time_without_inventing_check_time(self):
        from job_radar_ai.availability import observation,merge_states,closed_for_review
        job=dict(id='linkedin:123456',url='https://linkedin.com/jobs/view/123456')
        note=observation(job,job['url'],'closed','No longer accepting applications',provenance='user_reported',reported_at='2026-01-01T10:00:00Z')
        self.assertIsNone(note['checked_at']);self.assertEqual(note['channel'],'linkedin')
        self.assertEqual(note['reported_at'],'2026-01-01T10:00:00Z')
        self.store.upsert_job({**job,'source_availability':{note['url']:note}})
        unknown=observation(job,job['url'],'unknown',http_status=429,checked_at='2026-01-02T10:00:00Z')
        self.store.upsert_job({'id':job['id'],'source_availability':{note['url']:unknown}})
        retained=self.store.jobs()[0]['source_availability'][note['url']]
        self.assertEqual(retained['status'],'closed');self.assertEqual(retained['last_access']['http_status'],429)
        official='https://employer.example/jobs/REQ-42'
        available=observation(job,official,'open','Apply for REQ-42',checked_at='2026-01-02T10:00:00Z')
        updated={**job,'availability':'closed_banner_observed','description_source':{'kind':'public_verified','url':official},
            'source_availability':merge_states({note['url']:note},{official:available})}
        self.assertFalse(closed_for_review(updated))
        with self.assertRaises(ValueError):observation(job,job['url'],'closed','HTTP 404',http_status=404)

    def test_404_alternative_source_is_attempted_and_failure_stays_unknown(self):
        original='https://employer.example/jobs/old';moved='https://employer.example/jobs/new'
        class AI(fixtures.ScriptedAI):
            def run(self,kind,task,context,**opts):
                if kind=='research_v5':
                    self.telemetry={'web_calls':1,'observations':[
                        {'url':url,'title':'Architecture Lead','snippet':'Example Employer Berlin, Germany. Own electrical system architecture.'} for url in (original,moved)]}
                    return dict(jobs=[{**fixtures.candidate(123456),'url':original,'company':'Example Employer',
                        'description_sources':[{'url':moved,'employer_url':''}]}],summary='Observed exact alternatives',limitations=[],continue_research=False,next_avenues=[])
                if kind=='priority_v52':return {'assessments':[decision(j['id']) for j in context['jobs']]}
                return super().run(kind,task,context,**opts)
        attempts=[]
        def transport(job,url,*args):
            attempts.append(url)
            if url==original:raise RetrievalError('unavailable','Missing address',404)
            return dict(title=job['title'],company=job['company'],description=full_job()['description'],source_url=moved,evidence={'sha256':'synthetic'})
        self.store.set('profile',{**fixtures.PROFILE,'markets':fixtures.PROFILE['markets'][:1]})
        with patch('job_radar_ai.session_search.recover',side_effect=transport):
            run=self.store.start_run('codex')
            SessionSearch(self.root,self.store).execute(run,threading.Event(),ai=AI(),fetcher=PublicFetcher(self.store,request=lambda _:self.fail('No live requests')))
        job=self.store.jobs()[0]
        self.assertEqual(attempts,[original,moved])
        self.assertEqual(job['source_availability'][original]['status'],'unknown')
        self.assertEqual(job['source_availability'][original]['access_status'],'missing_or_moved')
        self.assertEqual(job['description_source']['url'],moved)
        self.assertNotEqual(job['availability'],'closed_banner_observed')


if __name__=='__main__':unittest.main()
