"""Rev3.7 source-owned, foreground read-only capability probe issuer.

The existing Bridge 'androidctl status/screen-state/keyguard-state' is the
only Android probe transport. No touch, wake, unlock, app launch, UI dump
or arbitrary shell command is used. The physical TikTok signature/overlay
contract needs a SEPARATE accepted native receipt: package existence alone
cannot establish App UI compatibility.

A probe candidate is NOT trusted authority; publication and consumption
have independent acceptance switches, both FALSE in development.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from automation.authoritative_state_reader import observe_authoritative_state
from automation.capability_catalog import load_catalog
from automation.capability_job_store import _atomic_new, _atomic_replace, _read_json, _root_dir
from automation.runtime_evidence_producer import CAPABILITY_PROBE_ROOT
from automation.trusted_ingress_approval import _root_owned_record

ANDROIDCTL = Path("/opt/y700/workspaces/y700-agent/bridge/androidctl.sh")
_NATIVE_APP_SOURCE = Path("/opt/y700/runtime/native-app-contract/accepted.json")
_NATIVE_PROBE_ROOT = Path("/opt/y700/runtime/native-capability-checks")
_PROBE_ISSUANCE_ACCEPTED = False
_NATIVE_PROBE_SOURCE_ACCEPTED = False
_ALLOWED_PROBES = {
    "android.device.observe": "android_device_observe_probe_v1",
    "android.ui.workflow": "android_ui_workflow_probe_v1",
    "android.root.exec": "android_root_exec_probe_v1",
    "tiktok.publish": "tiktok_publish_probe_v1",
}


class CapabilityProbeUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(value: bool, code: str) -> None:
    if not value:
        raise CapabilityProbeUnavailable(code)


def _read_bridge(verb: str) -> str:
    _need(verb in {"status", "screen-state", "keyguard-state"},
          "CAPABILITY_PROBE_VERB_UNAUTHORIZED")
    _need(ANDROIDCTL.is_file() and not ANDROIDCTL.is_symlink(),
          "CAPABILITY_BRIDGE_UNAVAILABLE")
    try:
        result = subprocess.run(
            [str(ANDROIDCTL), verb],
            capture_output=True, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CapabilityProbeUnavailable(
            "CAPABILITY_BRIDGE_PROBE_UNAVAILABLE") from exc
    _need(result.returncode == 0
          and 0 < len(result.stdout) <= 8192,
          "CAPABILITY_BRIDGE_PROBE_FAILED")
    return result.stdout


def _read_fixed_device_facts() -> dict[str, Any]:
    raw = _read_bridge("status")
    values = [line.strip() for line in raw.splitlines() if line.strip()]
    # androidctl status prints 'id' followed by fixed three getprop calls.
    # Never infer readiness from a half-parsed or multi-record response.
    _need(len(values) == 4
          and values[0].startswith("uid=0(")
          and len(values[1]) <= 128
          and len(values[2]) <= 64
          and values[3] == "1",
          "CAPABILITY_DEVICE_FACTS_INCOMPLETE")
    # Package/version identity cannot be inferred from this host output.
    return {
        "model": values[1],
        "android_version": values[2],
        "boot_completed": True,
    }


def build_probe_candidate_readonly(capability: str) -> dict[str, Any]:
    """Observe boot/readiness, but do not publish an accepted probe."""
    _need(capability in _ALLOWED_PROBES, "CAPABILITY_PROBE_UNKNOWN")
    catalog = load_catalog()
    entry = catalog.get(capability)
    _need(isinstance(entry, dict), "CAPABILITY_CATALOG_ENTRY_MISSING")
    first = observe_authoritative_state()
    device = _read_fixed_device_facts()
    screen = _read_bridge("screen-state")
    lock = _read_bridge("keyguard-state")
    final = observe_authoritative_state()
    _need(first.boot_id == final.boot_id
          and first.state_epoch == final.state_epoch
          and first.revision == final.revision,
          "CAPABILITY_PROBE_STATE_DRIFT")
    _need(device["android_version"] == "16"
          and device["boot_completed"] is True,
          "CAPABILITY_DEVICE_CONTRACT_UNVERIFIED")
    # UI readiness needs foreground/signature/native modal checks, not
    # merely an interactive screen and a nonlocked display.
    display_interactive = "mWakefulness=Awake" in screen
    keyguard_unknown = ("KeyguardStateMonitor" not in lock)
    requirements = entry.get("execution_profile", {}).get(
        "readiness_requirements", [])
    _need(isinstance(requirements, list)
          and all(isinstance(s, str) for s in requirements),
          "CAPABILITY_READINESS_SCHEMA_INVALID")
    readiness = {item: False for item in requirements}
    # No positive dependency until that specific independent physical
    # contract has been accepted; a negative candidate is still useful.
    probe = {
        "runtime_probe_version": 1,
        "source": "Y700_TRUSTED_DEVICE_BRIDGE_PROBE",
        "capability": capability,
        "probe_id": _ALLOWED_PROBES[capability],
        "boot_id": final.boot_id,
        "state_epoch": final.state_epoch,
        "revision": final.revision,
        "observed_boottime_ms": final.observed_boottime_ms,
        "device_contract": "y700-android16-zui",
        "readiness_requirements": readiness,
        "adapter_present": False,
        "runtime_compatible": False,
        "runtime_available": False,
        "runtime_degraded": True,
        "display_interactive_positive": display_interactive,
        "keyguard_observation_complete": not keyguard_unknown,
        "probe_candidate_only": True,
        "execution_authorized": False,
    }
    if capability == "tiktok.publish":
        # Do not fabricate versionCode/cert or 'ACCEPTED' from installed
        # package name. A separately accepted native source is required.
        probe.update(
            app_ui_contract_match=False,
            app_version_code=None,
            app_signing_cert_sha256=None,
            app_ui_contract_version=None,
        )
    return probe


def publish_accepted_probe(capability: str) -> dict[str, Any]:
    """One trusted positive observation, tied to a native/Bridge receipt.

    This producer CANNOT accept a CLI-provided 'ready' flag or a guessed
    App version. A real accepted versioned native sensor must furnish
    all positive readiness facts and exact installed App identity first.
    """
    if not _PROBE_ISSUANCE_ACCEPTED or not _NATIVE_PROBE_SOURCE_ACCEPTED:
        raise CapabilityProbeUnavailable("CAPABILITY_PROBE_ISSUER_CLOSED")
    _need(capability in _ALLOWED_PROBES, "CAPABILITY_PROBE_UNKNOWN")
    catalogue = load_catalog()
    entry = catalogue[capability]
    start = observe_authoritative_state()
    physical = _read_fixed_device_facts()
    _need(physical["android_version"] == "16"
          and physical["boot_completed"] is True,
          "CAPABILITY_DEVICE_CONTRACT_UNVERIFIED")
    probe_id = _ALLOWED_PROBES[capability]
    accepted = _root_owned_record(_NATIVE_PROBE_ROOT / (probe_id + ".json"))
    end = observe_authoritative_state()
    elapsed = accepted.get("observed_boottime_ms")
    _need(start.boot_id == end.boot_id
          and start.state_epoch == end.state_epoch
          and start.revision == end.revision
          and accepted.get("native_probe_version") == 1
          and accepted.get("source") == "Y700_ACCEPTED_NATIVE_BRIDGE_SENSOR"
          and accepted.get("capability") == capability
          and accepted.get("probe_id") == probe_id
          and accepted.get("boot_id") == end.boot_id
          and accepted.get("state_epoch") == end.state_epoch
          and accepted.get("revision") == end.revision
          and type(elapsed) is int
          and 0 <= end.observed_boottime_ms - elapsed <= 1000
          and accepted.get("device_contract") == "y700-android16-zui",
          "CAPABILITY_NATIVE_SENSOR_STALE")
    required = entry["execution_profile"]["readiness_requirements"]
    checks = accepted.get("readiness_requirements")
    _need(isinstance(checks, dict)
          and set(checks) == set(required)
          and all(type(checks[key]) is bool for key in required),
          "CAPABILITY_NATIVE_SENSOR_FACTS_INCOMPLETE")
    for key in ("adapter_present", "runtime_compatible",
                "runtime_available", "runtime_degraded"):
        _need(type(accepted.get(key)) is bool,
              "CAPABILITY_NATIVE_SENSOR_FACTS_INCOMPLETE")
    record = {
        "runtime_probe_version": 1,
        "source": "Y700_TRUSTED_DEVICE_BRIDGE_PROBE",
        "capability": capability,
        "probe_id": probe_id,
        "boot_id": end.boot_id,
        "state_epoch": end.state_epoch,
        "revision": end.revision,
        "observed_boottime_ms": end.observed_boottime_ms,
        "device_contract": "y700-android16-zui",
        "readiness_requirements": dict(checks),
        "adapter_present": accepted["adapter_present"],
        "runtime_compatible": accepted["runtime_compatible"],
        "runtime_available": accepted["runtime_available"],
        "runtime_degraded": accepted["runtime_degraded"],
    }
    if capability == "android.ui.workflow":
        # A generic installed Settings package is NOT enough. This
        # contract requires a separately accepted native Settings probe
        # (selector/foreground/modal/restore readiness).
        _need(accepted.get("app_ui_contract_match") is True,
              "SETTINGS_APP_UI_CONTRACT_NOT_ACCEPTED")
        record["app_ui_contract_match"] = True
    if capability == "tiktok.publish":
        ui = entry.get("app_ui_contract")
        _need(isinstance(ui, dict)
              and ui.get("acceptance_status") == "ACCEPTED"
              and type(accepted.get("app_version_code")) is int
              and accepted["app_version_code"]
                  in ui.get("accepted_version_codes", [])
              and accepted.get("app_signing_cert_sha256")
                  == ui.get("signing_cert_sha256")
              and accepted.get("app_ui_contract_version")
                  == ui.get("ui_contract_version"),
              "APP_UI_CONTRACT_NOT_ACCEPTED")
        record.update(
            app_version_code=accepted["app_version_code"],
            app_signing_cert_sha256=accepted["app_signing_cert_sha256"],
            app_ui_contract_version=accepted["app_ui_contract_version"],
            app_ui_contract_match=True,
        )
    _root_dir(CAPABILITY_PROBE_ROOT)
    target = CAPABILITY_PROBE_ROOT / (probe_id + ".json")
    if target.exists() or target.is_symlink():
        old = _read_json(target)
        _need(old.get("probe_id") == probe_id
              and old.get("capability") == capability,
              "CAPABILITY_PROBE_IDENTITY_CONFLICT")
        _atomic_replace(target, record)
    else:
        _atomic_new(target, record)
    return {
        "status": "TRUSTED_CAPABILITY_PROBE_WRITTEN",
        "capability": capability,
        "probe_id": probe_id,
        "ui_input_attempts": 0,
        "production_dispatch_authorized": False,
    }
