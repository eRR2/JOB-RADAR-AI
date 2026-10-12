"""Loopback-only browser application with explicit local write protection."""
import json
import os
import secrets
import sys
import tempfile
import threading
import hashlib
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .store import Store, now
from .hunter import Hunter, DEFAULT_BUDGETS, profile_signature
from .profile import validate_profile
from .providers import Provider, bounded_process, executable
from .schedule import install_task, due_slot, catchup_slot
from .markets import market_profile, country_of, REGIONAL
from .recovery import DescriptionResolver, description_state
from .updates import check_release, version
from .sources import PublicFetcher

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


class Application:
    def __init__(self, root, database, skill_mode=False):
        self.root = Path(root).resolve()
        self.skill_mode = skill_mode
        self.workspace_id = hashlib.sha256((str(self.root) + '\n' + str(Path(database).resolve())).encode()).hexdigest()
        self.store = Store(database)
        self.hunter = Hunter(root, self.store)
        self.csrf = secrets.token_urlsafe(32)
        self.mutations = threading.RLock()
        self.operation = None
        self.operation_thread = None
        self.operation_cancel = threading.Event()
        self.release_status = None
        self.update_check_running = False
        self.update_cancel=threading.Event()
        self.update_thread=None
        if self.store.get('update_notifications', False):
            self.check_updates()

    def check_updates(self):
        if self.update_check_running:
            return
        self.update_check_running = True
        def check():
            try:
                self.release_status = check_release(self.root, PublicFetcher(self.store, self.update_cancel, budget=3))
            finally:
                self.update_check_running = False
        self.update_thread=threading.Thread(target=check, daemon=True)
        self.update_thread.start()

    def providers(self, refresh=False):
        statuses = self.store.get('providers', {})
        if refresh or not statuses:
            statuses = {name: Provider(name, self.root/'.private/ai').status() for name in ('codex', 'claude')}
            self.store.set('providers', statuses)
        for name, state in statuses.items():
            state['last_verified'] = self.store.get('provider_verified:' + name)
        return statuses

    def state(self):
        profile = self.store.get('profile')
        jobs = self.store.jobs()
        markets=(profile or {}).get('markets',[])
        for job in jobs:
            job['description_status'] = description_state(job, self.store)
            job['country_id']=country_of(job,markets)
            job['country_status']='country stated in source' if job['country_id'] else 'country unverified'
            for key,item in job['market_evaluations'].items():
                market=next((m for m in markets if m['id']==key),None)
                item['assessment_stale']=bool(item['content_stale'] or not market or item['evaluation'].get('profile_signature')!=profile_signature(market_profile(profile,market,self.store)))
            job['assessment_stale'] = bool(job['evaluation'] and (markets or job['evaluation'].get('profile_signature')!=profile_signature({**(profile or {}),'_preference_revision':self.store.preference_revision()})))
        market_state={m['id']:{'learned':self.store.get('learned:'+m['id'],[]),'learning_explanation':self.store.get('learning_explanation:'+m['id'],''), 'revision':self.store.preference_revision(market_id=m['id'])} for m in markets}
        return {'csrf': self.csrf, 'profile': profile, 'jobs': jobs, 'runs': self.store.runs(),
                'providers': self.providers(), 'cv': {'text':self.store.get('cv_text',''), 'filename':self.store.get('cv_filename')},
                'proposed_profile': self.store.get('proposed_profile'), 'learned': self.store.get('learned', []),
                'learning_explanation':self.store.get('learning_explanation',''), 'learning_paused':self.store.get('learning_paused',False),
                'market_state':market_state, 'global_learned':self.store.get('learned:global',[]),
                'budgets':self.store.get('budgets',DEFAULT_BUDGETS), 'linkedin_stop':self.store.get('linkedin_stop'),
                'linkedin_pending':self.store.get('linkedin_pending',False), 'linkedin_last_success':self.store.get('linkedin_last_success'),
                'operation':self.operation, 'native_task':self.store.get('native_task'), 'timezone':datetime.now().astimezone().tzname(),
                'skill_mode':self.skill_mode, 'catchup':self.catchup(),
                'version':version(self.root) if (self.root/'version.json').exists() else {'version':'2.1-preview','channel':'preview'},
                'updates':self.release_status, 'update_check_running':self.update_check_running,
                'update_notifications':self.store.get('update_notifications',False)}

    def catchup(self):
        profile = self.store.get('profile')
        if not self.skill_mode or not profile:
            return None
        slot = catchup_slot(profile, previous=self.store.get('schedule_slot'))
        reminder = self.store.get('catchup_reminder') or {}
        if not slot or (reminder.get('slot') == slot and datetime.fromisoformat(reminder['until']) > datetime.now().astimezone()):
            return None
        return {'slot':slot}

    def catchup_action(self, data):
        with self.mutations:
            due = self.catchup()
            if not due or data.get('slot') != due['slot'] or data.get('action') not in ('run', 'later', 'skip'):
                raise ValueError('This reminder changed or was already handled. Refresh the dashboard.')
            if (self.operation and self.operation['status'] == 'running') or any(run['status'] == 'running' for run in self.store.runs()):
                raise ValueError('Wait for the current AI operation first.')
            if data['action'] == 'later':
                self.store.set('catchup_reminder', {'slot':due['slot'], 'until':(datetime.now().astimezone()+timedelta(hours=1)).isoformat()})
                return {'reminded_later':True}
            if data['action'] == 'run':
                run_id = self.hunter.start()
                if run_id is None:
                    raise ValueError('Another search is already active.')
            else:
                self.store.record_skipped('User skipped catch-up slot ' + due['slot'])
                run_id = None
            self.store.set('schedule_slot', due['slot'])
            self.store.set('catchup_reminder', None)
            return {'run_id':run_id, 'saved':True}

    def async_operation(self, kind, function):
        if self.operation and self.operation.get('status') == 'running':
            raise ValueError('Another profile/provider operation is active.')
        if any(run['status'] == 'running' for run in self.store.runs()):
            raise ValueError('Wait for or cancel the active search first.')
        self.operation = {'kind':kind, 'status':'running', 'message':'AI is working…'}
        self.operation_cancel = threading.Event()
        def work():
            try:
                function(self.operation_cancel)
                self.operation = {'kind':kind, 'status':'completed', 'message':'Completed. Review the result.'}
            except Exception as exc:
                from .providers import ProviderError
                message = str(exc) if isinstance(exc, (ValueError, ProviderError)) else 'Operation failed; private data was not logged.'
                self.operation = {'kind':kind, 'status':'canceled' if self.operation_cancel.is_set() else 'failed', 'message':message}
        self.operation_thread = threading.Thread(target=work, daemon=True)
        self.operation_thread.start()

    def scheduler(self, stop):
        if self.skill_mode:
            return
        while not stop.wait(20):
            with self.mutations:
                profile = self.store.get('profile')
                if not profile or not profile.get('consent') or not profile.get('linkedin_consent'):
                    continue
                slot = due_slot(profile, previous=self.store.get('schedule_slot'))
                if slot and not (self.operation and self.operation['status']=='running'):
                    self.store.set('schedule_slot', slot)
                    try:
                        self.hunter.start()
                    except ValueError:
                        pass


