"""Evidence-aware work status; no career scoring or invented assessments."""
from .availability import closed_for_review


def review_state(job, diagnostics=None):
    if closed_for_review(job):
        return {'status': 'excluded', 'reason': 'confirmed_closed'}
    if job.get('application_status', 'none') not in ('none', 'saved'):
        return {'status': 'excluded', 'reason': 'application_recorded'}
    if job.get('obsolete') or job.get('identity_review_required'):
        return {'status': 'excluded', 'reason': 'identity_or_obsolete_review'}
    if job.get('evaluation_status') == 'needs_verification' or job.get('preliminary_stale'):
        return {'status': 'needs_verification', 'reason': 'evidence_validation'}
    if job.get('preliminary'):
        return {'status': 'assessed', 'reason': 'source_based_assessment'}
    if job.get('shortlist_status') == 'low_relevance':
        return {'status': 'not_selected', 'reason': 'triage_not_selected' if job.get('triage_decision') else 'triage_reason_missing'}
    triage=job.get('triage_review') or {}
    if triage.get('status') in ('pending','failed'):
        return {'status':'pending','reason':triage['reason']}
    failed_triage=next((call for call in (diagnostics or {}).get('ai_calls',[]) if
        call.get('kind')=='enrichment' and call.get('status')=='failed' and job['id'] in call.get('job_ids',[])),None)
    if failed_triage:
        return {'status':'pending','reason':'triage_timeout' if failed_triage.get('category')=='time_window' else 'triage_error'}
    recorded = job.get('review_state') or (diagnostics or {}).get('review_states', {}).get(job['id'])
    if recorded:
        return recorded
    failures = [f for f in (diagnostics or {}).get('failures', []) if f.get('phase') == 'evaluation']
    country = job.get('review_country') or job.get('country') or 'Location unverified'
    relevant = next((f for f in failures if job['id'] in f.get('job_ids',[])), None)
    relevant = relevant or next((f for f in failures if 'job_ids' not in f and f.get('country') == country), None)
    reason = (relevant or {}).get('reason', '')
    if reason == 'time_window':
        return {'status': 'pending', 'reason': 'evaluation_timeout'}
    if reason in ('phase_budget', 'total_budget', 'invocation_budget') or any(f.get('reason') in ('phase_budget','total_budget','invocation_budget') for f in failures):
        return {'status': 'pending', 'reason': 'evaluation_budget'}
    if relevant:
        return {'status': 'pending', 'reason': 'evaluation_error'}
    stop=(diagnostics or {}).get('stop',{})
    if stop.get('reason') not in (None,'completed','completed_with_limitations'):
        if not job.get('shortlist_status'):
            return {'status':'pending','reason':'triage_not_reached'}
        if stop.get('reason')=='canceled':
            return {'status':'pending','reason':'canceled'}
        return {'status':'pending','reason':'evaluation_budget' if stop.get('reason') in ('phase_budget','total_budget','invocation_budget') else 'evaluation_timeout' if stop.get('reason')=='time_window' else 'evaluation_error'}
    return {'status': 'pending', 'reason': 'not_started'}


def coverage(jobs, diagnostics=None):
    counts = dict(total=len(jobs), selected=0, assessed=0, excluded=0, pending=0,
                  needs_verification=0, not_selected=0, verified_assessed=0, source_pending=0)
    from .recommendations import verified_description,active
    for job in jobs:
        state = review_state(job, diagnostics)
        if state['status'] != 'not_selected':
            counts['selected'] += 1
            counts[state['status']] += 1
            if state['status']=='assessed' and verified_description(job):counts['verified_assessed']+=1
            if active(job) and not verified_description(job):counts['source_pending']+=1
        else:
            counts['not_selected'] += 1
    return counts


def compared_opportunities(jobs):
    """Compare saved AI judgments; transport code adds no new suitability claims."""
    from .recommendations import verified_description,PRIORITIES,active
    eligible=[j for j in jobs if active(j) and verified_description(j) and
              review_state(j)['status']=='assessed' and j.get('preliminary',{}).get('signature')]
    eligible.sort(key=lambda j:-PRIORITIES.get(j['preliminary'].get('priority'),-1))
    return [{'job_id':j['id'],'assessment_signature':j['preliminary']['signature'],
             'title':j.get('title',''),'company':j.get('company',''),
             'country':j.get('country',''),**{k:j['preliminary'].get(k,'' if k not in ('gaps','evidence') else [])
                 for k in ('priority','next_step','gaps','evidence','authority','tradeoffs','salary_evidence','hours_evidence','work_arrangement')}}
            for j in eligible]
