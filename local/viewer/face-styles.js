import * as THREE from 'three';

export const FACE_STYLES={
  realistic:{label:'写实女性',texture:'skin-realistic-v1.png',jaw:.13,eyes:.06,nose:.16,chin:.04,hair:0x251713,highlight:0x4b3025,roughness:.66},
  cartoon:{label:'3D 卡通女生',texture:'skin-cartoon-v1.png',jaw:.20,eyes:.25,nose:.38,chin:.09,hair:0x713323,highlight:0xad643a,roughness:.82},
  anime:{label:'二次元女生',texture:'skin-anime-v1.png',jaw:.29,eyes:.40,nose:.60,chin:.14,hair:0x30274b,highlight:0x625483,roughness:1},
};
const smooth=(a,b,x)=>{const t=THREE.MathUtils.clamp((x-a)/(b-a),0,1);return t*t*(3-2*t);};

// Transform the base and every target through the same smooth map. This keeps
// UVs, topology and expression names, while changing actual face proportions.
export function faceTransform(point,style) {
  const q=point.clone(),x=point.x-5593,z=point.z;
  const front=smooth(7800,10800,point.y);
  q.x=5593+x*(1-style.jaw*smooth(8500,13900,z));
  q.z-=style.chin*Math.max(0,z-10800);
  for(const sign of [-1,1]) {
    const dx=x-sign*1660,dz=z-8050;
    const local=Math.exp(-Math.pow(dx/1500,4)-Math.pow(dz/1700,4))*front;
    q.x+=dx*style.eyes*local;
    q.z+=dz*style.eyes*local;
  }
  const nose=Math.exp(-(x*x)/(1250*1250)-Math.pow((z-9800)/1700,2))*front;
  q.y-=Math.max(0,point.y-11700)*style.nose*nose;
  return q;
}

export function applyFaceStyle(root,style) {
  root.updateMatrixWorld(true);
  let head;
  root.traverse(o=>{if(o.isMesh && o.morphTargetDictionary)head=o;});
  const headInverse=head.matrixWorld.clone().invert();
  root.traverse(mesh=>{
    if(!mesh.isMesh)return;
    const geometry=mesh.geometry,position=geometry.attributes.position;
    const toHead=headInverse.clone().multiply(mesh.matrixWorld),fromHead=toHead.clone().invert();
    const base=new Float32Array(position.count*3),targets=geometry.morphAttributes.position||[];
    const changed=targets.map(()=>new Float32Array(base.length));
    const original=new THREE.Vector3(),p=new THREE.Vector3();
    for(let i=0;i<position.count;i++) {
      original.fromBufferAttribute(position,i);
      const mapped=faceTransform(original.clone().applyMatrix4(toHead),style).applyMatrix4(fromHead);
      mapped.toArray(base,i*3);
      targets.forEach((delta,k)=>{
        p.fromBufferAttribute(delta,i).add(original).applyMatrix4(toHead);
        faceTransform(p,style).applyMatrix4(fromHead).sub(mapped).toArray(changed[k],i*3);
      });
    }
    geometry.setAttribute('position',new THREE.BufferAttribute(base,3));
    geometry.morphAttributes.position=changed.map((values,i)=>{const a=new THREE.BufferAttribute(values,3);a.name=targets[i].name;return a;});
    // Imported packed int8 normals cannot accumulate unnormalized face normals.
    geometry.deleteAttribute('normal');geometry.computeVertexNormals();
    const baseNormals=geometry.attributes.normal.array;
    geometry.morphAttributes.normal=changed.map(values=>{
      const temp=new THREE.BufferGeometry();temp.setIndex(geometry.index);
      temp.setAttribute('position',new THREE.BufferAttribute(Float32Array.from(base,(v,i)=>v+values[i]),3));
      temp.computeVertexNormals();const normals=Float32Array.from(temp.attributes.normal.array,(v,i)=>v-baseNormals[i]);temp.dispose();
      return new THREE.BufferAttribute(normals,3);
    });
    if(!targets.length)geometry.morphAttributes={};
    geometry.computeBoundingBox();geometry.computeBoundingSphere();
  });
  addHair(head,style);
}

