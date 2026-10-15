"""One strict structured-result contract for both CLI providers."""
import copy
import jsonschema

WEIGHTS = ['progression', 'technical', 'salary', 'flexibility', 'company', 'location', 'learning']
TRIAGE_MAX_JOBS=8
TRIAGE_TEXT_LIMITS={'reason':300,'transferable_fit':200,'specialist_gap':200,'source_quote':240}


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def string(limit=4000):
    return {'type': 'string', 'maxLength': limit}


def array(item, limit=20):
    return {'type': 'array', 'items': item, 'maxItems': limit}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


QUERY = obj({'query': string(160), 'location': string(160), 'remote': enum('any', 'remote', 'hybrid', 'onsite'), 'reason': string(800)})
EVIDENCE = obj({'requirement': string(800), 'job_quote': string(1500), 'cv_quote': string(1500), 'assessment': string(1200)})
EVALUATION = obj({
    'job_id': string(250), 'category': enum('direct', 'transferable', 'stretch', 'unrelated', 'needs_verification'),
    'recommend': {'type': 'boolean'}, 'summary': string(),
    'scores': obj({key: {'type': ['number', 'null'], 'minimum': 0, 'maximum': 100} for key in WEIGHTS}),
    'hard_requirements': array(obj({'requirement': string(500), 'status': enum('met', 'violated', 'unknown'), 'job_quote': string(1500), 'reason': string(1000)})),
    'evidence': array(EVIDENCE), 'missing_information': array(string(1000)),
    'ats': obj({'readiness': enum('ready', 'tailoring_needed', 'significant_gaps', 'insufficient_evidence'), 'explanation': string(), 'truthful_cv_changes': array(string(1200))}),
    'hr': obj({'assessment': string(), 'strengths': array(string(1000)), 'gaps': array(string(1000)), 'interview_risks': array(string(1000))}),
})
SCHEMAS = {
    'research_guidance':obj({'focus':string(500),'transferable_capabilities':array(string(200),4),
        'specialist_gaps':array(string(200),4),'unsuccessful_queries':array(string(160),4),
        'missing_sources':array(string(200),4),'next_queries':array(string(160),3),'continue_research':{'type':'boolean'}}),
    'enrichment':obj({'candidate_ids':array(string(250),40),'reason':string(1500)}),
    'session_brief': obj({'background':array(string(700),12),'direction':string(1500),'country_preferences':array(obj({'country_id':string(2),'conditions':array(string(800),15)}),6)}),
    'priority_v52': obj({'assessments': array(obj({'job_id': string(250), 'category': enum('direct','transferable','stretch','unrelated','needs_verification'), 'recommend': {'type':'boolean'}, 'priority': enum('exceptional','strong','consider','weak','unsuitable'), 'next_step': string(3000), 'critical_gap': {'type':'boolean'}, 'gaps': array(string(1000)), 'evidence': array(EVIDENCE)}),20)}),

    'brief_v5': obj({'professional_background':array(string(1000)), 'career_direction':string(4000)}),
    'research_v5': obj({'jobs': array(obj({'url':string(2000),'title':string(500),'company':string(500),'location':string(500), 'country':string(100),'country_quote':string(2000),'geography_inference':obj({'country_id':string(2),'basis':enum('city_country_mapping','unknown'),'confidence':enum('strong','ambiguous','unknown'),'explanation':string(1000)}),'description_sources':array(obj({'url':string(2000),'employer_url':string(2000)}),5)}),20), 'summary':string(6000),'limitations':array(string(1000)), 'continue_research':{'type':'boolean'},'next_avenues':array(string(1000))}),
    'preliminary_v5': obj({'assessments':array(obj({'job_id':string(250),'category':enum('direct','transferable','stretch','unrelated','needs_verification'),'explanation':string(4000),'promising':{'type':'boolean'},'gaps':array(string(1000))}),20)}),
    'boards':obj({'boards':array(obj({'provider':enum('greenhouse','lever','ashby','smartrecruiters','workable'),'url':string(2000),'employer_url':string(2000),'query':string(160)}),2),'limitations':array(string(1000))}),
    'intent': obj({'summary': string(), 'experience': array(obj({'text':string(1000),'quote':string(1500)})),
        'preferences':array(obj({'topic':string(100),'value':string(1000),'scope':string(2),'origin':enum('explicit','cv_evidenced','inferred','unknown'),'quote':string(1500),'hard':{'type':'boolean'}}),30),
        'markets':array(obj({'id':{'type':'string','pattern':'^[A-Z]{2}$'},'country':string(100),'scope_type':enum('city','region','country','mixed'),'preferred':array(string(100),10),'secondary':array(string(100),10),'remote':enum('none','within_country','anywhere'),'relocation':{'type':'boolean'},'origin':enum('explicit','cv_evidenced','inferred'),'quote':string(1500)}),6),
        'questions':array(string(500),2)}),
    'resolve': obj({'sources': array(obj({'url': string(2000), 'employer_url': string(2000)}), 2), 'limitations': array(string(1000))}),
    'profile': obj({'summary': string(), 'strengths': array(string(1000)), 'evidence': array(string(1500)), 'gaps': array(string(1000)), 'questions': array(string(500), 3)}),
    'plan': obj({'strategy': string(), 'role_families': array(string(500), 10), 'queries': array(QUERY, 8), 'supplementary_research': {'type': 'boolean'}, 'research_queries': array(string(300), 3)}),
    'triage': obj({'detail_ids': array(string(250), 20), 'rationale': string(), 'expand_queries': array(QUERY, 2)}),
    'evaluation': obj({'evaluations': array(EVALUATION, 20), 'report': string(10000)}),
    'learning': obj({'preferences': array(obj({'text': string(1000), 'confidence': enum('tentative', 'repeated', 'explicit'), 'feedback_ids': array({'type': 'integer'}, 20)}), 20), 'explanation': string()}),
    'research': obj({'jobs': array(obj({'url': string(2000), 'employer_url': string(2000), 'title': string(500), 'company': string(500), 'location': string(500), 'requisition_id': string(200), 'description': string(30000), 'evidence_quote': string(1500)}), 3), 'limitations': array(string(1000)), 'summary': string()}),
    'probe': obj({'status': enum('ready'), 'message': string(500)}),
}


