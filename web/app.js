'use strict';

// Untrusted profile, vacancy and AI strings enter the DOM through textContent only.
const $ = (selector, root = document) => root.querySelector(selector);
const LOCATION_STATUS={preferred:'Within preferred location',secondary_conditional:'Secondary / conditional location',verified_remote:'Verified remote opportunity',outside_preferred:'Outside preferred location',location_unknown:'Location unknown'};
const DIMENSIONS = {progression:'Career progression & leadership',technical:'Professional & technical fit',salary:'Salary & benefits',flexibility:'Work flexibility',company:'Company & industry',location:'Location & commuting',learning:'Learning & future opportunities'};
const STATUS = {none:'Not tracked',saved:'Saved',applied:'Applied',interview:'Interview',offer:'Offer',rejected:'Rejected',dismissed:'Dismissed'};
let state, view = 'discover', discoverTab = 'promising', marketTab = 'all', applicationTab = 'saved', wizardStep = 1, draft, filterText = '', filterCategory = 'all', sortBy = 'score', shown = 40, busy = false, intentText, intentReview, intentReviewKey, reviewEdits=[];

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
  const signature = JSON.stringify([state.catchup,state.updates,!!latestActive(),state.operation?.status==='running']);
  if (region.dataset.signature === signature) return;
  region.dataset.signature = signature;
  const due = state.catchup;
  const disabled = !!latestActive() || state.operation?.status==='running';
  region.replaceChildren(...(due ? [el('div',{class:'status-box warning',role:'region','aria-label':'Search reminder'},el('strong',{},'Your scheduled search is due'),el('p',{},'Missed slot: '+due.slot+'. Searches run only when you choose. Remind later waits one hour; Skip records this slot.'),actions(...[['Run now','run'],['Remind later','later'],['Skip','skip']].map(([label,action])=>button(label,()=>act('/api/catchup',{slot:due.slot,action},action==='run'?'AI search started.':'Reminder saved.'),action==='run'?'primary':'',disabled))))] : []));
  if(state.updates?.status==='available')region.append(el('div',{class:'status-box',role:'status'},el('strong',{},'JOB-RADAR AI '+state.updates.release_version+' is available'),safeLink(state.updates.url,'Release notes'),button('How to update',()=>navigate('preferences'))));
  if (state.skill_mode && !$('#close-workspace')) {
    $('.topbar > div').prepend(el('button',{id:'close-workspace',type:'button',onClick:async()=>{
      try { const result=await api('/api/close',{}); state=null; region.replaceChildren(); $('#main').replaceChildren(el('div',{class:'panel',role:'status'},el('h1',{},'Workspace closed'),el('p',{},result.message+' Invoke your JOB-RADAR skill to reopen.'))); $('#close-workspace').disabled=true; } catch(error){toast(error.message,true);}
    }},'Close workspace'));
    $('.version').textContent=(state.version?.version||'V2')+' · SKILL WORKSPACE';
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
function searchButton() { return button(marketTab==='all'?'Search all markets':'Search this country',()=>act('/api/search',{market_id:marketTab},'AI search started.'),'primary',!!latestActive()||state.operation?.status==='running'); }
function marketTabs() {
  const tabs=el('div',{class:'tabs',role:'group','aria-label':'Country markets'});
  for(const [id,label] of [...(state.profile?.markets||[]).map(m=>[m.id,m.country]),['all','All']]) {
    const control=button(label,()=>{marketTab=id;shown=40;render();},marketTab===id?'active':'');
    control.setAttribute('aria-pressed',String(marketTab===id));tabs.append(control);
  }
  return tabs;
}
function inMarket(job, market=marketTab) { return market==='all' || (job.display_country_id||job.country_id)===market; }
function marketJob(job, market=marketTab) {
  const configured=(state.profile?.markets||[]).map(m=>m.id);
  const assessments=Object.keys(job.market_evaluations||{});
  const regional=assessments.filter(id=>configured.includes(id));
  const preferred=regional.find(id=>job.market_evaluations[id].evaluation.recommend&&!job.market_evaluations[id].assessment_stale)||regional.find(id=>job.market_evaluations[id].evaluation.recommend)||regional[0];
  const key=job.country_id || (assessments.includes(market)?market:preferred||assessments[0]);
  const item=job.market_evaluations?.[key];
  // A missing country assessment must never borrow another country's or legacy evaluation.
  return {...job,evaluation:item?.evaluation || (!key?job.evaluation:undefined),assessment_stale:item?.assessment_stale??(!key?job.assessment_stale:false),assessment_market:key};
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
  root.append(button('Investigate promising opportunities',()=>act('/api/complete-descriptions',{},'Targeted description and freshness investigation started; no new discovery run.'),'',!!latestActive()||state.operation?.status==='running'||!state.jobs.some(j=>!j.description)));
  if(state.profile.market_migration?.review_required)root.append(el('div',{class:'status-box warning'},el('strong',{},'Review regional preferences before searching'),el('p',{},'Ambiguous legacy geography was preserved. Set each country’s conditions in Preferences, save, and confirm the review.'),button('Review in Preferences',()=>navigate('preferences'))));
  const outcome=marketTab==='all'?last?.payload:last?.payload.markets?.[marketTab];
  root.append(stat('Source limitations',new Set(outcome?.warnings||[]).size,'Latest selected market run'));
  const tabs=el('div',{class:'tabs',role:'group','aria-label':'Discovery views'});
  for (const [key,text] of [['promising','Promising — Needs Verification'],['recommended','Recommended'],['all','All Opportunities'],['new','New Opportunities']]) tabs.append(button(text,()=>{discoverTab=key;shown=40;render();},discoverTab===key?'active':''));
  root.append(el('div',{class:'section-head'},el('div',{},el('h2',{},'Opportunities worth a closer look'),el('p',{},'Career fit, transferable strengths and the facts still missing.')),tag('LinkedIn first','green')),tabs,filters());
  let jobs=marketJobs;
  if(discoverTab==='recommended') jobs=jobs.filter(recommended);
  if(discoverTab==='promising') jobs=jobs.filter(j=>j.preliminary?.promising&&!j.evaluation&&j.availability!=='closed_banner_observed');
  if(discoverTab==='new') jobs=jobs.filter(j => last?.payload.job_ids?.includes(j.id) && new Date(j.first_seen)>=new Date(last.started));
  jobs=filterJobs(jobs);
  if (!jobs.length) root.append(empty(discoverTab==='recommended'?'Your next opportunity starts here':'No jobs in this view',state.jobs.length?'Try All jobs or adjust your filters. Missing descriptions and low-ranked jobs are always retained.':'Start an AI search to discover real vacancies. Your AI chooses the queries; nothing here is demo data.',state.jobs.length?button('See all jobs',()=>{discoverTab='all';filterText='';filterCategory='all';render();}):searchButton()));
  else root.append(jobList(jobs));
  root.append(el('p',{class:'inline-note'},'Preliminary findings are useful leads, not full assessments. Research their description and freshness without repeating discovery.'));
  return root;
}
function freshnessLabel(job){return job.availability==='closed_banner_observed'?'Confirmed closed':job.freshness?.status==='confirmed_open'?'Confirmed open':'Güncellik doğrulanmadı';}
function countryLabel(job){const id=job.display_country_id||job.country_id;const country=state.profile?.markets.find(m=>m.id===id)?.country||id;return job.geography?.status==='inferred'?'Likely '+country+' · location inferred':country||'Location unverified';}
function recommended(job) { return job.evaluation?.recommend && !job.identity_review_required && job.location_status!=='outside_preferred' && ['none','saved'].includes(job.application_status) && job.availability!=='closed_banner_observed'; }

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
  return jobs.filter(j=>[j.title,j.company,j.location].some(s=>(s||'').toLowerCase().includes(query)) && (filterCategory==='all' || (filterCategory==='unevaluated'?!j.evaluation:(j.evaluation?.category||j.preliminary?.category||'unevaluated')===filterCategory))).sort((a,b)=>sortBy==='company'?(a.company||'').localeCompare(b.company||''):sortBy==='new'?b.first_seen.localeCompare(a.first_seen):Number(recommended(b))-Number(recommended(a))||b.first_seen.localeCompare(a.first_seen));
}
function jobList(jobs) { return el('div',{},el('div',{class:'job-grid'},jobs.slice(0,shown).map(card)),jobs.length>shown?button(`Show more (${jobs.length-shown} remaining)`,()=>{shown+=40;render();}):null,el('p',{class:'inline-note'},`${Math.min(shown,jobs.length)} of ${jobs.length} opportunities`)); }
function card(job) {
  const evaluation=job.evaluation;
  return el('article',{class:'job-card'},el('div',{class:'job-top'},el('div',{class:'company-mark','aria-hidden':'true'},(job.company||'?').slice(0,2).toUpperCase()),el('div',{},el('h3',{},job.title),el('div',{class:'company-line'},[job.company||'Employer not verified',job.location||'Location unknown'].join(' · ')))),
    el('div',{class:'job-tags'},tag(job.assessment_stale?'Reassessment pending':evaluation?.category.replaceAll('_',' ')||'Awaiting full evaluation',recommended(job)?'green':''),tag(countryLabel(job)),job.evaluation&&job.assessment_market?tag('Assessment: '+job.assessment_market):null,evaluation && evaluation.assessment_version!==2?tag('Legacy assessment','amber'):null,job.application_status!=='none'?tag(STATUS[job.application_status]):null,tag(job.description?'Description obtained':'Description missing',job.description?'':'amber'),tag(freshnessLabel(job),'amber')),
    el('p',{class:'job-summary'},evaluation?.summary||job.preliminary?.explanation||'This vacancy has been observed. Career fit requires further evidence.'),
    job.preliminary&&!evaluation?el('details',{},el('summary',{},'Observed evidence & what to verify'),el('p',{class:'prose'},(job.source_observations||[]).map(o=>o.text).join('\n')),el('ul',{},job.preliminary.gaps.map(g=>el('li',{},g)))):null,
    el('div',{class:'job-bottom'},el('div',{class:'score'},evaluation?.weighted_score!==null && evaluation?.weighted_score!==undefined?`Legacy score: ${evaluation.weighted_score} / 100`:evaluation?(evaluation.recommend?'AI recommended':'Review evidence'):job.preliminary?'Preliminary fit · needs verification':'Fit not assessed',el('small',{},job.assessment_stale?'Prior assessment retained until validated replacement':'Evidence-backed assessment')),actions(button('View opportunity',()=>detail(job)),button(job.application_status==='none'?'Save':'Saved / tracked',()=>act('/api/application',{job_id:job.id,status:'saved'},'Vacancy saved.'),'',job.application_status!=='none'))));
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
  dialog.dataset.jobId=job.id;
  const content=$('#job-dialog-content'); const evaluation=job.evaluation;
  const close=button('×',()=>$('#job-dialog').close());close.setAttribute('aria-label','Close opportunity details');
  const changeStatus=async status=>{await act('/api/application',{job_id:job.id,status},'Application history updated.');detail({...state.jobs.find(j=>j.id===job.id),assessment_market:job.assessment_market});};
  const select=el('select',{'aria-label':'Application status'},...Object.entries(STATUS).map(([key,text])=>el('option',{value:key},text)));
  select.value=job.application_status;
  select.addEventListener('change',()=>changeStatus(select.value));
  content.replaceChildren(el('div',{class:'dialog-head'},el('div',{},el('div',{class:'eyebrow'},job.source||'Source recorded'),el('h2',{},job.title),el('p',{class:'muted'},`${job.company||'Unknown employer'} · ${job.location||'Location unknown'}`)),close),
    actions(safeLink(job.url,'View original posting'),select,assessmentSelector(job),button('Refresh AI assessment',()=>act('/api/reevaluate',{job_id:job.id,market_id:job.assessment_market},'AI is reviewing this stored description. No source request is needed.'),'',!job.description||!!latestActive()||!state.profile.markets.some(m=>m.id===job.assessment_market))),
    actions(...['saved','applied','interview','offer','rejected','dismissed'].map(status=>button(STATUS[status],()=>changeStatus(status),'quiet',job.application_status===status))),
    el('div',{class:'details-meta'},tag(countryLabel(job)),job.location_status?tag(LOCATION_STATUS[job.location_status]||'Location unknown','amber'):null,job.integration==='experimental'?tag('Experimental source','amber'):null,job.identity_review_required?tag('Identity needs review','amber'):null,tag(freshnessLabel(job),'amber'),tag('First seen '+date(job.first_seen)),job.description_obtained?tag('Description '+date(job.description_obtained)):null),
    el('p',{class:'compact muted'},job.evidence||'Source observation only.'),
    ...(job.freshness?.published_at?[el('p',{class:'compact'},'Publisher publication date: '+job.freshness.published_at+' · checked '+date(job.freshness.checked_at))]:[]),
    descriptionPanel(job),
    ...(job.preliminary?[el('div',{class:'panel'},el('h3',{},'Preliminary career perspective'),tag('Title / indexed evidence only','amber'),el('p',{class:'prose'},job.preliminary.explanation),el('p',{},'Still to verify: '+job.preliminary.gaps.join('; ')))]:[]),
    el('details',{},el('summary',{},'Actually observed source evidence'),el('p',{class:'prose'},(job.source_observations||[]).map(o=>o.text).join('\n'))),
    evaluation?el('div',{},el('div',{class:'panel'},el('h3',{},'Career assessment'),el('p',{class:'prose'},evaluation.summary),el('div',{class:'job-tags'},tag(evaluation.category.replaceAll('_',' ')),tag(job.assessment_stale?'Reassessment pending · prior evidence retained':'Validated assessment'),evaluation.assessment_version!==2?tag(`Legacy score: ${evaluation.weighted_score??'Unknown'} / 100`):tag('Natural-language preferences · no weighted total')),el('p',{class:'inline-note'},'AI dimension assessments are subjective. Unknown facts require verification. ATS and HR explanations are separate; no proprietary ATS score is claimed.'),el('div',{class:'report-metrics'},Object.entries(evaluation.scores).map(([key,value])=>el('div',{},el('strong',{},value===null?'Unknown':value),el('small',{},DIMENSIONS[key]))))),
      el('div',{class:'details-columns'},el('div',{class:'panel'},el('h3',{},'ATS / CV readiness'),tag(evaluation.ats.readiness.replaceAll('_',' '),'amber'),el('p',{class:'prose'},evaluation.ats.explanation),el('h4',{},'Truthful CV improvements'),el('ul',{},evaluation.ats.truthful_cv_changes.map(t=>el('li',{},t)))),el('div',{class:'panel'},el('h3',{},'HR / Hiring manager'),el('p',{class:'prose'},evaluation.hr.assessment),el('h4',{},'Strengths'),el('ul',{},evaluation.hr.strengths.map(t=>el('li',{},t))),el('h4',{},'Gaps & interview risks'),el('ul',{},[...evaluation.hr.gaps,...evaluation.hr.interview_risks].map(t=>el('li',{},t))))),
      el('div',{class:'panel'},el('h3',{},'Evidence, not just a title'),evaluation.evidence.map(item=>el('div',{class:'evidence'},el('strong',{},item.requirement),el('blockquote',{},'Job: “'+item.job_quote+'”'),el('blockquote',{},item.cv_quote?'CV: “'+item.cv_quote+'”':'No direct CV quote; verify evidence.'),el('p',{},item.assessment))),evaluation.hard_requirements.map(item=>el('div',{class:'evidence'},tag(item.status,item.status==='violated'?'red':item.status==='unknown'?'amber':'green'),el('strong',{},' '+item.requirement),el('p',{},item.reason))),el('h4',{},'Information to verify'),el('ul',{},evaluation.missing_information.map(t=>el('li',{},t))))) : el('div',{class:'status-box warning'},el('strong',{},'Career fit has not been assessed.'),el('p',{},'A real full description and successful structured AI review are required. This vacancy remains visible.')),
    feedbackPanel(job),el('div',{class:'panel'},el('h3',{},'Application history'),job.events.length?el('div',{class:'timeline'},job.events.map(event=>el('span',{},STATUS[event.status]+' · '+date(event.at)))):el('p',{class:'muted'},'No application events yet.')),el('details',{},el('summary',{},'Read the retrieved full description'),el('p',{class:'prose'},job.description||'No full description has been obtained.')));
  if(!$('#job-dialog').open) $('#job-dialog').showModal();
  else if(wasOpen){close.focus({preventScroll:true});dialog.scrollTop=scroll;}
}
function feedbackPanel(job) {
  const selected=new Set();
  const reasons=['career direction','responsibilities','industry','compensation','working arrangement','location','growth opportunity'];
  const note=el('textarea',{placeholder:'Preference or context for this job','aria-label':'Feedback note',maxlength:'1000'});
  const last=job.feedback.at(-1);
  const save=async kind=>{await act('/api/feedback',{job_id:job.id,kind,reasons:[...selected],note:note.value},'Feedback saved. Prior recommendations remain visible while reassessment is pending.');detail({...state.jobs.find(j=>j.id===job.id),assessment_market:job.assessment_market});};
  return el('div',{class:'panel feedback-box'},el('h3',{},'Help your radar learn.'),el('p',{},'Like teaches AI; Save tracks your application. Rejections never train preferences. Default feedback scope: '+(job.country_id||'unclassified; review country before regional learning')+'.'),last?tag('Saved feedback: '+last.kind+' · '+last.scope,'green'):null,el('div',{class:'feedback-reasons'},reasons.map(reason=>el('label',{class:'check'},el('input',{type:'checkbox',onChange:event=>event.target.checked?selected.add(reason):selected.delete(reason)}),reason))),note,actions(...['like','dislike','irrelevant'].map(kind=>{const control=button(kind==='like'?'Like':kind==='irrelevant'?'Not relevant':'Dislike',()=>save(kind),last?.kind===kind?'primary':'');control.setAttribute('aria-pressed',String(last?.kind===kind));return control;})),job.feedback.length?el('details',{},el('summary',{},`Previous feedback · ${job.feedback.length}`),job.feedback.map(f=>el('p',{class:'compact'},`${f.kind} · ${f.scope} · ${f.reasons.join(', ')} · ${f.note} · ${date(f.at)}`))):null);
}
function assessmentSelector(job) {
  const markets=state.profile.markets||[];
  const relevant=job.country_id?[job.country_id]:Object.keys(job.market_evaluations||{});
  const label=id=>(markets.find(m=>m.id===id)?.country||id)+' assessment';
  if(relevant.length<=1 || job.country_id) return tag(job.assessment_market?label(job.assessment_market):'Assessment pending');
  const select=el('select',{'aria-label':'Assessment market',onChange:event=>detail({...job,assessment_market:event.target.value})},...relevant.map(id=>el('option',{value:id},label(id))));
  select.value=job.assessment_market||'';return select;
}
function descriptionPanel(job) {
  const labels={not_attempted:'Detail never attempted',budget_deferred:'Detail deferred by budget',failed:'Detail attempted and failed',blocked:'Source access restricted',incomplete:'Incomplete description',unavailable:'Verified source unavailable',unverified:'Alternative identity unverified',user_supplied:'User-supplied description · publisher retrieval unverified',public_verified:'Verified public source text',linkedin:'LinkedIn detail retrieved',available:'Stored description available'};
  const busy=!!latestActive()||state.operation?.status==='running';
  const panel=el('div',{class:'panel'},el('h3',{},'Full description'),tag(labels[job.description_status]||'Description missing','amber'));
  if(job.description_status==='blocked_shared_stop')panel.append(el('p',{},'Skipped due to an existing publisher stop; no new HTTP denial. Independent official sources may still be available.'));
  if(job.description_source_url)panel.append(safeLink(job.description_source_url,'Description source'),el('p',{class:'compact'},'Original posting identity is retained. Source retrieval: '+date(job.description_source?.at)));
  if(job.description_attempts?.length)panel.append(el('details',{},el('summary',{},'Retrieval attempts'),...job.description_attempts.map(a=>el('p',{},a.source+' · '+a.status+' · '+a.reason))));
  if(!job.description) {
    for(const candidate of job.description_candidates||[])panel.append(el('div',{class:'status-box warning'},el('strong',{},'Ambiguous source association — your confirmation is required'),el('p',{},candidate.company+' · '+candidate.title+' · '+candidate.location+' · '+(candidate.requisition_id||'ID unknown')),safeLink(candidate.url,'Verified source candidate'),button('Confirm this posting',async()=>{if(!confirm('Associate this fetched posting with this exact vacancy? Original ID, URL and history will remain.'))return;await act('/api/confirm-description-source',{job_id:job.id,candidate_id:candidate.candidate_id,confirm:'CONFIRM POSTING IDENTITY'},'Confirmed source association; existing country evaluation will run.');},'',busy)));
    panel.append(button('Find full description',()=>resolveDescription(job,'/api/resolve-description'),'',busy));
    const text=el('textarea',{'aria-label':'User-supplied job description',maxlength:'60000',placeholder:'Paste the full description for this exact vacancy (100–60,000 characters).'});
    panel.append(el('details',{},el('summary',{},'Supply a description yourself'),el('p',{},'This will be labeled user-supplied. It does not prove publisher retrieval or vacancy availability.'),text,button('Use supplied description',()=>resolveDescription(job,'/api/supplied-description',text.value),'',busy)));
  }
  return panel;
}
async function resolveDescription(job,path,description) {
  await act(path,{job_id:job.id,...(description!==undefined?{description}:{})},'Description operation started. Source evidence and assessment will be shown here.');
  if(state)detail({...state.jobs.find(j=>j.id===job.id),assessment_market:job.assessment_market});
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
  if(state.linkedin_access)root.append(el('div',{class:'status-box'},el('strong',{},'LinkedIn direct access: '+state.linkedin_access.state.replaceAll('_',' ')),el('p',{},state.linkedin_access.until?'Retry no earlier than '+date(state.linkedin_access.until)+'. No repeated attempts during this run.':'Direct access status is separate from indexed web discovery; availability does not prove a successful request.'),el('p',{},'Indexed LinkedIn vacancies can still be discovered through permitted web search.')));
  if(!state.runs.length) {root.append(empty('Your first report is one search away.','Every completed, partial, failed, canceled or skipped run is recorded here.',searchButton()));return root;}
  const latest=state.runs.find(r=>r.status!=='skipped')||state.runs[0];
  root.append(reportPanel(latest),el('div',{class:'section-head'},el('h2',{},'Search history'),el('p',{class:'muted'},'Compare results across runs')));
  const table=el('table',{},el('thead',{},el('tr',{},...['Run / date','Provider','Outcome','New','Seen before','Descriptions','AI reviews'].map(t=>el('th',{},t)))),el('tbody',{},state.runs.map(run=>el('tr',{},el('td',{},button(`#${run.id} · ${date(run.started)}`,()=>{const target=$('#historical-report');target.replaceChildren(reportPanel(run));target.scrollIntoView({behavior:'smooth'});},'text-link')),el('td',{},run.provider),el('td',{},tag(run.status,run.status==='completed'?'green':'amber')),...['new_jobs','previously_seen','descriptions','evaluated'].map(k=>el('td',{},run.payload[k]||0))))));
  root.append(el('div',{class:'panel report-history'},table),el('div',{id:'historical-report'}));return root;
}
function reportPanel(run) {
  const panel=reportContent(run);
  const retained=state.jobs.filter(j=>run.payload.job_ids?.includes(j.id)&&j.preliminary?.promising&&inMarket(j));
  if(retained.length)panel.append(el('div',{class:'panel'},el('h3',{},'Promising retained opportunities'),el('p',{},'These buttons open actual stored vacancy identities. The research narrative is an AI overview, not independent proof of additional postings.'),...retained.map(j=>button(j.title+' · '+(j.company||'Employer unverified'),()=>detail(marketJob(j)),'text-link'))));
  return panel;
}
function reportContent(run) {
  if(run.payload.markets) {
    const entries=Object.entries(run.payload.markets).filter(([id])=>marketTab==='all'||marketTab===id);
    const p=run.payload, jobs=state.jobs.filter(j=>p.job_ids?.includes(j.id)).map(j=>marketJob(j,'all'));
    const totals=[['All markets: discovered',p.discovered],['Full descriptions available',p.available_descriptions],['Jobs fully evaluated in run',p.evaluated],['Promising preliminary findings',p.promising],['Duplicate observations',p.duplicates],['Recommended now',jobs.filter(recommended).length],['Reassessment pending',jobs.filter(j=>j.assessment_stale).length],['Distinct limitations',(p.warnings||[]).length]];
    return el('div',{},el('h2',{},`Run #${run.id} · ${run.status} · ${p.kind==='v5_research'?'AI research batches':'market research'}`),el('p',{},`${p.web_calls||0} observed web-tool calls · ${p.requests||0} controlled retrieval requests · ${p.linkedin_requests||0} direct LinkedIn requests`),el('p',{},'Web-tool actions may contain multiple queries or page operations; these counts are not total Internet requests.'),el('div',{class:'report-metrics'},totals.map(([label,value])=>el('div',{},el('strong',{},value||0),el('small',{},label)))),el('details',{},el('summary',{},'Actually observed LinkedIn links'),...jobs.filter(j=>j.source==='LinkedIn indexed web').map(j=>safeLink(j.url,j.title))),...(p.warnings||[]).map(w=>el('p',{class:'status-box warning'},w)),...entries.map(([id,payload])=>el('section',{'aria-label':id+' search outcome'},el('h3',{},id+' market'),reportPanel({...run,status:payload.status,payload:{...payload,market_id:id}}))),!entries.length?el('p',{},'No outcome recorded for this market in this run.'):null);
  }
  let p=run.payload;
  if(p.kind==='description_recovery'&&marketTab!=='all'&&p.outcomes) {
    const outcomes=p.outcomes.filter(o=>o.country_id===marketTab);
    const metrics={attempted:outcomes.length,recovered:outcomes.filter(o=>o.recovered).length,unavailable:outcomes.filter(o=>!o.available&&!['blocked','blocked_shared_stop'].includes(o.status)).length,blocked:outcomes.filter(o=>['blocked','blocked_shared_stop'].includes(o.status)).length,evaluated:outcomes.filter(o=>o.evaluated).length,remaining:outcomes.filter(o=>!o.available).length};
    const ids=outcomes.map(o=>o.job_id);
    p={...p,metrics,job_ids:ids,sources:p.sources.filter(s=>ids.includes(s.job_id)),descriptions:metrics.recovered,evaluated:metrics.evaluated,previously_seen:outcomes.length};
  }
  const reportJobs=state.jobs.filter(j=>p.job_ids?.includes(j.id)).map(j=>marketJob(j,p.market_id||marketTab));
  const recommendedCount=reportJobs.filter(recommended).length;
  return el('article',{class:'panel'},el('div',{class:'report-row'},el('div',{},el('div',{class:'eyebrow'},`RUN #${run.id} · ${date(run.started)}`),el('h2',{},p.plan?'Your AI search briefing':'Run record')),tag(run.status,run.status==='completed'?'green':'amber')),
    p.metrics?el('div',{class:'report-metrics'},...Object.entries(p.metrics).map(([label,value])=>el('div',{},el('strong',{},value),el('small',{},label)))):null,
    p.kind==='description_recovery'?el('p',{class:'inline-note'},`${(p.sources||[]).filter(s=>s.status==='blocked_shared_stop').length} shared-stop skips · ${(p.sources||[]).filter(s=>[401,403,406,429,999].includes(s.http_status)).length} actual HTTP denials · ${p.status_counts?.budget_deferred||0} budget deferred`):null,
    el('div',{class:'report-metrics'},... [['Jobs discovered',p.discovered??p.job_ids?.length],['New jobs',p.new_jobs],['Previously seen',p.previously_seen],['Full descriptions available',p.available_descriptions??p.descriptions],['AI reviews',p.evaluated],['Recommended now',recommendedCount],['Reassessment pending',reportJobs.filter(j=>j.assessment_stale).length],['Source limitations',new Set(p.warnings||[]).size],['Source requests',p.requests],['Cache hits',p.cache_hits]].map(([label,value])=>el('div',{},el('strong',{},value||0),el('small',{},label)))),
    el('p',{class:'prose'},p.report||run.stage),p.plan?el('details',{open:''},el('summary',{},'The strategy your AI chose'),el('p',{class:'prose'},p.plan.strategy),el('div',{class:'job-tags'},p.plan.role_families.map(f=>tag(f))),p.plan.queries.map(q=>el('div',{class:'source-row'},el('div',{},el('strong',{},q.query),el('p',{class:'muted'},q.location+' · '+q.reason))))):null,
    el('h3',{},'Sources checked'),(p.sources||[]).map(source=>el('div',{class:'source-row'},el('div',{},el('strong',{},source.source),el('p',{class:'muted'},source.query||source.reason||''),source.board||source.diagnostics?.length?el('details',{},el('summary',{},'Source diagnostics'),source.board?safeLink(source.board.url,'Suggested employer board'):null,el('p',{},source.identity==='response_verified'?'Posting identity verified in source response':'Board identity not verified by a posting response'),el('pre',{class:'mono'},JSON.stringify(source.diagnostics||[],null,2))):null),el('div',{},tag(source.status,source.status==='success'?'green':'amber'),source.http_status?tag('HTTP '+source.http_status,'amber'):null,source.integration?tag(source.integration==='experimental'?'Experimental source':'Live-verified adapter','amber'):null,source.count!==undefined?el('span',{class:'compact'},' '+source.count+' observed'):null))),
    p.research?el('p',{class:'prose'},p.research.summary):null,(p.warnings||[]).length?el('div',{class:'status-box warning'},el('strong',{},'Limits & missing evidence'),el('ul',{},p.warnings.map(w=>el('li',{},w)))):null,
    el('p',{class:'inline-note'},'Counts record observations and obtained descriptions, not verified-open vacancies. Recommended count reflects your current profile and application state.'));
}

