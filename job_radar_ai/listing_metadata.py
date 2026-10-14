"""Literal search-title hints, separate from verified identity/source facts."""
import re


def source_title_fields(job):
    title = job.get('title', '')
    observed = '\n'.join(o.get('text', '') for o in job.get('source_observations', []))
    if not title or title not in observed:
        return job
    hints = dict(job.get('inferred_fields') or {})

    def hint(field, value, **extra):
        if value and not job.get(field) and field not in hints:
            hints[field] = dict(value=value.strip(), kind='source_title', quote=title,
                                url=job.get('url', ''), verified=False, **extra)

    # Parse publication header syntax, never infer career suitability or geography.
    header = re.sub(r'\s*\|\s*LinkedIn(?: Jobs)?\s*$', '', title, flags=re.I)
    if header != title:
        match = re.match(r'^.+?\s+(?:bei|at)\s+(.+?)\s+[—–]\s+(.+)$', header)
        if not match:
            match = re.match(r'^(.+?)\s+(?:hiring|sucht)\s+.+\s+in\s+(.+)$', header)
        if match:
            hint('company', match[1])
            hint('location', match[2])
    salary = re.search(r'(?:(?:Up to|Bis zu)\s+)?\d[\d,. ]*\s*(?:EUR|€)(?=\W|$)', title, re.I)
    if salary:
        quote = salary[0].strip()
        hint('salary', quote, interpretation='advertised_upper_bound' if re.match(r'Up to|Bis zu', quote, re.I)
             else 'advertised_amount', period='not_stated')
    return {**job, 'inferred_fields': hints} if hints else job
