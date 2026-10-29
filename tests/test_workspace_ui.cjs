'use strict';
// Full UI regression in a processing-disabled fixture: no inference or downloaded models.
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],posts=[],vc=new VirtualConsole();
vc.on('jsdomError',e=>errors.push(e.message));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(test){for(let n=0;n<140;n++){if(test())return;await pause(50);}throw Error('Workspace UI timeout: '+errors.join(';'));}
async function open(preferences){
 return JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=(path,options)=>{if(options?.body)posts.push({path,body:JSON.parse(options.body)});return fetch(new URL(path,url),options);};
  w.structuredClone=structuredClone;w.ResizeObserver=class{observe(){}disconnect(){}};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:t=>({width:t.length*8})},{get:(o,k)=>o[k]||(()=>{})});
  if(preferences)w.localStorage.setItem('studio.canvas-workspace.v1',preferences);
 }});
}
(async()=>{
 let dom=await open(),w=dom.window,d=w.document,$=id=>d.getElementById(id);
 await wait(()=>w.eval('typeof initialized!=="undefined"&&initialized')&&$('workspace-recent').querySelectorAll('button').length===2);
 const controlsBefore=[...d.querySelectorAll('#pages input,#pages textarea,#pages select')].length;
 const nav=[...d.querySelectorAll('#navigation [data-page]')];
 assert.equal(nav.length,13);
 $('iprompt').value='Preserve this unsaved image prompt';
 $('vprompt').value='Preserve this unsaved video prompt';
 for(const button of nav){
  button.click();await pause(20);
  const id=button.dataset.page;
  assert.equal($('page-'+id).hidden,false,id);
  assert.equal(d.querySelectorAll('.page:not([hidden])').length,1,id);
  assert.equal(d.querySelector('.workspace-rail .active').dataset.workspaceGo,id);
  assert.equal(button.getAttribute('aria-current'),'page');
 }
 assert.equal($('iprompt').value,'Preserve this unsaved image prompt');
 assert.equal($('vprompt').value,'Preserve this unsaved video prompt');
 assert.equal([...d.querySelectorAll('#pages input,#pages textarea,#pages select')].length>=controlsBefore,true);
 d.querySelector('#navigation [data-page="images"]').click();await pause(20);
 assert.equal($('image-form').parentElement.classList.contains('workspace-docked'),true);
 assert.equal($('edit-form').parentElement.classList.contains('workspace-docked'),true);
 $('workspace-focus').click();assert(d.body.classList.contains('workspace-focus'));
 assert.equal($('workspace-focus').getAttribute('aria-pressed'),'true');
 assert.equal($('iprompt').value,'Preserve this unsaved image prompt');
 // Page navigation restores the dock so no controls become stranded in focus mode.
 d.querySelector('#navigation [data-page="video"]').click();await pause(20);
 assert(!d.body.classList.contains('workspace-focus'));
 $('workspace-filmstrip-toggle').click();assert(d.body.classList.contains('filmstrip-hidden'));
 $('workspace-dock-width').value='420';$('workspace-dock-width').dispatchEvent(new w.Event('input',{bubbles:true}));
 const saved=w.localStorage.getItem('studio.canvas-workspace.v1');assert.equal(JSON.parse(saved).width,420);assert.equal(JSON.parse(saved).filmstrip,false);
 $('workspace-filmstrip-toggle').click();
 d.querySelector('[data-recent-type="image"]').click();await wait(()=>$('workspace-recent').querySelectorAll('button').length===1);
 assert($('workspace-recent').textContent.includes('Reference image'));
 $('workspace-recent').querySelector('button').click();await wait(()=>$('media-dialog').open);
 $('media-dialog').close();
 d.querySelector('[data-recent-type="video"]').click();await wait(()=>$('workspace-recent').textContent.includes('Target video'));
 assert.equal($('workspace-recent').querySelectorAll('button').length,1);
 // New chrome must not intercept imports, queue submission, masks or Canvas events.
 assert.equal(posts.some(p=>p.path==='/api/queue/add'),false);
 assert.equal(errors.length,0,errors.join(';'));
 dom.window.close();
 dom=await open(saved);w=dom.window;d=w.document;$=id=>d.getElementById(id);
 await wait(()=>w.eval('typeof initialized!=="undefined"&&initialized')&&$('workspace-reset'));
 assert(d.body.classList.contains('filmstrip-hidden'));assert.equal($('workspace-dock-width').value,'420');
 $('workspace-reset').click();assert(!d.body.classList.contains('filmstrip-hidden'));assert.equal($('workspace-dock-width').value,'340');
 assert.equal(errors.length,0,errors.join(';'));
 const proof={pages:nav.length,drafts_preserved:true,filmstrip_filters_and_media_dialog:true,focus_navigation_restore:true,preferences_survive_reload:true,reset_workspace:true,no_script_errors:true,generation_started:false};
 fs.writeFileSync('outputs/workspace-ui-validation.json',JSON.stringify(proof,null,2));dom.window.close();console.log('WORKSPACE_UI_PASS '+JSON.stringify(proof));
})().catch(error=>{console.error(error);process.exit(1);});
