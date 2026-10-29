'use strict';
Object.assign(help,{
 queue:['Generation queue','Jobs run one at a time. Add images, edits, videos or enhancement passes while another job runs. Pause stops new jobs from starting; it lets the current one finish. Unfinished jobs reopen paused. Failed jobs keep their error in queue history. With “Continue after failed jobs” enabled, the next waiting job runs; otherwise the queue pauses for review.'],
 continueOnError:['Continue after failed jobs','If a job fails validation, loading or processing, its error stays in history and the queue moves on to the next waiting job. Turn this off to pause at the first failure. Changing this option does not resume a paused queue. Jobs remain paused after reopening until you click Resume queue.'],
 priority:['Queue priority','Higher numbers run first among waiting jobs (0–10). Equal priorities use their displayed order. Priority never interrupts a running job. Up/down moves jobs within the same priority. Editing a waiting job pauses the queue.'],
 autoEnhance:['Enhance after generation','When enabled, the original is saved first, followed by a separate enhancement pass. Images use Qwen 2.1 and Elusarca’s detail LoRA; video uses NVIDIA RTX VSR. Install the optional components in Models. Options come from the Upscale page and are copied into each queued job.'],
 enhanceSource:['Enhancement source','Choose a Library item, or use Local file to import a PNG, JPEG or WebP image up to 25 MB and 25 megapixels. The imported copy is saved in the Library and selected here. Upscaling saves a separate result; the original file is kept. Images can be creatively changed by the detail model, so inspect the result.'],
 enhanceScale:['Enhancement scale','1 keeps approximately the original size; larger values increase dimensions. Image enhancement is capped at about four megapixels and 4096 pixels per axis, rounded to multiples of 32. RTX VSR supports 1–4× and rounds to multiples of 8. Video denoise/deblur modes keep the original dimensions.'],
 detailStrength:['Detail LoRA strength','Controls Elusarca’s Qwen 2.1 detail adapter. Start at 1; lower it for a gentler effect. Values above 1 (up to 2) strengthen the effect and may change details more. Zero disables its weight changes while keeping the Qwen enhancement pass. Other enabled Qwen 2.1 LoRAs are also applied.'],
 vsrQuality:['RTX quality','HIGHBITRATE modes suit clean generated video. STREAMING modes target compression artifacts. DEBLUR and DENOISE modes keep the input size. Higher quality can take longer. This applies NVIDIA’s VFX model; it does not create extra motion frames.'],
 vsrStrength:['RTX effect strength','Effect intensity, from 0 to 1. The preprocessing strength controls only the optional first pass; main strength controls the selected quality mode.'],
 vsrPreprocess:['Preprocessing','Optionally denoise or deblur each source frame before its main upscale pass. None uses only the selected main effect. An extra pass takes more time.'],
 vsrChunks:['Frames per segment','Temporary disk segments bound memory use. Smaller chunks reduce peak RAM but create more files. Start at 48; range 4–240. Originals and audio are preserved by the upstream pipeline.'],
 vsrEncoder:['Output encoding','H.264 NVENC uses NVIDIA hardware and supports up to 4096 pixels per axis. HEVC NVENC allows larger supported outputs, but playback support varies. CPU H.264 is slower. The selected FFmpeg binary must support the encoder; there is no silent fallback.'],
 uninstall:['Uninstall model','Review exactly which downloaded weights will be removed and how much space they use. Shared files needed by other installed models are kept. LoRAs, runtime software, settings and library media remain. Cancel or finish queued jobs referencing this model first.']
});
pages.queue=['Queue','Arrange, edit and cancel waiting jobs. Images, edits, videos and enhancement passes run one at a time.'];
pages.upscale=['Upscale','Enhance a Library image or video, or import a local image, and save a separate result.'];
document.querySelector('#navigation [data-page="video"]').insertAdjacentHTML('afterend','<button data-page="upscale">Upscale</button>');
$('navigation').insertAdjacentHTML('beforeend','<button data-page="queue">Queue <span id="queue-count"></span></button>');
$('pages').insertAdjacentHTML('beforeend',`
<section id="page-queue" class="page" hidden><div class="queue-workspace"><div class="row queue-toolbar"><button id="queue-toggle" class="primary">Pause queue</button>${q('queue')}<span id="queue-status" class="muted"></span><label class="check"><input id="queue-continue-errors" type="checkbox" checked>Continue after failed jobs ${q('continueOnError')}</label><button id="queue-cancel-all">Cancel unfinished</button><button id="queue-clear">Clear history</button></div><div id="queue-list" class="queue-list"></div></div></section>
<section id="page-upscale" class="page" hidden><div class="workspace"><form id="upscale-form" class="controls"><div class="control-scroll">
${f('enhance-kind','Media type',sel('enhance-kind',[['image','Image · Qwen 2.1 Detail Enhancer'],['video','Video · NVIDIA RTX VSR']]),'autoEnhance')}
<div class="field"><div class="row">Library source ${q('enhanceSource')}</div><p id="enhance-source" class="notice" role="status">No source selected.</p></div><div class="row"><button type="button" id="enhance-library">Choose in Library</button><button type="button" id="enhance-local-file" data-import="upscale">Local file</button></div><p id="enhance-ready" class="notice"></p>
<fieldset id="image-enhance-controls">${f('ui-scale','Scale',num('ui-scale',2,1,4,.25),'enhanceScale')}${f('ui-detail_strength','Detail LoRA strength',num('ui-detail_strength',1,0,2,.05),'detailStrength')}${f('ui-prompt','Enhancement instruction','<textarea id="ui-prompt" maxlength="10000"></textarea>','prompt')}<details><summary>Advanced image enhancement</summary>${f('ui-negative','Negative prompt','<textarea id="ui-negative" maxlength="10000"></textarea>','negative')}<div class="two">${f('ui-steps','Steps',num('ui-steps',25,1,60),'steps')}${f('ui-cfg','Prompt strength',num('ui-cfg',1,1,15,.1),'cfg')}</div>${seedControls('ui-')}${f('ui-memory','Memory mode',sel('ui-memory',[['auto','Automatic'],['low','Low VRAM']]),'memory')}<button type="button" id="enhance-loras">Manage Qwen 2.1 LoRAs</button></details></fieldset>
<fieldset id="video-enhance-controls" hidden>${f('uv-scale','Scale',num('uv-scale',2,1,4,.25),'enhanceScale')}${f('uv-quality','Quality','<select id="uv-quality"></select>','vsrQuality')}${f('uv-strength','Effect strength',num('uv-strength',1,0,1,.05),'vsrStrength')}${f('uv-preprocess','Preprocessing','<select id="uv-preprocess"></select>','vsrPreprocess')}<details><summary>Advanced video enhancement</summary>${f('uv-preprocess_strength','Preprocessing strength',num('uv-preprocess_strength',1,0,1,.05),'vsrStrength')}${f('uv-frames_per_chunk','Frames per segment',num('uv-frames_per_chunk',48,4,240,4),'vsrChunks')}${f('uv-encoder','Output encoding',sel('uv-encoder',[['h264_nvenc','H.264 · NVIDIA'],['hevc_nvenc','HEVC · NVIDIA'],['libx264','H.264 · CPU']]),'vsrEncoder')}</details></fieldset>
${f('upscale-priority','Queue priority',num('upscale-priority',5,0,10),'priority')}<button type="button" id="save-enhance-defaults" data-job>Save enhancement defaults</button>
</div><div class="control-footer"><button type="submit" class="primary" id="upscale-submit">Add to queue</button></div></form><div class="preview"><div class="preview-heading"><span>Source preview</span><span id="enhance-dimensions"></span></div><div id="enhance-preview" class="preview-stage"><div class="empty-state">Choose an image or video from the library.</div></div><div class="notice">Enhanced copies and originals remain available in Library. Enable “Enhance after generation” in a generator to apply these options automatically.</div></div></div></section>`);
document.body.insertAdjacentHTML('beforeend',`<dialog id="uninstall-dialog"><div class="dialog-heading"><h2>Uninstall model</h2><button data-close aria-label="Close uninstall preview">×</button></div><div id="uninstall-summary"></div><div class="row" style="margin-top:18px"><button data-close>Keep model</button><button id="uninstall-confirm" class="danger" data-job>Uninstall weights</button></div></dialog>`);
let editingQueue=null,enhanceSource=null,toolsInitialized=false,queueSignature='',enhanceSourceSignature='',removalPreview=null;
for(const p of ['i','e','v']){
 const form=$(p==='i'?'image-form':p==='e'?'edit-form':'video-form');
 const controls=p==='e'?$('ai-edit-controls'):form.querySelector('.control-scroll');
 controls.insertAdjacentHTML('beforeend',`<details class="queue-options"><summary>Queue & enhancement ${q('queue')}</summary>${f(p+'priority','Queue priority',num(p+'priority',5,0,10),'priority')}<label class="check"><input id="${p}enhance" type="checkbox">Enhance after generation ${q('autoEnhance')}</label><button type="button" data-enhance-settings="${p==='v'?'video':'image'}">Enhancement options</button></details>`);
 form.insertAdjacentHTML('afterbegin',`<div id="${p}-queue-edit" class="queue-edit-banner" hidden>Editing a waiting job <button type="button" data-exit-queue-edit>Cancel editing</button></div>`);
 const submit=form.querySelector('[type=submit]')||form.querySelector('.control-footer button');submit.removeAttribute('data-job');submit.disabled=false;submit.textContent='Add to queue';
}
function enhancementPreset(kind){const p=kind==='image'?'ui-':'uv-',keys=Object.keys(kind==='image'?state.enhancers.image_defaults:state.enhancers.video_defaults);const o=Object.fromEntries(keys.map(k=>[k,$(p+k).type==='checkbox'?$(p+k).checked:$(p+k).value]));if(kind==='image')o.loras=savedLoras('qwen21');return o;}
function fillEnhancement(kind,options){if(!options)return;const p=kind==='image'?'ui-':'uv-';for(const [k,v] of Object.entries(options)){const input=$(p+k);if(input){if(input.type==='checkbox')input.checked=v;else input.value=v;}}}
function generationOptions(p){const o=values(p),kind=p==='v'?'video':'image';o.priority=Number($(p+'priority').value);o.upscale={enabled:$(p+'enhance').checked};if(o.upscale.enabled)o.upscale.options=enhancementPreset(kind);if(editingQueue&&editingQueue.kind===({i:'image',e:'edit',v:'video'}[p])){if(o.model===editingQueue.model)o.loras=editingQueue.loras;if(o.upscale.enabled&&kind==='image'&&editingQueue.upscaleLoras)o.upscale.options.loras=editingQueue.upscaleLoras;}return o;}
async function refreshTools(){state=await api('/api/state');renderTools();}
async function submitQueue(kind,options,priority){if(editingQueue){if(editingQueue.kind!==kind){notify('Finish or cancel the current queue edit first.');return;}await action('/api/queue/action',{action:'update',id:editingQueue.id,options,priority});exitQueueEdit();notify('Queue job updated. Resume the queue when ready.');}else{await action('/api/queue/add',{kind,options,priority});const p={image:'i',edit:'e',video:'v',enhance_image:'ui-',faceswap:'f'}[kind];if(p)advanceSeed(p,options.seed);if(options.upscale?.enabled&&kind!=='video')advanceSeed('ui-',options.upscale.options?.seed);notify('Added to queue.');}await refreshTools();}
$('image-form').onsubmit=async e=>{e.preventDefault();const o=generationOptions('i');await submitQueue('image',o,o.priority).catch(()=>{});};
$('video-form').onsubmit=async e=>{e.preventDefault();const o={...generationOptions('v'),mode:$('vmode').value,source_image:$('vmode').value==='image'?(videoSource?.id||''):'',frames:$('vframes').value==='custom'?$('vframecount').value:$('vframes').value,fps:$('vfps').value,shift:$('vshift').value,sampler:$('vsampler').value,scheduler:$('vscheduler').value,audio:$('vaudio').checked};await submitQueue('video',o,o.priority).catch(()=>{});};
$('edit-form').onsubmit=async e=>{e.preventDefault();if(!editorSource){notify('Choose a starting image first.');return;}if($('etool').value==='crop'){const o={id:editorSource.id};for(const [key,id] of [['x','crop-x'],['y','crop-y'],['crop_width','crop-w'],['crop_height','crop-h'],['width','resize-w'],['height','resize-h']])o[key]=$(id).value;await action('/api/images/crop',o).catch(()=>{});return;}const o={...generationOptions('e'),source_image:editorSource.id,references:references.map(x=>x.id),strength:$('estrength').value};if($('etool').value==='mask')o.mask=maskCanvas.toDataURL('image/png');await submitQueue('edit',o,o.priority).catch(()=>{});};
$('upscale-form').onsubmit=async e=>{e.preventDefault();if(!enhanceSource){notify('Choose a library source first.');return;}const kind=$('enhance-kind').value,o={...enhancementPreset(kind),source_id:enhanceSource.id};if(editingQueue?.kind==='enhance_image')o.loras=editingQueue.loras;await submitQueue('enhance_'+kind,o,Number($('upscale-priority').value)).catch(()=>{});};
function exitQueueEdit(){editingQueue=null;for(const p of ['i','e','v']){$(p+'-queue-edit').hidden=true;const form=$(p==='i'?'image-form':p==='e'?'edit-form':'video-form');form.querySelector('.control-footer button').textContent=p==='e'&&$('etool').value==='crop'?'Save crop / resize copy':'Add to queue';}$('upscale-submit').textContent='Add to queue';$('upscale-queue-edit').hidden=true;}
async function editQueueItem(id){await action('/api/queue/action',{action:'pause'});const item=await api('/api/queue/'+id);if(item.status!=='queued'){notify('This job has already started.');return;}const o=item.options;exitQueueEdit();editingQueue={id,kind:item.kind,model:o.model,loras:o.loras||[],upscaleLoras:o.upscale?.options?.loras};if(item.kind.startsWith('enhance_')){const kind=item.kind.split('_')[1];$('enhance-kind').value=kind;const source=item.sources.find(x=>x.id===o.source_id);enhanceSource=source?{...source,media_type:kind}:null;fillEnhancement(kind,o);$('upscale-priority').value=item.priority;$('upscale-submit').textContent='Save queue changes';$('upscale-queue-edit').hidden=false;enhanceSourceSignature='';updateEnhancementSource();showPage('upscale');return;}
 const p={image:'i',video:'v',edit:'e'}[item.kind];
 if(item.kind==='edit'){const source=item.sources.find(x=>x.id===o.source_image);if(!source)throw Error('Starting image is missing.');sendImage(source,'editor');references=o.references.map(id=>item.sources.find(x=>x.id===id)).filter(Boolean);$('etool').value=o.mask?'mask':'instruction';editorToolChanged();}
 fill(p,o);$(p+'priority').value=item.priority;$(p+'enhance').checked=!!o.upscale?.enabled;if(o.upscale?.options)fillEnhancement(item.kind==='video'?'video':'image',o.upscale.options);
 if(p==='v'){videoModelChanged(false);$('vaudio').checked=o.audio!==false;videoSource=item.sources.find(x=>x.id===o.source_image)||null;$('vmode').value=o.mode;$('video-source-controls').hidden=o.mode!=='image';const frames=String(o.frames);$('vframes').value=[...$('vframes').options].some(x=>x.value===frames)?frames:'custom';$('vframecount').value=frames;$('v-custom-frames').hidden=$('vframes').value!=='custom';updateDuration();}
 if(p==='i'||p==='v'){$(p+'shape').value='custom';$(p+'-size').hidden=false;}
 if(p==='e'){resetMask();if(o.mask){const img=new Image();img.onload=()=>{maskContext.drawImage(img,0,0,maskCanvas.width,maskCanvas.height);const overlay=maskContext.getImageData(0,0,maskCanvas.width,maskCanvas.height);for(let index=0;index<overlay.data.length;index+=4){const alpha=overlay.data[index]*.4;overlay.data[index]=53;overlay.data[index+1]=232;overlay.data[index+2]=220;overlay.data[index+3]=alpha;}paintContext.clearRect(0,0,paint.width,paint.height);paintContext.putImageData(overlay,0,0);};img.src=o.mask;}}
 $(p+'-queue-edit').hidden=false;$(p==='i'?'image-form':p==='e'?'edit-form':'video-form').querySelector('.control-footer button').textContent='Save queue changes';renderSources();showPage({i:'images',e:'editor',v:'video'}[p]);updateAvailability();await refreshTools();
}
function renderQueue(){const queue=state.queue;if(!queue)return;const signature=JSON.stringify(queue);$('queue-continue-errors').checked=queue.continue_on_error!==false;$('queue-count').textContent=queue.waiting?'('+queue.waiting+')':'';$('queue-toggle').textContent=queue.paused?'Resume queue':'Pause queue';$('queue-status').textContent=`${queue.paused?'Paused':'Automatic'} · ${queue.waiting} waiting`;
 if(signature===queueSignature)return;queueSignature=signature;
 $('queue-list').innerHTML=queue.jobs.length?queue.jobs.map(job=>{const waiting=job.status==='queued',running=job.status==='running';return `<article class="queue-card ${running?'running':''}"><div class="queue-job-copy"><div class="row"><strong>${esc(({image:'Image',video:'Video',edit:'Image edit',enhance_image:'Image enhancement',enhance_video:'Video enhancement',avatar:'Talking Avatar',faceswap:'Faceswap',faceswap_video:'Video faceswap',voice:'Voice'})[job.kind])}</strong><span class="badge">${esc(job.status)}</span><small>${esc(loraInfo(job.model)?.name||job.model)}</small></div><p>${esc(job.prompt||'Enhance a library source')}</p><small>${job.width?`${job.width} × ${job.height} · `:''}${esc(job.created)}${job.error?' · '+esc(job.error):''}</small></div><div class="queue-job-actions">${waiting?`${f('qp-'+job.id,'Priority',num('qp-'+job.id,job.priority,0,10),'priority')}<button data-queue-action="move" data-id="${job.id}" data-direction="up" aria-label="Move job up">↑</button><button data-queue-action="move" data-id="${job.id}" data-direction="down" aria-label="Move job down">↓</button><button data-queue-edit="${job.id}">Edit</button>`:`<span class="muted">Priority ${job.priority}</span>`}${waiting||running?`<button class="danger" data-queue-action="cancel" data-id="${job.id}">${job.cancel_requested?'Cancelling…':'Cancel'}</button>`:`<button data-queue-action="retry" data-id="${job.id}">Retry / copy</button>`}</div></article>`;}).join(''):'<div class="notice">No jobs yet. Add an image, edit, video or enhancement from its tool.</div>';
 for(const job of queue.jobs.filter(x=>x.status==='queued'))$('qp-'+job.id).onchange=async e=>{await action('/api/queue/action',{action:'update',id:job.id,priority:e.target.value}).catch(()=>{});await refreshTools();};
}
function setEnhancementSource(item,kind){enhanceSource={...item,media_type:kind};$('enhance-kind').value=kind;enhanceSourceSignature='';updateEnhancementSource();showPage('upscale');}
const beforeUpscaleSendImage=sendImage;
sendImage=function(item,target){if(target==='upscale'){setEnhancementSource(item,'image');return;}return beforeUpscaleSendImage(item,target);};
function updateEnhancementSource(){if(!toolsInitialized)return;const kind=$('enhance-kind').value;if(enhanceSource?.media_type!==kind)enhanceSource=null;
 $('enhance-source').textContent=enhanceSource?mediaTitle(enhanceSource):'No source selected.';$('enhance-source').title=enhanceSource?.name||'';
 $('enhance-local-file').hidden=kind!=='image';$('image-enhance-controls').hidden=kind!=='image';$('video-enhance-controls').hidden=kind!=='video';$('enhance-ready').textContent=state.enhancers[kind]?'Enhancement component installed.':'Install '+(kind==='image'?'Qwen 2.1 Detail Enhancer':'RTX video enhancement')+' in Models first.';
 if(enhanceSource&&$('enhance-preview').dataset.source!==enhanceSource.id){$('enhance-preview').dataset.source=enhanceSource.id;$('enhance-preview').innerHTML=kind==='video'?`<video controls preload="metadata" src="${mediaURL({...enhanceSource,media_type:'video'})}"></video>`:`<img src="${mediaURL(enhanceSource)}" alt="Enhancement source">`;}
 if(!enhanceSource&&($('enhance-preview').dataset.source!==''||!$('enhance-preview').querySelector('.empty-state'))){$('enhance-preview').dataset.source='';$('enhance-preview').innerHTML='<div class="empty-state">Choose a library image or video.</div>';}$('enhance-dimensions').textContent=enhanceSource?.width?`${enhanceSource.width} × ${enhanceSource.height}`:'';
}
function initTools(){if(toolsInitialized||!state?.enhancers)return;toolsInitialized=true;for(const [id,items] of [['uv-quality',state.enhancers.quality],['uv-preprocess',state.enhancers.preprocess]])$(id).innerHTML=items.map(x=>`<option value="${x}">${esc(x.replaceAll('_',' ').toLowerCase())}</option>`).join('');for(const kind of ['image','video'])fillEnhancement(kind,state.settings.enhancement_defaults?.[kind]||state.enhancers[kind+'_defaults']);for(const p of ['i','e','v'])$(p+'enhance').checked=false;initializeSeeds();updateEnhancementSource();}
function renderTools(){initTools();if(!toolsInitialized)return;renderQueue();updateEnhancementSource();if(!$('rtx-install-card'))$('pack-grid').insertAdjacentHTML('afterend',`<article class="pack" id="rtx-install-card" style="margin-top:16px"><h3>RTX video enhancement <span id="rtx-installed" class="badge"></span></h3><p>Optional NVIDIA VFX pass from tritant’s RTX VSR project. Uses temporary disk segments and keeps audio. Requires an RTX GPU and compatible NVIDIA driver.</p><button id="install-rtx" data-job>Install / repair RTX enhancement</button>${q('autoEnhance')}</article>`);$('rtx-installed').textContent=state.enhancers.video?'Installed':'Not installed';$('save-loras').disabled=state.busy&&!state.queue.jobs.some(x=>x.status==='running');$('install-rtx').disabled=state.busy;$('install-rtx').onclick=()=>action('/api/enhancers/install-video').catch(()=>{});const crop=$('etool').value==='crop';$('edit-save').disabled=crop&&state.busy;if(!editingQueue)$('edit-save').textContent=crop?'Save crop / resize copy':'Add to queue';}
$('enhance-kind').onchange=()=>{enhanceSource=null;enhanceSourceSignature='';updateEnhancementSource();};$('enhance-library').onclick=()=>showPage('library');$('enhance-loras').onclick=()=>openLoras('qwen21');
$('save-enhance-defaults').onclick=()=>action('/api/enhancers/defaults',{image:enhancementPreset('image'),video:enhancementPreset('video')}).then(()=>notify('Enhancement defaults saved.')).catch(()=>{});
$('queue-continue-errors').onchange=async e=>{await action('/api/queue/action',{action:'failure_policy',continue_on_error:e.target.checked}).catch(()=>{});await refreshTools();};
$('queue-toggle').onclick=async()=>{await action('/api/queue/action',{action:state.queue.paused?'resume':'pause'}).catch(()=>{});await refreshTools();};$('queue-clear').onclick=async()=>{await action('/api/queue/action',{action:'clear_finished'}).catch(()=>{});await refreshTools();};$('queue-cancel-all').onclick=async()=>{await action('/api/queue/action',{action:'cancel_all'}).catch(()=>{});await refreshTools();};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.queueAction){await action('/api/queue/action',{action:b.dataset.queueAction,id:b.dataset.id,direction:b.dataset.direction});await refreshTools();}if(b.dataset.queueEdit)await editQueueItem(b.dataset.queueEdit);if(b.hasAttribute('data-exit-queue-edit'))exitQueueEdit();if(b.dataset.enhanceSettings){$('enhance-kind').value=b.dataset.enhanceSettings;enhanceSourceSignature='';updateEnhancementSource();showPage('upscale');}if(b.dataset.uninstall){removalPreview=await action('/api/models/removal-plan',{model:b.dataset.uninstall});$('uninstall-summary').innerHTML=`<p><strong>${esc(removalPreview.name)}</strong></p><p>${(removalPreview.bytes/1024**3).toFixed(2)} GB in ${removalPreview.files.length} files will be removed.</p><ul>${removalPreview.files.map(x=>`<li>${esc(x.filename)}</li>`).join('')}</ul><p>Shared files kept:</p><ul>${removalPreview.shared.map(x=>`<li>${esc(x.filename)} · ${esc(x.used_by.join(', '))}</li>`).join('')||'<li>None required by another installed model.</li>'}</ul><p class="notice">Runtime software, LoRAs, settings, images and videos stay in place. Removed model weights can be downloaded again.</p>`;$('uninstall-confirm').disabled=state.busy||!removalPreview.files.length;$('uninstall-dialog').showModal();}}catch(error){notify(error.message);}});
$('uninstall-confirm').onclick=async()=>{if(!removalPreview)return;try{await action('/api/models/uninstall',{model:removalPreview.model,ticket:removalPreview.ticket});$('uninstall-dialog').close();}catch{}};
const imageViewer=$('image-viewer'),imageSpace=$('image-viewer-space'),viewerPicture=$('image-viewer-picture');
const imageView={scale:1,x:0,y:0,fit:1,drag:null,enteredFullscreen:false};
function renderImageView(){
 const w=imageSpace.clientWidth,h=imageSpace.clientHeight;
 const iw=viewerPicture.naturalWidth*imageView.scale,ih=viewerPicture.naturalHeight*imageView.scale;
 imageView.x=iw<=w?(w-iw)/2:Math.max(w-iw,Math.min(0,imageView.x));
 imageView.y=ih<=h?(h-ih)/2:Math.max(h-ih,Math.min(0,imageView.y));
 viewerPicture.style.transform=`translate(${imageView.x}px,${imageView.y}px) scale(${imageView.scale})`;
 $('image-zoom-level').textContent=`${Math.round(imageView.scale*100)}%`;
}
function fitImageView(){
 if(!imageViewer.open||!viewerPicture.naturalWidth)return;
 imageView.fit=Math.min(imageSpace.clientWidth/viewerPicture.naturalWidth,imageSpace.clientHeight/viewerPicture.naturalHeight);
 imageView.scale=imageView.fit;imageView.x=0;imageView.y=0;renderImageView();
}
function zoomImageView(scale,px=imageSpace.clientWidth/2,py=imageSpace.clientHeight/2){
 if(!viewerPicture.naturalWidth)return;
 const next=Math.max(Math.min(imageView.fit,1)/8,Math.min(Math.max(16,imageView.fit),scale));
 const ratio=next/imageView.scale;
 imageView.x=px-(px-imageView.x)*ratio;imageView.y=py-(py-imageView.y)*ratio;
 imageView.scale=next;renderImageView();
}
function openLibraryImage(item){
 imageView.drag=null;imageView.enteredFullscreen=false;
 $('image-viewer-name').textContent=mediaTitle(item);
 viewerPicture.style.visibility='hidden';
 viewerPicture.onload=()=>{if(imageViewer.open){fitImageView();viewerPicture.style.visibility='visible';}};
 viewerPicture.onerror=()=>{notify('This image could not be loaded. Check that its library file still exists.');imageViewer.close();};
 imageViewer.showModal();
 if(window.chrome?.webview)window.chrome.webview.postMessage('open-image-viewer');
 else if(!document.fullscreenElement&&document.documentElement.requestFullscreen){
  imageView.enteredFullscreen=true;
  document.documentElement.requestFullscreen().then(()=>{if(!imageViewer.open)document.exitFullscreen().catch(()=>{});}).catch(()=>{imageView.enteredFullscreen=false;});
 }
 viewerPicture.src=mediaURL(item);
}
imageSpace.addEventListener('wheel',e=>{
 e.preventDefault();const rect=imageSpace.getBoundingClientRect();
 const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?imageSpace.clientHeight:1);
 zoomImageView(imageView.scale*Math.exp(-Math.max(-1000,Math.min(1000,delta))*.0015),e.clientX-rect.left,e.clientY-rect.top);
},{passive:false});
imageSpace.onpointerdown=e=>{if(e.button!==0||!viewerPicture.naturalWidth)return;e.preventDefault();imageView.drag={id:e.pointerId,x:e.clientX,y:e.clientY,ox:imageView.x,oy:imageView.y};imageSpace.setPointerCapture(e.pointerId);imageSpace.classList.add('panning');};
imageSpace.onpointermove=e=>{const d=imageView.drag;if(!d||d.id!==e.pointerId)return;imageView.x=d.ox+e.clientX-d.x;imageView.y=d.oy+e.clientY-d.y;renderImageView();};
imageSpace.onpointerup=imageSpace.onpointercancel=imageSpace.onlostpointercapture=()=>{imageView.drag=null;imageSpace.classList.remove('panning');};
$('image-zoom-in').onclick=()=>zoomImageView(imageView.scale*1.25);
$('image-zoom-out').onclick=()=>zoomImageView(imageView.scale/1.25);
$('image-zoom-fit').onclick=fitImageView;
$('image-zoom-actual').onclick=()=>zoomImageView(1);
$('image-viewer-close').onclick=()=>imageViewer.close();
imageViewer.oncancel=e=>{e.preventDefault();imageViewer.close();};
imageViewer.onclose=()=>{
 imageView.drag=null;imageSpace.classList.remove('panning');viewerPicture.removeAttribute('src');
 if(window.chrome?.webview)window.chrome.webview.postMessage('close-image-viewer');
 else if(imageView.enteredFullscreen&&document.fullscreenElement)document.exitFullscreen().catch(()=>{});
 imageView.enteredFullscreen=false;
};
document.addEventListener('keydown',e=>{
 if(!imageViewer.open)return;
 if(e.key==='Escape'){
  e.stopImmediatePropagation();
  if(!$('help-dialog').open){e.preventDefault();imageViewer.close();}
 }else if(!$('help-dialog').open&&['+','=','-','0','1'].includes(e.key)){
  e.preventDefault();e.stopImmediatePropagation();
  if(e.key==='0')fitImageView();else if(e.key==='1')zoomImageView(1);else zoomImageView(imageView.scale*(e.key==='-'?.8:1.25));
 }
},true);
new ResizeObserver(fitImageView).observe(imageSpace);
document.addEventListener('fullscreenchange',()=>{if(imageViewer.open&&imageView.enteredFullscreen&&!document.fullscreenElement)imageViewer.close();});
const originalOpenMedia=openMedia;
openMedia=function(item){
 originalOpenMedia(item);
 if(item.kind==='enhanced')$('reuse-settings')?.remove();
 const preview=$('media-body').querySelector('.media-preview-column');
 if(item.media_type!=='video'){
  const picture=preview.querySelector('img.modal-media');
  picture.classList.add('zoomable');picture.tabIndex=0;picture.setAttribute('role','button');
  picture.setAttribute('aria-label','Open fullscreen image viewer');picture.title='Click to view fullscreen · Scroll to zoom';
  picture.onclick=()=>openLibraryImage(item);
  picture.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openLibraryImage(item);}};
 }
 const folderActions=document.createElement('div');
 folderActions.className='row';
 folderActions.innerHTML=`<button type="button" id="library-open-folder">Open containing folder</button>${q('libraryFolder')}`;
 const folderButton=folderActions.querySelector('#library-open-folder');
 folderButton.onclick=async()=>{
  folderButton.disabled=true;
  try{await action('/api/library/open-folder',{id:item.id});}catch{}finally{folderButton.disabled=false;}
 };
 preview.append(folderActions);
 const button=document.createElement('button');
 button.textContent='Upscale / enhance';
 button.onclick=()=>{$('media-dialog').close();setEnhancementSource(item,item.media_type==='video'?'video':'image');};
 preview.append(button);
};
$('upscale-form').insertAdjacentHTML('afterbegin','<div id="upscale-queue-edit" class="queue-edit-banner" hidden>Editing a waiting job <button type="button" data-exit-queue-edit>Cancel editing</button></div>');
const originalToolsLoraSave=$('save-loras').onclick;$('save-loras').onclick=async()=>{const model=$('lora-target').value;await originalToolsLoraSave();if(editingQueue){if(model===editingQueue.model)editingQueue.loras=savedLoras(model);if(model==='qwen21')editingQueue.upscaleLoras=savedLoras(model);}};
const originalToolsOpenLoras=openLoras;openLoras=function(model){originalToolsOpenLoras(model);if(editingQueue){const selected=model===editingQueue.model?editingQueue.loras:model==='qwen21'?editingQueue.upscaleLoras:null;if(selected){loraDrafts[model]=JSON.parse(JSON.stringify(selected));renderLoras(true);}}};
if(initialized)initTools();
