'use strict';
// The full upstream editor runs in a separate local origin. No Studio token is sent to it.
pages.openjutsu=['Video Editor','Replace characters, edit objects, relight scenes and finish videos with the full OpenJutsu editor.'];
document.querySelector('#navigation [data-page="video"]').insertAdjacentHTML('afterend','<button data-page="openjutsu">Video Editor</button>');
$('pages').insertAdjacentHTML('beforeend',`
<section id="page-openjutsu" class="page" hidden><div class="workspace oj-workspace">
 <div class="controls"><div class="control-scroll">
  <h2>Video editing with OpenJutsu</h2>
  <p class="notice">The complete editor: Simple and Advanced character swaps, Montage / Find people, object Change / Remove / Add / Background, From picture, Relight, Fix faces and Fix colours.</p>
  <p id="oj-app-status" class="model-state" role="status"></p>
  <div class="row"><button type="button" id="oj-install" class="primary">Install selected setup</button><button type="button" id="oj-software">Software only</button></div>
  <small>Studio manages the editor, separate ComfyUI engine, required nodes and verified model downloads. Existing Studio generators are preserved.</small>
  <details id="oj-setup" open><summary>Backend & model downloads</summary>
   <label for="oj-mode">Backend</label><select id="oj-mode"><option value="managed">Managed by Studio · recommended</option><option value="external">Existing external ComfyUI</option></select>
   <div id="oj-managed">
    <p id="oj-software-status" class="model-state"></p>
    <label for="oj-models">OpenJutsu model folder</label><input id="oj-models" type="text" spellcheck="false"><button type="button" id="oj-models-browse">Browse…</button>
    <small>Choose a drive with enough space. Matching installed Studio models are verified and reused without moving them.</small>
    <div id="oj-model-groups"></div><p id="oj-download-size" class="notice"></p>
    <label for="oj-hf-token">Hugging Face read token · for FLUX relighting</label><input id="oj-hf-token" type="password" autocomplete="off">
    <small>Accept the <a href="https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy" target="_blank" rel="noopener noreferrer">FLUX model access conditions ↗</a> first. The token is used for installation and is not saved. Face-refinement models retain their own terms.</small>
   </div>
   <div id="oj-external" hidden><p>Use your existing ComfyUI 0.41.2+ installation with OpenJutsu's nodes and models.</p>
   <label for="oj-backend">OpenJutsu's ComfyUI address</label>
   <input id="oj-backend" type="url" value="http://127.0.0.1:8188" spellcheck="false" autocomplete="off">
   </div>
   <div class="row"><button type="button" id="oj-save">Save setup</button><button type="button" id="oj-check">Check backend</button></div>
   <div id="oj-backend-status" class="notice" role="status">Backend has not been checked.</div>
   <div id="oj-missing"></div>
   <p><a href="https://github.com/D3voz/openjutsu#requirements" target="_blank" rel="noopener noreferrer">Backend requirements & model list ↗</a></p>
   <small>Upstream tested H3 on an NVIDIA RTX 4060 Ti with 16 GB VRAM and 64 GB system RAM. That is not a Studio benchmark. The editor checks selected nodes and model filenames before each job; readiness still depends on dependencies, model integrity and memory.</small>
  </details>
  <details><summary>Sources, results & queues</summary>
   <p>Select source videos and reference images in the OpenJutsu editor. Studio Library files can be located with Library → Open folder, or saved as copies.</p>
   <p>Download the finished video in OpenJutsu, then use <strong>Import finished video</strong> below to copy it into Studio's Library.</p>
   <p>Opening this workspace pauses Studio's queue and releases its generation engine. OpenJutsu has its own jobs and cancellation controls. Finish or cancel those jobs before stopping the workspace, then resume Studio's queue when ready.</p>
   <small>Closing Studio stops its managed editor, proxy and backend, including an active managed render. External ComfyUI services stay running. Finish jobs before exiting.</small>
  </details>
  <small><a href="https://github.com/D3voz/openjutsu" target="_blank" rel="noopener noreferrer">OpenJutsu by D3voz · MIT ↗</a> · Models and node packs retain their own terms.</small>
 </div><div class="control-footer oj-buttons">
  <button type="button" id="oj-start" class="primary">Open workspace</button>
  <button type="button" id="oj-stop">Stop workspace</button>
  <button type="button" id="oj-import">Import finished video</button>
 </div></div>
 <div class="preview"><div class="preview-heading"><span>OpenJutsu · all modes</span><a id="oj-browser" hidden target="_blank" rel="noopener noreferrer">Open in browser ↗</a></div>
  <div class="oj-editor"><div id="oj-empty" class="oj-empty"><h2>A new character. The same performance.</h2><p>Swap characters, change objects and lighting, then refine faces and colour.</p><p>Choose a model folder, install the selected setup and open the workspace.</p><small>Opening the editor does not start generation.</small></div>
   <iframe id="oj-frame" title="OpenJutsu video editor" hidden referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-modals allow-popups allow-popups-to-escape-sandbox"></iframe>
  </div>
 </div></div></section>`);
