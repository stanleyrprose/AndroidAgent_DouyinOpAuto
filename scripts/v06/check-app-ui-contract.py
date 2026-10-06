#!/usr/bin/env python3
"""Collect installed TikTok package/version evidence for the Rev3.6 app/UI contract."""
from __future__ import annotations
import re
import subprocess
from common import PASS, FAIL, emit, repo_root

package = "com.zhiliaoapp.musically"
root_exec = repo_root() / "bridge" / "root-exec.sh"
proc = subprocess.run(
    [str(root_exec), f"dumpsys package {package}"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=45,
)
text = proc.stdout
version_code = None
version_name = None
m = re.search(r"versionCode=(\d+)", text)
if m:
    version_code = int(m.group(1))
m = re.search(r"versionName=([^\s]+)", text)
if m:
    version_name = m.group(1)
signing_available = bool(re.search(r"(signing|signature|SigningInfo)", text, re.IGNORECASE))
ok = proc.returncode == 0 and version_code is not None
raise SystemExit(emit("app-ui-contract-evidence", PASS if ok else FAIL,
    package=package,
    installed_version_code=version_code,
    installed_version_name=version_name,
    signing_identity_evidence_available=signing_available,
    signing_cert_sha256=None,
    note="certificate digest is optional when the platform dump does not expose a stable digest; runtime exact version remains mandatory"))
