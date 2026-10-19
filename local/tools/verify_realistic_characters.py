"""Validate all converted buffers and every frame of the three added characters."""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[1];VIEW=ROOT/'viewer'
data=json.loads((VIEW/'data.json').read_text());channels=data['blendshapes']['names'];weights=np.array(data['blendshapes']['values'],dtype='float32')
report={}
for role in ['allison','james','mark']:
    scene=json.loads((VIEW/f'official-{role}/scene.json').read_text());mapped=set();count=0;maximum=0
    for p in scene['parts']:
        base=np.fromfile(VIEW/p['base'],dtype='<f4').reshape(-1,3);normals=np.fromfile(VIEW/p['normals'],dtype='<f4').reshape(-1,3);uv=np.fromfile(VIEW/p['uv'],dtype='<f4').reshape(-1,2);idx=np.fromfile(VIEW/p['indices'],dtype='<u4')
        assert len(base)==len(normals)==len(uv) and len(idx)%3==0 and idx.max()<len(base)
        assert all(np.isfinite(a).all() for a in [base,normals,uv]);count+=len(base)
        for key in ['map','normalMap','roughnessMap']:
            if p.get(key):assert (VIEW/p[key]).is_file()
        if not p['morphNames']:continue
        names=p['morphNames'];assert set(names).issubset(channels);mapped.update(names)
        deltas=np.fromfile(VIEW/p['morphs'],dtype='<f4').reshape(len(names),-1);assert deltas.shape[1]==base.size and np.isfinite(deltas).all()
        normal_deltas=np.fromfile(VIEW/p['morphNormals'],dtype='<f4');assert normal_deltas.size==deltas.size and np.isfinite(normal_deltas).all()
        w=weights[:,[channels.index(n) for n in names]]
        for i in range(0,len(w),32):
            d=(w[i:i+32]@deltas).reshape(-1,len(base),3);assert np.isfinite(d+base).all();maximum=max(maximum,float(np.linalg.norm(d,axis=2).max()))
    assert len(mapped)==68
    report[role]={'status':'PASS','frames':len(weights),'mappedChannels':len(mapped),'renderVerticesIncludingUVSplits':count,'allDeformedVerticesFinite':True,'maxMorphDisplacementCm':maximum}
    print(role,report[role],flush=True)
(ROOT/'verification-realistic-characters.json').write_text(json.dumps({'characters':report,'scope':'Buffer validity, asset references and finite per-frame morph deformation. Does not certify full collision freedom or exact NVIDIA renderer equivalence.'},indent=2))
