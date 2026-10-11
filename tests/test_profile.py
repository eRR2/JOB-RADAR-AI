import io
import unittest
import zipfile
from job_radar_ai.profile import parse_cv, validate_profile
from job_radar_ai.contracts import WEIGHTS


class ProfileTests(unittest.TestCase):
    def test_text_pdf_extracts_actual_synthetic_content(self):
        stream=b'BT /F1 12 Tf 30 100 Td (Led a synthetic systems engineering team.) Tj ET'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
        content=b'%PDF-1.4\n'; offsets=[0]
        for index,obj in enumerate(objects,1):
            offsets.append(len(content));content+=str(index).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
        start=len(content)
        content+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
        content+=b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF'
        self.assertIn('Led a synthetic systems engineering team.',parse_cv('cv.pdf',content))
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
