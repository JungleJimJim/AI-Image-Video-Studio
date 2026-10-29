'use strict';
const {JSDOM,VirtualConsole}=require('jsdom'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],posts=[];const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn){for(let n=0;n<200;n++){if(fn())return;await pause(25);}throw Error('Filmstrip drag timeout: '+errors.join(';'));}
(async()=>{
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.structuredClone=structuredClone;w.ResizeObserver=class{observe(){}disconnect(){}};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  w.HTMLMediaElement.prototype.pause=function(){};w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:t=>({width:t.length*8})},{get:(o,k)=>o[k]||(()=>{})});
  w.Image=class{constructor(){this.naturalWidth=this.width=673;this.naturalHeight=this.height=406;}set src(value){this.url=value;queueMicrotask(()=>this.onload?.());}get src(){return this.url;}};
  w.fetch=async(path,options)=>{if(options?.body){const body=JSON.parse(options.body);posts.push({path,body});assert(!String(path).startsWith('/api/queue'),'A media drop must not queue generation');}return fetch(new URL(path,url),options);};
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id);await wait(()=>w.eval('typeof initialized!=="undefined"&&initialized')&&d.querySelectorAll('.filmstrip-item').length===2);
 const photoId='a'.repeat(24),videoId='target-video';
 function page(name){w.eval('showPage')(name);}
 function event(type,transfer,target){const e=new w.Event(type,{bubbles:true,cancelable:true});Object.defineProperties(e,{dataTransfer:{value:transfer},clientX:{value:160},clientY:{value:140}});target.dispatchEvent(e);return e;}
 function start(id){const button=d.querySelector('.filmstrip-item[data-media-key="'+id+'"]');assert(button);assert.equal(button.draggable,true);assert.equal(button.querySelector('img').draggable,false);const data=new Map(),transfer={types:[],files:[],effectAllowed:'',dropEffect:'',setData(k,v){data.set(k,v);this.types=[...data.keys()];},getData(k){return data.get(k)||'';}};event('dragstart',transfer,button);assert.equal(transfer.effectAllowed,'copy');const payload=JSON.parse(transfer.getData('application/x-studio-media'));assert.deepEqual(Object.keys(payload).sort(),['id','media_type']);return {button,transfer};}
 async function drop(id,target,verify){const drag=start(id),over=event('dragover',drag.transfer,target);assert(over.defaultPrevented);assert($('page-'+w.eval('current')).classList.contains('workspace-media-drop'));event('drop',drag.transfer,target);event('dragend',drag.transfer,drag.button);await wait(verify);assert(!d.querySelector('.workspace-media-drop'));assert.equal($('media-dialog').open,false);}
 page('editor');const first=start(photoId);$('workspace-recent-refresh').click();await pause(70);assert(first.button.isConnected,'Polling must not remove the thumbnail during drag');event('dragover',first.transfer,$('editor-stage'));event('drop',first.transfer,$('editor-stage'));event('dragend',first.transfer,first.button);await wait(()=>w.eval('editorSource?.id')===photoId);assert.equal(w.eval('current'),'editor');
 const saved=w.eval('editorSource.id');await drop(videoId,$('editor-stage'),()=>!d.querySelector('.workspace-media-drop'));assert.equal(w.eval('editorSource.id'),saved);assert.match($('toast').textContent,/accepts images/);
 page('upscale');const emptyPreview=$('enhance-preview').firstElementChild;w.eval('renderTools()');assert.equal($('enhance-preview').firstElementChild,emptyPreview,'Polling must preserve the empty drop target');await drop(photoId,$('enhance-preview'),()=>w.eval('enhanceSource?.id')===photoId);assert.equal($('enhance-kind').value,'image');
 await drop(videoId,$('enhance-preview'),()=>w.eval('enhanceSource?.id')===videoId);assert.equal($('enhance-kind').value,'video');
 page('video');await drop(photoId,$('video-preview'),()=>w.eval('videoSource?.id')===photoId);assert.equal($('vmode').value,'image');
 await drop(videoId,$('video-preview'),()=>$('video-preview').querySelector('video'));assert.equal(w.eval('videoSource?.id'),photoId,'Video preview must retain the image generation source');
 page('avatar');await drop(videoId,$('avatar-source'),()=>w.eval('avatarSource?.id')===videoId);assert.equal($('amodel').value,'avatar_musetalk');
 page('faceswap');await drop(videoId,$('face-preview'),()=>w.eval('videoFaceTarget?.id')===videoId);assert.equal($('face-media-mode').value,'video');
 await drop(photoId,$('face-video-reference'),()=>w.eval('videoFaceReference?.id')===photoId);
 page('images');$('imodel').value='moss_sft';$('imodel').dispatchEvent(new w.Event('change'));await drop(photoId,$('image-preview'),()=>$('image-preview').querySelector('img'));
 $('imodel').value='flux3';$('imodel').dispatchEvent(new w.Event('change'));await drop(photoId,$('image-preview'),()=>w.eval('generationRefItems("i").some(x=>x.id==="'+photoId+'")'));
 page('canvas');await wait(()=>w.eval('cv.ready'));await drop(photoId,$('cv-viewport'),()=>w.eval('cv.doc.layers.some(x=>x.source_id==="'+photoId+'")'));const layers=w.eval('cv.doc.layers.length');await drop(videoId,$('cv-viewport'),()=>!d.querySelector('.workspace-media-drop'));assert.equal(w.eval('cv.doc.layers.length'),layers);
 page('settings');await drop(photoId,$('page-settings'),()=>!d.querySelector('.workspace-media-drop'));assert.equal(w.eval('current'),'settings');
 assert.equal(errors.length,0,errors.join(';'));assert(!posts.some(p=>p.path==='/api/queue/add'||p.path.includes('/import')));
 const proof={editor:true,upscale_images_and_videos:true,video_image_source_and_video_preview:true,avatar_video:true,faceswap_video_and_reference:true,image_preview_and_generation_reference:true,canvas_layer:true,invalid_media_preserves_selection:true,refresh_preserves_drag:true,no_token_in_drag_payload:true,no_generation_or_import:true};fs.writeFileSync('outputs/workspace-drag-1.15.1.json',JSON.stringify(proof,null,2));dom.window.close();console.log('WORKSPACE_DRAG_UI_PASS '+JSON.stringify(proof));
})().catch(e=>{console.error(e);process.exit(1);});
