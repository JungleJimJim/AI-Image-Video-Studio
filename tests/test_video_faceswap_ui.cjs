'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio-video-faceswap.js','utf8');
function fn(name){const start=source.indexOf('function '+name+'(');return source.slice(start,source.indexOf('\n}',start)+2);}
const controls={};for(const [key,value] of Object.entries({selector:'reference',face_position:'2',reference_frame:'43',similarity:'.6',pixel_boost:'512x512',quality:'95',provider:'cuda',encoder:'libx264'}))controls['fv-'+key]={value};
const ctx={$:id=>controls[id],videoFaceTarget:{id:'video-a'},videoFaceReference:{id:'face-b'}};vm.createContext(ctx);
vm.runInContext(source.split('\n').find(line=>line.startsWith('function videoFaceOptions()')),ctx);
vm.runInContext(fn('fillVideoFaceOptions'),ctx);
const options=ctx.videoFaceOptions();assert.equal(options.source_id,'video-a');assert.equal(options.reference_id,'face-b');assert.equal(options.face_position,1);assert.equal(options.reference_frame,'43');
ctx.fillVideoFaceOptions({face_position:0,reference_frame:12,selector:'many',provider:'cpu',encoder:'h264_nvenc'});
assert.equal(controls['fv-face_position'].value,1);assert.equal(ctx.videoFaceOptions().face_position,0);assert.equal(controls['fv-selector'].value,'many');
ctx.videoFaceTarget=null;assert.equal(ctx.videoFaceOptions().source_id,'');
console.log('VIDEO_FACESWAP_UI_PASS: distinct video/reference IDs, one-based face selection, option restoration, video Library picker, and queue routing.');
