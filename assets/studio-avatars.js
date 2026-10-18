'use strict';
Object.assign(help,{
 avatarModel:['Talking-avatar model','EchoMimic is the recommended starting point on a 16 GB GPU. SoulX offers Lite and Pro. LongCat and InfiniteTalk use memory-saving Q4 checkpoints and can still take substantial time and system RAM. MuseTalk focuses on lip synchronization. Install the selected pack in Models first.'],
 avatarSource:['Avatar source','Use Library to choose a saved image, or Local file to pick a PNG, JPEG or WebP on your computer. Local images are also added to Library. Use the × beside the source to clear the selection; Library files remain saved. InfiniteTalk and MuseTalk also accept Library videos. Faces should be clearly visible; crop or edit a portrait first if necessary.'],
 avatarAudio:['Voice recording','Import a WAV, MP3, M4A, OGG or FLAC recording up to 60 MB and ten minutes. ElevenLabs exports work as ordinary local files. The app stores a mono 48 kHz WAV in Library/Audio. The models use audio encoders for synchronization; this page does not generate or clone a voice.'],
 avatarRange:['Recording range','Start chooses where speech begins in the recording. Duration selects up to 30 seconds for this job; the first preview defaults to five seconds. Longer clips use more time and memory. The original recording is retained, so you can queue other ranges.'],
 avatarVariant:['SoulX variant','Lite prioritizes speed and uses the LTX VAE under Open-RAIL-M. Pro prioritizes detail and uses the Wan VAE. Both model variants install together.'],
 avatarSteps:['Avatar sampling steps','EchoMimic defaults to 8 steps. InfiniteTalk defaults to 40 for its original sampling recipe. LongCat uses its fixed eight-step distilled recipe. SoulX uses its fixed four-step recipe. MuseTalk does not have a denoising-step control.'],
});
pages.avatar=['Talking Avatar','Make a Library portrait speak, or dub a video, using an imported voice recording. Results are saved as new Library videos.'];
document.querySelector('#navigation [data-page="video"]').insertAdjacentHTML('afterend','<button data-page="avatar">Talking Avatar</button>');
$('pages').insertAdjacentHTML('beforeend',`<section id="page-avatar" class="page" hidden><div class="workspace">
 <form id="avatar-form" class="controls"><div id="a-queue-edit" class="queue-edit-banner" hidden>Editing a waiting avatar job <button type="button" data-exit-queue-edit>Cancel editing</button></div><div class="control-scroll">
 ${f('amodel','Avatar model','<select id="amodel"></select>','avatarModel')}<p id="avatar-ready" class="model-state"></p>
 <div class="field"><label>Starting image / video ${q('avatarSource')}</label><div id="avatar-source" class="source-box">No source selected.</div><div class="row"><button type="button" id="avatar-library">Library</button><button type="button" id="avatar-local-file" data-import="avatar">Local file</button><button type="button" id="avatar-library-video">Choose video</button></div></div>
 <div class="field"><label for="avatar-audio">Voice recording ${q('avatarAudio')}</label><div class="row"><select id="avatar-audio" style="flex:1;min-width:0"></select><button type="button" id="avatar-import-audio">Import…</button></div></div><audio id="avatar-audio-player" controls preload="metadata" hidden></audio><input type="file" id="avatar-audio-file" accept=".wav,.mp3,.m4a,.ogg,.flac,audio/*" hidden>
 <div class="two">${f('aaudio_start','Start (seconds)',num('aaudio_start',0,0,600,.1),'avatarRange')}${f('aduration','Duration (seconds)',num('aduration',5,.5,30,.1),'avatarRange')}</div>
 <div id="avatar-variant-field">${f('avariant','SoulX variant',sel('avariant',[['lite','Lite · faster'],['pro','Pro · more detail']]),'avatarVariant')}</div>
 <details><summary>Advanced settings</summary><div id="avatar-prompt-field">${f('aprompt','Motion / scene description','<textarea id="aprompt">A person speaking naturally, looking at the camera.</textarea>','prompt')}</div>${sizes('a')}${seedControls('a')}${f('asteps','Sampling steps',num('asteps',8,4,80,1),'avatarSteps')}<div id="avatar-loras"><button type="button" id="avatar-manage-loras">Manage LoRAs</button>${q('loras')}<small id="avatar-lora-count"></small></div>
 ${f('apriority','Queue priority',num('apriority',5,0,10,1),'priority')}</details>
 </div><div class="control-footer"><button type="submit" id="avatar-submit" class="primary">Add to queue</button></div></form>
 <section class="preview"><div class="preview-heading"><strong>Talking avatar preview</strong><span class="badge">MP4 + your recording</span></div><div class="preview-stage" id="avatar-preview"><div class="empty-state">Choose a portrait or video and import your voice recording.</div></div><div class="preview-actions" id="avatar-actions" hidden></div></section>
 </div></section>`);
