#!/usr/bin/env python3
"""Linux/WSL GPU worker. Standard-library orchestration of pinned NVIDIA code.

Download this file and a plan from the workbench, then run:
    python3 worker.py run-plan plan.json
No training is simulated. Every stage checks the actual subprocess return code.
"""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import runpy
import shutil
import signal
import struct
import subprocess
import sys
import time
import wave

COMMIT = '112c5eb3408afd065ac8974b2c6ea9ab0e3965c6'
REPO = 'https://github.com/NVIDIA/Audio2Face-3D-Training-Framework.git'
DATASET = 'Audio2Face-3D-Dataset-v1.0.0-claire'
IMAGE = 'a2f-workbench:' + COMMIT[:12]
IDENTIFIER = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')

def absolute_path(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'/[a-zA-Z0-9_./-]+', value) or '..' in Path(value).parts or value == '/':
        raise ValueError(name + ' 必须是 Linux 绝对路径，只使用字母、数字、下划线、点、横线和斜杠')
    return value.rstrip('/')

def integer(value, default, name):
    if value is None or value == '':return default
    number=float(value)
    if isinstance(value,bool) or not math.isfinite(number) or not number.is_integer():raise ValueError(name+' 必须是整数')
    return int(number)

def validate(raw):
    p = {k: raw.get(k) for k in ['host', 'port', 'root', 'dataset', 'data_path', 'actor', 'model', 'epochs', 'fps', 'language', 'checkpoint', 'emotions']}
    p['host'] = p['host'] or ''
    if p['host'] and not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_.-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*', p['host']):
        raise ValueError('SSH 地址需使用 user@host；不接受额外命令参数')
    p['port'] = integer(p['port'],22,'SSH 端口')
    if not 1 <= p['port'] <= 65535: raise ValueError('SSH 端口无效')
    p['root'] = absolute_path(p['root'] or '/home/ubuntu/audio2face', '训练目录')
    if p['dataset'] not in ['sample', 'custom']: raise ValueError('请选择官方样例或自己的数据')
    if p['model'] not in ['regression', 'diffusion']: raise ValueError('未知模型类型')
    p['actor'] = 'claire' if p['dataset'] == 'sample' else (p['actor'] or 'actor')
    if not IDENTIFIER.fullmatch(p['actor']): raise ValueError('角色名格式无效')
    p['data_path'] = str(Path(p['root']) / 'datasets' / DATASET / 'data/claire') if p['dataset'] == 'sample' else absolute_path(p['data_path'], '数据目录')
    p['epochs'] = integer(p['epochs'],400 if p['model'] == 'diffusion' else 50,'训练轮数')
    if not 1 <= p['epochs'] <= 10000: raise ValueError('训练轮数需在 1–10000 之间')
    p['fps'] = 30 if p['dataset'] == 'sample' else float(30 if p['fps'] is None or p['fps']=='' else p['fps'])
    if not math.isfinite(p['fps']) or not 1 <= p['fps'] <= 120: raise ValueError('FPS 无效')
    p['language'] = p['language'] or 'zh'
    if p['language'] not in ['zh', 'en']: raise ValueError('语言需为 zh 或 en')
    p['checkpoint'] = p['checkpoint'] or ''
    if p['checkpoint']:
        p['checkpoint'] = absolute_path(p['checkpoint'], '权重路径')
        if not p['checkpoint'].endswith('.pth'): raise ValueError('微调需要兼容的训练权重 .pth，不能使用 ONNX / NPZ')
    p['emotions'] = p['emotions'] or 'neutral'
    names = [n.strip() for n in p['emotions'].split(',') if n.strip()]
    if not names or any(not IDENTIFIER.fullmatch(n) for n in names) or 'neutral' not in names:
        raise ValueError('情绪名用英文逗号分隔，至少包含 neutral')
    p['emotions'] = ','.join(dict.fromkeys(names))
    return p

def fingerprint(plan):
    return hashlib.sha256(json.dumps(validate(plan), sort_keys=True).encode()).hexdigest()

