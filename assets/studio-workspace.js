'use strict';
// Workspace chrome reuses existing pages, media APIs and tools. It never queues a job.
(() => {
 const body=document.body,main=document.querySelector('main');
 const icons={
  images:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
  editor:'<path d="m4 16 11-11 4 4L8 20H4zM13 7l4 4M15 5l2-2 4 4-2 2"/>',
  canvas:'<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M7 1v6M1 7h6M17 17h6M17 17v6M8 8h8v8H8z"/>',
  video:'<rect x="2" y="5" width="14" height="14" rx="2"/><path d="m16 10 6-4v12l-6-4M7 9l5 3-5 3z"/>',
  upscale:'<path d="M4 10V4h6M14 4h6v6M20 14v6h-6M10 20H4v-6M4 4l6 6M20 20l-6-6"/>',
  avatar:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3M8 21v-4M16 21v-4"/>',
  voice:'<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  faceswap:'<path d="M4 9V4h5M20 15v5h-5M4 4l4 4M20 20l-4-4"/><circle cx="13" cy="10" r="4"/><path d="M7 20a6 6 0 0 1 11-4"/>',
  library:'<rect x="3" y="5" width="18" height="16" rx="1"/><path d="M7 5V2h10v3M3 10h18M8 15h8"/>',
  models:'<path d="m12 2 9 5v10l-9 5-9-5V7zM3 7l9 5 9-5M12 12v10M7 4l10 6"/>',
  loras:'<path d="m12 3 10 5-10 5L2 8zM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  settings:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
  queue:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>'
 };
 const svg=id=>'<svg viewBox="0 0 24 24" aria-hidden="true">'+(icons[id]||icons.settings)+'</svg>';
 const brand=document.createElement('span');brand.className='workspace-brand';brand.textContent='A.I. Image & Video Studio';document.querySelector('.brand-lockup').append(brand);
 const options=document.createElement('div');options.className='workspace-options';options.setAttribute('aria-label','Workspace controls');
 options.innerHTML='<button type="button" id="workspace-focus" aria-pressed="false" title="Hide the properties dock and recent media for a larger preview">Focus</button><button type="button" id="workspace-filmstrip-toggle" aria-pressed="true" aria-controls="workspace-filmstrip">Recent media</button><span class="options-spacer"></span><label class="workspace-width">Properties width <input id="workspace-dock-width" type="range" min="280" max="460" step="10" value="340" aria-label="Properties panel width"></label><span class="options-divider"></span><button type="button" id="workspace-reset" title="Restore panel width, recent media and full workspace">Reset workspace</button>';
 document.querySelector('.top').after(options);
 const desk=document.createElement('div');desk.className='studio-desk';main.before(desk);
 const rail=document.createElement('nav');rail.className='workspace-rail';rail.setAttribute('aria-label','Tool shortcuts');
 rail.innerHTML=[...$('navigation').querySelectorAll('[data-page]')].map(button=>{const id=button.dataset.page,title=pages[id][0];return`<button type="button" data-workspace-go="${id}" title="${esc(title)}" aria-label="${esc(title)}">${svg(id)}</button>`;}).join('');desk.append(rail,main);
 document.querySelectorAll('.workspace').forEach(workspace=>{
  if(!workspace.querySelector(':scope > .preview'))return;
  workspace.classList.add('workspace-docked');
  const dock=workspace.querySelector(':scope > .controls');if(!dock)return;
  const title=document.createElement('div');title.className='dock-heading';
  const id=workspace.closest('.page')?.id;title.textContent=({'page-images':'Generate image','page-editor':'Edit properties','page-video':'Generate video','page-upscale':'Enhance properties','page-avatar':'Talking avatar','page-voice':'Voice properties','page-faceswap':'Faceswap properties'})[id]||'Properties';dock.prepend(title);
 });
 const filmstrip=document.createElement('section');filmstrip.id='workspace-filmstrip';filmstrip.className='workspace-filmstrip';filmstrip.setAttribute('aria-label','Recent library media');
 filmstrip.innerHTML='<div class="filmstrip-heading"><strong>Library</strong><button type="button" data-recent-type="all" aria-pressed="true">All media</button><button type="button" data-recent-type="image" aria-pressed="false">Images</button><button type="button" data-recent-type="video" aria-pressed="false">Videos</button><span class="filmstrip-count" id="workspace-recent-count"></span><button type="button" id="workspace-recent-refresh" title="Refresh recent media">Refresh</button><button type="button" data-workspace-go="library">Open Library ↗</button></div><div id="workspace-recent" class="filmstrip-items"><span class="filmstrip-empty">Your recent images and videos appear here.</span></div>';
 document.querySelector('.status').before(filmstrip);
 const preferenceKey='studio.canvas-workspace.v1';let prefs={width:340,filmstrip:true},focus=false,recentType='all',request=0,revision,loading=false;
 try{const saved=JSON.parse(localStorage.getItem(preferenceKey)||'null');if(saved){if(Number.isFinite(saved.width))prefs.width=Math.max(280,Math.min(460,saved.width));prefs.filmstrip=saved.filmstrip!==false;}}catch{}
 function save(){try{localStorage.setItem(preferenceKey,JSON.stringify(prefs));}catch{}}
 function refit(){requestAnimationFrame(()=>{fitCanvas();if(current==='canvas'&&typeof cvFit==='function')cvFit();});}
 function layout(){body.classList.toggle('workspace-focus',focus);body.classList.toggle('filmstrip-hidden',!prefs.filmstrip);body.style.setProperty('--dock-width',prefs.width+'px');$('workspace-focus').setAttribute('aria-pressed',String(focus));$('workspace-filmstrip-toggle').setAttribute('aria-pressed',String(prefs.filmstrip));$('workspace-dock-width').value=prefs.width;refit();}
 function syncPage(){body.dataset.workspacePage=current;for(const button of rail.querySelectorAll('[data-workspace-go]')){const selected=button.dataset.workspaceGo===current;button.classList.toggle('active',selected);if(selected)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}for(const button of $('navigation').querySelectorAll('[data-page]')){if(button.dataset.page===current)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}}
 document.querySelectorAll('[data-workspace-go]').forEach(button=>button.onclick=()=>{focus=false;layout();showPage(button.dataset.workspaceGo);syncPage();});
 new MutationObserver(()=>{focus=false;layout();syncPage();}).observe($('page-title'),{childList:true});
 $('workspace-focus').onclick=()=>{focus=!focus;layout();if(!focus)refreshRecent();};
 $('workspace-filmstrip-toggle').onclick=()=>{prefs.filmstrip=!prefs.filmstrip;save();layout();if(prefs.filmstrip)refreshRecent();};
 $('workspace-dock-width').oninput=event=>{prefs.width=Number(event.target.value);layout();save();};
 $('workspace-reset').onclick=()=>{prefs={width:340,filmstrip:true};focus=false;save();layout();refreshRecent();};
 async function refreshRecent(){
  if(!prefs.filmstrip||focus||document.hidden)return;const serial=++request;loading=true;
  const grid=$('workspace-recent');
  try{
   const result=await api(`/api/library?page=0&count=16&type=${recentType}&search=`);if(serial!==request)return;
   const items=result.items||[];
   grid.innerHTML=items.length?items.map(item=>`<button type="button" class="filmstrip-item" title="Open ${esc(item.name)}" aria-label="Open ${esc(item.name)}"><img data-thumbnail-id="${esc(item.id)}" data-thumb="${thumbURL(item)}" alt="${esc(item.name)}" loading="lazy">${item.media_type==='video'?'<span class="filmstrip-video">VIDEO</span>':''}<span>${esc(item.name)}</span></button>`).join(''):'<span class="filmstrip-empty">No matching media yet. Generate or import media to build your Library.</span>';
   grid.querySelectorAll('.filmstrip-item').forEach((button,index)=>button.onclick=()=>openMedia(items[index]));
   thumbnails(grid,items);$('workspace-recent-count').textContent=`${result.total??items.length} items`;
  }catch(error){if(serial===request){grid.innerHTML='<span class="filmstrip-empty">Library unavailable. Use Refresh to try again.</span>';$('workspace-recent-count').textContent='';}}
  finally{if(serial===request)loading=false;}
 }
 filmstrip.querySelectorAll('[data-recent-type]').forEach(button=>button.onclick=()=>{recentType=button.dataset.recentType;filmstrip.querySelectorAll('[data-recent-type]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));refreshRecent();});
 $('workspace-recent-refresh').onclick=refreshRecent;
 function checkRecent(){if(state&&state.library_revision!==revision&&!loading&&prefs.filmstrip&&!focus&&!document.hidden){revision=state.library_revision;refreshRecent();}}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshRecent();});setInterval(checkRecent,2500);
 layout();syncPage();refreshRecent();
})();
