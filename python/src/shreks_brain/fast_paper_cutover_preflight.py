from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Mapping

from shreks_brain.fast_paper_champion_promotion import (
    read_fast_paper_champion_registry,
)
from shreks_brain.fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from shreks_brain.fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    decode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    load_latest_paper_checkpoint,
    validate_fast_paper_accounting,
    validate_paper_accounting,
)


FAST_PAPER_CUTOVER_PREFLIGHT_SCHEMA_NAME = (
    "shreks.fast_paper_cutover_preflight"
)
FAST_PAPER_CUTOVER_PREFLIGHT_SCHEMA_VERSION = 1

_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_RESTART_RECEIPT_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "release_source_sha",
        "release_directory",
        "pre_restart_main_pid",
        "post_restart_main_pid",
        "pre_restart_invocation_id",
        "post_restart_invocation_id",
        "automatic_restart_delta",
        "pre_checkpoint_sequence",
        "post_checkpoint_sequence",
        "pre_last_processed_source_sequence",
        "post_last_processed_source_sequence",
        "run_id",
        "binding_fingerprint_sha256",
        "observed_at_unix_ms",
        "observation_seconds",
        "main_pid",
        "invocation_id",
        "unit_file_state",
        "n_restarts",
        "exec_main_status",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "completed_cycles_start",
        "completed_cycles_end",
        "completed_cycles_delta",
        "decisions_produced_delta",
        "executions_committed_delta",
        "decision_cursor_sequence_start",
        "decision_cursor_sequence_end",
        "execution_cursor_sequence_start",
        "execution_cursor_sequence_end",
        "paper_checkpoint_sequence_start",
        "paper_checkpoint_sequence_end",
        "pending_buy",
        "open_market_positions",
        "cpu_ticks_delta",
        "cpu_percent",
        "rss_bytes_start",
        "rss_bytes_end",
        "rss_bytes_peak",
        "shadow_storage_bytes_start",
        "shadow_storage_bytes_end",
        "shadow_storage_bytes_delta",
        "private_network_interfaces",
        "private_network_non_loopback_interfaces",
        "private_network_rx_bytes_delta",
        "private_network_tx_bytes_delta",
        "shadow_runtime",
        "shadow_enable_authority",
        "production_paper_cutover",
        "authoritative_paper_runtime",
        "signing_submission_authority",
        "live_authority",
        "receipt_fingerprint_sha256",
    }
)


class FastPaperCutoverPreflightError(RuntimeError):
    pass


