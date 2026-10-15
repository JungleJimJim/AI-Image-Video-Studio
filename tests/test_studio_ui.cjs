'use strict';
// Exercise actual UI helpers with fake controls; never contact an engine.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const main=fs.readFileSync('assets/studio.js','utf8'),tools=fs.readFileSync('assets/studio-tools.js','utf8');
function fn(source,name){const match=source.match(new RegExp('^(?:async )?function '+name+'\\(','m'));assert(match,name);const start=match.index,end=source.indexOf('\n',start),line=source.slice(start,end).trimEnd();return line.endsWith('{')?source.slice(start,source.indexOf('\n}',end)+2):line;}
const controls={};for(const p of ['i','e','v','ui-']){controls[p+'seed']={value:'123'};controls[p+'randomize_seed']={checked:true};}
const context={crypto:webcrypto,Uint32Array,$:id=>controls[id],editingQueue:null,
 esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
 pack:id=>({name:{flux3:'FLUX 3 Image Klein',qwen21:'Qwen 2.1 Detail Enhancer'}[id]||id}),
 notify:()=>{},refreshTools:async()=>{},exitQueueEdit:()=>{context.editingQueue=null;},action:async()=>({})};
vm.createContext(context);
for(const name of ['randomSeed','advanceSeed','initializeSeeds','mediaDetailsHTML','sourceHistoryHTML'])vm.runInContext(fn(main,name),context);
vm.runInContext(fn(tools,'submitQueue'),context);
(async()=>{
 const samples=new Set();for(let i=0;i<200;i++){const seed=context.randomSeed('123');assert(Number.isSafeInteger(Number(seed)));assert(Number(seed)>=0);assert.notEqual(seed,'123');samples.add(seed);}assert.equal(samples.size,200);
 let submitted;context.action=async(path,body)=>{submitted=structuredClone(body);};
 await context.submitQueue('image',{seed:'123'},5);assert.equal(submitted.options.seed,'123');assert.notEqual(controls.iseed.value,'123');
 controls.iseed.value='456';controls.irandomize_seed.checked=false;await context.submitQueue('image',{seed:'456'},5);assert.equal(controls.iseed.value,'456');
 controls.irandomize_seed.checked=true;context.action=async()=>{throw Error('rejected');};await assert.rejects(()=>context.submitQueue('image',{seed:'456'},5));assert.equal(controls.iseed.value,'456');
 context.action=async()=>{controls.iseed.value='User typed a new draft';};await context.submitQueue('image',{seed:'456'},5);assert.equal(controls.iseed.value,'User typed a new draft');
 context.action=async()=>{};controls.iseed.value='789';context.editingQueue={kind:'image',id:'job'};await context.submitQueue('image',{seed:'789'},5);assert.equal(controls.iseed.value,'789');
 controls.iseed.value='123';controls['ui-seed'].value='333';await context.submitQueue('image',{seed:'123',upscale:{enabled:true,options:{seed:'333'}}},5);assert.notEqual(controls.iseed.value,'123');assert.notEqual(controls['ui-seed'].value,'333');
 controls.vseed.value='11';controls.vrandomize_seed.checked=false;context.initializeSeeds();assert.equal(controls.vseed.value,'11');
 const original={id:'a',kind:'image',name:'Original',width:512,height:512,options:{model:'flux3',seed:0,prompt:'<script>alert(1)</script>',steps:16,upscale:{enabled:true}}};
 const enhanced={id:'b',kind:'enhanced',parent_id:'a',name:'Enhanced',width:1024,height:1024,options:{model:'qwen21',seed:999,detail_strength:1.7,scale:2}};
 const html=context.mediaDetailsHTML(enhanced,[original]);assert(html.includes('Qwen 2.1 Detail Enhancer'));assert(html.includes('<dt>Seed</dt><dd>999</dd>'));assert(html.includes('<dt>Enhanced</dt><dd>Yes</dd>'));assert(html.includes('<dt>Upscaled / enlarged</dt><dd>Yes</dd>'));assert(html.includes('1.7'));
 const history=context.sourceHistoryHTML([original]);assert(history.includes('FLUX 3 Image Klein'));assert(history.includes('seed 0'));assert(history.includes('&lt;script&gt;'));assert(!history.includes('<script>'));
 const originalHTML=context.mediaDetailsHTML(original,[]);assert(originalHTML.includes('No recorded enhancement'));assert(originalHTML.includes('<dt>Seed</dt><dd>0</dd>'));
 const imported=context.mediaDetailsHTML({kind:'imported',options:{}},[]);assert(imported.includes('Not recorded'));assert(!imported.includes('seed 0'));
 console.log('STUDIO_UI_PASS: random/fixed seeds, failed submission, draft preservation, queue editing, enhancement seeds, metadata and source history.');
})().catch(error=>{console.error(error);process.exitCode=1;});
