"""Convert NVIDIA Claire USD/EXR assets into a local WebGL playback asset.

Source USD, EXR and groom remain untouched. Mesh UV seams and UDIM groups are
preserved. Existing official 68 Claire blendshapes drive identical topology.
Groom is an explicitly reduced browser LOD; facial strands follow skin roots.
"""
from pathlib import Path
import json, sys
import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom
from scipy.spatial import cKDTree
import OpenEXR

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/claire-official'
OUT = ROOT / 'viewer/official-claire'
TEX = SOURCE / 'sourceimages/claire_rt'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {'topology': {}, 'textures': [], 'groom': []}

def buf(name, a, dtype='<f4'):
    a = np.asarray(a, dtype=dtype)
    assert np.isfinite(a).all(), name
    a.tofile(OUT / name)
    return 'official-claire/' + name

def normals(v, tri):
    n = np.zeros_like(v)
    face = np.cross(v[tri[:,1]]-v[tri[:,0]],v[tri[:,2]]-v[tri[:,0]])
    for i in range(3): np.add.at(n, tri[:,i], face)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)

def texture(name, color=False, size=2048, channel=None):
    src = TEX / (name + '.exr')
    if not src.exists(): return None
    suffix = ('-srgb' if color else '-linear') + (('-'+str(channel)) if channel is not None else '')
    dst = OUT / (src.stem + suffix + '.png')
    if not dst.exists():
        with OpenEXR.File(str(src)) as f:
            c=f.channels();a=c.get('RGBA',c.get('RGB'))
            if a is None: a=next(iter(c.values()))
            a=a.pixels
            if a.ndim==2: a=a[:,:,None]
            original=list(a.shape)
            a=a[:,:,:3]
            # Resize floating linear data first, avoiding multi-GB temporary RGB arrays.
            a=np.stack([np.array(Image.fromarray(a[:,:,i].astype('float32')).resize((size,size),Image.Resampling.LANCZOS)) for i in range(a.shape[2])],axis=2)
        if channel is not None: a=np.repeat(a[:,:,channel:channel+1],3,axis=2)
        if a.shape[2]==1: a=np.repeat(a,3,axis=2)
        if color: a=np.where(a<=.0031308,12.92*a,1.055*np.maximum(a,0)**(1/2.4)-.055)
        Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5)).save(dst)
        print('Texture',src.name,original,'->',size,flush=True)
    REPORT['textures'].append({'source':str(src.relative_to(SOURCE)), 'output':dst.name, 'colorSpace':'sRGB' if color else 'linear', 'resolution':size})
    return 'official-claire/'+dst.name

def load_shapes(kind):
    f=np.load(ROOT/f'assets/claire/bs_{kind}.npz',allow_pickle=False)
    names=[x.decode('utf-8') if isinstance(x,bytes) else str(x) for x in f['poseNames'][1:]]
    return f['neutral'], names, np.stack([f[n] for n in names])

skin, skin_names, skin_delta = load_shapes('skin')
skin_tree=cKDTree(skin)
stage=Usd.Stage.Open(str(SOURCE/'claire_lookdev.usda'))
skin_prim=next(p for p in stage.Traverse() if p.GetName()=='c_headWatertight_hi')
source_skin=np.array(UsdGeom.Mesh(skin_prim).GetPointsAttr().Get())
source_tree=cKDTree(source_skin)

def binding(points):
    d, ids=source_tree.query(points,k=3)
    w=1/np.maximum(d,.001)**2;w/=w.sum(axis=1,keepdims=True)
    correction=((skin[ids]-source_skin[ids])*w[:,:,None]).sum(axis=1)
    delta=(skin_delta[:,ids,:]*w[None,:,:,None]).sum(axis=2)
    return correction, delta

