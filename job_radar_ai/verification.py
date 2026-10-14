"""Bounded verification scheduling from AI order, never a career classifier."""
import json
from .recommendations import active,context,verified_description


def ranked_candidates(jobs):
    return sorted(jobs,key=lambda j:(j.get('shortlist_rank',10**9),j['id']))


def triage_batches(jobs):
    """One cheap global comparison when compact evidence fits the input bound."""
    batch=[];size=0
    for job in jobs:
        item={'id':job['id'],'title':job.get('title',''),'company':job.get('company',''),
              'location':job.get('location',''),'country':job.get('country',''),
              'source_excerpt':(job.get('description') or ' '.join(o.get('text','') for o in job.get('source_observations',[])[:2]))[:650]}
        length=len(json.dumps(item))
        if batch and (len(batch)>=80 or size+length>40000):
            yield batch;batch=[];size=0
        batch.append(item);size+=length
    if batch:yield batch


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
