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
from .intent import TASK as INTENT_TASK, validate_with_evidence_correction, confirm_intent, legacy_text
from .geography import location_status
from .research import ResearchHunter
from .access import linkedin_state
from .location import geography
from .completion import CompletionResolver
from .session_search import SessionSearch
from .listing_metadata import source_title_fields
from .reporting import review_state, coverage

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


class Application:
    def __init__(self, root, database, skill_mode=False):
        self.root = Path(root).resolve()
        self.skill_mode = skill_mode
        self.workspace_id = hashlib.sha256((str(self.root) + '\n' + str(Path(database).resolve())).encode()).hexdigest()
        self.v5 = (self.root/'version.json').is_file() and version(self.root).get('version','').startswith('5.')
        self.simple = self.v5 and version(self.root).get('version','').startswith('5.3')
        self.store = Store(database, v5=self.v5)
        if self.simple and not self.store.get('search_session'):
            self.store.fresh_session()
        self.hunter = SessionSearch(root,self.store.bound(self.store.get('search_session'))) if self.simple else (ResearchHunter if self.v5 else Hunter)(root,self.store)
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

    def new_search_session(self):
        self.hunter.cancel.set()
        if self.hunter.thread and self.hunter.thread.is_alive():
            self.hunter.thread.join(timeout=3)
        token,_ = self.store.fresh_session()
        self.hunter = SessionSearch(self.root,self.store.bound(token))

    def start_search(self, market_id='all'):
        if self.simple:
            profile=self.store.get('profile') or {}
            if not profile.get('consent') or not profile.get('secondary') or len(profile.get('cv_text',''))<30:
                raise ValueError('A readable CV, saved career request and AI/web consent are required.')
            self.new_search_session()
        return self.hunter.start(market_id)

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
        runs=self.store.runs()
        diagnostics=(runs[0]['payload'].get('diagnostics') or {}) if runs else {}
        for job in jobs:
            if not self.simple and job.get('preliminary',{}).get('policy') == 'v5.2':
                from .recommendations import signature
                geo=geography(job,markets)
                scoped_market=next((m for m in markets if m['id']==geo['country_id']),None)
                scoped=market_profile(profile,scoped_market,self.store) if scoped_market else {**profile,'authoritative_request':profile.get('looking_for','')}
                feedback=self.store.feedback(scoped_market['id']) if scoped_market and country_of(job,markets)==scoped_market['id'] else []
                job['preliminary_stale']=job['preliminary']['signature']!=signature(job,scoped,feedback)
            job['description_status'] = description_state(job, self.store)
            job['country_id']=country_of(job,markets)
            job['geography']=geography(job,markets)
            job['display_country_id']=job['geography']['country_id']
            job['country_status']='country stated in source' if job['country_id'] else 'country unverified'
            market=next((m for m in markets if m['id']==job['country_id']),None)
            job['location_status']=location_status(job,profile,market) if market else 'location_unknown'
            review_market=next((m for m in markets if m['id']==job['geography']['country_id']),None)
            job['review_state']=review_state({**job,'review_country':review_market['country'] if review_market else 'Location unverified'},diagnostics)
            job.update(source_title_fields(job))
            for key,item in job['market_evaluations'].items():
                market=next((m for m in markets if m['id']==key),None)
                item['assessment_stale']=bool(item['content_stale'] or not market or item['evaluation'].get('profile_signature')!=profile_signature(market_profile(profile,market,self.store)))
            job['assessment_stale'] = bool(job['evaluation'] and (markets or job['evaluation'].get('profile_signature')!=profile_signature({**(profile or {}),'_preference_revision':self.store.preference_revision()})))
        market_state={m['id']:{'learned':self.store.get('learned:'+m['id'],[]),'learning_explanation':self.store.get('learning_explanation:'+m['id'],''), 'revision':self.store.preference_revision(market_id=m['id'])} for m in markets}
        return {'csrf': self.csrf, 'profile': profile, 'jobs': jobs,
                'previous_opportunities': self.store.historical_opportunities(8) if self.simple else [],
                'runs': runs, 'review_coverage':coverage(jobs,diagnostics),
                'providers': self.providers(), 'cv': {'text':self.store.get('cv_text',''), 'filename':self.store.get('cv_filename')},
                'proposed_profile': self.store.get('proposed_profile'), 'proposed_intent':self.store.get('proposed_intent'),
                'intent_review_required':bool(profile and not profile.get('intent_confirmed')), 'learned': self.store.get('learned', []),
                'learning_explanation':self.store.get('learning_explanation',''), 'learning_paused':self.store.get('learning_paused',False),
                'market_state':market_state, 'global_learned':self.store.get('learned:global',[]),
                'budgets':self.store.get('budgets',DEFAULT_BUDGETS), 'linkedin_stop':self.store.get('linkedin_stop'),
                'linkedin_access':linkedin_state(self.store) if self.v5 else None,
                'linkedin_pending':self.store.get('linkedin_pending',False), 'linkedin_last_success':self.store.get('linkedin_last_success'),
                'operation':self.operation, 'native_task':self.store.get('native_task'), 'timezone':datetime.now().astimezone().tzname(),
                'skill_mode':self.skill_mode, 'catchup':self.catchup(),
                'version':version(self.root) if (self.root/'version.json').exists() else {'version':'2.1-preview','channel':'preview'},
                'updates':self.release_status, 'update_check_running':self.update_check_running,
                'update_notifications':self.store.get('update_notifications',False)}

    def catchup(self):
        profile = self.store.get('profile')
        if self.simple or not self.skill_mode or not profile:
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
                run_id = self.start_search()
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
                self.operation = {'kind':kind, 'status':'completed', 'message':'Career request saved; AI research started.' if kind=='career_search' else 'Completed. Review the result.'}
            except Exception as exc:
                from .providers import ProviderError
                message = str(exc) if isinstance(exc, (ValueError, ProviderError)) else 'Operation failed; private data was not logged.'
                self.operation = {'kind':kind, 'status':'canceled' if self.operation_cancel.is_set() else 'failed', 'message':message,'category':getattr(exc,'category','clarification_or_validation')}
        self.operation_thread = threading.Thread(target=work, daemon=True)
        self.operation_thread.start()

    def scheduler(self, stop):
        if self.skill_mode or self.simple:
            return
        while not stop.wait(20):
            with self.mutations:
                profile = self.store.get('profile')
                if not profile or not profile.get('consent') or not profile.get('secondary' if self.v5 else 'linkedin_consent'):
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
            if app.simple and path in ('/api/resolve-description','/api/complete-descriptions','/api/supplied-description','/api/reevaluate','/api/reprioritize','/api/obsolete','/api/budgets','/api/source-reset','/api/intent-analysis','/api/intent-accept','/api/schedule'):
                raise ValueError('This control was removed. Start a fresh Search with AI.')
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
                return {'run_id':(CompletionResolver if app.v5 else DescriptionResolver)(app.hunter).start(data.get('job_id') if path!='/api/complete-descriptions' else None,
                                    data.get('description') if path=='/api/supplied-description' else None)}
            if path=='/api/confirm-description-source':
                if search_active or operation_active or data.get('confirm')!='CONFIRM POSTING IDENTITY' or not isinstance(data.get('candidate_id'),str):
                    raise ValueError('Finish active operations and explicitly confirm this ambiguous posting association.')
                return {'run_id':DescriptionResolver(app.hunter).start(data.get('job_id'),selection=data.get('candidate_id'))}
            if path == '/api/catchup':
                return app.catchup_action(data)
            if path == '/api/close' and app.skill_mode:
                if search_active or operation_active:
                    raise ValueError('Cancel or finish the AI operation before closing your workspace.')
                if app.update_check_running:
                    raise ValueError('Wait for the bounded public version check before closing.')
                threading.Thread(target=server.shutdown, daemon=True).start()
                return {'message':'Workspace closed. Your private data is saved.'}
            if path in ('/api/routine','/api/connection') and app.v5:
                if search_active or operation_active:
                    raise ValueError('Finish or cancel the active operation before changing its input.')
                profile=app.store.get('profile')
                if not profile:raise ValueError('Confirm your career understanding first.')
                if path=='/api/routine':
                    if data.get('frequency') not in ('manual','daily','weekly') or not isinstance(data.get('time'),str) or not __import__('re').fullmatch(r'\d{2}:\d{2}',data['time']) or not 0<=int(data['time'][:2])<=23 or not 0<=int(data['time'][3:])<=59 or type(data.get('weekday')) is not int or not 0<=data['weekday']<=6:
                        raise ValueError('Choose a valid local search time and weekday.')
                    profile.update({k:data[k] for k in ('frequency','time','weekday')})
                    app.store.set('schedule_slot',None);app.store.set('catchup_reminder',None)
                else:
                    if data.get('provider') not in ('codex','claude') or any(type(data.get(k)) is not bool for k in ('consent','linkedin_consent','secondary')):
                        raise ValueError('Select provider and explicitly review processing/source permissions.')
                    profile.update({k:data[k] for k in ('provider','consent','linkedin_consent','secondary')})
                app.store.set('profile',profile)
                return {'saved':True}
            if path in ('/api/career-search','/api/intent-analysis','/api/intent-accept','/api/profile','/api/cv','/api/profile-accept','/api/learned','/api/learning-reset','/api/source-reset','/api/budgets','/api/feedback') and (operation_active or (search_active and not (app.simple and path=='/api/career-search'))):
                raise ValueError('Wait for or cancel the active AI operation before changing its input or source policy.')
            if path in ('/api/intent-analysis','/api/career-search'):
                auto_search=path=='/api/career-search'
                text=data.get('looking_for')
                prior=app.store.get('profile') or {}
                cv=app.store.get('cv_text') or prior.get('cv_text','')
                if not isinstance(text,str) or not text.strip() or len(text)>12000 or len(cv)<30:
                    raise ValueError('Review your existing CV and describe your next move in one text field.')
                provider=data.get('provider',prior.get('provider'))
                if provider not in ('codex','claude') or data.get('consent') is not True:
                    raise ValueError('Choose an AI provider and confirm career-context processing.')
                if any(type(data.get(k,False)) is not bool for k in ('linkedin_consent','secondary')):
                    raise ValueError('Source permissions must be explicit boolean choices.')
                raw={'looking_for':text,'provider':provider,'consent':True,'linkedin_consent':data.get('linkedin_consent',False),'secondary':data.get('secondary',False)}
                summary_edit=data.get('summary_edit','')
                if not isinstance(summary_edit,str) or len(summary_edit)>12000:
                    raise ValueError('Keep the edited understanding within 12,000 characters.')
                evidence_text=text if auto_search else text+'\n'+summary_edit+'\n'+legacy_text(prior)
                if app.simple and auto_search:
                    if not raw['secondary']:
                        raise ValueError('Allow anonymous public web research before starting a search.')
                    unchanged=prior.get('intent_confirmed') and prior.get('markets') and ' '.join(prior.get('looking_for','').split())==' '.join(text.split())
                    if unchanged:
                        # Saved, confirmed preferences are knowledge, not a new AI proposal.
                        # Updating a CV must not reinterpret or reconstruct those preferences.
                        profile={**prior,'cv_text':cv,**{k:v for k,v in raw.items() if k!='looking_for'}}
                        app.new_search_session()
                        app.operation=None
                        app.store.set('profile',profile)
                        return {'run_id':app.hunter.start()}
                def interpret(cancel):
                    ai=Provider(provider,app.root/'.private/ai')
                    context={'cv_text':cv,'user_text':text,'edited_understanding':summary_edit,'legacy_texts':'' if auto_search else legacy_text(prior)}
                    task=INTENT_TASK+(' V5.1 interpretation is INTERNAL: original user text is authoritative, not a generic summary. No compulsory approval step. Preserve every country-specific condition, exception, exclusion and employer priority from that text. Ask only a genuinely essential ambiguity that prevents meaningful research; all optional unknowns stay unknown.' if auto_search else ' If an edited understanding is supplied, reconcile its changes with the original words. Do not retain contradicted preferences; keep unknowns unknown.')
                    result=ai.run('intent',task,context,cancel=cancel,timeout=60 if app.simple else 240)
                    result=validate_with_evidence_correction(result,cv,evidence_text,lambda invalid,issues:ai.run('intent','Correct ONLY the invalid quote fields identified below, copying a verbatim contiguous passage from the original source. A geographic passage must include its country and every listed preferred/secondary place. Keep all other fields, origins, markets, constraints and preferences exactly unchanged. Never change explicit to inferred. If unsupported, do not invent evidence. No onboarding restart, tools or search.',{**context,'invalid_intent':invalid,'invalid_evidence_fields':issues},cancel=cancel,research=False,timeout=60 if app.simple else 240))
                    if auto_search:
                        if result['questions'] or not result['markets']:
                            raise ValueError('Please clarify your career request: '+'; '.join(result['questions'] or ['Which geographic market should research cover?']))
                        profile=confirm_intent(result,prior,cv,text)
                        profile.update(raw);profile['objectives']=text;profile['intent_summary_edit']=''
                        if app.simple:
                            if cancel.is_set():
                                from .providers import ProviderError
                                raise ProviderError('Canceled by user.','canceled')
                            app.new_search_session()
                        app.store.set('profile',profile);app.store.set('proposed_intent',None)
                        app.store.preference_revision(bump=True)
                        app.hunter.start()
                    else:
                        app.store.set('proposed_intent',{'intent':result,'input':raw,'evidence_text':evidence_text,'cv_text':cv,'summary_edit':summary_edit})
                    app.store.set('provider_verified:'+provider,{'at':now(),'inference':True})
                app.async_operation('career_search' if auto_search else 'intent',interpret)
                return {'started':True}
            if path == '/api/intent-accept':
                proposal=app.store.get('proposed_intent')
                if not proposal or data.get('confirm')!='CONFIRM SEARCH INTENT':
                    raise ValueError('Review and explicitly confirm the proposed intent first.')
                edits=data.get('review_edits','')
                if not isinstance(edits,str) or len(edits)>12000:
                    raise ValueError('Keep review edits within 12,000 characters.')
                prior=app.store.get('profile') or {}
                current_cv=app.store.get('cv_text') or prior.get('cv_text','')
                if current_cv!=proposal['cv_text']:
                    raise ValueError('CV changed; interpret it again before confirming.')
                reviewed=data.get('intent',proposal['intent'])
                if not isinstance(reviewed,dict) or reviewed.get('summary')!=proposal['intent']['summary']:
                    raise ValueError('Understanding changed; reinterpret your edits before confirming.')
                accepted_input=data.get('input',proposal['input'])
                if not isinstance(accepted_input,dict) or set(accepted_input)!=set(proposal['input']) or accepted_input.get('looking_for')!=proposal['input']['looking_for']:
                    raise ValueError('Next-move text changed; interpret it again before confirming.')
                if accepted_input.get('provider') not in ('codex','claude') or accepted_input.get('consent') is not True or any(type(accepted_input.get(k)) is not bool for k in ('linkedin_consent','secondary')):
                    raise ValueError('Confirm the current provider processing and explicit source permissions.')
                profile=confirm_intent(data.get('intent',proposal['intent']),prior,current_cv,proposal['evidence_text'],edits)
                profile.update(accepted_input)
                profile['intent_summary_edit']=proposal.get('summary_edit','')
                app.store.set('profile',profile)
                app.store.set('proposed_intent',None)
                app.store.preference_revision(bump=True)
                return {'saved':True}
            if path == '/api/profile':
                if app.v5:
                    raise ValueError('Update career direction in your own words, then review the AI understanding.')
                profile = validate_profile(data)
                profile['cv_text'] = app.store.get('cv_text','')
                profile['interpreted'] = (app.store.get('profile') or {}).get('interpreted')
                prior=app.store.get('profile') or {}
                for key in ('intent','intent_confirmed','looking_for','legacy_profile','intent_review_edits','intent_summary_edit'):
                    if key in prior:profile[key]=prior[key]
                if prior.get('intent'):profile['assessment_policy']='evidence-v4'
                if prior.get('intent') and any(prior.get(k)!=profile.get(k) for k in ('markets','hard_requirements','objectives')):
                    profile['intent_confirmed']=False
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
                    app.store.set('proposed_intent',None)
                    profile = app.store.get('profile')
                    if profile:
                        profile['cv_text'] = text
                        profile['interpreted'] = None
                        profile['intent_confirmed'] = False
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
                if app.simple:
                    profile=app.store.get('profile') or {}
                    return self.mutate('/api/career-search',{**{k:profile.get(k) for k in ('looking_for','provider','consent')},'secondary':bool(profile.get('secondary')),'linkedin_consent':bool(profile.get('linkedin_consent'))})
                run_id = app.start_search(data.get('market_id','all'))
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
            if path == '/api/outlook-history-import' and app.simple:
                if search_active or operation_active:
                    raise ValueError('Finish current research before importing application records.')
                from .outlook_history import match_outlook_messages
                messages=data.get('messages')
                if not isinstance(messages,list) or len(messages)>500:
                    raise ValueError('Use a read-only Outlook Job Radar message export.')
                if any(not isinstance(m,dict) or
                       sum(len(str(m.get(k,''))) for k in ('subject','bodyPreview','body_preview'))>6500
                       for m in messages):
                    raise ValueError('Invalid or excessively large Outlook message record.')
                return match_outlook_messages(app.store,messages,folder_name=data.get('folder','Job Radar'))
            if path == '/api/application':
                if search_active or operation_active:
                    raise ValueError('Finish current research before updating application history.')
                if not isinstance(data.get('job_id'),str) or data.get('status') not in ('none','saved','applied','rejected','interview','offer','dismissed'):
                    raise ValueError('Select a vacancy and a valid application status.')
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
                if app.v5:raise ValueError('Active source restrictions cannot be cleared here. Respect cooldown expiry or resolve the publisher restriction.')
                if data.get('confirm')!='REVIEWED SOURCE STOP':
                    raise ValueError('Review restriction/unknown request extent before resetting. Reset is not permission to bypass access denial.')
                app.store.set('linkedin_stop',None)
                app.store.set('linkedin_pending',False)
                return {'saved':True}
            if path == '/api/native-task':
                if app.skill_mode or app.v5:
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
