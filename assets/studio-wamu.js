'use strict';
help.wamu=['WAMU Lightning 14B','Wan 2.2 image-to-video merge with separate high- and low-noise 14B models. Uses the original BF16 Diffusers shards, about 57 GB before shared Wan components. Reuses the Wan UMT5 encoder and Wan 2.1 VAE. Four-step default, CFG 1, UniPC and shift 3 from the repository configuration; up to eight steps. The noise stages switch at the repository boundary ratio of 0.9. This native ComfyUI workflow has not been verified by generating a video and may differ from Diffusers. 16 GB GPU performance is unverified; substantial system RAM and paging are required. Generates silent video. Extra LoRAs apply to both stages and must match Wan 2.2 I2V 14B. The merge publisher has not specified a license.'];
$('vmodel').insertAdjacentHTML('beforeend','<option value="wamu">WAMU · Wan 2.2 I2V Lightning 14B</option>');
$('v-ready').insertAdjacentHTML('afterend',`<div id="wamu-info" class="notice" hidden>WAMU Lightning · 14B high/low-noise stages · 57 GB model download · silent video. ${q('wamu')}</div>`);
let wasWamu=false;
const beforeWamuModel=videoModelChanged;
videoModelChanged=function(reset=true){
 const active=$('vmodel').value==='wamu';
 if(wasWamu&&!active){$('vsteps').min=1;$('vsteps').max=80;}
 beforeWamuModel(reset);$('wamu-info').hidden=!active;wasWamu=active;if(!active)return;
 $('vmode').value='image';$('vmode').querySelector('[value="text"]').disabled=true;$('vmode').closest('.field').hidden=true;
 $('video-source-controls').hidden=false;$('video-audio').hidden=true;
 $('vnegative').disabled=true;$('vsteps').disabled=false;$('vsteps').min=4;$('vsteps').max=8;
 if(reset){$('vsteps').value=4;$('vfps').value=16;}
 for(const [key,value] of Object.entries({cfg:1,shift:3,sampler:'uni_pc',scheduler:'simple'})){$('v'+key).value=value;$('v'+key).disabled=true;}
 $('vmemory').value='low';renderVideoInputHint();updateDuration();updateAvailability();renderLoraSummaries();
};
const beforeWamuOptions=generationOptions;
generationOptions=function(prefix){const o=beforeWamuOptions(prefix);if(prefix==='v'&&o.model==='wamu'){o.audio=false;o.cfg=1;o.shift=3;o.sampler='uni_pc';o.scheduler='simple';o.memory='low';}return o;};
