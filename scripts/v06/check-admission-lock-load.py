#!/usr/bin/env python3
"""Synthetic Phase-0 flock/fsync critical-section benchmark."""
from __future__ import annotations
import fcntl
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from common import PASS, FAIL, emit

iterations = max(20, int(os.environ.get("V06_BENCH_ITERATIONS", "60")))
samples = []
with tempfile.TemporaryDirectory(prefix="y700-v06-admission-") as td:
    root = Path(td)
    lock_path = root / "admission.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        for i in range(iterations):
            started = time.clock_gettime(time.CLOCK_MONOTONIC)
            fcntl.flock(fd, fcntl.LOCK_EX)
            tmp = root / f"binding-{i}.tmp"
            final = root / f"binding-{i}.json"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"submission": i, "request": "synthetic"}, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, final)
            dfd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
            fcntl.flock(fd, fcntl.LOCK_UN)
            samples.append((time.clock_gettime(time.CLOCK_MONOTONIC) - started) * 1000.0)
    finally:
        os.close(fd)

ordered = sorted(samples)
def percentile(p):
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]

p50 = percentile(0.50)
p95 = percentile(0.95)
p99 = percentile(0.99)
candidate = next((v for v in (5000, 10000, 15000) if p99 < v * 0.5), None)
raise SystemExit(emit("admission-lock-synthetic-baseline", PASS if candidate else FAIL,
    iterations=iterations, p50_ms=round(p50, 3), p95_ms=round(p95, 3),
    p99_ms=round(p99, 3), max_ms=round(max(samples), 3),
    initial_timeout_candidate_ms=candidate))
