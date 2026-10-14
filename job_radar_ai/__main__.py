"""Launcher; separate process lock prevents overlapping servers/search tasks."""
import argparse
import os
import threading
import webbrowser
from pathlib import Path
from .server import make_server
from .store import Store
from .hunter import Hunter
from .schedule import due_slot
from .updates import version
from .research import ResearchHunter


class ProcessLock:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.file = path.open('a+b')
        try:
            # Reading byte zero of another Windows owner's locked file is denied.
            # Metadata inspection avoids that read and initializes only empty files.
            if os.fstat(self.file.fileno()).st_size==0:
                self.file.write(b'1')
                self.file.flush()
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('JOB-RADAR AI is already running.')

    def close(self):
        self.file.close()


def main():
    parser=argparse.ArgumentParser(description='Launch your local career workspace.')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--scheduled',action='store_true')
    parser.add_argument('--skill-mode',action='store_true',help='Catch-up reminders only; no automatic or OS scheduling.')
    parser.add_argument('--database',default='.private/state.sqlite3',help='Private relative database path for isolated verification.')
    args=parser.parse_args()
    if args.skill_mode and args.scheduled:
        parser.error('Skill mode cannot run OS scheduled searches.')
    root=args.root.resolve()
    if args.scheduled and (root/'version.json').is_file() and version(root).get('version','').startswith('5.3'):
        parser.error('Scheduled searches are disabled in the current weekly preview. Start an explicit search from the dashboard.')
    database=(root/args.database).resolve()
    if not database.is_relative_to(root/'.private') or database.suffix!='.sqlite3':
        parser.error('Database must be a .sqlite3 file below this project’s .private directory.')
    if not 1<=args.port<=65535:
        parser.error('Invalid localhost port.')
    if (root/'.private/updates/transaction.json').exists():
        parser.error('Interrupted update detected. Ask Codex to recover the managed workspace before launching; private data is retained.')
    try:
        update_lock=ProcessLock(root/'.private/update.lock')
    except RuntimeError:
        parser.error('Workspace is running or updating. Wait for the update or reuse its dashboard.')
    try:
        lock=ProcessLock(database.with_suffix('.lock'))
    except RuntimeError:
        update_lock.close()
        if args.skill_mode:
            parser.error('Workspace already running. Reuse the verified URL through the skill launcher.')
        if args.scheduled:
            Store(database).record_skipped('Local server/search process already owns this workspace; no duplicate execution.')
        elif not args.no_browser:
            webbrowser.open('http://127.0.0.1:'+str(args.port))
        print('JOB-RADAR AI is already running; overlapping execution skipped.')
        return
    stop=threading.Event()
    server=None
    hunter=None
    scheduler=None
    try:
        v5=(root/'version.json').is_file() and version(root).get('version','').startswith('5.')
        store=Store(database,v5=v5)
        store.recover_runs()
        if args.scheduled:
            profile=store.get('profile')
            if not profile or not profile.get('consent') or not profile.get('secondary' if v5 else 'linkedin_consent'):
                store.record_skipped('Scheduled run skipped: onboarding or consent incomplete.')
                return
            slot=due_slot(profile,previous=store.get('schedule_slot'))
            if not slot:
                store.record_skipped('Scheduled run skipped: not due or already attempted today.')
                return
            store.set('schedule_slot',slot)
            hunter=(ResearchHunter if v5 else Hunter)(root,store)
            hunter.start()
            hunter.thread.join()
            return
        server=make_server(root,database,args.port,skill_mode=args.skill_mode)
        hunter=server.app.hunter
        if not args.skill_mode:
            scheduler=threading.Thread(target=server.app.scheduler,args=(stop,),daemon=True)
            scheduler.start()
        print('JOB-RADAR AI: http://127.0.0.1:'+str(server.server_port),flush=True)
        print('Local only. Close this process to stop the background server.',flush=True)
        if not args.no_browser:
            webbrowser.open('http://127.0.0.1:'+str(server.server_port))
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if scheduler:
            scheduler.join()
        if hunter and hunter.thread and hunter.thread.is_alive():
            hunter.cancel.set()
            hunter.thread.join()
        if server:
            server.app.update_cancel.set()
            if server.app.update_thread and server.app.update_thread.is_alive():
                server.app.update_thread.join()
            server.app.operation_cancel.set()
            if server.app.operation_thread and server.app.operation_thread.is_alive():
                server.app.operation_thread.join()
            server.server_close()
        lock.close()
        update_lock.close()


if __name__=='__main__':
    main()
