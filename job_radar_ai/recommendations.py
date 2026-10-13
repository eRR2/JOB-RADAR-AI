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


def active(job):
    return not (job.get('obsolete') or job.get('identity_review_required') or
                job.get('availability') == 'closed_banner_observed' or
                job.get('freshness', {}).get('status') == 'confirmed_closed' or
                job.get('application_status', 'none') not in ('none', 'saved'))


def evidence_text(job):
    return job.get('description') or '\n'.join(o.get('text', '') for o in job.get('source_observations', []))


def signature(job, profile, feedback):
    value = [POLICY, profile_signature(profile), source_context(job), evidence_text(job), feedback]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(item, job, profile, feedback):
    from .contracts import validate
    validate('priority_v52', {'assessments': [item]})
    if item['job_id'] != job['id']:
        raise ValueError('Career assessment identity mismatch.')
    for quote in item['evidence']:
        if not quote['job_quote'].strip() or quote['job_quote'] not in evidence_text(job):
            raise ValueError('Career assessment source quote is not observed evidence.')
        if not quote['cv_quote'].strip() or quote['cv_quote'] not in profile.get('cv_text', ''):
            raise ValueError('Career assessment CV quote is not verbatim evidence.')
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
    return {**source_context(job), 'source_observations': job.get('source_observations', []),
            'evidence_confidence': 'full_source' if job.get('description_source', {}).get('kind') in ('public_verified', 'linkedin') and job.get('description') else 'user_supplied' if job.get('description') else 'partial_source' if job.get('partial_source_text') else 'snippet',
            'application_status': job.get('application_status', 'none'), 'obsolete': bool(job.get('obsolete'))}


def private_profile(profile):
    # Preserve all decision-bearing intent, not transport/onboarding/diagnostic fields.
    fields=('cv_text','authoritative_request','looking_for','intent','market','hard_requirements','objectives','seniority','leadership','industries','unwanted','salary','hours','workplace','commute','relocation','learned_preferences')
    return {k:profile[k] for k in fields if k in profile}


def assess(ai, store, jobs, profile, feedback, **kwargs):
    """Bounded response envelopes, not a total job quota. Persist each valid batch."""
    pending = [j for j in jobs if active(j) and j.get('preliminary', {}).get('signature') != signature(j, profile, feedback)]
    calls = 0
    for start in range(0, len(pending), 20):
        batch = pending[start:start + 20]
        result = ai.run('priority_v52', TASK, {'profile': private_profile(profile), 'feedback': feedback, 'jobs': [context(j) for j in batch]}, **kwargs)
        calls += 1
        by_id = {v['job_id']: v for v in result['assessments']}
        if len(by_id) != len(result['assessments']) or set(by_id) != {j['id'] for j in batch}:
            raise ValueError('Career assessment must cover each exact vacancy identity once.')
        prepared = [(j, prepare(by_id[j['id']], j, profile, feedback)) for j in batch]
        for job, value in prepared:
            update = {'id': job['id'], 'preliminary': value}
            if not job.get('description'):
                update['evaluation_status'] = 'preliminary'
            store.upsert_job(update)
    return {'ai_invocations': calls, 'assessed': len(pending), 'cached': len(jobs) - len(pending)}
