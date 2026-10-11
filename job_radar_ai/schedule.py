"""Local wall-clock scheduling; never claims execution while computer is off."""
from datetime import datetime, timedelta
import os
import subprocess


def due_slot(profile, moment=None, previous=None):
    moment = moment or datetime.now().astimezone()
    frequency = profile.get('frequency', 'manual')
    if frequency == 'manual' or moment.strftime('%H:%M') < profile.get('time', '09:00'):
        return None
    if frequency == 'weekly' and moment.weekday() != profile.get('weekday', 0):
        return None
    slot = moment.strftime('%Y-%m-%d') + ':' + frequency + ':' + profile.get('time', '09:00')
    return slot if slot != previous else None


def catchup_slot(profile, moment=None, previous=None):
    """Offer only the latest missed local slot, never a backlog of searches."""
    moment = moment or datetime.now().astimezone()
    frequency = profile.get('frequency', 'manual')
    if frequency == 'manual':
        return None
    day = moment.date()
    if moment.strftime('%H:%M') < profile.get('time', '09:00'):
        day -= timedelta(days=1)
    if frequency == 'weekly':
        day -= timedelta(days=(day.weekday() - profile.get('weekday', 0)) % 7)
    slot = day.isoformat() + ':' + frequency + ':' + profile.get('time', '09:00')
    return slot if slot != previous else None


def task_command(python, root):
    return f'"{python}" "{root}/runner.py" --root "{root}" --scheduled'


def install_task(python, root, profile):
    if os.name != 'nt':
        raise ValueError('Native scheduled task setup is available on Windows only.')
    if profile['frequency'] == 'manual':
        raise ValueError('Choose daily or weekly first.')
    args = ['schtasks.exe', '/Create', '/TN', 'JOB-RADAR-AI', '/TR', task_command(python, root),
            '/SC', 'DAILY' if profile['frequency'] == 'daily' else 'WEEKLY', '/ST', profile['time'], '/RL', 'LIMITED', '/IT']
    if profile['frequency'] == 'weekly':
        args += ['/D', ['MON','TUE','WED','THU','FRI','SAT','SUN'][profile['weekday']]]
    # No /F: never overwrite an existing operating-system task.
    result = subprocess.run(args, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError('Windows task creation failed (existing task or insufficient permissions). Check Task Scheduler; nothing was overwritten.')
    return 'Windows task created. Runs only while this computer is on and you are logged in.'
