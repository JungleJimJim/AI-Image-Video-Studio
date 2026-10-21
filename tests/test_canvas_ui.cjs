'use strict';
// Runs against a fixture that has no inference route. Rendering/export is mocked.
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.argv[2],errors=[],requests=[],draws=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(test){for(let i=0;i<120;i++){if(test())return;await pause(50);}throw Error('Canvas UI timed out: '+errors.join(';'));}
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
(async()=>{
 const dom=await JSDOM.fromURL(url,{runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=(path,options)=>{if(options?.body)requests.push({route:path,body:JSON.parse(options.body)});return fetch(new URL(path,url),options);};
  w.structuredClone=structuredClone;w.ResizeObserver=class{observe(){} disconnect(){}};
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  w.Element.prototype.setPointerCapture=function(){};
  w.Image=class{set src(value){this.url=value;setTimeout(()=>this.onload?.(),0);}get src(){return this.url;}};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:text=>({width:text.length*8}),drawImage:(...args)=>draws.push(args)},{get:(obj,key)=>obj[key]||(()=>{})});
  w.HTMLCanvasElement.prototype.toDataURL=()=>'data:image/png;base64,cG5n';
 }});
 const w=dom.window,d=w.document,$=id=>d.getElementById(id),change=(id,value)=>{$(id).value=value;$(id).dispatchEvent(new w.Event('change',{bubbles:true}));};
 await wait(()=>d.readyState==='complete'&&$('page-canvas')&&$('imodel')?.value==='moss_sft'&&w.eval('initialized'));
 assert.equal(d.querySelector('[data-page="editor"]').nextElementSibling.dataset.page,'canvas');
 $('cv-viewport').getBoundingClientRect=()=>({left:0,top:0,width:800,height:600});
 d.querySelector('[data-page="canvas"]').click();await wait(()=>w.eval('cv.ready'));
 // Generic .panel has height:100%. Canvas chrome must override it so the
 // toolbar/footer cannot consume whole pages and hide the artboard.
 for(const element of d.querySelectorAll('.canvas-toolbar,.canvas-bottom,.canvas-sidebar'))assert.equal(w.getComputedStyle(element).height,'auto');
 assert.equal(w.getComputedStyle($('page-canvas')).overflow,'auto');
 for(const element of d.querySelectorAll('.canvas-sidebar'))assert.equal(w.getComputedStyle(element).overflow,'auto');
 await wait(()=>$('cv-library').querySelector('[data-id]'));$('cv-library').querySelector('[data-id]').click();
 await wait(()=>w.eval('cv.doc.layers.length')===1);assert.equal(w.eval('cv.doc.layers[0].source_id'),'a'.repeat(24));
 // Pointer move and corner resize use artboard pixels, even when zoomed.
 function pointer(type,target,x,y){const event=new w.MouseEvent(type,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0});Object.defineProperty(event,'pointerId',{value:1});target.dispatchEvent(event);}
 const before=w.eval('structuredClone(cv.doc.layers[0])');
 pointer('pointerdown',d.querySelector('#cv-layers [data-layer]'),200,200);pointer('pointermove',$('cv-viewport'),250,230);pointer('pointerup',$('cv-viewport'),250,230);
 assert(w.eval('cv.doc.layers[0].x')>before.x);
 change('cv-prop-x','10');change('cv-prop-y','20');change('cv-prop-w','500');assert.equal(w.eval('cv.doc.layers[0].w'),500);
 const ratio=w.eval('cv.doc.layers[0].w/cv.doc.layers[0].h');change('cv-prop-w','600');assert(Math.abs(w.eval('cv.doc.layers[0].w/cv.doc.layers[0].h')-ratio)<.001);
 const geometry=w.eval('structuredClone(cv.doc.layers[0])'),pan=w.eval('structuredClone(cv.pan)'),zoom=w.eval('cv.zoom');
 pointer('pointerdown',d.querySelector('[data-handle="se"]'),pan.x+(geometry.x+geometry.w)*zoom,pan.y+(geometry.y+geometry.h)*zoom);
 pointer('pointermove',$('cv-viewport'),pan.x+(geometry.x+geometry.w+100)*zoom,pan.y+(geometry.y+geometry.h+50)*zoom);pointer('pointerup',$('cv-viewport'),0,0);
 assert(w.eval('cv.doc.layers[0].w')>geometry.w);
 const grown=w.eval('cv.doc.layers[0].w');$('cv-undo').click();assert.equal(w.eval('cv.doc.layers[0].w'),geometry.w);$('cv-redo').click();assert.equal(w.eval('cv.doc.layers[0].w'),grown);
 change('cv-prop-rotation','25');change('cv-prop-opacity','.6');change('cv-caption','A blue robot');
 $('cv-duplicate').click();assert.equal(w.eval('cv.doc.layers.length'),2);$('cv-remove').click();assert.equal(w.eval('cv.doc.layers.length'),1);
 $('cv-text').click();change('cv-text-value','STUDIO');change('cv-font-size','80');change('cv-color','#ffaa00');
 d.querySelector('[data-lock="'+w.eval('cv.selected')+'"]').click();assert($('cv-remove').disabled);d.querySelector('[data-lock="'+w.eval('cv.selected')+'"]').click();
 const first=w.eval('cv.doc.layers[0].id');d.querySelector('[data-visible="'+first+'"]').click();assert.equal(d.querySelectorAll('#cv-layers [data-layer]').length,1);d.querySelector('[data-visible="'+first+'"]').click();
 const oldZoom=w.eval('cv.zoom');$('cv-viewport').dispatchEvent(new w.WheelEvent('wheel',{deltaY:-100,clientX:400,clientY:300,bubbles:true,cancelable:true}));assert(w.eval('cv.zoom')>oldZoom);
 change('cv-name','Canvas test');$('cv-save-project').click();await wait(()=>w.eval('cv.doc.id')==='b'.repeat(24));
 await pause(750);assert(requests.some(x=>x.route==='/api/canvas/draft'));
 $('cv-moss').click();assert.equal($('page-images').hidden,false,$('toast').textContent+' '+w.eval('JSON.stringify(cv.doc)')+' '+errors.join(';'));const layout=w.eval("values('i').moss.layout");assert.equal(layout.length,2);assert(layout.some(l=>l.caption==='A blue robot'));assert(layout.some(l=>l.text==='STUDIO'));
 assert(layout.every(l=>l.x>=0&&l.y>=0&&l.x+l.w<=100.00001&&l.y+l.h<=100.00001));
 w.eval("showPage('canvas')");await w.eval('cvExport()');const exported=requests.find(x=>x.route==='/api/canvas/export');assert(exported);assert.equal(exported.body.project.layers.length,2);assert.equal(draws.length,1);
 await w.eval("cvExport('video')");assert.equal($('page-video').hidden,false);assert.equal(w.eval('videoSource.id'),'c'.repeat(24));
 // File drop goes through the independent Canvas importer, not the generation importer.
 w.eval("showPage('canvas')");const drop=new w.Event('drop',{bubbles:true,cancelable:true});Object.defineProperties(drop,{clientX:{value:200},clientY:{value:200},dataTransfer:{value:{files:[new w.File(['fixture'],'Local.png',{type:'image/png'})],getData:()=>'',types:['Files']}}});$('cv-viewport').dispatchEvent(drop);
 await wait(()=>requests.some(x=>x.route==='/api/canvas/import'));await wait(()=>!w.eval('cv.importing'));
 assert.equal(requests.filter(x=>x.route==='/api/queue/add'||x.route==='/api/images/import').length,0);
 assert.equal(errors.length,0,errors.join(';'));
 const proof={tab_next_to_editor:true,panel_height_overrides:true,page_scroll_fallback:true,side_panel_scroll:true,library_and_local_drop:true,pointer_move_resize:true,rotation_opacity_layers:true,undo_redo:true,wheel_zoom:true,project_and_draft:true,moss_layout_transfer:true,export_and_send_video:true,no_script_errors:true,generation_started:false,canvas_rendering_mocked:true};
 fs.writeFileSync('outputs/canvas-ui-1.13.1.json',JSON.stringify(proof,null,2));dom.window.close();console.log('CANVAS_UI_PASS '+JSON.stringify(proof));
})().catch(e=>{console.error(e);process.exit(1);});
