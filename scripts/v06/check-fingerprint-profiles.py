#!/usr/bin/env python3
"""Reference checks for watched-field omission/null/empty semantics."""
import copy
import json
from pathlib import Path
from common import PASS, FAIL, emit

fixture = json.loads(((Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "v06-semantic-vector2-public.json").read_text(encoding="utf-8")))
base = json.loads(fixture["canonical_json"])
noisy = copy.deepcopy(base)
noisy["element"]["text"] = "dynamic"
noisy["element"]["content_desc"] = "dynamic-desc"

def profile(snapshot, watched):
    out = copy.deepcopy(snapshot)
    for key in ("text", "content_desc"):
        if key not in watched:
            out.get("element", {}).pop(key, None)
        elif key not in out.get("element", {}):
            raise ValueError("watched field unavailable: " + key)
    return out

unwatched_equal = profile(noisy, set()) == base
watched_a = profile(noisy, {"text", "content_desc"})
watched_b = copy.deepcopy(watched_a)
watched_b["element"]["text"] = "changed"
watched_changes = watched_a != watched_b
null_case = copy.deepcopy(noisy); null_case["element"]["text"] = None
empty_case = copy.deepcopy(noisy); empty_case["element"]["text"] = ""
null_value = profile(null_case, {"text"})["element"]["text"]
empty_value = profile(empty_case, {"text"})["element"]["text"]
blocked = False
try:
    profile(base, {"text"})
except ValueError:
    blocked = True
ok = unwatched_equal and watched_changes and null_value is None and empty_value == "" and null_value != empty_value and blocked
raise SystemExit(emit("fingerprint-profile-reference", PASS if ok else FAIL,
    unwatched_noise_immune=unwatched_equal,
    watched_change_detected=watched_changes,
    watched_null_explicit=(null_value is None),
    watched_empty_distinct_from_null=(empty_value == "" and null_value != empty_value),
    watched_unavailable_blocked=blocked))
