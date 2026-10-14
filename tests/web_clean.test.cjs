// Offline DOM behavior; not a visual browser claim.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.handlers={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attributes[k]=v;}
  addEventListener(k,f){this.handlers[k]=f;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  get text(){return (this.textContent||'')+this.children.map(c=>c.text??String(c)).join(' ');}
}
function fixture(){
  const surfaces=new Map();
  const document={createElement:t=>new Element(t),createTextNode:t=>({text:t}),querySelector:s=>{if(!surfaces.has(s))surfaces.set(s,new Element(s));return surfaces.get(s);},querySelectorAll:()=>[]};
  const ctx=vm.createContext({document,Node:Element,URL,setTimeout(){},setInterval(){}});
  const source=fs.readFileSync('web/app.js','utf8');vm.runInContext(source.slice(0,source.indexOf('\nrefresh();')),ctx);
  const run=code=>vm.runInContext(code,ctx);
  run(`state={profile:{provider:'codex',looking_for:'Original exact career request'},cv:{text:'Synthetic CV'},jobs:[],runs:[],providers:{codex:{status:'Subscription login detected'}},version:{version:'5.3.0-preview'}};`);
  return {run,surfaces};
}
function nodes(root){return [root,...(root.children||[]).flatMap(nodes)];}
test('exactly two results tabs; no historical feature controls',()=>{
  const {run}=fixture();const page=run('discover()');
  const tabs=nodes(page).find(n=>n.className==='tabs result-tabs');
  assert.deepEqual(nodes(tabs).filter(n=>n.tag==='button').map(n=>n.text),['Recommended','All Opportunities']);
  assert.doesNotMatch(page.text,/Promising|Obsolete|Applied|slider|ATS score/);
  const html=fs.readFileSync('web/index.html','utf8');assert.doesNotMatch(html,/data-view="applications"|data-view="reports"/);
});
test('verified strong fit is recommended and ranked ahead of newer weak specialist',()=>{
  const {run}=fixture();run(`state.jobs=[{id:'weak',title:'Architecture Lead',url:'https://example.org/weak',first_seen:'2026-12-01',preliminary:{priority:'unsuitable',recommend:false,critical_gap:true,next_step:'Specialist optics capability missing'}},{id:'strong',title:'Architecture Lead',url:'https://example.org/strong',first_seen:'2020-01-01',preliminary:{priority:'strong',recommend:true,critical_gap:false,next_step:'Direct system ownership capability',gaps:['Full responsibilities unknown']},source_observations:[{text:'Own system architecture'}]}];`);
  assert.equal(run('recommended(state.jobs[1])'),false);
  run(`state.jobs[1].description='Actual publisher architecture responsibilities. '.repeat(5);state.jobs[1].description_source={kind:'public_verified'};`);
  const page=run('discover()');assert.match(page.text,/Direct system ownership capability/);assert.doesNotMatch(page.text,/Specialist optics capability missing/);
  assert.match(page.text,/Full source description verified/);assert.match(page.text,/Güncellik doğrulanmadı/);
  run(`tab='all';`);assert.match(run('discover().text'),/Specialist optics capability missing/);
});
test('publisher closure excludes recommendation; full versus partial labels are honest',()=>{
  const {run}=fixture();run(`const j={preliminary:{recommend:true},freshness:{status:'confirmed_closed'},description:'Actual text',description_source:{kind:'public_verified'}};`);
  assert.equal(run('recommended(j)'),false);assert.match(run('evidenceLabel(j)'),/Full source description verified/);
  run(`j.description='';j.partial_source_text={text:'Actual partial text'};`);
  assert.match(run('evidenceLabel(j)'),/Partial.*full description unverified/);
});
test('original career request and unsaved edits survive a render',()=>{
  const {run}=fixture();let page=run('preferences()');const text=nodes(page).find(n=>n.tag==='textarea');
  assert.equal(text.value,'Original exact career request');text.handlers.input({target:{value:'My unmodified new goals'}});
  page=run('preferences()');assert.equal(nodes(page).find(n=>n.tag==='textarea').value,'My unmodified new goals');
  assert.equal(nodes(page).filter(n=>n.tag==='textarea').length,1);
  assert.doesNotMatch(page.text,/Confirm interpretation|Accept summary|Country code|Global scope/);
});
test('failed provider shows actionable message without successful fake jobs',()=>{
  const {run}=fixture();run(`state.runs=[{status:'failed',payload:{provider_error:{category:'time_window',message:'Provider time limit reached'}}}];`);
  assert.match(run('discover().text'),/Provider time limit reached/);
  assert.match(run('discover().text'),/No automatic retry/);
  assert.equal(run('state.jobs.length'),0);
});
test('intent provenance failure shows its reason without unrelated login advice',()=>{
  const {run}=fixture();run(`state.operation={status:'failed',category:'clarification_or_validation',message:'Germany (DE): preferred_location_not_supported'};`);
  const page=run('statusPanel().text');assert.match(page,/preferred_location_not_supported/);
  assert.doesNotMatch(page,/login|subscription|usage limits/);
});
test('diagnostics exposes real call and source outcomes, stays collapsible across refresh',()=>{
  const {run}=fixture();run(`state.runs=[{status:'partial',payload:{usage:{ai_invocations:4,model_seconds:12,web_actions:2},diagnostics:{started_at:'2026-10-13',elapsed_seconds:12,total_budget_seconds:900,phase:'evaluation',country:'Germany',completed_phases:['strategy','discovery','enrichment'],counts:{discovered:3,accepted:2,duplicates:1,discarded:0,evaluated:0},descriptions:{full:0,partial:0,snippet_only:2},linkedin_direct:[{operation:'search',country:'Germany',requests:1,http_status:429,status:'restricted'}],ai_calls:[{kind:'priority_v52',phase:'evaluation',country:'Germany',seconds:4,timeout_category:'provider_call_timeout'}],stop:{phase:'evaluation',reason:'time_window'}}}}];`);
  let panel=run('researchDiagnostics()');assert.equal(panel.tag,'details');assert.equal(panel.attributes.open,undefined);
  assert.match(panel.text,/Research Diagnostics|LinkedIn direct/);assert.match(panel.text,/429/);assert.match(panel.text,/provider_call_timeout/);assert.match(panel.text,/Token usage not supplied/);
  panel.handlers.toggle({target:{open:true}});panel=run('researchDiagnostics()');assert.equal(panel.attributes.open,'');
  run(`state.runs[0].payload.usage.reported_tokens={input_tokens:123};`);assert.match(run('researchDiagnostics().text'),/input_tokens 123/);
});
test('direct LinkedIn permission is explicit, defaults off and is submitted by the search button',()=>{
  const {run}=fixture();run(`let sent;act=(path,data)=>{sent=data};`);
  const page=run('preferences()'),label=nodes(page).find(n=>n.tag==='label'&&n.text.includes('Allow direct LinkedIn'));
  assert.ok(label);const input=nodes(label).find(n=>n.tag==='input');assert.equal(input.checked,false);
  input.checked=true;nodes(page).find(n=>n.tag==='button'&&n.text==='Search with AI').handlers.click();
  assert.equal(run('sent.linkedin_consent'),true);
});

