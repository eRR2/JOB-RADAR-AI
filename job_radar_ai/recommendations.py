"""AI career suitability, independent of evidence confidence; no keyword scores."""
import hashlib
import json
from .hunter import profile_signature, source_context
from .store import now
from .availability import closed_for_review

POLICY = 'weekly-verified-v2'
PRIORITIES = {'exceptional': 4, 'strong': 3, 'consider': 2, 'weak': 1, 'unsuitable': 0}
TASK = '''Assess EVERY supplied exact vacancy identity against the actual CV and authoritative
next-career request. Career suitability and evidence confidence are separate. Strong preliminary
fit signals are permitted, but final recommendations require complete publisher duties
and requirements. Missing responsibilities remain unknown. Transferability or
title similarity alone is insufficient. Assess ownership, seniority, technical leadership versus
formal people management, credible progression and critical specialist-domain requirements.
Do not optimistically rationalize every stretch or reject credible cross-industry progression.
Explain the worthwhile NEXT step, directly supporting CV capabilities, and important gaps.
Copy evidence job_quote and cv_quote verbatim from supplied job evidence and actual CV;
never quote your own interpretation. A critical unmet specialist requirement blocks a strong
recommendation; technology examples are not universal exclusions. Explain uncertainty instead
of inventing responsibilities, location, freshness or rejection reasons. Give a qualitative
priority exceptional/strong/consider/weak/unsuitable, not an ATS percentage. Recommend only
exceptional/strong opportunities with verified full publisher descriptions, literal
duty/requirement evidence and a convincing next step. Snippets and partial text are
verification candidates, never final strong recommendations.
Application and Obsolete state exclude this exact posting, never other employer postings.
Application state does not change technical suitability, category or specialist gaps;
an already-applied direct fit remains a direct fit with no new-application recommendation.
Use feedback ONLY in the supplied country scope. Return one assessment for each job.'''
TASK += ' Keep each next_step under 80 words. Use one or two SHORT exact evidence pairs and at most three material gaps per job; no repetitive prose.'
TASK += ''' Explain WHY suitable, the key unmet skills, whether this is real decision
authority or only coordination, and what compromise is needed. State salary, hours and
hybrid only when found in the supplied posting; distinguish posted compensation from
an estimate. For Dutch roles, report employer ruling support only if explicitly evidenced
by the posting. Personal tax eligibility is ALWAYS unverified and must not be inferred.
Company brand or nominal Manager/Architect title is not a proxy for seniority or relevance.
Never fill Recommended with weak matches merely to reach a target count.'''
TASK += ''' Return authority, tradeoffs, work_arrangement, salary_evidence,
hours_evidence, ruling_employer_support, ruling_quote and ruling_eligibility.
Use empty strings for unknown terms. Salary, hours and work_arrangement must be
SHORT exact source quotations, not estimates. Ruling support means explicit
employer assistance: merely mentioning the scheme is insufficient. Use
not_supported for an explicit refusal, unknown otherwise, and copy ruling_quote
verbatim for either supported or not_supported. Show personal eligibility as
unverified. Authority is a cautious assessment supported by the evidence pairs.'''
TASK += ''' For snippet/partial evidence, keep next_step under 45 words: state only
the known capability match, then the missing responsibility or requirement that
prevents a full decision. Use at most one SHORT evidence pair and two material gaps.
Do not repeat generic uncertainty, inferred salary guarantees or employer reputation.
Title-derived field hints are unverified publication metadata, not confirmed terms.'''



def active(job):
    return not (job.get('obsolete') or job.get('identity_review_required') or
                closed_for_review(job) or
                job.get('application_status', 'none') not in ('none', 'saved'))


def verified_description(job):
    return bool(job.get('description_source',{}).get('kind') in ('public_verified','linkedin')
                and 100<=len(job.get('description',''))<=60000)


