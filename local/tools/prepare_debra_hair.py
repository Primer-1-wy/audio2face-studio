"""Create an original short curly groom fitted to Debra's converted scalp.

This is local procedural geometry, not an NVIDIA/Reallusion supplied hairstyle.
Only adds new files; the source mesh, textures and expression targets stay intact.
"""
from pathlib import Path
import json
import argparse
import numpy as np
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[1]
VIEW=ROOT/'viewer'
parser=argparse.ArgumentParser();parser.add_argument('--role',default='debra',choices=['debra','james','mark']);args=parser.parse_args();role=args.role
OUT=VIEW/(role+'-hair')
OUT.mkdir(exist_ok=True)
rng=np.random.default_rng(20261013)
scene=json.loads((VIEW/f'official-{role}/scene.json').read_text())
vertices=np.concatenate([np.fromfile(VIEW/p['base'],dtype='<f4').reshape(-1,3) for p in scene['parts'] if p['kind']=='skin'])
center=np.array([.05,166.8,-1.7]) if role=='debra' else np.array([0,vertices[:,1].max()-9.6,-4 if role=='james' else -7])
scalp=vertices[vertices[:,1]>center[1]-5]
vectors=scalp-center
radii=np.linalg.norm(vectors,axis=1)
tree=cKDTree(vectors/radii[:,None])

def limit(phi):
    c=np.cos(phi)
    return 1.53-.52*np.maximum(c,0)**2+.42*np.maximum(-c,0)**2

def surface(theta,phi):
    directions=np.stack([np.sin(theta)*np.sin(phi),np.cos(theta),np.sin(theta)*np.cos(phi)],axis=-1)
    dist,ids=tree.query(directions,k=6)
    weights=1/np.maximum(dist,.001)**3
    radius=(weights*radii[ids]).sum(-1)/weights.sum(-1)
    return center+directions*radius[...,None],directions

def save(name,positions,indices,colors):
    positions=np.asarray(positions,dtype=np.float32).reshape(-1,3)
    indices=np.asarray(indices,dtype=np.uint32).reshape(-1,3)
    normals=np.zeros_like(positions)
    tris=positions[indices]
    cross=np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])
    for j in range(3):np.add.at(normals,indices[:,j],cross)
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    spec={'name':name,'vertices':len(positions),'triangles':len(indices)}
    for key,array,dtype in [('positions',positions,'<f4'),('normals',normals,'<f4'),('indices',indices,'<u4'),('colors',colors,'<f4')]:
        assert np.isfinite(array).all()
        filename=f'{name}.{key}.bin';np.asarray(array,dtype=dtype).tofile(OUT/filename);spec[key]=role+'-hair/'+filename
    spec['bounds']=[positions.min(0).tolist(),positions.max(0).tolist()]
    return spec

# Thin fitted foundation, covered by individually curved fibers. A deliberately
# irregular edge avoids a perfectly straight helmet-like hairline.
rows,cols=42,160
u,v=np.meshgrid(np.arange(cols+1)/cols,np.arange(rows+1)/rows)
phi=u*2*np.pi
theta=v*(limit(phi)+.007*np.sin(phi*39)+.004*np.cos(phi*71))
cap,n=surface(theta,phi)
cap+=n*(.08+.045*(1-v))[...,None]
idx=[]
for i in range(rows):
    for j in range(cols):
        a=i*(cols+1)+j;b=a+cols+1;idx.extend([[a,a+1,b],[a+1,b+1,b]])
shade=.78+.22*rng.random(cap.shape[:2])
base=np.array([.016,.010,.007])
parts=[save('scalp-foundation',cap,idx,(shade[...,None]*base).reshape(-1,3))]

# Tight but varied curls with fine tapered tips, warm highlights and short
# temple/nape lengths. Their bases are sampled from the actual scalp surface.
count=5200
phi=rng.uniform(-np.pi,np.pi,count)
theta=np.arccos(1-rng.random(count)*(1-np.cos(limit(phi))))
roots,normals=surface(theta,phi)
positions=[];indices=[];colors=[]
steps,sides=24,3
for root,n,th,ph in zip(roots,normals,theta,phi):
    edge=np.clip((limit(ph)-th)/.3,0,1)
    crown=np.clip((1.4-th)/1.4,0,1)
    height=(.22+1.22*edge+.6*crown)*rng.uniform(.8,1.2)*({'debra':1,'james':.4,'mark':.65}[role])
    curl_radius=rng.uniform(.105,.21)*(.4+.6*edge)
    tangent=np.cross(n,[0,1,0]);tangent/=max(np.linalg.norm(tangent),1e-8)
    second=np.cross(n,tangent)
    phase=rng.uniform(0,2*np.pi);turns=rng.uniform(1.05,1.9)
    t=np.linspace(0,1,steps+1)
    angle=phase+t*turns*2*np.pi
    # Mostly upright short curls, gently swept backward over the crown.
    lift=.03+height*np.sin(t*np.pi*.74)
    coil=(np.sin(t*np.pi/2)*curl_radius)
    path=root+lift[:,None]*n+coil[:,None]*(np.cos(angle)[:,None]*tangent+np.sin(angle)[:,None]*second)
    path+=np.array([-.12,0,-.24])[None,:]*t[:,None]**2*edge
    forward=np.gradient(path,axis=0);forward/=np.linalg.norm(forward,axis=1,keepdims=True)
    right=np.cross(forward,np.broadcast_to(tangent,forward.shape));right/=np.maximum(np.linalg.norm(right,axis=1,keepdims=True),1e-8)
    up=np.cross(forward,right)
    thickness=rng.uniform(.016,.031)*(1-.83*t**3)
    hue=np.array([.027,.016,.010])*rng.uniform(.55,1.7)
    start=len(positions)
    for i in range(steps+1):
        for j in range(sides):
            a=j*2*np.pi/sides
            positions.append(path[i]+thickness[i]*(np.cos(a)*right[i]+np.sin(a)*up[i]))
            colors.append(hue*(.78+.22*t[i]))
    for i in range(steps):
        for j in range(sides):
            a=start+i*sides+j;b=start+i*sides+(j+1)%sides
            indices.extend([[a,b,a+sides],[b,b+sides,a+sides]])
parts.append(save('short-curls',positions,indices,colors))
manifest={'title':role.title()+' · 深棕黑短发','origin':'Original procedural hairstyle created locally; not part of the official NVIDIA/Reallusion sample.','strands':count,'parts':parts,'limits':['Static groom attached to the head, without hair physics.']}
(OUT/'scene.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({k:manifest[k] for k in ['title','strands','parts']},ensure_ascii=False,indent=2))
