'use strict';
// All model responses and installs are mocked; this test never starts inference.
const {JSDOM,VirtualConsole}=require('jsdom'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],posts=[];const pause=ms=>new Promise(r=>setTimeout(r,ms));async function wait(fn){for(let n=0;n<200;n++){if(fn())return;await pause(25);}throw Error('Prompt UI timeout: '+errors.join(';'));}
let info={ready:true,busy:false,id:'',stage:'',result:null,error:'',name:'Local AI prompt enhancer',model:'Test local CPU model',size:1141729977,source:'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF',note:'CPU only',license:'Apache-2.0'},serial=0,delay=25,cancelled=false;
const reply=(value,ok=true)=>({ok,json:async()=>value});
(async()=>{
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.structuredClone=structuredClone;w.ResizeObserver=class{observe(){}disconnect(){}};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};w.HTMLMediaElement.prototype.pause=function(){};w.HTMLMediaElement.prototype.load=function(){};w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:t=>({width:t.length*8})},{get:(o,k)=>o[k]||(()=>{})});
  w.fetch=async(path,options)=>{
   const route=new URL(path,url).pathname,body=options?.body?JSON.parse(options.body):null;if(body)posts.push({route,body});
   if(route==='/api/state'){const state=await (await fetch(new URL(path,url),options)).json();state.busy=true;state.prompt_enhancer=structuredClone(info);return reply(state);}
   if(route==='/api/prompts/enhance'){
    cancelled=false;info={...info,busy:true,id:'prompt-'+(++serial),stage:'Rewriting on CPU…',result:null,error:''};const id=info.id;
    for(let n=0;n<delay;n+=10){await pause(10);if(cancelled){info={...info,busy:false,stage:'Cancelled',error:'Prompt enhancement cancelled.'};return reply({error:info.error},false);}}
    const result={id,original:body.prompt,prompt:'Refined: '+body.prompt,context:body.context,mode:body.mode};info={...info,busy:false,result,stage:'Review draft.'};return reply({ok:true,id,result});
   }
   if(route==='/api/prompts/install'){info={...info,ready:true};return reply({ok:true});}
   if(route==='/api/prompts/cancel'){assert.equal(body.id,info.id);cancelled=true;return reply({ok:true});}
   assert(!route.startsWith('/api/queue'),'Prompt enhancement must not queue media generation');return fetch(new URL(path,url),options);
  };
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id);await wait(()=>w.eval('typeof initialized!=="undefined"&&initialized')&&$('prompt-ai-model-card'));
 assert.equal(d.querySelectorAll('[data-prompt-ai]').length,5);assert.equal(d.querySelector('[data-prompt-ai="iprompt"]').disabled,false,'CPU prompt AI is available during media generation');
 $('iprompt').value='A "green dragon" over a lake';d.querySelector('[data-prompt-ai="iprompt"]').click();await wait(()=>!$('prompt-ai-apply').disabled);assert.equal($('iprompt').value,'A "green dragon" over a lake');assert.equal($('prompt-ai-original').value,$('iprompt').value);assert.equal(posts.find(x=>x.route==='/api/prompts/enhance').body.context,'image');
 $('prompt-ai-result').value='My edited AI draft';$('prompt-ai-result').dispatchEvent(new w.Event('input'));$('prompt-ai-apply').click();assert.equal($('iprompt').value,'My edited AI draft');assert.equal($('prompt-ai-dialog').open,false);
 for(const [id,context] of [['eprompt','edit'],['vprompt','video'],['fprompt','faceswap'],['aprompt','avatar']]){
  $(id).value='Original '+context;d.querySelector('[data-prompt-ai="'+id+'"]').click();await wait(()=>!$('prompt-ai-apply').disabled);assert.equal(posts.filter(x=>x.route==='/api/prompts/enhance').at(-1).body.context,context);$('prompt-ai-dialog').close();
 }
 $('iprompt').value='A new portrait';d.querySelector('[data-prompt-ai="iprompt"]').click();await wait(()=>!$('prompt-ai-apply').disabled);$('iprompt').value='A later manual edit';$('prompt-ai-apply').click();assert.equal($('iprompt').value,'A later manual edit');assert.match($('prompt-ai-stage').textContent,/changed/);$('prompt-ai-dialog').close();
 info={...info,ready:false,result:null,error:''};await w.eval('refreshTools')();$('iprompt').value='Install model test';const before=posts.filter(x=>x.route==='/api/prompts/enhance').length;d.querySelector('[data-prompt-ai="iprompt"]').click();assert.equal($('prompt-ai-install').hidden,false);assert.equal(posts.filter(x=>x.route==='/api/prompts/enhance').length,before);$('prompt-ai-install').click();await wait(()=>!$('prompt-ai-apply').disabled);assert(posts.some(x=>x.route==='/api/prompts/install'));
 $('prompt-ai-mode').value='expand';$('prompt-ai-run').click();await wait(()=>!$('prompt-ai-apply').disabled);assert.equal(posts.filter(x=>x.route==='/api/prompts/enhance').at(-1).body.mode,'expand');$('prompt-ai-dialog').close();
 delay=1500;$('iprompt').value='Cancellation test';d.querySelector('[data-prompt-ai="iprompt"]').click();await w.eval('refreshTools')();await wait(()=>!$('prompt-ai-cancel').hidden);$('prompt-ai-cancel').click();await wait(()=>$('prompt-ai-stage').textContent.includes('cancelled'));assert.equal($('iprompt').value,'Cancellation test');assert.equal($('prompt-ai-apply').disabled,true);
 assert.equal(errors.length,0,errors.join(';'));assert(!posts.some(x=>x.route.startsWith('/api/queue')));const proof={five_prompt_contexts:true,local_cpu_during_media_generation:true,original_preserved_until_apply:true,editable_draft:true,stale_prompt_protected:true,optional_install:true,refine_and_expand:true,cancellation:true,no_media_generation:true,no_actual_ai_inference:true};fs.writeFileSync('outputs/prompt-enhancer-ui-1.15.1.json',JSON.stringify(proof,null,2));dom.window.close();console.log('PROMPT_ENHANCER_UI_PASS '+JSON.stringify(proof));
})().catch(e=>{console.error(e);process.exit(1);});
