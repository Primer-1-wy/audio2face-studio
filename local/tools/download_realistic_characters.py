"""Restore the three added characters from their recorded official sources."""
from pathlib import Path
import hashlib,json,urllib.request,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]
def fetch(record):
    path=ROOT/'assets'/record['path']
    assert path.resolve().is_relative_to((ROOT/'assets').resolve())
    if path.exists() and path.stat().st_size==record['bytes'] and hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==record['sha256']:return
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.partial')
    urllib.request.urlretrieve(record['url'],temporary)
    assert temporary.stat().st_size==record['bytes']
    assert hashlib.file_digest(temporary.open('rb'),'sha256').hexdigest()==record['sha256']
    temporary.replace(path);print('Restored',record['path'],flush=True)
if __name__=='__main__':
    records=[]
    for role in ['allison','james','mark']:records.extend(json.loads((ROOT/f'assets/{role}-official/manifest.json').read_text()))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,records))
    print('All source files verified:',len(records))
