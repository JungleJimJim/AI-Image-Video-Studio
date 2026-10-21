'use strict';
Object.assign(help,{
 videoFace:['Video faceswap','FaceFusion with HyperSwap replaces a face across an existing video and keeps its motion, dimensions, frame rate and source audio. Choose a clear reference portrait with one face. Results are saved as separate Library videos. FaceFusion’s upstream content checks remain enabled. The image mode continues to use BFS head swap.'],
 videoPerson:['Person to replace','Track a selected person matches the face chosen in a reference frame, sorted largest to smallest. Face number 1 is the largest face in that frame. Largest face per frame can switch people when their sizes change. All detected faces replaces every detected face with the reference identity. Tracking can miss occluded or strongly turned faces.'],
 videoFaceFrame:['Tracking reference','Choose a frame number where the target person is clearly visible, then their face number (1 is largest). These identify the original person to replace, not your replacement portrait. Frame 0 is the first frame.'],
 videoFaceSimilarity:['Tracking tolerance','How different a detected face can be from the target person in the reference frame. Higher values match more faces but can include other people. Start at 0.6. Used only for Track a selected person.'],
 videoFaceQuality:['Face quality','256 is the native face resolution. 512 uses pixel boosting and takes longer. Output quality controls MP4 encoding, from 1 to 100. The original video dimensions are preserved.'],
 videoFaceCompute:['Processing device','NVIDIA CUDA uses the installed GPU. CPU is slower and can be used if CUDA is unavailable. Dependencies are installed separately from your image/video generators. No silent fallback changes the chosen device.'],
 videoFaceEncoder:['Video encoding','CPU H.264 is the default for broad compatibility. NVIDIA H.264 uses hardware encoding when supported by FFmpeg and your GPU. Audio is retained and encoded as AAC.']
});
pages.faceswap[1]='Swap a face in an image or video using a reference portrait. Save a separate result in Library.';
const faceScroll=$('face-form').querySelector('.control-scroll');
faceScroll.insertAdjacentHTML('afterbegin',`${f('face-media-mode','Media type',sel('face-media-mode',[['image','Image · BFS'],['video','Video · FaceFusion / HyperSwap']]),'videoFace')}`);
const imageFields=document.createElement('fieldset');imageFields.id='face-image-fields';
for(const child of [...faceScroll.children])if(child!==faceScroll.firstElementChild)imageFields.append(child);
faceScroll.append(imageFields);
faceScroll.insertAdjacentHTML('beforeend',`<fieldset id="face-video-fields" hidden disabled>
 <p id="video-face-ready" class="model-state"></p><button type="button" id="face-video-install">Install / repair video faceswap</button>
 <div class="field"><label>Target video ${q('videoFace')}</label><div id="face-video-target" class="notice">No video selected.</div><div class="row"><button type="button" data-pick="face-video">Library</button><button type="button" id="face-video-local">Local file</button></div></div>
 <div class="field"><label>Reference face ${q('videoFace')}</label><div id="face-video-reference" class="notice">No face selected.</div><div class="row"><button type="button" data-pick="face-video-reference">Library</button><button type="button" data-import="face-video-reference">Local file</button></div></div>
 ${f('fv-selector','Person to replace',sel('fv-selector',[['reference','Track a selected person'],['one','Largest face per frame'],['many','All detected faces']]),'videoPerson')}
 <div id="fv-tracking"><div class="two">${f('fv-face_position','Face number',num('fv-face_position',1,1,100,1),'videoFaceFrame')}${f('fv-reference_frame','Reference frame',num('fv-reference_frame',0,0,10000000,1),'videoFaceFrame')}</div>${f('fv-similarity','Tracking tolerance',num('fv-similarity',.6,0,1,.05),'videoFaceSimilarity')}</div>
 <details><summary>Quality & processing</summary>${f('fv-pixel_boost','Face resolution',sel('fv-pixel_boost',[['256x256','256 · standard'],['512x512','512 · pixel boost']]),'videoFaceQuality')}${f('fv-quality','Output quality',num('fv-quality',90,1,100,1),'videoFaceQuality')}${f('fv-provider','Processing device',sel('fv-provider',[['cuda','NVIDIA GPU'],['cpu','CPU']]),'videoFaceCompute')}${f('fv-encoder','Video encoder',sel('fv-encoder',[['libx264','H.264 · CPU'],['h264_nvenc','H.264 · NVIDIA']]),'videoFaceEncoder')}${f('fv-priority','Queue priority',num('fv-priority',5,0,10,1),'priority')}</details>
 <small>Original video and audio are preserved. FaceFusion: OpenRAIL-AS; HyperSwap and supporting models have separate terms. <a href="https://github.com/facefusion/facefusion" target="_blank" rel="noreferrer">Project & licenses ↗</a></small>
</fieldset>`);
let videoFaceTarget=null,videoFaceReference=null,videoFaceInitialized=false;
function renderVideoFaceSources(){
 for(const [key,item] of [['target',videoFaceTarget],['reference',videoFaceReference]]){
  $('face-video-'+key).innerHTML=item?`<div class="source-chip"><img src="${thumbURL(item)}" alt=""><span>${esc(item.name)}${item.width?`<small>${item.width} × ${item.height}</small>`:''}</span><button type="button" data-video-face-clear="${key}" aria-label="Clear ${key==='target'?'target video':'video reference face'}">×</button></div>`:(key==='target'?'No video selected.':'No face selected.');
 }
}
function videoFaceModeChanged(){
 const video=$('face-media-mode').value==='video';
 $('face-image-fields').hidden=$('face-image-fields').disabled=video;
 $('face-video-fields').hidden=$('face-video-fields').disabled=!video;
 $('fv-tracking').hidden=$('fv-selector').value!=='reference';
 const empty=$('face-preview').querySelector('.empty-state');if(empty)empty.textContent=video?'Choose a target video and a reference face.':'Choose a target image and a reference face.';
 for(const id of ['fv-face_position','fv-reference_frame','fv-similarity'])$(id).disabled=$('fv-selector').value!=='reference';
 $('face-preview').closest('.preview').querySelector('.preview-heading span:last-child').textContent=video?'MP4 + original audio':'PNG';
 renderVideoFaceSources();
}
function videoFaceOptions(){return {model:'facefusion_video',source_id:videoFaceTarget?.id||'',reference_id:videoFaceReference?.id||'',selector:$('fv-selector').value,face_position:Number($('fv-face_position').value)-1,reference_frame:$('fv-reference_frame').value,similarity:$('fv-similarity').value,pixel_boost:$('fv-pixel_boost').value,quality:$('fv-quality').value,provider:$('fv-provider').value,encoder:$('fv-encoder').value};}
function fillVideoFaceOptions(options){
 for(const key of ['selector','reference_frame','similarity','pixel_boost','quality','provider','encoder'])if(options[key]!==undefined)$('fv-'+key).value=options[key];
 $('fv-face_position').value=Number(options.face_position??0)+1;
}
$('face-media-mode').onchange=()=>{if(editingQueue){notify('Finish or cancel the queue edit before changing media type.');$('face-media-mode').value=editingQueue.kind==='faceswap_video'?'video':'image';}videoFaceModeChanged();};
$('fv-selector').onchange=videoFaceModeChanged;
$('face-video-install').onclick=()=>action('/api/faceswap/install-video').catch(()=>{});
$('face-video-local').onclick=async()=>{
 if(state?.busy){notify('Wait for the current operation before importing a local video.');return;}
 pending={before:state?.latest_media?.id,target:'face-video'};
 try{const result=await action('/api/videos/import-local');if(result.cancelled)pending=null;}catch{pending=null;}
};
document.addEventListener('click',event=>{const button=event.target.closest('[data-video-face-clear]');if(!button)return;if(button.dataset.videoFaceClear==='target'){videoFaceTarget=null;if(pending?.target==='face-video')pending=null;}else{videoFaceReference=null;if(pending?.target==='face-video-reference')pending=null;}renderVideoFaceSources();});
const beforeVideoFacePicker=openPicker;
openPicker=function(target){const video=target==='face-video';$('pick-type').innerHTML=video?'<option value="video">Videos</option>':'<option value="image">Images</option>';beforeVideoFacePicker(target);if(video)$('picker-title').textContent='Choose a target video';};
const beforeVideoFaceSend=sendImage;
sendImage=function(item,target){
 if(target==='face-video'||target==='face-video-reference'){
  const video=target==='face-video';if((item.media_type==='video')!==video){notify(video?'Choose a video.':'Choose a reference image.');return;}
  if(video)videoFaceTarget=item;else videoFaceReference=item;
  $('face-media-mode').value='video';videoFaceModeChanged();showPage('faceswap');return;
 }
 return beforeVideoFaceSend(item,target);
};
const beforeVideoFaceSubmit=$('face-form').onsubmit;
$('face-form').onsubmit=async event=>{
 if($('face-media-mode').value!=='video')return beforeVideoFaceSubmit(event);
 event.preventDefault();if(!videoFaceTarget||!videoFaceReference){notify('Choose a target video and reference face.');return;}
 await submitQueue('faceswap_video',videoFaceOptions(),Number($('fv-priority').value)).catch(()=>{});
};
const beforeVideoFaceTools=renderTools;
renderTools=function(){
 beforeVideoFaceTools();if(!videoFaceInitialized){const saved=state.settings.video_face_options||{};fillVideoFaceOptions(saved);videoFaceInitialized=true;}
 $('video-face-ready').textContent=state.video_faceswap?.ready?'Video faceswap installed.':'Install video faceswap to download its models and isolated runtime.';
 $('face-video-install').disabled=$('face-video-local').disabled=!!state.busy;$('face-video-install').hidden=!!state.video_faceswap?.ready;
 if(!$('video-faceswap-card'))$('pack-grid').insertAdjacentHTML('afterend',`<article class="pack" id="video-faceswap-card" style="margin-top:16px"><h3>FaceFusion · HyperSwap video <span class="badge" id="video-faceswap-badge"></span></h3><p>Swap faces in existing videos with person selection and source audio. Separate dependencies preserve your existing generators. <a href="https://github.com/facefusion/facefusion" target="_blank" rel="noreferrer">Project & licenses ↗</a></p><button type="button" id="models-install-video-faceswap">Install / repair video faceswap</button></article>`);
 $('video-faceswap-badge').textContent=state.video_faceswap?.ready?'Installed':'Not installed';$('models-install-video-faceswap').disabled=!!state.busy;
 $('models-install-video-faceswap').onclick=()=>$('face-video-install').click();
};
const beforeVideoFaceMedia=openMedia;
openMedia=function(item){beforeVideoFaceMedia(item);if(item.media_type!=='video')return;const button=document.createElement('button');button.textContent='Send to Faceswap';button.onclick=()=>{$('media-dialog').close();sendImage(item,'face-video');};$('media-body').querySelector('.media-preview-column').append(button);};
const beforeVideoFaceResult=showResult;
showResult=function(item,target){beforeVideoFaceResult(item,target);if(item.options?.model==='facefusion_video'){$('face-preview').innerHTML=`<video src="${mediaURL({...item,media_type:'video'})}" controls preload="metadata"></video>`;renderActions(item,'face-actions',true);}};
const beforeVideoFaceEdit=editQueueItem;
editQueueItem=async function(id){
 if(state.queue.jobs.find(item=>item.id===id)?.kind!=='faceswap_video'){await beforeVideoFaceEdit(id);if(editingQueue?.kind==='faceswap'){$('face-media-mode').value='image';videoFaceModeChanged();}return;}
 await action('/api/queue/action',{action:'pause'});const detail=await api('/api/queue/'+id);if(detail.status!=='queued'){notify('This job has already started.');return;}
 exitQueueEdit();editingQueue={id,kind:'faceswap_video',model:'facefusion_video',loras:[]};
 videoFaceTarget=detail.sources.find(item=>item.id===detail.options.source_id)||null;videoFaceReference=detail.sources.find(item=>item.id===detail.options.reference_id)||null;
 fillVideoFaceOptions(detail.options);$('fv-priority').value=detail.priority;$('face-media-mode').value='video';videoFaceModeChanged();
 $('f-queue-edit').hidden=false;$('face-submit').textContent='Save queue changes';showPage('faceswap');
};
videoFaceModeChanged();