for(const id of ['awidth','aheight']){$(id).value=512;$(id).max=768;}
let avatarSource=null,avatarInitialized=false,avatarAudioSignature='',avatarResult='',avatarAudioImportBefore='';
function setAvatarSource(item){
 avatarSource={...item,media_type:item.media_type==='video'?'video':'image'};
 if(avatarSource.media_type==='video'&&!['avatar_infinite','avatar_musetalk'].includes($('amodel').value))$('amodel').value='avatar_musetalk';
 renderAvatarSource();updateAvatarModel(false);showPage('avatar');
}
function renderAvatarSource(){
 $('avatar-source').innerHTML=avatarSource?`<div class="source-chip">${avatarSource.media_type==='video'?'<span>VIDEO</span>':`<img src="${mediaURL(avatarSource)}" alt="Avatar source">`}<span>${esc(avatarSource.name)}</span><button type="button" id="avatar-clear-source" aria-label="Clear avatar source" title="Clear selection">×</button></div>`:'No source selected.';
 if(avatarSource)$('avatar-clear-source').onclick=()=>{
  if(pending?.target==='avatar')pending=null;
  avatarSource=null;renderAvatarSource();updateAvatarModel(false);
 };
}
function updateAvatarModel(reset=true){
 const model=$('amodel').value,info=pack(model),soul=model==='avatar_soulx',muse=model==='avatar_musetalk';
 $('avatar-variant-field').hidden=!soul;$('avatar-prompt-field').hidden=soul||muse;
 $('asteps').closest('.field').hidden=soul||muse||model==='avatar_longcat';
 $('avatar-library-video').hidden=!['avatar_infinite','avatar_musetalk'].includes(model);
 $('avatar-loras').hidden=!['avatar_longcat','avatar_infinite'].includes(model);
 $('avatar-lora-count').textContent=`${savedLoras(model).length} enabled`;
 if(reset)$('asteps').value=model==='avatar_infinite'?40:8;
 $('avatar-ready').textContent=info?.ready?'Model and avatar runtime installed.':'Install this avatar model in Models first.';
 $('avatar-submit').disabled=!info?.ready||!avatarSource||!$('avatar-audio').value;
 if(avatarSource?.media_type==='video'&&!['avatar_infinite','avatar_musetalk'].includes(model)){
  $('avatar-ready').textContent='Choose an image for this model, or use InfiniteTalk / MuseTalk with the selected video.';$('avatar-submit').disabled=true;
 }
}
function renderAvatar(){
 if(!state)return;
 if(!avatarInitialized){
  const models=state.packs.filter(p=>p.kind==='avatar');if(!models.length)return;
  $('amodel').innerHTML=models.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  const saved=state.settings.avatar_options||{};
  for(const key of ['model','prompt','width','height','seed','steps','variant','duration','audio_start'])if(saved[key]!==undefined)$('a'+key).value=saved[key];
  $('arandomize_seed').checked=saved.randomize_seed!==false;if($('arandomize_seed').checked)$('aseed').value=randomSeed($('aseed').value);
  avatarSource=[...state.images,...state.library.map(x=>({...x,media_type:'video'}))].find(x=>x.id===saved.source_id)||null;
  if(avatarSource)avatarSource={...avatarSource,media_type:avatarSource.media_type||'image'};
  renderAvatarSource();avatarInitialized=true;
 }
 const recordings=state.recordings||[],signature=JSON.stringify(recordings.map(x=>[x.id,x.name,x.duration]));
 if(signature!==avatarAudioSignature){
  const selected=$('avatar-audio').value||state.settings.avatar_options?.audio_id;
  avatarAudioSignature=signature;
  $('avatar-audio').innerHTML='<option value="">Choose an imported recording…</option>'+recordings.map(x=>`<option value="${esc(x.id)}">${esc(x.name)} · ${Number(x.duration).toFixed(1)} s</option>`).join('');
  $('avatar-audio').value=recordings.some(x=>x.id===selected)?selected:recordings.at(-1)?.id||'';
  updateAvatarAudio();
 }
 if(state.audio_result&&state.audio_result.id!==avatarAudioImportBefore){$('avatar-audio').value=state.audio_result.id;avatarAudioImportBefore=state.audio_result.id;updateAvatarAudio();}
 $('avatar-import-audio').disabled=state.busy;
 updateAvatarModel(false);
 const result=state.avatar_result;
 if(result&&result.id!==avatarResult){avatarResult=result.id;$('avatar-preview').innerHTML=`<video controls src="${mediaURL({...result,media_type:'video'})}" preload="metadata"></video>`;$('avatar-actions').hidden=false;$('avatar-actions').innerHTML='<button id="avatar-open-result">Open in Library</button>';$('avatar-open-result').onclick=()=>openMedia({...result,media_type:'video'});}
}
function updateAvatarAudio(){const selected=$('avatar-audio').value,player=$('avatar-audio-player');player.hidden=!selected;if(selected){const url='/audio/'+encodeURIComponent(selected)+'?token='+encodeURIComponent(token);if(player.getAttribute('src')!==url)player.src=url;}else player.removeAttribute('src');updateAvatarModel(false);}
$('amodel').onchange=()=>updateAvatarModel();$('avatar-audio').onchange=updateAvatarAudio;
$('avatar-library').onclick=()=>openPicker('avatar');
$('avatar-library-video').onclick=()=>{showPage('library');$('lib-type').value='video';libraryPage=0;loadLibrary();notify('Open a Library video and choose Send to Talking Avatar.');};
$('avatar-manage-loras').onclick=()=>openLoras($('amodel').value);
$('avatar-import-audio').onclick=()=>$('avatar-audio-file').click();
$('avatar-audio-file').onchange=async()=>{
 const input=$('avatar-audio-file'),file=input.files[0];if(!file)return;
 try{if(file.size>60*1024**2)throw Error('Choose a recording no larger than 60 MB.');
  const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read the recording.'));reader.readAsDataURL(file);});
  await action('/api/avatars/audio/import',{name:file.name,data});notify('Importing your recording…');
 }catch(error){notify(error.message);}finally{input.value='';}
};
$('avatar-form').onsubmit=async event=>{
 event.preventDefault();if(!avatarSource){notify('Choose a Library image or video.');return;}
 const options={source_id:avatarSource.id,source_type:avatarSource.media_type,audio_id:$('avatar-audio').value,randomize_seed:$('arandomize_seed').checked};
 for(const key of ['model','prompt','width','height','seed','steps','variant','duration','audio_start'])options[key]=$('a'+key).value;
 if(editingQueue?.kind==='avatar')options.loras=editingQueue.loras;
 const before=options.seed,wasEditing=!!editingQueue;
 try{await submitQueue('avatar',options,Number($('apriority').value));if(!wasEditing)advanceSeed('a',before);}catch{}
};
const beforeAvatarSend=sendImage;sendImage=function(item,target){if(target==='avatar'){setAvatarSource(item);return;}return beforeAvatarSend(item,target);};
const beforeAvatarMedia=openMedia;openMedia=function(item){beforeAvatarMedia(item);const button=document.createElement('button');button.textContent='Send to Talking Avatar';button.onclick=()=>{$('media-dialog').close();setAvatarSource(item);};$('media-body').querySelector('.media-preview-column').append(button);};
const beforeAvatarTools=renderTools;renderTools=function(){beforeAvatarTools();renderAvatar();};
const beforeAvatarExit=exitQueueEdit;exitQueueEdit=function(){beforeAvatarExit();$('a-queue-edit').hidden=true;$('avatar-submit').textContent='Add to queue';};
const beforeAvatarEdit=editQueueItem;editQueueItem=async function(id){
 const item=state.queue.jobs.find(x=>x.id===id);if(item?.kind!=='avatar')return beforeAvatarEdit(id);
 await action('/api/queue/action',{action:'pause'});const detail=await api('/api/queue/'+id);if(detail.status!=='queued'){notify('This job has already started.');return;}
 exitQueueEdit();editingQueue={id,kind:'avatar',model:detail.options.model,loras:detail.options.loras||[]};
 for(const key of ['model','prompt','width','height','seed','steps','variant','duration','audio_start'])if(detail.options[key]!==undefined)$('a'+key).value=detail.options[key];
 $('avatar-audio').value=detail.options.audio_id;$('arandomize_seed').checked=false;$('apriority').value=detail.priority;
 const source=detail.sources.find(x=>x.id===detail.options.source_id);avatarSource=source?{...source,media_type:detail.options.source_type}:null;renderAvatarSource();updateAvatarAudio();
 $('a-queue-edit').hidden=false;$('avatar-submit').textContent='Save queue changes';showPage('avatar');
};
const beforeAvatarPacks=renderPacks;renderPacks=function(){beforeAvatarPacks();for(const packInfo of state.packs.filter(p=>p.kind==='avatar')){
 const card=document.querySelector(`[data-uninstall="${packInfo.id}"]`)?.closest('.pack');if(!card||card.querySelector('.avatar-model-links'))continue;
 const links=document.createElement('p');links.className='avatar-model-links';links.innerHTML=`<a href="${esc(packInfo.source)}" target="_blank" rel="noreferrer">Model & examples ↗</a>${packInfo.checkpoint_source?` · <a href="${esc(packInfo.checkpoint_source)}" target="_blank" rel="noreferrer">Q4 checkpoint ↗</a>`:''}<small>Requires a voice recording. The optional avatar runtime adds about 230 MB once.</small>`;card.append(links);
}};
if(initialized)renderAvatar();
