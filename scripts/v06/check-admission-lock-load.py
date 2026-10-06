#!/usr/bin/env python3
"""Phase-0 admission critical-section benchmark: fsync pressure + concurrent callers."""
from __future__ import annotations

import fcntl
import json
import os
import statistics
import tempfile
import threading
import time
from pathlib import Path

from common import PASS, FAIL, emit

ITERATIONS = max(20, int(os.environ.get("V06_BENCH_ITERATIONS", "60")))
WORKERS = max(2, int(os.environ.get("V06_BENCH_WORKERS", "4")))
PAYLOAD_BYTES = max(4096, int(os.environ.get("V06_BENCH_PAYLOAD_BYTES", "65536")))

def percentile(values, p):
    ordered = sorted(values)
    idx = min(len(ordered)-1, max(0, int(round((len(ordered)-1)*p))))
    return ordered[idx]

def fsync_dir(path: Path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def run_once(root: Path, lock_path: Path, sequence: int, payload: str):
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    started = time.clock_gettime(time.CLOCK_MONOTONIC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        acquired = time.clock_gettime(time.CLOCK_MONOTONIC)
        tmp = root / f"binding-{sequence}.tmp"
        final = root / f"binding-{sequence}.json"
        body = {"submission": sequence, "request": payload}
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(body, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
        fsync_dir(root)
        released = time.clock_gettime(time.CLOCK_MONOTONIC)
        return (acquired-started)*1000.0, (released-acquired)*1000.0, (released-started)*1000.0
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

wait_samples=[]; hold_samples=[]; total_samples=[]
payload="x"*PAYLOAD_BYTES
with tempfile.TemporaryDirectory(prefix="y700-v06-admission-") as td:
    root=Path(td)
    lock=root/"admission.lock"
    for i in range(ITERATIONS):
        wait, hold, total = run_once(root, lock, i, payload)
        wait_samples.append(wait); hold_samples.append(hold); total_samples.append(total)

    gate=threading.Barrier(WORKERS)
    errors=[]
    seq=[ITERATIONS]
    seq_lock=threading.Lock()
    def worker():
        try:
            gate.wait()
            for _ in range(max(5, ITERATIONS//WORKERS)):
                with seq_lock:
                    n=seq[0]; seq[0]+=1
                wait, hold, total=run_once(root,lock,n,payload)
                wait_samples.append(wait); hold_samples.append(hold); total_samples.append(total)
        except Exception as exc:
            errors.append(type(exc).__name__+":"+str(exc))
    threads=[threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads: t.start()
    for t in threads: t.join()

p99_hold=percentile(hold_samples,0.99)
candidate=next((v for v in (5000,10000,15000) if p99_hold < v*0.5),None)
ok=not errors and candidate is not None
raise SystemExit(emit(
    "admission-lock-synthetic-baseline",
    PASS if ok else FAIL,
    serial_iterations=ITERATIONS,
    concurrent_workers=WORKERS,
    payload_bytes=PAYLOAD_BYTES,
    sample_count=len(hold_samples),
    wait_p95_ms=round(percentile(wait_samples,0.95),3),
    wait_p99_ms=round(percentile(wait_samples,0.99),3),
    hold_p50_ms=round(percentile(hold_samples,0.50),3),
    hold_p95_ms=round(percentile(hold_samples,0.95),3),
    hold_p99_ms=round(p99_hold,3),
    hold_max_ms=round(max(hold_samples),3),
    total_p99_ms=round(percentile(total_samples,0.99),3),
    initial_timeout_candidate_ms=candidate,
    errors=errors,
))
