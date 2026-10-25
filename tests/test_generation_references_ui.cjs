'use strict';
const {JSDOM,VirtualConsole}=require('jsdom'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],posts=[],vc=new VirtualConsole();vc.on('jsdomError',error=>errors.push(error.message));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));async function wait(test){for(let i=0;i<150;i++){if(test())return;await pause(50);}throw Error('Reference UI timed out: '+errors.join(';'));}
(async()=>{
 const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=(path,options)=>{if(options?.body)posts.push({path,body:JSON.parse(options.body)});return fetch(new URL(path,url),options);};w.structuredClone=structuredClone;
  w.ResizeObserver=class{observe(){} disconnect(){}};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({},{get:()=>()=>{}});
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id),change=(id,value)=>{$(id).value=value;$(id).dispatchEvent(new w.Event('change',{bubbles:true}));};
 await wait(()=>d.readyState==='complete'&&$('i-generation-references')&&w.eval('initialized'));
 change('imodel','zimage');assert($('i-generation-references').hidden);
 change('imodel','moss_sft');assert($('i-generation-references').hidden);change('emodel','moss_sft');assert($('reference-panel').hidden);
 change('emodel','fluxklein');assert(!$('reference-panel').hidden);
 change('imodel','fluxklein');assert(!$('i-generation-references').hidden);assert($('i-reference-count').textContent.includes('/ 3'));
 function item(id){return {id:id.repeat(24),name:id+'.png',width:512,height:512,media_type:'image'};}
 w.eval('sendImage')(item('a'),'generation-reference:i');w.eval('sendImage')(item('b'),'generation-reference:i');w.eval('sendImage')(item('c'),'generation-reference:i');
 assert($('i-reference-library').disabled);assert($('i-reference-local').disabled);w.eval('updateImageImportButtons()');assert($('i-reference-local').disabled);
 w.eval('sendImage')(item('a'),'generation-reference:i');assert.equal(w.eval("generationOptions('i').image_references.length"),3);
 $('iprompt').value='Create a new robot scene using image 1 and image 2';$('image-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 await wait(()=>posts.some(p=>p.path==='/api/queue/add'&&p.body.kind==='image'));
 const first=posts.find(p=>p.path==='/api/queue/add'&&p.body.kind==='image');assert.deepEqual(first.body.options.image_references,['a'.repeat(24),'b'.repeat(24),'c'.repeat(24)]);
 change('imodel','flux3');assert($('i-reference-count').textContent.includes('/ 10'));assert.equal(w.eval("generationOptions('i').image_references.length"),0);
 change('imodel','fluxklein');assert.equal(w.eval("generationOptions('i').image_references.length"),3);
 d.querySelector('[data-generation-remove="i:1"]').click();assert.equal(w.eval("generationOptions('i').image_references.length"),2);assert(!$('i-reference-local').disabled);
 $('i-reference-clear').click();assert.equal(w.eval("generationOptions('i').image_references.length"),0);
 // Local-file controls use the existing safe import request and retain the target.
 const click=w.HTMLInputElement.prototype.click;
 w.HTMLInputElement.prototype.click=function(){if(this.type==='file'){Object.defineProperty(this,'files',{configurable:true,value:[new w.File(['fixture'],'Reference.png',{type:'image/png'})]});this.dispatchEvent(new w.Event('change',{bubbles:true}));}else click.call(this);};
 $('i-reference-local').click();await wait(()=>w.eval("generationOptions('i').image_references.length")===1);
 assert(posts.some(p=>p.path==='/api/images/import-source'));assert.equal(w.eval("generationOptions('i').image_references[0]"),'d'.repeat(24));
 // fill is shared by saved settings, result reuse and queue editing.
 w.eval('fill')('i',{model:'viggle',image_references:['a'.repeat(24)]});assert.equal(w.eval("generationOptions('i').image_references[0]"),'a'.repeat(24));
 change('imodel','zimage');assert($('i-generation-references').hidden);assert.equal(w.eval("generationOptions('i').image_references.length"),0);
 change('vmodel','wan22');assert($('v-generation-references').hidden);
 change('vmodel','ref2va');assert(!$('v-generation-references').hidden);assert($('vsource').previousElementSibling.textContent.includes('Reference image 1'));
 w.eval('sendImage')(item('a'),'video');w.eval('sendImage')(item('b'),'generation-reference:v');
 assert($('v-reference-images').textContent.includes('<Picture 2>'));$('vprompt').value='The robot from <Picture 1> waves beside the toy from <Picture 2>';
 $('video-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await wait(()=>posts.some(p=>p.path==='/api/queue/add'&&p.body.kind==='video'));
 const video=posts.find(p=>p.path==='/api/queue/add'&&p.body.kind==='video').body.options;assert.equal(video.source_image,'a'.repeat(24));assert.deepEqual(video.video_references,['b'.repeat(24)]);
 change('vmodel','ltx2');assert($('v-generation-references').hidden);assert.equal(w.eval("generationOptions('v').video_references.length"),0);
 assert.equal(errors.length,0,errors.join(';'));
 const proof={conditional_image_controls:true,conditional_video_controls:true,model_limits:true,library_and_local_import:true,removal_clear_and_restore:true,per_model_selections:true,queue_reference_payloads:true,editor_capability_visibility:true,generation_started:false};
 fs.writeFileSync('outputs/references-ui-1.14.0.json',JSON.stringify(proof,null,2));dom.window.close();console.log('REFERENCE_UI_PASS '+JSON.stringify(proof));
})().catch(error=>{console.error(error);process.exit(1);});
