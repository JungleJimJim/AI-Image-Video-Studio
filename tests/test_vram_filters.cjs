'use strict';
// Run against the processing-disabled fixture server; never start inference.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.argv[2]);await page.waitForFunction(()=>typeof initialized!=='undefined'&&initialized);
 await page.evaluate(()=>{showPage('models');state.packs.forEach(p=>p.ready=false);renderPacks();});
 const result=await page.evaluate(()=>{
  const assert=(value,message)=>{if(!value)throw Error(message)},cards=()=>[...document.querySelectorAll('#pack-grid .pack')],visible=()=>cards().filter(c=>!c.hidden);
  const total=cards().length;assert(total>30,'catalog populated');assert(cards().every(c=>c.querySelector('.vram-description')?.textContent.includes('VRAM:')),'VRAM description coverage');
  const jug=document.querySelector('.pack-check[value="juggernaut"]'),wan=document.querySelector('.pack-check[value="wan22"]');jug.checked=true;wan.checked=true;
  document.querySelector('[data-vram="8"]').click();const eight=visible().length;assert(eight>=7,'8 GB candidates');assert(visible().every(c=>c.dataset.vramTier==='8'),'8 GB only');assert(wan.checked&&wan.closest('.pack').hidden,'hidden selection retained');assert(jug.checked,'visible selection retained');assert(document.querySelector('[data-vram="8"]').getAttribute('aria-pressed')==='true','active filter');assert($('voice-model-card').hidden,'external voice hidden');
  document.querySelector('[data-vram="16"]').click();const sixteen=visible().length;assert(sixteen>eight,'16 GB includes lighter packs');assert(visible().every(c=>Number(c.dataset.vramTier)>0&&Number(c.dataset.vramTier)<=16),'16 GB tiers');assert(document.querySelector('.pack-check[value="ref2va"]').closest('.pack').hidden,'24 GB excluded');assert(document.querySelector('.pack-check[value="wamu"]').closest('.pack').hidden,'unverified excluded');
  state.packs[0].remaining=123;renderPacks();assert(document.querySelector('.pack-check[value="juggernaut"]').checked&&document.querySelector('.pack-check[value="wan22"]').checked,'refresh retains selections');assert(document.querySelector('.pack-check[value="wamu"]').closest('.pack').hidden,'refresh retains filter');
  document.querySelector('[data-vram="all"]').click();assert(visible().length===total,'all restored');assert(!$('voice-model-card').hidden,'external voice restored');
  document.querySelector('[data-vram="8"]').click();return {total,eight,sixteen,selection_preserved:true,refresh_preserved:true,inference_started:false};
 });
 assert.deepEqual(errors,[]);await page.screenshot({path:'outputs/vram-filters-preview.png',fullPage:true});fs.writeFileSync('outputs/vram-filters-validation.json',JSON.stringify({...result,errors},null,2));console.log('VRAM_FILTER_PASS',result);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});


