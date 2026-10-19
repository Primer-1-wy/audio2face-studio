import * as THREE from 'three';

const sideOf=name=>/^l_|Eye_L/.test(name)?'Left':/^r_|Eye_R/.test(name)?'Right':null;

export function createAccessoryAnimator(mesh,spec,config,channels) {
  const side=sideOf(spec.name);
  // Cornea and iris must rotate around the same eyeball centre.
  const eye=['eye','cornea'].includes(spec.kind)&&side
    ?config.parts.find(p=>p.kind==='eye'&&sideOf(p.name)===side&&p.eyePivot):null;
  const origin=eye?.eyePivot||(spec.jawDriven&&(config.jawPivot||[0,config.bounds.max[1]-13,-5]));
  if(!origin)return null;
  const pivot=new THREE.Vector3(...origin),rotated=new THREE.Vector3();
  const indices=new Map(channels.map((name,i)=>[name,i]));
  return values=>{
    const get=name=>Math.max(0,Math.min(1,values[indices.get(name)]||0));
    if(eye)mesh.rotation.set((get('eyeLookDown'+side)-get('eyeLookUp'+side))*.2,
      (get('eyeLookIn'+side)-get('eyeLookOut'+side))*(side==='Left'?-.24:.24),0);
    else mesh.rotation.set(get('jawOpen')*.27,0,0);
    mesh.position.copy(pivot).sub(rotated.copy(pivot).applyEuler(mesh.rotation));
  };
}
