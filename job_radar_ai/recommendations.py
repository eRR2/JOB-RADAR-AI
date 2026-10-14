"""AI career suitability, independent of evidence confidence; no keyword scores."""
import hashlib
import json
from .hunter import profile_signature, source_context
from .store import now

POLICY = 'v5.2'
PRIORITIES = {'exceptional': 4, 'strong': 3, 'consider': 2, 'weak': 1, 'unsuitable': 0}
TASK = '''Assess EVERY supplied exact vacancy identity against the actual CV and authoritative
next-career request. Career suitability and evidence confidence are separate. Strong preliminary
recommendations are permitted, but missing responsibilities remain unknown. Transferability or
title similarity alone is insufficient. Assess ownership, seniority, technical leadership versus
formal people management, credible progression and critical specialist-domain requirements.
Do not optimistically rationalize every stretch or reject credible cross-industry progression.
Explain the worthwhile NEXT step, directly supporting CV capabilities, and important gaps.
Copy evidence job_quote and cv_quote verbatim from supplied job evidence and actual CV;
never quote your own interpretation. A critical unmet specialist requirement blocks a strong
recommendation; technology examples are not universal exclusions. Explain uncertainty instead
of inventing responsibilities, location, freshness or rejection reasons. Give a qualitative
priority exceptional/strong/consider/weak/unsuitable, not an ATS percentage. Recommend only
exceptional/strong opportunities supported by direct evidence and a convincing next step.
Application and Obsolete state exclude this exact posting, never other employer postings.
Use feedback ONLY in the supplied country scope. Return one assessment for each job.'''
TASK += ' Keep each next_step under 80 words. Use one or two SHORT exact evidence pairs and at most three material gaps per job; no repetitive prose.'
TASK += ''' Explain WHY suitable, the key unmet skills, whether this is real decision
authority or only coordination, and what compromise is needed. State salary, hours and
hybrid only when found in the supplied posting; distinguish posted compensation from
an estimate. For Dutch roles, report employer ruling support only if explicitly evidenced
by the posting. Personal tax eligibility is ALWAYS unverified and must not be inferred.
Company brand or nominal Manager/Architect title is not a proxy for seniority or relevance.
Never fill Recommended with weak matches merely to reach a target count.'''



def active(job):
    return not (job.get('obsolete') or job.get('identity_review_required') or
                job.get('availability') == 'closed_banner_observed' or
                job.get('freshness', {}).get('status') == 'confirmed_closed' or
                job.get('application_status', 'none') not in ('none', 'saved'))


def evidence_text(job):
    # A source quote can be taken from either a publisher description or its
    # separately observed snippet. Both have immutable provenance.
    return '\n'.join(filter(None, [job.get('description', '')] +
        [o.get('text', '') for o in job.get('source_observations', [])]))


def exact_quote(quote, source):
    """Accept only literal text, with insignificant whitespace normalized."""
    import re
    clean = lambda v: ' '.join(re.split(r'\s+', v.strip()))
    return bool(quote.strip()) and clean(quote) in clean(source)


def signature(job, profile, feedback):
    value = [POLICY, profile_signature(profile), source_context(job), evidence_text(job), feedback]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(item, job, profile, feedback):
    from .contracts import validate
    validate('priority_v52', {'assessments': [item]})
    if item['job_id'] != job['id']:
        raise ValueError('Career assessment identity mismatch.')
    for quote in item['evidence']:
        if not exact_quote(quote['job_quote'],evidence_text(job)):
            raise ValueError('Career assessment source quote is not observed evidence.')
        if not exact_quote(quote['cv_quote'],profile.get('cv_text', '')):
            raise ValueError('Career assessment CV quote is not verbatim evidence.')
    if item.get('ruling_employer_support') == 'stated':
        source = evidence_text(job).casefold()
        if 'ruling' not in source and '30%' not in source and '30 percent' not in source:
            item = {**item, 'ruling_employer_support':'unknown'}
    result = {**item, 'policy': POLICY, 'at': now(), 'signature': signature(job, profile, feedback), 'market_id': profile.get('market', {}).get('id') if feedback else None}
    result['recommend'] = bool(item['recommend'] and item['priority'] in ('exceptional', 'strong')
                               and item['category'] not in ('unrelated', 'needs_verification')
                               and item['next_step'].strip() and item['evidence']
                               and not item['critical_gap'] and active(job))
    if profile.get('market'):
        from .geography import location_status
        if location_status(job,profile,profile['market']) == 'outside_preferred':
            result['recommend'] = False
    return result


def context(job):
    # Send only bounded source evidence to avoid reprocessing entire indexed
    # search pages in every evaluation call. Exact quotes remain verifiable
    # against the full stored observations.
    return {**source_context(job),
            'description': (job.get('description') or '')[:9000],
            'source_observations': [{'url':o.get('url',''),'text':o.get('text','')[:1600]}
                                    for o in job.get('source_observations',[])[:2]],
            'evidence_confidence': 'full_source' if job.get('description_source', {}).get('kind') in ('public_verified', 'linkedin') and job.get('description') else 'user_supplied' if job.get('description') else 'partial_source' if job.get('partial_source_text') else 'snippet',
            'application_status': job.get('application_status', 'none'), 'obsolete': bool(job.get('obsolete'))}


def private_profile(profile):
    # Preserve all decision-bearing intent, not transport/onboarding/diagnostic fields.
    fields=('cv_text','authoritative_request','looking_for','intent','market','hard_requirements','objectives','seniority','leadership','industries','unwanted','salary','hours','workplace','commute','relocation','learned_preferences')
    return {k:profile[k] for k in fields if k in profile}


def assess(ai, store, jobs, profile, feedback, **kwargs):
    """Validate and persist EACH decision, never losing an entire AI batch."""
    pending = [j for j in jobs if active(j) and
               j.get('preliminary',{}).get('signature') != signature(j,profile,feedback)]
    calls=0
    valid=0
    rejected=0
    for start in range(0,len(pending),8):
        batch=pending[start:start+8]
        result=ai.run('priority_v52',TASK,{'profile':private_profile(profile),
                      'feedback':feedback,'jobs':[context(j) for j in batch]},**kwargs)
        calls+=1
        by_id={}
        for item in result.get('assessments',[]):
            job_id=item.get('job_id')
            if job_id not in {j['id'] for j in batch} or job_id in by_id:
                continue
            by_id[job_id]=item
        for job in batch:
            item=by_id.get(job['id'])
            try:
                if item is None:
                    raise ValueError('AI omitted this vacancy from its assessment.')
                decision=prepare(item,job,profile,feedback)
            except (ValueError,KeyError,TypeError):
                # Only this vacancy becomes unassessed. Do NOT relax quotation
                # provenance and do NOT call AI again automatically.
                store.upsert_job({'id':job['id'],
                                  'evaluation_status':'needs_verification',
                                  'assessment_issue':'Source/CV evidence needs verification.'})
                rejected+=1
                continue
            update={'id':job['id'],'preliminary':decision,
                    'assessment_issue':''}
            if not job.get('description'):
                update['evaluation_status']='preliminary'
            store.upsert_job(update)
            valid+=1
    return {'ai_invocations':calls,'assessed':valid,'invalid_evidence':rejected,
            'cached':len(jobs)-len(pending)}