def export_mesh(p):
    name=p.GetName();m=UsdGeom.Mesh(p)
    v=np.array(m.GetPointsAttr().Get(0),dtype='float32')
    x=np.array(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0))
    v=(np.c_[v,np.ones(len(v))]@x)[:,:3].astype('float32')
    face_ids=np.array(m.GetFaceVertexIndicesAttr().Get());counts=np.array(m.GetFaceVertexCountsAttr().Get())
    uvvar=UsdGeom.PrimvarsAPI(p).GetPrimvar('st');uv=np.array(uvvar.ComputeFlattened())
    corners=[];offset=0
    for count in counts:
        for i in range(1,count-1): corners.append([offset,offset+i,offset+i+1])
        offset+=count
    corners=np.array(corners);tri=face_ids[corners]
    names=[];deltas=None;normal_deltas=None
    is_skin=name=='c_headWatertight_hi';is_tongue=name=='c_tongue_hi'
    if is_skin or is_tongue:
        kind='skin' if is_skin else 'tongue';base,names,deltas=load_shapes(kind)
        old=np.fromfile(ROOT/f'viewer/geometry/{kind}.indices.bin',dtype='<u4').reshape(-1,3)
        assert np.array_equal(tri,old),f'{kind}: official topology/order mismatch'
        assert v.shape==base.shape
        dist=np.linalg.norm(v-base,axis=1)
        REPORT['topology'][kind]={'vertices':len(v),'triangleOrderExact':True,'sourceToNeutralMaxCm':float(dist.max()),'morphs':len(names)}
        v=base
    elif 'tearline' in name or 'caruncle' in name:
        correction,deltas=binding(v);v+=correction;names=skin_names
    n=normals(v,tri)
    if deltas is not None:
        normal_deltas=np.stack([normals(v+d,tri)-n for d in deltas])
    tiles=np.floor(uv[corners].mean(axis=1)).astype(int)
    unique_tiles=np.unique(tiles,axis=0)
    specs=[]
    for tile_xy in unique_tiles:
        tile=1001+int(tile_xy[0])+10*int(tile_xy[1]);sel=np.all(tiles==tile_xy,axis=1)
        flat=corners[sel].flatten();vid=face_ids[flat];uvs=uv[flat]-tile_xy
        # Duplicate only UV seams. Keep original vertex mapping for every morph.
        keys=np.c_[vid,uvs];unique,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
        ids=vid[first];localuv=uvs[first];tag=f'{name}-{tile}'
        kind='skin' if is_skin else 'tongue' if is_tongue else 'dental' if 'Denture' in name else 'cornea' if 'cornea' in name else 'lens' if 'lens' in name else 'tearline' if 'tearline' in name else 'eye' if 'choroid' in name else 'caruncle' if 'caruncle' in name else 'hairTie'
        spec={'name':tag,'kind':kind,'tile':tile,'vertexCount':len(ids),'base':buf(tag+'.pos.bin',v[ids]),'normals':buf(tag+'.normal.bin',n[ids]),'uv':buf(tag+'.uv.bin',localuv),'indices':buf(tag+'.idx.bin',inverse,'<u4'),'morphNames':names}
        if deltas is not None:
            spec['morphs']=buf(tag+'.morph.bin',deltas[:,ids]);spec['morphNormals']=buf(tag+'.morph-normal.bin',normal_deltas[:,ids])
        if is_skin or is_tongue:
            spec['sourceVertices']=buf(tag+'.source-vertices.bin',ids,'<u4')
        prefix='c_skin' if is_skin else 'c_dental' if kind in ['dental','tongue'] else 'c_eye'
        if kind in ['skin','tongue','dental','eye','caruncle']:
            spec['map']=texture(f'{prefix}_diffuseReflectionColor.{tile}',True,4096 if is_skin and tile==1001 else 2048)
            spec['normalMap']=texture(f'{prefix}_geometryNormal.{tile}',False,4096 if is_skin and tile==1001 else 2048)
        if kind=='eye':
            # The lookdev material explicitly uses the same RT eye texture on both eyes.
            spec['map']=texture('c_eye_diffuseReflectionColor_rt.1013',True)
            spec['normalMap']=texture('c_eye_geometryNormal.1013')
        if is_skin:
            combined=f'combined/c_skin_specularReflectionColor-subsurfaceScatteringColor-specularReflectionRoughness.{tile}'
            spec['roughnessMap']=texture(combined,False,2048,0)
        specs.append(spec)
    print('Mesh',name,len(v),len(tri),'tiles',[s['tile'] for s in specs],flush=True)
    return specs

