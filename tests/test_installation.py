"""Synthetic Windows setup boundaries; no software/network/login actions."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name=='nt','Windows setup')
class InstallationTests(unittest.TestCase):
    def setUp(self):
        Path('.private').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=Path('.private').resolve())
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.package=self.root/'package'
        (self.package/'scripts').mkdir(parents=True)
        for name in ('install-workspace.ps1','register-skill.ps1','setup-codex.ps1','runtime-manifest.json','launch-skill.ps1'):
            shutil.copyfile(Path('scripts')/name,self.package/'scripts'/name)
        (self.package/'skills/job-radar-ai').mkdir(parents=True)
        (self.package/'skills/job-radar-ai/SKILL.md').write_text('Synthetic canonical skill')
        (self.package/'README.md').write_text('Synthetic public application')
        self.target=self.root/'installed'

    def run_script(self,name,*args):
        return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.package/'scripts'/name),*map(str,args)],capture_output=True,text=True,timeout=20)

    def install(self):
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_fresh_install_and_upgrade_preserve_independent_private_files(self):
        self.assertFalse(self.install()['upgraded'])
        private=self.target/'.private'
        (private/'state.sqlite3').write_bytes(b'Synthetic persistent database sentinel')
        (private/'cv').mkdir(); (private/'cv/synthetic.docx').write_bytes(b'Synthetic user CV')
        before={str(p.relative_to(private)):p.read_bytes() for p in private.rglob('*') if p.is_file() and p.name!='install-manifest.json'}
        (self.package/'README.md').write_text('Synthetic upgrade')
        self.assertTrue(self.install()['upgraded'])
        self.assertEqual(before,{str(p.relative_to(private)):p.read_bytes() for p in private.rglob('*') if p.is_file() and p.name!='install-manifest.json'})
        self.assertEqual((self.target/'README.md').read_text(),'Synthetic upgrade')

    def test_private_source_and_unmanaged_existing_destination_fail_before_copy(self):
        (self.package/'.private').mkdir(); (self.package/'.private/developer.txt').write_text('Synthetic developer secret')
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertNotEqual(result.returncode,0); self.assertFalse(self.target.exists())
        shutil.rmtree(self.package/'.private')
        self.target.mkdir(); (self.target/'existing.txt').write_text('Keep')
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertNotEqual(result.returncode,0); self.assertEqual(list(self.target.iterdir()),[self.target/'existing.txt'])

    def test_modified_code_refuses_upgrade_without_changing_user_data(self):
        self.install()
        (self.target/'README.md').write_text('Local custom change')
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Local application files changed',result.stderr)
        self.assertEqual((self.target/'README.md').read_text(),'Local custom change')

    def test_new_source_file_cannot_overwrite_an_unmanaged_local_file(self):
        self.install()
        (self.target/'local-note.txt').write_text('Keep my local note')
        (self.package/'local-note.txt').write_text('New source collision')
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('conflicts',result.stderr)
        self.assertEqual((self.target/'local-note.txt').read_text(),'Keep my local note')

    def test_running_workspace_and_manifest_path_escape_refuse_upgrade(self):
        from job_radar_ai.__main__ import ProcessLock
        self.install()
        lock=ProcessLock(self.target/'.private/custom/nested.lock')
        try:
            result=self.run_script('install-workspace.ps1','-Destination',self.target)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Close workspace',result.stderr)
        finally:
            lock.close()
        manifest=self.target/'.private/install-manifest.json'
        data=json.loads(manifest.read_text()); data['files']={'../outside.txt':'malicious'}
        manifest.write_text(json.dumps(data))
        result=self.run_script('install-workspace.ps1','-Destination',self.target)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('escapes',result.stderr)

    def test_skill_registration_is_idempotent_and_never_overwrites_another_skill(self):
        skills=self.root/'user-skills'
        result=self.run_script('register-skill.ps1','-SkillsDirectory',skills)
        self.assertEqual(result.returncode,0,result.stderr)
        file=skills/'job-radar-ai/SKILL.md'; initial=file.read_bytes()
        self.assertIn(str(self.package).encode(),initial)
        self.assertEqual(self.run_script('register-skill.ps1','-SkillsDirectory',skills).returncode,0)
        self.assertEqual(file.read_bytes(),initial)
        file.write_text('Another existing skill')
        self.assertNotEqual(self.run_script('register-skill.ps1','-SkillsDirectory',skills).returncode,0)
        self.assertEqual(file.read_text(),'Another existing skill')

    def test_missing_cli_requires_separate_consent_and_rejects_damaged_cached_archive(self):
        result=self.run_script('setup-codex.ps1','-PrivateOnly')
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('CODEX_DOWNLOAD_APPROVAL_REQUIRED',result.stdout)
        self.assertFalse((self.package/'.private').exists())
        folder=self.package/'.private/runtime/codex/0.162.1'; folder.mkdir(parents=True)
        (folder/'codex.zip').write_bytes(b'Synthetic invalid archive')
        result=self.run_script('setup-codex.ps1','-PrivateOnly','-ApproveDownload')
        self.assertNotEqual(result.returncode,0); self.assertIn('checksum mismatch',result.stderr)
        self.assertFalse((folder/'codex.exe').exists())
