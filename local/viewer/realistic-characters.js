import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { addDebraHair } from './debra-hair.js?v=multi-1';
import { addAllisonGroom } from './adapted-groom.js';

import { createAccessoryAnimator } from './character-motion.js';

export async function loadRealisticCharacter({role,renderer,scene,group,channels,onProgress}) {
  const response=await fetch(`official-${role}/scene.json`,{cache:'no-cache'});
  if(!response.ok)throw new Error(`${role} 资源加载失败`);
  const config=await response.json(),parts=[],textures=new Map();
  const label=config.label;
  const binary=async(url,Type=Float32Array)=>{if(!url)return null;const r=await fetch(url);if(!r.ok)throw new Error(url);return new Type(await r.arrayBuffer());};
  const texture=async(url,color=false)=>{
    if(!url)return null;
    if(!textures.has(url))textures.set(url,new THREE.TextureLoader().loadAsync(url).then(t=>{t.colorSpace=color?THREE.SRGBColorSpace:THREE.NoColorSpace;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());return t;}));
    return textures.get(url);
  };
  const environment=new RoomEnvironment(),pmrem=new THREE.PMREMGenerator(renderer),env=pmrem.fromScene(environment,.03);
  environment.dispose();pmrem.dispose();scene.environment=env.texture;scene.environmentIntensity=.35;scene.userData.dispose=()=>env.dispose();
  renderer.setClearColor(0x343e46);renderer.toneMappingExposure=.95;
  for(const spec of config.parts) {
    onProgress(`${label} · ${spec.kind==='skin'?'皮肤与表情':'眼睛与细节'}载入中`);
    const maps=config.materials?.[spec.material]||spec;
    const [base,normals,uv,indices,deltas,normalDeltas,map,normalMap,roughnessMap,alphaMap]=await Promise.all([
      binary(spec.base),binary(spec.normals),binary(spec.uv),binary(spec.indices,Uint32Array),binary(spec.morphs),binary(spec.morphNormals),
      texture(maps.map,true),texture(maps.normalMap),texture(maps.roughnessMap),texture(maps.alphaMap)
    ]);
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(base,3));g.setAttribute('normal',new THREE.BufferAttribute(normals,3));g.setAttribute('uv',new THREE.BufferAttribute(uv,2));g.setIndex(new THREE.BufferAttribute(indices,1));
    if(deltas&&spec.morphNames.length){
      g.morphAttributes.position=spec.morphNames.map((name,i)=>{const a=new THREE.BufferAttribute(deltas.subarray(i*base.length,(i+1)*base.length),3);a.name=name;return a;});
      g.morphAttributes.normal=spec.morphNames.map((_,i)=>new THREE.BufferAttribute(normalDeltas.subarray(i*base.length,(i+1)*base.length),3));g.morphTargetsRelative=true;
    }
    const material=new THREE.MeshPhysicalMaterial({map,normalMap,roughnessMap,alphaMap,alphaTest:alphaMap?.35:0,color:spec.kind==='brow'?0x34261e:0xffffff,roughness:spec.kind==='skin'?.78:.48,metalness:0,envMapIntensity:.55,side:THREE.DoubleSide});
    material.normalScale.set(.45,.45);material.ior=1.4;material.specularIntensity=.5;
    if(role==='james'&&spec.kind==='skin')material.color.set(0x9b7057);
    if(spec.kind==='eye'){material.roughness=.25;material.clearcoat=.7;}
    if(spec.kind==='cornea'){material.transparent=true;material.opacity=.09;material.depthWrite=false;material.roughness=.07;}
    const mesh=new THREE.Mesh(g,material);mesh.name=spec.name;mesh.frustumCulled=false;mesh.castShadow=!['eye','cornea'].includes(spec.kind);mesh.receiveShadow=true;group.add(mesh);
    const part={mesh,channelIndices:spec.morphNames.map(n=>channels.indexOf(n))};
    part.animate=createAccessoryAnimator(mesh,spec,config,channels);
    parts.push(part);
  }
  if(role==='allison')parts.push(...await addAllisonGroom({group,onProgress}));
  if(role==='james'||role==='mark')await addDebraHair(group,role);
  const mapped=config.mappedChannels;
  return {parts,config,mapped};
}
