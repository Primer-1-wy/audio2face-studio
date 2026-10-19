"""Bake a browser preview using Allison's authored character-transfer bind.

Read USD numeric data only. Closest-triangle barycentric interpolation reproduces
a surface transfer from the authored open-mouth bind, not OmniGraph execution.
No vertex IDs are copied from Claire onto the unrelated Allison topology.
"""
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image
from pxr import Usd,UsdGeom
import OpenEXR

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'assets/allison-official';OUT=ROOT/'viewer/official-allison'
OUT.mkdir(exist_ok=True)

def buf(name,a,dtype='<f4'):
    a=np.asarray(a,dtype=dtype);assert np.isfinite(a).all();a.tofile(OUT/name);return 'official-allison/'+name

def normals(v,tri):
    n=np.zeros_like(v);f=np.cross(v[tri[:,1]]-v[tri[:,0]],v[tri[:,2]]-v[tri[:,0]])
    for i in range(3):np.add.at(n,tri[:,i],f)
    return n/np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)

def geometry(p):
    m=UsdGeom.Mesh(p);v=np.array(m.GetPointsAttr().Get(),dtype='float32')
    counts=np.array(m.GetFaceVertexCountsAttr().Get());ids=np.array(m.GetFaceVertexIndicesAttr().Get());corners=[];offset=0
    for n in counts:
        for i in range(1,n-1):corners.append([offset,offset+i,offset+i+1])
        offset+=n
    corners=np.array(corners);tri=ids[corners]
    pv=UsdGeom.PrimvarsAPI(p);uv=pv.GetPrimvar('st')
    if not uv:uv=pv.GetPrimvar('map1')
    if not uv:uv=pv.GetPrimvar('st0')
    uv=np.array(uv.ComputeFlattened())[corners] if uv else np.zeros((*tri.shape,2))
    return v,tri,uv

def bind(points,base,tri):
    # Candidate triangle projection with closest-edge fallback, preserving
    # the open-mouth separation provided in the official transfer scene.
    faces=base[tri];tree=cKDTree(faces.mean(1));all_ids=[];all_w=[];errors=[]
    for offset in range(0,len(points),2048):
        q=points[offset:offset+2048];_,ids=tree.query(q,k=16);f=faces[ids];a,b,c=f[:,:,0],f[:,:,1],f[:,:,2];p=q[:,None,:]
        v0=b-a;v1=c-a;v2=p-a
        dot=lambda x,y:np.sum(x*y,axis=-1)
        d00=dot(v0,v0);d01=dot(v0,v1);d11=dot(v1,v1);d20=dot(v2,v0);d21=dot(v2,v1)
        den=np.maximum(d00*d11-d01*d01,1e-15)
        wb=(d11*d20-d01*d21)/den;wc=(d00*d21-d01*d20)/den;wa=1-wb-wc
        w=np.stack([wa,wb,wc],axis=-1);projected=(f*w[:,:,:,None]).sum(2)
        distances=dot(projected-p,projected-p);distances[np.min(w,axis=-1)<0]=np.inf
        for start,end in [(0,1),(1,2),(2,0)]:
            edge=f[:,:,end]-f[:,:,start];t=np.clip(dot(p-f[:,:,start],edge)/np.maximum(dot(edge,edge),1e-15),0,1)
            nearest=f[:,:,start]+t[:,:,None]*edge;dist=dot(nearest-p,nearest-p);take=dist<distances
            ew=np.zeros_like(w);ew[:,:,start]=1-t;ew[:,:,end]=t
            w=np.where(take[:,:,None],ew,w);distances=np.minimum(distances,dist)
        best=distances.argmin(1);row=np.arange(len(q));all_ids.append(tri[ids[row,best]]);all_w.append(w[row,best]);errors.extend(np.sqrt(distances[row,best]))
    return np.concatenate(all_ids),np.concatenate(all_w),np.array(errors)

def texture(name,color=False,size=4096):
    source=SOURCE/'textures'/name;dest=OUT/(source.stem+'.png')
    if source.suffix=='.exr':
        with OpenEXR.File(str(source)) as ex:
            ch=ex.channels();a=ch.get('RGB',ch.get('RGBA')).pixels[:,:,:3]
            a=np.stack([np.array(Image.fromarray(a[:,:,i].astype('float32')).resize((size,size),Image.Resampling.LANCZOS)) for i in range(3)],axis=2)
        if color:a=np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
        Image.fromarray(np.uint8(np.clip(a,0,1)*255+.5)).save(dest)
    else:
        im=Image.open(source);im.thumbnail((size,size));im.save(dest)
    return 'official-allison/'+dest.name

