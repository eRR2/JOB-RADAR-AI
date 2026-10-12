"""Local document text extraction and editable profile boundary validation."""
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from pypdf import PdfReader
from .contracts import WEIGHTS
from .store import normalize_weights
from .markets import validate_markets, defaults

TEXT_FIELDS = ['objectives', 'seniority', 'leadership', 'industries', 'strengths', 'city', 'region', 'commute',
               'relocation', 'workplace', 'salary', 'hours', 'unwanted', 'hard_requirements', 'followup_answers']


def parse_cv(filename, data):
    if not data or len(data) > 10_000_000:
        raise ValueError('Upload a PDF/DOCX up to 10 MB.')
    suffix = Path(filename).suffix.casefold()
    try:
        if suffix == '.pdf' and data.startswith(b'%PDF-'):
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 50:
                raise ValueError('Use an unencrypted CV with at most 50 pages.')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        elif suffix == '.docx' and data.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 20_000_000:
                    raise ValueError('DOCX expanded size exceeds the safety limit.')
                xml = archive.read('word/document.xml')
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                    raise ValueError('DOCX XML entities are not supported.')
                tree = ElementTree.fromstring(xml)
                ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
                text = '\n'.join(''.join(p.itertext()) for p in tree.iter(ns + 'p'))
        else:
            raise ValueError('File contents must be a real PDF or DOCX.')
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('CV could not be read. Export an unencrypted text PDF or DOCX.') from exc
    # Contact details are not career-fit evidence. The UI previews extracted text.
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[email removed]', text)
    text = re.sub(r'https?://\S+', '[URL removed]', text)
    text = re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)', '[phone removed]', text)
    text = text.strip()
    if len(text) < 30:
        raise ValueError('No readable CV text found. Scanned PDFs need OCR; upload a text PDF or DOCX.')
    if len(text) > 60000:
        raise ValueError('CV text exceeds 60,000 characters; upload a shorter document.')
    return text


def validate_profile(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid profile.')
    allowed = set(TEXT_FIELDS) | {'provider', 'weights', 'markets', 'consent', 'linkedin_consent', 'secondary', 'frequency', 'weekday', 'time'}
    if set(value) - allowed:
        raise ValueError('Unknown profile fields.')
    result = {}
    for field in TEXT_FIELDS:
        text = value.get(field, '')
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError('Profile fields must be text up to 4,000 characters.')
        result[field] = text.strip()
    if not result['objectives']:
        raise ValueError('Describe your career objectives.')
    if value.get('provider') not in ('codex', 'claude'):
        raise ValueError('Select Codex or Claude Code.')
    result['provider'] = value['provider']
    for key in ('consent', 'linkedin_consent', 'secondary'):
        if type(value.get(key, False)) is not bool:
            raise ValueError('Consent flags must be boolean.')
        result[key] = value.get(key, False)
    # Old clients may send weights; retain them only as historical data.
    if 'weights' in value:
        if not isinstance(value['weights'], dict) or set(value['weights']) != set(WEIGHTS):
            raise ValueError('Invalid legacy weights.')
        result['weights'] = normalize_weights(value['weights'])
    result['markets'] = validate_markets(value.get('markets', defaults()))
    result['assessment_policy'] = 'evidence-v2'
    if value.get('frequency') not in ('manual', 'daily', 'weekly') or type(value.get('weekday')) is not int or not 0 <= value['weekday'] <= 6 or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(value.get('time'))):
        raise ValueError('Invalid local search schedule.')
    result.update({k: value[k] for k in ('frequency', 'weekday', 'time')})
    return result
