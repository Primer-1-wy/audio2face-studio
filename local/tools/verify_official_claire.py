"""Check source completeness and exact morph preservation through UV splitting."""
from pathlib import Path
import json, numpy as np

ROOT=Path(__file__).resolve().parents[1]
viewer=ROOT/'viewer'
scene=json.loads((viewer/'official-claire/scene.json').read_text())
animation=json.loads((viewer/'data.json').read_text())
manifest=json.loads((ROOT/'assets/claire-official/manifest.json').read_text())
for f in manifest['files']:
    assert (ROOT/'assets/claire-official'/f['path']).stat().st_size==f['bytes'],f['path']
checks=[]
for kind in ['skin','tongue']:
    npz=np.load(ROOT/f'assets/claire/bs_{kind}.npz',allow_pickle=False)
    names=[x.decode() if isinstance(x,bytes) else str(x) for x in npz['poseNames'][1:]]
    source=np.stack([npz[n] for n in names]);count=0
    for spec in scene['parts']:
        if spec['kind']!=kind:continue
        ids=np.fromfile(viewer/spec['sourceVertices'],dtype='<u4')
        base=np.fromfile(viewer/spec['base'],dtype='<f4').reshape(-1,3)
        delta=np.fromfile(viewer/spec['morphs'],dtype='<f4').reshape(len(names),-1,3)
        assert spec['morphNames']==names
        assert np.array_equal(base,npz['neutral'][ids]),spec['name']
        assert np.array_equal(delta,source[:,ids]),spec['name']
        uv=np.fromfile(viewer/spec['uv'],dtype='<f4')
        assert uv.min()>=-.00001 and uv.max()<=1.00001
        count+=len(ids)
    weights=np.array(animation['blendshapes']['values'],dtype='float32')[:,[animation['blendshapes']['names'].index(n) for n in names]]
    maximum=0
    for start in range(0,len(weights),32):
        motion=(weights[start:start+32]@source.reshape(len(names),-1)).reshape(-1,len(npz['neutral']),3)
        assert np.isfinite(motion).all()
        maximum=max(maximum,float(np.linalg.norm(motion,axis=2).max()))
    checks.append({'kind':kind,'frames':len(weights),'exportedVerticesIncludingUVSeams':count,'neutralAndAllMorphsBitExact':True,'maxDisplacementCm':maximum})
mapped={n for p in scene['parts'] for n in p['morphNames']}
assert mapped==set(animation['blendshapes']['names'])
result={'status':'PASS','sourceFiles':len(manifest['files']),'sourceBytes':sum(f['bytes'] for f in manifest['files']),'channels':len(mapped),'meshes':len(scene['parts']),'groomGroups':len(scene['groom']),'previewStrands':sum(p['strandCount'] for p in scene['groom']),'checks':checks}
(ROOT/'verification-official-claire-playback.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
