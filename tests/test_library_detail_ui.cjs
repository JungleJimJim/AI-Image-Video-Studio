'use strict';
// Disposable in-memory media; the fixture has no inference route.
const {JSDOM,VirtualConsole}=require('jsdom'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],posts=[],downloads=[],catalog=Array.from({length:26},(_,i)=>({id:i.toString(16).padStart(24,'0'),name:'Original_'+i+(i%2?'.mp4':'.png'),media_type:i%2?'video':'image',kind:'generated',created:'2026-10-'+String(29-Math.floor(i/3)).padStart(2,'0'),options:{prompt:'A cinematic landscape with mountains number '+i},thumbnail:{status:'ready'},width:640,height:480}));
let items=[...catalog],batches=[],delay=0;
const pause=ms=>new Promise(r=>setTimeout(r,ms));async function wait(fn){for(let n=0;n<180;n++){if(fn())return;await pause(40);}throw Error('Library UI timeout: '+errors.join(';'));}
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const reply=value=>({ok:true,json:async()=>value});
(async()=>{
 const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.structuredClone=structuredClone;w.ResizeObserver=class{observe(){}disconnect(){}};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
  w.HTMLMediaElement.prototype.pause=function(){};w.HTMLMediaElement.prototype.load=function(){};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:t=>({width:t.length*8})},{get:(o,k)=>o[k]||(()=>{})});
  w.HTMLAnchorElement.prototype.click=function(){downloads.push({href:this.href,name:this.download});};
  w.fetch=async(path,options)=>{
   const route=new URL(path,url),body=options?.body?JSON.parse(options.body):null;
   if(body)posts.push({route:route.pathname,body});
   if(route.pathname==='/api/state'){const response=await fetch(new URL(path,url),options);const state=await response.json();for(const key of ['image_options','edit_options','options'])state.settings[key]={...(state.settings[key]||{}),upscale:{enabled:true}};state.local_voices=[{id:'kokoro',name:'Kokoro',ready:false,size:353719767,vram_tier_gb:8,vram_note:'CPU',source:'https://huggingface.co/hexgrad/Kokoro-82M',license:'Apache-2.0'},{id:'qwen_tts',name:'Qwen',ready:false,size:2516100892,vram_tier_gb:8,vram_note:'8 GB estimated',source:'https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base',license:'Apache-2.0'}];return reply(state);}
   if(route.pathname==='/api/library'){
    const type=route.searchParams.get('type')||'all',search=route.searchParams.get('search')||'',page=Number(route.searchParams.get('page')||0),count=Number(route.searchParams.get('count')||24);
    const filtered=items.filter(x=>(type==='all'||x.media_type===type)&&JSON.stringify(x).includes(search));
    if(delay)await pause(delay);
    return reply({items:filtered.slice(page*count,(page+1)*count),total:filtered.length,page,count});
   }
   if(route.pathname==='/api/queue/add')return reply({ok:true,id:'captured-only'});
   if(route.pathname==='/api/voice/install')return reply({ok:true});
   if(route.pathname==='/api/library/trash')return reply({items:batches.map(b=>({id:b.id,count:b.items.length,names:b.items.map(x=>x.name),created:'2026-10-29'}))});
   if(route.pathname==='/api/library/delete'){
    const removed=items.filter(x=>body.ids.includes(x.id));batches.push({id:'f'.repeat(32),items:removed});items=items.filter(x=>!body.ids.includes(x.id));return reply({ok:true,count:removed.length,deleted:removed.map(x=>x.id),batch:'f'.repeat(32)});
   }
   if(route.pathname==='/api/library/restore'){const batch=batches.find(x=>x.id===body.batch);items.push(...batch.items);batches=[];return reply({ok:true,count:batch.items.length});}
   if(route.pathname==='/api/library/export')return reply({id:'e'.repeat(32),name:'Studio-test.zip',count:body.ids.length});
   if(route.pathname.startsWith('/api/library/'))return reply({item:catalog.find(x=>x.id===route.pathname.split('/').pop()),ancestors:[]});
   return fetch(new URL(path,url),options);
  };
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id);
 await wait(()=>w.eval('typeof initialized!=="undefined"&&initialized')&&$('library-select-page'));
 for(const p of ['i','e','v'])assert.equal($(p+'enhance').checked,false,'Enhancement defaults off even after previously enabled jobs');
 $('ienhance').checked=true;w.eval('renderTools()');assert.equal($('ienhance').checked,true,'Manual enable stays selected during polling');$('ienhance').checked=false;
 d.querySelector('#navigation [data-page="library"]').click();
 await wait(()=>d.querySelectorAll('#lib-grid .library-select-item').length===24);
 assert.equal(d.querySelector('.card-name').textContent,'A cinematic landscape with mountains');
 assert.equal(d.querySelector('.card-name').title,'Original_0.png');
 assert.equal(w.eval('mediaTitle({name:"fallback.png",options:{prompt:"  "}})'),'fallback.png');
 assert.equal(w.eval('mediaTitle({name:"x",options:{prompt:" one\\n two\\tthree four five six"}})'),'one two three four five');
 d.querySelector('#lib-grid .thumb').click();await wait(()=>$('media-dialog').open);
 assert.equal($('media-title').textContent,'A cinematic landscape with mountains');assert($('media-previous').disabled);assert(!$('media-next').disabled);
 // A press inside then release outside must not dismiss the view.
 $('media-dialog').getBoundingClientRect=()=>({left:100,top:100,right:700,bottom:500});
 function pointer(type,target,x,y){target.dispatchEvent(new w.MouseEvent(type,{bubbles:true,clientX:x,clientY:y,button:0}));}
 pointer('pointerdown',$('media-body'),150,150);pointer('click',$('media-dialog'),50,50);assert($('media-dialog').open);
 pointer('pointerdown',$('media-dialog'),150,150);pointer('click',$('media-dialog'),150,150);assert($('media-dialog').open);
 $('media-next').click();assert.equal($('media-dialog').dataset.item,catalog[1].id);assert($('frame-video'));
 $('media-previous').click();assert.equal($('media-dialog').dataset.item,catalog[0].id);assert(!$('frame-video'));
 // Navigate across both page boundaries, retaining the full filtered ordering.
 for(let i=0;i<24;i++){$('media-next').click();if(i===23)await wait(()=>$('media-dialog').dataset.item===catalog[24].id);}
 assert.equal($('media-position').textContent,'25 of 26');
 $('media-previous').click();await wait(()=>$('media-dialog').dataset.item===catalog[23].id);
 assert.equal($('media-position').textContent,'24 of 26');
 pointer('pointerdown',$('media-dialog'),50,50);pointer('click',$('media-dialog'),50,50);assert(!$('media-dialog').open);
 // Closing cancels a pending page navigation.
 w.eval('openMedia') (catalog[23],{items:catalog.slice(0,24),page:0,count:24,total:26,type:'all',search:''});
 delay=120;$('media-next').click();$('media-dialog').close();await pause(180);assert(!$('media-dialog').open);delay=0;
 // Selection survives pagination and exports mixed image/video originals.
 const checks=d.querySelectorAll('#lib-grid .library-select-item');checks[0].click();checks[1].click();assert.equal($('library-selected-count').textContent,'2 selected');
 $('lib-next').click();await wait(()=>d.querySelectorAll('#lib-grid .library-select-item').length===2);
 d.querySelector('#lib-grid .library-select-item').click();assert.equal($('library-selected-count').textContent,'3 selected');
 $('library-export-selected').click();await wait(()=>downloads.length===1);assert(downloads[0].name.endsWith('.zip'));
 assert.equal(posts.find(x=>x.route==='/api/library/export').body.ids.length,3);
 // Cancellation does not send a delete request.
 $('library-delete-selected').click();$('library-delete-dialog').close();assert.equal(posts.filter(x=>x.route==='/api/library/delete').length,0);
 $('library-delete-selected').click();$('library-delete-confirm').click();await wait(()=>posts.some(x=>x.route==='/api/library/delete')&&!$('library-delete-dialog').open);
 assert.equal(items.length,23);await wait(()=>$('library-selected-count').textContent==='0 selected');
 $('library-show-trash').click();await wait(()=>d.querySelector('[data-restore]'));d.querySelector('[data-restore]').click();await wait(()=>items.length===26&&batches.length===0);
 $('library-trash-dialog').close();
 // A filter is retained while navigating details.
 $('lib-type').value='video';$('lib-type').dispatchEvent(new w.Event('change',{bubbles:true}));
 await wait(()=>d.querySelectorAll('#lib-grid .library-select-item').length===13);
 d.querySelector('#lib-grid .thumb').click();$('media-next').click();assert.equal($('media-dialog').querySelector('video')!==null,true);
 assert.equal($('media-position').textContent,'2 of 13');
 assert.equal(posts.filter(x=>x.route==='/api/queue/add').length,0);
 $('media-dialog').close();
 assert.equal(d.querySelector('select#enhance-source'),null);
 w.eval('setEnhancementSource')(catalog[0],'image');assert.equal($('enhance-source').textContent,'A cinematic landscape with mountains');assert.equal($('enhance-preview').dataset.source,catalog[0].id);
 w.eval('setEnhancementSource')(catalog[1],'video');assert.equal($('enhance-kind').value,'video');assert.equal($('enhance-preview').dataset.source,catalog[1].id);assert.equal($('enhance-local-file').hidden,true);
 $('enhance-library').click();assert.equal($('page-library').hidden,false);
 d.querySelector('#navigation [data-page="voice"]').click();
 $('hprotocol').value='local';$('hprotocol').dispatchEvent(new w.Event('change',{bubbles:true}));
 assert.equal($('local-voice-controls').hidden,false);assert.equal($('hendpoint').closest('.field').hidden,true);
 assert.equal($('hreference_id').closest('.field').hidden,true);
 $('hmodel').value='qwen_tts';$('hmodel').dispatchEvent(new w.Event('change',{bubbles:true}));
 assert.equal($('qwen-voice-fields').hidden,false);assert.equal($('hreference_id').closest('.field').hidden,false);assert.equal($('hreference_id').required,true);assert.match($('hreference_id').options[0].textContent,/Choose a 0.1/);
 $('hreference_id').insertAdjacentHTML('beforeend','<option value="reference">Test reference</option>');$('hreference_id').value='reference';$('htext').value='A short test speech';$('hlanguage').value='English';
 $('voice-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await wait(()=>posts.some(x=>x.route==='/api/queue/add'));
 const voiceJob=posts.find(x=>x.route==='/api/queue/add').body;
 assert.equal(voiceJob.kind,'voice');assert.equal(voiceJob.options.protocol,'local');assert.equal(voiceJob.options.model,'qwen_tts');assert.equal(voiceJob.options.device,'cuda');assert.equal(voiceJob.options.reference_id,'reference');
 $('hprotocol').value='fish';$('hprotocol').dispatchEvent(new w.Event('change',{bubbles:true}));assert.equal($('local-voice-controls').hidden,true);assert.equal($('hendpoint').closest('.field').hidden,false);
 d.querySelector('#navigation [data-page="models"]').click();await wait(()=>$('local-voice-pack-kokoro')&&$('local-voice-pack-qwen_tts'));

 assert.equal(errors.length,0,errors.join(';'));
 const proof={upscale_library_picker_only:true,enhancement_default_off:true,manual_enhancement_preserved:true,backdrop_close:true,inside_and_drag_protected:true,photo_video_navigation:true,page_boundaries:true,filter_retained:true,close_cancels_pending_navigation:true,mixed_selection_across_pages:true,zip_export:true,delete_confirmation_cancel:true,trash_restore:true,prompt_titles:true,no_script_errors:true,local_voice_controls:true,voice_queue_payload_captured:true,generation_started:false};
 fs.writeFileSync('outputs/library-ui-1.15.1.json',JSON.stringify(proof,null,2));dom.window.close();console.log('LIBRARY_DETAIL_UI_PASS '+JSON.stringify(proof));
})().catch(error=>{console.error(error);process.exit(1);});
