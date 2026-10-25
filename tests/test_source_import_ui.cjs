"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
const start=source.indexOf('let sourceImportBusy=false;'),end=source.indexOf('\nfunction ',source.indexOf('async function importFile(',start)+1);
assert(start>=0&&end>start);
const controls=['v','e','reference','upscale','avatar'].map(target=>({dataset:{import:target},disabled:false}));
let readers=[],requests=[],notices=[],selected=[],referenceCount=0,respond;
class Reader{readAsDataURL(file){readers.push(this);queueMicrotask(()=>{if(file.failRead)this.onerror();else{this.result='data:image/png;base64,cG5n';this.onload();}});}}
const ctx={document:{querySelectorAll:()=>controls},references:[],referenceLimit:()=>2,state:{busy:true,latest_media:{id:'generation-result'}},FileReader:Reader,
 sourceFor:target=>({v:'video',e:'editor'}[target]||target),notify:text=>notices.push(text),sendImage:(item,target)=>selected.push({item,target}),showPage:page=>selected.push({page}),
 api:async(path,body)=>{requests.push({path,body});return new Promise(done=>respond=done);}};
vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
const file={name:'Photo.png',type:'image/png',size:123};
(async()=>{
 ctx.updateImageImportButtons();assert(controls.every(b=>!b.disabled),'Busy generation must not disable source imports');
 const first=ctx.importFile(file,'v');assert(controls.every(b=>b.disabled));
 await ctx.importFile(file,'v');assert.equal(readers.length,1);assert(notices.at(-1).includes('current image import'));
 await new Promise(setImmediate);assert.equal(requests[0].path,'/api/images/import-source');
 ctx.state.latest_media={id:'unrelated-render-result'};respond({item:{id:'new-source'}});await first;
 assert.equal(selected.at(-1).target,'video');assert.equal(selected.at(-1).item.id,'new-source');assert.equal(ctx.state.busy,true);assert(controls.every(b=>!b.disabled));
 // Replacing an existing source and picking the same local file remain supported.
 ctx.api=async(path,body)=>{requests.push({path,body});return {item:{id:'replacement'}};};
 await ctx.importFile(file,'v');await ctx.importFile(file,'v');assert.equal(selected.at(-1).item.id,'replacement');assert(controls.every(b=>!b.disabled));
 assert(source.includes("importFile(e.target.files[0],importTarget);e.target.value=''"));
 ctx.api=async()=>{throw Error('Import failed');};const before=selected.length;await ctx.importFile(file,'v');assert.equal(selected.length,before);assert(controls.every(b=>!b.disabled));
 await ctx.importFile({...file,failRead:true},'v');assert(notices.at(-1).includes('could not be read'));assert(controls.every(b=>!b.disabled));
 ctx.references=[{},{}];ctx.updateImageImportButtons();assert(controls.find(b=>b.dataset.import==='reference').disabled);assert(!controls.find(b=>b.dataset.import==='v').disabled);
 assert(source.includes("updateImageImportButtons();renderResources()"));
 console.log('SOURCE_IMPORT_UI_PASS: replace source during rendering, exact request routing, repeated picks, concurrent guard and error recovery; no media generated');
})().catch(error=>{console.error(error);process.exitCode=1;});
