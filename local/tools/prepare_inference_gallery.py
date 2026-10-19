#!/usr/bin/env python3
"""Import the five supplied v3 results. Uploaded scripts/HTML are never executed.

Preserve float32 predictions in overlapping, half-second browser chunks. Validate
the NPZ shape, timestamps, hashes and the exact official v3 mesh topology first.
"""
from pathlib import Path, PurePosixPath
import argparse
import csv
import hashlib
import json
import re
import shutil
import wave
import zipfile

import numpy as np
from scipy.spatial.transform import Rotation
from prepare_mesh import parse_mesh
from prepare_reference_characters import james_material_uv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo-data/v3-20s-01-05'
WEB = '/demo-data/v3-20s-01-05/'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False))


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def extract(archive):
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir() or len(parts) < 2:
                continue
            if '..' in parts or PurePosixPath(item.filename).is_absolute():
                raise ValueError('Unsafe archive path')
            relative = Path(*parts[1:])
            if relative.suffix.lower() not in {'.npz', '.json', '.csv', '.txt', '.wav', '.mp3', '.mp4', '.jpg', '.md'}:
                continue
            target = OUT / relative
            if target.exists() and target.stat().st_size == item.file_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)


def export_scene(model, topology):
    dest = OUT / 'web'
    dest.mkdir(exist_ok=True)
    def buf(name, value, dtype='<f4'):
        np.asarray(value, dtype=dtype).tofile(dest / name)
        return WEB + 'web/' + name
    source = ROOT / 'assets/james-official/claire_geom_v3_material_reference.ma'
    text = source.read_text()
    old = json.loads((ROOT / 'viewer/official-claire/scene.json').read_text())
    scene = {'parts': [], 'canonical': {}, 'mayaSha256': digest(source)}
    for kind in ('skin', 'tongue'):
        scene['canonical'][kind] = {
            'base': buf(kind + '.base.bin', model['neutral_' + kind]),
            'indices': buf(kind + '.indices.bin', topology[kind + '_triangles'], '<u4')}
    for block in re.split(r'(?=^createNode )', text, flags=re.M):
        node = re.match(r'createNode mesh -n "([^"]+)"', block)
        if not node:
            continue
        name = node[1].replace('Shape', '')
        kind = ('skin' if name == 'c_headWatertight_hi' else 'tongue' if name == 'c_tongue_hi'
                else 'dental' if 'Denture' in name else 'eye' if 'choroid' in name else None)
        if not kind:
            continue
        base, tri, _ = parse_mesh(block)
        if kind in ('skin', 'tongue'):
            assert np.array_equal(tri, topology[kind + '_triangles']), f'{kind}: mismatched topology'
            assert base.shape == model['neutral_' + kind].shape
            assert np.max(np.linalg.norm(base - model['neutral_' + kind], axis=1)) < .6
            base = model['neutral_' + kind]
        uv = []
        for m in re.finditer(r'setAttr(?: -s \d+)? "\.uvst\[0\]\.uvsp\[(\d+)(?::(\d+))?\]"(?: -type "float2")?\s*([^;]+);', block):
            assert int(m[1]) == len(uv)
            uv.extend(np.fromstring(m[3], sep=' ').reshape(-1, 2))
        uvtri = []
        for m in re.finditer(r'\bmu 0 (\d+) ([\d\s]+)', block, re.M):
            ids = np.fromstring(m[2], sep=' ', dtype=int)
            for i in range(1, len(ids)-1):
                uvtri.append([ids[0], ids[i], ids[i+1]])
        assert len(uvtri) == len(tri)
        coords = np.asarray(uv)[np.asarray(uvtri)]
        if kind == 'skin':
            coords = james_material_uv(tri, coords)
        tiles = np.floor(coords.mean(1)).astype(int)
        for xy in np.unique(tiles, axis=0):
            tile = 1001 + int(xy[0]) + 10 * int(xy[1])
            selected = np.all(tiles == xy, axis=1)
            vid, tex = tri[selected].flatten(), (coords[selected] - xy).reshape(-1, 2)
            _, first, inverse = np.unique(np.c_[vid, tex], axis=0, return_index=True, return_inverse=True)
            ids, tag = vid[first], f'{name}-{tile}'
            spec = {'name': tag, 'kind': kind, 'base': buf(tag + '.pos.bin', base[ids]),
                    'uv': buf(tag + '.uv.bin', tex[first]), 'indices': buf(tag + '.idx.bin', inverse, '<u4')}
            if kind in ('skin', 'tongue'):
                spec['sourceVertices'] = buf(tag + '.source.bin', ids, '<u4')
            if kind == 'eye':
                spec['eyeSide'] = 'right' if name.startswith('r_') else 'left'
                spec['eyePivot'] = ((base.min(0) + base.max(0))/2).tolist()
            spec['jawDriven'] = 'bottomDenture' in name
            match = next((p for p in old['parts'] if p['kind'] == kind and p.get('tile') == tile), None)
            if kind == 'eye':
                match = next(p for p in old['parts'] if p['kind'] == 'eye')
            if match:
                for key in ('map', 'normalMap', 'roughnessMap'):
                    if key in match:
                        spec[key] = '/viewer/' + match[key]
            scene['parts'].append(spec)
    scene['appearance'] = 'Claire materials adapted to the v3 UV layout; raw skin/tongue motion unchanged. Teeth use rigid jaw-anchor fit; eye pivots approximated from mesh bounds.'
    write_json(dest / 'scene.json', scene)
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    extract(args.archive)
    model = np.load(OUT / 'model_data_Claire.npz', allow_pickle=False)
    topology = np.load(OUT / 'topology.npz', allow_pickle=False)
    scene = export_scene(model, topology)
    source_manifest = json.loads((OUT / 'manifest.json').read_text())
    result = {'id': 'v3-20s-01-05', 'title': 'Claire · 情绪推理实验', 'scene': WEB+'web/scene.json',
              'repository': 'nvidia/Audio2Face-3D-v3.0', 'revision': source_manifest['model_revision'],
              'chunkFrames': 30, 'stride': 88831, 'demos': [], 'emotionSource': 'manually authored'}
    report = {'archive': args.archive.name, 'sceneTopologyMatched': True, 'mayaSha256': scene['mayaSha256'], 'demos': []}
    anchor = model['neutral_jaw'].astype('float64')
    center = anchor.mean(0)
    for item in source_manifest['demos']:
        folder = OUT / item['id']
        assert folder.parent == OUT and folder.is_dir()
        run = json.loads((folder / 'run.json').read_text())
        for filename, meta in run['files'].items():
            p = folder / filename
            assert p.parent == folder and p.stat().st_size == meta['bytes']
            assert digest(p) == meta['sha256'], f'Hash mismatch: {p}'
        with np.load(folder / 'motion.npz', allow_pickle=False) as data:
            pred = data['prediction']
            time = data['time_seconds']
            emotion = data['emotion']
            names = [n.decode() if isinstance(n, bytes) else str(n) for n in data['emotion_names']]
        assert pred.dtype == np.float32 and pred.shape == (1200, 88831)
        assert np.isfinite(pred).all() and np.isfinite(emotion).all()
        assert emotion.shape == (1200, 10) and len(names) == 10
        assert np.allclose(time, np.arange(1200)/60, atol=1e-5)
        chunks = folder / 'chunks'
        chunks.mkdir(exist_ok=True)
        chunk_urls = []
        for first in range(0, len(pred), 30):
            part = np.asarray(pred[first:first+31], dtype='<f4')
            path = chunks / f'{first//30:03}.bin'
            part.tofile(path)
            assert np.array_equal(np.fromfile(path, dtype='<f4').reshape(part.shape), part)
            chunk_urls.append(WEB+item['id']+'/chunks/'+path.name)
        target = anchor[None] + pred[:, 88812:88827].reshape(-1, 5, 3)
        target_center = target.mean(1)
        h = np.einsum('ki,fkj->fij', anchor-center, target-target_center[:, None])
        u, _, vt = np.linalg.svd(h)
        fix = np.tile(np.eye(3), (len(pred), 1, 1))
        fix[:, 2, 2] = np.linalg.det(u @ vt)
        rotation = (u @ fix @ vt).transpose(0, 2, 1)
        translation = target_center - np.einsum('fij,j->fi', rotation, center)
        jaw = np.c_[Rotation.from_matrix(rotation).as_quat(), translation].astype('<f4')
        jaw.tofile(folder / 'jaw.bin')
        residual = np.linalg.norm(np.einsum('fij,kj->fki', rotation, anchor) + translation[:, None] - target, axis=2)
        with (folder / 'frame_metrics.csv').open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(pred)
        metrics = {k: [float(r[k]) for r in rows] for k in ('skin_rms', 'tongue_rms', 'jaw0_dy')}
        # Cross-check reported metrics against the actual predictions.
        assert np.allclose(metrics['skin_rms'], np.sqrt((pred[:, :72006]**2).mean(1)), atol=1e-6)
        with wave.open(str(folder / 'audio.wav')) as wav:
            assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
            sr, samples = wav.getframerate(), wav.getnframes()
            audio = np.frombuffer(wav.readframes(samples), dtype='<i2').astype(float)/32768
        assert sr == 16000 and samples/sr == 20
        waveform = [float(np.abs(a).max()) for a in np.array_split(audio, 400)]
        details = {'emotionNames': names, 'emotion': emotion.tolist(), 'metrics': metrics, 'waveform': waveform,
                   'track': json.loads((folder/'emotion_track.json').read_text()),
                   'transcript': (folder/'transcript.txt').read_text(), 'run': run}
        write_json(folder / 'details.json', details)
        prefix = WEB + item['id'] + '/'
        result['demos'].append({
            'id': item['id'], 'title': item['title'], 'fps': 60, 'frameCount': 1200, 'duration': 20,
            'chunks': chunk_urls, 'jaw': prefix+'jaw.bin', 'details': prefix+'details.json',
            'audio': prefix+'audio.wav', 'video': prefix+'preview.mp4',
            'downloads': {key: prefix+name for key, name in {'motion':'motion.npz','metrics':'frame_metrics.csv','track':'emotion_track.json','run':'run.json'}.items()},
            'peakEmotions': {name: float(emotion[:,i].max()) for i,name in enumerate(names) if emotion[:,i].max() > 0}})
        report['demos'].append({'id': item['id'], 'frames': len(pred), 'hashesVerified': len(run['files']),
                                'float32ChunksExact': True, 'timestampsValidated': True,
                                'jawFitMaxErrorCm': float(residual.max()), 'audioSeconds': samples/sr})
        print('Prepared', item['id'], pred.shape, flush=True)
        del pred
    write_json(OUT/'web/manifest.json', result)
    write_json(OUT/'web/validation.json', report)
    print('Ready:', OUT/'web/manifest.json', flush=True)


if __name__ == '__main__':
    main()
