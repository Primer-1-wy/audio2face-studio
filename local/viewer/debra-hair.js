import * as THREE from 'three';

// Separate accessory: never copy another character's vertex deltas onto Debra.
export async function addDebraHair(group,role='debra') {
  const response=await fetch(`${role}-hair/scene.json`);
  if(!response.ok)throw new Error('无法加载 Debra 短卷发');
  const config=await response.json(),hair=new THREE.Group();hair.name='debra-short-hair';
  for(const part of config.parts) {
    const arrays=await Promise.all(['positions','normals','colors','indices'].map(async key=>{
      const r=await fetch(part[key]);if(!r.ok)throw new Error(part[key]);
      return new (key==='indices'?Uint32Array:Float32Array)(await r.arrayBuffer());
    }));
    const geometry=new THREE.BufferGeometry();
    for(const [i,key] of ['position','normal','color'].entries())geometry.setAttribute(key,new THREE.BufferAttribute(arrays[i],3));
    geometry.setIndex(new THREE.BufferAttribute(arrays[3],1));
    const material=new THREE.MeshPhysicalMaterial({vertexColors:true,roughness:.66,metalness:0,side:THREE.DoubleSide,specularIntensity:.48,envMapIntensity:.55});
    const mesh=new THREE.Mesh(geometry,material);mesh.name=part.name;mesh.castShadow=true;mesh.receiveShadow=true;hair.add(mesh);
  }
  group.add(hair);return hair;
}
