from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .common import run


class DouzyError(RuntimeError):
    pass


def _process_rows() -> list[tuple[int, str]]:
    p = run(["ps", "-axo", "pid=,command="])
    rows = []
    for line in p.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)$", line)
        if not m:
            continue
        cmd = m.group(2)
        if "douyin-dl-sidecar" in cmd and "--serve" in cmd:
            rows.append((int(m.group(1)), cmd))
    return rows


def ensure_running(timeout: int = 15) -> int:
    rows = _process_rows()
    if rows:
        return rows[0][0]
    run(["open", "-a", "Douzy"], check=False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        rows = _process_rows()
        if rows:
            return rows[0][0]
    raise DouzyError("Douzy sidecar did not start")


def _environment(pid: int) -> dict[str, str]:
    p = run(["ps", "eww", "-p", str(pid), "-o", "command="])
    env: dict[str, str] = {}
    for token in p.stdout.split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        if k.startswith("DOUYIN_"):
            env[k] = v
    return env


def _listen_port(pid: int) -> int:
    # Douzy starts the sidecar with --serve-port 0. On current Electron builds
    # the loopback listener may be attributed to the parent Douzy process in
    # lsof, so do not bind discovery to the sidecar PID.
    p = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], check=False)
    ports: list[int] = []
    for line in p.stdout.splitlines():
        m = re.search(r"127\.0\.0\.1:(\d+)\s+\(LISTEN\)", line)
        if m:
            port = int(m.group(1))
            if port not in ports:
                ports.append(port)
    for port in ports:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=1.5) as resp:
                if resp.status != 200:
                    continue
                spec = json.load(resp)
                if "/api/v1/download" in spec.get("paths", {}):
                    return port
        except Exception:
            continue
    raise DouzyError("Douzy sidecar API port not found")


class Client:
    def __init__(self):
        pid = ensure_running()
        env = _environment(pid)
        token = env.get("DOUYIN_SIDECAR_TOKEN")
        if not token:
            raise DouzyError("DOUYIN_SIDECAR_TOKEN unavailable")
        self._token = token
        self.port = _listen_port(pid)
        self.base = f"http://127.0.0.1:{self.port}"

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise DouzyError(f"Douzy HTTP {e.code}: {body[:500]}") from e

    def cookie_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/cookies/status")

    def download(self, url: str, output_dir: Path, *, timeout: int = 240) -> dict[str, Any]:
        status = self.cookie_status()
        if not status.get("logged_in") or not status.get("has_session"):
            raise DouzyError("BLOCKED_LOGIN: open Douzy and complete Douyin login")
        job = self._request("POST", "/api/v1/download", {
            "url": url,
            "output_dir": str(output_dir),
            "video": True,
            "cover": False,
            "music": False,
            "video_quality": "highest",
        })
        jid = job["job_id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(2)
            cur = self._request("GET", f"/api/v1/jobs/{jid}")
            state = str(cur.get("status", "")).lower()
            if state in {"done", "success"}:
                return cur
            if state in {"failed", "cancelled"}:
                raise DouzyError(f"Douzy download {state}: {cur.get('error') or cur.get('failure_reason_summary')}")
        raise DouzyError(f"Douzy download timed out: {jid}")
