import * as THREE from 'three';
export async function addAllisonGroom({group,onProgress}) {
const config=await (await fetch('official-claire/scene.json')).json(),parts=[];
const binary=async(url,Type=Float32Array)=>new Type(await (await fetch(url)).arrayBuffer());
  for(const original of config.groom.filter(p=>['hairMain','hairMainFront','hairMainBack','babyHairFront','babyHairBack','babyHairNeck'].includes(p.name))) {
    const spec={...original,morphs:null,morphNames:[]};
    onProgress('Allison · 适配发型载入中');
    const [base,tangent,width,progress,segments,deltas]=await Promise.all([
      binary(spec.base),binary(spec.tangent),binary(spec.width),binary(spec.progress),binary(spec.indices,Uint32Array),spec.morphs?binary(spec.morphs):null
    ]);
    for(let i=0;i<base.length;i+=3){base[i]=(base[i]-.05)*1.015+.43;base[i+1]=(base[i+1]-157.92648)*1.015+182.55;base[i+2]=(base[i+2]+5.21)*1.015+.7;}
    const n=base.length/3,positions=new Float32Array(n*6),normals=new Float32Array(n*6),tangents=new Float32Array(n*6),widths=new Float32Array(n*2),sides=new Float32Array(n*2),strandColors=new Float32Array(n*6);
    for(let i=0;i<n;i++)for(let side=0;side<2;side++) {
      const v=i*2+side;positions.set(base.subarray(i*3,i*3+3),v*3);tangents.set(tangent.subarray(i*3,i*3+3),v*3);
      normals.set([0,0,1],v*3);widths[v]=width[i];sides[v]=side?1:-1;
      const variation=.83+.17*Math.sin(base[i*3]*13+base[i*3+1]*2)+.10*progress[i];
      strandColors.set([variation,variation,variation],v*3);
    }
    const indices=new Uint32Array(segments.length*3);
    for(let i=0;i<segments.length;i+=2) {
      const a=segments[i]*2,b=segments[i+1]*2;
      indices.set([a,b,a+1,b,b+1,a+1],i*3);
    }
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.BufferAttribute(positions,3));g.setAttribute('normal',new THREE.BufferAttribute(normals,3));
    g.setAttribute('strandTangent',new THREE.BufferAttribute(tangents,3));g.setAttribute('strandWidth',new THREE.BufferAttribute(widths,1));g.setAttribute('strandSide',new THREE.BufferAttribute(sides,1));
    g.setAttribute('color',new THREE.BufferAttribute(strandColors,3));g.setIndex(new THREE.BufferAttribute(indices,1));
    if(deltas) {
      g.morphAttributes.position=spec.morphNames.map((name,k)=>{
        const values=new Float32Array(n*6);
        for(let i=0;i<n;i++){const v=deltas.subarray(k*base.length+i*3,k*base.length+i*3+3);values.set(v,i*6);values.set(v,i*6+3);}
        const a=new THREE.BufferAttribute(values,3);a.name=name;return a;
      });g.morphTargetsRelative=true;
    }
    const facial=spec.name==='facialHair',lash=spec.name==='eyeLashes';
    const material=new THREE.MeshStandardMaterial({color:facial?0x8d7160:lash?0x211912:0x3d2922,roughness:.52,metalness:0,vertexColors:true,side:THREE.DoubleSide,envMapIntensity:.3});
    material.onBeforeCompile=shader=>{
      shader.vertexShader=shader.vertexShader.replace('#include <common>',`#include <common>
        attribute vec3 strandTangent;attribute float strandWidth;attribute float strandSide;`)
        .replace('#include <defaultnormal_vertex>',`#include <defaultnormal_vertex>
          vec3 strandView = normalize(-(modelViewMatrix*vec4(position,1.0)).xyz);
          transformedNormal = strandView;`)
        .replace('#include <project_vertex>',`
          vec3 strandCamera = (inverse(modelMatrix)*vec4(cameraPosition,1.0)).xyz;
          vec3 strandRight = normalize(cross(strandTangent,normalize(strandCamera-transformed)));
          transformed += strandRight * strandWidth * strandSide * ${spec.name==='hairMain'?'1.35':'.6'};
          #include <project_vertex>`);
    };
    material.customProgramCacheKey=()=>`claire-groom-${spec.name==='hairMain'?'main':'fine'}`;
    const mesh=new THREE.Mesh(g,material);mesh.name=spec.name;mesh.frustumCulled=false;group.add(mesh);
    parts.push({mesh,channelIndices:[]});
  }
return parts;
}
