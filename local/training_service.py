"""Loopback API for a real, SSH-backed NVIDIA training pipeline. No simulated jobs."""
import base64
import csv
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import threading
import time
import uuid
import wave
import zipfile

ROOT = Path(__file__).resolve().parent
WORKER = ROOT/'viewer/training/worker.py'
spec = importlib.util.spec_from_file_location('a2f_worker', WORKER)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
TERMINAL = {'succeeded','failed','cancelled','unknown'}

def ssh_command(plan, mode, job=None):
    p = worker.validate(plan)
    if not p['host']: raise ValueError('请先填写 GPU 训练机的 SSH 地址')
    payload = {'mode':mode,'plan':p,'job':job}
    script = 'import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(WORKER.read_bytes()).decode())+'),"a2f-worker","exec"))'
    remote = ' '.join(shlex.quote(v) for v in ['python3','-u','-c',script,json.dumps(payload)])
    return ['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
            '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-p',str(p['port']),p['host'],remote]

def remote_json(plan, mode, job=None):
    try:
        result = subprocess.run(ssh_command(plan,mode,job),capture_output=True,text=True,timeout=150)
    except subprocess.TimeoutExpired as e: raise ValueError('SSH 检查超时；请确认网络和 Docker 状态') from e
    if result.returncode: raise ValueError((result.stderr or result.stdout or 'SSH 执行失败')[-4000:])
    try: return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError) as e: raise ValueError('训练机没有返回有效结果：'+result.stdout[-1000:]) from e

def current_data():
    data = ROOT/'demo-data/emotions-56s'
    files = sorted(p.name for p in data.iterdir() if p.is_file()) if data.exists() else []
    result = {'files':files,'trainable':False,'reason':'这是服务器推理结果；缺少与原始录音同步、拓扑一致的真实面部顶点动画标注。'}
    wav = data/'audio.wav'
    if wav.exists():
        with wave.open(str(wav)) as f: result.update(seconds=round(f.getnframes()/f.getframerate(),3),sample_rate=f.getframerate())
    for file in data.glob('*.csv'):
        with file.open(newline='') as f:
            reader=csv.reader(f);header=next(reader,[]);rows=sum(1 for _ in reader)
        result[file.name]={'columns':len(header),'frames':rows}
    return result

def bundle(plan):
    plan=worker.validate(plan)
    output=io.BytesIO()
    readme='''Audio2Face-3D training workbench\n\nOn a Linux/WSL machine with an NVIDIA GPU (at least 6 GB), Docker, NVIDIA Container Toolkit, Python 3, Git and Git LFS:\n\n1. Review plan.json. Set root to a writable Linux directory. For custom data, set data_path to the actor folder containing audio/ and cache/skin/.\n2. Run: python3 worker.py run-plan plan.json\n\nThis performs real downloads, Docker image build, data audit, deterministic shot split, preprocessing, training and ONNX export. Diffusion also generates an animation for one held-out recording. Regression Python inference is not implemented in this NVIDIA revision; validate the exported model using Maya-ACE.\n\nThe workbench requires at least 5 paired shots to leave out validation data. WAV: >=16kHz, >=16bit PCM. NPY: float32/64 [frames, vertices, 3], consistent topology and FPS. Maya MC/XML and PC2 are also accepted. Naming: audio/shot01_neutral.wav paired with cache/skin/shot01_neutral.npy (or .pc2, or shot01_neutral/shot01_neutral.xml + .mc). Emotional suffixes must match the emotions list. All data must already be synchronized and head-stabilized. Vertex-order/quality checks still require a DCC tool.\n\nTraining and held-out shots are separated before PCA/preprocessing (seed 42, about 20% held out); no quality pass is inferred automatically. Custom data is not uploaded by the website. Outputs remain on the GPU machine under root/jobs/<job>. Exported vertex caches require character-specific retargeting to drive a browser rig or MetaHuman.\n\nFor fine-tuning, supply a compatible training .pth checkpoint. Topology, model configuration and latent dimensions must match; ONNX/NPZ inference assets are not training checkpoints. This initializes weights, not optimizer-state resume.\n\nNVIDIA source revision: '''+worker.COMMIT+'\n'+worker.REPO+'\n\nNo GPU execution has been verified on the current Mac. Network downloads and compatible GPU infrastructure are required for an actual run.\n'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('plan.json',json.dumps(plan,ensure_ascii=False,indent=2))
        z.write(WORKER,'worker.py');z.writestr('README.txt',readme)
    return output.getvalue()

