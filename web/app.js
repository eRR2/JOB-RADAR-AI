'use strict';

// Untrusted profile, vacancy and AI strings enter the DOM through textContent only.
const $ = (selector, root = document) => root.querySelector(selector);
const DIMENSIONS = {progression:'Career progression & leadership',technical:'Professional & technical fit',salary:'Salary & benefits',flexibility:'Work flexibility',company:'Company & industry',location:'Location & commuting',learning:'Learning & future opportunities'};
const STATUS = {none:'Not tracked',saved:'Saved',applied:'Applied',interview:'Interview',offer:'Offer',rejected:'Rejected',dismissed:'Dismissed'};
let state, view = 'discover', discoverTab = 'recommended', marketTab = 'all', applicationTab = 'saved', wizardStep = 1, draft, filterText = '', filterCategory = 'all', sortBy = 'score', shown = 40, busy = false;

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'value') node.value = value;
    else if (key === 'checked' || key === 'disabled' || key === 'hidden') node[key] = value;
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}
const button = (text, action, kind = '', disabled = false) => el('button',{type:'button',class:kind,onClick:action,disabled},text);
const tag = (text, kind = '') => el('span',{class:'tag '+kind},text);
const date = value => value ? new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}) : 'No searches yet';
const actions = (...children) => el('div',{class:'actions'},children);
function toast(message, error = false) { const node = $('#toast'); node.textContent = message; node.className = error ? 'error' : ''; node.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { node.hidden = true; }, error ? 10000 : 4500); }
async function api(path, data, options = {}) {
  const response = await fetch(path,{method:data !== undefined ? 'POST' : 'GET',headers:data !== undefined ? {'Content-Type':'application/json','X-Radar-CSRF':state.csrf,...options.headers} : {},body:data !== undefined ? (options.raw ? data : JSON.stringify(data)) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || 'Local request failed.');
  return result;
}
async function act(path, data, message) { try { await api(path,data); await refresh(); if (message) toast(message); } catch (error) { toast(error.message,true); } }
async function refresh(renderPage = true) {
  try {
    state = await api('/api/state');
    updateCatchup();
    const provider = state.providers[state.profile?.provider || draft?.provider || 'codex'];
    $('#provider-pill').textContent = provider?.last_verified ? `${(state.profile?.provider || draft?.provider) === 'claude' ? 'Claude Code' : 'Codex'} · last inference verified` : provider?.authenticated ? 'Subscription login detected' : 'Select your AI environment';
    $('#application-count').textContent = state.jobs.filter(j => ['applied','interview','offer'].includes(j.application_status)).length;
    if (renderPage) render();
  } catch(error) { toast('Workspace unavailable: '+error.message,true); }
}
function navigate(next) { view=next; shown=40; location.hash=next; render(); $('#main').focus(); }
document.querySelectorAll('[data-view]').forEach(node => node.addEventListener('click',() => navigate(node.dataset.view)));
window.addEventListener('hashchange',() => { const next=location.hash.slice(1); if (['discover','applications','reports','preferences'].includes(next)) { view=next; render(); } });

function render() {
  if (!state) return;
  document.querySelectorAll('[data-view]').forEach(node => { node.classList.toggle('active',node.dataset.view===view); if(node.dataset.view===view) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current'); });
  $('#breadcrumb').textContent = 'Workspace / '+(state.profile ? view[0].toUpperCase()+view.slice(1) : 'Welcome');
  const main = $('#main');
  main.replaceChildren(!state.profile ? onboarding() : ({discover:discover,applications:applications,reports:reports,preferences:preferences}[view])());
}
function updateCatchup() {
  const region = $('#catchup');
  const signature = JSON.stringify([state.catchup,!!latestActive(),state.operation?.status==='running']);
  if (region.dataset.signature === signature) return;
  region.dataset.signature = signature;
  const due = state.catchup;
  const disabled = !!latestActive() || state.operation?.status==='running';
  region.replaceChildren(...(due ? [el('div',{class:'status-box warning',role:'region','aria-label':'Search reminder'},el('strong',{},'Your scheduled search is due'),el('p',{},'Missed slot: '+due.slot+'. Searches run only when you choose. Remind later waits one hour; Skip records this slot.'),actions(...[['Run now','run'],['Remind later','later'],['Skip','skip']].map(([label,action])=>button(label,()=>act('/api/catchup',{slot:due.slot,action},action==='run'?'AI search started.':'Reminder saved.'),action==='run'?'primary':'',disabled))))] : []));
  if (state.skill_mode && !$('#close-workspace')) {
    $('.topbar > div').prepend(el('button',{id:'close-workspace',type:'button',onClick:async()=>{
      try { const result=await api('/api/close',{}); state=null; region.replaceChildren(); $('#main').replaceChildren(el('div',{class:'panel',role:'status'},el('h1',{},'Workspace closed'),el('p',{},result.message+' Invoke your JOB-RADAR skill to reopen.'))); $('#close-workspace').disabled=true; } catch(error){toast(error.message,true);}
    }},'Close workspace'));
    $('.version').textContent='V2 · SKILL WORKSPACE';
  }
}
function title(name, description) { return el('div',{class:'page-title'},el('div',{class:'eyebrow'},'YOUR CAREER WORKSPACE'),el('h1',{},name),el('p',{},description)); }
function empty(name, description, action) { return el('div',{class:'empty'},el('div',{class:'empty-icon','aria-hidden':'true'},'◎'),el('h3',{},name),el('p',{},description),action); }
function latestActive() { return state.runs.find(run => run.status==='running'); }
function runStatus() {
  const run=latestActive();
  if (run) return el('div',{class:'status-box',role:'status'},el('span',{class:'pulse'}),el('strong',{},run.stage),el('p',{},`Run #${run.id} · ${run.provider} · started ${date(run.started)}`),button('Cancel run',()=>act('/api/cancel',{},'Cancellation requested.')));
  const last=state.runs[0];
  if (!last || last.status==='completed') return null;
  return el('div',{class:'status-box '+(['failed','canceled'].includes(last.status)?'error':'warning')},el('strong',{},`Latest run: ${last.status}`),el('p',{},last.stage),... (last.payload.warnings||[]).slice(0,3).map(w=>el('p',{},w)));
}
function searchButton() { return button(marketTab==='all'?'Search all markets':'Search this country',()=>act('/api/search',{market_id:marketTab},'AI search started.'),'primary',marketTab==='unclassified'||!!latestActive()||state.operation?.status==='running'); }
function marketTabs() {
  const tabs=el('div',{class:'tabs',role:'group','aria-label':'Country markets'});
  for(const [id,label] of [...(state.profile?.markets||[]).map(m=>[m.id,m.country]),['all','All'],['unclassified','Country unverified']]) {
    const control=button(label,()=>{marketTab=id;shown=40;render();},marketTab===id?'active':'');
    control.setAttribute('aria-pressed',String(marketTab===id));tabs.append(control);
  }
  return tabs;
}
function inMarket(job, market=marketTab) { return market==='all' || (market==='unclassified'?!job.country_id:job.country_id===market || (!job.country_id && job.market_ids?.includes(market))); }
function marketJob(job, market=marketTab) {
  const configured=(state.profile?.markets||[]).map(m=>m.id);
  const assessments=Object.keys(job.market_evaluations||{});
  const regional=assessments.filter(id=>configured.includes(id));
  const preferred=regional.find(id=>job.market_evaluations[id].evaluation.recommend&&!job.market_evaluations[id].assessment_stale)||regional.find(id=>job.market_evaluations[id].evaluation.recommend)||regional[0];
  const key=market==='all' || market==='unclassified' ? job.country_id || preferred || assessments[0] : market;
  const item=job.market_evaluations?.[key];
  return {...job,evaluation:item?.evaluation||job.evaluation,assessment_stale:item?.assessment_stale??job.assessment_stale,assessment_market:key};
}
function visibleJobs() { return state.jobs.filter(j=>inMarket(j)).map(j=>marketJob(j)); }
function discoveryCounts(jobs) {
  return [['Jobs discovered',jobs.length],['Full descriptions',jobs.filter(j=>j.description).length],['AI evaluated',jobs.filter(j=>j.evaluation).length],['Recommended',jobs.filter(recommended).length],['Reassessment pending',jobs.filter(j=>j.assessment_stale).length]];
}

function radar() { return el('div',{class:'radar-wrap','aria-hidden':'true'},el('div',{class:'radar'},el('div',{class:'radar-center'},'◎'),el('i',{class:'radar-dot one'}),el('i',{class:'radar-dot two'}),el('i',{class:'radar-dot three'})),el('div',{class:'radar-label'},'A wider view of your next move')); }
function discover() {
  const last=state.runs.find(r=>r.status!=='skipped');
  const marketJobs=visibleJobs();
  const root=el('div',{},el('div',{class:'hero'},el('div',{},el('div',{class:'eyebrow'},'OPPORTUNITIES, WITH PERSPECTIVE'),el('h1',{},'Your next chapter, found.'),el('p',{},'Your AI explores the roles you know — and the paths you may not have considered. Every recommendation starts with your experience.'),actions(searchButton(),button('Tune your preferences',()=>navigate('preferences'),'quiet')),el('div',{class:'inline-note'},'Last search: '+date(last?.started))),radar()),runStatus());
  root.append(marketTabs(),el('div',{class:'stat-grid'},discoveryCounts(marketJobs).map(([label,value])=>stat(label,value,'Selected market · retained state'))));
  if(state.profile.market_migration?.review_required)root.append(el('div',{class:'status-box warning'},el('strong',{},'Review regional preferences before searching'),el('p',{},'Ambiguous legacy geography was preserved. Set each country’s conditions in Preferences, save, and confirm the review.'),button('Review in Preferences',()=>navigate('preferences'))));
  const outcome=marketTab==='all'?last?.payload:last?.payload.markets?.[marketTab];
  root.append(stat('Source limitations',new Set(outcome?.warnings||[]).size,'Latest selected market run'));
  const tabs=el('div',{class:'tabs',role:'group','aria-label':'Discovery views'});
  for (const [key,text] of [['recommended','Recommended'],['all','All jobs'],['new','New discoveries']]) tabs.append(button(text,()=>{discoverTab=key;shown=40;render();},discoverTab===key?'active':''));
  root.append(el('div',{class:'section-head'},el('div',{},el('h2',{},'Opportunities worth a closer look'),el('p',{},'Career fit, transferable strengths and the facts still missing.')),tag('LinkedIn first','green')),tabs,filters());
  let jobs=marketJobs;
  if(discoverTab==='recommended') jobs=jobs.filter(recommended);
  if(discoverTab==='new') jobs=jobs.filter(j => last?.payload.job_ids?.includes(j.id) && new Date(j.first_seen)>=new Date(last.started));
  jobs=filterJobs(jobs);
  if (!jobs.length) root.append(empty(discoverTab==='recommended'?'Your next opportunity starts here':'No jobs in this view',state.jobs.length?'Try All jobs or adjust your filters. Missing descriptions and low-ranked jobs are always retained.':'Start an AI search to discover real vacancies. Your AI chooses the queries; nothing here is demo data.',state.jobs.length?button('See all jobs',()=>{discoverTab='all';filterText='';filterCategory='all';render();}):searchButton()));
  else root.append(jobList(jobs));
  root.append(el('p',{class:'inline-note'},'Guest endpoints provide limited coverage. Observed listings are not confirmed open; check the original posting before applying.'));
  return root;
}
function recommended(job) { return job.evaluation?.recommend && ['none','saved'].includes(job.application_status) && job.availability!=='closed_banner_observed'; }

function stat(label,value,note) { return el('div',{class:'stat'},el('small',{},label),el('strong',{},value),el('p',{},note)); }
function filters() {
  const search=el('input',{type:'search',placeholder:'Search title, company or location…','aria-label':'Search discovered jobs',value:filterText});
  search.addEventListener('input',()=>{filterText=search.value;updateList();});
  const category=el('select',{'aria-label':'Career fit category',onChange:event=>{filterCategory=event.target.value;render();}},...['all','direct','transferable','stretch','unrelated','needs_verification','unevaluated'].map(key=>el('option',{value:key},key.replaceAll('_',' '))));
  category.value=filterCategory;
  const sort=el('select',{'aria-label':'Sort opportunities',onChange:event=>{sortBy=event.target.value;render();}},el('option',{value:'score'},'Recommended first'),el('option',{value:'new'},'Newest discovered'),el('option',{value:'company'},'Company A–Z'));
  sort.value=sortBy;
  return el('div',{class:'filters'},search,category,sort);
}
function updateList() {
  // Preserve focus/caret in search control while updating the list.
  const input=$('input[type=search]'); const position=input.selectionStart;
  render(); const next=$('input[type=search]'); next?.focus(); try {next?.setSelectionRange(position,position);} catch {}
}
function filterJobs(jobs) {
  const query=filterText.toLowerCase();
  return jobs.filter(j=>[j.title,j.company,j.location].some(s=>(s||'').toLowerCase().includes(query)) && (filterCategory==='all' || (j.evaluation?.category||'unevaluated')===filterCategory)).sort((a,b)=>sortBy==='company'?(a.company||'').localeCompare(b.company||''):sortBy==='new'?b.first_seen.localeCompare(a.first_seen):Number(recommended(b))-Number(recommended(a))||b.first_seen.localeCompare(a.first_seen));
}
function jobList(jobs) { return el('div',{},el('div',{class:'job-grid'},jobs.slice(0,shown).map(card)),jobs.length>shown?button(`Show more (${jobs.length-shown} remaining)`,()=>{shown+=40;render();}):null,el('p',{class:'inline-note'},`${Math.min(shown,jobs.length)} of ${jobs.length} opportunities`)); }
function card(job) {
  const evaluation=job.evaluation;
  return el('article',{class:'job-card'},el('div',{class:'job-top'},el('div',{class:'company-mark','aria-hidden':'true'},(job.company||'?').slice(0,2).toUpperCase()),el('div',{},el('h3',{},job.title),el('div',{class:'company-line'},[job.company||'Employer not verified',job.location||'Location unknown'].join(' · ')))),
    el('div',{class:'job-tags'},tag(job.assessment_stale?'Reassessment pending':evaluation?.category.replaceAll('_',' ')||'Awaiting full evaluation',recommended(job)?'green':''),tag(job.country_id||'Country unverified'),job.assessment_market?tag('Assessment: '+job.assessment_market):null,evaluation && evaluation.assessment_version!==2?tag('Legacy assessment','amber'):null,job.application_status!=='none'?tag(STATUS[job.application_status]):null,tag(job.description?'Description obtained':'Description missing',job.description?'':'amber')),
    el('p',{class:'job-summary'},evaluation?.summary||'This vacancy has been observed. Career fit requires a retrieved description and AI assessment.'),
    el('div',{class:'job-bottom'},el('div',{class:'score'},evaluation?.weighted_score!==null && evaluation?.weighted_score!==undefined?`Legacy score: ${evaluation.weighted_score} / 100`:evaluation?(evaluation.recommend?'AI recommended':'Review evidence'):'Fit not assessed',el('small',{},job.assessment_stale?'Prior assessment retained until validated replacement':'Evidence-backed assessment')),actions(button('View opportunity',()=>detail(job)),button(job.application_status==='none'?'Save':'Saved / tracked',()=>act('/api/application',{job_id:job.id,status:'saved'},'Vacancy saved.'),'',job.application_status!=='none'))));
}
function applications() {
  const root=el('div',{},title('Keep your next move in view.','Saved opportunities, active applications and a dated history — all in one place.'));
  const tabs=el('div',{class:'tabs',role:'group','aria-label':'Application views'});
  const groups={saved:['saved'],ongoing:['applied','interview','offer'],history:['rejected','dismissed']};
  for(const key of Object.keys(groups)) tabs.append(button(key[0].toUpperCase()+key.slice(1)+` · ${state.jobs.filter(j=>groups[key].includes(j.application_status)).length}`,()=>{applicationTab=key;render();},applicationTab===key?'active':''));
  root.append(tabs,filters());
  const jobs=filterJobs(state.jobs.filter(j=>groups[applicationTab].includes(j.application_status)).map(j=>marketJob(j,'all')));
  root.append(jobs.length?jobList(jobs):empty('Nothing here yet.',applicationTab==='saved'?'Save an opportunity from Discover to revisit it here.':'Update a saved opportunity to Applied, Interview, Offer, Rejected or Dismissed. Every transition keeps its date.',button('Explore discoveries',()=>navigate('discover'))));
  return root;
}
function safeLink(url, text) {
  try { const parsed=new URL(url); if(parsed.protocol!=='https:'||parsed.username||parsed.password) throw new Error(); return el('a',{href:parsed.href,target:'_blank',rel:'noopener noreferrer'},text); }
  catch { return el('span',{class:'muted'},'Original URL unavailable / unsafe'); }
}
function detail(job) {
  job=marketJob(state.jobs.find(j=>j.id===job.id)||job,job.assessment_market||marketTab);
  const dialog=$('#job-dialog'), wasOpen=dialog.open, scroll=dialog.scrollTop;
  const content=$('#job-dialog-content'); const evaluation=job.evaluation;
  const close=button('×',()=>$('#job-dialog').close());close.setAttribute('aria-label','Close opportunity details');
  const changeStatus=async status=>{await act('/api/application',{job_id:job.id,status},'Application history updated.');detail({...state.jobs.find(j=>j.id===job.id),assessment_market:job.assessment_market});};
  const select=el('select',{'aria-label':'Application status'},...Object.entries(STATUS).map(([key,text])=>el('option',{value:key},text)));
  select.value=job.application_status;
  select.addEventListener('change',()=>changeStatus(select.value));
  content.replaceChildren(el('div',{class:'dialog-head'},el('div',{},el('div',{class:'eyebrow'},job.source||'Source recorded'),el('h2',{},job.title),el('p',{class:'muted'},`${job.company||'Unknown employer'} · ${job.location||'Location unknown'}`)),close),
    actions(safeLink(job.url,'View original posting'),select,assessmentSelector(job),button('Refresh AI assessment',()=>act('/api/reevaluate',{job_id:job.id,market_id:job.assessment_market},'AI is reviewing this stored description. No source request is needed.'),'',!job.description||!!latestActive()||!state.profile.markets.some(m=>m.id===job.assessment_market))),
    actions(...['saved','applied','interview','offer','rejected','dismissed'].map(status=>button(STATUS[status],()=>changeStatus(status),'quiet',job.application_status===status))),
    el('div',{class:'details-meta'},tag(job.availability==='closed_banner_observed'?'Closed banner observed':'Availability unconfirmed','amber'),tag('First seen '+date(job.first_seen)),job.description_obtained?tag('Description '+date(job.description_obtained)):null),
    el('p',{class:'compact muted'},job.evidence||'Source observation only.'),
    evaluation?el('div',{},el('div',{class:'panel'},el('h3',{},'Career assessment'),el('p',{class:'prose'},evaluation.summary),el('div',{class:'job-tags'},tag(evaluation.category.replaceAll('_',' ')),tag(job.assessment_stale?'Reassessment pending · prior evidence retained':'Validated assessment'),evaluation.assessment_version!==2?tag(`Legacy score: ${evaluation.weighted_score??'Unknown'} / 100`):tag('Natural-language preferences · no weighted total')),el('p',{class:'inline-note'},'AI dimension assessments are subjective. Unknown facts require verification. ATS and HR explanations are separate; no proprietary ATS score is claimed.'),el('div',{class:'report-metrics'},Object.entries(evaluation.scores).map(([key,value])=>el('div',{},el('strong',{},value===null?'Unknown':value),el('small',{},DIMENSIONS[key]))))),
      el('div',{class:'details-columns'},el('div',{class:'panel'},el('h3',{},'ATS / CV readiness'),tag(evaluation.ats.readiness.replaceAll('_',' '),'amber'),el('p',{class:'prose'},evaluation.ats.explanation),el('h4',{},'Truthful CV improvements'),el('ul',{},evaluation.ats.truthful_cv_changes.map(t=>el('li',{},t)))),el('div',{class:'panel'},el('h3',{},'HR / Hiring manager'),el('p',{class:'prose'},evaluation.hr.assessment),el('h4',{},'Strengths'),el('ul',{},evaluation.hr.strengths.map(t=>el('li',{},t))),el('h4',{},'Gaps & interview risks'),el('ul',{},[...evaluation.hr.gaps,...evaluation.hr.interview_risks].map(t=>el('li',{},t))))),
      el('div',{class:'panel'},el('h3',{},'Evidence, not just a title'),evaluation.evidence.map(item=>el('div',{class:'evidence'},el('strong',{},item.requirement),el('blockquote',{},'Job: “'+item.job_quote+'”'),el('blockquote',{},item.cv_quote?'CV: “'+item.cv_quote+'”':'No direct CV quote; verify evidence.'),el('p',{},item.assessment))),evaluation.hard_requirements.map(item=>el('div',{class:'evidence'},tag(item.status,item.status==='violated'?'red':item.status==='unknown'?'amber':'green'),el('strong',{},' '+item.requirement),el('p',{},item.reason))),el('h4',{},'Information to verify'),el('ul',{},evaluation.missing_information.map(t=>el('li',{},t))))) : el('div',{class:'status-box warning'},el('strong',{},'Career fit has not been assessed.'),el('p',{},'A real full description and successful structured AI review are required. This vacancy remains visible.')),
    feedbackPanel(job),el('div',{class:'panel'},el('h3',{},'Application history'),job.events.length?el('div',{class:'timeline'},job.events.map(event=>el('span',{},STATUS[event.status]+' · '+date(event.at)))):el('p',{class:'muted'},'No application events yet.')),el('details',{},el('summary',{},'Read the retrieved full description'),el('p',{class:'prose'},job.description||'No full description has been obtained.')));
  if(!$('#job-dialog').open) $('#job-dialog').showModal();
  else if(wasOpen){close.focus({preventScroll:true});dialog.scrollTop=scroll;}
}
function feedbackPanel(job) {
  const selected=new Set();
  const reasons=['too software-heavy','too junior','wrong sector','low salary','interesting career progression','commute','leadership scope','transferable skills'];
  const note=el('textarea',{placeholder:'Preference or context for this job','aria-label':'Feedback note',maxlength:'1000'});
  const global=el('input',{type:'checkbox'});
  const last=job.feedback.at(-1);
  const save=async kind=>{await act('/api/feedback',{job_id:job.id,kind,reasons:[...selected],note:note.value,scope:global.checked?'global':undefined},'Feedback saved. Prior recommendations remain visible while reassessment is pending.');detail({...state.jobs.find(j=>j.id===job.id),assessment_market:job.assessment_market});};
  return el('div',{class:'panel feedback-box'},el('h3',{},'Help your radar learn.'),el('p',{},'Like teaches AI; Save tracks your application. Rejections never train preferences. Default feedback scope: '+(job.country_id||'unclassified; review country before regional learning')+'.'),last?tag('Saved feedback: '+last.kind+' · '+last.scope,'green'):null,el('label',{class:'check'},global,'Apply to all markets'),el('div',{class:'feedback-reasons'},reasons.map(reason=>el('label',{class:'check'},el('input',{type:'checkbox',onChange:event=>event.target.checked?selected.add(reason):selected.delete(reason)}),reason))),note,actions(...['like','dislike','irrelevant'].map(kind=>{const control=button(kind==='like'?'Like':kind[0].toUpperCase()+kind.slice(1),()=>save(kind),last?.kind===kind?'primary':'');control.setAttribute('aria-pressed',String(last?.kind===kind));return control;})),job.feedback.length?el('details',{},el('summary',{},`Previous feedback · ${job.feedback.length}`),job.feedback.map(f=>el('p',{class:'compact'},`${f.kind} · ${f.scope} · ${f.reasons.join(', ')} · ${f.note} · ${date(f.at)}`))):null);
}
function assessmentSelector(job) {
  const select=el('select',{'aria-label':'Assessment market',onChange:event=>detail({...job,assessment_market:event.target.value})},...(state.profile.markets||[]).map(m=>el('option',{value:m.id},m.country+' assessment')));
  select.value=job.assessment_market||'';return select;
}
function backdropClick(event) {
  const dialog=event.currentTarget;
  if(event.target!==dialog)return;
  const r=dialog.getBoundingClientRect();
  if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();
}

$('#job-dialog').addEventListener('click',backdropClick);
$('#job-dialog').addEventListener('close',()=>{if(document.activeElement===document.body||!document.activeElement?.isConnected)$('#main').focus();});
function reports() {
  const root=el('div',{},title('The story behind your search.','What your AI explored, what it found and what still needs verification.'),marketTabs(),runStatus());
  if(!state.runs.length) {root.append(empty('Your first report is one search away.','Every completed, partial, failed, canceled or skipped run is recorded here.',searchButton()));return root;}
  const latest=state.runs.find(r=>r.status!=='skipped')||state.runs[0];
  root.append(reportPanel(latest),el('div',{class:'section-head'},el('h2',{},'Search history'),el('p',{class:'muted'},'Compare results across runs')));
  const table=el('table',{},el('thead',{},el('tr',{},...['Run / date','Provider','Outcome','New','Seen before','Descriptions','AI reviews'].map(t=>el('th',{},t)))),el('tbody',{},state.runs.map(run=>el('tr',{},el('td',{},button(`#${run.id} · ${date(run.started)}`,()=>{const target=$('#historical-report');target.replaceChildren(reportPanel(run));target.scrollIntoView({behavior:'smooth'});},'text-link')),el('td',{},run.provider),el('td',{},tag(run.status,run.status==='completed'?'green':'amber')),...['new_jobs','previously_seen','descriptions','evaluated'].map(k=>el('td',{},run.payload[k]||0))))));
  root.append(el('div',{class:'panel report-history'},table),el('div',{id:'historical-report'}));return root;
}
function reportPanel(run) {
  if(run.payload.markets) {
    const entries=Object.entries(run.payload.markets).filter(([id])=>marketTab==='all'||marketTab===id);
    const p=run.payload, jobs=state.jobs.filter(j=>p.job_ids?.includes(j.id)).map(j=>marketJob(j,'all'));
    const totals=[['All markets: discovered',p.discovered],['Full descriptions available',p.available_descriptions],['Jobs AI-evaluated in run',p.evaluated],['Market assessments in run',p.market_assessments],['Recommended now',jobs.filter(recommended).length],['Reassessment pending',jobs.filter(j=>j.assessment_stale).length],['Distinct limitations',(p.warnings||[]).length]];
    return el('div',{},el('h2',{},`Run #${run.id} · ${run.status} · one shared source budget`),el('p',{},`${p.requests||0} total network requests`),el('div',{class:'report-metrics'},totals.map(([label,value])=>el('div',{},el('strong',{},value||0),el('small',{},label)))),...entries.map(([id,payload])=>el('section',{'aria-label':id+' search outcome'},el('h3',{},id+' market'),reportPanel({...run,status:payload.status,payload:{...payload,market_id:id}}))),!entries.length?el('p',{},'No outcome recorded for this market in this run.'):null);
  }
  const p=run.payload;
  const reportJobs=state.jobs.filter(j=>p.job_ids?.includes(j.id)).map(j=>marketJob(j,p.market_id||marketTab));
  const recommendedCount=reportJobs.filter(recommended).length;
  return el('article',{class:'panel'},el('div',{class:'report-row'},el('div',{},el('div',{class:'eyebrow'},`RUN #${run.id} · ${date(run.started)}`),el('h2',{},p.plan?'Your AI search briefing':'Run record')),tag(run.status,run.status==='completed'?'green':'amber')),
    el('div',{class:'report-metrics'},... [['Jobs discovered',p.discovered??p.job_ids?.length],['New jobs',p.new_jobs],['Previously seen',p.previously_seen],['Full descriptions available',p.available_descriptions??p.descriptions],['AI reviews',p.evaluated],['Recommended now',recommendedCount],['Reassessment pending',reportJobs.filter(j=>j.assessment_stale).length],['Source limitations',new Set(p.warnings||[]).size],['Source requests',p.requests],['Cache hits',p.cache_hits]].map(([label,value])=>el('div',{},el('strong',{},value||0),el('small',{},label)))),
    el('p',{class:'prose'},p.report||run.stage),p.plan?el('details',{open:''},el('summary',{},'The strategy your AI chose'),el('p',{class:'prose'},p.plan.strategy),el('div',{class:'job-tags'},p.plan.role_families.map(f=>tag(f))),p.plan.queries.map(q=>el('div',{class:'source-row'},el('div',{},el('strong',{},q.query),el('p',{class:'muted'},q.location+' · '+q.reason))))):null,
    el('h3',{},'Sources checked'),(p.sources||[]).map(source=>el('div',{class:'source-row'},el('div',{},el('strong',{},source.source),el('p',{class:'muted'},source.query||source.reason||'')),el('div',{},tag(source.status,source.status==='success'?'green':'amber'),source.count!==undefined?el('span',{class:'compact'},' '+source.count+' observed'):null))),
    p.research?el('p',{class:'prose'},p.research.summary):null,(p.warnings||[]).length?el('div',{class:'status-box warning'},el('strong',{},'Limits & missing evidence'),el('ul',{},p.warnings.map(w=>el('li',{},w)))):null,
    el('p',{class:'inline-note'},'Counts record observations and obtained descriptions, not verified-open vacancies. Recommended count reflects your current profile and application state.'));
}

function defaultDraft() {return {objectives:'',seniority:'',leadership:'',industries:'',strengths:'',unwanted:'',hard_requirements:'',followup_answers:'',provider:'codex',markets:[{id:'DE',country:'Germany',locations:['Germany'],languages:'German / English',conditions:'',hard_requirements:''},{id:'NL',country:'Netherlands',locations:['Netherlands'],languages:'Dutch / English',conditions:'',hard_requirements:''}],consent:false,linkedin_consent:false,secondary:false,frequency:'manual',time:'09:00',weekday:0};}

function field(key,label,placeholder='',wide=false,textarea=false) {
  const control=el(textarea?'textarea':'input',{id:'profile-'+key,value:draft[key]||'',placeholder,maxlength:'4000',onInput:event=>{draft[key]=event.target.value;}});
  return el('label',{class:'field'+(wide?' wide':''),for:'profile-'+key},label,control);
}
function check(key,text) { return el('label',{class:'check'},el('input',{type:'checkbox',checked:draft[key],onChange:event=>{draft[key]=event.target.checked;}}),text); }
function careerFields() { return el('div',{class:'field-grid'},field('objectives','What would make your next move worthwhile?','The impact, progression or change you want…',true,true),field('seniority','Desired seniority','Senior, lead, manager…'),field('leadership','Leadership responsibilities','People, technical direction, delivery…'),field('industries','Industries you are interested in','Areas you want to explore…'),field('strengths','Technical & transferable strengths','What you want the AI to understand…',false,true)); }
function locationFields() {return el('div',{class:'field-grid'},field('unwanted','Globally unwanted roles or industries','What does not suit you?',true,true),field('hard_requirements','Global non-negotiables','One hard requirement per line',true,true));}
function marketFields() {
  const root=el('div',{});
  draft.markets.forEach((market,index)=>{
    const fields=el('div',{class:'field-grid'});
    for(const [key,label] of [['id','Country code (two letters)'],['country','Country name'],['locations','Search locations (one per line)'],['languages','Search / working languages'],['conditions','Regional career conditions: commute, relocation, workplace, salary, hours'],['hard_requirements','Regional non-negotiables (one per line)']]) {
      const input=el(['conditions','hard_requirements','locations'].includes(key)?'textarea':'input',{'aria-label':market.country+' '+label,value:key==='locations'?market.locations.join('\n'):market[key],maxlength:'4000',onInput:event=>{market[key]=key==='locations'?event.target.value.split('\n').filter(x=>x.trim()):event.target.value;}});
      fields.append(el('label',{class:'field'},label,input));
    }
    root.append(el('div',{class:'panel'},el('h3',{},market.country+' market'),fields,button('Remove market',()=>{draft.markets.splice(index,1);render();},'quiet',draft.markets.length===1)));
  });
  root.append(button('Add country market',()=>{draft.markets.push({id:'',country:'New country',locations:[''],languages:'',conditions:'',hard_requirements:''});render();},'',draft.markets.length>=6));
  const migration=state.profile?.market_migration;
  if(migration)root.append(el('details',{open:migration.review_required?'':undefined},el('summary',{},migration.review_required?'Review required: legacy geography':'Preserved legacy geography'),el('p',{},'Copy the relevant conditions into each market and save preferences. Ambiguous text was preserved without guessing. Old unclassified feedback is retained in job details and is excluded from regional learning; resubmit it locally or explicitly globally.'),...Object.entries(migration.legacy_geography||{}).filter(([,value])=>value).map(([key,value])=>el('p',{},key+': '+value)),migration.review_required?button('Save conditions & confirm my review',async()=>{if(await saveProfile())await act('/api/migration-review',{confirm:'REVIEWED LEGACY GEOGRAPHY'},'Migration review recorded.');}):null));
  return root;
}



function cvUpload() {
  const input=el('input',{type:'file',accept:'.pdf,.docx','aria-label':'Upload your PDF or DOCX CV',onChange:async event=>{
    const file=event.target.files[0];if(!file)return;
    if(file.size>10000000){toast('Use a CV up to 10 MB.',true);return;}
    event.target.disabled=true;
    try{await api('/api/cv',await file.arrayBuffer(),{raw:true,headers:{'Content-Type':'application/octet-stream','X-Filename':'CV'+file.name.slice(file.name.lastIndexOf('.'))}});await refresh();toast('CV text extracted locally. Review the preview before AI processing.');}catch(error){toast(error.message,true);event.target.disabled=false;}
  }});
  return el('div',{},el('div',{class:'upload-box'},el('h3',{},state.cv.text?'Your CV is ready to review.':'Start with your experience.'),el('p',{},'Upload a text PDF or DOCX · Up to 10 MB · Stored only on this computer'),input,state.cv.filename?el('p',{},`${state.cv.filename} · ${state.cv.text.length.toLocaleString()} characters extracted`):null),state.cv.text?el('details',{},el('summary',{},'Preview the exact extracted text sent to your selected AI'),el('p',{class:'prose'},state.cv.text)):null);
}
function providerFields() {
  const choices=el('div',{class:'provider-cards'});
  for(const name of ['codex','claude']) {
    const info=state.providers[name];
    choices.append(el('div',{class:'provider-card'+(draft.provider===name?' selected':'')},el('h3',{},name==='codex'?'OpenAI Codex':'Anthropic Claude Code'),el('p',{},info.status),tag(info.installed?'Installed':'Not installed',info.installed?'green':'amber'),tag(info.authenticated?'Subscription login detected':'Login not verified',info.authenticated?'green':'amber'),el('p',{},info.last_verified?'Last inference: '+date(info.last_verified.at):'A saved login is not a live inference test.'),button(draft.provider===name?'Selected':'Select provider',()=>{draft.provider=name;render();}),button('Test inference',()=>act('/api/provider-probe',{provider:name},'Bounded inference test started.'),'quiet',!info.installed)));
  }
  return el('div',{},choices,button('Refresh installed environments',()=>act('/api/providers',{}),'text-link'),check('consent','I understand that my selected cloud AI provider processes the career context I send. Contact email, phone numbers and URLs are removed from extracted CV text, but other personal information may remain.'),check('linkedin_consent','I understand that LinkedIn guest endpoints are unsupported, automated use can conflict with LinkedIn terms, and coverage and vacancy openness are not guaranteed. No account or cookies are used.'),check('secondary','Allow supplementary AI web research on public official vacancy sources. Actual tool retrieval must be observable; unverified results are not imported.'));
}
function scheduleFields() {
  const frequency=el('select',{id:'frequency',onChange:event=>{draft.frequency=event.target.value;}},...['manual','daily','weekly'].map(f=>el('option',{value:f},f[0].toUpperCase()+f.slice(1))));frequency.value=draft.frequency;
  const weekday=el('select',{id:'weekday',onChange:event=>{draft.weekday=Number(event.target.value);}},...['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day,i)=>el('option',{value:i},day)));weekday.value=draft.weekday;
  return el('div',{},el('div',{class:'field-grid'},el('label',{class:'field',for:'frequency'},'Search frequency',frequency),el('label',{class:'field',for:'search-time'},'Local time',el('input',{id:'search-time',type:'time',value:draft.time,onChange:event=>{draft.time=event.target.value;}})),el('label',{class:'field',for:'weekday'},'Weekday (weekly searches)',weekday)),el('p',{class:'inline-note'},state.skill_mode ? `Computer timezone: ${state.timezone}. When you open the dashboard after a missed search, choose Run now, Remind later or Skip. Nothing searches automatically while closed.` : `Computer timezone: ${state.timezone}. Automatic searches run while the local server is running. A Windows task requires a separate confirmation. A switched-off computer cannot search.`));
}
async function saveProfile(analyze=false) {
  if(busy)return;busy=true;
  try {
    if(!state.cv.text) throw new Error('Upload a readable PDF or DOCX CV first.');
    if(!draft.consent||!draft.linkedin_consent) throw new Error('Review and confirm the provider processing and LinkedIn guest-use disclosures.');
    await api('/api/profile',draft);
    if(analyze) await api('/api/profile-analysis',{});
    view='preferences';await refresh();toast(analyze?'Profile saved. Your AI is interpreting the CV.':'Profile saved.');return true;
  } catch(error){toast(error.message,true);return false;}finally{busy=false;}
}
function onboarding() {
  draft ||= defaultDraft();
  const root=el('div',{class:'wizard'},el('div',{class:'hero'},el('div',{},el('div',{class:'eyebrow'},'WELCOME TO JOB-RADAR AI'),el('h1',{},'Let’s find what’s next for you.'),el('p',{},'Give your radar a little context. Your own AI environment will turn your experience into a thoughtful career search.'))));
  root.append(el('div',{class:'steps'},...['Your experience','What matters to you','Your AI & routine'].map((label,i)=>el('div',{class:'step'+(wizardStep===i+1?' active':'')},el('span',{},i+1),label))));
  const panel=el('div',{class:'panel'});
  if(wizardStep===1)panel.append(cvUpload(),el('h2',{},'A little about your next chapter'),careerFields());
  if(wizardStep===2)panel.append(el('h2',{},'Independent country markets'),locationFields(),marketFields());
  if(wizardStep===3)panel.append(el('h2',{},'Use the AI environment you already own.'),providerFields(),el('hr',{class:'divider'}),el('h3',{},'Choose your search rhythm'),scheduleFields());
  panel.append(el('div',{class:'wizard-footer'},el('p',{},`Step ${wizardStep} of 3 · Personal data stays out of GitHub`),actions(wizardStep>1?button('Back',()=>{wizardStep--;render();}):null,wizardStep<3?button('Continue →',()=>{if(wizardStep===1&&(!state.cv.text||!draft.objectives.trim())){toast('Upload your CV and describe your career objectives first.',true);return;}wizardStep++;render();},'primary'):button('Build my career profile →',()=>saveProfile(true),'primary'))));
  root.append(panel);return root;
}
function preferences() {
  if(!draft) {draft=defaultDraft();for(const key of Object.keys(draft))if(state.profile[key]!==undefined)draft[key]=structuredClone(state.profile[key]);}
  const root=el('div',{},title('Make this search your own.','Your experience, priorities and explicit feedback guide every AI decision.'));
  if(state.operation)root.append(el('div',{class:'status-box '+(state.operation.status==='failed'?'error':'')},el('strong',{},`${state.operation.kind} · ${state.operation.status}`),el('p',{},state.operation.message),state.operation.status==='running'?button('Cancel',()=>act('/api/cancel',{})):null));
  const proposed=state.proposed_profile;
  if(proposed) {
    const summary=el('textarea',{'aria-label':'Edit proposed career summary',value:proposed.summary});
    root.append(el('div',{class:'panel'},el('div',{class:'eyebrow'},'YOUR AI CAREER PROFILE · REVIEW BEFORE USING'),el('h2',{},'What your experience makes possible'),summary,el('ul',{},proposed.strengths.map(s=>el('li',{},s))),proposed.gaps.length?el('p',{class:'prose'},'To verify: '+proposed.gaps.join('; ')):null,proposed.questions.length?el('div',{},el('h3',{},'A few things worth clarifying'),el('ul',{},proposed.questions.map(q=>el('li',{},q))),field('followup_answers','Your answers','Only clarify what matters…',true,true)):null,actions(button('Use this reviewed profile',()=>act('/api/profile-accept',{summary:summary.value,followup_answers:draft.followup_answers},'Reviewed career profile accepted.'),'primary'),button('Interpret CV again',()=>act('/api/profile-analysis',{},'AI profile interpretation started.')))));
  }
  root.append(el('div',{class:'panel'},el('div',{class:'panel-head'},el('h2',{},'Your experience & direction'),button('Save preferences',()=>saveProfile(),'primary')),cvUpload(),careerFields()),el('div',{class:'panel'},el('h2',{},'Global preferences & non-negotiables'),locationFields()),el('div',{class:'panel'},el('h2',{},'Independent country markets'),marketFields()));
  const learned=el('textarea',{'aria-label':'Editable learned preferences',value:state.global_learned.map(p=>p.text).join('\n'),placeholder:'One genuinely global preference per line'});
  const paused=el('input',{type:'checkbox',checked:state.learning_paused,'aria-label':'Pause automatic preference learning'});
  root.append(el('div',{class:'panel'},el('h2',{},'Global learned preferences'),el('p',{},state.learning_explanation||'No learned preferences yet. Explicit job feedback will be considered in later searches.'),el('div',{class:'job-tags'},state.global_learned.map(p=>tag(p.confidence,p.confidence==='tentative'?'amber':'green'))),learned,el('label',{class:'check'},paused,'Pause automatic learning and keep my edits.'),actions(button('Save learned preferences',()=>act('/api/learned',{preferences:learned.value.split('\n').filter(Boolean),paused:paused.checked,scope:'global'},'Learned preferences saved.')),button('Reset learning',()=>{if(confirm('Reset learned preferences and pause automatic learning? Past job feedback will remain available.'))act('/api/learning-reset',{confirm:'RESET LEARNING'},'Learning reset.');},'danger'))),el('div',{class:'panel'},el('h2',{},'Your AI environment'),providerFields(),el('hr',{class:'divider'}),button('Interpret my CV with AI',()=>act('/api/profile-analysis',{},'AI profile interpretation started.'))),el('div',{class:'panel'},el('h2',{},'Search routine'),scheduleFields(),actions(button('Save routine & preferences',()=>saveProfile(),'primary'),state.skill_mode?null:button('Create Windows scheduled task',async()=>{if(!confirm('Create a Windows Task Scheduler task named JOB-RADAR-AI using your saved daily/weekly time? It runs with your logged-in account, while the computer is on. Existing tasks are never overwritten.'))return;try{await api('/api/profile',draft);await act('/api/native-task',{confirm:'CREATE WINDOWS TASK'},'Windows scheduled task created.');}catch(error){toast(error.message,true);}})),!state.skill_mode&&state.native_task?el('p',{class:'inline-note'},state.native_task.message+' Saved task uses '+state.native_task.schedule.frequency+' at '+state.native_task.schedule.time+'. Later schedule edits require updating the task in Windows Task Scheduler.'):null));
  for(const market of state.profile.markets) {
    const info=state.market_state[market.id];
    const input=el('textarea',{'aria-label':market.country+' learned preferences',value:info.learned.map(p=>p.text).join('\n')});
    root.append(el('div',{class:'panel'},el('h2',{},market.country+' learning'),el('p',{},info.learning_explanation||'Only this country feedback and explicit global feedback influence this market.'),input,button('Save regional learning',()=>act('/api/learned',{scope:market.id,preferences:input.value.split('\n').filter(Boolean),paused:paused.checked},'Regional learning saved.'))));
  }
  if(state.learned.length)root.append(el('details',{},el('summary',{},'Preserved legacy learned preferences · review scope'),...state.learned.map(p=>el('p',{},p.text))));
  root.append(budgetPanel(),el('div',{class:'panel'},el('h2',{},'Private data, under your control'),el('p',{},'CVs, profile, feedback, reports and SQLite backups stay in the ignored local .private folder. Your selected AI provider receives career context; its own data policies and history controls apply.'),actions(safeDownload(),button('Create local SQLite backup',()=>act('/api/backup',{},'Local backup created.')),button('Delete local career data',()=>{if(confirm('Permanently delete this app’s career database contents, CV and app-created backups? AI-provider-owned history and Windows scheduled tasks are managed separately.'))act('/api/erase',{confirm:'DELETE LOCAL CAREER DATA'},'Local career data deleted.').then(()=>{draft=null;wizardStep=1;render();});},'danger'))));
  return root;
}
function safeDownload(){return el('a',{href:'/api/export',download:'job-radar-private-export.json'},'Export private data');}
function budgetPanel(){
  const controls={}; const limits={searches:[1,6,'AI search queries'],pages:[1,2,'Pages per query'],details:[1,8,'Full descriptions'],requests:[1,16,'Total source requests'],spacing:[5,60,'Spacing in seconds']};
  const fields=el('div',{class:'field-grid'});
  for(const[key,[min,max,label]]of Object.entries(limits)){controls[key]=el('input',{type:'number',min,max,value:state.budgets[key],'aria-label':label});fields.append(el('label',{class:'field'},label,controls[key],el('small',{},`${min}–${max}`)));}
  return el('div',{class:'panel'},el('h2',{},'Keep source access bounded'),el('p',{},'Budgets are operating limits, not permission from LinkedIn. Successful search responses cache for 2 hours; descriptions for 24 hours. Access restrictions stop future requests.'),fields,el('p',{class:'inline-note'},'Last successful LinkedIn request: '+date(state.linkedin_last_success)),state.linkedin_stop||state.linkedin_pending?el('div',{class:'status-box warning'},el('strong',{},'Source access stopped'),el('p',{},state.linkedin_stop||'An interrupted request has unknown extent. No automatic retry.'),button('Review & clear stop',()=>{if(confirm('Have you reviewed this source stop? Do not retry access denial or bypass a restriction. Clear only after the restriction is resolved or an interrupted request is understood.'))act('/api/source-reset',{confirm:'REVIEWED SOURCE STOP'},'Source stop cleared by your explicit action.');})):null,button('Save request budgets',()=>act('/api/budgets',Object.fromEntries(Object.entries(controls).map(([k,input])=>[k,Number(input.value)])),'Source budgets saved.')));
}
view=['discover','applications','reports','preferences'].includes(location.hash.slice(1))?location.hash.slice(1):'discover';
refresh();
setInterval(async()=>{if(!state)return;const wasActive=!!latestActive()||state.operation?.status==='running';await refresh(false);if(wasActive){if(!latestActive()&&state.operation?.status!=='running'){toast('AI operation finished. Review its status and evidence.');}render();}},3000);