def main():
    s=Usd.Stage.Open(str(SOURCE/'allison_fullface.usd'));raw=Usd.Stage.Open(str(SOURCE/'allison.usd'))
    driver,tri,_=geometry(s.GetPrimAtPath('/World/a2fTemplates/gen_openMouth'))
    bound=np.array(s.GetPrimAtPath('/World/LazyGraph/m_head_mid_result_SetPoints').GetAttribute('inputs:points').Get())
    ids,w,error=bind(bound,driver,tri)
    f=np.load(ROOT/'assets/claire/bs_skin.npz',allow_pickle=False)
    names=[x.decode() if isinstance(x,bytes) else str(x) for x in f['poseNames'][1:]]
    assert len(driver)==len(f['neutral'])==61520
    source_tri=np.fromfile(ROOT/'viewer/geometry/skin.indices.bin',dtype='<u4').reshape(-1,3)
    assert np.array_equal(tri,source_tri),'Driver topology must exactly match the Claire shapes'
    space=np.array(s.GetPrimAtPath('/World/transfer_character/m_head_mid_result/deltaBlend_space').GetAttribute('xformOp:transform').Get())[:3,:3]
    delta=np.stack([((f[n][ids]*w[:,:,None]).sum(1)@space) for n in names]).astype('float32')
    base_skin=np.array(UsdGeom.Mesh(raw.GetPrimAtPath('/World/allison_models_grp/m_head_mid')).GetPointsAttr().Get())
    skin_tree=cKDTree(base_skin);parts=[]
    skinmap=texture('allison_head_diff_linear.exr',True);normalmap=texture('allison_headDetail1_norm.exr');eyemap=texture('eye_Base_Color_vd1.png',True,2048)
    for p in raw.Traverse():
        if not p.IsA(UsdGeom.Mesh):continue
        name=p.GetName();base,indices,uv=geometry(p);morphs=None;pose_names=[]
        kind='skin' if name=='m_head_mid' else 'brow' if 'brow' in name else 'cornea' if 'cornea' in name else 'eye'
        if kind=='skin':morphs=delta;pose_names=names
        elif kind=='brow':
            d,near=skin_tree.query(base,k=3);weights=1/np.maximum(d,.002)**2;weights/=weights.sum(1,keepdims=True)
            morphs=(delta[:,near]*weights[None,:,:,None]).sum(2);pose_names=names
        n=normals(base,indices)
        dn=np.stack([normals(base+d,indices)-n for d in morphs]) if morphs is not None else None
        verts=indices.flatten();coords=uv.reshape(-1,2);_,first,inverse=np.unique(np.c_[verts,coords],axis=0,return_index=True,return_inverse=True);vi=verts[first]
        spec={'name':name,'kind':kind,'base':buf(name+'.pos.bin',base[vi]),'normals':buf(name+'.normal.bin',n[vi]),'uv':buf(name+'.uv.bin',coords[first]),'indices':buf(name+'.idx.bin',inverse,'<u4'),'morphNames':pose_names,'vertexCount':len(vi)}
        if morphs is not None:spec.update(morphs=buf(name+'.morph.bin',morphs[:,vi]),morphNormals=buf(name+'.morph-normal.bin',dn[:,vi]))
        if kind=='skin':spec.update(map=skinmap,normalMap=normalmap)
        if kind=='eye':spec.update(map=eyemap,eyePivot=((base.min(0)+base.max(0))/2).tolist())
        parts.append(spec);print(name,len(base),len(pose_names),flush=True)
    # Fit auxiliary Claire denture/tongue meshes into Allison's oral region.
    # They are explicitly adapted accessories, not native Allison assets.
    rest=np.array(s.GetPrimAtPath('/World/LazyGraph/m_head_mid_result_SetPoints_01').GetAttribute('inputs:points').Get())
    mask=(rest[:,1]>138)&(rest[:,1]<146)&(rest[:,2]>0)&(abs(rest[:,0])<4)
    affine=np.linalg.lstsq(np.c_[rest[mask],np.ones(mask.sum())],base_skin[mask],rcond=None)[0]
    aux=json.loads((ROOT/'viewer/official-claire/scene.json').read_text())
    for original in aux['parts']:
        if original['kind'] not in ['dental','tongue']:continue
        spec=dict(original);tag='adapted-'+spec['name'];spec['name']=tag
        base=np.fromfile(ROOT/'viewer'/original['base'],dtype='<f4').reshape(-1,3)
        base=(np.c_[base,np.ones(len(base))]@affine).astype('float32')
        tri=np.fromfile(ROOT/'viewer'/original['indices'],dtype='<u4').reshape(-1,3);n=normals(base,tri)
        spec['base']=buf(tag+'.pos.bin',base);spec['normals']=buf(tag+'.normal.bin',n)
        if original.get('morphs'):
            d=np.fromfile(ROOT/'viewer'/original['morphs'],dtype='<f4').reshape(len(spec['morphNames']),-1,3)@affine[:3,:]
            spec['morphs']=buf(tag+'.morph.bin',d);spec['morphNormals']=buf(tag+'.morph-normal.bin',np.stack([normals(base+x,tri)-n for x in d]))
        spec['jawDriven']='bottomDenture' in tag or spec['kind']=='tongue';parts.append(spec)
    jaw_pivot=(np.array([0,145,-5,1])@affine).tolist()
    result={'label':'Allison','source':'NVIDIA Audio2Face Samples_2023.2 character-transfer example','parts':parts,'bounds':{'min':base_skin.min(0).tolist(),'max':base_skin.max(0).tolist()},'jawPivot':jaw_pivot,'mappedChannels':68,'limits':['52 face channels baked using closest-triangle interpolation of the authored bind. Not an execution of the NVIDIA OmniGraph solver.','Denture, 16 tongue shapes and groom are fitted Claire accessories, not native Allison assets.']}
    (OUT/'scene.json').write_text(json.dumps(result,indent=2))
    report={'sourceTopologyExact':True,'sourceVertices':len(driver),'targetVertices':len(bound),'barycentricWeightsSumError':float(abs(w.sum(1)-1).max()),'bindDistanceCmPercentiles':np.percentile(error,[50,95,99,100]).tolist(),'mappedFaceChannels':len(names),'method':'Authored character-transfer bind plus closest-triangle barycentric interpolation and authored delta-space matrix.'}
    (ROOT/'verification-allison-transfer.json').write_text(json.dumps(report,indent=2));print(report)

if __name__=='__main__':main()