def npy_header(path):
    with path.open('rb') as f:
        if f.read(6) != b'\x93NUMPY': raise ValueError('不是有效 NPY 文件（检查 Git LFS 是否只下载了指针）')
        major, minor = f.read(2)
        if major not in (1, 2, 3): raise ValueError('不支持的 NPY 版本')
        length = struct.unpack('<H' if major == 1 else '<I', f.read(2 if major == 1 else 4))[0]
        if length > 65536: raise ValueError('NPY 头部过大')
        header = ast.literal_eval(f.read(length).decode('utf-8' if major == 3 else 'latin1'))
        shape = header['shape']; dtype = header['descr']
        if not re.fullmatch(r'[<>=|]f[48]', dtype): raise ValueError('顶点缓存需要 float32 / float64，禁止 object/pickle')
        if len(shape) != 3 or shape[2] != 3 or min(shape) <= 0: raise ValueError('顶点 NPY 形状应为 [帧数, 顶点数, 3]')
        if path.stat().st_size != f.tell() + math.prod(shape) * int(dtype[-1]): raise ValueError('NPY 数据长度与头部不一致')
        return shape

def audit_dataset(root, fps):
    root = Path(root); errors=[]; warnings=[]; shots=[]; vertices=set()
    audios = sorted((root/'audio').glob('*.wav'))
    for audio in audios:
        name=audio.stem
        if not IDENTIFIER.fullmatch(name): errors.append(f'{name}: shot 名需为字母、数字、下划线或横线');continue
        candidates = [root/'cache/skin'/name/f'{name}{ext}' for ext in ['.npy','.xml','.pc2']]+[root/'cache/skin'/f'{name}{ext}' for ext in ['.npy','.xml','.pc2']]
        cache=next((p for p in candidates if p.is_file()),None)
        if cache is None: errors.append(name+': 缺少同名皮肤动画缓存');continue
        try:
            with wave.open(str(audio)) as w:
                duration=w.getnframes()/w.getframerate()
                if w.getframerate()<16000 or w.getsampwidth()<2: raise ValueError('WAV 需至少 16 kHz / 16 bit PCM')
            shape=None
            if cache.suffix=='.npy':
                shape=npy_header(cache);vertices.add(shape[1])
                if abs(shape[0]/fps-duration)>max(.12,2/fps): raise ValueError('音频与缓存时长不一致，请确认 FPS 和音画偏移')
            elif cache.suffix=='.xml':
                if not cache.with_suffix('.mc').is_file(): raise ValueError('Maya cache 缺少配套 .mc')
                warnings.append(name+': Maya 缓存的拓扑和帧数将在官方预处理阶段验证')
            else: warnings.append(name+': PC2 缓存将在官方预处理阶段进一步验证')
            if not 3<=duration<=30: warnings.append(name+': 官方建议每段约 3–30 秒')
            shots.append({'name':name,'duration':round(duration,3),'audio':str(audio.relative_to(root)),'cache':str(cache.relative_to(root)),'shape':shape})
        except (ValueError, OSError, wave.Error, EOFError, SyntaxError, struct.error) as e: errors.append(name+': '+str(e))
    if len(shots)<5: errors.append('本工作台至少需要 5 个配对片段，用于按 shot 留出验证集；这不是官方框架的最低片段数')
    if len(vertices)>1: errors.append('不同片段的顶点数不一致')
    warnings.append('目录检查不能证明顶点顺序一致、音画精确同步或标注质量；仍需在 DCC 中检查。')
    return {'ready':not errors,'shots':shots,'errors':errors,'warnings':warnings[:12]}

def capture(args, timeout=20):
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip()
    except (OSError,subprocess.TimeoutExpired) as e:return 1,str(e)

