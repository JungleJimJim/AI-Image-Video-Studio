'use strict';
// Library details, selection and file actions share the existing authenticated APIs.
(() => {
 const dialog=$('media-dialog'),selected=new Map();
 let navigation=null,navRevision=0,navBusy=false,backdropPress=false,pendingDelete=null,deleteBusy=false,exportBusy=false;
 dialog.insertAdjacentHTML('afterbegin','<button type="button" id="media-previous" class="media-side previous" aria-label="Previous Library item" title="Previous (←)">‹</button><button type="button" id="media-next" class="media-side next" aria-label="Next Library item" title="Next (→)">›</button>');
 const position=document.createElement('output');position.id='media-position';position.setAttribute('aria-live','polite');dialog.querySelector('.dialog-heading').insertBefore(position,dialog.querySelector('.dialog-heading [data-close]'));
 function outside(event){const r=dialog.getBoundingClientRect();return event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom;}
 dialog.addEventListener('pointerdown',event=>{backdropPress=event.button===0&&event.target===dialog&&outside(event);});
 dialog.addEventListener('pointercancel',()=>{backdropPress=false;});
 dialog.addEventListener('click',event=>{const close=backdropPress&&event.target===dialog&&outside(event);backdropPress=false;if(close)dialog.close();});
 function pauseVideo(release=false){const video=dialog.querySelector('video');if(video){if(!video.paused)video.pause();if(release){video.removeAttribute('src');video.load();}}}
 function renderNavigation(){
  const index=navigation?.items.findIndex(x=>x.id===dialog.dataset.item)??-1;
  $('media-previous').disabled=navBusy||!navigation||index<0||(index===0&&navigation.page===0);
  $('media-next').disabled=navBusy||!navigation||index<0||navigation.page*navigation.count+index>=navigation.total-1;
  position.textContent=navigation&&index>=0?(navBusy?'Loading…':(navigation.page*navigation.count+index+1)+' of '+navigation.total):'';
 }
 const previousOpenMedia=openMedia;
 openMedia=function(item,context=null){
  ++navRevision;navBusy=false;pauseVideo(true);
  navigation=context?{...context,items:[...context.items]}:null;
  previousOpenMedia(item);
  const remove=document.createElement('button');remove.type='button';remove.className='danger';remove.id='media-delete';remove.textContent='Delete from Library…';remove.onclick=()=>confirmDelete([item.id],[mediaTitle(item)]);
  dialog.querySelector('.media-preview-column').append(remove);renderNavigation();
 };
 dialog.addEventListener('close',()=>{pauseVideo(true);++navRevision;navBusy=false;navigation=null;backdropPress=false;dialog.dataset.item='';});
 async function navigate(direction){
  if(!dialog.open||navBusy||!navigation)return;
  const index=navigation.items.findIndex(x=>x.id===dialog.dataset.item);
  if(index<0)return;
  const neighbor=index+direction;
  if(neighbor>=0&&neighbor<navigation.items.length){openMedia(navigation.items[neighbor],navigation);return;}
  const page=navigation.page+direction;
  if(page<0||page*navigation.count>=navigation.total)return;
  const serial=navRevision,context=navigation;navBusy=true;renderNavigation();
  try{
   const result=await api('/api/library?page='+page+'&count='+context.count+'&type='+encodeURIComponent(context.type)+'&search='+encodeURIComponent(context.search));
   if(serial!==navRevision||!dialog.open)return;
   if(!result.items?.length){navigation.total=result.total;notify('No more matching Library items.');return;}
   openMedia(direction>0?result.items[0]:result.items[result.items.length-1],{...context,items:result.items,page:result.page??page,total:result.total});
  }catch(error){if(serial===navRevision)notify(error.message);}
  finally{if(serial===navRevision){navBusy=false;renderNavigation();}}
 }
 $('media-previous').onclick=()=>navigate(-1);$('media-next').onclick=()=>navigate(1);
 document.addEventListener('keydown',event=>{
  if(!dialog.open||document.querySelector('dialog[open]:not(#media-dialog)')||event.altKey||event.ctrlKey||event.metaKey||event.target.closest('input,textarea,select,video,[contenteditable="true"]'))return;
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();navigate(event.key==='ArrowLeft'?-1:1);}
 });

 const selection=document.createElement('div');selection.className='library-selection';selection.setAttribute('aria-label','Library selection actions');
 selection.innerHTML='<label class="check"><input type="checkbox" id="library-select-page">Select this page</label><strong id="library-selected-count" role="status">0 selected</strong><button type="button" id="library-selection-clear">Clear selection</button><span class="selection-spacer"></span><button type="button" id="library-export-selected">Export selected ZIP</button><button type="button" class="danger" id="library-delete-selected">Delete selected…</button><button type="button" id="library-show-trash">Trash</button><span id="library-export-status" role="status"></span>';
 $('main-library').querySelector('.library-tools').after(selection);
 function selectionState(){
  const cards=[...$('lib-grid').querySelectorAll('.media-card')],inputs=cards.map(card=>card.querySelector('.library-select-item')).filter(Boolean);
  inputs.forEach(input=>{input.checked=selected.has(input.dataset.id);input.closest('.media-card').classList.toggle('media-selected',input.checked);});
  const count=inputs.filter(x=>x.checked).length;
  $('library-select-page').checked=inputs.length>0&&count===inputs.length;$('library-select-page').indeterminate=count>0&&count<inputs.length;$('library-select-page').disabled=!inputs.length;
  $('library-selected-count').textContent=selected.size+' selected';
  $('library-selection-clear').disabled=!selected.size;
  $('library-export-selected').disabled=!selected.size||exportBusy;
  $('library-delete-selected').disabled=!selected.size||deleteBusy;
 }
 function decorateCards(){
  for(const card of $('lib-grid').querySelectorAll('.media-card')){
   if(card.querySelector('.library-select-item'))continue;
   const id=card.querySelector('[data-thumbnail-id]')?.dataset.thumbnailId;if(!id)continue;
   const name=card.querySelector('.card-name')?.textContent||'Library item';
   const label=document.createElement('label');label.className='library-select-label';
   const input=document.createElement('input');input.type='checkbox';input.className='library-select-item';input.dataset.id=id;input.setAttribute('aria-label','Select '+name);
   input.onchange=()=>{if(input.checked){if(selected.size>=500){input.checked=false;notify('Select up to 500 items at once.');return;}selected.set(id,{name});}else selected.delete(id);selectionState();};
   label.append(input);label.addEventListener('click',event=>event.stopPropagation());card.prepend(label);
  }
  selectionState();
 }
 new MutationObserver(decorateCards).observe($('lib-grid'),{childList:true});decorateCards();
 $('library-select-page').onchange=event=>{
  for(const input of $('lib-grid').querySelectorAll('.library-select-item')){
   const name=input.closest('.media-card').querySelector('.card-name').textContent;
   if(event.target.checked){if(selected.size<500)selected.set(input.dataset.id,{name});}else selected.delete(input.dataset.id);
  }
  selectionState();
 };
 $('library-selection-clear').onclick=()=>{selected.clear();selectionState();};
 async function changed(deleted=[]){
  for(const id of deleted)selected.delete(id);
  if(deleted.includes(editorSource?.id)){editorSource=null;$('canvas-wrap').hidden=true;$('editor-empty').hidden=false;}
  if(deleted.includes(videoSource?.id))clearVideoSource();
  references=references.filter(item=>!deleted.includes(item.id));renderSources();
  try{
   if(current==='library'){
    const result=await api('/api/library?page=0&count=1&type='+encodeURIComponent($('lib-type').value)+'&search='+encodeURIComponent($('lib-search').value));
    libraryPage=Math.min(libraryPage,Math.max(0,Math.ceil(result.total/24)-1));await loadLibrary();
   }
  }catch(error){notify(error.message);}
  window.dispatchEvent(new Event('studio-library-changed'));selectionState();
 }
 document.body.insertAdjacentHTML('beforeend','<dialog id="library-delete-dialog"><div class="dialog-heading"><h2>Delete Library media?</h2><button type="button" data-close aria-label="Cancel deletion">×</button></div><p id="library-delete-description"></p><p class="notice">Files move to Studio Trash. Restore them later from Library → Trash. Media used by queued jobs must be removed from those jobs first.</p><p id="library-delete-error" role="alert"></p><div class="row"><button type="button" data-close>Cancel</button><button type="button" class="danger" id="library-delete-confirm">Move to Trash</button></div></dialog><dialog id="library-trash-dialog" class="wide"><div class="dialog-heading"><h2>Studio Trash</h2><button type="button" data-close aria-label="Close Trash">×</button></div><p>Deleted files remain recoverable here and still use disk space.</p><div id="library-trash-list"></div></dialog>');
 function confirmDelete(ids,names){
  pendingDelete=[...ids];$('library-delete-description').textContent=ids.length===1?'Move “'+names[0]+'” to Studio Trash?':'Move '+ids.length+' selected images/videos to Studio Trash?';
  $('library-delete-error').textContent='';$('library-delete-dialog').showModal();
 }
 $('library-delete-selected').onclick=()=>confirmDelete([...selected.keys()],[...selected.values()].map(x=>x.name));
 $('library-delete-dialog').addEventListener('cancel',event=>{if(deleteBusy)event.preventDefault();});
 $('library-delete-dialog').addEventListener('close',()=>{pendingDelete=null;});
 $('library-delete-confirm').onclick=async()=>{
  if(deleteBusy||!pendingDelete)return;
  const ids=[...pendingDelete];deleteBusy=true;selectionState();$('library-delete-error').textContent='';
  $('library-delete-dialog').querySelectorAll('button').forEach(button=>button.disabled=true);
  try{
   pauseVideo(true);
   const result=await api('/api/library/delete',{ids,confirmed:true});
   $('library-delete-dialog').close();
   if(dialog.open&&result.deleted.includes(dialog.dataset.item))dialog.close();
   await changed(result.deleted);notify(result.count+' item'+(result.count===1?'':'s')+' moved to Studio Trash.');
  }catch(error){$('library-delete-error').textContent=error.message;}
  finally{deleteBusy=false;$('library-delete-dialog').querySelectorAll('button').forEach(button=>button.disabled=false);selectionState();}
 };
 async function showTrash(){
  const box=$('library-trash-list');box.textContent='Loading Trash…';
  try{
   const result=await api('/api/library/trash');
   box.innerHTML=result.items.length?result.items.map(batch=>'<article class="trash-entry"><div><strong>'+esc(batch.count)+' item'+(batch.count===1?'':'s')+'</strong><small>'+esc(batch.created)+' · '+batch.names.map(esc).join(', ')+'</small></div><button type="button" data-restore="'+esc(batch.id)+'">Restore</button></article>').join(''):'<p class="notice">Studio Trash is empty.</p>';
   box.querySelectorAll('[data-restore]').forEach(button=>button.onclick=async()=>{
    box.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{const result=await api('/api/library/restore',{batch:button.dataset.restore});await changed();await showTrash();notify(result.count+' item'+(result.count===1?'':'s')+' restored.');}
    catch(error){notify(error.message);const message=document.createElement('p');message.className='notice';message.textContent=error.message;box.prepend(message);}
    finally{box.querySelectorAll('button').forEach(b=>b.disabled=false);}
   });
  }catch(error){box.textContent=error.message;}
 }
 $('library-show-trash').onclick=()=>{$('library-trash-dialog').showModal();showTrash();};
 $('library-export-selected').onclick=async()=>{
  if(exportBusy||!selected.size)return;
  const ids=[...selected.keys()];exportBusy=true;selectionState();$('library-export-status').textContent='Preparing ZIP…';
  try{
   const result=await api('/api/library/export',{ids});
   const link=document.createElement('a');link.href='/library-export/'+encodeURIComponent(result.id)+'?token='+encodeURIComponent(token);link.download=result.name;link.textContent='Download ZIP';
   $('library-export-status').replaceChildren(link);link.click();
  }catch(error){$('library-export-status').textContent=error.message;}
  finally{exportBusy=false;selectionState();}
 };
})();