def validate(kind, value):
    try:
        jsonschema.Draft202012Validator(SCHEMAS[kind]).validate(value)
    except (jsonschema.ValidationError, TypeError) as exc:
        raise ValueError('AI returned invalid structured output; it was not applied.') from exc
    return value


def provider_schema(kind):
    """Strict wire contract; keep saved-record validation backward compatible.

    Every object, including array items, must require every declared property.
    Existing strings can use empty text for absent evidence; enums already offer
    unknown/unverified states. No evidence is invented to fill these fields.
    """
    schema = copy.deepcopy(SCHEMAS[kind])
    if kind=='research_v5':schema['properties']['jobs']['maxItems']=TRIAGE_MAX_JOBS
    if kind=='enrichment':
        schema['properties']['candidate_ids']['maxItems']=TRIAGE_MAX_JOBS
        schema['properties']['reason']['maxLength']=300
        decisions=schema['properties']['decisions']
        decisions['maxItems']=TRIAGE_MAX_JOBS
        fields=decisions['items']['properties']
        for key,limit in TRIAGE_TEXT_LIMITS.items():fields[key]['maxLength']=limit
        fields['missing_information']['maxItems']=2
        fields['missing_information']['items']['maxLength']=120

    def strict(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                node['required'] = list(node['properties'])
                node['additionalProperties'] = False
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema

# Additional findings are optional for backward compatibility with saved decisions.
# Missing terms must be unknown, never inferred from the employer's reputation.
SCHEMAS['priority_v52']['properties']['assessments']['items']['properties'].update({
    'authority': string(900),
    'tradeoffs': string(1200),
    'work_arrangement': string(900),
    'salary_evidence': string(900),
    'hours_evidence': string(900),
    'ruling_employer_support': enum('stated','not_supported','not_stated','unknown'),
    'ruling_quote': string(900),
    'ruling_eligibility': enum('unverified','not_applicable'),
})
SCHEMAS['research_v5']['properties']['jobs']['items']['properties']['requisition_id'] = string(200)
SCHEMAS['enrichment']['properties']['decisions'] = array(obj({
    'job_id':string(250),'action':enum('verify','needs_evidence','low_relevance'),
    'basis':enum('observed_mismatch','missing_evidence','unknown'),
    'reason':string(1200),'transferable_fit':string(800),'specialist_gap':string(800),
    'source_quote':string(1500),'missing_information':array(string(500),3)}),80)

