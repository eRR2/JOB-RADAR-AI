"""Bounded child worker: receives a public URL only, never career context."""
import json
import sys
from .sources import request_public, RetrievalError

if __name__ == '__main__':
    try:
        print(json.dumps(request_public(sys.argv[1]), ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, RetrievalError) else 'Public retrieval failed; no retry.',
                          'status': getattr(exc, 'status', 'failed'),'http_status':getattr(exc,'http_status',None)}))
        sys.exit(1)
