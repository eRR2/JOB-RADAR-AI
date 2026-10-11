import tempfile
import unittest
from unittest.mock import patch,Mock
from job_radar_ai.__main__ import main


class LauncherTests(unittest.TestCase):
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
            self.assertEqual(order,['cancel','unlock'])
