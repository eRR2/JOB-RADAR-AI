import io
import unittest
import zipfile
from job_radar_ai.profile import parse_cv, validate_profile
from job_radar_ai.contracts import WEIGHTS


class ProfileTests(unittest.TestCase):
    def test_docx_extracts_synthetic_cv_and_redacts_contact(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Led a synthetic engineering team. contact@example.invalid</w:t></w:r></w:p></w:document>')
        text = parse_cv('cv.docx', data.getvalue())
        self.assertIn('Led a synthetic engineering team.', text)
        self.assertNotIn('contact@example.invalid', text)

    def test_wrong_type_and_empty_pdf_fail_without_faking_cv(self):
        with self.assertRaises(ValueError):
            parse_cv('cv.exe', b'content')
        with self.assertRaises(ValueError):
            parse_cv('cv.pdf', b'not pdf')

    def test_user_fields_are_editable_without_json_and_provider_enum_is_checked(self):
        value = {'provider': 'codex', 'objectives': 'Lead synthetic team', 'weights': {k: 1 for k in WEIGHTS}, 'consent': True, 'linkedin_consent': True, 'frequency': 'manual', 'time': '09:00', 'weekday': 0}
        self.assertAlmostEqual(sum(validate_profile(value)['weights'].values()), 100, places=4)
        with self.assertRaises(ValueError):
            validate_profile({**value, 'provider': 'arbitrary command'})
