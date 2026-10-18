'use strict';
Object.assign(help,{
 minimaxTurbo:['MiniMax H3 Turbo','Local version of Pepe104’s Space: standard MiniMax H3 FL2VA plus Larry Turbo. The Space uses unquantized cloud models and a remote encoder; Studio uses a quantized checkpoint and local encoder. No separate uncensoring checkpoint was found in the Space. This is experimental on a 16 GB GPU; use small dimensions and short clips first. Large models also need substantial system RAM and paging capacity.'],
 turbo:['Turbo adapter','Larry v1-850 matches the Space’s default adapter. The author recommends the newer v4-600 for most work, especially static or small-motion scenes. Use 6–8 steps; v4 can smear fast motion at four steps. Off uses the base model and needs more steps (start with 28). These are speed adapters, not separate uncensoring models.'],
 turboStrength:['Turbo strength','Start at 1.0. The author suggests about 1.05–1.2 for blurry ghosting, or 0.8–0.95 for over-sharp grain. This changes the Turbo adapter only; extra LoRAs keep their own strengths. Ignored with Turbo off.'],
 turboMemory:['Low-memory Turbo','Merges the Turbo update into quantized weights to reduce peak memory. The author warns this can soften detail; turn it off for sharper runtime adapters if your GPU has enough memory. This option does not guarantee that a large clip fits.'],
 lastImage:['Last image','Optional final keyframe for MiniMax H3 Image → Video. The starting image anchors the first frame; this image guides the final frame. Images are fitted to the output canvas, so choose a matching shape. Clear removes the selection without deleting the Library item. Text → Video ignores both image selections.'],
});
pages.video[1]='Generate video from text, animate an image, or guide a clip with reference images and optional sound.';
help.audio[1]+=' MiniMax H3 Turbo also generates its own audio; it does not synchronize your voice recording.';
$('vmodel').insertAdjacentHTML('beforeend','<option value="minimax_h3">MiniMax H3 · Turbo (Pepe104)</option>');
$('v-ready').insertAdjacentHTML('afterend',`<div id="minimax-info" class="notice" hidden>Local quantized MiniMax H3 Turbo · experimental on 16 GB GPUs. ${q('minimaxTurbo')}</div>`);
$('video-audio').insertAdjacentHTML('afterend',`<details id="minimax-controls" hidden open><summary>MiniMax Turbo</summary>${f('vturbo','Turbo adapter',sel('vturbo',[['larry850','Larry v1-850 · Space default'],['larryv4','Larry v4-600 · author recommended'],['off','Off · base model']]),'turbo')}${f('vturbo_strength','Turbo strength',num('vturbo_strength',1,.1,2,.05),'turboStrength')}<label class="check"><input id="vturbo_low_vram" type="checkbox" checked>Low-memory Turbo ${q('turboMemory')}</label></details>`);
$('video-source-controls').insertAdjacentHTML('beforeend',`<div id="minimax-end-controls" hidden><label>Last image (optional) ${q('lastImage')}</label><div id="minimax-end" class="notice">No last image selected.</div><div class="row"><button type="button" data-pick="minimax-end">Library</button><button type="button" data-import="minimax-end">Local file</button><button type="button" id="minimax-end-clear" aria-label="Clear last image">× Clear</button></div></div>`);
let minimaxEnd=null,wasMiniMaxTurbo=false;
function renderMiniMaxEnd(){const item=minimaxEnd;$('minimax-end').innerHTML=item?`<div class="source-chip"><img src="${mediaURL(item)}" alt=""><span>${esc(item.name)}</span></div>`:'No last image selected.';$('minimax-end-clear').disabled=!item;}
function updateTurboControls(){const active=$('vturbo').value!=='off';$('vturbo_strength').disabled=$('vturbo_low_vram').disabled=!active;$('vsteps').min=active?4:1;$('vsteps').max=active?8:80;}
$('vturbo').onchange=()=>{updateTurboControls();$('vsteps').value=$('vturbo').value==='off'?28:6;};
$('minimax-end-clear').onclick=()=>{minimaxEnd=null;renderMiniMaxEnd();};
const beforeMiniMaxSend=sendImage;
sendImage=function(item,target){if(target==='minimax-end'){minimaxEnd=item;renderMiniMaxEnd();showPage('video');return;}return beforeMiniMaxSend(item,target);};
const beforeMiniMaxFill=fill;
fill=function(prefix,options){beforeMiniMaxFill(prefix,options);if(prefix==='v'&&options?.model==='minimax_h3'){const id=options.last_image;minimaxEnd=id?(state?.images.find(x=>x.id===id)||{id,name:'Selected last image'}):null;renderMiniMaxEnd();}};
const beforeMiniMaxModel=videoModelChanged;
videoModelChanged=function(reset=true){
 const selected=$('vmodel').value==='minimax_h3';
 $('minimax-info').hidden=$('minimax-controls').hidden=$('minimax-end-controls').hidden=!selected;
 if(!selected&&wasMiniMaxTurbo){$('vframes').innerHTML=ordinaryFrames;$('vframes').value='49';$('vframecount').min=9;$('vframecount').max=481;$('v-custom-frames').hidden=true;$('vsteps').min=1;$('vsteps').max=80;}
 wasMiniMaxTurbo=selected;beforeMiniMaxModel(reset);if(!selected)return;
 $('vmode').closest('.field').hidden=false;$('vmode').querySelector('[value="text"]').disabled=false;$('vmode').querySelector('[value="image"]').disabled=false;
 $('vnegative').disabled=true;$('vfps').disabled=true;
 for(const id of ['vwidth','vheight'])$(id).max=1344;
 $('vshape').innerHTML=[['960x544','Landscape · 960 × 544'],['544x960','Portrait · 544 × 960'],['544x544','Square · 544 × 544'],['768x512','Small landscape · 768 × 512'],['1344x768','Full landscape · 1344 × 768'],['768x1344','Full portrait · 768 × 1344'],['custom','Custom dimensions']].map(([v,t])=>`<option value="${v}">${t}</option>`).join('');
 $('vframes').innerHTML='<option value="56">56 frames · 2.33 seconds</option><option value="124">124 frames · 5.17 seconds</option><option value="243">243 frames · 10.13 seconds</option><option value="362">362 frames · 15.08 seconds</option><option value="custom">Custom frame count</option>';
 $('vframecount').min=22;$('vframecount').max=362;$('vframecount').step=17;
 if(reset){$('vwidth').value=960;$('vheight').value=544;$('vframes').value='124';$('v-custom-frames').hidden=true;$('v-size').hidden=true;$('vturbo').value='larry850';$('vturbo_strength').value=1;$('vturbo_low_vram').checked=true;$('vsteps').value=6;}
 for(const [key,value] of Object.entries({cfg:1,fps:24,shift:12,sampler:'euler',scheduler:'simple'})){$('v'+key).value=value;$('v'+key).disabled=true;}
 $('vsteps').disabled=false;$('video-audio').hidden=false;$('vmemory').value='low';updateTurboControls();updateDuration();updateAvailability();renderLoraSummaries();
};
const beforeMiniMaxOptions=generationOptions;
generationOptions=function(prefix){const o=beforeMiniMaxOptions(prefix);if(prefix==='v'&&o.model==='minimax_h3'){o.turbo=$('vturbo').value;o.turbo_strength=Number($('vturbo_strength').value);o.turbo_low_vram=$('vturbo_low_vram').checked;o.last_image=$('vmode').value==='image'?(minimaxEnd?.id||''):'';}return o;};
const beforeMiniMaxPacks=renderPacks;
renderPacks=function(){beforeMiniMaxPacks();const card=document.querySelector('[data-uninstall="minimax_h3"]')?.closest('.pack');if(!card||card.querySelector('.minimax-links'))return;const hint=[...card.querySelectorAll('small')].find(x=>x.textContent.startsWith('Compatible engine installs automatically'));if(hint)hint.textContent='Compatible engine and Windows kernels install separately (about 75 MB). Shared encoder and VAEs are reused.';const p=document.createElement('p');p.className='minimax-links';p.innerHTML='<a href="https://huggingface.co/spaces/Pepe104/MiniMax-H3-Turbo-Lora-UNCENSORED" target="_blank" rel="noreferrer">Original Space ↗</a> · <a href="https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora" target="_blank" rel="noreferrer">Turbo adapters & guidance ↗</a><small>Local quantized workflow. The Space’s name does not identify a separate uncensoring checkpoint. 16 GB performance is unverified; 24 GB or more is advised.</small>';card.append(p);};
renderMiniMaxEnd();
