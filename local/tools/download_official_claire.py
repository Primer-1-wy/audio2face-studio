"""Download the public NVIDIA Claire lookdev scene and every non-thumbnail dependency."""
from pathlib import Path
import concurrent.futures, hashlib, json, time, urllib.request, xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'assets/claire-official'
BASE = 'https://omniverse-content-production.s3.us-west-2.amazonaws.com/'
PREFIX = 'Samples/Examples/2023_1/Rendering/Claire/'
NS = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}

def fetch(item):
    name, size = item
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size != size:
        tmp = path.with_suffix(path.suffix + '.partial')
        for attempt in range(4):
            try:
                with urllib.request.urlopen(BASE + PREFIX + name, timeout=120) as response, tmp.open('wb') as out:
                    while chunk := response.read(4 * 1024 * 1024): out.write(chunk)
                assert tmp.stat().st_size == size, name
                tmp.replace(path)
                break
            except Exception:
                if attempt == 3: raise
                time.sleep(2)
    digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    print(f'OK {size/1e6:.1f} MB {name}', flush=True)
    return {'path': name, 'bytes': size, 'sha256': digest, 'url': BASE + PREFIX + name}

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    xml = urllib.request.urlopen(BASE + '?list-type=2&prefix=' + PREFIX, timeout=60).read()
    (DEST / 'inventory.xml').write_bytes(xml)
    tree = ET.fromstring(xml)
    assert tree.find('s:IsTruncated', NS).text == 'false'
    items = [(e.find('s:Key', NS).text[len(PREFIX):], int(e.find('s:Size', NS).text)) for e in tree.findall('s:Contents', NS)]
    items = [(n, s) for n, s in items if s and '.thumb' not in n and not n.endswith('/')]
    # Download USD geometry first, while large texture dependencies continue.
    items.sort(key=lambda item: (not item[0].endswith(('.usd', '.usda')), item[0]))
    print(f'{len(items)} source files, {sum(s for n,s in items)/1e9:.3f} GB', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, items))
    (DEST / 'manifest.json').write_text(json.dumps({'source': BASE+PREFIX, 'files': records}, indent=2))
    print('COMPLETE', flush=True)

if __name__ == '__main__': main()
