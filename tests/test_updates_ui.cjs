'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio-updates.js','utf8').replaceAll('\r\n','\n');
const controls={};for(const id of ['check-updates','update-version','update-status','install-update','update-install-hint','update-title','update-description','update-notes','update-dialog'])controls[id]={};
controls['update-dialog'].showModal=()=>{controls['update-dialog'].open=true;};controls['update-dialog'].close=()=>{controls['update-dialog'].open=false;};
const offer={status:'checked',current:'1.6.0',version:'1.6.1',available:true,can_install:true,bytes:1024**2,ticket:'server-ticket',notes:'<script>untrusted notes</script>',url:'https://github.com/JungleJimJim/AI-Image-Video-Studio/releases/tag/v1.6.1'};
const requests=[],context={$:id=>controls[id],state:{busy:false,updates:{status:'idle',current:'1.6.0',can_install:true}},updateOffer:null,updateCheckPending:false,updateInstallPending:false,
 notify:()=>{},api:async path=>{requests.push(path);return {...offer};},action:async(path,body)=>{requests.push({path,body});}};
vm.createContext(context);
for(const name of ['renderStudioUpdates','showUpdateOffer']){const start=source.indexOf('function '+name+'('),lineEnd=source.indexOf('\n',start),line=source.slice(start,lineEnd),end=line.endsWith('{')?source.indexOf('\n}',lineEnd)+2:lineEnd;vm.runInContext(source.slice(start,end),context);}
for(const line of source.split('\n').filter(line=>line.startsWith("$('check-updates').onclick")||line.startsWith("$('install-update').onclick")))vm.runInContext(line,context);
(async()=>{
 context.renderStudioUpdates();assert.equal(controls['check-updates'].disabled,false);assert.equal(controls['update-version'].textContent,'Installed version: 1.6.0');assert.equal(controls['update-status'].hidden,true);assert(!source.includes('GitHub'));assert(!source.includes('github.com/'));assert(!source.includes('update-release'));
 context.state.busy=true;await controls['check-updates'].onclick();assert.equal(controls['update-dialog'].open,true);assert.equal(requests.length,1);assert.equal(controls['install-update'].disabled,true);assert.equal(controls['update-notes'].textContent,offer.notes);assert.equal(controls['update-title'].textContent,'Install Studio 1.6.1?');
 await controls['install-update'].onclick();assert.equal(requests.length,1);
 context.state.busy=false;context.renderStudioUpdates();assert.equal(controls['install-update'].disabled,false);assert.equal(controls['check-updates'].disabled,false);
 await controls['install-update'].onclick();assert.equal(requests.length,2);assert.equal(requests[1].path,'/api/updates/install');assert.equal(requests[1].body.ticket,'server-ticket');assert.equal(Object.keys(requests[1].body).length,1);assert.equal(controls['update-dialog'].open,false);assert.equal(controls['check-updates'].disabled,true);
 context.state.updates={...offer,status:'error',error:'Fixture download failed'};context.renderStudioUpdates();assert.equal(controls['check-updates'].disabled,false);assert(controls['update-status'].textContent.includes('Fixture download failed'));
 console.log('UPDATES_UI_PASS: check only, confirmation, busy guard, server ticket, plain-text notes and retry after failure.');
})().catch(error=>{console.error(error);process.exitCode=1;});
