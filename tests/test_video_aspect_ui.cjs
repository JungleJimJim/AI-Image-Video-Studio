'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('assets/studio.js','utf8');
function fn(name){const start=source.indexOf('function '+name+'(');return source.slice(start,source.indexOf('\n}',start)+2);}
const options=[];
const shape={value:'custom',options,querySelector:()=>({remove:()=>{const i=options.findIndex(x=>x.value==='source');if(i>=0)options.splice(i,1);}}),insertAdjacentHTML:(_,html)=>{options.unshift({value:'source',html});}};
const controls={vmodel:{value:'wan22'},vshape:shape,vwidth:{value:'832'},vheight:{value:'480'},'v-size':{hidden:false}};
const context={$:id=>controls[id],videoSource:{id:'old'},selectVideoSource:item=>{context.videoSource=item;},renderSources:()=>{}};
vm.createContext(context);for(const name of ['videoAspectDimensions','adaptVideoAspect','clearVideoSource'])vm.runInContext(fn(name),context);
const proofs=[];
for(const model of ['wan13','wan22','ltx2','ref2va','minimax_h3'])for(const [width,height] of [[1600,900],[900,1600],[1200,900],[900,1200],[1024,1024],[2400,1000],[1,20]]){
 const result=context.videoAspectDimensions({width,height},model),[w,h]=result;
 const step=model==='wan13'?16:model==='ltx2'?64:32;
 assert.equal(w%step,0);assert.equal(h%step,0);assert(w>=144&&h>=144);
 assert(w<=(['ref2va','minimax_h3'].includes(model)?1344:1024));
 assert(h<=(['ref2va','minimax_h3'].includes(model)?1344:1024));
 if(width/height<=2.4&&width/height>=.4)assert(Math.abs(w/h/(width/height)-1)<.085,`${model}: ${width}:${height} -> ${w}:${h}`);
 proofs.push({model,source:[width,height],dimensions:[w,h]});
}
for(const image of [{width:0,height:1},{width:Infinity,height:4},{}])assert.equal(context.videoAspectDimensions(image,'wan22'),null);
context.adaptVideoAspect({width:1600,height:900});assert(shape.options[0].html.includes('16:9'));assert.equal(shape.value,'source');assert(controls['v-size'].hidden);
context.adaptVideoAspect({width:900,height:1600});assert(shape.options[0].html.includes('9:16'));assert.equal(shape.options.length,1);assert(Number(controls.vheight.value)>Number(controls.vwidth.value));
context.clearVideoSource();assert.equal(context.videoSource,null);assert.equal(shape.value,'custom');assert(!controls['v-size'].hidden);assert.equal(shape.options.length,0);
context.adaptVideoAspect({width:1200,height:900});assert(shape.options[0].html.includes('4:3'));
assert(source.includes("f('vshape','Aspect ratio'"));assert(source.includes('data-clear-video-source aria-label="Remove starting image"'));
if(process.env.STUDIO_ASPECT_PROOF)fs.writeFileSync(process.env.STUDIO_ASPECT_PROOF,JSON.stringify(proofs,null,2));
console.log('VIDEO_ASPECT_UI_PASS: source ratio, landscape/portrait/square, model alignment, extreme sizes, clear and replace; no engine.');
