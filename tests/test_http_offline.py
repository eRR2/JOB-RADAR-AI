"""Execute real HTTP handlers with in-memory streams; no socket or live providers.

These tests supplement, not replace, the loopback integration suite.
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from job_radar_ai.server import make_server
from job_radar_ai.session_search import SessionSearch
from job_radar_ai.store import SessionExpired
from test_clean_search import PROFILE, CV


class MemoryServer:
    def __init__(self, address, handler):
        self.server_port = address[1]
        self.RequestHandlerClass = handler


class OfflineHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'version.json').write_text(json.dumps({'version':'5.3.0-preview'}))
        with patch('job_radar_ai.server.ThreadingHTTPServer', MemoryServer):
            self.server = make_server(self.root, self.root / 'state.sqlite3', 8879, skill_mode=True)
        self.app = self.server.app
        self.app.store.set('profile',{**PROFILE,'intent_confirmed':True})
        self.app.store.set('cv_text',CV)
        self.app.store.set('providers',{})
        self.job = dict(id='synthetic',url='https://example.invalid/jobs/101',title='Systems Lead',
                        company='Company Alpha',location='City A',requisition_id='101')
        self.app.store.upsert_job(self.job)

    def request(self, path, data=None, headers=None):
        handler = object.__new__(self.server.RequestHandlerClass)
        handler.server = self.server
        handler.path = path
        handler.headers = {'Host':'127.0.0.1:8879','Origin':'http://127.0.0.1:8879',
                           'X-Radar-CSRF':self.app.csrf,**(headers or {})}
        captured = []
        handler.response = lambda status,content,*args,**kwargs: captured.append((status,content))
        if data is None:
            handler.do_GET()
        else:
            raw = json.dumps(data).encode()
            handler.headers['Content-Length'] = str(len(raw))
            handler.headers['Content-Type'] = 'application/json'
            handler.rfile = io.BytesIO(raw)
            handler.connection = SimpleNamespace(settimeout=lambda _:None)
            handler.do_POST()
        return captured[0]

    def test_origin_host_and_csrf_guards_refuse_mutations(self):
        for headers in ({'Origin':'https://evil.invalid'},{'Host':'evil.invalid'},
                        {'X-Radar-CSRF':'wrong'},{'Sec-Fetch-Site':'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/application',{'job_id':'synthetic','status':'rejected'},headers)[0],403)
        self.assertEqual(self.app.store.jobs()[0]['application_status'],'none')

    def test_only_readonly_selected_mail_folder_can_import_and_export_history(self):
        message = dict(subject='Company Alpha - 101',bodyPreview='We regret to inform you.')
        self.assertEqual(self.request('/api/outlook-history-import',{'folder':'Inbox','messages':[message]})[0],422)
        status, result = self.request('/api/outlook-history-import',{'folder':'Job Radar','messages':[message]})
        self.assertEqual(status,200)
        self.assertEqual(result['matched'],1)
        status, exported = self.request('/api/export')
        self.assertEqual(status,200)
        self.assertEqual(exported['job_history'][0]['application_status'],'rejected')

    def test_search_preserves_history_and_expires_previous_worker_without_inference(self):
        old_worker = self.app.hunter.store
        self.app.store.application('synthetic','rejected')
        with patch('job_radar_ai.server.Provider') as provider, patch.object(SessionSearch,'start',return_value=42):
            status, result = self.request('/api/search',{})
            provider.assert_not_called()
        self.assertEqual(status,200)
        self.assertEqual(result['run_id'],42)
        self.assertEqual(self.app.store.jobs(),[])
        self.assertEqual(self.app.store.export()['job_history'][0]['application_status'],'rejected')
        with self.assertRaises(SessionExpired):
            old_worker.upsert_job(self.job)

    def test_private_files_and_removed_research_routes_are_inaccessible(self):
        self.assertEqual(self.request('/.private/state.sqlite3')[0],404)
        for route in ('/api/reevaluate','/api/reprioritize','/api/complete-descriptions'):
            with self.subTest(route=route):
                self.assertEqual(self.request(route,{})[0],422)
