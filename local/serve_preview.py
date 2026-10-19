#!/usr/bin/env python3
"""Loopback viewer and training workbench; SSH jobs start only through its API."""
import argparse
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from training_service import SERVICE, bundle, current_data

ROOT = Path(__file__).resolve().parent

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def allowed_path(self):
        path = unquote(urlsplit(self.path).path)
        target = (ROOT / path.lstrip('/')).resolve()
        return any(target.is_relative_to(ROOT / folder) for folder in ('viewer', 'demo-data'))

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path.startswith('/api/training/'):
            if not self.api_allowed(): return
            if path == '/api/training/status': self.send_json(SERVICE.snapshot())
            elif path == '/api/training/data': self.send_json(current_data())
            else: self.send_json({'error':'接口不存在'},404)
            return
        if path == '/':
            self.send_response(302)
            self.send_header('Location', '/viewer/')
            self.end_headers()
            return
        if not self.allowed_path():
            self.send_error(404)
            return
        super().do_GET()

    def send_json(self, value, code=200):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(data)

    def api_allowed(self, write=False):
        port=self.server.server_address[1]
        hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        if host not in hosts or (origin and origin != 'http://'+host):
            self.send_json({'error':'只允许本机同源请求'},403);return False
        if write and (self.headers.get('X-A2F-Workbench')!='1' or self.headers.get_content_type()!='application/json'):
            self.send_json({'error':'需要工作台 JSON 请求'},403);return False
        return True

    def do_POST(self):
        if not self.path.startswith('/api/training/'):
            self.send_error(404);return
        if not self.api_allowed(write=True):return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:raise ValueError('请求大小无效')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('需要 JSON 对象')
            if self.path=='/api/training/inspect': result=SERVICE.inspect(payload.get('plan',{}))
            elif self.path=='/api/training/start': result=SERVICE.start(payload.get('plan',{}))
            elif self.path=='/api/training/cancel': result=SERVICE.cancel(payload.get('id',''))
            elif self.path=='/api/training/bundle':
                data=bundle(payload.get('plan',{}))
                self.send_response(200);self.send_header('Content-Type','application/zip')
                self.send_header('Content-Disposition','attachment; filename="a2f-training-kit.zip"')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            else:self.send_json({'error':'接口不存在'},404);return
            self.send_json(result)
        except (ValueError,TypeError,KeyError) as e:self.send_json({'error':str(e)},400)
        except Exception as e:self.log_error('Training API: %s',e);self.send_json({'error':'操作失败，请检查本地服务日志'},500)

    def do_HEAD(self):
        if not self.allowed_path():
            self.send_error(404)
            return
        super().do_HEAD()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        self.range_remaining = None
        request_range = self.headers.get('Range')
        path = Path(self.translate_path(self.path))
        if not request_range or not path.is_file():
            return super().send_head()
        source = path.open('rb')
        stat = path.stat()
        modified = self.date_time_string(stat.st_mtime)
        if self.headers.get('If-Range', modified) != modified:
            source.close()
            return super().send_head()
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', request_range.strip())
        start, end = 0, -1
        if match and any(match.groups()):
            first, last = match.groups()
            start = int(first) if first else max(0, stat.st_size - int(last))
            end = min(int(last), stat.st_size - 1) if first and last else stat.st_size - 1
        if not (0 <= start <= end < stat.st_size):
            source.close()
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{stat.st_size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Content-Range', f'bytes {start}-{end}/{stat.st_size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Last-Modified', modified)
        self.end_headers()
        source.seek(start)
        self.range_remaining = end - start + 1
        return source

    def copyfile(self, source, outputfile):
        if self.range_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self.range_remaining
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    print(f'Open http://127.0.0.1:{args.port}/viewer/  (Ctrl+C to stop)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
