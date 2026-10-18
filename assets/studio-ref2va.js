'use strict';
Object.assign(help,{
 ref2va:['Ref2VA VSA','Creates a new video using the identity/appearance of a reference image. In the prompt, refer to it as <Picture 1>. Uses MiniMax H3 Ref2VA, the four-step Turbo LoRA, and optional experimental VSA acceleration. Audio is generated from the prompt; this is separate from synchronizing an ElevenLabs recording in Talking Avatar. The author specifies a 24 GB NVIDIA GPU. Smaller GPUs are unverified, and the large encoder also needs substantial system RAM/paging capacity.'],
 ref2vaVsa:['VSA acceleration','Uses Kablex’s experimental sparse-attention patch and trained gates. Requires the isolated comfy-kitchen CUDA Sol-Attention backend. Turn it off for the dense four-step Turbo workflow if your GPU/kernel is incompatible; dense attention can use more time and memory.'],
 ref2vaSparsity:['VSA sparsity','Fraction of generated-video attention blocks skipped. The upstream four-step example uses 0.75. Higher values reduce attention work but may reduce quality. Reference-image, text and audio tokens stay dense. Ignored when VSA is disabled.'],
});
help.audio=['Generated audio','LTX-2 and MiniMax H3 Ref2VA can generate audio alongside video. Turning this off exports a silent MP4. Ref2VA still creates a joint audio/video latent internally. For precise synchronization to your own recorded speech, use Talking Avatar.'];
help.frames[1]+=' MiniMax H3 Ref2VA uses 17n + 5 frames at 24 fps: 124, 243 or 362 frames. Its limits are separate from Wan and LTX-2.';
$('video-audio').querySelector('[data-help="audio"]').setAttribute('aria-label','Explain generated audio');
pages.video[1]='Generate video from text, animate an image, or use a reference character with MiniMax H3 Ref2VA.';
$('vmodel').insertAdjacentHTML('beforeend','<option value="ref2va">MiniMax H3 · Ref2VA VSA</option>');
$('v-ready').insertAdjacentHTML('afterend',`<div id="ref2va-info" class="notice" hidden>Experimental · 24 GB NVIDIA GPU specified. Mention &lt;Picture 1&gt; in your prompt. ${q('ref2va')}</div>`);
$('video-audio').insertAdjacentHTML('afterend',`<details id="ref2va-controls" hidden><summary>Ref2VA acceleration</summary><label class="check"><input type="checkbox" id="vvsa" checked>Use VSA acceleration ${q('ref2vaVsa')}</label>${f('vsparsity','VSA sparsity',num('vsparsity',.75,0,.95,.05),'ref2vaSparsity')}</details>`);
const ordinaryFrames=$('vframes').innerHTML;
let wasRef2va=false;
const beforeRef2vaModel=videoModelChanged;
videoModelChanged=function(reset=true){
 const selected=$('vmodel').value==='ref2va';
 $('ref2va-info').hidden=$('ref2va-controls').hidden=!selected;
 $('vmode').querySelector('[value="text"]').disabled=selected;
 $('vmode').closest('.field').hidden=selected;
 $('vnegative').disabled=selected;$('vfps').disabled=selected;
 for(const id of ['vwidth','vheight'])$(id).max=selected?1344:1024;
 if(!selected){
  if(wasRef2va){$('vframes').innerHTML=ordinaryFrames;$('vframes').value='49';$('vframecount').min=9;$('vframecount').max=481;$('v-custom-frames').hidden=true;}
  wasRef2va=false;return beforeRef2vaModel(reset);
 }
 const shapes=[['768x512','Small landscape · 768 × 512'],['512x768','Small portrait · 512 × 768'],['1344x768','Landscape · 1344 × 768'],['768x1344','Portrait · 768 × 1344'],['768x768','Square · 768 × 768'],['custom','Custom dimensions']];
 $('vshape').innerHTML=shapes.map(([value,label])=>`<option value="${value}">${label}</option>`).join('');
 $('vframes').innerHTML='<option value="124">124 frames · 5.17 seconds</option><option value="243">243 frames · 10.13 seconds</option><option value="362">362 frames · 15.08 seconds</option><option value="custom">Custom frame count</option>';
 $('vframecount').min=22;$('vframecount').max=362;$('vframecount').step=17;
 if(reset){$('vwidth').value=768;$('vheight').value=512;$('v-size').hidden=true;$('vframes').value='124';$('v-custom-frames').hidden=true;$('vvsa').checked=true;$('vsparsity').value=.75;}
 else if(!wasRef2va&&state?.settings.options?.model==='ref2va'){
  const saved=state.settings.options;
  $('vvsa').checked=saved.vsa!==false;$('vsparsity').value=saved.sparsity??.75;
 }
 $('vmode').value='image';$('vmode').querySelector('[value="image"]').disabled=false;
 $('video-source-controls').hidden=false;$('video-audio').hidden=false;
 for(const [key,value] of Object.entries({steps:4,cfg:1,fps:24,shift:12,sampler:'euler',scheduler:'simple'})){$('v'+key).value=value;$('v'+key).disabled=true;}
 $('vmemory').value='low';$('vsparsity').disabled=!$('vvsa').checked;wasRef2va=true;updateDuration();updateAvailability();renderLoraSummaries();
};
const beforeRef2vaOptions=generationOptions;
generationOptions=function(prefix){const options=beforeRef2vaOptions(prefix);if(prefix==='v'&&options.model==='ref2va'){options.vsa=$('vvsa').checked;options.sparsity=Number($('vsparsity').value);}return options;};
$('vvsa').onchange=()=>{$('vsparsity').disabled=!$('vvsa').checked;};
const beforeRef2vaPacks=renderPacks;
renderPacks=function(){beforeRef2vaPacks();const card=document.querySelector('[data-uninstall="ref2va"]')?.closest('.pack');if(!card||card.querySelector('.ref2va-links'))return;const hint=[...card.querySelectorAll('small')].find(x=>x.textContent.startsWith('Compatible engine installs automatically'));if(hint)hint.textContent='Compatible engine and Windows attention kernels install automatically (about 75 MB).';const links=document.createElement('p');links.className='ref2va-links';links.innerHTML='<a href="https://github.com/Kablex/ComfyUI-Ref2VA-VSA" target="_blank" rel="noreferrer">Upstream workflow & requirements ↗</a><small>Experimental VSA · 24 GB NVIDIA GPU specified by author. Weights are optional; engine dependencies install separately without replacing existing generators.</small>';card.append(links);};