function defaultDraft() {return {objectives:'',seniority:'',leadership:'',industries:'',strengths:'',unwanted:'',hard_requirements:'',followup_answers:'',provider:'codex',markets:[],consent:false,linkedin_consent:false,secondary:false,frequency:'manual',time:'09:00',weekday:0};}

function field(key,label,placeholder='',wide=false,textarea=false) {
  const control=el(textarea?'textarea':'input',{id:'profile-'+key,value:draft[key]||'',placeholder,maxlength:'4000',onInput:event=>{draft[key]=event.target.value;}});
  return el('label',{class:'field'+(wide?' wide':''),for:'profile-'+key},label,control);
}
function check(key,text) { return el('label',{class:'check'},el('input',{type:'checkbox',checked:draft[key],onChange:event=>{draft[key]=event.target.checked;}}),text); }
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
    if(name==='codex'&&!info.authenticated) choices.append(el('div',{class:'status-box warning'},el('strong',{},info.installed?'Complete your Codex CLI sign-in':'Codex CLI setup needed'),el('p',{},'Desktop sign-in does not prove the separate CLI is ready. In Codex Desktop ask: "Prepare the JOB-RADAR AI Codex CLI and help me sign in with my own ChatGPT account." Codex can install the pinned CLI privately after your approval and start the official browser login; you do not need a terminal or an API key.'),el('p',{},'Then refresh installed environments and Test inference. Network permissions, account access or usage limits can still prevent AI execution.')));
  }
  return el('div',{},choices,button('Refresh installed environments',()=>act('/api/providers',{}),'text-link'),check('consent','I understand that my selected cloud AI provider processes the career context I send. Contact email, phone numbers and URLs are removed from extracted CV text, but other personal information may remain.'),check('linkedin_consent','I understand that LinkedIn guest endpoints are unsupported, automated use can conflict with LinkedIn terms, and coverage and vacancy openness are not guaranteed. No account or cookies are used.'),check('secondary','Allow AI public web research for vacancies, including indexed LinkedIn links and employer careers. Only observed source evidence is imported. Personal CV content must never be used as public search text.'));
}
function scheduleFields() {
  const frequency=el('select',{id:'frequency',onChange:event=>{draft.frequency=event.target.value;}},...['manual','daily','weekly'].map(f=>el('option',{value:f},f[0].toUpperCase()+f.slice(1))));frequency.value=draft.frequency;
  const weekday=el('select',{id:'weekday',onChange:event=>{draft.weekday=Number(event.target.value);}},...['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((day,i)=>el('option',{value:i},day)));weekday.value=draft.weekday;
  return el('div',{},el('div',{class:'field-grid'},el('label',{class:'field',for:'frequency'},'Search frequency',frequency),el('label',{class:'field',for:'search-time'},'Local time',el('input',{id:'search-time',type:'time',value:draft.time,onChange:event=>{draft.time=event.target.value;}})),el('label',{class:'field',for:'weekday'},'Weekday (weekly searches)',weekday)),el('p',{class:'inline-note'},state.skill_mode ? `Computer timezone: ${state.timezone}. When you open the dashboard after a missed search, choose Run now, Remind later or Skip. Nothing searches automatically while closed.` : `Computer timezone: ${state.timezone}. Automatic searches run while the local server is running. A Windows task requires a separate confirmation. A switched-off computer cannot search.`));
}
function onboarding() {
  draft ||= defaultDraft();
  return el('div',{class:'wizard'},title('Let’s find what’s next for you.','Your CV and your own words guide the search. Review the AI interpretation before discovery.'),intentPanel());
}
function preferences() {
  if(!draft){draft=defaultDraft();for(const key of Object.keys(draft))if(state.profile?.[key]!==undefined)draft[key]=structuredClone(state.profile[key]);}
  return el('div',{},title('Your next move.','Edit your own words, then review the interpretation.'),intentPanel(),el('div',{class:'panel'},el('h2',{},'Search routine'),scheduleFields(),button('Save routine',()=>act('/api/routine',{frequency:draft.frequency,time:draft.time,weekday:draft.weekday},'Search routine saved.'))),el('div',{class:'panel'},el('h2',{},'Private workspace'),actions(safeDownload(),button('Create local backup',()=>act('/api/backup',{},'Private backup saved.')))),updatePanel());
}
function intentPanel() {
  intentText ??= state.proposed_intent?.input?.looking_for ?? state.profile?.looking_for ?? state.profile?.objectives ?? '';
  const original=el('div',{},cvUpload(),el('label',{class:'field',for:'next-move'},'What are you looking for in your next career move?',el('textarea',{id:'next-move',value:intentText,rows:'7',maxlength:'12000',placeholder:'Describe what matters to you in your own words. Unknown details can stay unknown.',onInput:event=>{intentText=event.target.value;}})));
  const root=el('div',{class:'panel'},original);
  if(state.intent_review_required)root.append(el('p',{class:'status-box warning'},'Review your preserved settings before replacing them. No new CV upload is required.'));
  root.append(el('details',{},el('summary',{},'Privacy & AI connection'),providerFields()));
  if(state.profile)root.append(button('Save privacy & connection',()=>act('/api/connection',{provider:draft.provider,consent:draft.consent,linkedin_consent:draft.linkedin_consent,secondary:draft.secondary},'Privacy and connection saved.')));
  const active=!!latestActive()||state.operation?.status==='running';
  if(state.operation)root.append(el('div',{class:'status-box',role:'status'},state.operation.kind+' · '+state.operation.status,el('p',{},state.operation.message),active?button('Cancel',()=>act('/api/cancel',{})):null));
  root.append(button('Search with AI',async()=>{await act('/api/career-search',{looking_for:intentText,provider:draft.provider,consent:draft.consent,linkedin_consent:draft.linkedin_consent,secondary:draft.secondary},'AI is interpreting your complete request and starting research.');},'primary',active));
  return root;
}
function updatePanel() {
  const info=state.updates;
  const enabled=el('input',{type:'checkbox',checked:state.update_notifications,onChange:event=>act('/api/update-notifications',{enabled:event.target.checked},'Startup version check preference saved.')});
  return el('div',{class:'panel'},el('h2',{},'Application updates'),el('p',{},'Installed version: '+(state.version?.version||'2.1-preview')),el('p',{},'Only public GitHub Release metadata is queried. Your CV, profile and history stay local. Updates require your approval in Codex Desktop.'),button('Check for updates',()=>act('/api/check-updates',{},'Checking public stable release metadata.'),'',state.update_check_running),el('label',{class:'check'},enabled,'Check public version metadata when this dashboard starts'),info?el('div',{class:'status-box'},el('strong',{},info.status==='available'?'Update available: '+info.release_version:info.status.replaceAll('_',' ')),info.url?safeLink(info.url,'Read release notes'):null,el('p',{class:'prose'},info.notes||info.message||'Your installed version is current.'),info.instruction?el('p',{},info.instruction):null):null,el('p',{},'To update, ask Codex: “Update my JOB-RADAR AI”. Codex reviews an exact stable release and preserves this same workspace. This button does not control your Codex chat.'));
}
function safeDownload(){return el('a',{href:'/api/export',download:'job-radar-private-export.json'},'Export private data');}
view=['discover','applications','reports','preferences'].includes(location.hash.slice(1))?location.hash.slice(1):'discover';
refresh();
setInterval(async()=>{if(!state)return;const checking=state.update_check_running;const wasActive=!!latestActive()||state.operation?.status==='running';await refresh(false);if(wasActive||checking){if(wasActive&&!latestActive()&&state.operation?.status!=='running'){toast('AI operation finished. Review its status and evidence.');const dialog=$('#job-dialog');const job=state.jobs.find(j=>j.id===dialog.dataset.jobId);if(dialog.open&&job)detail(job);}render();}},3000);
