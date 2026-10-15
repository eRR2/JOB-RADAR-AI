const $=s=>document.querySelector(s);
let state,tab='recommended',view='discover',careerDraft,diagnosticsOpen=false;
function el(name,attrs={},...children){
  const node=document.createElement(name);
  for(const [k,v] of Object.entries(attrs)){
    if(k.startsWith('on'))node.addEventListener(k.slice(2).toLowerCase(),v);
    else if(k==='class')node.className=v;
    else if(k==='value'||k==='checked'||k==='disabled')node[k]=v;
    else node.setAttribute(k,v);
  }
  for(const child of children.flat())if(child!==null&&child!==undefined)node.append(child instanceof Node?child:document.createTextNode(String(child)));
  return node;
}
const button=(text,action,kind='',disabled=false)=>el('button',{type:'button',class:kind,onClick:action,disabled},text);
const tag=(text,kind='')=>el('span',{class:'tag '+kind},text);
const priority=job=>({exceptional:4,strong:3,consider:2,weak:1,unsuitable:0})[job.preliminary?.priority]||0;
function verifiedSource(job){return ['public_verified','linkedin'].includes(job.description_source?.kind)&&String(job.description||'').length>=100;}
function reviewClosed(job){return job.availability_review_closed??(job.availability==='closed_banner_observed'||job.freshness?.status==='confirmed_closed');}
function recommended(job){return verifiedSource(job)&&!!job.preliminary?.recommend&&!job.preliminary?.critical_gap&&job.evaluation_status!=='needs_verification'&&!job.preliminary_stale&&['none','saved'].includes(job.application_status||'none')&&!reviewClosed(job);}
function evidenceLabel(job){
  if(['public_verified','linkedin'].includes(job.description_source?.kind)&&job.description)return 'Full source description verified';
  if(job.partial_source_text)return 'Partial source text verified · full description unverified';
  if(job.source_observations?.length)return 'Preliminary · search snippet only';
  return 'Description unavailable';
}
function freshnessLabel(job){return reviewClosed(job)?'Source channel confirmed closed':job.freshness?.status==='confirmed_open'?'Publisher-confirmed open':'Güncellik doğrulanmadı';}
function toast(text,error=false){$('#toast').textContent=text;$('#toast').className=error?'error':'';$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,6000);}
async function api(path,data){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-Radar-CSRF':state.csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();if(!response.ok)throw Error(result.error?.message||'Operation failed.');return result;
}
async function act(path,data){try{await api(path,data);await refresh();}catch(e){toast(e.message,true);}}
function working(){return state.runs.some(r=>r.status==='running')||state.operation?.status==='running';}
function safeLink(url,text){try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password)return el('a',{href:u.href,target:'_blank',rel:'noopener noreferrer'},text);}catch{}return el('span',{},'Source link unavailable');}
const compact=(text,limit=45)=>String(text||'').split(/\s+/).slice(0,limit).join(' ');
function review(job){
  if(job.review_state)return job.review_state;
  if(reviewClosed(job))return {status:'excluded',reason:'confirmed_closed'};
  if(job.evaluation_status==='needs_verification'||job.preliminary_stale)return {status:'needs_verification',reason:'evidence_validation'};
  if(job.preliminary)return {status:'assessed'};
  return {status:job.shortlist_status==='low_relevance'?'not_selected':'pending',reason:'not_started'};
}
function reviewCounts(){
  if(state.review_coverage)return state.review_coverage;
  const jobs=state.jobs.filter(j=>j.shortlist_status!=='low_relevance');
  return {selected:jobs.length,...Object.fromEntries(['assessed','pending','excluded','needs_verification'].map(k=>[k,jobs.filter(j=>review(j).status===k).length]))};
}
function coverageText(){const c=reviewCounts();return c.selected+' review candidates · '+c.assessed+' assessed · '+c.pending+' pending · '+c.excluded+' excluded · '+c.needs_verification+' need evidence verification'+(c.verified_assessed===undefined?'':' · '+c.verified_assessed+' assessed against verified full text · '+c.source_pending+' awaiting full source');}
function reviewReason(job){
  return ({triage_timeout:'Triage time limit reached; suitability was not assessed.',triage_error:'Triage failed; suitability was not assessed.',triage_budget:'Triage budget reached before this candidate; suitability was not assessed.',confirmed_closed:'Excluded from suitability review: source confirmed closed.',application_recorded:'Application recorded for this exact position; technical fit is a separate question.',identity_or_obsolete_review:'Identity or obsolete status requires review.',
    evaluation_timeout:'Evaluation time limit reached; suitability remains unassessed.',evaluation_budget:'Evaluation budget exhausted; suitability remains unassessed.',evaluation_error:'Evaluation failed; no completed assessment is available.',
    evidence_validation:'Assessment evidence needs verification; recommendation withheld.',full_source_required:'Verified full duties and requirements are needed before a final assessment.',triage_not_selected:'Not selected by career relevance triage; no suitability assessment.',triage_reason_missing:'Individual triage rationale was not recorded; suitability remains unverified.',triage_not_reached:'Research stopped before relevance triage; suitability remains unassessed.',canceled:'Research was canceled before this assessment.',not_started:'Assessment not started; suitability is unverified.'})[review(job).reason]||'Suitability remains unverified.';
}
function fieldLabel(job,field,fallback){const hint=job.inferred_fields?.[field];return job[field]|| (hint?hint.value+' (source title; unverified)':fallback);}
function salaryLabel(job){
  const hint=job.inferred_fields?.salary;
  const text=job.salary?.stated||job.salary_stated||hint?.value||job.preliminary?.salary_evidence||'Not stated';
  return text+(hint?' (source title; unverified)':'')+(/up to|bis zu/i.test(text)||hint?.interpretation==='advertised_upper_bound'?' · Advertised upper bound; not guaranteed':'');
}
function assessmentSummary(job){
  const p=job.preliminary;
  if(review(job).status!=='assessed')return el('p',{class:'job-summary'},reviewReason(job));
  return el('div',{},el('p',{class:'job-summary'},'Known fit: '+compact(p?.evidence?.[0]?.assessment||'Specific capability evidence not supplied.',30)),
    el('p',{class:'job-summary'},'Assessment: '+compact(p?.next_step,job.description?70:45)),
    !job.description||p?.gaps?.length?el('p',{class:'muted'},'Missing for full assessment: '+compact((p?.gaps||[]).slice(0,2).join('; ')||'Full responsibilities and requirements remain unverified.',40)):null);
}
function sourceAndTriage(job){
  const d=job.triage_decision,notes=Object.values(job.source_availability||{});
  return el('div',{},d?el('p',{class:'muted'},'Triage: '+compact(d.reason,30)+' · Transferable fit: '+compact(d.transferable_fit||'Not established',25)+' · Specialist gap: '+compact(d.specialist_gap||'Not established',25)+(d.evidence_issue?' · Evidence needs verification: '+d.evidence_issue:'')):null,
    ...notes.map(n=>el('p',{class:'muted'},n.channel+': '+n.status+' · '+(n.access_status||'observed')+(n.http_status?' HTTP '+n.http_status:'')+' · '+n.provenance+' · '+(n.checked_at?'Checked '+n.checked_at:'Check time unknown')+(n.reported_at?' · Reported '+n.reported_at:'')+' · '+compact(n.quote,20),safeLink(n.url,' Source'))));
}
function statusPanel(){
  const run=state.runs[0],operation=state.operation;
  if(working())return el('div',{class:'status-box',role:'status'},el('strong',{},operation?.status==='running'?'Interpreting your career request':run?.stage),el('p',{},'Findings appear as they are saved.'),button('Cancel',()=>act('/api/cancel',{})));
  const problem=operation?.status==='failed'?operation:run?.payload.provider_error;
  const providerFailure=['subscription_usage_limit','model_access','provider_rate_limit','execution_error'].includes(problem?.category);
  if(problem)return el('div',{class:'status-box error',role:'alert'},el('strong',{},'AI research could not finish'),el('p',{},problem.message),el('p',{},providerFailure?'No automatic retry. Check the provider error above before another search.':'No automatic retry. '+(problem.category==='time_window'?'The processing time limit was reached.':problem.category==='canceled'?'The operation was canceled.':'Review the specific validation reason above; your saved preferences remain unchanged.')));
  const counts=reviewCounts();
  if(run?.status==='partial'||run?.status==='canceled'||counts.pending||counts.needs_verification)return el('div',{class:'status-box',role:'status'},el('strong',{},'Research incomplete'),el('p',{},coverageText()),el('p',{},'Saved findings are retained. Missing assessments are listed separately; no automatic retry.'));
  return null;
}
function researchDiagnostics(){
  const run=state.runs[0],d=run?.payload?.diagnostics;if(!d)return null;
  const usage=run.payload.usage||{},c=d.counts||{},descriptions=d.descriptions||{};
  const table=(head,rows)=>el('div',{class:'report-history'},el('table',{},el('thead',{},el('tr',{},head.map(h=>el('th',{scope:'col'},h)))),el('tbody',{},rows.map(row=>el('tr',{},row.map(value=>el('td',{},value??'Not reported')))))));
  return el('details',{class:'panel research-diagnostics',...(diagnosticsOpen?{open:''}:{}),onToggle:event=>diagnosticsOpen=event.target.open},el('summary',{},'Research Diagnostics'),
    el('p',{},'Started: '+new Date(d.started_at).toLocaleString()+' · '+Math.round(d.elapsed_seconds)+' / '+d.total_budget_seconds+' seconds'),
    el('p',{},'Phase: '+d.phase+' · '+(d.country||'All selected markets')+' · '+run.status),
    el('p',{},'Completed phases: '+(d.completed_phases||[]).filter(p=>!(d.failures||[]).some(f=>f.phase===p)&&!(p==='evaluation'&&(reviewCounts().pending||reviewCounts().needs_verification))).join(', ')),
    el('p',{},coverageText()),
    el('p',{},'Discovered '+c.discovered+' · accepted '+c.accepted+' · duplicates '+c.duplicates+' · discarded '+c.discarded+' · evaluated '+c.evaluated),
    el('p',{},'Descriptions: full '+descriptions.full+' · partial '+descriptions.partial+' · snippet only '+descriptions.snippet_only),
    el('p',{},'AI invocations '+usage.ai_invocations+' · model seconds '+Math.round(usage.model_seconds||0)+' · web-tool actions '+usage.web_actions),
    usage.reported_tokens?el('p',{},'Provider-reported tokens: '+Object.entries(usage.reported_tokens).map(([k,v])=>k+' '+v).join(' · ')):el('p',{class:'muted'},'Token usage not supplied by provider.'),
    d.stop?el('p',{},'Stopped: '+d.stop.phase+' · '+d.stop.reason+(d.stop.stage?' · '+d.stop.stage:'')):null,
    el('h3',{},'Country coverage'),table(['Market','Indexed passes','Outcome'],Object.entries(d.market_outcomes||{}).map(([id,v])=>[id,v.indexed_passes,v.status])),
    el('h3',{},'Queries performed'),table(['Source','Country','Query','Location'],(d.queries||[]).map(q=>[q.source,q.country,q.query,q.location||'—'])),
    ...(d.failures||[]).map(f=>el('p',{},'Failed: '+f.phase+' / '+f.country+' · '+f.reason+' · '+f.stage)),
    el('h3',{},'LinkedIn direct requests'),(d.linkedin_direct||[]).length?table(['Operation','Country','Requests','HTTP','Outcome'],d.linkedin_direct.map(r=>[r.operation,r.country,r.requests,r.http_status,r.status+(r.cache_hit?' · cached':'')+(r.reason?' · '+r.reason:'')])):el('p',{},'No direct LinkedIn request ran.'),
    el('h3',{},'Employer-site requests'),table(['Endpoint','Parameters','HTTP','Outcome'],(d.employer_requests||[]).map(r=>[r.endpoint,JSON.stringify(r.parameters||{}),r.http_status,r.status])),
    el('h3',{},'AI calls'),table(['Call','Phase / country','Seconds','Outcome / timeout'],(d.ai_calls||[]).map(r=>[r.kind,r.phase+' / '+(r.country||'all'),r.seconds,r.timeout_category||r.status])),
    el('h3',{},'Inference CLI events'),table(['Call','CLI started','Event count','Event types / timing'],(d.ai_calls||[]).map(r=>[r.kind,r.cli_events?.cli_started===undefined?'Not recorded':String(r.cli_events.cli_started),r.cli_events?.event_count,JSON.stringify(r.cli_events||{})])),
    d.linkedin_permission===false?el('p',{class:'muted'},'Direct LinkedIn permission is off. Enable it in My next move to allow guest requests.'):null,
    el('h3',{},'Discarded candidates'),table(['URL','Reason'],(d.discarded_candidates||[]).map(r=>[r.url,r.reason])),
    ...(run.payload.warnings||[]).map(w=>el('p',{class:'muted'},w)));
}
function discover(){
  const incomplete=state.runs[0]?.status!=='completed'&&(reviewCounts().pending||reviewCounts().needs_verification||state.runs[0]?.payload.provider_error);
  let jobs=state.jobs.filter(j=>j.shortlist_status!=='low_relevance' && review(j).status==='assessed' &&
    (tab==='all'||(!j.previously_seen&&recommended(j)))).sort((a,b)=>
    Number(!!a.previously_seen)-Number(!!b.previously_seen)||
    priority(b)-priority(a)||(a.title||'').localeCompare(b.title||''));
  const older=tab==='recommended'?[...state.jobs.filter(j=>j.previously_seen),...(state.previous_opportunities||[])].filter(recommended).sort((a,b)=>priority(b)-priority(a)).slice(0,6):[];
  const lower=tab==='all'?state.jobs.filter(j=>j.shortlist_status==='low_relevance'):[];
  const missing=state.jobs.filter(j=>j.shortlist_status!=='low_relevance'&&['pending','needs_verification'].includes(review(j).status));
  const excluded=state.jobs.filter(j=>j.shortlist_status!=='low_relevance'&&review(j).status==='excluded');

  return el('div',{},el('div',{class:'page-title'},el('h1',{},'Your next career move'),el('p',{},'Fresh research shaped by your CV and career goals.')),
    statusPanel(),button('Search with AI',()=>act('/api/search',{}),'primary',working()||!state.profile),researchDiagnostics(),
    el('p',{class:'inline-note'},'Each new search shows fresh findings while preserving your CV, career goals, learned feedback and application/previous vacancy history.'),
    el('div',{class:'tabs result-tabs',role:'group','aria-label':'Search results'},...[["recommended","Recommended"],["all","All Opportunities"]].map(([id,title])=>button(title,()=>{tab=id;render();},id===tab?'active':''))),
    el('h2',{},tab==='all'?'Assessed opportunities':'Fresh reasoned opportunities'),
    jobs.length?el('div',{class:'job-grid'},jobs.map(card)):el('div',{class:'empty'},el('h3',{},incomplete?'Assessment could not be completed':state.jobs.length?'No strong recommendations established yet':'Ready for a fresh search'),el('p',{},incomplete?'Research is incomplete; suitability has not been established for pending candidates. Previously verified opportunities remain available below.':state.jobs.length?'All discovered vacancies remain under All Opportunities. Weak matches are not promoted to fill this view.':state.cv.text?'Your saved CV and career goals are ready. Search with AI starts a fresh research session.':'Upload your CV and describe your next step in My next move.')),
    lower.length?el('details',{class:'panel'},el('summary',{},'Lower-relevance discoveries ('+lower.length+')'),
      el('p',{class:'muted'},'Observed source listings not selected for career-fit review. No automatic recommendation.'),
      ...lower.map(card)):null,
    older.length?el('section',{class:'panel'},el('h3',{},'Previously found · worth revisiting'),
      el('p',{class:'muted'},'Not new. Availability has not been rechecked.'),
      ...older.map(j=>el('div',{class:'previous-lead'},el('strong',{},j.title),
        el('p',{},fieldLabel(j,'company','Employer unverified')+' · '+fieldLabel(j,'location','Location unverified')),
        el('p',{class:'muted'},compact(j.preliminary?.next_step||'Previously shortlisted',35)),
        safeLink(j.url,'Original posting')))):null,
    missing.length?el('section',{class:'panel'},el('h2',{},'Incomplete assessments ('+missing.length+')'),el('p',{},'These findings remain available; suitability has not been established.'),el('div',{class:'job-grid'},missing.map(card))):null,
    excluded.length?el('details',{class:'panel'},el('summary',{},'Excluded from review ('+excluded.length+')'),el('div',{class:'job-grid'},excluded.map(card))):null);
}
function card(job){
  const historyUnverified=(job.application_status||'none')==='none'&&job.application_history_check?.status!=='recorded';
  const status=el('select',{class:'status-select','aria-label':'Application status for '+job.title,
    onChange:event=>act('/api/application',{job_id:job.id,status:event.target.value})},
    historyUnverified?el('option',{value:'unverified',disabled:true},'Application history unverified'):null,
    ...[['none','Not applied'],['saved','Saved'],['applied','Applied'],['interview','Interview'],
       ['offer','Offer'],['rejected','Rejected'],['dismissed','Dismissed']].map(([id,label])=>
       el('option',{value:id},label)));
  status.value=historyUnverified?'unverified':job.application_status||'none';
  return el('article',{class:'job-card'},el('h3',{},job.title),el('p',{},[fieldLabel(job,'company','Employer unverified'),fieldLabel(job,'location','Location unverified')].join(' · ')),
    el('div',{class:'job-tags'},
      job.previously_seen?tag('Previously seen'):tag('New discovery'),
      job.preliminary?.priority?tag('Priority: '+job.preliminary.priority):null,
      tag(evidenceLabel(job),'amber'),tag(freshnessLabel(job),'amber'),
      job.geography?.status==='inferred'?tag('Country inferred from observed locality','amber'):null),
    el('p',{class:'muted'},'Decision authority: '+(job.preliminary?.authority||'Not verified')+
      ' · Salary (source): '+salaryLabel(job)+
      ' · Hours: '+(job.preliminary?.hours_evidence||job.hours||'Not stated')+
      ' · Hybrid/remote: '+(job.preliminary?.work_arrangement||job.workplace||'Not verified')),
    job.preliminary?.tradeoffs?el('p',{class:'muted'},'Trade-offs: '+job.preliminary.tradeoffs):null,
    (job.country_id==='NL'||job.display_country_id==='NL')&&job.preliminary?.ruling_employer_support?
      el('p',{class:'muted'},'Dutch ruling employer support: '+
        job.preliminary.ruling_employer_support+' · Personal eligibility: not assessed'+
        (job.preliminary.ruling_quote?' · Source: '+job.preliminary.ruling_quote:'')):null,
    sourceAndTriage(job),assessmentSummary(job),
    el('div',{class:'actions'},button('View opportunity',()=>detail(job)),safeLink(job.url,'Original posting'),status));
}
function detail(job){
  const p=job.preliminary;
  $('#job-dialog-content').replaceChildren(el('div',{},el('div',{class:'dialog-head'},el('h2',{},job.title),button('Close',()=>$('#job-dialog').close())),safeLink(job.url,'Original posting'),
    el('p',{},evidenceLabel(job)+' · '+freshnessLabel(job)),assessmentSummary(job),
    p?.critical_gap?tag('Critical specialist gap','amber'):null,
    el('details',{},el('summary',{},'Observed source evidence'),el('p',{class:'prose'},job.description||job.partial_source_text?.text||(job.source_observations||[]).map(o=>o.text).join('\n')||'Description unavailable')),
    job.feedback?.length?tag('Saved feedback: '+job.feedback.at(-1).kind):null,el('div',{class:'actions'},...['like','irrelevant'].map(kind=>button(kind==='like'?'Like':'Not relevant',()=>act('/api/feedback',{job_id:job.id,kind,reasons:[],note:''})))),el('p',{class:'muted'},'Explicit feedback teaches preferences only within the verified country; uncertain geography stays unclassified.')));
  if(!$('#job-dialog').open)$('#job-dialog').showModal();
}
function preferences(){
  const outlookImport=el('input',{type:'file',accept:'.json,application/json',
    'aria-label':'Import read-only Outlook Job Radar evidence',
    onChange:async event=>{
      const f=event.target.files?.[0];if(!f)return;
      if(f.size>2000000)return toast('Use a Job Radar JSON export under 2 MB.',true);
      try{
        const payload=JSON.parse(await f.text());
        const messages=Array.isArray(payload)?payload:payload.messages;
        if(!Array.isArray(messages))throw Error('Expected JSON messages array.');
        const result=await api('/api/outlook-history-import',
                               {folder:'Job Radar',messages});
        await refresh();
        toast('Matched '+result.matched+' applications/rejections; '+
              result.ambiguous+' ambiguous records left unchanged.');
      }catch(err){toast(err.message,true);}
    }});
  const p=state.profile||{},text=el('textarea',{rows:8,'aria-label':'Your career goals',value:careerDraft??p.looking_for??p.objectives??'',onInput:event=>careerDraft=event.target.value,placeholder:'Describe your next career move, countries and locations, working conditions and anything important to you.'});
  const provider=el('select',{'aria-label':'AI subscription'},...['codex','claude'].map(id=>el('option',{value:id},id==='codex'?'Codex subscription':'Claude Code subscription')));provider.value=p.provider||'codex';
  const consent=el('input',{type:'checkbox',checked:!!p.consent}),web=el('input',{type:'checkbox',checked:!!p.secondary}),direct=el('input',{type:'checkbox',checked:!!p.linkedin_consent});
  const upload=el('input',{type:'file',accept:'.pdf,.docx','aria-label':'Upload CV',onChange:async event=>{
    const f=event.target.files[0];if(!f)return;if(f.size>10000000)return toast('Use a CV up to 10 MB.',true);
    try{const r=await fetch('/api/cv',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Radar-CSRF':state.csrf,'X-Filename':'CV'+f.name.slice(f.name.lastIndexOf('.'))},body:await f.arrayBuffer()});const data=await r.json();if(!r.ok)throw Error(data.error.message);await refresh();toast('CV extracted locally. Review its text before AI processing.');}catch(e){toast(e.message,true);}
  }});
  return el('div',{},el('h1',{},'My next move'),statusPanel(),researchDiagnostics(),el('div',{class:'panel'},el('h2',{},'Your experience'),upload,state.cv.filename?el('p',{},state.cv.filename):null,state.cv.text?el('details',{},el('summary',{},'Preview extracted CV'),el('p',{class:'prose'},state.cv.text)):null),
    el('div',{class:'panel'},el('h2',{},'Where you want to go'),text,provider,
    el('p',{},state.providers[provider.value]?.status||'Provider not checked'),el('p',{class:'muted'},'A separately authenticated subscription CLI is required. Desktop login alone does not prove inference works; no API-key fallback.'),
    el('label',{class:'check'},consent,'Allow the selected AI to process my CV and career preferences'),el('label',{class:'check'},web,'Allow anonymous public web research'),
    el('label',{class:'check'},direct,'Allow direct LinkedIn guest requests (stops on access restrictions)'),
    el('p',{class:'muted'},'Optional: import read-only message evidence from Outlook Job Radar. This local app does not automatically access your Outlook account.'),
    outlookImport,
    button('Search with AI',()=>act('/api/career-search',{looking_for:text.value,provider:provider.value,consent:consent.checked,secondary:web.checked,linkedin_consent:direct.checked}),'primary',working()),
    el('p',{class:'muted'},'The original text is authoritative. No understanding-approval screen. Every search starts with empty results.')));
}
function render(){
  $('#main').replaceChildren(view==='preferences'||!state.profile?preferences():discover());
  $('#provider-pill').textContent=state.profile?.provider||'Choose your AI';
  $('.version').textContent=state.version.version+' · PRIVATE WORKSPACE';
  $('#catchup').replaceChildren();
}
async function refresh(){state=await api('/api/state');render();}
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>{view=b.dataset.view;render();});
$('#job-dialog').addEventListener('click',event=>{if(event.target!==event.currentTarget)return;const r=event.currentTarget.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.currentTarget.close();});
refresh();
setInterval(async()=>{if(!state)return;const wasWorking=working();const next=await api('/api/state');if(wasWorking||next.runs[0]?.status==='running'||next.operation?.status==='running'){state=next;render();}},2500);

