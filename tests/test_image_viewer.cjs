'use strict';
// Run the actual viewer handlers with fake pixels; no browser, models or inference.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio-tools.js','utf8');
const code=source.slice(source.indexOf("const imageViewer="),source.indexOf('const originalOpenMedia='));
const nodes={},handlers={},messages=[];
for(const id of ['image-viewer','image-viewer-space','image-viewer-picture','image-viewer-name','image-zoom-level','image-zoom-in','image-zoom-out','image-zoom-fit','image-zoom-actual','image-viewer-close','help-dialog']){
 nodes[id]={style:{},open:false,clientWidth:800,clientHeight:600,classList:{add(){},remove(){}},
  addEventListener(name,callback,options){handlers[id+':'+name]={callback,options};},
  getBoundingClientRect(){return {left:20,top:40};},setPointerCapture(){},removeAttribute(){},
  showModal(){this.open=true;},close(){this.open=false;this.onclose?.();}};
}
nodes['image-viewer-picture'].naturalWidth=1000;nodes['image-viewer-picture'].naturalHeight=800;
const context={mediaTitle:item=>item.name,$:id=>nodes[id],window:{chrome:{webview:{postMessage:m=>messages.push(m)}}},
 document:{addEventListener:(name,callback)=>{handlers[name]=callback;},fullscreenElement:null},
 ResizeObserver:class{constructor(callback){}observe(){}},notify:()=>{},mediaURL:()=>'/image/fixture'};
vm.createContext(context);vm.runInContext(code,context);
const state=()=>JSON.parse(vm.runInContext('JSON.stringify(imageView)',context));
const near=(actual,expected)=>assert(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
context.openLibraryImage({name:'Fixture'});nodes['image-viewer-picture'].onload();
near(state().scale,.75);near(state().x,25);near(state().y,0);
assert.deepEqual(messages,['open-image-viewer']);
const wheel=handlers['image-viewer-space:wheel'];assert.equal(wheel.options.passive,false);
let prevented=0;
function scroll(delta,mode=0){wheel.callback({deltaY:delta,deltaMode:mode,clientX:420,clientY:340,preventDefault(){prevented++;}});}
scroll(-200);let zoomed=state();assert(zoomed.scale>.75);
// The same source pixel stays under the mouse when zooming away from the edges.
near((400-zoomed.x)/zoomed.scale,500);near((300-zoomed.y)/zoomed.scale,400);
scroll(200);near(state().scale,.75);assert.equal(prevented,2);
scroll(-10,1);assert(state().scale>.75);scroll(10,1);near(state().scale,.75);
context.zoomImageView(1e12);near(state().scale,16);
context.zoomImageView(1e-12);near(state().scale,.75/8);
nodes['image-zoom-actual'].onclick();near(state().scale,1);
nodes['image-zoom-in'].onclick();near(state().scale,1.25);
nodes['image-zoom-out'].onclick();near(state().scale,1);
context.zoomImageView(3);
nodes['image-viewer-space'].onpointerdown({button:0,pointerId:1,clientX:100,clientY:100,preventDefault(){}});
nodes['image-viewer-space'].onpointermove({pointerId:1,clientX:10000,clientY:-10000});
near(state().x,0);near(state().y,600-800*3);
nodes['image-viewer-space'].onpointerup();assert.equal(state().drag,null);
nodes['image-zoom-fit'].onclick();near(state().scale,.75);
let stopped=false;handlers.keydown({key:'Escape',stopImmediatePropagation(){stopped=true;},preventDefault(){}});
assert(stopped);assert.equal(nodes['image-viewer'].open,false);
assert.deepEqual(messages,['open-image-viewer','close-image-viewer']);
console.log('IMAGE_VIEWER_PASS: wheel zoom, cursor anchor, zoom limits, pan bounds, fit, actual size and Escape/native restoration.');
