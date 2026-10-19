"""Convert the official Debra sample and its native shapes, without executing OmniGraph.

Keep Debra topology and UVs. Two linear Catmull-Clark steps are applied equally
to neutral positions and every native offset. Face-varying UVs interpolate
linearly within each original polygon, retaining texture seams.
"""
from pathlib import Path
import json
import numpy as np
from scipy.sparse import csr_matrix, vstack, eye
from PIL import Image
from pxr import Usd, UsdGeom, UsdSkel, UsdShade

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'assets/debra-official'
OUT=ROOT/'viewer/official-debra'
OUT.mkdir(parents=True,exist_ok=True)

def buf(name,a,dtype='<f4'):
    a=np.asarray(a,dtype=dtype);assert np.isfinite(a).all(),name
    a.tofile(OUT/name);return 'official-debra/'+name

def normals(v,tri):
    n=np.zeros_like(v);f=np.cross(v[tri[:,1]]-v[tri[:,0]],v[tri[:,2]]-v[tri[:,0]])
    for i in range(3):np.add.at(n,tri[:,i],f)
    return n/np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)

def subdivision(n,faces,uv,material_ids):
    edges={};vertex_faces=[[] for _ in range(n)];vertex_edges=[[] for _ in range(n)]
    fr=[];fc=[];fv=[]
    for i,face in enumerate(faces):
        for j,a in enumerate(face):
            vertex_faces[a].append(i);fr.append(i);fc.append(a);fv.append(1/len(face))
            key=tuple(sorted((int(a),int(face[(j+1)%len(face)]))))
            if key not in edges:edges[key]=[]
            edges[key].append(i)
    F=csr_matrix((fv,(fr,fc)),shape=(len(faces),n))
    keys=list(edges);lookup={k:i for i,k in enumerate(keys)};er=[];ec=[];ev=[];efr=[];efc=[];efv=[]
    for i,(a,b) in enumerate(keys):
        adjacent=edges[(a,b)];assert len(adjacent)<=2
        vertex_edges[a].append(i);vertex_edges[b].append(i)
        scale=.25 if len(adjacent)==2 else .5
        er.extend([i,i]);ec.extend([a,b]);ev.extend([scale,scale])
        if len(adjacent)==2:
            efr.extend([i,i]);efc.extend(adjacent);efv.extend([.25,.25])
    E=csr_matrix((ev,(er,ec)),shape=(len(keys),n))+csr_matrix((efv,(efr,efc)),shape=(len(keys),len(faces)))@F
    vr=[];vc=[];vv=[];vfr=[];vfc=[];vfv=[]
    for i in range(n):
        neighbors=[];boundary=[]
        for e in vertex_edges[i]:
            a,b=keys[e];other=b if a==i else a;neighbors.append(other)
            if len(edges[(a,b)])==1:boundary.append(other)
        k=len(neighbors)
        if not k:vr.append(i);vc.append(i);vv.append(1);continue
        if boundary:
            if len(boundary)!=2:vr.append(i);vc.append(i);vv.append(1)
            else:vr.extend([i,i,i]);vc.extend([i,*boundary]);vv.extend([.75,.125,.125])
        else:
            vr.append(i);vc.append(i);vv.append((k-2)/k)
            for j in neighbors:vr.append(i);vc.append(j);vv.append(1/k**2)
            for f in vertex_faces[i]:vfr.append(i);vfc.append(f);vfv.append(1/(k*len(vertex_faces[i])))
    V=csr_matrix((vv,(vr,vc)),shape=(n,n))+csr_matrix((vfv,(vfr,vfc)),shape=(n,len(faces)))@F
    S=vstack([V,E,F]).tocsr();assert np.allclose(np.array(S.sum(axis=1)),1)
    new_faces=[];new_uv=[];new_material=[]
    for i,face in enumerate(faces):
        for j,a in enumerate(face):
            next_index=(j+1)%len(face);prev_index=(j-1)%len(face)
            e1=lookup[tuple(sorted((int(a),int(face[next_index]))))]
            e0=lookup[tuple(sorted((int(a),int(face[prev_index]))))]
            new_faces.append([a,n+e1,n+len(keys)+i,n+e0])
            new_uv.append([uv[i][j],(uv[i][j]+uv[i][next_index])/2,uv[i].mean(0),(uv[i][j]+uv[i][prev_index])/2])
            new_material.append(material_ids[i])
    return S,np.array(new_faces),np.array(new_uv),np.array(new_material)

def export_texture(asset):
    name=asset.path.replace('./','',1);src=SOURCE/name
    assert src.exists(),name
    dst=OUT/('textures/'+name.replace('Materials/Textures/','').replace('/','__'))
    dst.parent.mkdir(exist_ok=True)
    with Image.open(src) as im:
        # Native color textures already use sRGB. Preserve alpha if authored.
        im.thumbnail((4096,4096),Image.Resampling.LANCZOS);im.save(dst)
    return 'official-debra/textures/'+dst.name