def make_server(root, database, port=8767, skill_mode=False):
    app = Application(root, database, skill_mode)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass  # Request payloads and personal paths are not logged.

        def response(self, status, content, content_type='application/json; charset=utf-8', attachment=None):
            if not isinstance(content, bytes):
                content = json.dumps(content, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            for name, value in {'Content-Type':content_type, 'Content-Length':str(len(content)), 'Cache-Control':'no-store',
                                'Content-Security-Policy':CSP, 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY',
                                'Referrer-Policy':'no-referrer', 'Connection':'close'}.items():
                self.send_header(name,value)
            if attachment:
                self.send_header('Content-Disposition', 'attachment; filename="'+attachment+'"')
            self.end_headers()
            self.wfile.write(content)
            self.close_connection = True

        def guard(self, write=False):
            origin = 'http://127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                return False
            if self.headers.get('Origin') not in (None, origin):
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return False
            return not write or secrets.compare_digest(self.headers.get('X-Radar-CSRF',''), app.csrf)

        def do_GET(self):
            if not self.guard():
                return self.response(403, {'error': {'message':'Local origin required.'}})
            path = urlsplit(self.path).path
            if path == '/api/state':
                return self.response(200, app.state())
            if path == '/api/health':
                return self.response(200, {'app':'JOB-RADAR-AI', 'workspace_id':app.workspace_id, 'skill_mode':app.skill_mode})
            if path == '/api/export':
                return self.response(200, app.store.export(), attachment='job-radar-private-export.json')
            routes = {'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'),
                      '/style.css':('style.css','text/css; charset=utf-8')}
            if path in routes:
                filename, content_type = routes[path]
                return self.response(200, (app.root/'web'/filename).read_bytes(),content_type)
            return self.response(404, {'error':{'message':'Not found.'}})

        def do_POST(self):
            if not self.guard(write=True):
                return self.response(403, {'error':{'message':'Local origin and CSRF token required.'}})
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= (10_000_000 if path == '/api/cv' else 200_000):
                    raise ValueError('Invalid request size.')
                self.connection.settimeout(15)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError('Incomplete request body.')
                if path == '/api/cv':
                    if self.headers.get('Content-Type') != 'application/octet-stream':
                        raise ValueError('Use the CV upload control.')
                    data = body
                else:
                    if self.headers.get('Content-Type') != 'application/json':
                        raise ValueError('JSON content type required.')
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError('Expected an object.')
                with app.mutations:
                    result = self.mutate(path, data)
                self.response(200, result)
            except (ValueError, KeyError, TypeError) as exc:
                self.response(422, {'error':{'message':str(exc)[:500]}})
            except Exception:
                self.response(500, {'error':{'message':'Local operation failed; private state preserved. Check runtime installation.'}})

        def mutate(self, path, data):
            search_active=any(run['status']=='running' for run in app.store.runs())
            operation_active=bool(app.operation and app.operation['status']=='running')
            if path == '/api/check-updates':
                app.check_updates()
                return {'checking':True}
            if path == '/api/update-notifications':
                if type(data.get('enabled')) is not bool:
                    raise ValueError('Choose whether to check public version metadata at startup.')
                app.store.set('update_notifications',data['enabled'])
                return {'saved':True}
            if path in ('/api/resolve-description','/api/complete-descriptions','/api/supplied-description'):
                if search_active or operation_active:
                    raise ValueError('Wait for or cancel the active AI operation first.')
                if path != '/api/complete-descriptions' and not isinstance(data.get('job_id'),str):
                    raise ValueError('Select an existing vacancy.')
                if path=='/api/supplied-description' and not isinstance(data.get('description'),str):
                    raise ValueError('Paste the description for this exact vacancy.')
                return {'run_id':DescriptionResolver(app.hunter).start(data.get('job_id') if path!='/api/complete-descriptions' else None,
                                    data.get('description') if path=='/api/supplied-description' else None)}
            if path == '/api/catchup':
                return app.catchup_action(data)
            if path == '/api/close' and app.skill_mode:
                if search_active or operation_active:
                    raise ValueError('Cancel or finish the AI operation before closing your workspace.')
                if app.update_check_running:
                    raise ValueError('Wait for the bounded public version check before closing.')
                threading.Thread(target=server.shutdown, daemon=True).start()
                return {'message':'Workspace closed. Your private data is saved.'}
            if path in ('/api/profile','/api/cv','/api/profile-accept','/api/learned','/api/learning-reset','/api/source-reset','/api/budgets','/api/feedback') and (search_active or operation_active):
                raise ValueError('Wait for or cancel the active AI operation before changing its input or source policy.')
            if path == '/api/profile':
                profile = validate_profile(data)
                profile['cv_text'] = app.store.get('cv_text','')
                profile['interpreted'] = (app.store.get('profile') or {}).get('interpreted')
                prior=app.store.get('profile') or {}
                if 'weights' in prior and 'weights' not in profile:
                    profile['weights']=prior['weights']
                if prior.get('market_migration'):
                    profile['market_migration']=prior['market_migration']
                app.store.set('profile',profile)
                if any(prior.get(key)!=profile.get(key) for key in ('frequency','time','weekday')):
                    app.store.set('schedule_slot',None)
                    app.store.set('catchup_reminder',None)
                return {'saved':True}
            if path == '/api/cv':
                suffix = Path(self.headers.get('X-Filename','')).suffix.casefold()
                if suffix not in ('.pdf','.docx'):
                    raise ValueError('Upload PDF or DOCX.')
                folder = app.root/'.private/cv'
                folder.mkdir(parents=True,exist_ok=True)
                with tempfile.NamedTemporaryFile(suffix=suffix,dir=folder,delete=False) as upload:
                    upload.write(data)
                    file_path = Path(upload.name)
                try:
                    code, output, _ = bounded_process([sys.executable,'-m','job_radar_ai.cv_worker',str(file_path)],cwd=app.root,timeout=25,max_output=500000)
                    parsed = json.loads(output)
                    if code:
                        raise ValueError(parsed['error'])
                    text = parsed['text']
                    # Retain one original locally; user can replace/export/delete it.
                    target = folder/('current'+suffix)
                    target.write_bytes(data)
                    for old in folder.glob('current.*'):
                        if old != target and old.suffix in ('.pdf','.docx'):
                            old.unlink()
                    app.store.set('cv_text',text)
                    app.store.set('cv_filename','CV'+suffix)
                    app.store.set('proposed_profile',None)
                    profile = app.store.get('profile')
                    if profile:
                        profile['cv_text'] = text
                        profile['interpreted'] = None
                        app.store.set('profile',profile)
                    return {'text':text,'filename':'CV'+suffix}
                finally:
                    file_path.unlink(missing_ok=True)
            if path == '/api/profile-analysis':
                profile = app.store.get('profile')
                if not profile or not profile.get('consent') or not profile.get('cv_text'):
                    raise ValueError('Save your profile, upload readable CV and confirm provider processing first.')
                def analyze(cancel):
                    provider = Provider(profile['provider'],app.root/'.private/ai')
                    core={k:v for k,v in profile.items() if k not in (*REGIONAL,'weights','markets','market_migration')}
                    result = provider.run('profile','Interpret actual CV evidence and global career goals. Regional conditions are assessed independently during each market search. Propose an initial professional profile, transferable strengths and at most three necessary follow-up questions. Never infer unproven qualifications.',core,cancel=cancel)
                    app.store.set('proposed_profile',result)
                    app.store.set('provider_verified:'+profile['provider'],{'at':now(),'inference':True})
                app.async_operation('profile',analyze)
                return {'started':True}
            if path == '/api/profile-accept':
                summary = data.get('summary')
                proposed = app.store.get('proposed_profile')
                profile = app.store.get('profile')
                if not proposed or not profile or not isinstance(summary,str) or not summary.strip() or len(summary)>4000:
                    raise ValueError('Review a valid proposed career profile first.')
                answers=data.get('followup_answers',profile.get('followup_answers',''))
                if not isinstance(answers,str) or len(answers)>4000:
                    raise ValueError('Follow-up answers must be text up to 4,000 characters.')
                profile['followup_answers']=answers.strip()
                profile['interpreted'] = {**proposed,'summary':summary}
                app.store.set('profile',profile)
                return {'saved':True}
            if path == '/api/providers':
                return app.providers(refresh=True)
            if path == '/api/provider-probe':
                name = data['provider']
                provider = Provider(name,app.root/'.private/ai')
                def probe(cancel):
                    provider.run('probe','Report ready only if inference works.',{},cancel=cancel)
                    app.store.set('provider_verified:'+name,{'at':now(),'inference':True})
                app.async_operation('provider',probe)
                return {'started':True}
            if path == '/api/search':
                if app.operation and app.operation['status']=='running':
                    raise ValueError('Wait for or cancel the profile/provider operation first.')
                run_id = app.hunter.start(data.get('market_id','all'))
                if app.skill_mode and run_id is not None:
                    slot = catchup_slot(app.store.get('profile'))
                    app.store.set('schedule_slot', slot)
                return {'run_id':run_id}
            if path == '/api/cancel':
                app.hunter.cancel.set()
                app.operation_cancel.set()
                return {'cancel_requested':True}
            if path == '/api/reevaluate':
                if app.operation and app.operation['status']=='running':
                    raise ValueError('Wait for the current AI operation first.')
                return {'run_id':app.hunter.review(data['job_id'],data.get('market_id'))}
            if path == '/api/application':
                app.store.application(data['job_id'],data['status'])
                return {'saved':True}
            if path == '/api/feedback':
                app.store.add_feedback(data['job_id'],data['kind'],data.get('reasons',[]),data.get('note',''),scope=data.get('scope'))
                return {'saved':True}
            if path == '/api/learned':
                preferences = data.get('preferences')
                if not isinstance(preferences,list) or len(preferences)>20 or any(not isinstance(p,str) or len(p)>1000 for p in preferences):
                    raise ValueError('Invalid learned preferences.')
                scope=data.get('scope','global')
                if scope!='global' and scope not in {m['id'] for m in (app.store.get('profile') or {}).get('markets',[])}:
                    raise ValueError('Unknown learning scope.')
                app.store.set('learned:'+scope,[{'text':p,'confidence':'explicit','feedback_ids':[]} for p in preferences if p.strip()])
                app.store.set('learning_paused',bool(data.get('paused',True)))
                app.store.preference_revision(bump=True,market_id=None if scope=='global' else scope)
                return {'saved':True}
            if path == '/api/learning-reset':
                if data.get('confirm') != 'RESET LEARNING':
                    raise ValueError('Confirm reset explicitly.')
                app.store.set('learned',[])
                for scope in ['global']+[m['id'] for m in (app.store.get('profile') or {}).get('markets',[])]:
                    app.store.set('learned:'+scope,[])
                app.store.set('learning_explanation','Reset by user. Past explicit feedback is retained; automatic learning is paused.')
                app.store.set('learning_paused',True)
                app.store.preference_revision(bump=True)
                return {'saved':True}
            if path == '/api/migration-review':
                if search_active or operation_active:
                    raise ValueError('Wait for active AI operations first.')
                profile=app.store.get('profile')
                if not profile or data.get('confirm')!='REVIEWED LEGACY GEOGRAPHY':
                    raise ValueError('Review and save regional conditions before confirming.')
                profile.setdefault('market_migration',{})['review_required']=False
                app.store.set('profile',profile)
                return {'saved':True}
            if path == '/api/budgets':
                limits = {'searches':(1,6),'pages':(1,2),'details':(1,8),'requests':(1,16),'spacing':(5,60)}
                if set(data)!=set(limits) or any(type(data[key]) is not int or not lo<=data[key]<=hi for key,(lo,hi) in limits.items()):
                    raise ValueError('Choose budgets within the displayed safety limits.')
                app.store.set('budgets',data)
                return {'saved':True}
            if path == '/api/source-reset':
                if data.get('confirm')!='REVIEWED SOURCE STOP':
                    raise ValueError('Review restriction/unknown request extent before resetting. Reset is not permission to bypass access denial.')
                app.store.set('linkedin_stop',None)
                app.store.set('linkedin_pending',False)
                return {'saved':True}
            if path == '/api/native-task':
                if app.skill_mode:
                    raise ValueError('Skill mode uses catch-up reminders only; OS scheduling is disabled.')
                if data.get('confirm')!='CREATE WINDOWS TASK':
                    raise ValueError('Explicit confirmation required to create an operating-system task.')
                profile = app.store.get('profile')
                if not profile or not profile.get('consent') or not profile.get('linkedin_consent'):
                    raise ValueError('Finish onboarding first.')
                message = install_task(sys.executable,str(app.root),profile)
                app.store.set('native_task',{'at':now(),'message':message,'schedule':{k:profile[k] for k in ('frequency','time','weekday')}})
                return {'message':message}
            if path in ('/api/backup','/api/erase'):
                if any(run['status']=='running' for run in app.store.runs()) or (app.operation and app.operation['status']=='running'):
                    raise ValueError('Wait for or cancel active AI operations before data maintenance.')
                if path == '/api/backup':
                    folder = app.root/'.private/backups'
                    folder.mkdir(parents=True,exist_ok=True)
                    destination = folder/('radar-'+secrets.token_hex(6)+'.sqlite3')
                    app.store.backup(destination)
                    return {'message':'Consistent SQLite backup saved under .private/backups.'}
                if data.get('confirm')!='DELETE LOCAL CAREER DATA':
                    raise ValueError('Explicit data deletion confirmation required.')
                app.store.erase()
                for relative,pattern in [('.private/cv','*'),('.private/backups','radar-*.sqlite3'),('.private/backups','migration-*.sqlite3')]:
                    folder=(app.root/relative).resolve()
                    if folder.is_relative_to(app.root/'.private') and folder.is_dir():
                        for file in folder.glob(pattern):
                            if file.is_file() and not file.is_symlink():
                                file.unlink()
                app.operation=None
                return {'message':'Local career database, CV and app backups deleted. Provider-owned history is managed in your provider account.'}
            raise ValueError('Unknown action.')

    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads = True
    server.app = app
    return server
