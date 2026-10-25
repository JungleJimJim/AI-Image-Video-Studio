'use strict';
help.generationReferences=['Reference images','Guide the subject, appearance, objects or style using Library images or local PNG/JPEG/WebP files. FLUX.2 Klein and Viggle accept up to three images here; FLUX 3 accepts ten. Describe the new scene and how each image should be used. These are conditioning images, not overlays or guaranteed identity locks. Selected references are saved with queued jobs and results.'];
help.videoReferences=['Video character references','MiniMax H3 Ref2VA uses the primary image as <Picture 1> and supports up to eight additional images as <Picture 2> through <Picture 9>. Describe their roles in your prompt. These guide appearance; they do not set a first or last video frame. Wan 2.2, LTX-2 and MiniMax Turbo use starting-frame input instead and do not accept these extra references in this Studio. More references use more memory.'];
const generationRefDraft={i:{},v:{}},generationRefRestore={i:0,v:0},generationRefSignatures={};
function generationRefKey(p){return $(p+'model').value;}
function generationRefLimit(p){const total=pack(generationRefKey(p))?.generation_references||0;return p==='v'?Math.max(0,total-1):total;}
function generationRefItems(p){const key=generationRefKey(p);return generationRefDraft[p][key]||(generationRefDraft[p][key]=[]);}
function generationRefField(p){return p==='i'?'image_references':'video_references';}
for(const p of ['i','v']){
 const panel=document.createElement('section');panel.id=p+'-generation-references';panel.className='generation-reference-panel';panel.hidden=true;
 panel.innerHTML=`<h3>${p==='i'?'Reference images':'Additional character references'} ${q(p==='i'?'generationReferences':'videoReferences')}</h3><small id="${p}-reference-guidance"></small><div id="${p}-reference-images"></div><div class="row"><button type="button" id="${p}-reference-library" data-pick="generation-reference:${p}">Library</button><button type="button" id="${p}-reference-local" data-import="generation-reference:${p}">Local file</button><button type="button" id="${p}-reference-clear">Clear references</button></div><small id="${p}-reference-count" aria-live="polite"></small>`;
 if(p==='i')$('iprompt').closest('.field').after(panel);else $('video-source-controls').append(panel);
 $(p+'-reference-clear').onclick=()=>{generationRefRestore[p]++;generationRefDraft[p][generationRefKey(p)]=[];renderGenerationReferences();};
}
function renderGenerationReferences(){
 for(const p of ['i','v']){
  const limit=generationRefLimit(p),items=generationRefItems(p),panel=$(p+'-generation-references');panel.hidden=!limit;
  const full=items.length>=limit;$(p+'-reference-library').disabled=full;$(p+'-reference-local').dataset.referenceFull=String(full);$(p+'-reference-clear').disabled=!items.length;
  const key=generationRefKey(p),signature=JSON.stringify([key,limit,items.map(x=>[x.id,x.name,x.missing]),p==='v'?videoSource?.id:'']);
  if(generationRefSignatures[p]===signature)continue;generationRefSignatures[p]=signature;
  $(p+'-reference-guidance').textContent=p==='v'?'Primary image is <Picture 1>. Describe additional references as <Picture 2>, <Picture 3>, etc.':key==='flux3'?'Refer to the images as <ref_image_0>, <ref_image_1>, etc. Describe the complete new scene.':'Refer to the images as image 1, image 2, etc. Describe the scene and how to use each reference.';
  $(p+'-reference-count').textContent=items.length+' / '+limit+(p==='v'?' extra references':' references');
  $(p+'-reference-images').innerHTML=items.map((item,index)=>`<div class="source-chip">${item.missing?'':`<img src="${mediaURL(item)}" alt="">`}<span><strong>${esc(p==='v'?'<Picture '+(index+2)+'>':key==='flux3'?'<ref_image_'+index+'>':'Image '+(index+1))}</strong><small>${esc(item.name)}${item.missing?' · unavailable':''}</small></span><button type="button" data-generation-remove="${p}:${index}" aria-label="Remove reference ${index+1}">×</button></div>`).join('');
  $(p+'-reference-images').querySelectorAll('[data-generation-remove]').forEach(button=>button.onclick=()=>{generationRefRestore[p]++;generationRefItems(p).splice(Number(button.dataset.generationRemove.split(':')[1]),1);renderGenerationReferences();});
 }
 const label=$('vsource').previousElementSibling;if(label?.tagName==='LABEL')label.innerHTML=$('vmodel').value==='ref2va'?'Reference image 1 '+q('videoReferences'):'Starting image '+q('source');
 // MOSS/SDXL accept a starting image for repainting, not extra reference conditioning.
 $('reference-panel').hidden=!['fluxklein','flux3','qwenedit','viggle'].includes($('emodel').value);
 updateImageImportButtons();
}
function validateGenerationReferences(p){
 const items=generationRefLimit(p)?generationRefItems(p):[];
 if(items.length>generationRefLimit(p))throw Error('Remove extra references for the selected model.');
 if(items.some(x=>x.missing))throw Error('Remove or replace the unavailable reference image.');
 if(p==='v'&&items.some(x=>x.id===videoSource?.id))throw Error('Choose different images for the primary image and extra references.');
 return items.map(x=>x.id);
}
const referencesPreviousSend=sendImage;sendImage=function(item,target){
 if(!target.startsWith('generation-reference:'))return referencesPreviousSend(item,target);
 const p=target.split(':')[1];if(!['i','v'].includes(p))return;const items=generationRefItems(p),limit=generationRefLimit(p);
 if(!limit||items.length>=limit){notify('This model accepts '+limit+' references here. Remove one before adding another.');return;}
 if(items.some(x=>x.id===item.id)||(p==='v'&&item.id===videoSource?.id)){notify('Choose a different reference image.');return;}
 generationRefRestore[p]++;items.push({...item,media_type:'image'});renderGenerationReferences();showPage(p==='i'?'images':'video');
};
const referencesPreviousAvailability=updateAvailability;updateAvailability=function(){referencesPreviousAvailability();renderGenerationReferences();};
const referencesPreviousSources=renderSources;renderSources=function(){referencesPreviousSources();renderGenerationReferences();};
const referencesPreviousVideoModel=videoModelChanged;videoModelChanged=function(reset=true){referencesPreviousVideoModel(reset);renderGenerationReferences();};
const referencesPreviousOptions=generationOptions;generationOptions=function(p){const options=referencesPreviousOptions(p);if(['i','v'].includes(p))options[generationRefField(p)]=generationRefLimit(p)?generationRefItems(p).map(x=>x.id):[];return options;};
const referencesPreviousSubmit=submitQueue;submitQueue=async function(kind,options,priority){
 if(kind==='image'||kind==='video'){const p=kind==='image'?'i':'v';try{options[generationRefField(p)]=validateGenerationReferences(p);}catch(error){notify(error.message);return;}}
 return referencesPreviousSubmit(kind,options,priority);
};
function restoreGenerationReferences(p,options){
 if(!options||!['i','v'].includes(p))return;const key=options.model||generationRefKey(p),ids=options[generationRefField(p)]||[],revision=++generationRefRestore[p];
 generationRefDraft[p][key]=ids.map(id=>state?.images.find(x=>x.id===id)||{id,name:'Loading reference…',media_type:'image'});renderGenerationReferences();
 for(const id of ids){if(state?.images.some(x=>x.id===id))continue;api('/api/library/'+encodeURIComponent(id)).then(detail=>{if(generationRefRestore[p]!==revision)return;const index=generationRefDraft[p][key].findIndex(x=>x.id===id);if(index>=0)generationRefDraft[p][key][index]=detail.item;renderGenerationReferences();}).catch(()=>{if(generationRefRestore[p]!==revision)return;const item=generationRefDraft[p][key].find(x=>x.id===id);if(item){item.name='Missing Library image';item.missing=true;}renderGenerationReferences();});}
}
const referencesPreviousFill=fill;fill=function(p,options){referencesPreviousFill(p,options);restoreGenerationReferences(p,options);};
const referencesPreviousMediaDetails=mediaDetailsHTML;mediaDetailsHTML=function(item,ancestors=null){const names=item.reference_names||[],ids=item.options?.image_references||item.options?.video_references||[];return referencesPreviousMediaDetails(item,ancestors)+(ids.length?'<div class="media-prompt"><strong>Generation references</strong><p>'+ids.map((id,index)=>esc((index+1)+'. '+(names[index]||id))).join('<br>')+'</p></div>':'');};
if(initialized){restoreGenerationReferences('i',state.settings.image_options);restoreGenerationReferences('v',state.settings.options);}renderGenerationReferences();
