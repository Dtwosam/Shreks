from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping

from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    validate_fast_paper_accounting,
)

from .fast_paper_authoritative_cutover_config import (
    read_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_runtime.authoritative_release_handoff import (
    load_fast_paper_authoritative_release_handoff,
)
from .fast_paper_runtime.authoritative_runtime import (
    bootstrap_fast_paper_authoritative_runtime,
    load_fast_paper_authoritative_runtime_config,
)


_SCHEMA_NAME = "shreks.fast_paper_manual_recovery_assessment"
_SCHEMA_VERSION = 1
_CUTOVER_REVOCATION_SCHEMA = (
    "shreks.fast_paper_cutover_authorization_revocation"
)
_RELEASE_REVOCATION_SCHEMA = (
    "shreks.fast_paper_release_authorization_revocation"
)
_CUTOVER_FAILURE_SCHEMA = "shreks.fast_paper_physical_cutover_failure"
_RELEASE_FAILURE_SCHEMA = "shreks.fast_paper_release_upgrade_failure"

_PAPER_UNIT = "shreks-paper-campaign.service"
_EVIDENCE_UNIT = "shreks-paper-evidence.service"
_OBSERVE_UNIT = "shreks-observe.service"
_TARGET_UNIT = "shreks.target"
_SHADOW_UNIT = "shreks-fast-paper-shadow.service"
_SHOW_PROPERTIES = "ActiveState,SubState,MainPID"

_CUTOVER_REVOCATION_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "release_source_sha",
        "production_paper_cutover",
        "service_control_authority",
        "signing_submission_authority",
        "live_authority",
        "error_type",
        "revocation_fingerprint_sha256",
    }
)
_RELEASE_REVOCATION_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "target_release_source_sha",
        "target_fast_run_id",
        "release_handoff_fingerprint_sha256",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "error_type",
        "receipt_fingerprint_sha256",
    }
)
_CUTOVER_FAILURE_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "release_source_sha",
        "authoritative_state_changed",
        "legacy_unit_restored",
        "legacy_service_restarted",
        "fast_unit_retained",
        "final_fast_config_retained",
        "authorization_revoked",
        "production_paper_cutover",
        "service_control_authority",
        "signing_submission_authority",
        "live_authority",
        "error_type",
        "receipt_fingerprint_sha256",
    }
)
_RELEASE_FAILURE_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "source_release_source_sha",
        "target_release_source_sha",
        "target_fast_run_id",
        "target_start_attempted",
        "legacy_score_runtime_restored",
        "source_fast_runtime_restarted",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "error_type",
        "receipt_fingerprint_sha256",
    }
)


class FastPaperManualRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or type(self.returncode) is not int:
            raise ValueError("returncode must be exact integer")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise ValueError("stdout/stderr must be exact strings")


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]


def read_fast_paper_manual_recovery_revocation(
    path: str | Path,
) -> dict[str, object]:
    document = _read_canonical_json(path, "manual-recovery revocation")
    schema = document.get("schema_name")
    if schema == _CUTOVER_REVOCATION_SCHEMA:
        _require_exact_fields(
            document,
            _CUTOVER_REVOCATION_FIELDS,
            "cutover revocation",
        )
        _require_common_revocation(document)
        _source_sha(document["release_source_sha"], "release source SHA")
        _text(document["error_type"], "revocation error type")
        _verify_fingerprint(
            document,
            fingerprint_field="revocation_fingerprint_sha256",
            label="cutover revocation",
        )
        if (
            document["service_control_authority"]
            != "EXERCISED_BY_PROTECTED_CEREMONY"
        ):
            raise FastPaperManualRecoveryError(
                "cutover revocation service-control authority is incompatible"
            )
        return document
    if schema == _RELEASE_REVOCATION_SCHEMA:
        _require_exact_fields(
            document,
            _RELEASE_REVOCATION_FIELDS,
            "release revocation",
        )
        _require_common_revocation(document)
        _source_sha(
            document["target_release_source_sha"],
            "target release source SHA",
        )
        _text(document["target_fast_run_id"], "target Fast run id")
        _sha256(
            document["release_handoff_fingerprint_sha256"],
            "release handoff fingerprint",
        )
        _text(document["error_type"], "revocation error type")
        _verify_fingerprint(
            document,
            fingerprint_field="receipt_fingerprint_sha256",
            label="release revocation",
        )
        return document
    raise FastPaperManualRecoveryError(
        "manual-recovery revocation schema is unsupported"
    )