test('weekly report separates rediscoveries and displays source terms and priority',()=>{
  const {run}=fixture();run(`state.jobs=[
    {id:'fresh',title:'Fresh role',url:'https://example.org/fresh',preliminary:{recommend:true,priority:'strong',critical_gap:false,next_step:'Own systems',salary_evidence:'EUR 100,000',hours_evidence:'35 hours per week',work_arrangement:'Hybrid: two days onsite',tradeoffs:'Relocation required',authority:'Technical architecture decisions',ruling_employer_support:'unknown'}},
    {id:'seen',title:'Seen role',url:'https://example.org/seen',previously_seen:true,preliminary:{recommend:true,priority:'strong',critical_gap:false,next_step:'Prior credible opportunity'}}];`);
  run(`state.jobs.forEach(j=>{j.description='Actual publisher architecture responsibilities. '.repeat(5);j.description_source={kind:'public_verified'};});`);
  const page=run('discover()');
  const cards=nodes(page).filter(n=>n.tag==='article'&&n.className==='job-card');
  assert.equal(cards.length,1);assert.match(cards[0].text,/Fresh role/);
  assert.match(page.text,/Previously found/);assert.match(page.text,/Seen role/);
  assert.match(cards[0].text,/EUR 100,000/);assert.match(cards[0].text,/35 hours per week/);
  assert.match(cards[0].text,/Hybrid: two days onsite/);assert.match(cards[0].text,/Priority: strong/);
});

test('invalidated evidence cannot keep a recommendation visible',()=>{
  const {run}=fixture();run(`const invalid={preliminary:{recommend:true,priority:'strong'},evaluation_status:'needs_verification'};`);
  assert.equal(run('recommended(invalid)'),false);
});

