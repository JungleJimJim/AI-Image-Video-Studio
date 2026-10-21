'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const main=fs.readFileSync('assets/studio.js','utf8'),tools=fs.readFileSync('assets/studio-tools.js','utf8');
function fn(name){const start=main.search(new RegExp('^(?:async )?function '+name+'\\(','m')),line=main.indexOf('\n',start);assert(start>=0);return main.slice(start,main.slice(start,line).trimEnd().endsWith('{')?main.indexOf('\n}',line)+2:line);}
const a={id:'a',name:'A',width:512,height:512},b={id:'b',name:'B',width:512,height:512};
const controls={'vmodel':{value:'minimax_h3'},vmode:{value:'image'},'video-source-controls':{},'video-form':{},vframes:{value:'56'},vfps:{value:'24'},vshift:{value:'12'},vsampler:{value:'euler'},vscheduler:{value:'simple'},vaudio:{checked:true}};
let posts=[],notices=[],renders=0;
const ctx={state:{settings:{options:{source_image:'a'}},images:[a]},videoSource:null,videoSourceRevision:0,videoSourceSave:Promise.resolve(),
 $:id=>controls[id],api:async(path,body)=>{posts.push({path,body});return {};},notify:value=>notices.push(value),renderSources:()=>renders++,showPage:()=>{},
 videoModelChanged:()=>{},adaptVideoAspect:()=>{},generationOptions:()=>({model:'minimax_h3'}),submitQueue:async(kind,options)=>{ctx.submitted={kind,options};}};
vm.createContext(ctx);
for(const name of ['selectVideoSource','restoreVideoSource','sendImage'])vm.runInContext(fn(name),ctx);
vm.runInContext(tools.split('\n').find(line=>line.startsWith("$('video-form').onsubmit=")),ctx);
(async()=>{
 controls.vmodel.value='wan13';controls.vmode.value='text';await ctx.restoreVideoSource();assert.equal(controls.vmodel.value,'wan22');assert.equal(controls.vmode.value,'image');assert.equal(ctx.videoSource.id,'a');assert.equal(posts.length,0);assert.equal(renders,1);
 ctx.videoSource=null;ctx.state.settings.video_source_image='b';ctx.state.images=[];
 ctx.api=async(path,body)=>{posts.push({path,body});return {item:b};};await ctx.restoreVideoSource();assert.equal(ctx.videoSource.id,'b');assert.equal(posts.at(-1).path,'/api/library/b');
 ctx.videoSource=null;ctx.state.settings.video_source_image='a';let resolve;
 ctx.api=(path,body)=>body?(posts.push({path,body}),Promise.resolve({})):new Promise(done=>resolve=done);
 const delayed=ctx.restoreVideoSource();ctx.sendImage(b,'v');await ctx.videoSourceSave;resolve({item:a});await delayed;assert.equal(ctx.videoSource.id,'b');
 posts=[];ctx.api=async(path,body)=>{posts.push({path,body});return {};};ctx.sendImage(a,'video');ctx.sendImage(b,'v');await ctx.videoSourceSave;
 assert.deepEqual(posts.map(x=>x.body.video_source_image),['a','b']);
 await controls['video-form'].onsubmit({preventDefault(){}});assert.equal(ctx.submitted.kind,'video');assert.equal(ctx.submitted.options.source_image,'b');
 controls.vmode.value='text';await controls['video-form'].onsubmit({preventDefault(){}});assert.equal(ctx.submitted.options.source_image,'');
 ctx.videoSource=null;ctx.state.settings.video_source_image='';await ctx.restoreVideoSource();assert.equal(ctx.videoSource,null);
 ctx.state.settings.video_source_image='gone';ctx.api=async()=>{throw Error('missing');};await ctx.restoreVideoSource();assert.equal(ctx.videoSource,null);assert(notices.at(-1).includes('unavailable'));
 assert(main.match(/initialized=true;restoreVideoSource\(\)/));
 console.log('VIDEO_SELECTION_UI_PASS: reopen, older Library image, picker aliases, request source, rapid saves and restoration race; no engine.');
})().catch(error=>{console.error(error);process.exitCode=1;});
