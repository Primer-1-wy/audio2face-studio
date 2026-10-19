// Release model resources without creating a new WebGL context for each face.
export function disposeScene(scene) {
  if(!scene)return;
  const geometries=new Set(),materials=new Set(),textures=new Set();
  scene.traverse(object=>{
    if(object.geometry)geometries.add(object.geometry);
    if(object.material)for(const material of Array.isArray(object.material)?object.material:[object.material]){
      materials.add(material);
      for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
      if(material.userData.blendMap)textures.add(material.userData.blendMap);
    }
    object.shadow?.dispose();
  });
  for(const resource of [...geometries,...materials,...textures])resource.dispose();
  scene.userData.dispose?.();
  delete scene.userData.dispose;
  scene.environment=null;
  scene.clear();
}
