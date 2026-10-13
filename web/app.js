const $=s=>document.querySelector(s);
let state,tab='recommended',view='discover',careerDraft;
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
function recommended(job){return !!job.preliminary?.recommend&&!job.preliminary?.critical_gap&&job.availability!=='closed_banner_observed'&&job.freshness?.status!=='confirmed_closed';}
function evidenceLabel(job){
  if(job.description_source?.kind==='public_verified'&&job.description)return 'Full source description verified';
  if(job.partial_source_text)return 'Partial source text verified · full description unverified';
  if(job.source_observations?.length)return 'Preliminary · search snippet only';
  return 'Description unavailable';
}
function freshnessLabel(job){return job.freshness?.status==='confirmed_open'?'Publisher-confirmed open':job.availability==='closed_banner_observed'||job.freshness?.status==='confirmed_closed'?'Publisher-confirmed closed':'Güncellik doğrulanmadı';}
function toast(text,error=false){$('#toast').textContent=text;$('#toast').className=error?'error':'';$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,6000);}
async function api(path,data){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-Radar-CSRF':state.csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();if(!response.ok)throw Error(result.error?.message||'Operation failed.');return result;
}
async function act(path,data){try{await api(path,data);await refresh();}catch(e){toast(e.message,true);}}
function working(){return state.runs.some(r=>r.status==='running')||state.operation?.status==='running';}
function safeLink(url,text){try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password)return el('a',{href:u.href,target:'_blank',rel:'noopener noreferrer'},text);}catch{}return el('span',{},'Source link unavailable');}
function statusPanel(){
  const run=state.runs[0],operation=state.operation;
  if(working())return el('div',{class:'status-box',role:'status'},el('strong',{},operation?.status==='running'?'Interpreting your career request':run?.stage),el('p',{},'Findings appear as they are saved.'),button('Cancel',()=>act('/api/cancel',{})));
  const problem=operation?.status==='failed'?operation:run?.payload.provider_error;
  if(problem)return el('div',{class:'status-box error',role:'alert'},el('strong',{},'AI research could not finish'),el('p',{},problem.message),el('p',{},'Current findings are retained. No automatic retry. Check your provider login, access or usage limits before another search.'));
  return null;
}
function discover(){
  let jobs=state.jobs.filter(j=>tab==='all'||recommended(j)).sort((a,b)=>priority(b)-priority(a)||(a.title||'').localeCompare(b.title||''));
  return el('div',{},el('div',{class:'page-title'},el('h1',{},'Your next career move'),el('p',{},'Fresh research shaped by your CV and career goals.')),
    statusPanel(),button('Search with AI',()=>act('/api/search',{}),'primary',working()||!state.profile),
    el('p',{class:'inline-note'},'Each new search clears previous results and research history. Your CV, original career text, preferences and learned feedback stay.'),
    el('div',{class:'tabs result-tabs',role:'group','aria-label':'Search results'},...[["recommended","Recommended"],["all","All Opportunities"]].map(([id,title])=>button(title,()=>{tab=id;render();},id===tab?'active':''))),
    jobs.length?el('div',{class:'job-grid'},jobs.map(card)):el('div',{class:'empty'},el('h3',{},state.jobs.length?'No strong recommendations established yet':'Ready for a fresh search'),el('p',{},state.jobs.length?'All discovered vacancies remain under All Opportunities. Weak matches are not promoted to fill this view.':state.cv.text?'Your saved CV and career goals are ready. Search with AI starts a fresh research session.':'Upload your CV and describe your next step in My next move.')));
}
function card(job){
  return el('article',{class:'job-card'},el('h3',{},job.title),el('p',{},[job.company||'Employer unverified',job.location||'Location unverified'].join(' · ')),
    el('div',{class:'job-tags'},tag(evidenceLabel(job),'amber'),tag(freshnessLabel(job),'amber'),job.geography?.status==='inferred'?tag('Country inferred from observed locality','amber'):null),
    el('p',{class:'job-summary'},job.preliminary?.next_step||'Suitability not assessed yet.'),job.preliminary?.gaps?.length?el('p',{class:'muted'},'Important gap / uncertainty: '+job.preliminary.gaps[0]):null,
    el('div',{class:'actions'},button('View opportunity',()=>detail(job)),safeLink(job.url,'Original posting')));
}
function detail(job){
  const p=job.preliminary;
  $('#job-dialog-content').replaceChildren(el('div',{},el('div',{class:'dialog-head'},el('h2',{},job.title),button('Close',()=>$('#job-dialog').close())),safeLink(job.url,'Original posting'),
    el('p',{},evidenceLabel(job)+' · '+freshnessLabel(job)),el('p',{class:'prose'},p?.next_step||'Career suitability not assessed.'),
    p?.critical_gap?tag('Critical specialist gap','amber'):null,el('ul',{},(p?.gaps||[]).map(g=>el('li',{},g))),
    el('details',{},el('summary',{},'Observed source evidence'),el('p',{class:'prose'},job.description||job.partial_source_text?.text||(job.source_observations||[]).map(o=>o.text).join('\n')||'Description unavailable')),
    job.feedback?.length?tag('Saved feedback: '+job.feedback.at(-1).kind):null,el('div',{class:'actions'},...['like','irrelevant'].map(kind=>button(kind==='like'?'Like':'Not relevant',()=>act('/api/feedback',{job_id:job.id,kind,reasons:[],note:''})))),el('p',{class:'muted'},'Explicit feedback teaches preferences only within the verified country; uncertain geography stays unclassified.')));
  if(!$('#job-dialog').open)$('#job-dialog').showModal();
}
function preferences(){
  const p=state.profile||{},text=el('textarea',{rows:8,'aria-label':'Your career goals',value:careerDraft??p.looking_for??p.objectives??'',onInput:event=>careerDraft=event.target.value,placeholder:'Describe your next career move, countries and locations, working conditions and anything important to you.'});
  const provider=el('select',{'aria-label':'AI subscription'},...['codex','claude'].map(id=>el('option',{value:id},id==='codex'?'Codex subscription':'Claude Code subscription')));provider.value=p.provider||'codex';
  const consent=el('input',{type:'checkbox',checked:!!p.consent}),web=el('input',{type:'checkbox',checked:!!p.secondary});
  const upload=el('input',{type:'file',accept:'.pdf,.docx','aria-label':'Upload CV',onChange:async event=>{
    const f=event.target.files[0];if(!f)return;if(f.size>10000000)return toast('Use a CV up to 10 MB.',true);
    try{const r=await fetch('/api/cv',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Radar-CSRF':state.csrf,'X-Filename':'CV'+f.name.slice(f.name.lastIndexOf('.'))},body:await f.arrayBuffer()});const data=await r.json();if(!r.ok)throw Error(data.error.message);await refresh();toast('CV extracted locally. Review its text before AI processing.');}catch(e){toast(e.message,true);}
  }});
  return el('div',{},el('h1',{},'My next move'),statusPanel(),el('div',{class:'panel'},el('h2',{},'Your experience'),upload,state.cv.filename?el('p',{},state.cv.filename):null,state.cv.text?el('details',{},el('summary',{},'Preview extracted CV'),el('p',{class:'prose'},state.cv.text)):null),
    el('div',{class:'panel'},el('h2',{},'Where you want to go'),text,provider,
    el('p',{},state.providers[provider.value]?.status||'Provider not checked'),el('p',{class:'muted'},'A separately authenticated subscription CLI is required. Desktop login alone does not prove inference works; no API-key fallback.'),
    el('label',{class:'check'},consent,'Allow the selected AI to process my CV and career preferences'),el('label',{class:'check'},web,'Allow anonymous public web research'),
    button('Search with AI',()=>act('/api/career-search',{looking_for:text.value,provider:provider.value,consent:consent.checked,secondary:web.checked,linkedin_consent:!!p.linkedin_consent}),'primary',working()),
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