def inspect(plan):
    p=validate(plan);checks=[]
    def check(name, ok, detail): checks.append({'name':name,'ok':ok,'detail':detail})
    check('Linux / WSL',platform.system()=='Linux',platform.platform())
    code,gpu=capture(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'])
    try: enough=any(int(line.split(',')[1].strip())>=6000 for line in gpu.splitlines())
    except (ValueError,IndexError):enough=False
    check('NVIDIA GPU ≥ 6 GB',code==0 and enough,gpu)
    code,docker=capture(['docker','info','--format','{{json .Runtimes}}'])
    check('Docker + NVIDIA runtime',code==0 and 'nvidia' in docker,docker)
    code,git=capture(['git','--version']);check('Git',code==0,git)
    if p['dataset']=='sample':
        code,lfs=capture(['git','lfs','version']);check('Git LFS',code==0,lfs)
    dataset=audit_dataset(p['data_path'],p['fps']) if Path(p['data_path']).exists() else None
    if p['dataset']=='custom':check('自定义数据',dataset is not None and dataset['ready'],'；'.join(dataset['errors']) if dataset else '训练机上找不到数据目录')
    if p['checkpoint']:check('微调权重',Path(p['checkpoint']).is_file(),p['checkpoint'])
    probe=Path(p['root'])
    while not probe.exists() and probe!=probe.parent:probe=probe.parent
    check('工作目录可写',os.access(probe,os.W_OK),str(probe))
    return {'ready':all(c['ok'] for c in checks),'checks':checks,'dataset':dataset,'sample_download_pending':p['dataset']=='sample' and dataset is None,
        'note':'驱动兼容范围以锁定版本 README 为准。检查成功不代表训练质量已验证。','commit':COMMIT}

def split_shots(shots):
    names=sorted(s['name'] for s in shots);random.Random(42).shuffle(names)
    count=max(1,len(names)//5)
    return sorted(names[count:]),sorted(names[:count])

def emit(**event):print('A2F_EVENT '+json.dumps(event,ensure_ascii=False),flush=True)

class Cancelled(Exception):pass

class Runner:
    def __init__(self,plan,job):
        self.p=validate(plan)
        if not IDENTIFIER.fullmatch(job):raise ValueError('无效任务编号')
        self.job=job;self.root=Path(self.p['root']);self.jobdir=self.root/'jobs'/job
        self.repo=self.root/('framework-'+COMMIT[:12]);self.proc=None;self.container=None
    def command(self,args,cwd=None):
        print('$ '+subprocess.list2cmdline([str(a) for a in args]),flush=True)
        self.proc=subprocess.Popen([str(a) for a in args],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        try:
            for line in self.proc.stdout:print(line.rstrip(),flush=True)
            code=self.proc.wait()
            if code:raise RuntimeError('命令失败，退出码 '+str(code))
        finally:
            if self.proc.poll() is None:
                os.killpg(self.proc.pid,signal.SIGTERM)
                try:self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait()
            self.proc.stdout.close()
            self.proc=None
    def docker(self,stage,script,args):
        self.container='a2f-'+self.job+'-'+stage
        cmd=['docker','run','--rm','--name',self.container,'--gpus','all','--shm-size=8g',
            '-e','GIT_CONFIG_COUNT=1','-e','GIT_CONFIG_KEY_0=safe.directory','-e','GIT_CONFIG_VALUE_0=/framework',
            '-v',str(self.repo)+':/framework:ro','-v',str(self.jobdir)+':/workspace',
            '-v',self.p['data_path']+':/data-source:ro','-w','/framework',IMAGE,'python','-u',script]
        try:self.command(cmd+[json.dumps(v) if isinstance(v,dict) else str(v) for v in args])
        finally:
            capture(['docker','rm','-f',self.container]);self.container=None
    def stage(self,name):emit(stage=name,status='running')
    def run(self):
        if (self.root/('cancel-'+self.job)).exists():emit(status='cancelled',detail='任务在启动前已取消');return
        self.jobdir.mkdir(parents=True,exist_ok=False)
        (self.jobdir/'pid').write_text(str(os.getpid()))
        (self.jobdir/'plan.json').write_text(json.dumps(self.p,indent=2))
        signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(Cancelled()))
        try:
            if (self.root/('cancel-'+self.job)).exists():raise Cancelled()
            self.stage('environment')
            result=inspect(self.p)
            if not result['ready']:raise RuntimeError('环境检查失败：'+json.dumps(result['checks'],ensure_ascii=False))
            if not self.repo.exists():self.command(['git','clone',REPO,self.repo]);self.command(['git','checkout',COMMIT],self.repo)
            code,head=capture(['git','-C',str(self.repo),'rev-parse','HEAD'])
            if code or head!=COMMIT:raise RuntimeError('框架版本不一致，请使用新的训练工作目录')
            if capture(['docker','image','inspect',IMAGE])[0]:self.command(['docker','build','-t',IMAGE,str(self.repo/'docker')])
            self.stage('data')
            source=Path(self.p['data_path'])
            if self.p['dataset']=='sample':
                checkout=self.root/'datasets'/DATASET
                if not checkout.exists():checkout.parent.mkdir(parents=True,exist_ok=True);self.command(['git','clone','https://huggingface.co/datasets/nvidia/'+DATASET,checkout])
                self.command(['git','lfs','pull'],checkout)
            audit=audit_dataset(source,self.p['fps'])
            if not audit['ready']:raise RuntimeError('数据检查失败：'+'；'.join(audit['errors']))
            train_names,test_names=split_shots(audit['shots'])
            (self.jobdir/'dataset-audit.json').write_text(json.dumps(audit,indent=2))
            (self.jobdir/'split.json').write_text(json.dumps({'seed':42,'train':train_names,'validation':test_names},indent=2))
            # Only training shots enter PCA/preprocessing. Links resolve INSIDE Docker.
            staged=self.jobdir/'dataset'
            for shot in audit['shots']:
                if shot['name'] not in train_names:continue
                paths=[Path(shot['audio']),Path(shot['cache'])]
                if paths[-1].suffix=='.xml':paths.append(paths[-1].with_suffix('.mc'))
                for rel in paths:
                    # NVIDIA expects cache/skin/<shot>/<shot>.<ext>; accept flat input too.
                    target=Path('cache/skin')/shot['name']/rel.name if rel.parts[0]=='cache' else rel
                    dest=staged/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to('/data-source/'+str(rel))
            template=self.repo/'configs'/('example-'+self.p['model']+'-min')
            configs={k:{n:v for n,v in runpy.run_path(str(template/('config_'+k+'.py'))).items() if not n.startswith('_')} for k in ['dataset','preproc','train','inference']}
            actor=self.p['actor'];d=configs['dataset'];t=configs['train'];pre=configs['preproc'];inf=configs['inference']
            d.update(ACTOR_NAMES=[actor],AUDIO_ROOT={actor:'/workspace/dataset/audio'},SKIN_CACHE_ROOT={actor:'/workspace/dataset/cache/skin'},CACHE_FPS={actor:self.p['fps']})
            if self.p['dataset']=='custom':d['SHOT_EMOTION_NAMES']=self.p['emotions'].split(',')
            pre['RUN_NAME']=self.job
            t.update(RUN_NAME=self.job,NUM_EPOCHS=self.p['epochs'],AUG_MUTED_SHOTS=[],TRAIN_OUTPUT_ROOT='/workspace/output_train',FINAL_DEPLOY_ROOT='/workspace/output_deploy',PREPROC_ROOT='/workspace/output_preproc')
            if self.p['checkpoint']:
                shutil.copyfile(self.p['checkpoint'],self.jobdir/'initial-weights.pth');t['PRETRAINED_NET_FPATH']='/workspace/initial-weights.pth'
            self.stage('preprocess')
            self.docker('preprocess','runners/run_preproc.py',[actor,pre,d])
            outputs=list((self.jobdir/'output_preproc').glob('*'))
            outputs=[p for p in outputs if (p/'deploy/clips_template.py').is_file()]
            if len(outputs)!=1:raise RuntimeError('未找到唯一的预处理产物，不继续训练')
            pre_dir=outputs[0];t['PREPROC_RUN_NAME_FULL']={actor:pre_dir.name}
            # Parse generated literal assignments; never execute generated data files.
            tree=ast.parse((pre_dir/'deploy/clips_template.py').read_text())
            clips=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(a,ast.Name) and a.id=='CLIPS' for a in n.targets))
            if not clips:raise RuntimeError('预处理未生成训练片段')
            # Upstream's generated template defaults every shot to English. Preserve
            # the official dataset's explicit Chinese/English labels instead.
            sample_languages={c[1]:c[4] for c in t['CLIPS']}
            clips=[tuple(list(c[:4])+[self.p['language'] if self.p['dataset']=='custom' else sample_languages.get(c[1],c[4])]+list(c[5:])) for c in clips]
            t['CLIPS']=clips
            if self.p['model']=='regression':inf={'CONFIG':{'source_shot':clips[0][1],'source_frame':clips[0][2][0]}}
            else:inf.update(CONDITION=actor,ACTOR_NAME=actor,AUDIO_PATH='/data-source/audio/'+test_names[0]+'.wav',OUTPUT_NPY_FILE=True,INFERENCE_OUTPUT_ROOT='/workspace/output_inference')
            configs['inference']=inf
            (self.jobdir/'effective-config.json').write_text(json.dumps(configs,indent=2))
            self.stage('train');self.docker('train','runners/run_train.py',[t,d,inf])
            trained=[p for p in (self.jobdir/'output_train').glob('*') if (p/'weights.pth').is_file()]
            if len(trained)!=1:raise RuntimeError('未找到训练权重，不能标记训练成功')
            run=trained[0].name
            self.stage('export');self.docker('export','runners/run_deploy.py',[run,t,inf])
            if not any((self.jobdir/'output_deploy').rglob('*.onnx')):raise RuntimeError('导出未生成 ONNX 模型')
            if self.p['model']=='diffusion':
                self.stage('inference');self.docker('inference','runners/run_inference.py',[run,t,d,inf])
                if not any((self.jobdir/'output_inference').rglob('*.npy')):raise RuntimeError('未生成验证动画')
            else:emit(stage='inference',status='skipped',detail='该版本 Regression Python 推理尚未实现，请在 Maya-ACE 验证导出的模型')
            artifacts={'directory':str(self.jobdir),'weights':str(trained[0]/'weights.pth'),'deployment':str(self.jobdir/'output_deploy'),'validation_shots':test_names,'quality':'待检查口型、同步、抖动及穿模；没有自动判定质量合格'}
            (self.jobdir/'result.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2))
            emit(stage='done',status='succeeded',artifacts=artifacts)
        except Cancelled:emit(status='cancelled',detail='任务已停止');raise SystemExit(130)
        except Exception as e:emit(status='failed',detail=str(e));raise
        finally:(self.jobdir/'pid').unlink(missing_ok=True)

def cancel(plan,job):
    p=validate(plan)
    if not IDENTIFIER.fullmatch(job):raise ValueError('无效任务编号')
    root=Path(p['root']);root.mkdir(parents=True,exist_ok=True)
    (root/('cancel-'+job)).touch()
    pid_file=root/'jobs'/job/'pid'
    if not pid_file.exists():return {'stopped':True,'detail':'已取消待启动任务，或任务进程已结束'}
    pid=int(pid_file.read_text())
    try:cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
    except FileNotFoundError:return {'stopped':True,'detail':'任务进程已结束'}
    if job.encode() not in cmd:raise ValueError('进程身份不匹配，未发送停止信号')
    os.kill(pid,signal.SIGTERM)
    for _ in range(30):
        if not pid_file.exists():return {'stopped':True,'detail':'任务已停止，容器已清理'}
        time.sleep(1)
    return {'stopped':False,'detail':'已发送停止请求，工作进程仍在清理；请稍后再检查'}

def main():
    if sys.argv[1]=='run-plan':
        p=json.loads(Path(sys.argv[2]).read_text());Runner(p,'job-'+time.strftime('%Y%m%d-%H%M%S')).run();return
    request=json.loads(sys.argv[1]);p=request['plan']
    if request['mode']=='inspect':print(json.dumps(inspect(p),ensure_ascii=False))
    elif request['mode']=='cancel':print(json.dumps(cancel(p,request['job']),ensure_ascii=False))
    elif request['mode']=='run':Runner(p,request['job']).run()
    else:raise ValueError('未知操作')

if __name__=='__main__':main()