def evidence_text(job):
    # A source quote can be taken from either a publisher description or its
    # separately observed snippet. Both have immutable provenance.
    return '\n'.join(filter(None, [job.get('description', ''),
        (job.get('partial_source_text') or {}).get('text', '')] +
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
    for quote_field in ('salary_evidence','hours_evidence','work_arrangement','ruling_quote'):
        if item.get(quote_field) and not exact_quote(item[quote_field],evidence_text(job)):
            item = {**item,quote_field:''}
    if item.get('ruling_employer_support') in ('stated','not_supported') and not item.get('ruling_quote'):
        item = {**item, 'ruling_employer_support':'unknown'}
    if item.get('ruling_eligibility') != 'not_applicable':
        item = {**item, 'ruling_eligibility':'unverified'}
    result = {**item, 'policy': POLICY, 'at': now(), 'signature': signature(job, profile, feedback), 'market_id': profile.get('market', {}).get('id') if feedback else None}
    if not job.get('description'):
        result['next_step']=' '.join(result['next_step'].split()[:45])
        result['gaps']=[' '.join(g.split()[:25]) for g in result['gaps'][:2]]
    metadata={str(job.get(k,'')).strip().casefold() for k in ('title','company','location','country')}
    duty_evidence=any(exact_quote(e['job_quote'],job.get('description','')) and e['job_quote'].strip().casefold() not in metadata for e in item['evidence'])
    result['recommend'] = bool(verified_description(job) and duty_evidence and item['recommend'] and item['priority'] in ('exceptional', 'strong')
                               and item['category'] not in ('unrelated', 'needs_verification')
                               and item['next_step'].strip() and item['evidence']
                               and not item['critical_gap'] and active(job))
    if profile.get('market'):
        from .geography import location_status
        if location_status(job,profile,profile['market']) == 'outside_preferred':
            # Location is a preference/trade-off, not an automatic disqualification.
            result['location_tradeoff'] = True
            note = 'Outside preferred location; confirm remote eligibility or relocation.'
            result['tradeoffs'] = ' '.join(filter(None,[result.get('tradeoffs',''),note]))
    return result


def context(job):
    # Send only bounded source evidence to avoid reprocessing entire indexed
    # search pages in every evaluation call. Exact quotes remain verifiable
    # against the full stored observations.
    return {**source_context(job),
            # A final recommendation must see conditions at the end too. Large
            # complete descriptions are isolated by the bounded batch scheduler.
            'description': (job.get('description') or '')[:60000],
            'partial_source_text': '' if verified_description(job) else (job.get('partial_source_text') or {}).get('text', '')[:3000],
            'source_observations': [] if verified_description(job) else [{'url':o.get('url',''),'text':o.get('text','')[:1600]}
                                    for o in job.get('source_observations',[])[:2]],
            'evidence_confidence': 'full_source' if job.get('description_source', {}).get('kind') in ('public_verified', 'linkedin') and job.get('description') else 'user_supplied' if job.get('description') else 'partial_source' if job.get('partial_source_text') else 'snippet',
            'inferred_fields':job.get('inferred_fields',{}),
            'application_status': job.get('application_status', 'none'), 'obsolete': bool(job.get('obsolete'))}


def private_profile(profile):
    # Preserve all decision-bearing intent, not transport/onboarding/diagnostic fields.
    fields=('cv_text','authoritative_request','looking_for','intent','market','hard_requirements','objectives','seniority','leadership','industries','unwanted','salary','hours','workplace','commute','relocation','learned_preferences')
    value={k:profile[k] for k in fields if k in profile}
    if value.get('authoritative_request')==value.get('looking_for'):value.pop('looking_for',None)
    if isinstance(value.get('intent'),dict):
        value['intent']={k:v for k,v in value['intent'].items() if k!='experience'}
    return value


def assess(ai, store, jobs, profile, feedback, **kwargs):
    """Validate and persist EACH decision, never losing an entire AI batch."""
    eligible = [j for j in jobs if active(j)]
    pending = [j for j in eligible if
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
                                  'preliminary':{**job.get('preliminary', {}), 'recommend':False},
                                  'evaluation_status':'needs_verification',
                                  'assessment_issue':'Source/CV evidence needs verification.'})
                rejected+=1
                continue
            update={'id':job['id'],'preliminary':decision,
                    'assessment_issue':''}
            update['evaluation_status']='assessed' if job.get('description') else 'preliminary'
            store.upsert_job(update)
            valid+=1
    return {'ai_invocations':calls,'assessed':valid,'invalid_evidence':rejected,
            'cached':len(eligible)-len(pending), 'excluded':len(jobs)-len(eligible)}

