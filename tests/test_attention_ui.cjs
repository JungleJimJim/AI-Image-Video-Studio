'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
function fn(name){const start=source.indexOf('function '+name+'('),end=source.indexOf('\n}',start)+2;assert(start>=0&&end>start);return (name==='saveAttentionMode'?'async ':'')+source.slice(start,end);}
const controls={'attention-mode':{value:'pytorch',disabled:false},'attention-status':{textContent:''}};
const context={$:id=>controls[id],document:{activeElement:null},state:{settings:{attention:'pytorch'},attention:{preference:'sage',engine_running:true,active:'pytorch_fallback',reason:'Unsupported input',check:{checked_at:1,available:true}}},notify:()=>{},action:async()=>{}};
vm.createContext(context);vm.runInContext(fn('renderAttention'),context);vm.runInContext(fn('saveAttentionMode'),context);
(async()=>{
 context.renderAttention();assert.equal(controls['attention-mode'].value,'sage');assert(controls['attention-status'].textContent.includes('PyTorch fallback'));assert(controls['attention-status'].textContent.includes('Unsupported input'));
 context.state.attention.engine_running=false;context.renderAttention();assert(controls['attention-status'].textContent.includes('No generation engine'));
 let saved;context.action=async(path,body)=>{saved={path,body};};controls['attention-mode'].value='sage';await context.saveAttentionMode();assert.equal(saved.path,'/api/settings');assert.equal(saved.body.attention,'sage');assert.equal(context.state.settings.attention,'sage');
 context.action=async()=>{throw Error('rejected');};controls['attention-mode'].value='pytorch';await context.saveAttentionMode();assert.equal(controls['attention-mode'].value,'sage');assert.equal(controls['attention-mode'].disabled,false);
 console.log('ATTENTION_UI_PASS: requested and running backend, fallback reason, saved preference and rejected-save rollback.');
})().catch(error=>{console.error(error);process.exitCode=1;});
