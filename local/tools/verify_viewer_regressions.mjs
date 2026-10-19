import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import * as THREE from '../viewer/node_modules/three/build/three.module.js';
import {createPlaybackController} from '../viewer/playback-controller.js';
import {createAccessoryAnimator} from '../viewer/character-motion.js';
import {disposeScene} from '../viewer/scene-resources.js';

const checks=[];
function player() {
  let state,errors=[];
  const audio={paused:true,plays:0,currentTime:17,pause(){this.paused=true;},async play(){this.plays++;this.paused=false;}};
  const controls=createPlaybackController({audio,atEnd:()=>false,rewind:()=>{},onState:s=>state=s,onError:e=>errors.push(e)});
  return {audio,controls,errors,get state(){return state;}};
}
{
  const p=player();await p.controls.play();const token=p.controls.beginLoad();
  assert.equal(p.audio.paused,true);assert.equal(p.state.wanted,true);
  await p.controls.endLoad(token);assert.equal(p.audio.paused,false);assert.equal(p.audio.currentTime,17);
  checks.push('Switch preserves playback intent and time');
}
{
  const p=player();await p.controls.play();const token=p.controls.beginLoad();
  p.controls.pause();p.audio.currentTime=28.226;await p.controls.endLoad(token);
  assert.equal(p.audio.paused,true);assert.equal(p.audio.plays,1);assert.equal(p.audio.currentTime,28.226);
  checks.push('Pause/seek during loading cancels automatic resume');
}
{
  const p=player();const token=p.controls.beginLoad();await p.controls.play();
  assert.equal(p.audio.plays,0);await p.controls.endLoad(token);assert.equal(p.audio.plays,1);
  const failed=p.controls.beginLoad();await p.controls.endLoad(failed,false);
  assert.equal(p.audio.paused,true);assert.equal(p.state.wanted,false);
  await p.controls.play();assert.equal(p.audio.paused,false);
  checks.push('Play waits for model; failure recovers to usable audio controls');
}
{
  const p=player();let reject;
  p.audio.play=()=>new Promise((_,r)=>{reject=r;});
  const pending=p.controls.play();p.controls.pause();reject(new Error('AbortError'));await pending;
  assert.equal(p.errors.length,0);assert.equal(p.state.wanted,false);
  checks.push('Cancelled play promise cannot restore playback or report a false error');
}
for(const role of ['allison','james','mark']) {
  const config=JSON.parse(await readFile(new URL(`../viewer/official-${role}/scene.json`,import.meta.url)));
  const channels=['eyeLookInLeft','eyeLookDownLeft','eyeLookOutRight','eyeLookUpRight','jawOpen'];
  for(const [prefix,values] of [['l_', [1,.7,0,0,0]],['r_', [0,0,1,.4,0]]]) {
    const eye=config.parts.find(p=>p.kind==='eye'&&p.name.startsWith(prefix));
    const cornea=config.parts.find(p=>p.kind==='cornea'&&p.name.startsWith(prefix));
    const meshes=[eye,cornea].map(spec=>{
      const mesh=new THREE.Object3D();createAccessoryAnimator(mesh,spec,config,channels)(values);mesh.updateMatrix();return mesh;
    });
    assert.deepEqual(meshes[0].matrix.elements,meshes[1].matrix.elements);
    const center=new THREE.Vector3(...eye.eyePivot);
    assert.ok(center.clone().applyMatrix4(meshes[0].matrix).distanceTo(center)<1e-8);
    assert.ok(Math.abs(meshes[0].rotation.x)+Math.abs(meshes[0].rotation.y)>0);
  }
  checks.push(`${role}: both corneas follow their iris around the same centre`);
}
{
  const scene=new THREE.Scene(),g=new THREE.BoxGeometry(),t=new THREE.Texture();
  const m=new THREE.MeshBasicMaterial({map:t});scene.add(new THREE.Mesh(g,m),new THREE.Mesh(g,m));
  const light=new THREE.DirectionalLight();scene.add(light);let shadow=0,env=0;
  light.shadow.dispose=()=>shadow++;scene.userData.dispose=()=>env++;
  const counts={g:0,m:0,t:0};for(const [key,obj] of Object.entries({g,m,t}))obj.addEventListener('dispose',()=>counts[key]++);
  disposeScene(scene);disposeScene(scene);
  assert.deepEqual(counts,{g:1,m:1,t:1});assert.equal(shadow,1);assert.equal(env,1);assert.equal(scene.children.length,0);
  checks.push('Shared geometry/textures, shadow maps and environment released exactly once');
}
const report={status:'PASS',checks};
await writeFile(new URL('../verification-viewer-regressions.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