test('partial report retains 24 candidates with 8 assessed, 12 pending and 4 closed exclusions',()=>{
  const {run}=fixture();run(`state.runs=[{status:'partial',payload:{diagnostics:{completed_phases:['discovery','enrichment','evaluation'],failures:[{phase:'evaluation',country:'Netherlands',reason:'time_window'}]}}}];
    state.review_coverage={selected:24,assessed:8,pending:12,excluded:4,needs_verification:0};
    state.jobs=[...Array.from({length:8},(_,i)=>({id:'a'+i,title:'Assessed '+i,url:'https://example.org/a'+i,previously_seen:i<2,review_state:{status:'assessed',reason:'source_based_assessment'},preliminary:{recommend:true,priority:'strong',next_step:'Supported system ownership'}})),
    ...Array.from({length:12},(_,i)=>({id:'p'+i,title:'Pending '+i,url:'https://example.org/p'+i,review_state:{status:'pending',reason:i<5?'evaluation_timeout':'evaluation_budget'}})),
    ...Array.from({length:4},(_,i)=>({id:'c'+i,title:'Closed '+i,url:'https://example.org/c'+i,availability:'closed_banner_observed',review_state:{status:'excluded',reason:'confirmed_closed'}}))];`);
  run(`state.jobs.filter(j=>j.preliminary).forEach(j=>{j.description='Actual publisher architecture responsibilities. '.repeat(5);j.description_source={kind:'public_verified'};});`);
  const page=run('discover()');
  assert.match(page.text,/Research incomplete/);assert.match(page.text,/8 assessed/);assert.match(page.text,/12 pending/);assert.match(page.text,/4 excluded/);
  assert.match(page.text,/Fresh.*opportunities/);assert.match(page.text,/Previously found/);assert.match(page.text,/Incomplete assessments/);
  assert.match(page.text,/evaluation time limit|Evaluation time limit/);assert.match(page.text,/evaluation budget|Evaluation budget/);
  run(`tab='all';`);const all=run('discover()');
  for(let i=0;i<12;i++)assert.match(all.text,new RegExp('Pending '+i+'(?: |$)'));
  for(let i=0;i<4;i++)assert.match(all.text,new RegExp('Closed '+i+'(?: |$)'));
  const diagnostics=run('researchDiagnostics().text');
  assert.doesNotMatch(diagnostics,/Completed phases: discovery, enrichment, evaluation/);
});

test('ruling is restricted to Dutch roles and unknown application history is explicit',()=>{
  const {run}=fixture();run(`const j={id:'x',title:'Role',country_id:'DE',url:'https://example.org/x',application_status:'none',application_history_check:{status:'unverified'},preliminary:{next_step:'Known capability',ruling_employer_support:'unknown',ruling_quote:''}};`);
  let page=run('card(j)');assert.doesNotMatch(page.text,/Dutch ruling/);
  const select=nodes(page).find(n=>n.tag==='select');assert.equal(select.value,'unverified');
  assert.match(page.text,/Application history.*unverified/);
  run(`j.country_id='NL';`);assert.match(run('card(j).text'),/Dutch ruling/);
  run(`j.country_id=null;j.display_country_id='NL';`);assert.match(run('card(j).text'),/Dutch ruling/);
  run(`j.application_history_check={status:'recorded'};`);assert.equal(nodes(run('card(j)')).find(n=>n.tag==='select').value,'none');
});

test('title hints populate displayed company city and salary with unverified ceiling provenance',()=>{
  const {run}=fixture();run(`const j={id:'hint',title:'Observed header',url:'https://example.org/hint',inferred_fields:{company:{value:'Example Employer',kind:'source_title',verified:false},location:{value:'Example City',kind:'source_title',verified:false},salary:{value:'Up to 123,000 EUR',kind:'source_title',verified:false,interpretation:'advertised_upper_bound'}}};`);
  const page=run('card(j)');assert.match(page.text,/Example Employer/);assert.match(page.text,/Example City/);
  assert.match(page.text,/Up to 123,000 EUR/);assert.match(page.text,/title.*unverified/);
  assert.match(page.text,/upper bound.*not guaranteed/);
});

test('snippet commentary separates compact known fit and missing information',()=>{
  const {run}=fixture();run(`const j={id:'compact',title:'Observed role',url:'https://example.org/compact',source_observations:[{text:'Actual snippet'}],preliminary:{next_step:Array(160).fill('Repeated').join(' '),evidence:[{assessment:'Demonstrated system ownership'}],gaps:['Full responsibility and specialist requirements missing'],recommend:true,priority:'strong'}};`);
  const page=run('card(j)');assert.match(page.text,/Known fit: Demonstrated system ownership/);
  assert.match(page.text,/Missing for full assessment: Full responsibility/);
  assert.ok((page.text.match(/Repeated/g)||[]).length<=45);
});

