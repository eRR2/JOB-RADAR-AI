"""Synthetic scheduling and strict recommendation evidence regressions."""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.recommendations import prepare,context,private_profile
from job_radar_ai.store import Store
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.sources import PublicFetcher,RetrievalError
from test_clean_search import CV,PROFILE,candidate,ScriptedAI


def full_job(identity='linkedin:123456'):
    return dict(id=identity,title='Architecture Lead',description='Own electrical system architecture. '+('Define requirements and technical interfaces. '*15),
                description_source={'kind':'public_verified','url':'https://example.org/jobs/123456'},source_observations=[{'text':'Indexed source only'}])


def decision(identity='linkedin:123456'):
    return dict(job_id=identity,category='direct',recommend=True,priority='strong',next_step='Architecture duties support the requested system ownership.',
                critical_gap=False,gaps=[],evidence=[dict(requirement='Architecture ownership',job_quote='Own electrical system architecture.',cv_quote='Led electrical system architecture',assessment='Direct demonstrated capability')])


class VerificationFlowTests(unittest.TestCase):
    def test_strong_recommendation_requires_verified_description_and_duty_quote(self):
        snippet=dict(id='linkedin:123456',title='Architecture Lead',source_observations=[{'text':'Own electrical system architecture.'}])
        self.assertFalse(prepare(decision(),snippet,{'cv_text':CV},[])['recommend'])
        self.assertTrue(prepare(decision(),full_job(),{'cv_text':CV},[])['recommend'])
        supplied={**full_job(),'description_source':{'kind':'user_supplied'}}
        self.assertFalse(prepare(decision(),supplied,{'cv_text':CV},[])['recommend'])
        bad=decision();bad['evidence'][0]['job_quote']='Indexed source only'
        self.assertFalse(prepare(bad,full_job(),{'cv_text':CV},[])['recommend'])

    def test_full_context_keeps_requirements_tail_and_avoids_duplicate_snippets(self):
        job=full_job();job['description']='Responsibilities. '*650+'Mandatory synthetic qualification at the end.'
        job['partial_source_text']={'text':'Duplicate partial page body'}
        sent=context(job)
        self.assertIn('Mandatory synthetic qualification at the end.',sent['description'])
        self.assertEqual(sent['source_observations'],[])
        self.assertEqual(sent['partial_source_text'],'')

    def test_private_profile_does_not_repeat_cv_experience_or_identical_goals(self):
        profile={'cv_text':CV,'looking_for':'Original next move','authoritative_request':'Original next move',
                 'intent':{'experience':[{'text':'Already in the CV','quote':CV}],'preferences':[{'value':'Preserved preference'}]}}
        sent=private_profile(profile)
        self.assertEqual(sent['cv_text'],CV)
        self.assertEqual(sent['authoritative_request'],'Original next move')
        self.assertNotIn('looking_for',sent)
        self.assertNotIn('experience',sent['intent'])
        self.assertEqual(profile['intent']['experience'][0]['quote'],CV)

    def test_global_triage_finishes_before_source_work_and_preserves_ai_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=Store(root/'state.sqlite3',v5=True)
            store.set('profile',{**copy.deepcopy(PROFILE),'markets':PROFILE['markets'][:1]})
            class RankedAI(ScriptedAI):
                def __init__(self):super().__init__();self.ranked=[];self.triaged=set()
                def run(self,kind,task,data,**kwargs):
                    if kind=='research_v5':
                        self.calls.append((kind,task,data,kwargs));jobs=[{**candidate(123456+i),'url':'https://employer.example/jobs/'+str(123456+i)} for i in range(73)]
                        self.telemetry={'web_calls':1,'observations':[dict(url=j['url'],title=j['title'],snippet='Synthetic Berlin, Germany. Own electrical system architecture.') for j in jobs]}
                        for j in jobs:j['description_sources']=[{'url':j['url'],'employer_url':''}]
                        return dict(jobs=jobs,summary='Synthetic',limitations=[],continue_research=True,next_avenues=['Unneeded broader discovery'])
                    if kind=='enrichment':
                        self.calls.append((kind,task,data,kwargs));self.telemetry={}
                        self.triaged.update(j['id'] for j in data['jobs'])
                        # A bounded provider sees only this packet. Its declared
                        # order still must control verification, never ID order.
                        chosen=[j['id'] for j in data['jobs'][:2]][::-1] if not self.ranked else []
                        if chosen:self.ranked=chosen
                        return dict(candidate_ids=chosen,reason='Source duties support these next steps, ordered by fit')
                    if kind=='priority_v52':
                        self.calls.append((kind,task,data,kwargs));self.telemetry={}
                        return {'assessments':[decision(j['id']) for j in data['jobs']]}
                    return super().run(kind,task,data,**kwargs)
            ai=RankedAI();attempts=[]
            def recover(job,*args):
                attempts.append(job['id'])
                self.assertEqual(len(ai.triaged),73)
                return dict(description=full_job()['description'],source_url=job['url'],evidence={'sha256':'synthetic'},title=job['title'],company=job['company'],location=job['location'])
            with patch('job_radar_ai.session_search.recover',side_effect=recover),patch('job_radar_ai.session_search.linkedin_state',return_value={'state':'available'}):
                run=store.start_run('codex')
                fetcher=PublicFetcher(store,request=lambda _:self.fail('No live publisher requests'))
                SessionSearch(root,store).execute(run,threading.Event(),ai=ai,fetcher=fetcher)
            selected=[j for j in store.jobs() if j.get('shortlist_status')=='selected']
            self.assertEqual(len(selected),2)
            self.assertEqual(len(store.jobs()),73)
            self.assertEqual(len(ai.triaged),73)
            self.assertTrue(all(len(data['jobs'])<=8 for kind,_,data,_ in ai.calls if kind=='enrichment'))
            self.assertEqual(sum(k=='research_v5' for k,_,_,_ in ai.calls),1)
            self.assertEqual([j['id'] for j in sorted(selected,key=lambda j:j['shortlist_rank'])],ai.ranked)
            self.assertEqual(attempts,ai.ranked)

    def test_verification_scheduler_only_batches_ready_candidates_within_context_bound(self):
        from job_radar_ai.verification import assessment_batches,ranked_candidates
        jobs=[{**full_job('high'),'shortlist_rank':0},{**full_job('lower'),'shortlist_rank':1},
              dict(id='missing',shortlist_rank=2,source_observations=[{'text':'Unknown duties'}])]
        self.assertEqual([j['id'] for j in ranked_candidates(list(reversed(jobs)))],['high','lower','missing'])
        batches=list(assessment_batches(jobs))
        self.assertEqual([j['id'] for b in batches for j in b],['high','lower'])
        self.assertTrue(all(len(b)<=2 for b in batches))
        huge={**full_job('huge'),'description':'Actual duty. '*3000}
        self.assertEqual(len(list(assessment_batches([huge,full_job('small')]))),2)