function surface(rows,cols,point) {
  const vertices=[],indices=[];
  for(let r=0;r<=rows;r++)for(let c=0;c<=cols;c++)vertices.push(...point(r/rows,c/cols));
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
    const a=r*(cols+1)+c,b=a+cols+1;indices.push(a,b,a+1,b,b+1,a+1);
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setIndex(indices);g.computeVertexNormals();return g;
}
function addHair(head,style) {
  const hair=new THREE.Group();hair.name='procedural-hair';head.add(hair);
  const toon=style===FACE_STYLES.anime;
  const material=new (toon?THREE.MeshToonMaterial:THREE.MeshStandardMaterial)({color:style.hair,side:THREE.DoubleSide,...(toon?{}:{roughness:.55,metalness:0})});
  const accent=material.clone();accent.color.set(style.highlight);
  const cap=surface(34,96,(v,u)=>{
    const phi=u*Math.PI*2,front=Math.max(0,Math.cos(phi));
    const end=2.0-.92*Math.pow(front,3),theta=v*end;
    const ridges=1+.003*Math.cos(phi*56+theta*3);
    return [5593+5120*Math.sin(theta)*Math.sin(phi)*ridges,7100+6410*Math.sin(theta)*Math.cos(phi)*ridges,8200-6530*Math.cos(theta)];
  });
  hair.add(new THREE.Mesh(cap,material));
  // Side and back curtains; the front remains clear for expression inspection.
  const length=toon?13900:style===FACE_STYLES.cartoon?14800:15900;
  const curtain=surface(32,88,(v,u)=>{
    const phi=.70+u*(Math.PI*2-1.40),swell=Math.sin(v*Math.PI)*.10;
    const radius=1+swell-.10*v*v;
    const wave=(toon?70:160)*Math.sin(v*9+phi*3)*v;
    return [5593+(5070*radius+wave)*Math.sin(phi),7100+(5400*radius+wave)*Math.cos(phi),5700+v*(length-5700)+220*Math.cos(phi*9)*v*v];
  });
  hair.add(new THREE.Mesh(curtain,material));
  // Swept locks and fine raised strands provide actual volume in profile.
  const lock=(points,radius,mat,flatten=.5)=>{
    const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)));
    const g=new THREE.TubeGeometry(curve,36,radius,8,false);
    // Hair lock thickness tapers toward its endpoint.
    const pos=g.attributes.position;
    for(let i=0;i<pos.count;i++){
      const t=Math.floor(i/9)/36,center=curve.getPointAt(t),p=new THREE.Vector3().fromBufferAttribute(pos,i).sub(center);
      p.multiplyScalar(.96-.88*Math.pow(t,4));p.y*=flatten;p.add(center);pos.setXYZ(i,p.x,p.y,p.z);
    }
    g.computeVertexNormals();hair.add(new THREE.Mesh(g,mat));
  };
  if(toon){
    for(let k=-3;k<=3;k++) {
      const x=5593+k*790;
      lock([[x*.65+5593*.35,11600,3200],[x,13020,4350],[x+k*70,13360,5400],[x+k*120,12900,6200+(k%2?350:0)]],520,material,.45);
    }
  } else {
    for(const sign of [-1,1])for(let k=0;k<5;k++) {
      const start=5593-600+sign*k*190;
      lock([[start,11900,2900+k*75],[5593+sign*(2100+k*230),13100,4250+k*170],[5593+sign*(3900+k*140),12300,6700+k*100],[5593+sign*(4350+k*95),11000,11600+k*380]],420-k*45,k===2?accent:material,.5);
    }
  }
  for(const sign of [-1,1])for(let k=0;k<12;k++) {
    const x=5593+sign*(3650+k*110),y=11200-k*200;
    lock([[x,y,6300],[x+sign*600,y+70,8900],[x+sign*(300+70*Math.sin(k)),y-100,11900],[x+sign*150,y-300,length-250-k*65]],toon?25:18,k%4===0?accent:material,.55);
  }
}