class TrainingService:
    def __init__(self, state_dir=None):
        self.root=Path(state_dir or ROOT/'training-runs')
        self.lock=threading.RLock();self.checks={};self.jobs={}
        if self.root.exists():
            for f in sorted(self.root.glob('job-*.json'))[-100:]:
                try:
                    j=json.loads(f.read_text())
                    if j['status'] not in TERMINAL:
                        j['status']='unknown';j['detail']='本地服务曾中断，远端状态未知；请检查训练机后再启动新任务。'
                    self.jobs[j['id']]=j
                except (ValueError,KeyError):continue
    def save(self,job):
        self.root.mkdir(parents=True,exist_ok=True)
        file=self.root/(job['id']+'.json');temp=file.with_suffix('.tmp')
        temp.write_text(json.dumps(job,ensure_ascii=False,indent=2));temp.replace(file)
    def snapshot(self):
        with self.lock:return json.loads(json.dumps({'jobs':list(self.jobs.values())[-20:],'commit':worker.COMMIT}))
    def inspect(self,plan):
        p=worker.validate(plan);result=remote_json(p,'inspect')
        key=worker.fingerprint(p)
        with self.lock:self.checks[key]={'time':time.time(),'ready':result.get('ready',False)}
        return result
    def start(self,plan):
        p=worker.validate(plan);key=worker.fingerprint(p)
        with self.lock:
            check=self.checks.get(key,{})
            if not check.get('ready') or time.time()-check.get('time',0)>600:raise ValueError('请用当前配置完成训练机检查；检查结果有效期为 10 分钟')
            if any(j['status'] not in TERMINAL for j in self.jobs.values()):raise ValueError('已有任务运行中，请等待或停止当前任务')
            if any(j['status']=='unknown' for j in self.jobs.values()):raise ValueError('存在状态未知的远端任务，请先点击“停止任务”确认结束')
            job={'id':'job-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6], 'plan':p,
                'status':'starting','stage':'environment','stages':{},'created':time.time(),'detail':'正在连接训练机','log_tail':''}
            self.jobs[job['id']]=job;self.save(job)
            threading.Thread(target=self.run,args=(job,),daemon=True).start()
            return json.loads(json.dumps(job))
    def run(self,job):
        log=self.root/(job['id']+'.log');complete=False
        try:
            process=subprocess.Popen(ssh_command(job['plan'],'run',job['id']),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            with log.open('a') as out:
                for line in process.stdout:
                    out.write(line);out.flush()
                    with self.lock:
                        job['log_tail']=(job['log_tail']+line)[-24000:]
                        if line.startswith('A2F_EVENT '):
                            try:event=json.loads(line[10:])
                            except ValueError:continue
                            stage=event.get('stage');status=event.get('status')
                            if stage and status=='running':
                                previous=job.get('stage')
                                if previous in job['stages'] and job['stages'][previous]=='running':job['stages'][previous]='succeeded'
                                job['stage']=stage;job['stages'][stage]='running'
                            if status=='skipped':job['stages'][stage]='skipped'
                            if status in TERMINAL:
                                complete=True
                                if status=='succeeded':
                                    job['stages']={k:('succeeded' if v=='running' else v) for k,v in job['stages'].items()}
                                elif job.get('stage'):job['stages'][job['stage']]=status
                            if status!='skipped':job['status']=status
                            job['detail']=event.get('detail','')
                            if 'artifacts' in event:job['artifacts']=event['artifacts']
                        self.save(job)
                code=process.wait()
                process.stdout.close()
            with self.lock:
                if not complete:
                    job['status']='unknown' if code==255 else 'failed'
                    job['detail']='SSH 连接断开，远端状态未知；请检查或停止远端任务。' if code==255 else f'进程退出（{code}），未收到成功事件，请查看日志。'
                elif code and job['status']=='succeeded':job.update(status='failed',detail=f'进程异常退出（{code}）')
                job['finished']=time.time();self.save(job)
        except Exception as e:
            with self.lock:job.update(status='failed',detail=str(e));self.save(job)
    def cancel(self,job_id):
        with self.lock:
            if job_id not in self.jobs:raise ValueError('任务不存在')
            job=self.jobs[job_id]
            if job['status'] in TERMINAL-{'unknown'}:return {'detail':'任务已经结束'}
        result=remote_json(job['plan'],'cancel',job_id)
        with self.lock:
            job['detail']=result['detail']
            if job['status']=='unknown' and result.get('stopped'):job['status']='cancelled'
            self.save(job)
        return result

SERVICE=TrainingService()
