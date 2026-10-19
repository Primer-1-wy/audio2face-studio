#!/usr/bin/env python3
"""Create reviewable upload files for the first GitHub web upload."""
from pathlib import Path
import gzip
import hashlib
import json
import tarfile
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
part_size=20*1024*1024
with tempfile.TemporaryFile() as archive_file:
    with gzip.GzipFile(fileobj=archive_file,mode='wb',mtime=0) as zipped:
        with tarfile.open(fileobj=zipped,mode='w|') as archive:
            for folder in ('data','geometry','textures','vendor'):
                for source in sorted((ROOT/'docs'/folder).rglob('*')):
                    if source.is_file():
                        info=archive.gettarinfo(str(source),arcname=str(source.relative_to(ROOT/'docs')))
                        info.mtime=0;info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o644
                        with source.open('rb') as file:archive.addfile(info,file)
    archive_file.seek(0);parts=[];digest=hashlib.sha256()
    while raw:=archive_file.read(part_size):
        name=f'site-assets-{len(parts):03}.part'
        (ROOT/name).write_bytes(raw);digest.update(raw)
        parts.append({'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    (ROOT/'site-bundle.json').write_text(json.dumps({'format':'tar-gzip-split-v1','sha256':digest.hexdigest(),'parts':parts},indent=2))

with zipfile.ZipFile(ROOT/'project-source.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    sources=[ROOT/name for name in ('README.md','THIRD_PARTY_NOTICES.md','package.json','.gitignore')]
    for folder in ('docs','local','tools'):
        sources.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and not any(x in {'data','geometry','textures','vendor','__pycache__'} for x in p.relative_to(ROOT).parts))
    for source in sorted(sources):
        assert source.stat().st_size<25*1024*1024
        archive.write(source,arcname=str(source.relative_to(ROOT)))
print(json.dumps({'parts':len(parts),'assetBytes':sum(p['bytes'] for p in parts),'sourceBytes':(ROOT/'project-source.zip').stat().st_size,'uploadFiles':['project-source.zip','site-bundle.json']+[p['name'] for p in parts]},indent=2))
