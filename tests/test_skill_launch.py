import json
import os
import subprocess
import shutil
import tempfile
import venv
import unittest
import socket
import time
import urllib.request
from pathlib import Path


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell launcher')
class SkillLaunchTests(unittest.TestCase):
    def launch(self, *args, script=None):
        return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                               str(script or Path('scripts/launch-skill.ps1').resolve()), *args],
                              capture_output=True, text=True, timeout=20)

    def copy_launcher(self, folder):
        target = Path(folder) / 'scripts'
        target.mkdir()
        for name in ('launch-skill.ps1', 'runtime-manifest.json'):
            shutil.copyfile(Path('scripts') / name, target / name)
        return target / 'launch-skill.ps1'

    def test_current_runtime_probe_and_managed_only_probe_do_not_install(self):
        result = self.launch('-Check')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertFalse(state['system_install'])
        self.assertEqual(state['storage'], '.private')
        managed = self.launch('-Check', '-ManagedOnly')
        self.assertEqual(managed.returncode, 0, managed.stderr)
        self.assertIn('bootstrap_required', json.loads(managed.stdout))

    def test_missing_managed_runtime_requires_approval_before_download(self):
        Path('.private').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path('.private').resolve()) as folder:
            script = self.copy_launcher(folder)
            result = self.launch('-ManagedOnly', '-NoBrowser', script=script)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('BOOTSTRAP_APPROVAL_REQUIRED', result.stdout)
            self.assertFalse((Path(folder) / '.private').exists())

    def test_incomplete_python_environment_is_a_missing_prerequisite(self):
        Path('.private').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path('.private').resolve()) as folder:
            script = self.copy_launcher(folder)
            venv.EnvBuilder(with_pip=False).create(Path(folder) / '.venv')
            result = self.launch('-Check', script=script)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['python_ready'])

    def test_database_path_cannot_escape_private_workspace(self):
        for path in ['state.sqlite3', '.private/../../escape.sqlite3', '.private/state.txt']:
            result = self.launch('-Check', '-Database', path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Database must', result.stderr)

    def test_first_launch_returns_without_inheriting_agent_pipes_and_reuses_workspace(self):
        Path('.private').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path('.private').resolve()) as folder:
            database=str((Path(folder)/'fresh.sqlite3').relative_to(Path.cwd()))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            url=f'http://127.0.0.1:{port}'
            try:
                first=self.launch('-NoBrowser','-Database',database,'-Port',str(port))
                self.assertEqual(first.returncode,0,first.stdout+first.stderr)
                initial=json.loads(first.stdout)
                self.assertTrue(initial['ready']); self.assertFalse(initial['browser_requested'])
                second=self.launch('-NoBrowser','-Database',database,'-Port',str(port))
                self.assertEqual(second.returncode,0,second.stderr)
                self.assertEqual(json.loads(second.stdout)['workspace_id'],initial['workspace_id'])
                with urllib.request.urlopen(url+'/api/state') as response: state=json.load(response)
                self.assertEqual(state['jobs'],[]); self.assertIsNone(state['profile'])
                self.assertTrue(state['skill_mode'])
            finally:
                try:
                    with urllib.request.urlopen(url+'/api/state') as response: state=json.load(response)
                    request=urllib.request.Request(url+'/api/close',data=b'{}',headers={'Content-Type':'application/json','Origin':url,'X-Radar-CSRF':state['csrf']})
                    with urllib.request.urlopen(request): pass
                    for _ in range(20):
                        try:
                            urllib.request.urlopen(url+'/api/health',timeout=.2).close()
                            time.sleep(.1)
                        except OSError: break
                except OSError: pass
