import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from job_radar_ai.schedule import catchup_slot
from job_radar_ai.server import Application


class CatchupTests(unittest.TestCase):
    def test_weekly_missed_day_and_daily_before_time_offer_latest_slot(self):
        moment = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
        profile = {'frequency': 'daily', 'time': '09:00', 'weekday': 0}
        self.assertEqual(catchup_slot(profile, moment), '2026-10-13:daily:09:00')
        self.assertEqual(catchup_slot({**profile, 'frequency': 'weekly'}, moment),
                         '2026-10-12:weekly:09:00')
        self.assertIsNone(catchup_slot({**profile, 'frequency': 'manual'}, moment))

    def test_consumed_slot_is_not_reoffered_but_new_slot_is(self):
        profile = {'frequency': 'daily', 'time': '09:00'}
        moment = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
        slot = catchup_slot(profile, moment)
        self.assertIsNone(catchup_slot(profile, moment, previous=slot))
        self.assertIsNotNone(catchup_slot(profile, moment, previous='2026-10-13:daily:09:00'))

    def test_reminder_survives_restart_without_consuming_due_search(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'state.sqlite3'
            app = Application(Path.cwd(), database, skill_mode=True)
            app.store.set('profile', {'frequency': 'daily', 'time': '00:00'})
            slot = app.catchup()['slot']
            app.catchup_action({'action': 'later', 'slot': slot})
            restarted = Application(Path.cwd(), database, skill_mode=True)
            self.assertIsNone(restarted.catchup())
            self.assertIsNone(restarted.store.get('schedule_slot'))
            restarted.store.set('catchup_reminder', {'slot': slot, 'until': '2000-01-01T00:00:00+00:00'})
            self.assertEqual(restarted.catchup()['slot'], slot)

    def test_skip_persists_and_stale_or_duplicate_actions_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(Path.cwd(), Path(folder) / 'state.sqlite3', skill_mode=True)
            app.store.set('profile', {'frequency': 'daily', 'time': '00:00'})
            slot = app.catchup()['slot']
            with self.assertRaises(ValueError):
                app.catchup_action({'action': 'skip', 'slot': 'stale'})
            app.catchup_action({'action': 'skip', 'slot': slot})
            self.assertIsNone(app.catchup())
            self.assertEqual(app.store.runs()[0]['status'], 'skipped')
            with self.assertRaises(ValueError):
                app.catchup_action({'action': 'run', 'slot': slot})

    def test_failed_start_does_not_consume_slot_and_skill_scheduler_never_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(Path.cwd(), Path(folder) / 'state.sqlite3', skill_mode=True)
            app.store.set('profile', {'frequency': 'daily', 'time': '00:00'})
            slot = app.catchup()['slot']
            with patch.object(app.hunter, 'start', side_effect=ValueError('No consent')):
                with self.assertRaises(ValueError):
                    app.catchup_action({'action': 'run', 'slot': slot})
            self.assertIsNone(app.store.get('schedule_slot'))
            with patch.object(app.hunter, 'start') as start:
                app.scheduler(None)
                start.assert_not_called()

    def test_run_now_records_one_attempt_and_duplicate_click_cannot_start_another(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(Path.cwd(), Path(folder) / 'state.sqlite3', skill_mode=True)
            app.store.set('profile', {'frequency':'daily', 'time':'00:00'})
            slot = app.catchup()['slot']
            with patch.object(app.hunter, 'start', return_value=7) as start:
                self.assertEqual(app.catchup_action({'action':'run', 'slot':slot})['run_id'], 7)
                with self.assertRaises(ValueError):
                    app.catchup_action({'action':'run', 'slot':slot})
                start.assert_called_once()
            restarted = Application(Path.cwd(), Path(folder) / 'state.sqlite3', skill_mode=True)
            self.assertIsNone(restarted.catchup())
