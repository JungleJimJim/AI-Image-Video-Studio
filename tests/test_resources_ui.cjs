'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8'),start=source.indexOf('function renderResources()');
const meter={innerHTML:''},ctx={$:()=>meter,state:{resources:{updated:Date.now()/1000,gpu:{percent:0,used:8*1024**3,total:16*1024**3}}}};
vm.createContext(ctx);vm.runInContext(source.slice(start,source.indexOf('\n}',start)+2),ctx);
ctx.renderResources();assert(meter.innerHTML.includes('<span>0%</span>'));assert(meter.innerHTML.includes('8.0 / 16.0 GB'));
ctx.state.resources.gpu.percent=null;ctx.renderResources();assert(!meter.innerHTML.includes('null%'));assert(!meter.innerHTML.includes('<span>0%</span>'));assert(meter.innerHTML.includes('8.0 / 16.0 GB'));
ctx.state.resources.updated-=10;ctx.state.resources.gpu.percent=99;ctx.renderResources();assert(!meter.innerHTML.includes('99%'));assert(!meter.innerHTML.includes('8.0 / 16.0 GB'));
console.log('RESOURCE_UI_PASS: real zero, unavailable activity with valid VRAM, and stale telemetry are distinct.');
