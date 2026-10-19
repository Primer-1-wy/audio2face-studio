#!/usr/bin/env python3
"""Verify the bundled public assets and reconstruct docs/ for Pages or localhost."""
from pathlib import Path
import hashlib
import json
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
meta=json.loads((ROOT/'site-bundle.json').read_text())
with tempfile.TemporaryFile() as bundle:
    digest=hashlib.sha256()
    for item in meta['parts']:
        path=ROOT/item['name']
        if path.parent!=ROOT:raise ValueError('Invalid part path')
        raw=path.read_bytes()
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Bundle hash mismatch: '+item['name'])
        bundle.write(raw);digest.update(raw)
    if digest.hexdigest()!=meta['sha256']:raise ValueError('Bundle checksum mismatch')
    bundle.seek(0)
    with tarfile.open(fileobj=bundle,mode='r:gz') as archive:
        for item in archive:
            target=(ROOT/'docs'/item.name).resolve()
            if not target.is_relative_to((ROOT/'docs').resolve()) or not item.isfile():
                raise ValueError('Invalid asset member: '+item.name)
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(item) as src,target.open('wb') as out:
                while block:=src.read(1024*1024):out.write(block)
print('Assets verified and unpacked into docs/')