def export_groom(p):
    m=UsdGeom.BasisCurves(p);name=p.GetName()
    v=np.array(m.GetPointsAttr().Get(0));counts=np.array(m.GetCurveVertexCountsAttr().Get(0));width=np.array(m.GetWidthsAttr().Get(0))
    x=np.array(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0));v=(np.c_[v,np.ones(len(v))]@x)[:,:3].astype('float32')
    # All facial strands; reduced control-point density for the 61k main hairs.
    stride=3 if name=='hairMain' else 1
    starts=np.r_[0,np.cumsum(counts)[:-1]];chosen=np.arange(0,len(counts),stride)
    roots=v[starts[chosen]];correction,root_delta=binding(roots)
    attached=name in ['eyeLashes','eyeBrows','facialHair','babyHairFront']
    positions=[];indices=[];widths=[];root_ids=[];tangents=[];progress=[]
    for j,i in enumerate(chosen):
        sample=np.unique(np.r_[np.arange(0,counts[i],2 if counts[i]>=40 else 1),counts[i]-1]);idx=starts[i]+sample
        pts=v[idx]+correction[j];start=len(positions);positions.extend(pts)
        widths.extend(width[idx] if len(width)==len(v) else np.full(len(idx),float(width[0])))
        tangent=np.gradient(pts,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-9);tangents.extend(tangent)
        root_ids.extend([j]*len(idx));progress.extend(np.linspace(0,1,len(idx)))
        indices.extend([[start+k,start+k+1] for k in range(len(idx)-1)])
    positions=np.array(positions,dtype='float32');root_ids=np.array(root_ids)
    tag='groom-'+name
    # Camera-facing ribbons are made in the vertex shader with original widths.
    spec={'name':name,'kind':'groom','base':buf(tag+'.pos.bin',positions),'tangent':buf(tag+'.tangent.bin',tangents),'width':buf(tag+'.width.bin',widths),'progress':buf(tag+'.progress.bin',progress),'indices':buf(tag+'.idx.bin',indices,'<u4'),'vertexCount':len(positions),'strandCount':len(chosen),'morphNames':skin_names if attached else []}
    if attached:spec['morphs']=buf(tag+'.morph.bin',root_delta[:,root_ids])
    REPORT['groom'].append({'name':name,'sourceStrands':len(counts),'previewStrands':len(chosen),'sourcePoints':len(v),'previewPoints':len(positions),'skinRootBinding':attached})
    print('Groom',name,len(chosen),'strands',len(positions),'points',flush=True)
    return spec

def main():
    parts=[];groom=[]
    for p in stage.Traverse():
        if p.IsA(UsdGeom.Mesh) and p.GetName()!='Disk' and UsdGeom.Imageable(p).ComputeVisibility()!='invisible': parts+=export_mesh(p)
        if p.IsA(UsdGeom.BasisCurves):groom.append(export_groom(p))
    result={'source':'NVIDIA official Claire lookdev 2023_1','parts':parts,'groom':groom,'units':'cm','bounds':{'min':skin.min(0).tolist(),'max':skin.max(0).tolist()},'limits':['WebGL physical materials approximate NVIDIA MDL/RTX subsurface scattering.','Groom is a browser LOD; all source curves are retained.','Lower teeth and tongue receive an approximate jawOpen rigid transform; eye gaze is neutral.']}
    (OUT/'scene.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'verification-official-claire.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2))
    print('DONE',flush=True)

if __name__=='__main__':main()
