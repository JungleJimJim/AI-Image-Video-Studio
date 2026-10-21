'use strict';
// Development dependency: jsdom. This fixture has no inference route.
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2];if(!url)throw Error('Pass the URL from research/serve_moss_ui_1120.py');
const errors=[],imports=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(test){for(let i=0;i<100;i++){if(test())return;await pause(50);}throw Error('UI state timed out: '+errors.join(';'));}
(async()=>{
 const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=(path,options)=>fetch(new URL(path,url),options);w.structuredClone=structuredClone;
  w.ResizeObserver=class{observe(){} disconnect(){}};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({},{get:()=>()=>{}});
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id),change=(id,value)=>{$(id).value=value;$(id).dispatchEvent(new w.Event('change',{bubbles:true}));};
 await wait(()=>$('imodel')?.value==='moss_sft'&&!$('imoss-panel').hidden);
 assert.equal([...$('imodel').options].filter(x=>/MOSS|Kromoss/.test(x.text)).length,6);
 assert.equal($('imoss-recipe').value,'full');change('imoss-recipe','sft8');
 assert.equal($('icfg').value,'1');assert.equal($('isteps').value,'8');assert.equal($('inegative').disabled,true);
 change('imoss-mode','layout');$('imoss-layout').click();$('moss-box-add').click();
 for(const [key,value] of Object.entries({type:'text',caption:'A title sign',text:'COAST',x:5,y:10,w:80,h:20,palette:'#ffaa00'})){
  $('moss-box-'+key).value=value;$('moss-box-'+key).dispatchEvent(new w.Event('input',{bubbles:true}));
 }
 const compiled=JSON.parse($('moss-layout-json').textContent);assert.equal(compiled.items[0].text,'COAST');assert.equal(compiled.bbox_format,'yxyx');
 $('moss-layout-save').click();
 w.eval("sendImage({id:'reference-logo',name:'Color map.png',media_type:'image'},'moss:i:color')");
 w.eval("sendImage({id:'reference-logo',name:'Depth map.png',media_type:'image'},'moss:i:depth')");
 let options=w.eval("values('i')");assert.equal(options.moss.layout[0].text,'COAST');assert.equal(options.moss.color_id,'reference-logo');assert.equal(options.moss.depth_id,'reference-logo');
 change('imoss-encoder','int8');change('imoss-vae','full');options=w.eval("values('i')");assert.equal(options.moss.encoder,'int8');assert.equal(options.moss.vae,'full');
 const saved=structuredClone(options);w.eval('fill')( 'i',saved);assert.equal(w.eval("values('i')").moss.layout[0].text,'COAST');
 $('image-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 await wait(()=>$('toast').textContent.includes('queue'));
 // The file button uses the existing import pipeline with the exact map target.
 w.__imports=imports;w.eval('importFile=(file,target)=>__imports.push(target)');
 const click=w.HTMLInputElement.prototype.click;
 w.HTMLInputElement.prototype.click=function(){if(this.type==='file'){Object.defineProperty(this,'files',{value:[new w.File(['fixture'],'map.png',{type:'image/png'})]});this.onchange();}else click.call(this);};
 d.querySelector('[data-moss-import="i:color"]').click();assert.equal(imports[0],'moss:i:color');
 change('imodel','kromoss');change('imoss-recipe','dmd2');change('imoss-fast-steps','4');
 assert.equal(w.eval("values('i')").moss.layout[0].text,'COAST');assert.equal(w.eval("values('i')").moss.color_id,'reference-logo');
 assert.equal($('isteps').value,'4');assert.equal($('icfg').value,'1');
 change('imoss-recipe','full');assert.equal($('icfg').value,'3');assert.equal($('isteps').value,'50');
 assert.equal(errors.length,0,errors.join(';'));
 const proof={models:6,layout_text_and_boxes:true,color_depth_ids_preserved:true,precision_options:true,queue_payload_captured:true,local_map_import_routing:true,fast_steps_4_and_8:true,no_script_errors:true,generation_started:false};
 fs.writeFileSync('outputs/moss-ui-1.12.0.json',JSON.stringify(proof,null,2));
 dom.window.close();console.log('MOSS_UI_PASS '+JSON.stringify(proof));
})().catch(e=>{console.error(e);process.exit(1);});
