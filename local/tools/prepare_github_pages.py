#!/usr/bin/env python3
"""Build a portable, bounded-size Pages distribution from this local project.

The original float32 inference data is never modified. Public animation blocks
use signed 16-bit quantization, temporal differences and gzip. Geometric error
is at most .0005 cm per coordinate; eye angle error at most .005 degrees.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
import zipfile
import numpy as np
from PIL import Image


def json_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--local-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repository',default='Primer-1-wy/audio2face-studio')
    args=parser.parse_args()
    root,out=args.local_root.resolve(),args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    site=out/'docs';site.mkdir(exist_ok=True)
    data=root/'demo-data/v3-20s-01-05'
    manifest=json.loads((data/'web/manifest.json').read_text())
    manifest['scene']='data/scene.json'
    manifest['encoding']='delta16-gzip-v1'
    manifest['positionStepCm']=.001
    manifest['angleStepDegrees']=.01
    report={'encoding':manifest['encoding'],'fps':60,'positionStepCm':.001,'angleStepDegrees':.01,'demos':[]}
    scale=np.full(manifest['stride'],.001,dtype='float64');scale[-4:]=.01
    for demo in manifest['demos']:
        dest=site/'data'/demo['id'];dest.mkdir(parents=True,exist_ok=True)
        for key in ('audio','video','jaw','details'):
            original=root/demo[key].lstrip('/')
            target=dest/original.name
            shutil.copyfile(original,target)
            demo[key]=str(target.relative_to(site))
        details=json.loads((dest/'details.json').read_text())
        # Keep only the documented run metadata. No machine inventory or paths.
        details['run']={k:details['run'][k] for k in ('id','title','model_repository','model_revision','identity','duration_seconds','fps','frame_count','prediction_shape','channel_slices','emotion_source','postprocessing','inference_timing')}
        json_write(dest/'details.json',details)
        for key in ('metrics','track','run'):
            source=root/demo['downloads'][key].lstrip('/')
            if key=='run':json_write(dest/source.name,details['run'])
            else:shutil.copyfile(source,dest/source.name)
            demo['downloads'][key]=str((dest/source.name).relative_to(site))
        demo['downloads'].pop('motion',None)
        chunks=[];max_position_error=0.;max_eye_error=0.;total=0
        for index,url in enumerate(demo['chunks']):
            original=np.fromfile(root/url.lstrip('/'),dtype='<f4').reshape(-1,manifest['stride'])
            q=np.rint(original/scale).astype('int32')
            assert q.min()>=-32768 and q.max()<=32767,'Quantization would overflow'
            delta=q.copy();delta[1:]=q[1:]-q[:-1]
            assert delta.min()>=-32768 and delta.max()<=32767,'Temporal delta would overflow'
            packed=gzip.compress(delta.astype('<i2').tobytes(),compresslevel=6,mtime=0)
            # Verify the same decoder used in the browser, for every value.
            unpack=np.frombuffer(gzip.decompress(packed),dtype='<i2').reshape(q.shape)
            decoded=np.cumsum(unpack,axis=0,dtype='int32')*scale
            pe=float(np.abs(decoded[:,:-4]-original[:,:-4]).max())
            ee=float(np.abs(decoded[:,-4:]-original[:,-4:]).max())
            assert pe<=.00050001 and ee<=.00500001
            max_position_error=max(max_position_error,pe);max_eye_error=max(max_eye_error,ee)
            target=dest/f'{index:03}.dq16.gz';target.write_bytes(packed)
            chunks.append(str(target.relative_to(site)));total+=len(packed)
        demo['chunks']=chunks
        report['demos'].append({'id':demo['id'],'frames':demo['frameCount'],'maxCoordinateErrorCm':max_position_error,'maxEyeErrorDegrees':max_eye_error,'compressedBytes':total})
        print(demo['id'],round(total/1e6,1),'MB; max coordinate error',max_position_error,'cm',flush=True)
    json_write(site/'data/manifest.json',manifest)
    json_write(site/'data/validation.json',report)

    scene=json.loads((data/'web/scene.json').read_text())
    def asset(url):
        source=root/url.lstrip('/')
        folder='textures' if source.suffix=='.png' else 'geometry'
        target=site/folder/source.name;target.parent.mkdir(exist_ok=True)
        if source.suffix=='.png':
            with Image.open(source) as image:
                image.thumbnail((2048,2048),Image.Resampling.LANCZOS);image.save(target,optimize=True)
        else:shutil.copyfile(source,target)
        return str(target.relative_to(site))
    for spec in scene['canonical'].values():
        for key in ('base','indices'):spec[key]=asset(spec[key])
    for spec in scene['parts']:
        for key in ('base','uv','indices','sourceVertices','map','normalMap','roughnessMap'):
            if spec.get(key):spec[key]=asset(spec[key])
    json_write(site/'data/scene.json',scene)
    for filename in ('index.html','style.css','app.js','renderer.js','chunk-cache.js'):
        text=(root/'viewer/inference'/filename).read_text()
        text=text.replace("'/demo-data/v3-20s-01-05/web/manifest.json'","'data/manifest.json'")
        text=text.replace('/demo-data/v3-20s-01-05/web/validation.json','data/validation.json')
        text=text.replace('../node_modules/three/','./vendor/three/')
        text=text.replace('LOCAL STUDIO','INFERENCE GALLERY').replace('● 本地工作空间','● 在线演示')
        text=text.replace('href="../"','href="./"')
        text=text.replace('<a href="../?asset=official-allison">人物回放</a>','<a href="training.html">训练流程</a>')
        text=text.replace('<a href="../training/">训练工作台</a>',f'<a href="https://github.com/{args.repository}" target="_blank" rel="noopener">GitHub 源码 ↗</a>')
        text=text.replace(' · 原始顶点动画',' · 60 fps 顶点动画')
        text=text.replace('float32 原始结果','60 fps 压缩预览 · 数据来源见说明')
        text=text.replace('原始文件与渲染说明','数据下载与渲染说明')
        text=text.replace('皮肤和舌头按 neutral + 原始位移回放，无嘴形缩放或平滑。','皮肤和舌头按 neutral + 位移回放，无嘴形缩放或平滑。在线数据采用 16 位量化压缩，保留全部 60 fps；每个坐标的量化误差 ≤ 0.005 mm，眼球角度误差 ≤ 0.005°。原始 float32 NPZ 保存在本地项目中。')
        text=text.replace("[['动画 NPZ',demo.downloads.motion],",'[')
        text=text.replace('原始 60 fps 数据','60 fps 压缩预览数据')
        text=text.replace('查看本地数据校验报告','查看压缩精度校验报告')
        if filename=='app.js':
            text=text.replace('chunkFrames:manifest.chunkFrames});','chunkFrames:manifest.chunkFrames,encoding:manifest.encoding});')
        if filename=='chunk-cache.js':
            text="import {decodeDelta16} from './motion-codec.js';\n"+text
            text=text.replace('limit=4, fetcher=',"limit=4, encoding='float32', fetcher=")
            text=text.replace('{demo,stride,chunkFrames,limit,fetcher}','{demo,stride,chunkFrames,limit,encoding,fetcher}')
            text=text.replace('const buffer=await response.arrayBuffer();',"const raw=await response.arrayBuffer();\n      const buffer=this.encoding==='delta16-gzip-v1'?await decodeDelta16(raw,this.stride):raw;")
        (site/filename).write_text(text)
    vendor=site/'vendor/three';vendor.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root/'viewer/node_modules/three/build',vendor/'build',dirs_exist_ok=True)
    for relative in ('controls/OrbitControls.js','environments/RoomEnvironment.js','utils/BufferGeometryUtils.js'):
        path=vendor/'examples/jsm'/relative;path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'viewer/node_modules/three/examples/jsm'/relative,path)
    shutil.copyfile(root/'viewer/node_modules/three/LICENSE',vendor/'LICENSE')
    licenses=site/'licenses';licenses.mkdir(exist_ok=True)
    for p in (data/'LICENSES').iterdir():
        if p.is_file():shutil.copyfile(p,licenses/p.name)
    shutil.copyfile(root/'assets/claire/NVIDIA_OPEN_MODEL_LICENSE.pdf',licenses/'NVIDIA_OPEN_MODEL_LICENSE.pdf')
    (site/'.nojekyll').touch()
    # Include readable source for the existing local workbench, excluding all
    # environments, model weights, credentials, job records and generated media.
    local=out/'local';local.mkdir(exist_ok=True)
    for dirname in ('tools','unreal','viewer'):
        for path in (root/dirname).rglob('*'):
            rel=path.relative_to(root)
            if not path.is_file() or path.suffix not in {'.py','.mjs','.js','.html','.css','.md','.txt','.json','.ts'}:continue
            if any(x in {'node_modules','__pycache__','models','geometry'} or x.startswith('official-') for x in rel.parts):continue
            if dirname=='viewer' and len(rel.parts)>2 and rel.parts[1] not in {'training','inference'}:continue
            if path.name in {'data.json','mesh.json','worker.js'}:continue
            target=local/rel;target.parent.mkdir(parents=True,exist_ok=True)
            text=path.read_text().replace(str(root),'/path/to/audio2face-local').replace('/path/to/downloads','/path/to/downloads')
            target.write_text(text)
    for name in ('serve_preview.py','training_service.py','README.md','requirements-lock.txt'):
        text=(root/name).read_text().replace(str(root),'/path/to/audio2face-local').replace('/path/to/downloads','/path/to/downloads')
        if name=='requirements-lock.txt':text='\n'.join(line for line in text.splitlines() if ' @ file:' not in line)+'\n'
        (local/name).write_text(text)
    print('Site built',site,'bytes',sum(p.stat().st_size for p in site.rglob('*') if p.is_file()),flush=True)


if __name__=='__main__':main()
