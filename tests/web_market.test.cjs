// Pure DOM/handler regressions; these do not claim real-browser or visual coverage.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.handlers={};this.dataset={};this.classList={toggle(){}};this.open=false;}
  append(...items){this.children.push(...items);}
  prepend(...items){this.children.unshift(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(key,value){this.attributes[key]=value;}
  removeAttribute(key){delete this.attributes[key];}
  addEventListener(name,handler){this.handlers[name]=handler;}
  querySelector(){return null;}
  focus(){this.focused=true;}
  showModal(){this.open=true;}
  close(){this.open=false;this.closed=true;}
  getBoundingClientRect(){return {left:100,right:500,top:100,bottom:500};}
  get text(){return (this.textContent||'')+this.children.map(c=>c.text??String(c)).join(' ');}
  set innerHTML(value){throw new Error('Untrusted HTML injection');}
}
function fixture(){
  const surfaces=new Map();
  const document={createElement:t=>new Element(t),createTextNode:t=>({text:t}),querySelector:s=>{if(!surfaces.has(s))surfaces.set(s,new Element(s));return surfaces.get(s);},querySelectorAll:()=>[]};
  const context=vm.createContext({document,Node:Element,window:{addEventListener(){}},location:{hash:''},URL,structuredClone,setTimeout,clearTimeout,console,confirm:()=>false});
  const source=fs.readFileSync('web/app.js','utf8');
  vm.runInContext(source.slice(0,source.lastIndexOf('\nview=')),context);
  const run=code=>vm.runInContext(code,context);
  run(`state={csrf:'synthetic',profile:{markets:defaultDraft().markets,objectives:'Leadership'},market_state:{DE:{learned:[]},NL:{learned:[]}},global_learned:[],learned:[],runs:[],jobs:[],providers:{codex:{status:'Synthetic',installed:false},claude:{status:'Synthetic',installed:false}},cv:{text:'Synthetic CV',filename:'synthetic'},budgets:{},skill_mode:true};`);
  return {run,surfaces,context};
}
function nodes(root){return [root,...(root.children||[]).flatMap(nodes)];}

test('one Like revision retains stale Recommended and regional selection is isolated',()=>{
  const {run}=fixture();
  run(`state.jobs=['DE','NL'].map(id=>({id,location:id,country_id:id,first_seen:'2026-01-01',application_status:'none',feedback:[],events:[],market_ids:[id],market_evaluations:{[id]:{evaluation:{recommend:true,category:'direct',summary:'Synthetic',assessment_version:2},assessment_stale:id==='NL'}}}));`);
  assert.equal(run('visibleJobs().filter(recommended).length'),2);
  assert.equal(run("marketTab='DE';visibleJobs().filter(recommended).length"),1);
  assert.equal(run("visibleJobs()[0].assessment_stale"),false);
  assert.equal(run("marketTab='NL';visibleJobs()[0].assessment_stale"),true);
  assert.match(run('card(visibleJobs()[0])').text,/Reassessment pending/);
});
test('backdrop click closes, inner clicks and dialog padding do not close',()=>{
  const {run,surfaces}=fixture();const dialog=surfaces.get('#job-dialog');
  const handler=dialog.handlers.click;
  dialog.open=true;
  handler({target:new Element('button'),currentTarget:dialog,clientX:0,clientY:0});assert.equal(dialog.open,true);
  handler({target:dialog,currentTarget:dialog,clientX:150,clientY:150});assert.equal(dialog.open,true);
  handler({target:dialog,currentTarget:dialog,clientX:50,clientY:50});assert.equal(dialog.open,false);
});
test('onboarding and Preferences contain no sliders or hidden draft weights',()=>{
  const {run}=fixture();
  const onboarding=run('draft=defaultDraft();wizardStep=2;onboarding()');
  assert.equal(nodes(onboarding).filter(n=>n.attributes?.type==='range').length,0);
  assert.equal(run("'weights' in defaultDraft()"),false);
  const preferences=run('preferences()');
  assert.equal(nodes(preferences).filter(n=>n.attributes?.type==='range').length,0);
  assert.match(preferences.text,/Germany market/);assert.match(preferences.text,/Netherlands market/);
});
test('reopened detail exposes persisted Like independently of Save',()=>{
  const {run,surfaces}=fixture();
  run(`state.jobs=[{id:'NL',country_id:'NL',title:'Synthetic lead',company:'Example',location:'Netherlands',application_status:'none',feedback:[{kind:'like',scope:'NL',reasons:[],note:'Synthetic'}],events:[],market_evaluations:{}}];detail(state.jobs[0]);`);
  const content=surfaces.get('#job-dialog-content');assert.match(content.text,/Saved feedback: like · NL/);
  const like=nodes(content).find(n=>n.tag==='button'&&n.text==='Like');assert.equal(like.attributes['aria-pressed'],'true');
  assert.equal(run('state.jobs[0].application_status'),'none');
  surfaces.get('#job-dialog').close();run('detail(state.jobs[0])');assert.equal(surfaces.get('#job-dialog').open,true);
});
test('Search this country sends selected country to the API; All is explicit',async()=>{
  const {run,context}=fixture();const calls=[];
  context.capture=(path,data)=>calls.push({path,data});run('act=async(path,data)=>capture(path,data)');
  const country=run("marketTab='DE';searchButton()");await country.handlers.click();assert.equal(calls[0].data.market_id,'DE');
  const all=run("marketTab='all';searchButton()");await all.handlers.click();assert.equal(calls[1].data.market_id,'all');
});
test('all reports preserve partial outcomes and distinct market strategies',()=>{
  const {run}=fixture();
  const report=run(`reportPanel({id:1,status:'partial',payload:{requests:2,warnings:['Limited'],markets:{DE:{status:'failed',warnings:['Limited'],job_ids:[],sources:[]},NL:{status:'completed',warnings:[],job_ids:[],sources:[],plan:{strategy:'Independent Dutch strategy',role_families:[],queries:[]}}}}})`);
  assert.match(report.text,/DE market/);assert.match(report.text,/NL market/);assert.match(report.text,/Independent Dutch strategy/);assert.match(report.text,/partial/);
});
test('unknown-country All view keeps regional recommendations without assigning a country',()=>{
  const {run}=fixture();
  run(`state.jobs=[{id:'unknown',application_status:'none',market_evaluations:{unclassified:{evaluation:{recommend:true},assessment_stale:true},DE:{evaluation:{recommend:false},assessment_stale:false},NL:{evaluation:{recommend:true},assessment_stale:true}}}];`);
  assert.equal(run('visibleJobs()[0].assessment_market'),'NL');
  assert.equal(run('visibleJobs()[0].country_id'),undefined);
  assert.equal(run('visibleJobs().filter(recommended).length'),1);
  assert.equal(run('visibleJobs()[0].assessment_stale'),true);
});

test('only country and All tabs remain; ambiguous locations stay labeled in All jobs',()=>{
  const {run}=fixture();
  const tabs=run('marketTabs()');
  assert.deepEqual(nodes(tabs).filter(n=>n.tag==='button').map(n=>n.text),['Germany','Netherlands','All']);
  run(`state.jobs=[{id:'unknown',title:'Synthetic',location:'Ambiguous city',application_status:'none',market_ids:['DE'],market_evaluations:{}}];`);
  assert.equal(run('visibleJobs().length'),1);
  assert.match(run('card(visibleJobs()[0])').text,/Location unverified/);
  assert.equal(run("marketTab='DE';visibleJobs().length"),0);
});

test('verified country chooses only its assessment; other country never fills a missing assessment',()=>{
  const {run}=fixture();
  run(`state.jobs=[{id:'nl',country_id:'NL',evaluation:{summary:'Legacy German summary'},market_evaluations:{DE:{evaluation:{summary:'German summary',recommend:true}},NL:{evaluation:{summary:'Dutch summary'}}}}];`);
  assert.equal(run("marketJob(state.jobs[0],'DE').evaluation.summary"),'Dutch summary');
  assert.equal(run("assessmentSelector(marketJob(state.jobs[0],'all')).tag"),'span');
  assert.match(run("assessmentSelector(marketJob(state.jobs[0],'all')).text"),/Netherlands assessment/);
  run('delete state.jobs[0].market_evaluations.NL');
  assert.equal(run("marketJob(state.jobs[0],'all').evaluation"),undefined);
  assert.equal(run("marketJob(state.jobs[0],'all').assessment_market"),'NL');
});

test('assessment selector appears only for actual multiple assessments of an unverified location',()=>{
  const {run}=fixture();
  run(`state.jobs=[{id:'unknown',market_evaluations:{DE:{evaluation:{recommend:false}},NL:{evaluation:{recommend:true}}}}];`);
  const select=run("assessmentSelector(marketJob(state.jobs[0],'all'))");
  assert.equal(select.tag,'select');assert.equal(select.children.length,2);
  assert.equal(select.value,'NL');
  assert.equal(run("marketJob(state.jobs[0],'DE').assessment_market"),'DE');
  run('delete state.jobs[0].market_evaluations.DE');
  assert.equal(run("assessmentSelector(marketJob(state.jobs[0],'all')).tag"),'span');
});

test('onboarding distinguishes Desktop sign-in from a missing or unauthenticated CLI',()=>{
  const {run}=fixture();
  const missing=run('draft=defaultDraft();providerFields()');
  assert.match(missing.text,/Codex CLI setup needed/);
  assert.match(missing.text,/own ChatGPT account/);
  assert.match(missing.text,/after your approval/);
  const unauthenticated=run('state.providers.codex.installed=true;providerFields()');
  assert.match(unauthenticated.text,/Complete your Codex CLI sign-in/);
  const ready=run('state.providers.codex.authenticated=true;providerFields()');
  assert.doesNotMatch(ready.text,/Codex CLI setup needed|Complete your Codex CLI sign-in/);
});
