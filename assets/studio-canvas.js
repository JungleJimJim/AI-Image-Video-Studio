'use strict';
// A local compositor. Model generation only happens through the existing queue.
help.canvas=['Canvas','Drop PNG, JPEG or WebP files, or drag Library thumbnails onto the artboard. Select a layer to move it; drag a corner to resize. Shift preserves proportions. Use the wheel to zoom, or Space/middle-drag to pan. Delete removes a layer; Ctrl+Z undoes it. Sources are saved in Library.'];
help.canvasDocument=['Canvas document','Dimensions are output pixels, up to 8192 per side and 16,777,216 pixels total. Changing dimensions changes the artboard without scaling layers. Background is a solid color; transparent source images keep their transparency. Projects and the automatic draft save locally in canvas-projects.'];
help.canvasLayer=['Layer properties','X and Y locate the unrotated layer’s top-left corner in output pixels. Rotation is around its center. Opacity blends it with lower layers. Higher layers appear in front. Locking prevents changes until unlocked. A caption describes an image to MOSS; it is not printed on the image.'];
help.canvasExport=['Save and send','Save project keeps separate, editable layers. Save image creates a new PNG in Library, including hidden-layer information in its metadata. Send to editor/video first saves that composite. These actions do not run an AI model.'];
help.canvasMoss=['MOSS layout','Send visible layer captions, text and positions to the MOSS Images controls. This describes placement; it does not preserve the identity of dropped photos. To repaint actual pixels, send the composite to Image Editor and choose MOSS there. Layouts support up to 24 visible elements. No generation starts until you add a job to the queue.'];
pages.canvas=['Canvas','Arrange images and text in layers. Save a composition, repaint it in Image Editor, or send its layout to MOSS.'];
const canvasNav=document.createElement('button');canvasNav.dataset.page='canvas';canvasNav.textContent='Canvas';
document.querySelector('[data-page="editor"]').after(canvasNav);canvasNav.onclick=()=>showPage('canvas');
$('page-editor').insertAdjacentHTML('afterend',`<section id="page-canvas" class="page" hidden>
 <div class="canvas-toolbar panel"><div class="row"><input id="cv-name" value="Untitled canvas" maxlength="100" aria-label="Canvas project name"><button id="cv-new">New</button><button id="cv-save-project">Save project</button><button id="cv-open-project">Open project</button>${q('canvasDocument')}<span class="canvas-spacer"></span><button id="cv-undo" title="Undo (Ctrl+Z)">Undo</button><button id="cv-redo" title="Redo (Ctrl+Shift+Z)">Redo</button><button id="cv-fit">Fit</button><button id="cv-zoom-out" aria-label="Zoom out">−</button><output id="cv-zoom">100%</output><button id="cv-zoom-in" aria-label="Zoom in">+</button>${q('canvas')}</div></div>
 <div class="canvas-workspace"><aside class="canvas-sidebar panel"><h3>Sources</h3><div class="row"><button id="cv-local">Local files</button><button id="cv-library-refresh">Refresh Library</button></div><input id="cv-files" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden><label for="cv-search">Search Library</label><input id="cv-search" type="search" placeholder="Find an image"><div id="cv-library" class="canvas-library"></div><div class="row"><button id="cv-prev">‹</button><small id="cv-count"></small><button id="cv-next">›</button></div><p class="notice">Drag thumbnails or local files onto the artboard. Click a thumbnail to add it.</p><button id="cv-text">Add text</button>
 <details><summary>Artboard ${q('canvasDocument')}</summary>${f('cv-size','Preset',sel('cv-size',[['1024x1024','Square · 1024 × 1024'],['1536x1024','Landscape · 1536 × 1024'],['1024x1536','Portrait · 1024 × 1536'],['1920x1080','16:9 · 1920 × 1080'],['1080x1920','9:16 · 1080 × 1920'],['custom','Custom']]),'canvasDocument')}<div class="two">${f('cv-width','Width',num('cv-width',1024,64,8192,1),'canvasDocument')}${f('cv-height','Height',num('cv-height',1024,64,8192,1),'canvasDocument')}</div>${f('cv-background','Background','<input id="cv-background" type="color" value="#ffffff">','canvasDocument')}</details></aside>
 <div id="cv-viewport" class="canvas-viewport" tabindex="0" aria-label="Composition artboard. Drop images here."><div id="cv-board" class="canvas-board"><div id="cv-layers"></div></div><div id="cv-empty" class="canvas-empty">Drop images here<br><small>or add them from the Library</small></div></div>
 <aside class="canvas-sidebar panel"><h3>Layers ${q('canvasLayer')}</h3><div id="cv-layer-list" class="canvas-layer-list"></div><div class="row"><button id="cv-up" title="Move layer forward">↑</button><button id="cv-down" title="Move layer backward">↓</button><button id="cv-duplicate">Duplicate</button><button id="cv-remove" aria-label="Remove selected layer">×</button></div><div id="cv-properties"><p class="notice">Select a layer to change it.</p></div></aside></div>
 <div class="canvas-bottom panel"><span id="cv-status" role="status">Your draft saves automatically.</span><div class="row"><button id="cv-moss">Use as MOSS layout</button>${q('canvasMoss')}<button id="cv-save-image">Save image to Library</button><button id="cv-editor">Send to editor</button><button id="cv-video">Send to video</button>${q('canvasExport')}</div></div>
 </section>`);
