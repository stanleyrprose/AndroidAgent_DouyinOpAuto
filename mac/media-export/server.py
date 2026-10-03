#!/usr/bin/env python3
import argparse
import hmac
import json
import mimetypes
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

SAFE=re.compile(r"^[A-Za-z0-9._-]+$")

class Handler(BaseHTTPRequestHandler):
    server_version="Y700Media/0.3"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {self.command} {self.path.rsplit('/',1)[-1]}")

    def _resolve(self):
        parts=[unquote(p) for p in urlparse(self.path).path.split("/") if p]
        if len(parts)!=4 or parts[0]!="cap":
            return None
        _,token,job_id,name=parts
        if not SAFE.fullmatch(job_id) or not SAFE.fullmatch(name):
            return None
        job=self.server.root/job_id
        cap=job/".capability"
        target=job/name
        if not cap.is_file() or not target.is_file():
            return None
        try:
            data=json.loads(cap.read_text(encoding="utf-8"))
            expected=str(data["token"])
            expires_at=int(data["expires_at"])
        except Exception:
            return None
        if int(time.time()) > expires_at:
            return None
        if not hmac.compare_digest(token,expected):
            return None
        return target

    def _send(self, head=False):
        target=self._resolve()
        if target is None:
            self.send_error(404)
            return
        size=target.stat().st_size
        ctype=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(size))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        if not head:
            with open(target,"rb") as f:
                while True:
                    chunk=f.read(1024*1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    def do_GET(self):
        self._send(False)

    def do_HEAD(self):
        self._send(True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="exports")
    ap.add_argument("--host",default="127.0.0.1")
    ap.add_argument("--port",type=int,default=8790)
    args=ap.parse_args()
    root=Path(args.root).resolve()
    root.mkdir(parents=True,exist_ok=True)
    httpd=ThreadingHTTPServer((args.host,args.port),Handler)
    httpd.root=root
    print(f"Y700 media server listening on {args.host}:{args.port} root={root}",flush=True)
    httpd.serve_forever()

if __name__=="__main__":
    main()
