import json
import os
import subprocess
import shutil
import tempfile
import venv
import unittest
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
