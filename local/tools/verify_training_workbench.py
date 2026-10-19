#!/usr/bin/env python3
"""Contract, data, failure propagation and localhost API tests. No GPU training."""
import contextlib
import http.client
import io
import json
from pathlib import Path
import runpy
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave
import zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import training_service as service
from training_service import worker
import serve_preview

class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='a2f-tests-');self.root=Path(self.temp.name)
        self.plan={'dataset':'custom','model':'diffusion','data_path':str(self.root/'data'),'root':str(self.root/'work'),'host':'tester@gpu.example','actor':'testactor','epochs':5,'language':'zh'}
    def tearDown(self):self.temp.cleanup()
    def dataset(self):
        data=Path(self.plan['data_path']);(data/'audio').mkdir(parents=True);(data/'cache/skin').mkdir(parents=True)
        for i in range(5):
            name=f'shot{i}_neutral'
            with wave.open(str(data/'audio'/f'{name}.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*48000)
            cache=data/'cache/skin'/f'{name}.npy'
            if i%2:cache=data/'cache/skin'/name/f'{name}.npy';cache.parent.mkdir()
            np.save(cache,np.zeros((90,16,3),dtype=np.float32))
        return data
    def test_validation_and_injection(self):
        for extra in [{'host':'me@host;touch /tmp/no'},{'root':'/tmp/../etc'},{'epochs':-1},{'epochs':0},{'epochs':1.5},{'port':0},{'fps':0},{'checkpoint':'/tmp/a.onnx'},{'fps':float('nan')},{'emotions':'joy'}]:
            with self.subTest(extra=extra),self.assertRaises((ValueError,TypeError)):worker.validate(self.plan|extra)
        self.assertEqual(service.ssh_command(self.plan,'inspect')[-2],'tester@gpu.example')
        with self.assertRaises(ValueError):service.ssh_command(self.plan|{'host':''},'run')
    def test_data_pairs_and_split(self):
        data=self.dataset();report=worker.audit_dataset(data,30);self.assertTrue(report['ready'],report)
        train,test=worker.split_shots(report['shots']);self.assertFalse(set(train)&set(test));self.assertEqual(len(train),4);self.assertEqual(len(test),1)
        self.assertEqual((train,test),worker.split_shots(list(reversed(report['shots']))))
        np.save(data/'cache/skin/shot0_neutral.npy',np.zeros((20,17,3),dtype=np.float32))
        self.assertFalse(worker.audit_dataset(data,30)['ready'])
        (data/'cache/skin/shot0_neutral.npy').write_text('version https://git-lfs.github.com/spec/v1')
        self.assertIn('NPY',' '.join(worker.audit_dataset(data,30)['errors']))
    def test_reject_pickle_and_nan_fps(self):
        file=self.root/'unsafe.npy';np.save(file,np.array([object()],dtype=object))
        with self.assertRaises(ValueError):worker.npy_header(file)
    def test_bundle_no_gpu(self):
        data=service.bundle({'dataset':'sample','model':'diffusion'})
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(set(z.namelist()),{'worker.py','plan.json','README.txt'})
            self.assertEqual(json.loads(z.read('plan.json'))['host'],'')
            self.assertIn(worker.COMMIT.encode(),z.read('worker.py'))
    def test_start_requires_fresh_matching_check(self):
        svc=service.TrainingService(self.root/'state')
        with self.assertRaises(ValueError):svc.start(self.plan)
        svc.checks[worker.fingerprint(self.plan)]={'ready':True,'time':time.time()-601}
        with self.assertRaises(ValueError):svc.start(self.plan)
        svc.checks[worker.fingerprint(self.plan)]={'ready':True,'time':time.time()}
        with self.assertRaises(ValueError):svc.start(self.plan|{'epochs':6})
    def test_restart_preserves_unknown(self):
        path=self.root/'state';path.mkdir();(path/'job-test.json').write_text(json.dumps({'id':'job-test','status':'running'}))
        svc=service.TrainingService(path);self.assertEqual(svc.snapshot()['jobs'][0]['status'],'unknown')
    def run_contract(self,model='diffusion',fail=None):
        self.dataset();plan=self.plan|{'model':model};runner=worker.Runner(plan,'job-test');runner.repo=ROOT/'repos/Audio2Face-3D-Training-Framework'
        events=[];calls=[]
        def docker(stage,script,args):
            calls.append(stage)
            if stage==fail:raise RuntimeError('injected subprocess failure')
            if stage=='preprocess':
                staged=runner.jobdir/'dataset/cache/skin';names=sorted(p.name for p in staged.iterdir())
                split=json.loads((runner.jobdir/'split.json').read_text());self.assertEqual(names,split['train']);self.assertFalse(set(names)&set(split['validation']))
                for n in names:self.assertTrue((staged/n/f'{n}.npy').is_symlink())
                p=runner.jobdir/'output_preproc/run/deploy';p.mkdir(parents=True)
                clips=[('testactor',n,(0,89),'testactor','en',n+'.wav',0) for n in names]
                (p/'clips_template.py').write_text('CLIPS = '+repr(clips))
            elif stage=='train':
                self.assertTrue(all(c[4]=='zh' for c in args[0]['CLIPS']))
                p=runner.jobdir/'output_train/run';p.mkdir(parents=True);(p/'weights.pth').write_text('test-fixture')
            elif stage=='export':
                p=runner.jobdir/'output_deploy/run';p.mkdir(parents=True);(p/'network.onnx').write_text('test-fixture')
            else:
                p=runner.jobdir/'output_inference/run';p.mkdir(parents=True);np.save(p/'skin.npy',np.zeros((90,16,3),dtype=np.float32))
        original_signal=signal.getsignal(signal.SIGTERM)
        try:
            with patch.object(worker,'inspect',return_value={'ready':True}),patch.object(worker,'capture',return_value=(0,worker.COMMIT)),patch.object(runner,'docker',side_effect=docker),patch.object(worker,'emit',side_effect=lambda **e:events.append(e)):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'injected'):runner.run()
                else:runner.run()
        finally:signal.signal(signal.SIGTERM,original_signal)
        self.assertFalse((runner.jobdir/'pid').exists())
        return runner,events,calls
    def test_diffusion_contract(self):
        runner,events,calls=self.run_contract();self.assertEqual(calls,['preprocess','train','export','inference']);self.assertEqual(events[-1]['status'],'succeeded')
        config=json.loads((runner.jobdir/'effective-config.json').read_text());self.assertTrue(config['inference']['OUTPUT_NPY_FILE'])
    def test_regression_does_not_call_unimplemented_inference(self):
        runner,events,calls=self.run_contract('regression');self.assertNotIn('inference',calls);self.assertTrue(any(e.get('status')=='skipped' for e in events));self.assertEqual(events[-1]['status'],'succeeded')
        self.assertIn('source_shot',json.loads((runner.jobdir/'effective-config.json').read_text())['inference']['CONFIG'])
    def test_failure_stops_before_export(self):
        runner,events,calls=self.run_contract(fail='train');self.assertEqual(calls,['preprocess','train']);self.assertEqual(events[-1]['status'],'failed');self.assertFalse((runner.jobdir/'result.json').exists())
    def test_command_nonzero_raises(self):
        runner=worker.Runner(self.plan,'job-command')
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):runner.command([sys.executable,'-c','raise SystemExit(17)'])
    def test_cancel_before_start(self):
        p=worker.validate(self.plan);result=worker.cancel(p,'job-not-started');self.assertTrue(result['stopped'])
        events=[]
        with patch.object(worker,'emit',side_effect=lambda **e:events.append(e)):worker.Runner(p,'job-not-started').run()
        self.assertEqual(events[-1]['status'],'cancelled')
    def test_official_schema_keys(self):
        # Check generated overrides against actual pinned base configs, without importing CUDA dependencies.
        repo=ROOT/'repos/Audio2Face-3D-Training-Framework'
        for model in ['diffusion','regression']:
            for k in ['train','dataset','preproc','inference']:
                config={key for key in runpy.run_path(str(repo/f'configs/example-{model}-min/config_{k}.py')) if not key.startswith('_')}
                name=f'config_{k}_{model}_base.py' if k in ['train','inference'] else f'config_{k}_base.py'
                base=runpy.run_path(str(repo/'audio2face/config_base'/name))
                self.assertFalse(config-set(base),config-set(base))

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='a2f-api-');cls.original=serve_preview.SERVICE
        serve_preview.SERVICE=service.TrainingService(cls.temp.name)
        cls.server=serve_preview.ThreadingHTTPServer(('127.0.0.1',0),serve_preview.Handler)
        cls.port=cls.server.server_address[1];cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();serve_preview.SERVICE=cls.original;cls.temp.cleanup()
    def req(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);c.request(method,path,body=body,headers=headers or {});r=c.getresponse();result=(r.status,r.read());c.close();return result
    def test_no_gpu_no_fake_jobs(self):
        status,data=self.req('/api/training/status');self.assertEqual(status,200);self.assertEqual(json.loads(data)['jobs'],[])
        status,data=self.req('/api/training/data');self.assertEqual(status,200);self.assertFalse(json.loads(data)['trainable'])
    def test_reject_cross_origin_and_wrong_host(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'}]:
            self.assertEqual(self.req('/api/training/status',headers=headers)[0],403)
        self.assertEqual(self.req('/api/training/start','POST','{}',{'Content-Type':'application/json'})[0],403)
    def test_start_blocked_and_bundle_available(self):
        payload=json.dumps({'plan':{'dataset':'sample','model':'diffusion'}});headers={'Content-Type':'application/json','X-A2F-Workbench':'1'}
        self.assertEqual(self.req('/api/training/start','POST',payload,headers)[0],400)
        status,data=self.req('/api/training/bundle','POST',payload,headers);self.assertEqual(status,200);self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
    def test_no_private_files_and_range_preserved(self):
        self.assertEqual(self.req('/training-runs/job-test.json')[0],404)
        self.assertEqual(self.req('/viewer/../../training_service.py')[0],404)
        self.assertEqual(self.req('/viewer/training/')[0],200)
        status,data=self.req('/demo-data/emotions-56s/audio.wav',headers={'Range':'bytes=0-9'});self.assertEqual(status,206);self.assertEqual(len(data),10)

if __name__=='__main__':unittest.main(verbosity=2)
