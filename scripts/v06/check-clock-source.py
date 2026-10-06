#!/usr/bin/env python3
"""Validate same-kernel BOOTTIME evidence between Debian chroot and Android host root view."""
from __future__ import annotations
import time
from pathlib import Path
from common import PASS, FAIL, emit

chroot_uptime = Path("/proc/uptime")
host_uptime = Path("/proc/1/root/proc/uptime")
clock_supported = hasattr(time, "CLOCK_BOOTTIME")
details = {"clock_boottime_supported": clock_supported}
ok = clock_supported and chroot_uptime.exists() and host_uptime.exists()
if ok:
    before = int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000)
    c = float(chroot_uptime.read_text().split()[0]) * 1000.0
    h = float(host_uptime.read_text().split()[0]) * 1000.0
    after = int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000)
    details.update({
        "chroot_uptime_ms": round(c, 3),
        "host_root_uptime_ms": round(h, 3),
        "clock_boottime_ms": before,
        "read_window_ms": after - before,
        "host_chroot_delta_ms": round(abs(c - h), 3),
    })
    ok = abs(c - h) <= 1000.0 and abs(before - c) <= 3000.0
raise SystemExit(emit("clock-source-equivalence", PASS if ok else FAIL, **details))
