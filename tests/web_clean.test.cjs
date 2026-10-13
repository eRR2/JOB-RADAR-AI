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
test('strong preliminary is recommended and ranked ahead of newer weak specialist',()=>{
  const {run}=fixture();run(`state.jobs=[{id:'weak',title:'Architecture Lead',url:'https://example.org/weak',first_seen:'2026-12-01',preliminary:{priority:'unsuitable',recommend:false,critical_gap:true,next_step:'Specialist optics capability missing'}},{id:'strong',title:'Architecture Lead',url:'https://example.org/strong',first_seen:'2020-01-01',preliminary:{priority:'strong',recommend:true,critical_gap:false,next_step:'Direct system ownership capability',gaps:['Full responsibilities unknown']},source_observations:[{text:'Own system architecture'}]}];`);
  const page=run('discover()');assert.match(page.text,/Direct system ownership capability/);assert.doesNotMatch(page.text,/Specialist optics capability missing/);
  assert.match(page.text,/Preliminary.*search snippet only/);assert.match(page.text,/Güncellik doğrulanmadı/);
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
