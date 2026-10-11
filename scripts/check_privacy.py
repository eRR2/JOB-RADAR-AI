"""Fail publication on private paths, payload formats or recognizable credentials.

Run from the repository after staging. This supplements human diff review; it
cannot prove that arbitrary prose contains no personal information.
"""
import re
import subprocess
import sys
from pathlib import Path


def git(*args):
    return subprocess.check_output(['git',*args],stderr=subprocess.DEVNULL)


def main():
    paths=git('ls-files','-z').decode().split('\0')
    secrets=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    forbidden=re.compile(r'(^|/)(\.private|\.tools|\.venv|node_modules|profiles|reports|backups)(/|$)|(^|/)(\.env(?:\..*)?|auth\.json|credentials(?:\.json)?|sessions?)(/|$)',re.I)
    failures=[]
    for path in filter(None,paths):
        if forbidden.search(path) or Path(path).suffix.lower() in ('.pdf','.docx','.db','.pem','.key') or '.sqlite' in path.lower():
            failures.append('Private path/format: '+path)
        data=git('show',':'+path)
        if secrets.search(data):failures.append('Credential pattern: '+path)
        if re.search(rb'[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+[\\/]',data):
            failures.append('Machine-specific personal path: '+path)
    historical=git('rev-list','--objects','--all').decode().splitlines()
    for item in historical:
        if ' ' not in item:continue
        identity,path=item.split(' ',1)
        if forbidden.search(path) or Path(path).suffix.lower() in ('.pdf','.docx','.db','.pem','.key') or '.sqlite' in path.lower():
            failures.append('Private history path: '+path)
        if git('cat-file','-t',identity).strip()==b'blob' and secrets.search(git('cat-file','blob',identity)):
            failures.append('Credential pattern in history: '+path)
    expected=['.private/state.sqlite3','.private/cv/current.docx','.private/backups/radar-test.sqlite3','.private/verification.sqlite3','.tools/validation/tool.py','.env','private-example.pdf','private-example.docx']
    for path in expected:
        result=subprocess.run(['git','check-ignore','--quiet',path])
        if result.returncode:failures.append('Missing ignore protection: '+path)
    if failures:
        print('\n'.join(sorted(set(failures))));return 1
    print(f'Privacy scan passed: {len(list(filter(None,paths)))} indexed files; history and {len(expected)} ignore probes checked. Human prose review remains required.')
    return 0


if __name__=='__main__':
    sys.exit(main())
