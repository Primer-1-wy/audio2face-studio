"""James/Mark official topology and own morphs with explicitly adapted Claire materials.

Maya ASCII is parsed as geometry data; no MEL, script nodes or scene code runs.
The reused skin/eye appearance is a local preview, not the original James/Mark lookdev.
"""
from pathlib import Path
import re,json
import numpy as np
from prepare_mesh import parse_mesh
from prepare_official_allison import normals,bind

ROOT=Path(__file__).resolve().parents[1]
claire=json.loads((ROOT/'viewer/official-claire/scene.json').read_text())

def james_material_uv(target_tri,native_uv):
    # Topology 2 has a different UV layout. Transfer appearance through the
    # same-identity Claire topology-2 reference, then use James's identical
    # topology-2 face order. Neither actor's expression deltas are modified.
    text=(ROOT/'assets/james-official/claire_geom_v3_material_reference.ma').read_text()
    block=next(b for b in re.split(r'(?=^createNode )',text,flags=re.M) if b.startswith('createNode mesh -n "c_headWatertight_hiShape"'))
    reference,reference_tri,_=parse_mesh(block);assert np.array_equal(reference_tri,target_tri)
    source=np.load(ROOT/'assets/claire/bs_skin.npz',allow_pickle=False)['neutral']
    source_faces=[];source_uv=[]
    for p in claire['parts']:
        if p['kind']!='skin':continue
        ids=np.fromfile(ROOT/'viewer'/p['sourceVertices'],dtype='<u4');idx=np.fromfile(ROOT/'viewer'/p['indices'],dtype='<u4').reshape(-1,3)
        uv=np.fromfile(ROOT/'viewer'/p['uv'],dtype='<f4').reshape(-1,2);tile=p['tile']-1001;uv+=np.array([tile%10,tile//10])
        source_faces.extend(ids[idx]);source_uv.extend(uv[idx])
    faces=np.array(source_faces);uv=np.array(source_uv);lookup={tuple(f):i for i,f in enumerate(faces)}
    nearest,_,error=bind(reference[target_tri].mean(1),source,faces)
    chosen=np.array([lookup[tuple(f)] for f in nearest]);tri=source[nearest];a=tri[:,0];u=tri[:,1]-a;v=tri[:,2]-a
    d00=(u*u).sum(1);d01=(u*v).sum(1);d11=(v*v).sum(1);den=np.maximum(d00*d11-d01*d01,1e-15)
    q=reference[target_tri]-a[:,None,:];d20=(q*u[:,None,:]).sum(2);d21=(q*v[:,None,:]).sum(2)
    b=(d11[:,None]*d20-d01[:,None]*d21)/den[:,None];c=(d00[:,None]*d21-d01[:,None]*d20)/den[:,None]
    weights=np.stack([1-b-c,b,c],axis=-1)
    result=np.einsum('tij,tjk->tik',weights,uv[chosen])
    # Keep every triangle within its selected chart to prevent UDIM bleeding.
    tile=np.floor(uv[chosen].mean(1))
    result=np.clip(result,tile[:,None,:]+.00001,tile[:,None,:]+.99999)
    # Topology 2 has a broader neck cut. Its original neck UV remains valid;
    # projecting beyond the topology-1 boundary samples empty atlas pixels.
    result=np.where((reference[target_tri].mean(1)[:,1]<134)[:,None,None],native_uv,result)
    print('James UV transfer distance p50/p95',np.percentile(error,[50,95]),flush=True)
    return result

def export(role,filename):
    source=ROOT/f'assets/{role}-official';out=ROOT/f'viewer/official-{role}';out.mkdir(exist_ok=True)
    text=(source/filename).read_text();parts=[];report=[];bounds=None
    def buf(name,a,dtype='<f4'):
        a=np.asarray(a,dtype=dtype);assert np.isfinite(a).all();a.tofile(out/name);return f'official-{role}/'+name
    for block in re.split(r'(?=^createNode )',text,flags=re.M):
        node=re.match(r'createNode mesh -n "([^"]+)"',block)
        if not node:continue
        name=node[1].replace('Shape','')
        kind='skin' if name=='c_headWatertight_hi' else 'tongue' if name=='c_tongue_hi' else 'dental' if 'Denture' in name else 'eye' if 'choroid' in name else 'cornea' if 'cornea' in name else None
        if kind is None:continue
        scene_base,tri,_=parse_mesh(block);base=scene_base.astype('float32');names=[];deltas=None
        if kind in ['skin','tongue']:
            f=np.load(source/f'bs_{kind}.npz',allow_pickle=False);base=f['neutral'];names=[x.decode() if isinstance(x,bytes) else str(x) for x in f['poseNames'][1:]];deltas=np.stack([f[n] for n in names]);assert base.shape==scene_base.shape
            distance=np.linalg.norm(scene_base-base,axis=1)
            if role=='mark' and kind=='skin':assert np.array_equal(tri,np.fromfile(ROOT/'viewer/geometry/skin.indices.bin',dtype='<u4').reshape(-1,3))
            assert distance.max()<(.8 if role=='mark' else .5),(role,kind,float(distance.max()))
            report.append({'part':kind,'vertices':len(base),'morphs':len(names),'mayaNeutralMaxDifferenceCm':float(distance.max())})
            if kind=='skin':bounds={'min':base.min(0).tolist(),'max':base.max(0).tolist()}
        uv=[]
        for m in re.finditer(r'setAttr(?: -s \d+)? "\.uvst\[0\]\.uvsp\[(\d+)(?::(\d+))?\]"(?: -type "float2")?\s*([^;]+);',block):
            assert int(m[1])==len(uv);uv.extend(np.fromstring(m[3],sep=' ').reshape(-1,2))
        uv=np.array(uv);uvtri=[]
        for m in re.finditer(r'\bmu 0 (\d+) ([\d\s]+)',block,re.M):
            ids=np.fromstring(m[2],sep=' ',dtype=int)
            for i in range(1,len(ids)-1):uvtri.append([ids[0],ids[i],ids[i+1]])
        assert len(uvtri)==len(tri),(role,name,len(uvtri),len(tri))
        uvs=james_material_uv(tri,uv[np.array(uvtri)]) if role=='james' and kind=='skin' else uv[np.array(uvtri)]
        tiles=np.floor(uvs.mean(1)).astype(int)
        n=normals(base,tri);dn=np.stack([normals(base+d,tri)-n for d in deltas]) if deltas is not None else None
        for xy in np.unique(tiles,axis=0):
            tile=1001+int(xy[0])+10*int(xy[1]);selected=np.all(tiles==xy,axis=1);vid=tri[selected].flatten();coords=(uvs[selected]-xy).reshape(-1,2)
            _,first,inverse=np.unique(np.c_[vid,coords],axis=0,return_index=True,return_inverse=True);ids=vid[first];tag=f'{name}-{tile}'
            spec={'name':tag,'kind':kind,'base':buf(tag+'.pos.bin',base[ids]),'normals':buf(tag+'.normal.bin',n[ids]),'uv':buf(tag+'.uv.bin',coords[first]),'indices':buf(tag+'.idx.bin',inverse,'<u4'),'morphNames':names,'vertexCount':len(ids)}
            if deltas is not None:spec.update(morphs=buf(tag+'.morph.bin',deltas[:,ids]),morphNormals=buf(tag+'.morph-normal.bin',dn[:,ids]))
            match=next((p for p in claire['parts'] if p['kind']==kind and p.get('tile')==tile),None)
            if kind=='eye':match=next(p for p in claire['parts'] if p['kind']=='eye');spec['eyePivot']=((base.min(0)+base.max(0))/2).tolist()
            if match:
                for key in ['map','normalMap','roughnessMap']:
                    if key in match:spec[key]=match[key]
            if kind in ['tongue','dental'] and ('bottom' in name or kind=='tongue'):spec['jawDriven']=True
            parts.append(spec)
        print(role,name,len(base),len(names),flush=True)
    matched={n for p in parts for n in p['morphNames']};assert len(matched)==68
    result={'label':role.title(),'parts':parts,'bounds':bounds,'mappedChannels':68,'source':'NVIDIA Maya-ACE and identity-matched Audio2Face NPZ assets','appearance':'Adapted NVIDIA Claire materials; not an official complete James/Mark appearance package.'}
    (out/'scene.json').write_text(json.dumps(result,indent=2));(ROOT/f'verification-{role}-conversion.json').write_text(json.dumps({'parts':report,'mappedChannels':len(matched),'appearance':result['appearance']},indent=2))

if __name__=='__main__':
    export('james','james_geom_v3.ma')
    export('mark','mark_geom_v2_topo1.ma')
