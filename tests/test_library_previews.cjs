'use strict';
// Exercise real preview helpers with deterministic network and timer fixtures.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
function fn(name){const start=source.indexOf('function '+name+'('),end=source.indexOf('\n',start);return source.slice(start,source.slice(start,end).trimEnd().endsWith('{')?source.indexOf('\n}',end)+2:end);}
let nextTimer=0,calls=[],status={};const timers=new Map();
const context={token:'session',current:'library',Map,encodeURIComponent,
 $:()=>({open:true}),setTimeout:(f,delay)=>{const id=++nextTimer;timers.set(id,{f,delay});return id;},
 clearTimeout:id=>timers.delete(id),api:async url=>{calls.push(url);return status;}};
vm.createContext(context);for(const name of ['thumbURL','thumbnails'])vm.runInContext(fn(name),context);
function picture(id){const classes=new Set();return {dataset:{thumbnailId:id},isConnected:true,alt:'',classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},removeAttribute(name){delete this[name];}};}
function grid(images){return {id:'lib-grid',isConnected:true,querySelectorAll:()=>images};}
async function tick(){assert(timers.size);const [id,{f}]=timers.entries().next().value;timers.delete(id);await f();}
(async()=>{
 const cached=picture('cached');context.thumbnails(grid([cached]),[{id:'cached',name:'Saved',thumbnail:{status:'ready',key:'hash'}}]);
 assert(cached.src.endsWith('&v=hash'));assert(!cached.src.includes('retry='));assert.equal(timers.size,0);assert.equal(calls.length,0);
 const a=picture('a'),b=picture('b'),container=grid([a,b]);
 context.thumbnails(container,[{id:'a',name:'A',thumbnail:{status:'pending'}},{id:'b',name:'B',thumbnail:{status:'pending'}}]);
 assert.equal(timers.size,1);assert.equal([...timers.values()][0].delay,200);
 status={a:{status:'ready',key:'one'},b:{status:'pending',key:'two'}};await tick();
 assert.equal(calls.length,1);assert(calls[0].includes('ids=a%2Cb'));assert(a.src.endsWith('&v=one'));assert(!b.src);
 status.b.status='ready';await tick();assert(b.src.endsWith('&v=two'));assert.equal(timers.size,0);
 a.onload();assert.equal(a.alt,'A');
 const missing=picture('missing');context.thumbnails(container,[{id:'a',thumbnail:{status:'pending'}},{id:'b',thumbnail:{status:'pending'}}]);
 // Replacing the grid cancels its previous poll and ignores stale work.
 container.querySelectorAll=()=>[missing];context.thumbnails(container,[{id:'missing',thumbnail:{status:'pending'}}]);assert.equal(timers.size,1);
 status={missing:{status:'unavailable'}};await tick();assert.equal(missing.alt,'Preview unavailable');assert.equal(timers.size,0);
 context.thumbnails(container,[{id:'missing',thumbnail:{status:'pending'}}]);const before=calls.length;context.current='video';await tick();assert.equal(calls.length,before);assert.equal(timers.size,0);
 console.log('LIBRARY_PREVIEWS_PASS: stable cached URLs, fast batched readiness, unavailable files, cancelled old pages, and navigation cleanup.');
})().catch(error=>{console.error(error);process.exitCode=1;});
