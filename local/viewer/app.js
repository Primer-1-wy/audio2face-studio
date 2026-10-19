import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { createFaceCapRetargeter } from './facecap-retarget.js';
import { FACE_STYLES,applyFaceStyle } from './face-styles.js';
import { loadOfficialClaire } from './official-claire.js?v=claire-official-3';
import { loadOfficialDebra } from './official-debra.js?v=debra-hair-1';
import { loadRealisticCharacter } from './realistic-characters.js?v=bugfix-1';

import { createPlaybackController } from './playback-controller.js';
import { disposeScene } from './scene-resources.js';

const $ = id => document.getElementById(id);
const audio = $('audio');
let data, currentTime = 0, dataset = 'blendshapes', selected = 0, parts = [];
let renderer, scene, camera, orbit, homePosition, homeTarget;
let resizeObserver, playback;
const meterNames = ['jawOpen','mouthFunnel','mouthPucker','mouthSmileLeft','eyeBlinkLeft'];
const meterRows = new Map();
const fail = message => { $('error').hidden = false; $('error').textContent = message; };
const clamp = (x,a,b) => Math.min(b,Math.max(a,x));

async function json(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}
async function binary(url, Type) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return new Type(await r.arrayBuffer());
}

function samples(time) {
  const p = clamp(time * data.fps,0,data.frameCount-1), a = Math.floor(p);
  return {a,b:Math.min(a+1,data.frameCount-1),f:p-a};
}
function value(group, channel, time = currentTime) {
  const {a,b,f} = samples(time), rows = data[group].values;
  return THREE.MathUtils.lerp(rows[a][channel],rows[b][channel],f);
}
function canvasContext(canvas) {
  const width = Math.max(1,canvas.clientWidth), height = Math.max(1,canvas.clientHeight);
  const dpr = Math.min(devicePixelRatio,2);
  if (canvas.width !== Math.round(width*dpr) || canvas.height !== Math.round(height*dpr)) {
    canvas.width = Math.round(width*dpr); canvas.height = Math.round(height*dpr);
  }
  const c = canvas.getContext('2d'); c.setTransform(dpr,0,0,dpr,0,0); c.clearRect(0,0,width,height);
  c.font = '11px -apple-system, sans-serif';
  return {c,w:width,h:height};
}
function drawCurve() {
  const {c,w,h} = canvasContext($('curve'));
  const points = data[dataset].values.map(row=>row[selected]);
  const min = Math.min(0,...points), max = Math.max(0.01,...points);
  const left = 39, right = w-8, top = 12, bottom = h-23;
  const x = t=>left+t/data.duration*(right-left);
  const y = v=>bottom-(v-min)/(max-min)*(bottom-top);
  for(let k=0;k<3;k++) {
    const v = min+(max-min)*k/2, py = y(v);
    c.strokeStyle='#e7ebe3'; c.lineWidth=1; c.beginPath();c.moveTo(left,py);c.lineTo(right,py);c.stroke();
    c.fillStyle='#66746c'; c.textAlign='right';c.fillText(v.toFixed(2),left-6,py+4);
  }
  c.strokeStyle='#52764a';c.lineWidth=1.7;c.beginPath();
  points.forEach((v,i)=>i?c.lineTo(x(data.times[i]),y(v)):c.moveTo(x(data.times[i]),y(v)));c.stroke();
  c.strokeStyle='#263b30';c.lineWidth=1;c.beginPath();c.moveTo(x(currentTime),top);c.lineTo(x(currentTime),bottom);c.stroke();
  c.fillStyle='#263b30';c.beginPath();c.arc(x(currentTime),y(value(dataset,selected)),3.5,0,Math.PI*2);c.fill();
  c.fillStyle='#66746c';c.textAlign='center';for(let k=0;k<=4;k++) { const s=k*data.duration/4;c.fillText(`${Number(s.toFixed(1))}s`,x(s),h-4); }
}
function drawWaveform() {
  const {c,w,h} = canvasContext($('waveform'));
  const peaks = data.audio.peaks;
  const peakValue = p=>Array.isArray(p)?Math.max(...p.map(Math.abs)):typeof p==='number'?Math.abs(p):Math.max(Math.abs(p.min||0),Math.abs(p.max||0));
  const peakMax = Math.max(0.001,...peaks.map(peakValue));
  const width = w*data.audio.duration/data.duration;
  const progress = currentTime/data.duration*w;
  peaks.forEach((peak,i)=>{
    const x = i/peaks.length*width, amp=peakValue(peak)/peakMax*(h-8)/2;
    c.fillStyle=x<progress?'#648756':'#d4dccd';
    c.fillRect(x,h/2-amp,Math.max(1,width/peaks.length-1),Math.max(1,amp*2));
  });
  c.fillStyle='#243d2d';c.fillRect(progress,0,1.5,h);
}
function update() {
  $('timeline').value=currentTime;
  $('frame-label').textContent=`Frame ${String(Math.min(data.frameCount-1,Math.floor(currentTime*data.fps+1e-6))).padStart(String(data.frameCount-1).length,'0')}`;
  $('time-label').textContent=`${currentTime.toFixed(3)} / ${data.duration.toFixed(3)} s`;
  $('current-value').textContent=value(dataset,selected).toFixed(4);
  document.querySelectorAll('#emotion-segments button').forEach(button=>{
    button.setAttribute('aria-pressed',String(currentTime>=Number(button.dataset.start)&&currentTime<=Number(button.dataset.end)));
  });
  for(const [name,el] of meterRows) {
    const v=value('blendshapes',data.blendshapes.names.indexOf(name));
    el.fill.style.width=`${clamp(v,0,1)*100}%`;el.value.textContent=v.toFixed(3);
  }
  const weights=data.blendshapes.names.map((_,i)=>value('blendshapes',i));
  for(const part of parts) {
    part.channelIndices.forEach((channel,i)=>{
      part.mesh.morphTargetInfluences[i]=channel<0?0:weights[channel];
    });
    part.retargeter?.apply(part.mesh.morphTargetInfluences);
    part.animate?.(weights);
  }
  drawCurve();drawWaveform();
}
function seek(time) {
  currentTime=clamp(time,0,data.lastFrameTime);
  audio.currentTime=Math.min(currentTime,data.audio.duration);
  update();
}
function pause() {playback.pause();}
function play() {return playback.play();}
function populateChannels() {
  $('channel').replaceChildren(...data[dataset].names.map((name,index)=>{
    const option = document.createElement('option');option.value=index;option.textContent=name;return option;
  }));
  selected=Math.max(0,data[dataset].names.indexOf(dataset==='blendshapes'?'jawOpen':'CTRL_C_jaw.translateY'));
  $('channel').value=selected;
}
function setupData() {
  audio.src=data.audio.url;
  playback=createPlaybackController({audio,
    atEnd:()=>audio.currentTime>=data.audio.duration-.002||currentTime>=data.lastFrameTime,
    rewind:()=>seek(0),
    onState:({wanted})=>{$('play').textContent=wanted?'暂停':'播放音频与动画';},
    onError:e=>fail(`音频播放失败：${e.message}`),
  });
  $('timeline').max=data.lastFrameTime;
  $('timeline-end').textContent=`0 秒 — ${data.duration} 秒`;
  $('frame-count').textContent=`${data.frameCount} / ${data.fps} fps`;
  $('audio-duration').textContent=`${data.audio.duration.toFixed(3)} 秒`;
  $('fbx-download').href=data.package.fbxUrl;
  $('audio-download').href=data.audio.url;
  $('source-label').textContent=`数据：${data.package.name} · 推理模型 Claire v2.3.1 · ${data.source.emotion==='timeline'?'人工情绪时间线':data.source.emotion}`;
  $('motion-note').textContent=`驱动来源：blendshapes.csv，每帧 68 路权重。${data.source.proceduralBlinks?'包内已叠加规则眨眼；情绪是人工设定的推理条件。':'按原值回放，帧间线性插值。'}`;
  for(const segment of data.emotionTrack?.segments||[]) {
    const button=document.createElement('button');button.type='button';
    button.textContent=`${segment.label} · ${segment.start.toFixed(1)}s`;
    button.dataset.start=segment.start;button.dataset.end=segment.end;
    button.onclick=()=>{pause();seek(segment.start);};$('emotion-segments').append(button);
  }
  populateChannels();
  for (const name of meterNames) {
    const row=document.createElement('div');row.className='meter';
    const label=document.createElement('span');label.textContent=name;
    const track=document.createElement('div');track.className='track';
    const fill=document.createElement('div');fill.className='fill';track.append(fill);
    const val=document.createElement('span');val.className='meter-value';
    row.append(label,track,val);$('meters').append(row);meterRows.set(name,{fill,value:val});
  }
  $('play').onclick=()=>playback.toggle();
  $('prev').onclick=()=>{pause();seek((Math.ceil(currentTime*data.fps-1e-7)-1)/data.fps);};
  $('next').onclick=()=>{pause();seek((Math.floor(currentTime*data.fps+1e-7)+1)/data.fps);};
  $('timeline').oninput=e=>{pause();seek(Number(e.target.value));};
  $('rate').onchange=e=>{audio.playbackRate=Number(e.target.value);};
  $('dataset').onchange=e=>{dataset=e.target.value;populateChannels();update();};
  $('channel').onchange=e=>{selected=Number(e.target.value);update();};
  audio.onended=()=>{if($('loop').checked){seek(0);play();}else{pause();currentTime=data.lastFrameTime;update();}};
  audio.onerror=()=>fail('无法加载 audio.wav。请通过 Start Preview.command 启动本机预览。');
  update();
}
async function setupMesh(mode='textured') {
  const style=FACE_STYLES[mode],isDebra=mode==='debra-official',newRole=['allison-official','james-official','mark-official'].includes(mode)?mode.replace('-official',''):null,isOfficial=mode==='claire-official'||isDebra||!!newRole,isFaceCap=mode!=='claire'&&!isOfficial;
  let framingBounds;
  const viewport=$('viewport');
  viewport.closest('.viewport-panel').classList.toggle('official-claire',isOfficial);
  $('model-select').disabled=true;$('mesh-status').textContent='载入中';
  $('compare-model').disabled=true;
  $('reset-camera').disabled=true;
  $('wireframe').disabled=true;
  $('model-note').textContent='正在载入角色…';
  $('debra-hair-control').hidden=!isDebra;
  $('debra-hair').disabled=true;
  if(resizeObserver) resizeObserver.disconnect();
  if(orbit) orbit.dispose();
  parts=[];camera=null;orbit=null;
  disposeScene(scene);
  if(renderer) {renderer.renderLists.dispose();renderer.clear();}
  else {renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});viewport.append(renderer.domElement);}
  renderer.shadowMap.enabled=false;
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.setClearColor(0xedf0e9);renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=isFaceCap?.88:1.15;
  renderer.domElement.setAttribute('aria-label',isDebra?'由当前服务器表情数据重定向驱动的 Debra 三维头模':isFaceCap?`${style?.label||'通用人脸'}：由服务器表情数据驱动的三维头模`:'由实际服务器表情曲线驱动的 NVIDIA Claire 三维头模');
  scene=new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xf4f7ef,0x495044,isOfficial?.8:isFaceCap?1.4:2.3));
  const key=new THREE.DirectionalLight(0xfff3e7,isFaceCap?2.5:3.2);key.position.set(-3,5,6);scene.add(key);
  const rim=new THREE.DirectionalLight(0xdce9fa,2);rim.position.set(4,3,-2);scene.add(rim);
  const fill=new THREE.DirectionalLight(0xffffff,.6);fill.position.set(3,0,5);scene.add(fill);
  const group=new THREE.Group();scene.add(group);
  if(isFaceCap) {
    const ktx=new KTX2Loader().setTranscoderPath('./node_modules/three/examples/jsm/libs/basis/').detectSupport(renderer);
    const loader=new GLTFLoader().setKTX2Loader(ktx).setMeshoptDecoder(MeshoptDecoder);
    const [gltf,skin]=await Promise.all([loader.loadAsync('models/facecap.glb'),new THREE.TextureLoader().loadAsync(`models/${style?.texture||'skin-albedo-v1.png'}`)]);
    ktx.dispose();
    if(style)for(const name of ['grp_eyeLeft','grp_eyeRight','grp_transform'])gltf.scene.getObjectByName(name)?.rotation.set(0,0,0);
    skin.flipY=false;skin.colorSpace=THREE.SRGBColorSpace;skin.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());
    const matched=new Set();
    gltf.scene.traverse(object=>{
      if(!object.isMesh)return;
      const original=object.material.map;
      if(original){skin.offset.copy(original.offset);skin.repeat.copy(original.repeat);skin.center.copy(original.center);skin.rotation=original.rotation;skin.wrapS=original.wrapS;skin.wrapT=original.wrapT;skin.updateMatrix();}
      object.material=mode==='anime'?new THREE.MeshToonMaterial({map:skin,side:THREE.DoubleSide}):object.material.clone();object.material.map=skin;object.material.color.set(0xffffff);if('roughness' in object.material){object.material.roughness=style?.roughness||.75;object.material.metalness=0;}object.material.needsUpdate=true;
      if(style && object.parent?.name?.startsWith('eye')) {
        // The sample splits iris and sclera into separate UV islands. Project
        // the new full-eye disk across the globe so the iris stays centered.
        const pos=object.geometry.attributes.position;
        const box=new THREE.Box3().setFromBufferAttribute(pos),center=box.getCenter(new THREE.Vector3());
        const radius=(box.max.x-box.min.x)/2,span=mode==='anime'?.048:mode==='cartoon'?.060:.085;
        const left=object.parent.name==='eyeLeft';
        const diskU=mode==='anime'?(left?.096:.903):mode==='cartoon'?(left?.098:.903):(left?.099:.900);
        const diskV=mode==='anime'?.910:mode==='cartoon'?.917:.926,values=new Float32Array(pos.count*2);
        for(let i=0;i<pos.count;i++) {
          const u=diskU+(pos.getX(i)-center.x)/radius*span,v=diskV+(pos.getZ(i)-center.z)/radius*span;
          values[i*2]=(u-skin.offset.x)/skin.repeat.x;values[i*2+1]=(v-skin.offset.y)/skin.repeat.y;
        }
        object.geometry.setAttribute('uv',new THREE.BufferAttribute(values,2));
      }
      object.frustumCulled=false;
      if(object.morphTargetDictionary) {
        const channelIndices=new Array(object.morphTargetInfluences.length).fill(-1);
        object.morphTargetInfluences.fill(0);
        for(const [name,index] of Object.entries(object.morphTargetDictionary)) {
          const canonical=name.replace(/^blendShape1\./,'').replace(/_L$/,'Left').replace(/_R$/,'Right');
          const channel=data.blendshapes.names.indexOf(canonical);channelIndices[index]=channel;
          if(channel>=0)matched.add(canonical);
        }
        parts.push({mesh:object,channelIndices});
      }
    });
    if(matched.size!==52)throw new Error(`人脸通道映射不完整：${matched.size}/52`);
    if(style)applyFaceStyle(gltf.scene,style);
    for(const part of parts)part.retargeter=createFaceCapRetargeter(part.mesh);
    // The sample's recorded animation is intentionally unused: only user CSV weights drive the face.
    group.add(gltf.scene);
    $('mesh-status').textContent=`${style?.label||'皮肤贴图'} · 52 路面部形变`;
    $('model-note').textContent=style?`${style.label}风格试作 · 调整脸型 + AI 贴图 + 立体发型，共用 Face Cap 表情拓扑。已适配嘴型；头发、眼球和牙齿为静态参考。`:'Face Cap 通用头模 + AI 皮肤，已收敛夸张嘴型并适配唇部接触。曲线显示原始数据；完整 68 路可切换 Claire。眼球与牙齿为静态参考。';
  } else if(newRole) {
    const result=await loadRealisticCharacter({role:newRole,renderer,scene,group,channels:data.blendshapes.names,onProgress:text=>$('mesh-status').textContent=text});
    parts=result.parts;framingBounds=result.config.bounds;
    renderer.domElement.setAttribute('aria-label',`${result.config.label}：由当前表情数据驱动的写实角色`);
    $('mesh-status').textContent=`${result.config.label} · ${result.mapped}/68 路适配`;
    $('model-note').textContent=newRole==='allison'?'Allison · 官方皮肤与面部网格，52 路面部动作经绑定转移；牙齿、舌头与发型由 Claire 资产适配。共用当前音频和时间轴。':`${result.config.label} · 官方脸型与 68 路原生表情，搭配适配皮肤和本地短发；这是本地外观版本，并非官方完整外观包。`;
  } else if(isDebra) {
    const result=await loadOfficialDebra({renderer,scene,group,channels:data.blendshapes.names,onProgress:text=>$('mesh-status').textContent=text});
    parts=result.parts;
    $('mesh-status').textContent=`Debra 原生表情 · ${result.mapped}/68 路适配`;
    result.hair.visible=$('debra-hair').checked;
    $('debra-hair').disabled=false;
    $('debra-hair').onchange=()=>{result.hair.visible=$('debra-hair').checked;};
    $('model-note').textContent=`NVIDIA 示例中的 Reallusion Debra · 原生皮肤与表情，搭配本地制作的深棕黑短卷发。可关闭发型对比；共用当前音频与时间轴，适配 ${result.mapped}/68 路。`;
  } else if(isOfficial) {
    const result=await loadOfficialClaire({renderer,scene,group,channels:data.blendshapes.names,onProgress:text=>$('mesh-status').textContent=text});
    parts=result.parts;
    $('mesh-status').textContent='官方皮肤 + 毛发 · 68 路形变';
    $('model-note').textContent='NVIDIA Claire 官方模型、皮肤、眼睛与毛发。WebGL 材质和毛发精简预览；完整 USD / EXR 已保存在本地。下牙和舌头附加近似下颌运动，眼球保持正视。';
  } else {
  const config=await json('mesh.json');
  for(const spec of config.parts) {
    const [base,indices,deltas]=await Promise.all([
      binary(spec.base,Float32Array),binary(spec.indices,Uint32Array),
      spec.morphs?binary(spec.morphs,Float32Array):Promise.resolve(new Float32Array())
    ]);
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(base,3));geometry.setIndex(new THREE.BufferAttribute(indices,1));
    geometry.computeVertexNormals();
    const names=spec.morphNames||[];
    if(names.length) {
      geometry.morphAttributes.position=names.map((name,i)=>{
        const attribute=new THREE.BufferAttribute(deltas.subarray(i*base.length,(i+1)*base.length),3);attribute.name=name;return attribute;
      });geometry.morphTargetsRelative=true;
    }
    const type=spec.name.toLowerCase();
    const color=type.includes('tongue')?0xad7368:type.includes('teeth')?0xe7decc:type.includes('eye')?0xd8d5c8:0xc5ae96;
    const material=new THREE.MeshStandardMaterial({color,roughness:.73,metalness:0,side:THREE.DoubleSide});
    if(type.includes('cornea')) { material.transparent=true;material.opacity=.08;material.depthWrite=false; }
    const mesh=new THREE.Mesh(geometry,material);mesh.name=spec.name;mesh.frustumCulled=false;group.add(mesh);
    parts.push({mesh,channelIndices:names.map(name=>data.blendshapes.names.indexOf(name))});
  }
  $('mesh-status').textContent='68 路形变 · 已载入';
  $('model-note').textContent='NVIDIA Claire 表情预览 · 皮肤与舌头受曲线驱动，眼球与牙齿为静态参考。MetaHuman 效果需在 Unreal 角色上查看。';
  }
  // Use neutral positions to frame the face; morph envelopes can be much larger.
  const bounds=new THREE.Box3();
  group.updateMatrixWorld(true);
  group.traverse(mesh=>{
    if(!mesh.isMesh)return;
    if(framingBounds)return;
    if(isOfficial&&!mesh.name.startsWith(isDebra?'CC_Game_Body':'c_headWatertight'))return;
    const box=new THREE.Box3().setFromBufferAttribute(mesh.geometry.attributes.position).applyMatrix4(mesh.matrixWorld);bounds.union(box);
  });
  if(framingBounds){bounds.min.fromArray(framingBounds.min);bounds.max.fromArray(framingBounds.max);}
  if(isOfficial&&!isDebra)bounds.max.y+=3.5;
  if(isDebra)bounds.max.y+=3;
  const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
  if(isOfficial) {
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    key.castShadow=true;key.position.copy(center).add(new THREE.Vector3(-40,60,80));
    key.target.position.copy(center);scene.add(key.target);
    key.shadow.mapSize.set(2048,2048);key.shadow.camera.left=-25;key.shadow.camera.right=25;
    key.shadow.camera.top=25;key.shadow.camera.bottom=-25;key.shadow.camera.near=1;key.shadow.camera.far=200;
    key.shadow.bias=-.00015;key.shadow.normalBias=.025;
  }
  camera=new THREE.PerspectiveCamera(29,1,Math.max(size.y/1000,.01),Math.max(size.y*30,1000));
  homeTarget=center.clone();
  homePosition=center.clone().add(new THREE.Vector3(0,size.y*.015,Math.max(size.y*2.05,size.x*2.0)));
  camera.position.copy(homePosition);orbit=new OrbitControls(camera,renderer.domElement);
  orbit.target.copy(homeTarget);orbit.enableDamping=true;orbit.dampingFactor=.08;
  orbit.minDistance=size.y*.7;orbit.maxDistance=size.y*5;orbit.update();
  $('reset-camera').onclick=()=>{if(!camera||!orbit)return;camera.position.copy(homePosition);orbit.target.copy(homeTarget);orbit.update();};
  const setWireframe=()=>group.traverse(mesh=>{if(mesh.isMesh)mesh.material.wireframe=$('wireframe').checked;});
  $('wireframe').onchange=setWireframe;setWireframe();
  $('mesh-message').hidden=true;$('model-select').disabled=false;$('error').hidden=true;
  $('reset-camera').disabled=false;$('wireframe').disabled=false;
  const resize=()=>{const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();};
  resizeObserver=new ResizeObserver(resize);resizeObserver.observe(viewport);resize();update();
  $('compare-model').hidden=!isOfficial;
  $('compare-model').disabled=false;
  const nextMode=newRole==='allison'?'james-official':newRole==='james'?'mark-official':newRole==='mark'?'claire-official':isDebra?'allison-official':'debra-official';
  const nextLabel=({'james-official':'James','mark-official':'Mark','allison-official':'Allison','claire-official':'Claire','debra-official':'Debra'})[nextMode];
  $('compare-model').textContent=`切换至 ${nextLabel}`;
  $('compare-model').onclick=()=>{$('model-select').value=nextMode;$('model-select').dispatchEvent(new Event('change'));};
  const url=new URL(location.href);url.searchParams.set('asset',isOfficial?'official-'+mode.replace('-official',''):mode);history.replaceState(null,'',url);
}
function tick() {
  requestAnimationFrame(tick);
  if(data&&!audio.paused){currentTime=clamp(audio.currentTime,0,data.lastFrameTime);update();}
  if(renderer&&camera){orbit.update();renderer.render(scene,camera);}
}
try {
  data=await json('data.json');setupData();
  const requestedAsset=new URLSearchParams(location.search).get('asset');
  const requestedMode=({'official-debra':'debra-official','official-claire':'claire-official','official-allison':'allison-official','official-james':'james-official','official-mark':'mark-official'})[requestedAsset]||requestedAsset;
  if([...$('model-select').options].some(option=>option.value===requestedMode))$('model-select').value=requestedMode;
  new ResizeObserver(()=>update()).observe($('curve'));
  const loadModel=async()=>{
    const token=playback.beginLoad();let success=false;
    try {await setupMesh($('model-select').value);success=true;}
    catch(e) {
      parts=[];camera=null;orbit?.dispose();orbit=null;
      resizeObserver?.disconnect();disposeScene(scene);renderer?.renderLists.dispose();
      renderer?.clear();
      $('mesh-message').hidden=false;$('mesh-message').textContent='3D 模型载入失败；可重新选择角色，或播放音频查看曲线。';
      $('model-note').textContent='请选择角色重试。';
      $('mesh-status').textContent='模型未就绪';$('model-select').disabled=false;fail(e.message);
    } finally {await playback.endLoad(token,success);}
  };
  $('model-select').onchange=loadModel;loadModel();
  tick();
} catch(e){fail(`数据载入失败：${e.message}`);}