let ojInitialized=false,ojFrameURL='',ojCheckSignature='';
async function ojAction(name,data={}){return action('/api/openjutsu/'+name,data);}
function ojBackendMode(){const managed=$('oj-mode').value==='managed';$('oj-managed').hidden=!managed;$('oj-external').hidden=managed;$('oj-software').hidden=!managed;}
function ojGroups(){return [...$('oj-model-groups').querySelectorAll('input:checked')].map(input=>input.value);}
function ojEstimate(){const groups=(state?.openjutsu?.managed?.groups||[]).filter(group=>ojGroups().includes(group.id));$('oj-download-size').textContent=`Selected models: ${(groups.reduce((n,g)=>n+g.remaining,0)/1024**3).toFixed(1)} GB download · ${(groups.reduce((n,g)=>n+g.size,0)/1024**3).toFixed(1)} GB total. Allow 6 GB separately for software, caches and builds.`;}
async function ojSave(){await ojAction('settings',{mode:$('oj-mode').value,backend:$('oj-backend').value,models:$('oj-models').value});await refreshTools();$('oj-backend').value=state.openjutsu.backend;}
$('oj-save').onclick=()=>ojSave().then(()=>notify('OpenJutsu setup settings saved.')).catch(()=>{});
$('oj-mode').onchange=ojBackendMode;
$('oj-models-browse').onclick=async()=>{try{const result=await action('/api/pick-folder');if(result.path)$('oj-models').value=result.path;}catch{}};
async function ojInstall(softwareOnly){try{await ojSave();if($('oj-mode').value==='managed')await ojAction('install-managed',{groups:softwareOnly?[]:ojGroups(),token:$('oj-hf-token').value});else await ojAction('install');}catch{}}
$('oj-install').onclick=()=>ojInstall(false);
$('oj-software').onclick=()=>ojInstall(true);
$('oj-check').onclick=()=>ojAction('check').catch(()=>{});
$('oj-start').onclick=async()=>{
 try{await ojSave();}catch{return;}
 await ojAction('start').catch(()=>{});
};
$('oj-stop').onclick=()=>ojAction('stop').catch(()=>{});
$('oj-import').onclick=async()=>{
 try{const result=await action('/api/videos/import-local');if(!result.cancelled)notify('Importing the finished video. Its copy will appear in Library.');}catch{}
};
function renderOpenJutsu(){
 const info=state?.openjutsu;if(!info)return;
 if(!ojInitialized){$('oj-backend').value=info.backend;$('oj-mode').value=info.mode||'managed';$('oj-models').value=info.managed?.models||'';ojBackendMode();ojInitialized=true;}
 if(!$('oj-model-groups').children.length&&info.managed?.groups){$('oj-model-groups').innerHTML=info.managed.groups.map(group=>`<label class="check" style="margin:14px 0"><input type="checkbox" value="${esc(group.id)}" checked><span>${esc(group.name)}<small id="oj-group-${esc(group.id)}"></small></span></label>`).join('');$('oj-model-groups').onchange=ojEstimate;}
 for(const group of info.managed?.groups||[]){const label=$('oj-group-'+group.id);if(label)label.textContent=group.ready?'Installed':`${(group.remaining/1024**3).toFixed(1)} GB download${group.gated?' · Hugging Face access':''}`;}
 ojEstimate();
 $('oj-software-status').textContent=info.managed?.ready?'Managed engine and all required node packs installed.':'Managed engine and nodes are not installed.';
 $('oj-app-status').textContent=info.running?'Workspace running · Studio queue paused':info.ready?'OpenJutsu editor installed':'OpenJutsu editor is not installed';
 $('oj-install').textContent=$('oj-mode').value==='external'?'Install / repair editor':'Install selected setup';
 $('oj-install').disabled=!!state.busy||info.owned||info.running;
 $('oj-start').disabled=!!state.busy||info.running||!info.ready||(info.mode==='managed'&&!info.managed?.ready);
 $('oj-stop').disabled=!!state.busy||!(info.owned||info.running);
 $('oj-save').disabled=$('oj-backend').disabled=!!state.busy||info.owned||info.running;
 for(const id of ['oj-mode','oj-models','oj-models-browse','oj-software','oj-hf-token'])$(id).disabled=!!state.busy||info.owned||info.running;
 for(const input of $('oj-model-groups').querySelectorAll('input'))input.disabled=!!state.busy||info.owned||info.running;
 $('oj-check').disabled=$('oj-import').disabled=!!state.busy;
 const check=info.check;
 $('oj-backend-status').textContent=!check?'Backend has not been checked.':!check.connected?'Backend unavailable: '+check.error:`Connected to ComfyUI ${check.version}. ${check.missing.length?'Some node packs are missing.':'Listed node packs are registered.'} The editor checks model files for each mode.`;
 const signature=JSON.stringify(check);if(signature!==ojCheckSignature){ojCheckSignature=signature;
  $('oj-missing').innerHTML=check?.connected&&check.missing.length?'<details><summary>Detected node gaps (some features are optional)</summary><ul>'+check.missing.map(group=>`<li><a href="${esc(group.url)}" target="_blank" rel="noopener noreferrer">${esc(group.name)}</a><small>${esc(group.missing.join(', '))}</small></li>`).join('')+'</ul></details>':'';
 }
 const url=info.running?info.url:'';
 // Keep the editor mounted across status polls and page changes.
 if(url!==ojFrameURL){ojFrameURL=url;if(url)$('oj-frame').src=url;else $('oj-frame').removeAttribute('src');}
 $('oj-frame').hidden=!url;$('oj-empty').hidden=!!url;$('oj-browser').hidden=!url;
 if(url)$('oj-browser').href=url;else $('oj-browser').removeAttribute('href');
 if(!$('oj-model-card'))$('pack-grid').insertAdjacentHTML('afterend','<article class="pack" id="oj-model-card" style="margin-top:16px"><h3>OpenJutsu · full video editor</h3><p>Character and object swaps, relighting, face refinement and colour finishing. Managed engine, node packs and selectable model downloads.</p><button type="button" id="oj-model-open">Open setup</button></article>');
 $('oj-model-open').onclick=()=>showPage('openjutsu');
}
const beforeOpenJutsuTools=renderTools;
renderTools=function(){beforeOpenJutsuTools();renderOpenJutsu();};