document.body.insertAdjacentHTML('beforeend',`<dialog id="cv-project-dialog"><div class="dialog-heading"><h2>Open Canvas project</h2><button data-close aria-label="Close project list">×</button></div><div id="cv-project-list"></div></dialog>`);
const cv={doc:cvFresh(),selected:null,history:[],future:[],sources:new Map(),images:new Map(),page:0,search:'',request:0,zoom:1,pan:{x:0,y:0},drag:null,space:false,ready:false,starting:null,dirty:0,saved:0,saving:false,exporting:false,importing:false};
function cvFresh(){return {schema:1,name:'Untitled canvas',width:1024,height:1024,background:'#ffffff',layers:[]};}
function cvId(){return crypto.randomUUID();}
function cvSelected(){return cv.doc.layers.find(x=>x.id===cv.selected);}
function cvStatus(message){$('cv-status').textContent=message;}
function cvSnapshot(){return JSON.stringify(cv.doc);}
function cvPush(snapshot=cvSnapshot()){cv.history.push(snapshot);if(cv.history.length>50)cv.history.shift();cv.future=[];}
function cvChanged(){cv.dirty++;cvStatus('Draft changed · saving…');clearTimeout(cv.timer);cv.timer=setTimeout(cvSaveDraft,600);cvRender();}
async function cvSaveDraft(){
 if(cv.saving||cv.saved===cv.dirty)return;cv.saving=true;const version=cv.dirty;
 try{await api('/api/canvas/draft',{project:structuredClone(cv.doc)});cv.saved=version;if(cv.saved===cv.dirty)cvStatus('Draft saved locally.');}
 catch(e){cvStatus('Draft not saved: '+e.message);}
 finally{cv.saving=false;if(cv.saved!==cv.dirty&&cv.dirty!==version)cvSaveDraft();}
}
async function cvStart(){
 if(cv.ready)return;if(cv.starting)return cv.starting;
 $('page-canvas').inert=true;cv.starting=(async()=>{try{const result=await api('/api/canvas/draft');if(result.project){cv.doc=result.project;for(const item of result.sources)cv.sources.set(item.id,item);await cvLoadSources();}}catch(e){cvStatus('Could not restore draft: '+e.message);}finally{cv.ready=true;$('page-canvas').inert=false;cvRender();cvFit();cvLibrary();}})();return cv.starting;
}
const canvasPreviousShowPage=showPage;showPage=function(id){canvasPreviousShowPage(id);if(id==='canvas')cvStart().then(()=>requestAnimationFrame(cvFit));};
function cvRender(){
 $('cv-name').value=cv.doc.name;$('cv-width').value=cv.doc.width;$('cv-height').value=cv.doc.height;$('cv-background').value=cv.doc.background;
 const preset=cv.doc.width+'x'+cv.doc.height;$('cv-size').value=[...$('cv-size').options].some(o=>o.value===preset)?preset:'custom';
 const board=$('cv-board');board.style.width=cv.doc.width+'px';board.style.height=cv.doc.height+'px';board.style.background=cv.doc.background;
 $('cv-layers').innerHTML=cv.doc.layers.filter(l=>l.visible).map(l=>`<div class="canvas-layer ${l.id===cv.selected?'selected':''} ${l.locked?'locked':''}" data-layer="${esc(l.id)}" style="left:${l.x}px;top:${l.y}px;width:${l.w}px;height:${l.h}px;transform:rotate(${l.rotation}deg);opacity:${l.opacity}">${l.kind==='image'?`<img src="${cv.images.has(l.source_id)?esc(mediaURL(cv.sources.get(l.source_id))):''}" alt="${esc(l.name)}" draggable="false">`:`<div class="canvas-text" style="font:${l.font_size}px/${1.2} ${l.font};color:${l.color}">${esc(l.text)}</div>`}${l.id===cv.selected&&!l.locked?['nw','ne','se','sw'].map(k=>`<i class="canvas-handle ${k}" data-handle="${k}"></i>`).join(''):''}</div>`).join('');
 $('cv-empty').hidden=!!cv.doc.layers.length;
 $('cv-layer-list').innerHTML=[...cv.doc.layers].reverse().map(l=>`<div class="canvas-layer-row ${l.id===cv.selected?'selected':''}"><button data-select="${esc(l.id)}" title="${esc(l.name)}">${l.kind==='text'?'T':'▧'} ${esc(l.name)}</button><button data-visible="${esc(l.id)}" aria-label="${l.visible?'Hide':'Show'} ${esc(l.name)}" title="Visibility">${l.visible?'◉':'○'}</button><button data-lock="${esc(l.id)}" aria-label="${l.locked?'Unlock':'Lock'} ${esc(l.name)}" title="Lock">${l.locked?'🔒':'◇'}</button></div>`).join('')||'<p class="notice">No layers yet.</p>';
 $('cv-layer-list').querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>{cv.selected=b.dataset.select;cvRender();});
 for(const key of ['visible','lock'])$('cv-layer-list').querySelectorAll('[data-'+key+']').forEach(b=>b.onclick=()=>{cvPush();const l=cv.doc.layers.find(x=>x.id===b.dataset[key]);if(key==='visible')l.visible=!l.visible;else l.locked=!l.locked;cvChanged();});
 cvProperties();const layer=cvSelected(),editable=!!layer&&!layer.locked;
 for(const key of ['up','down','duplicate','remove'])$('cv-'+key).disabled=!editable;
 $('cv-up').disabled=!editable||cv.doc.layers.at(-1)===layer;$('cv-down').disabled=!editable||cv.doc.layers[0]===layer;
 $('cv-undo').disabled=!cv.history.length;$('cv-redo').disabled=!cv.future.length;cvTransform();
}
function cvProperties(){
 const l=cvSelected(),box=$('cv-properties');if(!l){box.innerHTML='<p class="notice">Select a layer to change it.</p>';return;}
 box.innerHTML=`<fieldset ${l.locked?'disabled':''}>${f('cv-layer-name','Name',`<input id="cv-layer-name" maxlength="200" value="${esc(l.name)}">`,'canvasLayer')}<div class="two">${['x','y','w','h','rotation','opacity'].map(k=>f('cv-prop-'+k,({x:'X',y:'Y',w:'Width',h:'Height',rotation:'Rotation °',opacity:'Opacity'})[k],num('cv-prop-'+k,Math.round(l[k]*100)/100,k==='opacity'?0:k==='w'||k==='h'?1:k==='rotation'?-360:-32768,k==='opacity'?1:k==='rotation'?360:32768,k==='opacity'?.05:.1),'canvasLayer')).join('')}</div><label class="check"><input id="cv-ratio" type="checkbox" ${cv.keepRatio!==false?'checked':''}>Keep proportions ${q('canvasLayer')}</label>${l.kind==='text'?`${f('cv-text-value','Text',`<textarea id="cv-text-value" maxlength="2000">${esc(l.text)}</textarea>`,'canvasLayer')}${f('cv-font-size','Font size',num('cv-font-size',l.font_size,1,2048,1),'canvasLayer')}${f('cv-font','Font',sel('cv-font',[['sans-serif','Sans serif'],['serif','Serif'],['monospace','Monospace']]),'canvasLayer')}${f('cv-color','Text color',`<input id="cv-color" type="color" value="${l.color}">`,'canvasLayer')}`:''}${f('cv-caption','MOSS description',`<textarea id="cv-caption" maxlength="1000" placeholder="Describe this element">${esc(l.caption)}</textarea>`,'canvasMoss')}</fieldset>`;
 if(l.kind==='text')$('cv-font').value=l.font;
 $('cv-ratio').onchange=()=>cv.keepRatio=$('cv-ratio').checked;
 const properties={...Object.fromEntries(['x','y','w','h','rotation','opacity'].map(k=>['cv-prop-'+k,k])),'cv-layer-name':'name','cv-caption':'caption','cv-text-value':'text','cv-font-size':'font_size','cv-font':'font','cv-color':'color'};
 for(const [id,key] of Object.entries(properties)){const input=$(id);if(!input)continue;input.onchange=()=>{let value=input.type==='number'?Number(input.value):input.value;if(input.type==='number'&&(!Number.isFinite(value)||value<Number(input.min)||value>Number(input.max))){notify('Choose a value within the displayed limits.');cvRender();return;}cvPush();if((key==='w'||key==='h')&&cv.keepRatio!==false){const other=key==='w'?'h':'w';l[other]=Math.max(1,Math.min(32768,l[other]*value/l[key]));}l[key]=value;cvChanged();};}
}
function cvTransform(){const v=$('cv-viewport'),dpr=1/cv.zoom;$('cv-board').style.transform=`translate(${cv.pan.x}px,${cv.pan.y}px) scale(${cv.zoom})`;v.style.setProperty('--cv-handle',8*dpr+'px');v.style.setProperty('--cv-line',dpr+'px');$('cv-zoom').textContent=Math.round(cv.zoom*100)+'%';}
function cvFit(){if($('page-canvas').hidden)return;const r=$('cv-viewport').getBoundingClientRect();if(r.width<1||r.height<1)return;cv.zoom=Math.max(.03,Math.min(3,(r.width-64)/cv.doc.width,(r.height-64)/cv.doc.height));cv.pan={x:(r.width-cv.doc.width*cv.zoom)/2,y:(r.height-cv.doc.height*cv.zoom)/2};cvTransform();}
function cvZoom(factor,at){const r=$('cv-viewport').getBoundingClientRect(),p=at||{x:r.width/2,y:r.height/2},old=cv.zoom;cv.zoom=Math.max(.02,Math.min(8,old*factor));cv.pan.x=p.x-(p.x-cv.pan.x)*cv.zoom/old;cv.pan.y=p.y-(p.y-cv.pan.y)*cv.zoom/old;cvTransform();}
function cvPoint(event){const r=$('cv-viewport').getBoundingClientRect();return {x:(event.clientX-r.left-cv.pan.x)/cv.zoom,y:(event.clientY-r.top-cv.pan.y)/cv.zoom};}
function cvUndo(redo=false){const from=redo?cv.future:cv.history,to=redo?cv.history:cv.future;if(!from.length)return;to.push(cvSnapshot());cv.doc=JSON.parse(from.pop());cv.selected=cv.doc.layers.some(x=>x.id===cv.selected)?cv.selected:null;cvChanged();cvLoadSources().then(cvRender);}
async function cvImage(item){
 cv.sources.set(item.id,item);if(cv.images.has(item.id))return cv.images.get(item.id);
 const pixels=[...cv.images.keys()].reduce((sum,id)=>sum+(cv.sources.get(id)?.width||0)*(cv.sources.get(id)?.height||0),0);
 if(pixels+item.width*item.height>100000000)throw Error('This canvas already uses 100 megapixels of source images. Save the project and start a new canvas, or remove unused images.');
 const image=new Image();image.src=mediaURL(item);await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Could not load '+item.name+'. Refresh the Library or choose another image.'));});cv.images.set(item.id,image);return image;
}
async function cvLoadSources(){const used=new Set(cv.doc.layers.filter(l=>l.kind==='image').map(l=>l.source_id));for(const id of cv.images.keys())if(!used.has(id))cv.images.delete(id);for(const id of used){const item=cv.sources.get(id);if(!item)continue;try{await cvImage(item);}catch(e){cvStatus(e.message);}}}
function cvLayer(kind){return {id:cvId(),kind,name:kind==='text'?'Text':'Image',caption:'',text:kind==='text'?'Your text':'',x:0,y:0,w:400,h:150,rotation:0,opacity:1,visible:true,locked:false,font_size:64,color:'#101820',font:'sans-serif'};}
function cvAdd(item,point){const result=(cv.addTail||Promise.resolve()).then(async()=>{await cvStart();const document=cv.doc;if(document.layers.length>=64)throw Error('Use up to 64 canvas layers.');await cvLoadSources();await cvImage(item);if(cv.doc!==document)return;cvPush();const ratio=Math.min(1,cv.doc.width*.75/item.width,cv.doc.height*.75/item.height),l={...cvLayer('image'),source_id:item.id,name:item.name,w:item.width*ratio,h:item.height*ratio};l.x=(point?.x??cv.doc.width/2)-l.w/2;l.y=(point?.y??cv.doc.height/2)-l.h/2;cv.doc.layers.push(l);cv.selected=l.id;cvChanged();});cv.addTail=result.catch(()=>{});return result;}
async function cvImport(files,point){
 if(cv.importing)return;cv.importing=true;const buttons=['cv-local'];buttons.forEach(id=>$(id).disabled=true);
 try{await cvStart();for(const file of files){if(cv.doc.layers.length>=64)throw Error('Use up to 64 canvas layers.');if(!/^image\/(png|jpeg|webp)$/.test(file.type)||file.size>25*1024**2)throw Error('Choose PNG, JPEG or WebP files up to 25 MB each.');cvStatus('Importing '+file.name+'…');const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read '+file.name));reader.readAsDataURL(file);});const result=await api('/api/canvas/import',{name:file.name,data:encoded});await cvAdd(result.item,point);}cvLibrary();}
 catch(e){notify(e.message);cvStatus(e.message);}finally{cv.importing=false;buttons.forEach(id=>$(id).disabled=false);}
}
async function cvLibrary(){
 const request=++cv.request;try{const result=await api(`/api/library?type=image&count=16&page=${cv.page}&search=${encodeURIComponent(cv.search)}`);if(request!==cv.request)return;
 $('cv-library').innerHTML=result.items.map(item=>`<button class="canvas-library-item" draggable="true" data-id="${esc(item.id)}" title="${esc(item.name)}"><img alt="${esc(item.name)}" data-thumbnail-id="${esc(item.id)}" data-thumb="${esc(thumbURL(item))}" loading="lazy" draggable="false"><span>${esc(item.name)}</span></button>`).join('')||'<small>No matching images.</small>';
 $('cv-library').querySelectorAll('[data-id]').forEach((button,i)=>{const item=result.items[i];cv.sources.set(item.id,item);button.onclick=()=>cvAdd(item).catch(e=>notify(e.message));button.ondragstart=event=>{event.dataTransfer.setData('application/x-studio-image',item.id);event.dataTransfer.effectAllowed='copy';};});thumbnails($('cv-library'),result.items);$('cv-count').textContent=`${cv.page+1} / ${Math.max(1,Math.ceil(result.total/16))}`;$('cv-prev').disabled=!cv.page;$('cv-next').disabled=(cv.page+1)*16>=result.total;
 }catch(e){cvStatus('Library: '+e.message);}
}
const canvasPreviousSendImage=sendImage;sendImage=function(item,target){if(target==='canvas'){showPage('canvas');cvAdd(item).catch(e=>notify(e.message));return;}return canvasPreviousSendImage(item,target);};
const canvasPreviousOpenMedia=openMedia;openMedia=function(item){canvasPreviousOpenMedia(item);if(item.media_type==='video')return;const button=document.createElement('button');button.textContent='Send to Canvas';button.onclick=()=>{sendImage(item,'canvas');$('media-dialog').close();};$('media-body').querySelector('.media-preview-column').append(button);};
function cvTextLines(ctx,text,width){const lines=[];for(const paragraph of text.split('\n')){let line='';for(const word of paragraph.split(/(\s+)/)){if(ctx.measureText(line+word).width<=width){line+=word;continue;}if(line){lines.push(line.trimEnd());line='';}for(const character of word){if(line&&ctx.measureText(line+character).width>width){lines.push(line);line='';}line+=character;}}lines.push(line.trimEnd());}return lines;}
async function cvExport(target){
 if(cv.exporting)return;cv.exporting=true;const ids=['cv-save-image','cv-editor','cv-video'];ids.forEach(id=>$(id).disabled=true);
 try{await cvLoadSources();const doc=structuredClone(cv.doc);for(const l of doc.layers)if(l.visible&&l.kind==='image'&&!cv.images.has(l.source_id))throw Error('A source image is missing: '+l.name+'. Remove or replace that layer before exporting.');
 const output=document.createElement('canvas');output.width=doc.width;output.height=doc.height;const ctx=output.getContext('2d');ctx.fillStyle=doc.background;ctx.fillRect(0,0,doc.width,doc.height);
 for(const l of doc.layers){if(!l.visible)continue;ctx.save();ctx.translate(l.x+l.w/2,l.y+l.h/2);ctx.rotate(l.rotation*Math.PI/180);ctx.globalAlpha=l.opacity;ctx.translate(-l.w/2,-l.h/2);ctx.beginPath();ctx.rect(0,0,l.w,l.h);ctx.clip();if(l.kind==='image')ctx.drawImage(cv.images.get(l.source_id),0,0,l.w,l.h);else{ctx.font=`${l.font_size}px ${l.font}`;ctx.fillStyle=l.color;ctx.textBaseline='top';cvTextLines(ctx,l.text,l.w).forEach((line,i)=>ctx.fillText(line,0,i*l.font_size*1.2));}ctx.restore();}
 const encoded=output.toDataURL('image/png');output.width=output.height=1;if(encoded.length>Math.floor(25*1024**2*4/3))throw Error('This PNG exceeds 25 MB. Use a smaller artboard to export it.');
 cvStatus('Saving composition…');const result=await api('/api/canvas/export',{name:doc.name+'.png',data:encoded,project:doc});cvStatus('Composition saved to Library.');notify('Composition saved to Library.');cvLibrary();if(target)sendImage(result.item,target);
 }catch(e){cvStatus('Export failed: '+e.message);notify(e.message);}finally{cv.exporting=false;ids.forEach(id=>$(id).disabled=false);}
}
function cvMoss(){
 const visible=cv.doc.layers.filter(l=>l.visible&&l.opacity>0);if(!visible.length||visible.length>24){notify('Use between 1 and 24 visible layers for a MOSS layout.');return;}
 const layout=[];for(const l of visible){const angle=l.rotation*Math.PI/180,w=Math.abs(l.w*Math.cos(angle))+Math.abs(l.h*Math.sin(angle)),h=Math.abs(l.w*Math.sin(angle))+Math.abs(l.h*Math.cos(angle)),left=Math.max(0,l.x+l.w/2-w/2),top=Math.max(0,l.y+l.h/2-h/2),right=Math.min(cv.doc.width,l.x+l.w/2+w/2),bottom=Math.min(cv.doc.height,l.y+l.h/2+h/2);if(right<=left||bottom<=top)continue;
 if((right-left)/cv.doc.width*100<.1||(bottom-top)/cv.doc.height*100<.1){notify('Enlarge or hide '+l.name+'. MOSS layout elements need at least 0.1% of the artboard in each dimension.');return;}
 if(l.kind==='text'&&l.text.length>1000){notify('Shorten '+l.name+' to 1,000 characters or fewer for a MOSS layout.');return;}
 layout.push({type:l.kind==='text'?'text':'object',caption:l.caption||l.name,text:l.kind==='text'?l.text:'',palette:l.kind==='text'?l.color:'',x:left/cv.doc.width*100,y:top/cv.doc.height*100,w:(right-left)/cv.doc.width*100,h:(bottom-top)/cv.doc.height*100});}
 if(!layout.length){notify('Move at least one layer onto the artboard.');return;}
 if(!isMoss('i')){$('imodel').value='moss_sft';applyModel('i');}
 const scale=Math.min(1,Math.sqrt(4000000/(cv.doc.width*cv.doc.height)),4096/Math.max(cv.doc.width,cv.doc.height));$('iwidth').value=Math.max(256,Math.floor(cv.doc.width*scale/16)*16);$('iheight').value=Math.max(256,Math.floor(cv.doc.height*scale/16)*16);
 // Very narrow artboards need an extra cap after the 256-pixel minimum.
 if(Number($('iwidth').value)*Number($('iheight').value)>4000000){if(Number($('iwidth').value)>Number($('iheight').value))$('iwidth').value=Math.floor(4000000/Number($('iheight').value)/16)*16;else $('iheight').value=Math.floor(4000000/Number($('iwidth').value)/16)*16;}
 $('ishape').value='custom';$('i-size').hidden=false;mossRestore('i',{...mossRead('i'),prompt_mode:'layout',layout});showPage('images');notify('MOSS layout is ready. Review captions and settings, then add it to the queue.');
}
const viewport=$('cv-viewport');
viewport.addEventListener('pointerdown',event=>{
 if(event.button!==0&&event.button!==1)return;viewport.focus();const point=cvPoint(event);
 if(event.button===1||cv.space){cv.drag={mode:'pan',x:event.clientX,y:event.clientY,pan:{...cv.pan}};event.preventDefault();}
 else{const node=event.target.closest('[data-layer]'),layer=cv.doc.layers.find(l=>l.id===node?.dataset.layer);cv.selected=layer?.id||null;const handle=event.target.dataset.handle;
 if(layer&&!layer.locked){cv.drag={mode:handle?'resize':'move',point,layer:structuredClone(layer),handle,before:cvSnapshot(),changed:false};event.preventDefault();}cvRender();}
 if(cv.drag)viewport.setPointerCapture(event.pointerId);
});
viewport.addEventListener('pointermove',event=>{
 const drag=cv.drag;if(!drag)return;if(drag.mode==='pan'){cv.pan.x=drag.pan.x+event.clientX-drag.x;cv.pan.y=drag.pan.y+event.clientY-drag.y;cvTransform();return;}
 const point=cvPoint(event),l=cvSelected(),start=drag.layer;if(!l)return;
 if(drag.mode==='move'){l.x=Math.max(-32768,Math.min(32768,start.x+point.x-drag.point.x));l.y=Math.max(-32768,Math.min(32768,start.y+point.y-drag.point.y));}
 else{const sx=drag.handle.includes('e')?1:-1,sy=drag.handle.includes('s')?1:-1,angle=start.rotation*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle),ax=start.x+start.w/2-c*sx*start.w/2+s*sy*start.h/2,ay=start.y+start.h/2-s*sx*start.w/2-c*sy*start.h/2,dx=point.x-ax,dy=point.y-ay;let w=Math.max(1,Math.min(32768,(c*dx+s*dy)*sx)),h=Math.max(1,Math.min(32768,(-s*dx+c*dy)*sy));if(event.shiftKey||cv.keepRatio!==false){const ratio=start.w/start.h;if(w/h>ratio)h=w/ratio;else w=h*ratio;const cap=Math.min(1,32768/w,32768/h);w*=cap;h*=cap;}l.w=w;l.h=h;l.x=Math.max(-32768,Math.min(32768,ax+c*sx*w/2-s*sy*h/2-w/2));l.y=Math.max(-32768,Math.min(32768,ay+s*sx*w/2+c*sy*h/2-h/2));}
 drag.changed=true;cvRender();
});
function cvFinish(){if(cv.drag?.changed){cvPush(cv.drag.before);cvChanged();}cv.drag=null;}
viewport.addEventListener('pointerup',cvFinish);viewport.addEventListener('pointercancel',cvFinish);viewport.addEventListener('lostpointercapture',cvFinish);
viewport.addEventListener('wheel',event=>{event.preventDefault();const r=viewport.getBoundingClientRect();cvZoom(Math.exp(-event.deltaY*.0015),{x:event.clientX-r.left,y:event.clientY-r.top});},{passive:false});
viewport.addEventListener('dragover',event=>{if([...event.dataTransfer.types].some(t=>t==='Files'||t==='application/x-studio-image')){event.preventDefault();viewport.classList.add('dragover');event.dataTransfer.dropEffect='copy';}});
viewport.addEventListener('dragleave',event=>{if(!viewport.contains(event.relatedTarget))viewport.classList.remove('dragover');});
viewport.addEventListener('drop',event=>{event.preventDefault();viewport.classList.remove('dragover');const point=cvPoint(event),id=event.dataTransfer.getData('application/x-studio-image');if(event.dataTransfer.files.length)cvImport([...event.dataTransfer.files],point);else if(cv.sources.has(id))cvAdd(cv.sources.get(id),point).catch(e=>notify(e.message));});
// Stop a file drop outside the artboard from navigating away from Studio.
document.addEventListener('dragover',e=>{if(current==='canvas'&&[...e.dataTransfer.types].includes('Files'))e.preventDefault();});
document.addEventListener('drop',e=>{if(current==='canvas'&&e.dataTransfer.files.length)e.preventDefault();});
document.addEventListener('keydown',event=>{if(current!=='canvas'||event.target.closest('input,textarea,select,dialog'))return;if(event.code==='Space'){cv.space=true;event.preventDefault();}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();cvUndo(event.shiftKey);}else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='y'){event.preventDefault();cvUndo(true);}else if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();$('cv-remove').click();}else if(event.key==='Escape'){cv.selected=null;cvRender();}});
document.addEventListener('keyup',event=>{if(event.code==='Space')cv.space=false;});window.addEventListener('blur',()=>{cv.space=false;cvFinish();});
$('cv-undo').onclick=()=>cvUndo();$('cv-redo').onclick=()=>cvUndo(true);$('cv-fit').onclick=cvFit;$('cv-zoom-in').onclick=()=>cvZoom(1.25);$('cv-zoom-out').onclick=()=>cvZoom(.8);
$('cv-local').onclick=()=>$('cv-files').click();$('cv-files').onchange=()=>{cvImport([...$('cv-files').files]);$('cv-files').value='';};
$('cv-text').onclick=()=>{if(cv.doc.layers.length>=64){notify('Use up to 64 layers.');return;}cvPush();const l=cvLayer('text');l.x=(cv.doc.width-l.w)/2;l.y=(cv.doc.height-l.h)/2;cv.doc.layers.push(l);cv.selected=l.id;cvChanged();};
$('cv-remove').onclick=()=>{const l=cvSelected();if(!l||l.locked)return;cvPush();cv.doc.layers=cv.doc.layers.filter(x=>x.id!==l.id);cv.selected=null;cvChanged();cvLoadSources();};
$('cv-duplicate').onclick=()=>{const l=cvSelected();if(!l||l.locked||cv.doc.layers.length>=64)return;cvPush();const copy={...l,id:cvId(),name:(l.name+' copy').slice(0,200),x:Math.min(32768,l.x+20),y:Math.min(32768,l.y+20)};cv.doc.layers.splice(cv.doc.layers.indexOf(l)+1,0,copy);cv.selected=copy.id;cvChanged();};
for(const [id,direction] of [['up',1],['down',-1]])$('cv-'+id).onclick=()=>{const l=cvSelected(),index=cv.doc.layers.indexOf(l),next=index+direction;if(!l||l.locked||next<0||next>=cv.doc.layers.length)return;cvPush();[cv.doc.layers[index],cv.doc.layers[next]]=[cv.doc.layers[next],cv.doc.layers[index]];cvChanged();};
$('cv-name').onchange=()=>{const name=$('cv-name').value.trim();if(!name){cvRender();return;}cvPush();cv.doc.name=name;cvChanged();};
function cvDimensions(w,h){if(!Number.isInteger(w)||!Number.isInteger(h)||w<64||h<64||w>8192||h>8192||w*h>16777216){notify('Use dimensions from 64 to 8192, with up to 16,777,216 pixels total.');cvRender();return;}cvPush();cv.doc.width=w;cv.doc.height=h;cvChanged();cvFit();}
$('cv-size').onchange=()=>{if($('cv-size').value!=='custom')cvDimensions(...$('cv-size').value.split('x').map(Number));};
for(const key of ['width','height'])$('cv-'+key).onchange=()=>cvDimensions(Number($('cv-width').value),Number($('cv-height').value));
$('cv-background').onchange=()=>{cvPush();cv.doc.background=$('cv-background').value;cvChanged();};
$('cv-library-refresh').onclick=cvLibrary;$('cv-prev').onclick=()=>{cv.page--;cvLibrary();};$('cv-next').onclick=()=>{cv.page++;cvLibrary();};$('cv-search').oninput=()=>{clearTimeout(cv.searchTimer);cv.searchTimer=setTimeout(()=>{cv.page=0;cv.search=$('cv-search').value;cvLibrary();},250);};
$('cv-save-image').onclick=()=>cvExport();$('cv-editor').onclick=()=>cvExport('editor');$('cv-video').onclick=()=>cvExport('video');$('cv-moss').onclick=cvMoss;
$('cv-save-project').onclick=async()=>{const document=cv.doc;try{const result=await api('/api/canvas/project',{project:structuredClone(document)});if(cv.doc===document){cv.doc.id=result.project.id;cvChanged();cvStatus('Project saved. Your draft also saves automatically.');}notify('Canvas project saved.');}catch(e){notify(e.message);}};
$('cv-new').onclick=()=>{cvPush();cv.doc=cvFresh();cv.selected=null;cv.images.clear();cvChanged();cvFit();};
$('cv-open-project').onclick=async()=>{try{const result=await api('/api/canvas/projects');$('cv-project-list').innerHTML=result.items.map(item=>`<button class="canvas-project-choice" data-project="${esc(item.id)}"><strong>${esc(item.name)}</strong><small>${item.width} × ${item.height} · ${item.layers} layers · ${esc(item.updated)}</small></button>`).join('')||'<p>No saved projects yet. Use Save project to keep this composition.</p>';$('cv-project-list').querySelectorAll('[data-project]').forEach(button=>button.onclick=async()=>{try{const result=await api('/api/canvas/project/'+button.dataset.project);cvPush();cv.doc=result.project;cv.selected=null;cv.images.clear();for(const item of result.sources)cv.sources.set(item.id,item);await cvLoadSources();cvChanged();cvFit();$('cv-project-dialog').close();}catch(e){notify(e.message);}});$('cv-project-dialog').showModal();}catch(e){notify(e.message);}};
new ResizeObserver(()=>{if(current==='canvas')cvFit();}).observe(viewport);
cvRender();
