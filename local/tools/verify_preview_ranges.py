"""Exercise actual HTTP range responses needed by browser audio seeking."""
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util, json, threading, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('preview', ROOT / 'serve_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
class QuietHandler(preview.Handler):
    def log_message(self, *args): pass

server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
file = ROOT/'demo-data/emotions-56s/audio.wav';data = file.read_bytes();checks=[]
def request(path, headers=None, method='GET'):
    connection=HTTPConnection('127.0.0.1',server.server_port)
    connection.request(method,path,headers=headers or {})
    response=connection.getresponse();body=response.read();result=(response.status,dict(response.getheaders()),body)
    connection.close();return result
try:
    path='/demo-data/emotions-56s/audio.wav'
    for value,start,end in [('bytes=0-43',0,43),('bytes=1000-2023',1000,2023),('bytes=-32',len(data)-32,len(data)-1),('bytes=1000-',1000,len(data)-1)]:
        status,headers,body=request(path,{'Range':value})
        assert status==206 and body==data[start:end+1]
        assert headers['Content-Range']==f'bytes {start}-{end}/{len(data)}'
        checks.append(value)
    for value in [f'bytes={len(data)}-','bytes=200-100','bytes=-0','bytes=-','not-a-range']:
        status,headers,body=request(path,{'Range':value});assert status==416 and not body
        assert headers['Content-Range']==f'bytes */{len(data)}'
        checks.append('reject '+value)
    status,headers,body=request(path,{'Range':'bytes=10-19'},'HEAD')
    assert status==206 and headers['Content-Length']=='10' and not body;checks.append('HEAD range')
    status,headers,body=request(path,{'Range':'bytes=0-1','If-Range':'old-version'})
    assert status==200 and body==data;checks.append('If-Range fallback')
    assert request('/serve_preview.py',{'Range':'bytes=0-10'})[0]==404;checks.append('private files remain blocked')
finally:
    server.shutdown();server.server_close();thread.join()
report={'status':'PASS','checks':checks}
(ROOT/'verification-preview-ranges.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
