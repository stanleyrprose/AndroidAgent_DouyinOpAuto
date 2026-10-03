#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
mkdir -p runtime/bin runtime/jobs runtime/tmp
swiftc scripts/render_text.swift -o runtime/bin/render_text
echo "BOOTSTRAP_PASS"
.venv/bin/python - <<'PY'
from faster_whisper import WhisperModel
import ctranslate2
print("faster-whisper runtime:", ctranslate2.__version__)
PY