def assess_fast_paper_cutover_preflight(
    *,
    fast_manifest_path: str | Path,
    champion_registry_path: str | Path,
    shadow_restart_receipt_path: str | Path,
    shadow_ledger_database_path: str | Path,
    legacy_runtime_manifest_path: str | Path,
    legacy_observer_database_path: str | Path,
    expected_release_sha: str,
) -> dict[str, object]:
    expected_sha = _release_sha(expected_release_sha)

    manifest = _read_fast_manifest(
        fast_manifest_path,
        expected_sha=expected_sha,
    )
    registry = _read_registry(champion_registry_path)
    _require_approved_champion(manifest, registry)

    restart = _read_restart_receipt(shadow_restart_receipt_path)
    _require_restart_identity(
        restart,
        manifest=manifest,
        expected_sha=expected_sha,
    )

    try:
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=restart["run_id"],
            database_path=shadow_ledger_database_path,
        )
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "shadow ledger binding construction failed"
        ) from exc
    if (
        binding.binding_fingerprint_sha256
        != restart["binding_fingerprint_sha256"]
    ):
        raise FastPaperCutoverPreflightError(
            "shadow ledger binding fingerprint does not match restart proof"
        )

    try:
        shadow_checkpoint = (
            load_latest_fast_paper_shadow_ledger_checkpoint(
                manifest,
                binding,
            )
        )
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "latest shadow PAPER checkpoint authentication failed"
        ) from exc
    if shadow_checkpoint is None:
        shadow_status = None
        shadow_sequence = None
        shadow_payload_sha256 = None
    else:
        try:
            shadow_accounting = validate_fast_paper_accounting(
                shadow_checkpoint.state
            )
        except Exception as exc:
            raise FastPaperCutoverPreflightError(
                "shadow PAPER accounting validation failed"
            ) from exc
        shadow_status = _accounting_status(shadow_accounting.status)
        shadow_sequence = shadow_checkpoint.sequence
        shadow_payload_sha256 = _sha256(
            shadow_checkpoint.payload_sha256,
            "shadow checkpoint payload fingerprint",
        )

    legacy_manifest = _read_legacy_manifest(legacy_runtime_manifest_path)
    try:
        legacy_checkpoint = load_latest_paper_checkpoint(
            legacy_observer_database_path,
            legacy_manifest.paper_run_id,
        )
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "latest legacy PAPER checkpoint authentication failed"
        ) from exc

    legacy_status: str | None = None
    legacy_sequence: int | None = None
    legacy_payload_sha256: str | None = None
    open_positions: int | None = None
    pending_entries: int | None = None
    deferred_executions: int | None = None
    active_intents: int | None = None

    if legacy_checkpoint is not None:
        try:
            legacy_accounting = validate_paper_accounting(
                legacy_checkpoint.state
            )
        except Exception as exc:
            raise FastPaperCutoverPreflightError(
                "legacy PAPER accounting validation failed"
            ) from exc
        legacy_status = _accounting_status(legacy_accounting.status)
        legacy_sequence = legacy_checkpoint.sequence
        legacy_payload_sha256 = _sha256(
            legacy_checkpoint.payload_sha256,
            "legacy checkpoint payload fingerprint",
        )
        (
            open_positions,
            pending_entries,
            deferred_executions,
            active_intents,
        ) = _legacy_handoff_counts(legacy_checkpoint.state)

    gates = [
        _gate(
            "APPROVED_FAST_CHAMPION_BOUND",
            True,
            manifest.champion_fingerprint_sha256,
            manifest.champion_fingerprint_sha256,
            "approved Fast Lane champion exactly matches the runtime manifest",
        ),
        _gate(
            "SHADOW_RESTART_RECONSTRUCTION_PROVEN",
            True,
            restart["state"],
            "RESTART_RECONSTRUCTION_PROVEN",
            "physical learned-shadow restart proof is exact and authenticated",
        ),
        _gate(
            "SHADOW_PAPER_CHECKPOINT_PRESENT",
            shadow_checkpoint is not None,
            shadow_sequence,
            "present",
            (
                "latest isolated learned PAPER checkpoint is available"
                if shadow_checkpoint is not None
                else "latest isolated learned PAPER checkpoint is unavailable"
            ),
        ),
        _gate(
            "SHADOW_PAPER_ACCOUNTING_RECONCILED",
            shadow_status == AccountingValidationStatus.RECONCILED.value,
            shadow_status,
            AccountingValidationStatus.RECONCILED.value,
            "isolated learned PAPER accounting must reconcile",
        ),
        _gate(
            "LEGACY_FINAL_CHECKPOINT_PRESENT",
            legacy_checkpoint is not None,
            legacy_sequence,
            "present",
            (
                "latest authoritative legacy PAPER checkpoint is available"
                if legacy_checkpoint is not None
                else "final authoritative legacy PAPER checkpoint is unavailable"
            ),
        ),
        _gate(
            "LEGACY_PAPER_ACCOUNTING_RECONCILED",
            legacy_status == AccountingValidationStatus.RECONCILED.value,
            legacy_status,
            AccountingValidationStatus.RECONCILED.value,
            "legacy authoritative PAPER accounting must reconcile",
        ),
        _gate(
            "LEGACY_OPEN_POSITIONS_ZERO",
            open_positions == 0,
            open_positions,
            0,
            "legacy authoritative PAPER ledger must be flat",
        ),
        _gate(
            "LEGACY_PENDING_ENTRIES_ZERO",
            pending_entries == 0,
            pending_entries,
            0,
            "legacy runtime must have no pending entry",
        ),
        _gate(
            "LEGACY_DEFERRED_EXECUTIONS_ZERO",
            deferred_executions == 0,
            deferred_executions,
            0,
            "legacy runtime must have no deferred entry or exit execution",
        ),
        _gate(
            "LEGACY_ACTIVE_INTENTS_ZERO",
            active_intents == 0,
            active_intents,
            0,
            "legacy runtime must have no active intent",
        ),
    ]

    decision = (
        "CUTOVER_PREFLIGHT_READY"
        if all(gate["status"] == "PASS" for gate in gates)
        else "CUTOVER_PREFLIGHT_NOT_READY"
    )
    observed_state = {
        "shadow_accounting_status": shadow_status,
        "legacy_accounting_status": legacy_status,
        "legacy_open_position_count": open_positions,
        "legacy_pending_entry_count": pending_entries,
        "legacy_deferred_execution_count": deferred_executions,
        "legacy_active_intent_count": active_intents,
    }
    material: dict[str, object] = {
        "schema_name": FAST_PAPER_CUTOVER_PREFLIGHT_SCHEMA_NAME,
        "schema_version": FAST_PAPER_CUTOVER_PREFLIGHT_SCHEMA_VERSION,
        "release_source_sha": expected_sha,
        "fast_manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_registry_revision": registry["revision"],
        "champion_registry_fingerprint_sha256": registry[
            "registry_fingerprint_sha256"
        ],
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "shadow_restart_receipt_fingerprint_sha256": restart[
            "receipt_fingerprint_sha256"
        ],
        "shadow_binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "shadow_run_id": binding.run_id,
        "shadow_checkpoint_sequence": shadow_sequence,
        "shadow_checkpoint_payload_sha256": shadow_payload_sha256,
        "legacy_runtime_manifest_fingerprint_sha256": (
            legacy_manifest.manifest_fingerprint_sha256
        ),
        "legacy_paper_run_id": legacy_manifest.paper_run_id,
        "legacy_checkpoint_sequence": legacy_sequence,
        "legacy_checkpoint_payload_sha256": legacy_payload_sha256,
        "observed_state": observed_state,
        "gate_results": gates,
        "decision": decision,
        "production_fast_paper_runner": "NOT_PRESENT_IN_THIS_SLICE",
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "authoritative_paper_mutation": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize_report(material)


def canonical_fast_paper_cutover_preflight(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperCutoverPreflightError(
            "cutover preflight document must be a mapping"
        )
    try:
        return _canonical(dict(document))
    except (TypeError, ValueError) as exc:
        raise FastPaperCutoverPreflightError(
            "cutover preflight document is not canonicalizable"
        ) from exc


def _read_fast_manifest(
    path: str | Path,
    *,
    expected_sha: str,
):
    try:
        manifest = read_fast_paper_runtime_manifest(path)
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperCutoverPreflightError(
            "Fast PAPER runtime manifest release identity mismatch"
        )
    return manifest


def _read_registry(path: str | Path) -> dict[str, object]:
    try:
        registry = read_fast_paper_champion_registry(path)
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "Fast PAPER champion registry authentication failed"
        ) from exc
    if not isinstance(registry, dict):
        raise FastPaperCutoverPreflightError(
            "Fast PAPER champion registry result is incompatible"
        )
    _positive_int(registry.get("revision"), "champion registry revision")
    _sha256(
        registry.get("registry_fingerprint_sha256"),
        "champion registry fingerprint",
    )
    return registry


def _require_approved_champion(manifest, registry: Mapping[str, object]) -> None:
    if (
        registry.get("current_champion_version")
        != manifest.champion_version
        or registry.get("current_champion_fingerprint_sha256")
        != manifest.champion_fingerprint_sha256
    ):
        raise FastPaperCutoverPreflightError(
            "approved champion identity does not match Fast PAPER runtime"
        )


def _read_restart_receipt(path: str | Path) -> dict[str, object]:
    source = _regular_file(path, "shadow restart receipt")
    try:
        payload = source.read_text(encoding="utf-8")
        document = _decode_canonical_json(payload, "shadow restart receipt")
    except (OSError, UnicodeError, ValueError) as exc:
        raise FastPaperCutoverPreflightError(
            "shadow restart receipt is malformed or non-canonical"
        ) from exc
    if frozenset(document) != _RESTART_RECEIPT_FIELDS:
        raise FastPaperCutoverPreflightError(
            "shadow restart receipt has unknown or missing fields"
        )
    claimed = _sha256(
        document.get("receipt_fingerprint_sha256"),
        "shadow restart receipt fingerprint",
    )
    material = dict(document)
    material.pop("receipt_fingerprint_sha256", None)
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise FastPaperCutoverPreflightError(
            "shadow restart receipt fingerprint mismatch"
        )
    if (
        document.get("schema_name")
        != "shreks.fast_paper_shadow_physical_restart"
        or document.get("schema_version") != 1
        or document.get("state") != "RESTART_RECONSTRUCTION_PROVEN"
    ):
        raise FastPaperCutoverPreflightError(
            "shadow restart receipt schema/state is incompatible"
        )
    _non_empty(document.get("run_id"), "shadow restart run_id")
    _sha256(
        document.get("binding_fingerprint_sha256"),
        "shadow restart binding fingerprint",
    )
    return document


def _require_restart_identity(
    receipt: Mapping[str, object],
    *,
    manifest,
    expected_sha: str,
) -> None:
    expected = {
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "shadow_runtime": "ACTIVE_DETACHED",
        "shadow_enable_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "authoritative_paper_runtime": "LEGACY_UNCHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    for name, value in expected.items():
        if receipt.get(name) != value:
            raise FastPaperCutoverPreflightError(
                f"shadow restart receipt {name} identity mismatch"
            )


def _read_legacy_manifest(path: str | Path):
    source = _regular_file(path, "legacy PAPER runtime manifest")
    try:
        payload = source.read_bytes()
        manifest = decode_observer_paper_campaign_runtime_manifest(payload)
    except Exception as exc:
        raise FastPaperCutoverPreflightError(
            "legacy PAPER runtime manifest authentication failed"
        ) from exc
    _non_empty(manifest.paper_run_id, "legacy PAPER run id")
    _sha256(
        manifest.manifest_fingerprint_sha256,
        "legacy PAPER runtime manifest fingerprint",
    )
    return manifest


def _legacy_handoff_counts(state) -> tuple[int, int, int, int]:
    try:
        positions = state.ledger.positions
        managed_positions = state.managed_positions
        pending_entry = state.pending_entry
    except AttributeError as exc:
        raise FastPaperCutoverPreflightError(
            "legacy PAPER checkpoint state is incompatible"
        ) from exc

    open_positions = sum(
        1
        for position in positions
        if position.state is PaperPositionState.OPEN
    )
    pending_entries = 1 if pending_entry is not None else 0
    pending_exits = sum(
        1
        for managed in managed_positions
        if managed.pending_exit is not None
    )
    deferred_executions = pending_entries + pending_exits
    active_intents = pending_entries
    return (
        open_positions,
        pending_entries,
        deferred_executions,
        active_intents,
    )


def _gate(
    code: str,
    passed: bool,
    observed: object,
    expected: object,
    message: str,
) -> dict[str, object]:
    return {
        "code": code,
        "status": "PASS" if passed else "FAIL",
        "observed_value": observed,
        "expected_value": expected,
        "message": message,
    }


def _finalize_report(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    if "report_fingerprint_sha256" in document:
        raise FastPaperCutoverPreflightError(
            "cutover preflight material may not predefine report fingerprint"
        )
    return {
        **document,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(document).encode("utf-8")
        ).hexdigest(),
    }


def _accounting_status(value: object) -> str:
    if type(value) is AccountingValidationStatus:
        return value.value
    try:
        return AccountingValidationStatus(value).value
    except (TypeError, ValueError) as exc:
        raise FastPaperCutoverPreflightError(
            "PAPER accounting status is incompatible"
        ) from exc


def _regular_file(path: str | Path, label: str) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperCutoverPreflightError(
            f"{label} must be a regular non-symlink file"
        )
    return source


def _decode_canonical_json(
    payload: str,
    label: str,
) -> dict[str, object]:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    if payload != _canonical(document):
        raise ValueError(f"{label} must use canonical JSON")
    return document


def _release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperCutoverPreflightError(
            "expected release SHA must be lowercase 40-character hex"
        )
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperCutoverPreflightError(
            f"{label} must be lowercase SHA-256"
        )
    return value


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FastPaperCutoverPreflightError(
            f"{label} must be non-empty trimmed text"
        )
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperCutoverPreflightError(
            f"{label} must be a positive integer"
        )
    return value


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-cutover-preflight"
    )
    parser.add_argument("--fast-manifest-path", required=True)
    parser.add_argument("--champion-registry-path", required=True)
    parser.add_argument("--shadow-restart-receipt-path", required=True)
    parser.add_argument("--shadow-ledger-database-path", required=True)
    parser.add_argument("--legacy-runtime-manifest-path", required=True)
    parser.add_argument("--legacy-observer-database-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = assess_fast_paper_cutover_preflight(
            fast_manifest_path=args.fast_manifest_path,
            champion_registry_path=args.champion_registry_path,
            shadow_restart_receipt_path=args.shadow_restart_receipt_path,
            shadow_ledger_database_path=args.shadow_ledger_database_path,
            legacy_runtime_manifest_path=args.legacy_runtime_manifest_path,
            legacy_observer_database_path=args.legacy_observer_database_path,
            expected_release_sha=args.expected_release_sha,
        )
    except (FastPaperCutoverPreflightError, OSError, ValueError) as exc:
        print(
            _canonical(
                {
                    "schema_name": (
                        "shreks.fast_paper_cutover_preflight_failure"
                    ),
                    "schema_version": 1,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "production_paper_cutover": "NOT_GRANTED",
                    "service_control_authority": "NOT_GRANTED",
                    "authoritative_paper_mutation": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1

    print(_canonical(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
