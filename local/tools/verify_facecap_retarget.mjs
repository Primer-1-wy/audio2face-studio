// CPU regression check against the actual pinned GLB and active CSV preview data.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import * as THREE from '../viewer/node_modules/three/build/three.module.js';
import {MeshoptDecoder} from '../viewer/node_modules/three/examples/jsm/libs/meshopt_decoder.module.js';
import {FACE_STYLES,faceTransform} from '../viewer/face-styles.js';
import {createFaceCapRetargeter} from '../viewer/facecap-retarget.js';
const root=fileURLToPath(new URL('../',import.meta.url));
await MeshoptDecoder.ready;
const b=fs.readFileSync(root+'viewer/models/facecap.glb');if(createHash('sha256').update(b).digest('hex')!=='6bfce6d0fcbb5839f5102b79733007859fef7c5df6d9eb49e2264542810b5f64') throw Error('Pinned GLB changed');const n=b.readUInt32LE(12),j=JSON.parse(b.subarray(20,20+n)),bin=b.subarray(28+n);const views=j.bufferViews.map(v=>{const e=v.extensions?.EXT_meshopt_compression;if(!e)return bin.subarray(v.byteOffset,v.byteOffset+v.byteLength);const out=new Uint8Array(e.count*e.byteStride);MeshoptDecoder.decodeGltfBuffer(out,e.count,e.byteStride,bin.subarray(e.byteOffset,e.byteOffset+e.byteLength),e.mode,e.filter);return out;});
function accessor(i){const a=j.accessors[i],v=j.bufferViews[a.bufferView],buf=views[a.bufferView],dv=new DataView(buf.buffer,buf.byteOffset,buf.byteLength);const c={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type];const [sz,method]={5123:[2,'getUint16'],5122:[2,'getInt16'],5120:[1,'getInt8'],5126:[4,'getFloat32']}[a.componentType];return Array.from({length:a.count},(_,r)=>Array.from({length:c},(_,k)=>dv[method]((a.byteOffset||0)+r*(v.byteStride||c*sz)+k*sz,true)));}
const m=j.meshes[2],p=m.primitives[0];const t=j.materials[0].pbrMetallicRoughness.baseColorTexture.extensions.KHR_texture_transform;
const out={position:accessor(p.attributes.POSITION),uv:accessor(p.attributes.TEXCOORD_0).map(a=>a.map((v,k)=>t.offset[k]+v*t.scale[k])),triangles:accessor(p.indices).flat(),targets:Object.fromEntries(m.extras.targetNames.map((s,i)=>[s,accessor(p.targets[i].POSITION)])),teeth:accessor(116)};

const asset=out;
const data=JSON.parse(fs.readFileSync(root+'viewer/data.json'));
const geometry=new THREE.BufferGeometry();
geometry.setAttribute('position',new THREE.Float32BufferAttribute(asset.position.flat(),3));
geometry.morphTargetsRelative=true;
geometry.morphAttributes.position=Object.entries(asset.targets).map(([name,values])=>{const a=new THREE.Float32BufferAttribute(values.flat(),3);a.name=name;return a;});
const mesh=new THREE.Mesh(geometry);const retarget=createFaceCapRetargeter(mesh);
const indices=Object.keys(asset.targets).map(n=>data.blendshapes.names.indexOf(n.replace(/_L$/,'Left').replace(/_R$/,'Right')));
let before=0,after=0,minBefore=Infinity,minAfter=Infinity,maxJawCorrection=0,count=0,maxWidthBefore=0,maxWidthAfter=0,maxJawAfter=0;
for(let f=0;f<=data.frameCount-1;f+=.25){
 const a=Math.floor(f),b=Math.min(data.frameCount-1,a+1),t=f-a;
 const w=indices.map(i=>data.blendshapes.values[a][i]*(1-t)+data.blendshapes.values[b][i]*t);
 const old=Math.min(...retarget.gaps(w));if(old<-1e-6)before++;minBefore=Math.min(minBefore,old);
 maxWidthBefore=Math.max(maxWidthBefore,retarget.widthRatio(w));
 const result=retarget.apply(w);
 maxWidthAfter=Math.max(maxWidthAfter,retarget.widthRatio(w));maxJawAfter=Math.max(maxJawAfter,w[mesh.morphTargetDictionary.jawOpen]);maxJawCorrection=Math.max(maxJawCorrection,result.jawCorrection);
 const now=Math.min(...retarget.gaps(w));if(now<-1e-6)after++;minAfter=Math.min(minAfter,now);count++;
 if(!w.every(Number.isFinite))throw Error('Nonfinite weights');
}
const passed=after===0 && maxWidthAfter<=1.32+1e-6 && maxJawAfter<.7;
const report={status:passed?'PASS':'FAIL',maxWidthBefore,maxWidthAfter,maxJawAfter,samples:count,lipContactPairs:retarget.contacts.length,penetratingSamplesBefore:before,penetratingSamplesAfter:after,minGapBefore:minBefore,minGapAfter:minAfter,maxJawCorrection,units:'quantized Face Cap local mesh units',scope:'11 inner lip contacts, all 1680 frames and quarter-frame interpolation; not a full mesh collision proof',sourceDataModified:false};
fs.writeFileSync(root+'verification-lip-fix.json',JSON.stringify(report,null,2)+'\n');console.log(report);if(!passed)process.exit(1);

const styles={};
for(const [name,style] of Object.entries(FACE_STYLES)) {
 const g=geometry.clone(),base=asset.position.map(p=>new THREE.Vector3(...p)),mapped=base.map(p=>faceTransform(p,style));
 g.setAttribute('position',new THREE.Float32BufferAttribute(mapped.flatMap(v=>v.toArray()),3));
 g.morphAttributes.position=Object.entries(asset.targets).map(([name,values])=>{const a=new THREE.Float32BufferAttribute(values.flatMap((d,i)=>faceTransform(base[i].clone().add(new THREE.Vector3(...d)),style).sub(mapped[i]).toArray()),3);a.name=name;return a;});
 const m=new THREE.Mesh(g),r=createFaceCapRetargeter(m);let crossings=0,minGap=Infinity,maxWidth=0,samples=0;
 for(let f=0;f<=data.frameCount-1;f+=.25) {
  const a=Math.floor(f),b=Math.min(data.frameCount-1,a+1),t=f-a;
  const w=indices.map(i=>data.blendshapes.values[a][i]*(1-t)+data.blendshapes.values[b][i]*t);
  r.apply(w);const gap=Math.min(...r.gaps(w));if(gap < -1e-5)crossings++;minGap=Math.min(minGap,gap);maxWidth=Math.max(maxWidth,r.widthRatio(w));samples++;
 }
 styles[name]={samples,crossings,minGap,maxWidth,status:crossings===0 && maxWidth<=1.32+1e-6?'PASS':'FAIL'};
}
fs.writeFileSync(root+'verification-face-styles.json',JSON.stringify(styles,null,2)+'\n');console.log(styles);
if(Object.values(styles).some(s=>s.status!=='PASS'))process.exit(1);
