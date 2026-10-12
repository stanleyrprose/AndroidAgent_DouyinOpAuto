#!/usr/bin/env python3
"""Rev3.7 capctl development CLI — discover/observe only.

No invocation, rollback, maintenance or reconciler is exposed here until
all frozen PRD gates and final acceptance are completed. In particular,
CLI flags cannot activate BUSINESS or call root/Android.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from automation.capability_catalog import (
    CatalogUnavailable, load_catalog, public_definition,
)
from automation.capability_axes import inspect_capability_readonly
from automation.node_health_v2 import inspect_node_health_readonly
from automation.foreground_entrypoint import (
    ForegroundEntrypointUnavailable, foreground_invoke,
)
from automation.capability_cancellation import (
    request_cancel_from_trusted_source,
)
from automation.gc_maintenance import gc_preview, gc_apply
from automation.recovery_inventory import (
    inspect_active_exact_readonly, inspect_startup_inventory_readonly,
)
from automation.resource_reconcile_v37 import (
    ResourceRecoveryRefused, observe_trusted_exact_stop_proof,
    preview_reconcile_resource, reconcile_resource_exact,
    emergency_force_reset_after_acceptance,
)
from automation.admin_stop_adapter import terminate_exact_owner_best_effort
from automation.capability_reconcile_runtime import (
    inspect_exact_outcome_readonly, reconcile_exact_after_acceptance,
)
from automation.capability_job_store import (
    CapabilityStore, CapabilityStoreError,
)
from automation.runtime_authority import RuntimeEvidenceUnavailable
from automation.runtime_evidence_producer import EvidenceProductionUnavailable
from automation.trusted_ingress_approval import IngressAuthorizationUnavailable
from automation.admission_fence import AdmissionFenceUnavailable
from automation.release_lifecycle import (
    ReleaseUnavailable, inspect_release_restart_readonly,
)
from automation.release_integrity import ReleaseIntegrityUnavailable
from automation.resource_arbiter import ResourceError
from automation.publisher_boundary_guard import PublisherBoundaryError


def _print(result: dict[str, Any]) -> None:
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


def _not_active(name: str) -> dict[str, Any]:
    return {
        "command": name,
        "status": "BLOCKED",
        "reason_code": "REV37_FINAL_ACCEPTANCE_PENDING",
        "dg3_status": "OPEN",
        "business_activation": False,
        "action_attempts": 0,
        "backend_submitted": False,
    }


def _describe(name: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = catalog.get(name)
    if row is None:
        return {
            "status": "NOT_FOUND",
            "capability": name,
            "reason_code": "CAPABILITY_CATALOG_ENTRY_MISSING",
            "production_dispatch_authorized": False,
        }
    # A documented UNKNOWN is more accurate than pretending runtime probes
    # were performed by a Catalog listing.
    support = inspect_capability_readonly(
        name,
        runtime_facts={},
        trusted_policy_facts={},
        catalog_advertised=row.get("enabled") is True,
    )
    return {
        "status": "READ_ONLY",
        "definition": public_definition(row),
        "support": support.support.as_dict(),
        "permission": support.permission.as_dict(),
        "readiness": support.readiness.as_dict(),
        "diagnostics": list(support.diagnostics),
        "production_dispatch_authorized": False,
    }


_TRUSTED_REQUEST_ROOT = Path("/opt/y700/runtime/trusted-capability-requests")


def _trusted_request(path_string: str) -> dict[str, Any]:
    """Read caller DATA only from a protected first-party inbox.

    A CLI path never authenticates a principal; Foreground Gateway
    independently verifies the exact root-owned ingress authorization,
    policy/clock/boot and runtime facts before any job is admitted.
    """
    path = Path(path_string)
    if (not path.is_absolute()
            or path.parent != _TRUSTED_REQUEST_ROOT
            or not path.name.endswith(".json")
            or len(path.name) > 128):
        raise CapabilityStoreError("CAPABILITY_REQUEST_PATH_UNTRUSTED")
    try:
        parent = path.parent.lstat()
        child = path.lstat()
    except OSError as exc:
        raise CapabilityStoreError("CAPABILITY_REQUEST_UNAVAILABLE") from exc
    if not (
        stat.S_ISDIR(parent.st_mode)
        and parent.st_uid == 0
        and stat.S_IMODE(parent.st_mode) == 0o700
        and stat.S_ISREG(child.st_mode)
        and child.st_uid == 0
        and stat.S_IMODE(child.st_mode) == 0o600
    ):
        raise CapabilityStoreError("CAPABILITY_REQUEST_PATH_UNTRUSTED")
    from automation.capability_job_store import _read_json
    return _read_json(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capctl")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Git Catalog only (no live claims)")
    describe = commands.add_parser("describe", help="Read-only definition")
    describe.add_argument("capability")
    commands.add_parser("doctor", help="Safe unknown/disabled diagnostic")
    status = commands.add_parser("status", help="Read-only durable job status")
    status.add_argument("capability_job_id")
    invoke = commands.add_parser("invoke", help="Disabled until final acceptance")
    invoke.add_argument("capability")
    invoke.add_argument("--request", required=True)
    cancel = commands.add_parser("cancel", help="Disabled until final acceptance")
    cancel.add_argument("capability_job_id")
    cancel.add_argument("--reason", required=True)
    reconcile = commands.add_parser("reconcile", help="Disabled until final acceptance")
    reconcile.add_argument("capability_job_id")
    reconcile.add_argument("--dry-run", action="store_true",
                           help="Observe the exact original Backend without mutation")
    commands.add_parser("startup-status",
                        help="Read-only crash/recovery inventory")
    recover = commands.add_parser("reconcile-resource",
                                  help="Disabled until final acceptance")
    recover.add_argument("--claim-id", required=True)
    recover.add_argument("--dry-run", action="store_true")
    gc = commands.add_parser("gc", help="Read-only candidate preview")
    gc_choice = gc.add_mutually_exclusive_group()
    gc_choice.add_argument("--dry-run", action="store_true")
    gc_choice.add_argument("--apply", action="store_true")
    gc.add_argument("--older-than", default="30d")
    admin = commands.add_parser("admin", help="Dormant emergency repair")
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)
    reset = admin_sub.add_parser("force-reset-ui-runtime")
    reset.add_argument("--claim-id", required=True)
    reset.add_argument("--reason", required=True)
    upgrade = commands.add_parser(
        "upgrade", help="Read-only release status; mutation disabled")
    upgrade.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in {"list", "describe", "doctor"}:
            catalog = load_catalog()
            if args.command == "list":
                _print({
                    "status": "READ_ONLY",
                    "capabilities": [
                        _describe(name, catalog)
                        for name in sorted(catalog)
                    ],
                    "production_dispatch_authorized": False,
                })
            elif args.command == "describe":
                _print(_describe(args.capability, catalog))
            else:
                # Stage-wise on-demand v2 facts; alive != ready. Missing
                # native/authorization proof is reported UNKNOWN rather
                # than converting a healthy host PID to execution rights.
                _print(inspect_node_health_readonly())
            return 0
        if args.command == "status":
            state = CapabilityStore().observe(args.capability_job_id)
            _print(state)
            return 0
        if args.command == "invoke":
            request = _trusted_request(args.request)
            if request.get("capability") != args.capability:
                raise CapabilityStoreError("CAPABILITY_REQUEST_IDENTITY_MISMATCH")
            _print(foreground_invoke(request))
            return 0
        if args.command == "cancel":
            _print(request_cancel_from_trusted_source(
                args.capability_job_id, reason_code=args.reason))
            return 0
        if args.command == "startup-status":
            _print(inspect_startup_inventory_readonly())
            return 0
        if args.command == "upgrade" and args.status:
            _print(inspect_release_restart_readonly())
            return 0
        if args.command == "admin" and (
                args.admin_command == "force-reset-ui-runtime"):
            # Source-owned stop adapter; no caller-controlled executable,
            # boolean authentication or process name matching.
            _print(emergency_force_reset_after_acceptance(
                claim_id=args.claim_id, reason=args.reason,
                stop_exact_backend=terminate_exact_owner_best_effort,
                proof_after_stop=lambda: observe_trusted_exact_stop_proof(
                    args.claim_id),
            ))
            return 0
        if args.command == "reconcile-resource":
            if args.dry_run:
                proof = observe_trusted_exact_stop_proof(args.claim_id)
                _print(preview_reconcile_resource(
                    claim_id=args.claim_id, proof=proof))
                return 0
            _print(reconcile_resource_exact(claim_id=args.claim_id))
            return 0
        if args.command == "reconcile":
            if args.dry_run:
                _print(inspect_exact_outcome_readonly(
                    args.capability_job_id))
                return 0
            _print(reconcile_exact_after_acceptance(
                args.capability_job_id))
            return 0
        if args.command == "gc":
            duration = args.older_than
            if not duration.endswith("d") or not duration[:-1].isdigit():
                _print({
                    **_not_active("gc"),
                    "reason_code": "GC_DURATION_INVALID",
                })
                return 2
            retention = int(duration[:-1]) * 86400
            if args.apply:
                # Apply is separately source-gated in gc_maintenance.
                # After acceptance, report its actual bounded result
                # rather than returning a hard-coded failure without output.
                _print(gc_apply(older_than_sec=retention))
                return 0
            _print(gc_preview(older_than_sec=retention))
            return 0
        _print(_not_active(
            args.command + ("." + args.admin_command
                            if args.command == "admin" else "")))
        return 2
    except (CatalogUnavailable, CapabilityStoreError,
            ResourceRecoveryRefused, ForegroundEntrypointUnavailable,
            RuntimeEvidenceUnavailable, EvidenceProductionUnavailable,
            IngressAuthorizationUnavailable, AdmissionFenceUnavailable,
            ReleaseUnavailable, ReleaseIntegrityUnavailable,
            ResourceError, PublisherBoundaryError) as exc:
        _print({
            "status": "BLOCKED",
            "reason_code": getattr(
                exc, "code",
                "RESOURCE_STATE_UNAVAILABLE"
                if isinstance(exc, ResourceError)
                else "CAPABILITY_OPERATION_UNAVAILABLE"),
            "command": args.command,
            "execution_authorized": False,
        })
        return 2
    except (OSError, TypeError, ValueError):
        _print({
            "status": "BLOCKED",
            "reason_code": "CAPABILITY_DIAGNOSTIC_UNAVAILABLE",
            "command": args.command,
            "execution_authorized": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
