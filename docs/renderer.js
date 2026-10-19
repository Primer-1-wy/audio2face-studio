import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

const binary=async(url,Type=Float32Array)=>{
  const r=await fetch(url);if(!r.ok)throw new Error(`头模资源：HTTP ${r.status}`);
  return new Type(await r.arrayBuffer());
};

export async function createFaceViewer(host,url){
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
  renderer.setClearColor(0x343e46);renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.05;host.append(renderer.domElement);
  const scene=new THREE.Scene(),group=new THREE.Group();scene.add(group);group.position.y=-143;
  const camera=new THREE.PerspectiveCamera(38,1,.1,300);
  const controls=new OrbitControls(camera,renderer.domElement);
  controls.enableDamping=true;controls.minDistance=22;controls.maxDistance=100;
  const reset=()=>{camera.position.set(0,4,53);controls.target.set(0,.5,0);controls.update();};reset();
  const ambient=new THREE.HemisphereLight(0xe8f2ff,0x6b6056,2.0);scene.add(ambient);
  const key=new THREE.DirectionalLight(0xffeddf,3);key.position.set(-15,25,30);scene.add(key);
  const fill=new THREE.DirectionalLight(0xd6e9ff,1.3);fill.position.set(18,10,14);scene.add(fill);
  const rim=new THREE.DirectionalLight(0xe1eaff,2);rim.position.set(5,20,-20);scene.add(rim);
  const environment=new RoomEnvironment(),pmrem=new THREE.PMREMGenerator(renderer);
  const env=pmrem.fromScene(environment,.04);scene.environment=env.texture;scene.environmentIntensity=.25;
  environment.dispose();pmrem.dispose();
  const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();};
  const observer=new ResizeObserver(resize);observer.observe(host);resize();
  const response=await fetch(url);if(!response.ok)throw new Error('无法读取 v3 头模清单');
  const config=await response.json(),canonical={},parts=[],textures=new Map();
  for(const [kind,spec] of Object.entries(config.canonical)){
    const [base,indices]=await Promise.all([binary(spec.base),binary(spec.indices,Uint32Array)]);
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(base.slice(),3));
    geometry.setIndex(new THREE.BufferAttribute(indices,1));geometry.computeVertexNormals();
    canonical[kind]={base,geometry,offset:kind==='skin'?0:72006};
  }
  const texture=(url,color=false)=>{
    if(!url)return null;
    if(!textures.has(url))textures.set(url,new THREE.TextureLoader().loadAsync(url).then(t=>{
      t.colorSpace=color?THREE.SRGBColorSpace:THREE.NoColorSpace;t.anisotropy=4;return t;
    }));return textures.get(url);
  };
  for(const spec of config.parts){
    const [positions,uv,indices,ids,map,normalMap,roughnessMap]=await Promise.all([
      binary(spec.base),binary(spec.uv),binary(spec.indices,Uint32Array),spec.sourceVertices?binary(spec.sourceVertices,Uint32Array):null,
      texture(spec.map,true),texture(spec.normalMap),texture(spec.roughnessMap)]);
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3).setUsage(THREE.DynamicDrawUsage));
    geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2));geometry.setIndex(new THREE.BufferAttribute(indices,1));geometry.computeVertexNormals();
    geometry.attributes.normal.setUsage(THREE.DynamicDrawUsage);
    const material=new THREE.MeshPhysicalMaterial({map,normalMap,roughnessMap,
      color:map?0xffffff:spec.kind==='skin'?0xc3947b:spec.kind==='tongue'?0xb16c69:0xe8e5d8,
      roughness:spec.kind==='eye'?.28:spec.kind==='skin'?.9:.5,envMapIntensity:.4});
    if(spec.kind==='skin'){material.normalScale.set(.55,.55);material.sheen=.12;material.sheenColor.set(0xbc7a65);}
    if(spec.kind==='eye'){material.clearcoat=.75;material.clearcoatRoughness=.08;}
    const mesh=new THREE.Mesh(geometry,material);mesh.frustumCulled=false;mesh.name=spec.name;group.add(mesh);
    parts.push({spec,mesh,ids,original:{map,normalMap,roughnessMap,color:material.color.clone()}});
  }
  const qa=new THREE.Quaternion(),qb=new THREE.Quaternion(),q=new THREE.Quaternion();
  const pa=new THREE.Vector3(),pb=new THREE.Vector3(),p=new THREE.Vector3(),pivot=new THREE.Vector3();
  const setFrame=(buffer,localFrame,alpha,jaw,globalFrame)=>{
    const stride=88831,a=localFrame*stride,b=Math.min(localFrame+1,buffer.length/stride-1)*stride;
    for(const c of Object.values(canonical)){
      const position=c.geometry.attributes.position;
      for(let i=0;i<c.base.length;i++)position.array[i]=c.base[i]+buffer[a+c.offset+i]*(1-alpha)+buffer[b+c.offset+i]*alpha;
      position.needsUpdate=true;c.geometry.computeVertexNormals();
    }
    const ja=globalFrame*7,jb=Math.min(globalFrame+1,jaw.length/7-1)*7;
    qa.fromArray(jaw,ja);qb.fromArray(jaw,jb);q.slerpQuaternions(qa,qb,alpha);
    pa.fromArray(jaw,ja+4);pb.fromArray(jaw,jb+4);p.lerpVectors(pa,pb,alpha);
    for(const {spec,mesh,ids} of parts){
      if(ids){
        const c=canonical[spec.kind].geometry.attributes,pos=mesh.geometry.attributes.position,norm=mesh.geometry.attributes.normal;
        for(let i=0;i<ids.length;i++)for(let k=0;k<3;k++){pos.array[i*3+k]=c.position.array[ids[i]*3+k];norm.array[i*3+k]=c.normal.array[ids[i]*3+k];}
        pos.needsUpdate=true;norm.needsUpdate=true;
      }
      // Tongue already contains its complete raw displacement: do not apply jaw twice.
      if(spec.jawDriven){mesh.quaternion.copy(q);mesh.position.copy(p);}
      if(spec.eyeSide){
        const offset=88827+(spec.eyeSide==='right'?0:2);
        const x=buffer[a+offset]*(1-alpha)+buffer[b+offset]*alpha;
        const y=buffer[a+offset+1]*(1-alpha)+buffer[b+offset+1]*alpha;
        mesh.rotation.set(THREE.MathUtils.degToRad(x),THREE.MathUtils.degToRad(y),0,'XYZ');
        pivot.fromArray(spec.eyePivot);mesh.position.copy(pivot).sub(pivot.clone().applyQuaternion(mesh.quaternion));
      }
    }
  };
  const setAppearance=value=>{
    for(const {mesh,original,spec} of parts){
      const m=mesh.material;m.wireframe=value==='wire';
      m.map=value==='skin'?original.map:null;m.normalMap=value==='skin'?original.normalMap:null;m.roughnessMap=value==='skin'?original.roughnessMap:null;
      m.color.copy(original.color);if(value!=='skin')m.color.set(spec.kind==='skin'?0xb8c2ba:spec.kind==='tongue'?0x9d8b88:0xd6dad2);
      m.needsUpdate=true;
    }
  };
  const render=()=>{controls.update();renderer.render(scene,camera);};
  return {setFrame,setAppearance,reset,render,resize,dispose(){
    observer.disconnect();controls.dispose();env.dispose();
    for(const p of parts){p.mesh.geometry.dispose();p.mesh.material.dispose();}
    for(const c of Object.values(canonical))c.geometry.dispose();
    for(const t of textures.values())t.then(v=>v.dispose());renderer.dispose();
  }};
}
