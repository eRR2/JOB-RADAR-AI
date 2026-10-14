import json
import tempfile
import unittest
from unittest.mock import patch,Mock
from pathlib import Path
from job_radar_ai.__main__ import main,ProcessLock


class LauncherTests(unittest.TestCase):
    def test_current_preview_rejects_scheduled_entry_before_storage_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'version.json').write_text(json.dumps({'version':'5.3.0-preview'}))
            store=Mock();store.get.side_effect=lambda key: {'consent':True,'secondary':True} if key=='profile' else None
            with patch('sys.argv',['job-radar','--root',directory,'--scheduled']),\
                 patch('job_radar_ai.__main__.Store',return_value=store) as storage,\
                 patch('job_radar_ai.__main__.ProcessLock') as lock,\
                 patch('job_radar_ai.__main__.ResearchHunter') as research,\
                 patch('job_radar_ai.__main__.Hunter') as legacy,\
                 patch('job_radar_ai.__main__.due_slot',return_value='synthetic-due'):
                with self.assertRaises(SystemExit) as rejected:
                    main()
                self.assertEqual(rejected.exception.code,2)
                storage.assert_not_called();lock.assert_not_called()
                research.assert_not_called();legacy.assert_not_called()
                self.assertFalse((root/'.private').exists())

    def test_real_process_lock_refuses_second_instance_and_can_be_reopened(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.lock'
            first=ProcessLock(path)
            try:
                with self.assertRaises(RuntimeError):
                    ProcessLock(path)
            finally:
                first.close()
            resumed=ProcessLock(path)
            resumed.close()
    def test_scheduled_interruption_cancels_and_joins_before_releasing_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            hunter=Mock();hunter.thread.join.side_effect=[KeyboardInterrupt(),None]
            store=Mock();store.get.side_effect=lambda key: {'consent':True,'linkedin_consent':True} if key=='profile' else None
            lock=Mock();order=[]
            hunter.cancel.set.side_effect=lambda:order.append('cancel')
            lock.close.side_effect=lambda:order.append('unlock')
            with patch('sys.argv',['job-radar','--root',directory,'--scheduled']),patch('job_radar_ai.__main__.Store',return_value=store),\
                 patch('job_radar_ai.__main__.ProcessLock',return_value=lock),patch('job_radar_ai.__main__.Hunter',return_value=hunter),\
                 patch('job_radar_ai.__main__.due_slot',return_value='synthetic-due'):
                main()
            hunter.cancel.set.assert_called_once()
            self.assertEqual(hunter.thread.join.call_count,2)
            self.assertEqual(order,['cancel','unlock','unlock'])  # Database and updater locks released after cancellation.
