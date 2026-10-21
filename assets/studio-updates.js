'use strict';
help.updates=['App updates','Check for a newer stable Windows release. Nothing is installed until you choose Install update. The download is verified before installation. Finish current processing first; the queue pauses during updating and stays paused after reopening. Only application files are replaced; settings, downloaded models, LoRAs and library media are kept. Windows may request administrator approval for Program Files.'];
$('page-settings').querySelector('.settings-grid').insertAdjacentHTML('afterbegin',`<section class="update-settings"><h2>App updates</h2><p id="update-version">Installed version: ${esc(state?.version||'')}</p><div class="row"><button id="check-updates">Check for updates</button>${q('updates')}</div><p id="update-status" class="notice" hidden></p></section>`);
$('page-settings').querySelector('.settings-grid').insertAdjacentHTML('beforeend',`<section class="about-settings"><h2>About</h2><p>This program was written by Codex in collaboration with Jungle Jim.</p><div class="about-links"><a href="https://backgroundpeople.gumroad.com" target="_blank" rel="noopener noreferrer">More info, free 3D models, Blender add-ons and software ↗</a><a href="https://www.sketchfab.com/Jungle_Jim" target="_blank" rel="noopener noreferrer">Free 3D models ↗</a><a href="https://junglejimjim.github.io/3D/" target="_blank" rel="noopener noreferrer">Jungle Jim’s website ↗</a><a href="https://ainimania.gumroad.com" target="_blank" rel="noopener noreferrer">Free VFX ↗</a></div><p class="notice">You can adjust it to your liking as much as you want. If you don’t know how to code or add another model, ask ChatGPT or Claude.</p></section>`);
document.body.insertAdjacentHTML('beforeend',`<dialog id="update-dialog"><div class="dialog-heading"><h2 id="update-title">Install this update?</h2><button data-close aria-label="Close update offer">×</button></div><p id="update-description"></p><p>Application files will be replaced. Your settings, downloaded models, LoRAs, media and queue will be kept. The studio closes and reopens automatically; the queue reopens paused.</p><details open><summary>Release notes</summary><pre id="update-notes"></pre></details><p id="update-install-hint" class="notice"></p><div class="row"><button data-close>Later</button><button id="install-update" class="primary">Install update</button></div></dialog>`);
let updateCheckPending=false,updateInstallPending=false,updateOffer=null;
function renderStudioUpdates(){
 const u=state?.updates;if(!u)return;
 if(['downloading','installing','error'].includes(u.status))updateInstallPending=false;
 const active=updateCheckPending||updateInstallPending||['checking','downloading','installing'].includes(u.status);
 $('check-updates').disabled=active;
 $('check-updates').textContent=updateCheckPending||u.status==='checking'?'Checking…':'Check for updates';
 $('update-version').textContent='Installed version: '+(state.version||u.current);
 let message='';
 if(u.status==='error')message=u.error;
 else if(u.status==='checked')message=u.available?'Version '+u.version+' is available.':'You have the latest available version.';
 else if(u.status==='downloading'||updateInstallPending)message='Downloading and verifying the update…';
 else if(u.status==='installing')message='Installing. The studio will reopen automatically.';
 $('update-status').textContent=message;
 $('update-status').hidden=!message;
 $('install-update').disabled=active||state.busy||!updateOffer||!u.can_install;
 $('update-install-hint').textContent=!u.can_install?u.install_reason:state.busy?'Finish or cancel the current operation before installing.':'The download is verified before the current app closes.';
}
function showUpdateOffer(offer){updateOffer=offer;$('update-title').textContent='Install Studio '+offer.version+'?';$('update-description').textContent='Current version: '+offer.current+' · Update download: '+(offer.bytes/1024**2).toFixed(1)+' MB';$('update-notes').textContent=offer.notes||'No release notes provided.';renderStudioUpdates();$('update-dialog').showModal();}
$('check-updates').onclick=async()=>{updateOffer=null;updateCheckPending=true;renderStudioUpdates();try{const result=await api('/api/updates/check',{});state.updates=result;updateCheckPending=false;if(result.available)showUpdateOffer(result);else if(result.error)notify(result.error);else notify('You have the latest available version.');}catch(error){notify(error.message);}finally{updateCheckPending=false;renderStudioUpdates();}};
$('install-update').onclick=async()=>{if(!updateOffer||state.busy)return;updateInstallPending=true;renderStudioUpdates();try{await action('/api/updates/install',{ticket:updateOffer.ticket});$('update-dialog').close();notify('Downloading the update. The studio will close after verification and reopen when installation finishes.');}catch{updateInstallPending=false;}renderStudioUpdates();};
