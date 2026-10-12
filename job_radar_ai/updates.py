"""Public release metadata and recoverable, same-workspace code replacement.

No provider/auth files are read. The updater never executes a downloaded script,
starts a migration or restores a database automatically.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import time
import zipfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from .sources import PinnedHTTPS, AGENT, PublicFetcher, RetrievalError

REPOSITORY = 'eRR2/JOB-RADAR-AI'
LATEST = 'https://api.github.com/repos/' + REPOSITORY + '/releases/latest'
PRIVATE = re.compile(r'(^|/)(\.private|\.git|\.venv|\.tools|node_modules|profiles|reports|backups|\.env[^/]*|auth\.json|credentials(?:\.json)?|sessions?)(/|$)|\.(sqlite[^.]*|db|pdf|docx|key|pem)$', re.I)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.pending')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def version(root):
    return json.loads((Path(root) / 'version.json').read_text(encoding='utf-8'))


def check_release(root, fetcher):
    current = version(root)
    try:
        page = fetcher.get(LATEST, api=True)
        release = json.loads(page['text'])
        tag = release['tag_name']
        url = release['html_url']
        if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v\d+\.\d+\.\d+', tag) or url != 'https://github.com/' + REPOSITORY + '/releases/tag/' + tag:
            raise ValueError('Stable release metadata could not be verified.')
        # Never turn a preview into an assumed downgrade/upgrade by comparing strings.
        local = tuple(int(n) for n in current['version'].split('-')[0].split('.'))
        remote = tuple(int(n) for n in tag[1:].split('.'))
        return {'status': 'available' if remote > local or (remote == local and current['channel'] != 'stable') else 'current',
                'version': current['version'], 'release_version': tag, 'url': url,
                'notes': str(release.get('body') or '')[:10000],
                'instruction': 'In Codex Desktop ask: Update my JOB-RADAR AI. Review this exact release, approve downloads/update, and close the dashboard first.'}
    except RetrievalError as exc:
        return {'status': 'no_stable_release' if exc.status == 'unavailable' else 'unavailable', 'version': current['version'],
                'message':'No stable release has been published yet. Ask Codex to check again later.' if exc.status=='unavailable' else str(exc)}
    except (ValueError, KeyError, TypeError):
        return {'status': 'unavailable', 'version': current['version'], 'message': 'Release metadata could not be verified; nothing downloaded or changed.'}


def safe_path(root, relative, public=True):
    root = Path(root).absolute()
    relative = str(relative).replace('\\', '/')
    pieces=relative.split('/')
    if not relative or ':' in relative or relative.startswith('/') or any(p in ('', '.', '..') or p.endswith((' ','.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',p,re.I) or any(ord(c)<32 for c in p) for p in pieces) or (public and PRIVATE.search(relative)):
        raise ValueError('Unsafe/private package or manifest path.')
    result = root / relative
    for part in [root, *result.parents, result]:
        if part.exists() and (part.is_symlink() or (getattr(part.stat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
            raise ValueError('Linked package/workspace paths are unsupported.')
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes workspace.')
    return result


def package_files(package):
    safe_path(Path(package).absolute(),'README.md')
    package = Path(package).resolve()
    result = {}
    for path in package.rglob('*'):
        safe_path(package, path.relative_to(package))
        if path.is_file():
            result[path.relative_to(package).as_posix()] = digest(path)
    if not all(name in result for name in ('README.md', 'scripts/launch-skill.ps1', 'skills/job-radar-ai/SKILL.md')):
        raise ValueError('Incomplete reviewed application package.')
    return result


def private_snapshot(private):
    result = {}
    for path in Path(private).rglob('*'):
        relative = path.relative_to(private).as_posix()
        # Runtime binaries and provider-owned disposable process files are not user
        # career state. They remain in place and are never touched by code replacement.
        if relative.split('/')[0] in ('runtime', 'ai', 'launch', 'updates', 'verification') or path.name == 'install-manifest.json' or path.suffix in ('.lock', '.pending'):
            continue
        safe_path(private, relative, public=False)
        if path.is_file():
            if path.suffix == '.sqlite3':
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Private SQLite integrity check failed; no update.')
            result[relative] = digest(path)
    return result


def database_fingerprint(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Private SQLite backup integrity check failed.')
        schema=db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        tables=[name for kind,name,_ in schema if kind=='table']
        rows={}
        for name in tables:
            content=sorted(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr)
            rows[name]=hashlib.sha256(repr(content).encode()).hexdigest()
        return {'schema':hashlib.sha256(repr(schema).encode()).hexdigest(),'user_version':db.execute('PRAGMA user_version').fetchone()[0],'tables':rows}


class WorkspaceLocks:
    def __init__(self, target):
        self.target = Path(target)
        self.handles = []

    def __enter__(self):
        private = self.target / '.private'
        private.mkdir(exist_ok=True)
        # Also create/take the default launch lock, eliminating a launch/update race.
        paths = sorted(set([private / 'state.lock', private / 'update.lock', *private.rglob('*.lock')]))
        try:
            for path in paths:
                safe_path(private, path.relative_to(private), public=False)
                handle = path.open('a+b')
                self.handles.append(handle)
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b'1'); handle.flush()
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except OSError as exc:
            self.__exit__(None, None, None)
            raise ValueError('Close workspace in the dashboard before updating or recovering.') from exc

    def __exit__(self, *_):
        for handle in self.handles:
            handle.close()


def replace_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + '.update-pending')
    shutil.copyfile(source, pending)
    os.replace(pending, target)


def recover_update(target, approved=False):
    if not approved:
        raise ValueError('Explicit user approval required for update recovery.')
    target = Path(target).resolve()
    safe_path(target, '.private/updates/transaction.json', public=False)
    with WorkspaceLocks(target):
        return rollback(target)


def rollback(target):
    journal_path = target / '.private/updates/transaction.json'
    if not journal_path.exists():
        return {'recovered': False}
    journal = json.loads(journal_path.read_text())
    backup = safe_path(target / '.private/updates', journal['backup'], public=False)
    old = journal['previous']
    new = journal['new_files']
    # Preflight every backup and destination before restoring any file.
    for relative, expected in old['files'].items():
        source = safe_path(backup / 'code', relative)
        safe_path(target, relative)
        if digest(source).lower() != expected.lower():
            raise ValueError('Rollback code backup failed verification; preserve transaction for recovery.')
    for relative in new:
        safe_path(target, relative)
    if private_snapshot(target / '.private') != journal['private_files']:
        raise ValueError('Private data changed since update; no automatic restore/overwrite. Preserve backup and investigate.')
    for relative in old['files']:
        replace_file(safe_path(backup / 'code', relative), safe_path(target, relative))
    for relative in new:
        if relative not in old['files']:
            safe_path(target, relative).unlink(missing_ok=True)
    atomic_json(target / '.private/install-manifest.json', old)
    journal_path.unlink()
    return {'recovered': True, 'revision': old['revision'], 'private_data_preserved': True}


def apply_update(package, target, revision, approved=False):
    if not approved:
        raise ValueError('Explicit user approval required before updating.')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('An exact reviewed commit SHA is required.')
    safe_path(Path(target).absolute(),'.private/install-manifest.json',public=False)
    safe_path(Path(package).absolute(),'README.md')
    package, target = Path(package).resolve(), Path(target).resolve()
    if package == target or package.is_relative_to(target) or target.is_relative_to(package):
        raise ValueError('Reviewed staging package must be separate from installed workspace.')
    hashes = package_files(package)
    release_path=package/'release-manifest.json'
    if not release_path.is_file():
        raise ValueError('Use an integrity-verified staged release package with release-manifest.json.')
    release=json.loads(release_path.read_text())
    if release.get('commit')!=revision or not re.fullmatch(r'v\d+\.\d+\.\d+',str(release.get('tag',''))):
        raise ValueError('Staged release does not match the exact reviewed commit/tag.')
    if release.get('files')!={k:v for k,v in hashes.items() if k!='release-manifest.json'}:
        raise ValueError('Staged release inventory/hash changed after review; no update.')
    manifest = safe_path(target, '.private/install-manifest.json', public=False)
    if not manifest.is_file() or (target / '.git').exists():
        raise ValueError('Use the existing managed installation; do not update a developer Git checkout.')
    with WorkspaceLocks(target):
        if (target / '.private/updates/transaction.json').exists():
            raise ValueError('Interrupted update found. Recover it explicitly before another update.')
        old = json.loads(manifest.read_text(encoding='utf-8-sig'))
        old['files'] = {k.replace('\\', '/'): v.lower() for k, v in old['files'].items()}
        for relative, expected in old['files'].items():
            if digest(safe_path(target, relative)) != expected:
                raise ValueError('Local managed code changed; update refused before replacement.')
        for relative in hashes:
            if relative not in old['files'] and safe_path(target, relative).exists():
                raise ValueError('New code conflicts with an unmanaged local file.')
        private = target / '.private'
        before = private_snapshot(private)
        updates = private / 'updates'
        updates.mkdir(exist_ok=True)
        backup = updates / ('backup-' + str(time.time_ns()))
        (backup / 'code').mkdir(parents=True)
        for relative in old['files']:
            file = safe_path(backup / 'code', relative)
            file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(target, relative), file)
            if digest(file) != old['files'][relative]:
                raise ValueError('Code backup verification failed; nothing replaced.')
        for relative, expected in before.items():
            source = safe_path(private, relative, public=False)
            destination = safe_path(backup / 'private', relative, public=False)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if digest(destination) != expected:
                raise ValueError('Private backup verification failed; nothing replaced.')
        database_proof={}
        for relative in before:
            if Path(relative).suffix=='.sqlite3':
                original=database_fingerprint(safe_path(private,relative,public=False))
                if original!=database_fingerprint(safe_path(backup/'private',relative,public=False)):
                    raise ValueError('SQLite backup schema/rows differ; no code replacement.')
                database_proof[relative]=original
        atomic_json(backup/'database-proof.json',database_proof)
        atomic_json(backup / 'private-manifest.json', before)
        journal = {'backup': backup.name, 'previous': old, 'new_files': hashes, 'private_files': before, 'revision': revision}
        journal_path = updates / 'transaction.json'
        atomic_json(journal_path, journal)
        try:
            # Install the journal-aware launch gate first, before replacing modules.
            order=sorted(hashes,key=lambda name:(name!='scripts/launch-skill.ps1',name))
            for relative in order:
                expected=hashes[relative]
                source = safe_path(package, relative)
                if digest(source) != expected:
                    raise ValueError('Staged package changed during update.')
                replace_file(source, safe_path(target, relative))
            for relative in old['files']:
                if relative not in hashes:
                    safe_path(target, relative).unlink()
            if any(digest(safe_path(target, name)) != value for name, value in hashes.items()) or private_snapshot(private) != before:
                raise ValueError('Post-update code/data verification failed.')
            atomic_json(manifest, {'revision': revision, 'files': hashes})
            journal_path.unlink()
            return {'updated': True, 'revision': revision, 'backup': str(backup), 'private_data_preserved': True, 'relaunch_required': True}
        except Exception:
            rollback(target)
            raise


def stage_archive(archive, destination, expected_sha, commit, tag):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha) or digest(archive) != expected_sha:
        raise ValueError('Release archive SHA-256 mismatch; nothing extracted/executed.')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Exact stable release tag and reviewed commit required.')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Use a new staging directory; never overwrite another workspace.')
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if len(members) > 5000 or sum(m.file_size for m in members) > 30_000_000:
            raise ValueError('Release archive exceeds extraction bounds.')
        files = [m for m in members if not m.is_dir()]
        for m in files:
            safe_path(destination, m.filename)
            if stat.S_ISLNK(m.external_attr >> 16) or m.flag_bits & 1:
                raise ValueError('Linked/encrypted release members refused.')
        if len({m.filename.casefold() for m in files}) != len(files):
            raise ValueError('Duplicate release archive paths.')
        # Stable assets have root-level application files and a reviewed manifest.
        raw = z.read('release-manifest.json')
        release = json.loads(raw)
        if release['commit'] != commit or release['tag'] != tag:
            raise ValueError('Release manifest does not match reviewed tag/commit.')
        names = {m.filename for m in files} - {'release-manifest.json'}
        if names != set(release['files']):
            raise ValueError('Release file inventory mismatch.')
        for m in files:
            body = z.read(m)
            if m.filename != 'release-manifest.json' and hashlib.sha256(body).hexdigest() != release['files'][m.filename]:
                raise ValueError('Release file hash mismatch.')
        destination.mkdir(parents=True)
        for m in files:
            path = safe_path(destination, m.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(z.read(m))
    package_files(destination)
    return {'staged': True, 'package': str(destination), 'commit': commit, 'tag': tag, 'sha256': expected_sha}


def download_release(url, destination, expected_sha, approved=False):
    if not approved:
        raise ValueError('Explicit approval required for exact reviewed release download.')
    if not re.fullmatch(r'https://github\.com/eRR2/JOB-RADAR-AI/releases/download/v\d+\.\d+\.\d+/[A-Za-z0-9_.-]+\.zip', url):
        raise ValueError('Download must be an exact stable JOB-RADAR-AI Release asset; branch archives refused.')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha):
        raise ValueError('Reviewed independent SHA-256 required before download.')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Do not overwrite an existing download.')
    deadline = time.monotonic() + 60
    current = url
    for _ in range(4):
        p = urlsplit(current)
        if p.scheme != 'https' or p.hostname not in ('github.com', 'release-assets.githubusercontent.com') or p.username or p.password or p.port not in (None, 443):
            raise ValueError('Unsafe release asset redirect.')
        conn = PinnedHTTPS(p.hostname, timeout=8)
        try:
            conn.request('GET', p.path + ('?' + p.query if p.query else ''), headers={'User-Agent': AGENT, 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                current = urljoin(current, response.getheader('Location', ''))
                continue
            if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Release asset unavailable/restricted; no retry.')
            body = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise ValueError('Release download deadline exceeded.')
                block = response.read1(16384)
                if not block:
                    break
                body.extend(block)
                if len(body) > 30_000_000:
                    raise ValueError('Release asset exceeds size limit.')
            if hashlib.sha256(body).hexdigest() != expected_sha:
                raise ValueError('Release SHA-256 mismatch; archive not saved or executed.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(body)
            return
        finally:
            conn.close()
    raise ValueError('Release redirect limit exceeded; no retry.')
