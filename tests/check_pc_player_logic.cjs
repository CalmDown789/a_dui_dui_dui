// Unit tests for the exported controller and grayscale conversion. This is a
// simulated DOM, not a browser screenshot or end-to-end visual verification.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');

function load(file){
 const html=fs.readFileSync(file,'utf8');
 const raw=html.match(/<script id="playerData" type="application\/json">([\s\S]*?)<\/script>/)[1];
 const controller=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
 const parsed=JSON.parse(raw),elements=new Map(),events={},timers=new Map();let timerId=0;
 function element(id){
  if(!elements.has(id))elements.set(id,{
   id,textContent:'',value:id==='speed'?'2':'0',checked:id==='loop',style:{},classes:new Set(),
   classList:{add(name){elements.get(id).classes.add(name);}},
   getContext(){const item=this;return {
    createImageData(w,h){return {width:w,height:h,data:new Uint8ClampedArray(w*h*4)};},
    putImageData(pixels){item.pixels=pixels;},clearRect(){item.pixels=null;item.cleared=true;}
   };}
  });
  return elements.get(id);
 }
 element('playerData').textContent=raw;
 const body={classes:new Set(),classList:{add(name){body.classes.add(name);}}};
 const context=vm.createContext({document:{getElementById:element,body,addEventListener(name,callback){events[name]=callback;}},
  Uint8Array,Uint8ClampedArray,JSON,Number,String,Math,
  atob(encoded){return Buffer.from(encoded,'base64').toString('binary');},
  setTimeout(callback,delay){timers.set(++timerId,{callback,delay});return timerId;},
  clearTimeout(id){timers.delete(id);}
 });
 vm.runInContext(controller,context,{timeout:15000});
 return {parsed,elements,body,events,timers,context,execute(code){return vm.runInContext(code,context,{timeout:15000});}};
}

function verifyPixels(item,encoded){
 const input=Buffer.from(encoded,'base64'),pixels=item.pixels.data;
 assert.equal(pixels.length,input.length*4);
 for(let i=0;i<input.length;i++){
  const j=i*4;assert.equal(pixels[j],input[i]);assert.equal(pixels[j+1],input[i]);
  assert.equal(pixels[j+2],input[i]);assert.equal(pixels[j+3],255);
 }
}

const tests={};
const reference=load(process.argv[2]);
assert.equal(reference.parsed.mode,'software_reference');
assert(reference.body.classes.has('no-capture'));
assert(reference.elements.get('modeNotice').textContent.includes('不能据此判定板测通过'));
verifyPixels(reference.elements.get('inputCanvas'),reference.parsed.frames[0].input_b64);
verifyPixels(reference.elements.get('goldenCanvas'),reference.parsed.frames[0].golden_b64);
tests.reference_rgba_conversion='PASS';
for(let index=0;index<reference.parsed.frames.length;index++){
 reference.execute('seek('+index+')');
 verifyPixels(reference.elements.get('inputCanvas'),reference.parsed.frames[index].input_b64);
 verifyPixels(reference.elements.get('goldenCanvas'),reference.parsed.frames[index].golden_b64);
 assert(reference.elements.get('frameStatus').textContent.includes('frame ID '+String(reference.parsed.frames[index].frame_id).padStart(3,'0')));
}
tests.all_eight_reference_frames='PASS';reference.execute('seek(0)');
reference.elements.get('next').onclick();assert.equal(reference.execute('state.index'),1);
reference.elements.get('previous').onclick();assert.equal(reference.execute('state.index'),0);
reference.elements.get('position').oninput({target:{value:'7'}});assert.equal(reference.execute('state.index'),7);
reference.elements.get('next').onclick();assert.equal(reference.execute('state.index'),7);
reference.elements.get('first').onclick();assert.equal(reference.execute('state.index'),0);
tests.seek_and_boundaries='PASS';
reference.elements.get('play').onclick();assert(reference.execute('state.playing'));
assert.equal([...reference.timers.values()][0].delay,500);
reference.execute('tick()');assert.equal(reference.execute('state.index'),1);
reference.elements.get('play').onclick();assert(!reference.execute('state.playing'));
reference.elements.get('speed').value='4';reference.elements.get('play').onclick();
assert.equal([...reference.timers.values()].at(-1).delay,250);reference.execute('stop()');
reference.execute('seek(7); play(); tick()');assert.equal(reference.execute('state.index'),0);
reference.execute('stop(); seek(7)');reference.elements.get('loop').checked=false;
reference.execute('play(); tick()');assert(!reference.execute('state.playing'));
tests.play_pause_rate_loop_end='PASS';
reference.elements.get('view').onclick();assert.equal(reference.elements.get('goldenCanvas').style.width,'1920px');
reference.elements.get('view').onclick();assert.equal(reference.elements.get('goldenCanvas').style.width,'100%');
let prevented=false;reference.events.keydown({target:{matches(){return false;}},code:'ArrowLeft',preventDefault(){prevented=true;}});
assert(prevented);assert.equal(reference.execute('state.index'),6);
tests.full_resolution_and_keyboard='PASS';

const exact=load(process.argv[3]);assert.equal(exact.parsed.capture_report.status,'PASS');
assert(exact.elements.get('modeNotice').classes.has('pass'));
verifyPixels(exact.elements.get('captureCanvas'),exact.parsed.frames[0].capture_b64);
assert(exact.elements.get('evidence').textContent.includes('整组判定：PASS'));
tests.capture_comparison_pass='PASS';
for(let index=0;index<exact.parsed.frames.length;index++){
 exact.execute('seek('+index+')');verifyPixels(exact.elements.get('captureCanvas'),exact.parsed.frames[index].capture_b64);
}
tests.all_eight_capture_frames='PASS';

const failed=load(process.argv[4]);assert.equal(failed.parsed.capture_report.status,'FAIL');
assert(failed.elements.get('modeNotice').classes.has('fail'));
assert(failed.elements.get('evidence').textContent.includes('失配字节：1'));
tests.capture_failure_stays_fail='PASS';

const short=load(process.argv[5]);assert.equal(short.parsed.capture_report.status,'FAIL');
short.execute('seek(7)');
assert(short.elements.get('captureCanvas').cleared);
assert(short.elements.get('captureInfo').textContent.includes('拒绝绘制不完整画面'));
tests.incomplete_frame_not_rendered='PASS';
const arrival=load(process.argv[7]);
assert.equal(arrival.parsed.mode,'received_manifest');
assert.deepEqual(arrival.parsed.frames.map(frame=>frame.frame_id),[7,0]);
assert.equal(arrival.parsed.capture_report.status,'FAIL');
assert.equal(arrival.parsed.frames.length,2);
for(let index=0;index<2;index++){
 arrival.execute('seek('+index+')');
 verifyPixels(arrival.elements.get('captureCanvas'),arrival.parsed.frames[index].capture_b64);
 assert(arrival.elements.get('captureInfo').textContent.includes('arrival_'+index+'.bin'));
 assert(arrival.elements.get('evidence').textContent.includes('接收来源：software_fixture'));
 assert(arrival.elements.get('evidence').textContent.includes('整组判定：FAIL'));
}
tests.received_order_source_no_golden_substitution='PASS';
const report={status:'PASS',checks:tests,method:'Node VM simulated DOM unit tests; no real browser visual test',browser_visual_verified:false,board_capture_tested:false};
if(process.argv[6])fs.writeFileSync(process.argv[6],JSON.stringify(report,null,2)+'\n');
process.stdout.write(JSON.stringify(report,null,2)+'\n');
