'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
const start=source.indexOf('async function saveCompletionSound('),end=source.indexOf('\n}',start)+2;
const controls={'completion-sound':{checked:false,disabled:false},'sound-status':{textContent:''}};
let submission;const context={$:id=>controls[id],state:{settings:{output:'unchanged',completion_sound:true}},action:async(path,data)=>{submission={path,data};}};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
(async()=>{
 await context.saveCompletionSound();assert.equal(submission.path,'/api/settings');assert.equal(submission.data.completion_sound,false);assert.equal(Object.keys(submission.data).length,1);
 assert.equal(context.state.settings.completion_sound,false);assert.equal(context.state.settings.output,'unchanged');assert.equal(controls['completion-sound'].disabled,false);assert(controls['sound-status'].textContent.includes('muted'));
 controls['completion-sound'].checked=true;context.action=async()=>{throw Error('not saved');};await context.saveCompletionSound();assert.equal(controls['completion-sound'].checked,false);assert.equal(controls['completion-sound'].disabled,false);
 console.log('COMPLETION_SOUND_UI_PASS: immediate preference save, folder preservation, mute feedback, and rollback after failed save.');
})().catch(error=>{console.error(error);process.exitCode=1;});
