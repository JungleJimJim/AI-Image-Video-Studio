'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
const start=source.indexOf('function syncVideoFrameControls('),end=source.indexOf('\n}',start)+2;
const controls={vmodel:{value:'ltx2'},vframes:{value:'241'},vframecount:{value:'161'},'v-custom-frames':{hidden:true}};
const context={$:id=>controls[id]};vm.createContext(context);vm.runInContext(source.slice(start,end),context);
function sync(model,preset){controls.vmodel.value=model;controls.vframes.value=preset;context.syncVideoFrameControls();}
sync('minimax_h3','124');assert.equal(controls.vframecount.disabled,true);assert.equal(controls.vframecount.value,'124');assert.equal(controls.vframecount.step,17);
sync('minimax_h3','custom');assert.equal(controls.vframecount.disabled,false);assert.equal(controls['v-custom-frames'].hidden,false);assert.equal(controls.vframecount.value,'124');
controls.vframecount.value='161';sync('minimax_h3','custom');assert.equal(controls.vframecount.value,'161'); // Visible custom input remains subject to validation.
sync('ref2va','243');assert.equal(controls.vframecount.disabled,true);assert.equal(controls.vframecount.value,'243');assert.equal(controls.vframecount.min,22);
sync('wan22','49');assert.equal(controls.vframecount.step,4);assert.equal(controls.vframecount.min,9);assert.equal(controls.vframecount.value,'49');
sync('ltx2','custom');assert.equal(controls.vframecount.step,8);assert.equal(controls.vframecount.disabled,false);
sync('wan13','81');assert.equal(controls.vframecount.step,4);assert.equal(controls.vframecount.disabled,true);
console.log('VIDEO_FRAME_CONTROLS_PASS: preset frames exclude hidden custom values; model switching restores MiniMax, Ref2VA, LTX and Wan constraints.');
