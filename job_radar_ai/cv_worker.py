"""Short-lived CV parser; original uploads never become executable paths."""
import json
import sys
from pathlib import Path
from .profile import parse_cv

if __name__ == '__main__':
    try:
        path = Path(sys.argv[1])
        print(json.dumps({'text': parse_cv(path.name, path.read_bytes())}))
    except Exception:
        print(json.dumps({'error': 'CV parsing failed. Use an unencrypted text PDF or DOCX up to 10 MB; scanned PDFs require OCR.'}))
        sys.exit(1)