def read_fast_paper_manual_recovery_failure_receipt(
    path: str | Path,
) -> dict[str, object]:
    document = _read_canonical_json(path, "manual-recovery failure receipt")
    schema = document.get("schema_name")
    if schema == _CUTOVER_FAILURE_SCHEMA:
        _require_exact_fields(
            document,
            _CUTOVER_FAILURE_FIELDS,
            "cutover failure receipt",
        )
        _require_common_failure(document)
        _source_sha(document["release_source_sha"], "release source SHA")
        for name in (
            "authoritative_state_changed",
            "legacy_unit_restored",
            "legacy_service_restarted",
            "fast_unit_retained",
            "final_fast_config_retained",
            "authorization_revoked",
        ):
            _bool(document[name], name)
        if (
            document["legacy_unit_restored"] is not False
            or document["legacy_service_restarted"] is not False
            or document["fast_unit_retained"] is not True
            or document["final_fast_config_retained"] is not True
            or document["authorization_revoked"] is not True
            or document["service_control_authority"]
            != "EXERCISED_BY_PROTECTED_CEREMONY"
        ):
            raise FastPaperManualRecoveryError(
                "cutover failure receipt is not a post-start fail-closed state"
            )
        _verify_fingerprint(
            document,
            fingerprint_field="receipt_fingerprint_sha256",
            label="cutover failure receipt",
        )
        return document
    if schema == _RELEASE_FAILURE_SCHEMA:
        _require_exact_fields(
            document,
            _RELEASE_FAILURE_FIELDS,
            "release failure receipt",
        )
        _require_common_failure(document)
        _source_sha(
            document["source_release_source_sha"],
            "source release source SHA",
        )
        _source_sha(
            document["target_release_source_sha"],
            "target release source SHA",
        )
        _text(document["target_fast_run_id"], "target Fast run id")
        for name in (
            "target_start_attempted",
            "legacy_score_runtime_restored",
            "source_fast_runtime_restarted",
        ):
            _bool(document[name], name)
        if (
            document["target_start_attempted"] is not True
            or document["legacy_score_runtime_restored"] is not False
            or document["source_fast_runtime_restarted"] is not False
        ):
            raise FastPaperManualRecoveryError(
                "release failure receipt is not a post-start fail-closed state"
            )
        _verify_fingerprint(
            document,
            fingerprint_field="receipt_fingerprint_sha256",
            label="release failure receipt",
        )
        return document
    raise FastPaperManualRecoveryError(
        "manual-recovery failure receipt schema is unsupported"
    )


