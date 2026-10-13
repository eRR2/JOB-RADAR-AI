import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.access import restriction, active, linkedin_state
from job_radar_ai.store import Store
from job_radar_ai.linkedin import LinkedIn, SourceError
from job_radar_ai.sources import PublicFetcher, RetrievalError


class AccessTests(unittest.TestCase):
    def test_retry_after_seconds_date_expiry_and_nontransient_denial(self):
        at=datetime(2026,1,1,tzinfo=timezone.utc)
        for header,seconds in [('120',120),('Thu, 01 Jan 2026 02:00:00 GMT',7200),(None,3600),('bad',3600)]:
            state=restriction(429,header,clock=at)
            self.assertTrue(active(state,at))
            self.assertFalse(active(state,at+timedelta(seconds=seconds)))
        self.assertTrue(active(restriction(403,clock=at),at+timedelta(days=365)))
        self.assertEqual(restriction(429,previous=restriction(429,clock=at),clock=at)['attempts'],2)

    def test_confirmed_response_clears_pending_cooldown_no_in_run_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            source=LinkedIn(tmp,store,threading.Event(),{'requests':20,'spacing':0})
            with patch('job_radar_ai.linkedin.executable',return_value=['bun.exe']), patch('job_radar_ai.linkedin.bounded_process',return_value=(1,'',json.dumps({'error':'ACCESS_RESTRICTED HTTP 429','http_status':429,'retry_after':'120'}))) as process:
                with self.assertRaises(SourceError):source.invoke([], 'one',0)
                self.assertFalse(store.get('linkedin_pending'))
                self.assertIsNone(store.get('linkedin_stop'))
                store.set('linkedin_access',restriction(429,clock=datetime.now(timezone.utc)-timedelta(days=2)))
                with self.assertRaises(SourceError):source.invoke([], 'two',0)
                other=LinkedIn(tmp,store,threading.Event(),{'requests':20,'spacing':0})
                with self.assertRaises(SourceError):other.invoke([], 'three',0)
                self.assertEqual(process.call_count,1)
            self.assertEqual(linkedin_state(store)['state'],'restricted')
            store.fresh_session()
            self.assertEqual(linkedin_state(store)['state'],'available')

    def test_interruption_and_public_publisher_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'v5.sqlite3',v5=True)
            store.set('linkedin_pending',True)
            self.assertEqual(linkedin_state(store)['state'],'request_in_progress')
            self.assertIsNone(store.get('linkedin_access'))
            store.recover_runs()
            self.assertEqual(linkedin_state(store)['state'],'restricted')
            self.assertTrue(store.get('linkedin_access')['session_only'])
            with patch('job_radar_ai.sources.public_url') as url:
                url.return_value.hostname='careers.example.com'
                url.return_value.scheme='https';url.return_value.netloc='careers.example.com';url.return_value.path='/';url.return_value.query=''
                fetch=PublicFetcher(store,request=lambda _:(_ for _ in ()).throw(RetrievalError('blocked','429',429,'120')))
                with self.assertRaises(RetrievalError):fetch.get('https://careers.example.com/',api=True)
                self.assertEqual(store.get('public:access:careers.example.com')['state'],'cooling_down')
                self.assertIsNone(store.get('public:stop:careers.example.com'))

    def test_v5_refuses_historical_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.sqlite3';Store(path).set('cv_text','Old private CV')
            with self.assertRaises(RuntimeError):Store(path,v5=True)
            self.assertEqual(Store(path).get('cv_text'),'Old private CV')
            clean=Store(Path(tmp)/'new.sqlite3',v5=True)
            self.assertIsNone(clean.get('profile'));self.assertEqual(clean.jobs(),[])
            with clean.db() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],5)
