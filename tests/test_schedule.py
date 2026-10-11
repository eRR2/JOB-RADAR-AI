import unittest
from datetime import datetime, timezone
from job_radar_ai.schedule import due_slot, task_command


class ScheduleTests(unittest.TestCase):
    def test_manual_and_before_time_are_not_due(self):
        base = {'frequency': 'daily', 'time': '09:00', 'weekday': 0}
        self.assertIsNone(due_slot({**base, 'frequency': 'manual'}, datetime(2026,10,12,10,0,tzinfo=timezone.utc)))
        self.assertIsNone(due_slot(base, datetime(2026,10,12,8,0,tzinfo=timezone.utc)))

    def test_daily_slot_is_once_per_local_day_and_weekly_day_is_respected(self):
        base = {'frequency': 'daily', 'time': '09:00', 'weekday': 0}
        moment = datetime(2026,10,12,10,0,tzinfo=timezone.utc)
        slot = due_slot(base, moment)
        self.assertIsNotNone(slot)
        self.assertIsNone(due_slot(base, moment, slot))
        self.assertIsNone(due_slot({**base, 'frequency': 'weekly', 'weekday': 2}, moment))

    def test_native_task_requires_fixed_runner_and_preserves_spaces(self):
        cmd = task_command('C:/Program Files/Python/python.exe', 'F:/Project With Spaces')
        self.assertIn('"C:/Program Files/Python/python.exe"', cmd)
        self.assertIn('--root', cmd)
        self.assertNotIn('powershell', cmd)
