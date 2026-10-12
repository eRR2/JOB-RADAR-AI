"""Offline stable release metadata, package integrity and Windows update recovery."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from job_radar_ai.updates import (apply_update, recover_update, private_snapshot, package_files,
                                 stage_archive, check_release, LATEST, download_release, replace_file)
from job_radar_ai.sources import RetrievalError
from job_radar_ai.__main__ import ProcessLock
from job_radar_ai.store import Store
from job_radar_ai.markets import defaults

SHA='a'*40


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        # A real custom Documents-like path with spaces and Unicode, no assumed username.
        self.target=self.root/'Documents üser space'/'My career app'
        self.package=self.root/'reviewed staging'
        for folder in (self.target,self.package):
            (folder/'scripts').mkdir(parents=True)
            (folder/'skills/job-radar-ai').mkdir(parents=True)
            (folder/'README.md').write_text('Synthetic old version')
            (folder/'scripts/launch-skill.ps1').write_text('Synthetic reviewed launch')
            (folder/'skills/job-radar-ai/SKILL.md').write_text('Synthetic existing skill')
        self.old_files=package_files(self.target)
        private=self.target/'.private';private.mkdir()
        (private/'install-manifest.json').write_text(json.dumps({'revision':'older-installed-version','files':{k.replace('/','\\'):v.upper() for k,v in self.old_files.items()}}))
        self.store=Store(private/'state.sqlite3')
        self.store.set('profile',{'markets':defaults(),'cv_text':'Synthetic career context','provider':'codex'})
        self.store.set('schedule_slot','Synthetic catchup slot')
        self.store.set('linkedin_stop','Synthetic persisted source stop')
        self.store.upsert_job({'id':'linkedin:123456','title':'Synthetic','location':'Berlin, Germany'})
        self.store.add_feedback('linkedin:123456','like',[],'Synthetic')
        self.store.application('linkedin:123456','interview')
        (private/'cv').mkdir();(private/'cv/current.docx').write_bytes(b'Synthetic CV bytes')
        (private/'reports').mkdir();(private/'reports/retained.txt').write_text('Synthetic report')
        self.association=self.root/'user-skills/job-radar-ai/SKILL.md';self.association.parent.mkdir(parents=True)
        self.association.write_text('Canonical skill: '+str(self.target/'skills/job-radar-ai/SKILL.md'))
        self.before=private_snapshot(private)
        (self.package/'README.md').write_text('Synthetic new version')
        (self.package/'new.py').write_text('Synthetic new code')
        (self.package/'release-manifest.json').write_text(json.dumps({'commit':SHA,'tag':'v2.3.0','files':package_files(self.package)}))

    def test_existing_custom_workspace_data_and_skill_binding_preserved(self):
        binding=self.association.read_bytes()
        result=apply_update(self.package,self.target,SHA,approved=True)
        self.assertTrue(result['updated']);self.assertTrue(result['relaunch_required'])
        self.assertEqual(self.before,private_snapshot(self.target/'.private'))
        self.assertEqual(binding,self.association.read_bytes())
        self.assertEqual((self.target/'README.md').read_text(),'Synthetic new version')
        backup=Path(result['backup'])
        manifest=json.loads((backup/'private-manifest.json').read_text())
        for name,value in self.before.items():
            self.assertEqual(hashlib.sha256((backup/'private'/name).read_bytes()).hexdigest(),value)
        self.assertEqual(self.store.jobs()[0]['application_status'],'interview')
        self.assertEqual(self.store.jobs()[0]['feedback'][0]['kind'],'like')

    def test_copy_failure_rolls_back_all_code_without_touching_private_state(self):
        calls=0
        def fail_once(source,target):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Synthetic interrupted copy')
            replace_file(source,target)
        with patch('job_radar_ai.updates.replace_file',side_effect=fail_once),self.assertRaises(OSError):
            apply_update(self.package,self.target,SHA,True)
        self.assertEqual(package_files_for_installed(self.target),self.old_files)
        self.assertEqual(self.before,private_snapshot(self.target/'.private'))
        self.assertFalse((self.target/'.private/updates/transaction.json').exists())

    def test_process_interruption_journal_recover_and_launch_block(self):
        calls=0
        def interrupt(source,target):
            nonlocal calls
            calls+=1
            if calls==2:raise KeyboardInterrupt()
            replace_file(source,target)
        with patch('job_radar_ai.updates.replace_file',side_effect=interrupt),self.assertRaises(KeyboardInterrupt):
            apply_update(self.package,self.target,SHA,True)
        self.assertTrue((self.target/'.private/updates/transaction.json').exists())
        with self.assertRaises(ValueError):apply_update(self.package,self.target,SHA,True)
        from job_radar_ai.__main__ import main
        with patch('sys.argv',['radar','--root',str(self.target),'--skill-mode','--no-browser']),self.assertRaises(SystemExit):main()
        self.assertTrue(recover_update(self.target,True)['recovered'])
        self.assertEqual(package_files_for_installed(self.target),self.old_files)
        self.assertEqual(self.before,private_snapshot(self.target/'.private'))

    def test_refuses_silent_update_running_workspace_modified_code_and_collisions(self):
        with self.assertRaisesRegex(ValueError,'approval'):apply_update(self.package,self.target,SHA)
        lock=ProcessLock(self.target/'.private/custom/nested.lock')
        try:
            with self.assertRaisesRegex(ValueError,'Close workspace'):apply_update(self.package,self.target,SHA,True)
        finally:lock.close()
        (self.target/'README.md').write_text('Local code change')
        with self.assertRaisesRegex(ValueError,'code changed'):apply_update(self.package,self.target,SHA,True)
        (self.target/'README.md').write_text('Synthetic old version')
        (self.target/'new.py').write_text('Unmanaged private local note')
        with self.assertRaisesRegex(ValueError,'unmanaged'):apply_update(self.package,self.target,SHA,True)
        self.assertEqual(self.before,private_snapshot(self.target/'.private'))

    def test_corrupt_database_or_private_source_prevents_code_replacement(self):
        (self.package/'.private').mkdir();(self.package/'.private/secret.txt').write_text('Synthetic secret')
        with self.assertRaises(ValueError):apply_update(self.package,self.target,SHA,True)
        shutil.rmtree(self.package/'.private')
        (self.target/'.private/state.sqlite3').write_bytes(b'Synthetic corrupt database')
        with self.assertRaises(sqlite3.DatabaseError):apply_update(self.package,self.target,SHA,True)
        self.assertEqual((self.target/'README.md').read_text(),'Synthetic old version')

    def test_manifest_path_escape_and_linked_source_rejected_before_writes(self):
        file=self.target/'.private/install-manifest.json';old=file.read_text()
        file.write_text(json.dumps({'revision':'old','files':{'../escape':'a'*64}}))
        with self.assertRaises(ValueError):apply_update(self.package,self.target,SHA,True)
        file.write_text(old)
        if os.name!='nt':
            (self.package/'linked').symlink_to(self.target/'README.md')
            with self.assertRaises(ValueError):apply_update(self.package,self.target,SHA,True)

    def archive(self, changes=None):
        archive=self.root/'release.zip'
        files={str(p.relative_to(self.package)).replace('\\','/'):p.read_bytes() for p in self.package.rglob('*') if p.is_file() and p.name!='release-manifest.json'}
        manifest={'commit':SHA,'tag':'v2.3.0','files':{name:hashlib.sha256(body).hexdigest() for name,body in files.items()}}
        if changes:changes(files,manifest)
        with zipfile.ZipFile(archive,'w') as z:
            for name,body in files.items():z.writestr(name,body)
            z.writestr('release-manifest.json',json.dumps(manifest))
        return archive,hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_exact_release_archive_inventory_commit_and_hash_verified(self):
        archive,sha=self.archive()
        result=stage_archive(archive,self.root/'staged',sha,SHA,'v2.3.0')
        self.assertTrue(result['staged']);self.assertEqual((self.root/'staged/README.md').read_text(),'Synthetic new version')
        with self.assertRaisesRegex(ValueError,'SHA-256'):stage_archive(archive,self.root/'wrong','0'*64,SHA,'v2.3.0')
        with self.assertRaisesRegex(ValueError,'commit'):stage_archive(archive,self.root/'wrong',sha,'b'*40,'v2.3.0')

    def test_release_path_traversal_private_material_inventory_and_file_hash_rejected(self):
        for name in ('../escape','.private/state.sqlite3','auth.json','personal.pdf','.private /secret','CON.txt','folder/evil.','streams:secret'):
            archive,sha=self.archive(lambda f,m:f.update({name:b'Synthetic forbidden'}))
            with self.subTest(name=name),self.assertRaises(ValueError):stage_archive(archive,self.root/'wrong',sha,SHA,'v2.3.0')
        archive,sha=self.archive(lambda f,m:m['files'].update({'README.md':'0'*64}))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):stage_archive(archive,self.root/'wrong',sha,SHA,'v2.3.0')

    def test_public_metadata_check_sends_only_fixed_repository_url(self):
        (self.package/'version.json').write_text(json.dumps({'version':'2.3.0-phase3','channel':'preview'}))
        calls=[]
        class Fetcher:
            def get(self,url,**kw):
                calls.append((url,kw))
                return {'text':json.dumps({'tag_name':'v2.3.0','html_url':'https://github.com/eRR2/JOB-RADAR-AI/releases/tag/v2.3.0','body':'Synthetic release notes','draft':False,'prerelease':False})}
        result=check_release(self.package,Fetcher())
        self.assertEqual(result['status'],'available');self.assertEqual(calls,[(LATEST,{'api':True})])
        self.assertNotIn('cv',str(calls));self.assertNotIn(str(self.target),str(calls))

    def test_no_stable_release_and_mutable_branch_download_fail_visibly(self):
        (self.package/'version.json').write_text(json.dumps({'version':'2.3.0-phase3','channel':'preview'}))
        class Fetcher:
            def get(self,*_,**kw):raise RetrievalError('unavailable','404 fixture')
        self.assertEqual(check_release(self.package,Fetcher())['status'],'no_stable_release')
        with self.assertRaisesRegex(ValueError,'approval'):download_release('https://example.com',self.root/'download','a'*64)
        with self.assertRaisesRegex(ValueError,'branch archives refused'):
            download_release('https://github.com/eRR2/JOB-RADAR-AI/archive/refs/heads/main.zip',self.root/'download','a'*64,True)

    def test_recovery_refuses_changed_private_data_instead_of_restoring_old_database(self):
        with patch('job_radar_ai.updates.replace_file',side_effect=KeyboardInterrupt()),self.assertRaises(KeyboardInterrupt):apply_update(self.package,self.target,SHA,True)
        self.store.set('new_user_action','Preserve even after interrupted update')
        with self.assertRaisesRegex(ValueError,'Private data changed'):recover_update(self.target,True)
        self.assertEqual(self.store.get('new_user_action'),'Preserve even after interrupted update')

    def test_changed_staged_release_file_is_rejected_before_backup_or_copy(self):
        (self.package/'README.md').write_text('Changed after archive review')
        with self.assertRaisesRegex(ValueError,'changed after review'):apply_update(self.package,self.target,SHA,True)
        self.assertEqual((self.target/'README.md').read_text(),'Synthetic old version')
        self.assertEqual(self.before,private_snapshot(self.target/'.private'))


def package_files_for_installed(target):
    return {name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in ('README.md','scripts/launch-skill.ps1','skills/job-radar-ai/SKILL.md')}
