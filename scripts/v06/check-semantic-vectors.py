#!/usr/bin/env python3
"""Public fixed-vector regression check for Rev3.6 semantic-v1."""
import hashlib
import json
from pathlib import Path
from common import PASS, FAIL, emit

fixture_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
rows = []
for name in ("v06-semantic-vector1-public.json", "v06-semantic-vector2-public.json"):
    fixture = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
    canonical = fixture["canonical_json"].encode("utf-8")
    actual = hashlib.sha256(canonical).hexdigest()
    rows.append({
        "vector": fixture["vector"],
        "expected_sha256": fixture["expected_sha256"],
        "actual_sha256": actual,
        "match": actual == fixture["expected_sha256"],
    })

raise SystemExit(emit("semantic-v1-fixed-vectors", PASS if all(r["match"] for r in rows) else FAIL, vectors=rows))