def assess_fast_paper_manual_recovery(
    *,
    authoritative_runtime_env_path: str | Path,
    production_authorization_path: str | Path,
    failure_receipt_path: str | Path,
    current_link: str | Path,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    _require_root()
    revocation = read_fast_paper_manual_recovery_revocation(
        production_authorization_path
    )
    failure = read_fast_paper_manual_recovery_failure_receipt(
        failure_receipt_path
    )
    family = _require_evidence_pair(revocation, failure)
    runner = _default_command_runner if command_runner is None else command_runner
    stopped_units = _require_runtime_quiescent(family, runner)

    environment_path = Path(authoritative_runtime_env_path).expanduser()
    try:
        environment = read_fast_paper_authoritative_cutover_environment(
            environment_path
        )
        config = load_fast_paper_authoritative_runtime_config(environment)
        bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
    except Exception as exc:
        raise FastPaperManualRecoveryError(
            "retained authoritative Fast PAPER runtime does not authenticate"
        ) from exc

    manifest = bootstrap.decision_bootstrap.manifest
    execution = bootstrap.execution_bootstrap
    runtime = execution.runtime_state
    checkpoint = execution.checkpoint
    decision_state = bootstrap.decision_bootstrap.state
    expected_release_sha = _revocation_release_sha(revocation)
    if manifest.release_source_sha != expected_release_sha:
        raise FastPaperManualRecoveryError(
            "retained Fast manifest release does not match revocation"
        )
    release = _require_current_release(
        current_link,
        expected_release_sha=expected_release_sha,
    )

    if family == "RELEASE_UPGRADE":
        target_run_id = revocation["target_fast_run_id"]
        if (
            execution.binding.fast_run_id != target_run_id
            or failure["target_fast_run_id"] != target_run_id
        ):
            raise FastPaperManualRecoveryError(
                "retained Fast run does not match release-recovery evidence"
            )
        handoff = load_fast_paper_authoritative_release_handoff(
            config.execution_config.database_path,
            target_fast_run_id=target_run_id,
        )
        if (
            handoff.handoff_fingerprint_sha256
            != revocation["release_handoff_fingerprint_sha256"]
            or handoff.target_release_source_sha != expected_release_sha
            or handoff.source_release_source_sha
            != failure["source_release_source_sha"]
        ):
            raise FastPaperManualRecoveryError(
                "release handoff audit does not match recovery evidence"
            )
        handoff_fingerprint = handoff.handoff_fingerprint_sha256
    else:
        handoff_fingerprint = None

    accounting = validate_fast_paper_accounting(checkpoint.state)
    if accounting.status is not AccountingValidationStatus.RECONCILED:
        raise FastPaperManualRecoveryError(
            "authoritative Fast PAPER accounting is not reconciled"
        )
    _require_position_mapping_consistent(checkpoint.state.ledger, runtime)

    decision_sequence = (
        None
        if decision_state.cursor is None
        else decision_state.cursor.decision_sequence
    )
    execution_sequence = runtime.last_processed_source_sequence
    decision_evidence_count = _decision_evidence_count(config)
    pending_buy = checkpoint.state.pending_buy is not None
    recovery_state = _recovery_state(
        checkpoint_sequence=checkpoint.sequence,
        decision_sequence=decision_sequence,
        execution_sequence=execution_sequence,
        pending_buy=pending_buy,
        decision_evidence_count=decision_evidence_count,
    )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "state": recovery_state,
        "failure_family": family,
        "release_source_sha": expected_release_sha,
        "release_directory": str(release),
        "fast_run_id": execution.binding.fast_run_id,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "binding_fingerprint_sha256": (
            execution.binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            execution.execution_policy.policy_fingerprint_sha256
        ),
        "decision_state_fingerprint_sha256": (
            decision_state.state_fingerprint_sha256
        ),
        "runtime_state_fingerprint_sha256": (
            runtime.state_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": checkpoint.sequence,
        "paper_checkpoint_payload_sha256": checkpoint.payload_sha256,
        "decision_cursor_sequence": decision_sequence,
        "execution_cursor_sequence": execution_sequence,
        "pending_buy": pending_buy,
        "decision_evidence_count": decision_evidence_count,
        "open_position_count": accounting.open_position_count,
        "mapped_open_position_count": len(runtime.market_positions),
        "accounting": accounting.status.value,
        "release_handoff_fingerprint_sha256": handoff_fingerprint,
        "revocation_fingerprint_sha256": _recovery_evidence_fingerprint(
            revocation
        ),
        "failure_receipt_fingerprint_sha256": (
            failure["receipt_fingerprint_sha256"]
        ),
        "stopped_units": stopped_units,
        "recovery_restart_authority": "NOT_GRANTED",
        "service_control_authority": "READ_ONLY",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(material)


def _require_evidence_pair(
    revocation: Mapping[str, object],
    failure: Mapping[str, object],
) -> str:
    if revocation["schema_name"] == _CUTOVER_REVOCATION_SCHEMA:
        if (
            failure["schema_name"] != _CUTOVER_FAILURE_SCHEMA
            or revocation["release_source_sha"]
            != failure["release_source_sha"]
        ):
            raise FastPaperManualRecoveryError(
                "cutover revocation/failure receipt identity mismatch"
            )
        return "PHYSICAL_CUTOVER"
    if (
        failure["schema_name"] != _RELEASE_FAILURE_SCHEMA
        or revocation["target_release_source_sha"]
        != failure["target_release_source_sha"]
        or revocation["target_fast_run_id"]
        != failure["target_fast_run_id"]
    ):
        raise FastPaperManualRecoveryError(
            "release revocation/failure receipt identity mismatch"
        )
    return "RELEASE_UPGRADE"


def _require_runtime_quiescent(
    family: str,
    runner: CommandRunner,
) -> tuple[str, ...]:
    units = (
        (_PAPER_UNIT, _SHADOW_UNIT)
        if family == "PHYSICAL_CUTOVER"
        else (
            _PAPER_UNIT,
            _EVIDENCE_UNIT,
            _OBSERVE_UNIT,
            _TARGET_UNIT,
        )
    )
    stopped = []
    for unit in units:
        command = _show_command(unit)
        result = runner(command)
        if result.returncode != 0 or result.stderr.strip():
            raise FastPaperManualRecoveryError(
                f"unable to authenticate stopped unit {unit}"
            )
        fields = _parse_key_values(result.stdout)
        try:
            main_pid = int(fields["MainPID"])
        except (KeyError, ValueError) as exc:
            raise FastPaperManualRecoveryError(
                f"stopped unit state is invalid for {unit}"
            ) from exc
        if (
            fields.get("ActiveState") != "inactive"
            or fields.get("SubState") != "dead"
            or main_pid != 0
        ):
            raise FastPaperManualRecoveryError(
                f"manual recovery requires {unit} inactive/dead with MainPID=0"
            )
        stopped.append(unit)
    return tuple(stopped)


def _require_current_release(
    current_link: str | Path,
    *,
    expected_release_sha: str,
) -> Path:
    link = Path(current_link).expanduser()
    if not link.is_symlink():
        raise FastPaperManualRecoveryError(
            "current release must be an existing symlink"
        )
    try:
        release = link.resolve(strict=True)
    except OSError as exc:
        raise FastPaperManualRecoveryError(
            "current release cannot be resolved"
        ) from exc
    if not release.is_dir() or release.name != expected_release_sha:
        raise FastPaperManualRecoveryError(
            "current release does not match revoked Fast release"
        )
    return release


def _require_position_mapping_consistent(ledger, runtime_state) -> None:
    open_ids = {
        position.position_id
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    }
    mapped_ids = {
        mapping.position_id
        for mapping in runtime_state.market_positions
    }
    if open_ids != mapped_ids:
        raise FastPaperManualRecoveryError(
            "authoritative open-position mapping does not match PAPER ledger"
        )


def _decision_evidence_count(config) -> int:
    root = config.decision_config.evidence_directory
    checkpoint = config.decision_config.checkpoint_path
    count = 0
    for child in root.iterdir():
        if checkpoint is not None and child == checkpoint:
            continue
        if child.is_symlink() or not child.is_file():
            raise FastPaperManualRecoveryError(
                "decision evidence root contains a non-regular member"
            )
        count += 1
    return count


def _recovery_state(
    *,
    checkpoint_sequence: int,
    decision_sequence: int | None,
    execution_sequence: int | None,
    pending_buy: bool,
    decision_evidence_count: int,
) -> str:
    if pending_buy:
        return "RECOVERY_RECONCILIATION_REQUIRED"
    if execution_sequence is None:
        if checkpoint_sequence == 0 and decision_evidence_count == 0:
            return "READY_FOR_FAST_RECOVERY_PLANNING"
        return "RECOVERY_RECONCILIATION_REQUIRED"
    if decision_sequence == execution_sequence:
        return "READY_FOR_FAST_RECOVERY_PLANNING"
    if (
        decision_sequence is not None
        and decision_sequence == execution_sequence + 1
    ):
        return "RECOVERY_RECONCILIATION_REQUIRED"
    raise FastPaperManualRecoveryError(
        "authoritative learned decision/execution cursors are incompatible"
    )


def _revocation_release_sha(document: Mapping[str, object]) -> str:
    if document["schema_name"] == _CUTOVER_REVOCATION_SCHEMA:
        return str(document["release_source_sha"])
    return str(document["target_release_source_sha"])


def _recovery_evidence_fingerprint(
    document: Mapping[str, object],
) -> str:
    if document["schema_name"] == _CUTOVER_REVOCATION_SCHEMA:
        return str(document["revocation_fingerprint_sha256"])
    return str(document["receipt_fingerprint_sha256"])


def _require_common_revocation(document: Mapping[str, object]) -> None:
    if (
        document["schema_version"] != 1
        or document["state"] != "REVOKED_MANUAL_RECOVERY"
        or document["production_paper_cutover"]
        != "STOPPED_MANUAL_RECOVERY"
        or document["signing_submission_authority"] != "NOT_GRANTED"
        or document["live_authority"] != "DISABLED"
    ):
        raise FastPaperManualRecoveryError(
            "manual-recovery revocation state is incompatible"
        )


def _require_common_failure(document: Mapping[str, object]) -> None:
    if (
        document["schema_version"] != 1
        or document["state"] != "MANUAL_RECOVERY_REQUIRED"
        or document["production_paper_cutover"]
        != "STOPPED_MANUAL_RECOVERY"
        or document["signing_submission_authority"] != "NOT_GRANTED"
        or document["live_authority"] != "DISABLED"
    ):
        raise FastPaperManualRecoveryError(
            "manual-recovery failure state is incompatible"
        )
    _text(document["error_type"], "failure error type")


def _read_canonical_json(
    path: str | Path,
    label: str,
) -> dict[str, object]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperManualRecoveryError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise FastPaperManualRecoveryError(
            f"{label} is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperManualRecoveryError(
            f"{label} must be a JSON object"
        )
    if payload != _canonical(document) + "\n":
        raise FastPaperManualRecoveryError(
            f"{label} must use canonical JSON"
        )
    return document


def _require_exact_fields(
    document: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    if frozenset(document) != expected:
        raise FastPaperManualRecoveryError(
            f"{label} has unknown or missing fields"
        )


def _verify_fingerprint(
    document: Mapping[str, object],
    *,
    fingerprint_field: str,
    label: str,
) -> None:
    claimed = _sha256(document[fingerprint_field], fingerprint_field)
    material = dict(document)
    material.pop(fingerprint_field)
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise FastPaperManualRecoveryError(
            f"{label} fingerprint mismatch"
        )


def _source_sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise FastPaperManualRecoveryError(
            f"{label} must be exactly 40 lowercase hex characters"
        )
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise FastPaperManualRecoveryError(
            f"{label} must be lowercase SHA-256 hex"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FastPaperManualRecoveryError(
            f"{label} must be non-empty canonical text"
        )
    return value


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise FastPaperManualRecoveryError(
            f"{label} must be exact boolean"
        )
    return value


def _show_command(unit: str) -> tuple[str, ...]:
    return (
        "systemctl",
        "show",
        unit,
        f"--property={_SHOW_PROPERTIES}",
        "--no-pager",
    )


def _default_command_runner(
    command: tuple[str, ...],
) -> HostCommandResult:
    allowed = {
        _show_command(_PAPER_UNIT),
        _show_command(_EVIDENCE_UNIT),
        _show_command(_OBSERVE_UNIT),
        _show_command(_TARGET_UNIT),
        _show_command(_SHADOW_UNIT),
    }
    if command not in allowed:
        raise FastPaperManualRecoveryError(
            "manual-recovery verifier command is outside read-only allowlist"
        )
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FastPaperManualRecoveryError(
            "manual-recovery read-only host command failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _parse_key_values(payload: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in payload.splitlines():
        if not raw:
            continue
        if "=" not in raw:
            raise FastPaperManualRecoveryError(
                "systemd show output is malformed"
            )
        key, value = raw.split("=", 1)
        if key in values:
            raise FastPaperManualRecoveryError(
                "systemd show output contains duplicate keys"
            )
        values[key] = value
    expected = {"ActiveState", "SubState", "MainPID"}
    if set(values) != expected:
        raise FastPaperManualRecoveryError(
            "systemd show output has unknown or missing fields"
        )
    return values


def _finalize(material: dict[str, object]) -> dict[str, object]:
    return {
        **material,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


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
    )


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperManualRecoveryError(
            "manual-recovery verification requires root"
        )


def _production_paths() -> tuple[Path, Path, Path]:
    return (
        Path("/etc/shreks/fast-paper-authoritative.env"),
        Path("/etc/shreks/fast-paper-cutover-authorization.json"),
        Path("/opt/shreks/current"),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-manual-recovery"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    assess = sub.add_parser("assess")
    assess.add_argument("--failure-receipt-path", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(
        sys.argv[1:] if argv is None else argv
    )
    env_path, authorization_path, current_link = _production_paths()
    try:
        result = assess_fast_paper_manual_recovery(
            authoritative_runtime_env_path=env_path,
            production_authorization_path=authorization_path,
            failure_receipt_path=args.failure_receipt_path,
            current_link=current_link,
        )
    except Exception as exc:
        print(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "recovery_restart_authority": "NOT_GRANTED",
                    "service_control_authority": "READ_ONLY",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
