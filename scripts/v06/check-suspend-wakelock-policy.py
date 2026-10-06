#!/usr/bin/env python3
"""Characterize suspend behavior without changing device power state."""
from __future__ import annotations
import time
from common import PASS, FAIL, emit

supported = hasattr(time, "CLOCK_BOOTTIME")
raise SystemExit(emit(
    "suspend-wakelock-policy",
    PASS if supported else FAIL,
    clock_source="boottime",
    boottime_supported=supported,
    keep_awake_policy="do not require a wake lock for correctness",
    resume_behavior="an aged state observation is invalid and must be observed again",
    availability_note="a bounded keep-screen-awake optimization may be added only if later measurements justify it",
))
