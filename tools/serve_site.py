#!/usr/bin/env python3
"""Serve the static gallery on loopback with audio/video byte-range support."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]/'docs'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)

    def list_directory(self,path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header('Accept-Ranges','bytes')
        super().end_headers()

    def send_head(self):
        self.remaining=None
        path=Path(self.translate_path(self.path)).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            self.send_error(404)
            return None
        header=self.headers.get('Range')
        if not header or not path.is_file():return super().send_head()
        size=path.stat().st_size
        m=re.fullmatch(r'bytes=(\d*)-(\d*)',header.strip())
        start,end=0,-1
        if m and any(m.groups()):
            first,last=m.groups()
            start=int(first) if first else max(0,size-int(last))
            end=min(int(last),size-1) if first and last else size-1
        if not 0<=start<=end<size:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
        stream=path.open('rb');stream.seek(start);self.remaining=end-start+1
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Content-Length',str(self.remaining));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.end_headers()
        return stream

    def copyfile(self,source,output):
        if self.remaining is None:return super().copyfile(source,output)
        while self.remaining:
            block=source.read(min(65536,self.remaining))
            if not block:break
            output.write(block);self.remaining-=len(block)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    print(f'Open http://127.0.0.1:{args.port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
