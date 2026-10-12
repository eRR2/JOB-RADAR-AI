"""One strict structured-result contract for both CLI providers."""
import jsonschema

WEIGHTS = ['progression', 'technical', 'salary', 'flexibility', 'company', 'location', 'learning']


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