def main():
    s=Usd.Stage.Open(str(SOURCE/'Debra_A2F.usd'))
    mats={}
    for p in s.Traverse():
        if not p.IsA(UsdShade.Material):continue
        shader=s.GetPrimAtPath(str(p.GetPath())+'/Shader');spec={}
        for source,key in [('diffuse_texture','map'),('blend_map','blendMap'),('normalmap_texture','normalMap'),('reflectionroughness_texture','roughnessMap'),('ao_texture','aoMap'),('opacity_texture','alphaMap')]:
            a=shader.GetAttribute('inputs:'+source).Get()
            if a and a.path:spec[key]=export_texture(a)
        mats[p.GetName()]=spec
    parts=[];report=[]
    # Coordinate conversion (x,y,z Z-up) -> (x,z,-y Y-up). No Claire geometry is used.
    rot=np.array([[1,0,0],[0,0,-1],[0,1,0]],dtype='float32')
    for p in s.Traverse():
        if not p.IsA(UsdGeom.Mesh):continue
        m=UsdGeom.Mesh(p);name=p.GetName();base=np.array(m.GetPointsAttr().Get(),dtype='float32')@rot
        counts=np.array(m.GetFaceVertexCountsAttr().Get());idx=np.array(m.GetFaceVertexIndicesAttr().Get())
        assert np.all(counts==3),name
        faces=idx.reshape(-1,3);uv=np.array(UsdGeom.PrimvarsAPI(p).GetPrimvar('st0').ComputeFlattened()).reshape(-1,3,2)
        api=UsdSkel.BindingAPI(p);names=list(api.GetBlendShapesAttr().Get() or []);targets=api.GetBlendShapeTargetsRel().GetTargets();deltas=[]
        for target in targets:
            b=UsdSkel.BlendShape(s.GetPrimAtPath(target));d=np.zeros_like(base);ids=b.GetPointIndicesAttr().Get();offset=np.array(b.GetOffsetsAttr().Get())@rot
            if len(offset)==0:pass
            elif ids is None or len(ids)==0:d[:]=offset
            else:d[np.array(ids)]=offset
            deltas.append(d)
        source_vertices=len(base);deltas=np.array(deltas,dtype='float32')
        default=UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
        material_ids=np.zeros(len(faces),dtype=int);mat_names=[default.GetPrim().GetName() if default else '']
        for subset in UsdGeom.Subset.GetAllGeomSubsets(m):
            mat=UsdShade.MaterialBindingAPI(subset.GetPrim()).ComputeBoundMaterial()[0];mat_names.append(mat.GetPrim().GetName());material_ids[np.array(subset.GetIndicesAttr().Get())]=len(mat_names)-1
        for _ in range(2):
            S,faces,uv,material_ids=subdivision(len(base),faces,uv,material_ids)
            base=np.asarray(S@base,dtype='float32');deltas=np.stack([S@d for d in deltas]).astype('float32')
        tri=np.stack([faces[:,[0,1,2]],faces[:,[0,2,3]]],axis=1).reshape(-1,3)
        tri_uv=np.stack([uv[:,[0,1,2]],uv[:,[0,2,3]]],axis=1).reshape(-1,3,2);tri_mat=np.repeat(material_ids,2)
        norm=normals(base,tri);mnorm=np.stack([normals(base+d,tri)-norm for d in deltas])
        for mi in np.unique(tri_mat):
            selected=tri_mat==mi;verts=tri[selected].flatten();coords=tri_uv[selected].reshape(-1,2)
            _,first,inverse=np.unique(np.c_[verts,coords],axis=0,return_index=True,return_inverse=True);ids=verts[first]
            tag=name+'-'+mat_names[mi];kind='skin' if name=='CC_Game_Body' else 'tongue' if 'Tongue' in name else 'eye' if 'Eye' in name else 'dental'
            spec={'name':tag,'kind':kind,'material':mat_names[mi],'base':buf(tag+'.pos.bin',base[ids]),'normals':buf(tag+'.normal.bin',norm[ids]),'uv':buf(tag+'.uv.bin',coords[first]),'indices':buf(tag+'.idx.bin',inverse,'<u4'),'morphs':buf(tag+'.morph.bin',deltas[:,ids]),'morphNormals':buf(tag+'.morph-normal.bin',mnorm[:,ids]),'morphNames':names,'vertexCount':len(ids)}
            if kind=='eye':spec['eyePivot']=((base.min(0)+base.max(0))/2).tolist()
            parts.append(spec)
        report.append({'mesh':name,'nativeVertices':source_vertices,'subdividedVertices':len(base),'nativeShapes':len(names),'subdivision':'2 Catmull-Clark steps; face-varying UV interpolation linear'})
        print(name,source_vertices,'->',len(base),len(names),'native shapes',flush=True)
    result={'source':'NVIDIA Audio2Face Samples_2023.2 / Reallusion Debra GameBase','parts':parts,'materials':mats,'limits':['Native Reallusion expression mapping is approximate, not NVIDIA character-transfer graph execution.','No separate hair geometry is included in this sample.','Some independent tongue channels and jawForward have no native equivalent.']}
    (OUT/'scene.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'verification-debra-conversion.json').write_text(json.dumps({'meshes':report,'source':'Debra_A2F.usd','claireVertexDeltasUsed':False},indent=2))
    print('DONE',flush=True)

if __name__=='__main__':main()
