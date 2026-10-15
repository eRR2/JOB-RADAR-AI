"""Bounded verification scheduling from AI order, never a career classifier."""
import json
from .recommendations import active,context,verified_description,exact_quote
from .contracts import TRIAGE_MAX_JOBS,TRIAGE_TEXT_LIMITS

TRIAGE_INPUT_CHARS=40000
TRIAGE_OUTPUT_CHARS=14000


def triage_output_size(jobs):
    decisions=[{'job_id':j['id'],'action':'needs_evidence','basis':'observed_mismatch',
        **{key:'x'*limit for key,limit in TRIAGE_TEXT_LIMITS.items()},
        'missing_information':['x'*120]*2} for j in jobs]
    return len(json.dumps({'candidate_ids':[j['id'] for j in jobs],'reason':'x'*300,'decisions':decisions}))


def ranked_candidates(jobs):
    return sorted(jobs,key=lambda j:(j.get('shortlist_rank',10**9),j['id']))


def triage_batches(jobs,shared_chars=0):
    """Bound both complete private input and the per-job decision response."""
    batch=[];size=0
    for job in jobs:
        item={'id':job['id'],'title':job.get('title',''),'company':job.get('company',''),
              'location':job.get('location',''),'country':job.get('country',''),
              'evidence_completeness':'full_source' if verified_description(job) else 'partial' if job.get('partial_source_text') else 'snippet',
              'source_excerpt':(job.get('description') or ' '.join(o.get('text','') for o in job.get('source_observations',[])[:2]))[:650]}
        length=len(json.dumps(item))
        if batch and (len(batch)>=TRIAGE_MAX_JOBS or shared_chars+size+length+2>TRIAGE_INPUT_CHARS or triage_output_size(batch+[item])>TRIAGE_OUTPUT_CHARS):
            yield batch;batch=[];size=0
        batch.append(item);size+=length+2
    if batch:yield batch


def triage_decisions(selection,jobs):
    """Keep AI reasons; missing or unsupported evidence is not a mismatch."""
    by_id={j['id']:j for j in jobs};requested=selection['candidate_ids']
    if len(set(requested))!=len(requested) or not set(requested)<=set(by_id):
        raise ValueError('Enrichment selection identity mismatch.')
    decisions=selection.get('decisions')
    if decisions is None:
        return requested,{key:{'job_id':key,'action':'verify' if key in requested else 'not_selected',
            'reason':'Individual rationale was not recorded by the legacy contract.',
            'basis':'unknown','transferable_fit':'','specialist_gap':'','source_quote':'',
            'missing_information':['Individual relevance rationale']} for key in by_id}
    if len(decisions)!=len(by_id) or {d['job_id'] for d in decisions}!=set(by_id):
        raise ValueError('Every triage identity requires one individual decision.')
    retained={}
    for decision in decisions:
        item={**decision,'proposed_action':decision['action']};quote=item['source_quote']
        supported=exact_quote(quote,by_id[item['job_id']]['source_excerpt'])
        metadata_only=any(quote.strip().casefold() in str(by_id[item['job_id']].get(field,'')).casefold()
            for field in ('title','company','location','country')) if quote.strip() else False
        if quote and not supported:
            item.update(action='needs_evidence',basis='unknown',source_quote='',evidence_issue='unsupported_quote')
        if item['action']=='low_relevance' and (item['basis']!='observed_mismatch' or not supported or metadata_only or not item['reason'].strip()):
            item['action']='needs_evidence'
            item['evidence_issue']='missing_or_metadata_only_evidence'
        retained[item['job_id']]=item
    ordered=requested+[d['job_id'] for d in decisions if d['job_id'] not in requested]
    return [key for key in ordered if retained[key]['action']!='low_relevance'],retained


def assessment_batches(jobs):
    """At most two complete descriptions per call; never truncate role conditions."""
    batch=[];size=0
    for job in ranked_candidates(jobs):
        if not active(job) or not verified_description(job):continue
        length=len(json.dumps(context(job)))
        if batch and (len(batch)>=2 or size+length>24000):
            yield batch;batch=[];size=0
        batch.append(job);size+=length
    if batch:yield batch
