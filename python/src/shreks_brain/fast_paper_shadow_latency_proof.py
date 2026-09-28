from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Mapping

from shreks_brain.paper import PaperLedgerReasonCode

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_execution_source import (
    read_fast_paper_shadow_execution_input_source_record,
)
from .fast_paper_runtime.shadow_executor import (
    reconstruct_fast_paper_shadow_decision,
    reconstruct_fast_paper_shadow_pending_buy_retry,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    load_fast_paper_shadow_ledger_checkpoint_by_sequence,
)
from .fast_paper_runtime.shadow_pending_buy_retry_source import (
    read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint,
)
from .fast_paper_runtime.shadow_runtime_state import (
    load_fast_paper_shadow_runtime_state_by_checkpoint_sequence,
)
from .fast_paper_shadow_execution_telemetry import (
    _probe_retry_source_bindings,
    _probe_source_bindings,
    _require_retry_successor,
    _require_successor,
    _retry_source_filename,
    _single_new_ledger_entry,
)
from .fast_paper_shadow_sample_proof import _read_window_decisions
from .fast_paper_shadow_trade_economics import (
    _read_sample_proof,
    _require_sample_matches,
)


FAST_PAPER_SHADOW_LATENCY_PROOF_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_latency_proof"
)
FAST_PAPER_SHADOW_LATENCY_PROOF_SCHEMA_VERSION = 1


class FastPaperShadowLatencyProofError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowLatencyProofPolicy:
    version: str
    min_buy_decision_count: int
    min_booked_entry_count: int
    min_distinct_selected_horizon_count: int
    max_unbooked_buy_fraction: float
    max_p95_event_to_booked_horizon_fraction: float
    max_p99_event_to_booked_horizon_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("latency proof policy version must be non-empty")
        for name in (
            "min_buy_decision_count",
            "min_booked_entry_count",
            "min_distinct_selected_horizon_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        fraction = _finite_number(
            "max_unbooked_buy_fraction",
            self.max_unbooked_buy_fraction,
        )
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(
                "max_unbooked_buy_fraction must lie within [0, 1]"
            )
        for name in (
            "max_p95_event_to_booked_horizon_fraction",
            "max_p99_event_to_booked_horizon_fraction",
        ):
            value = _finite_number(name, getattr(self, name))
            if value <= 0.0:
                raise ValueError(f"{name} must be strictly positive")


_POLICY_KEYS = frozenset(
    field.name for field in fields(FastPaperShadowLatencyProofPolicy)
)


def encode_fast_paper_shadow_latency_proof_policy(
    policy: FastPaperShadowLatencyProofPolicy,
) -> str:
    if type(policy) is not FastPaperShadowLatencyProofPolicy:
        raise ValueError(
            "policy must be exact FastPaperShadowLatencyProofPolicy"
        )
    return json.dumps(
        asdict(policy),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_fast_paper_shadow_latency_proof_policy(
    payload: str,
) -> FastPaperShadowLatencyProofPolicy:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError("latency proof policy JSON is malformed") from exc
    if type(value) is not dict or frozenset(value) != _POLICY_KEYS:
        raise ValueError("latency proof policy keys are incompatible")
    return FastPaperShadowLatencyProofPolicy(**value)


def fast_paper_shadow_latency_proof_policy_fingerprint_sha256(
    policy: FastPaperShadowLatencyProofPolicy,
) -> str:
    return hashlib.sha256(
        encode_fast_paper_shadow_latency_proof_policy(policy).encode(
            "utf-8"
        )
    ).hexdigest()


def collect_fast_paper_shadow_latency_proof(
    *,
    manifest_path: str | Path,
    execution_policy_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    sample_proof_path: str | Path,
    latency_policy: FastPaperShadowLatencyProofPolicy,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    if type(latency_policy) is not FastPaperShadowLatencyProofPolicy:
        raise FastPaperShadowLatencyProofError(
            "latency_policy must be exact FastPaperShadowLatencyProofPolicy"
        )
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowLatencyProofError(
            "latency proof run id must be non-empty"
        )
    since, until = _window(since_unix_ms, until_unix_ms)

    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        execution_policy = read_fast_paper_shadow_execution_policy(
            manifest,
            execution_policy_path,
        )
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=run_id,
            database_path=ledger_database_path,
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof runtime authority authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_release_sha:
        raise FastPaperShadowLatencyProofError(
            "latency proof release identity mismatch"
        )

    try:
        sample = _read_sample_proof(sample_proof_path)
        _require_sample_matches(
            sample,
            manifest=manifest,
            binding=binding,
            expected_release_sha=expected_release_sha,
            since_unix_ms=since,
            until_unix_ms=until,
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof FL11.1 prerequisite failed"
        ) from exc

    try:
        decisions = _read_window_decisions(
            manifest=manifest,
            decision_evidence_directory=decision_evidence_directory,
            since_unix_ms=since,
            until_unix_ms=until,
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof decision evidence authentication failed"
        ) from exc
    if len(decisions) != sample["decision_count"]:
        raise FastPaperShadowLatencyProofError(
            "latency proof decision count does not reconcile with FL11.1"
        )

    source_root = _directory(
        execution_source_directory,
        "execution source",
    )
    retry_root = _directory(
        pending_buy_retry_source_directory,
        "pending BUY retry source",
    )
    retry_index = _retry_index(retry_root)

    buys = tuple(
        decision for decision in decisions
        if decision.decision.action == "BUY"
    )
    observations = tuple(
        _buy_observation(
            evidence,
            manifest=manifest,
            execution_policy=execution_policy,
            binding=binding,
            source_root=source_root,
            retry_root=retry_root,
            retry_index=retry_index,
        )
        for evidence in buys
    )
    overall = _summarize_observations(observations)
    by_horizon = _summarize_by_horizon(observations)
    _reconcile_horizons(overall, by_horizon)

    gates = _gates(overall, latency_policy)
    decision = (
        "LATENCY_PROVEN"
        if all(gate["status"] == "PASS" for gate in gates)
        else "LATENCY_NOT_PROVEN"
    )

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_LATENCY_PROOF_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_LATENCY_PROOF_SCHEMA_VERSION,
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "action_policy_version": manifest.action_policy.version,
        "binding_fingerprint_sha256": binding.binding_fingerprint_sha256,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        "sample_proof_fingerprint_sha256": sample[
            "report_fingerprint_sha256"
        ],
        "sample_policy_version": sample["policy_version"],
        "latency_policy": asdict(latency_policy),
        "latency_policy_fingerprint_sha256": (
            fast_paper_shadow_latency_proof_policy_fingerprint_sha256(
                latency_policy
            )
        ),
        **overall,
        "by_selected_horizon": list(by_horizon),
        "buy_observations": list(observations),
        "gate_results": gates,
        "decision": decision,
        "exit_timing_evidence": "MEASURED_BY_FL11_2A",
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(material)


def canonical_fast_paper_shadow_latency_proof(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowLatencyProofError(
            "latency proof document must be a mapping"
        )
    try:
        return json.dumps(
            dict(document),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof document is not canonicalizable"
        ) from exc


def _buy_observation(
    evidence: object,
    *,
    manifest: object,
    execution_policy: object,
    binding: object,
    source_root: Path,
    retry_root: Path,
    retry_index: Mapping[str, tuple[tuple[Path, Mapping[str, object]], ...]],
) -> dict[str, object]:
    horizon = evidence.decision.selected_horizon_ms
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise FastPaperShadowLatencyProofError(
            "latency proof BUY lacks positive selected horizon"
        )
    if evidence.as_of_unix_ms != evidence.feature_record.decision_observed_at_unix_ms:
        raise FastPaperShadowLatencyProofError(
            "latency proof BUY event timestamp conflicts with feature identity"
        )
    event_to_evaluation = evidence.evaluated_at_unix_ms - evidence.as_of_unix_ms
    if event_to_evaluation < 0:
        raise FastPaperShadowLatencyProofError(
            "latency proof BUY evaluation precedes event"
        )
    latency_ns = evidence.decision_latency_ns
    if (
        isinstance(latency_ns, bool)
        or not isinstance(latency_ns, int)
        or latency_ns < 0
    ):
        raise FastPaperShadowLatencyProofError(
            "latency proof BUY decision compute latency is invalid"
        )

    base = {
        "source_sequence": evidence.source_sequence,
        "source_event_id": evidence.source_event_id,
        "decision_evidence_fingerprint_sha256": (
            evidence.evidence_fingerprint_sha256
        ),
        "as_of_unix_ms": evidence.as_of_unix_ms,
        "evaluated_at_unix_ms": evidence.evaluated_at_unix_ms,
        "selected_horizon_ms": horizon,
        "event_to_evaluation_ms": float(event_to_evaluation),
        "decision_compute_ms": float(latency_ns) / 1_000_000.0,
    }

    source_path = source_root / f"{evidence.evidence_fingerprint_sha256}.json"
    if source_path.is_symlink():
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source must not be a symlink"
        )
    if not source_path.exists():
        return _unbooked(base, "MISSING_EXECUTION_SOURCE")
    if not source_path.is_file():
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source must be a regular file"
        )

    try:
        source_bindings = _probe_source_bindings(source_path)
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source binding probe failed"
        ) from exc
    if (
        source_bindings["decision_evidence_fingerprint_sha256"]
        != evidence.evidence_fingerprint_sha256
    ):
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source decision fingerprint mismatch"
        )
    pre_sequence = source_bindings["paper_checkpoint_sequence"]
    pre_checkpoint = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
        manifest,
        binding,
        sequence=pre_sequence,
    )
    pre_runtime = load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
        manifest,
        binding,
        sequence=pre_sequence,
    )
    if pre_checkpoint is None or pre_runtime is None:
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source references missing historical pre-state"
        )
    if (
        pre_checkpoint.payload_sha256
        != source_bindings["paper_checkpoint_payload_sha256"]
        or pre_runtime.state_fingerprint_sha256
        != source_bindings["shadow_runtime_state_fingerprint_sha256"]
    ):
        raise FastPaperShadowLatencyProofError(
            "latency proof execution source historical binding mismatch"
        )

    try:
        source_record = read_fast_paper_shadow_execution_input_source_record(
            manifest,
            execution_policy,
            evidence,
            source_root,
            paper_checkpoint_sequence=pre_checkpoint.sequence,
            paper_checkpoint_payload_sha256=pre_checkpoint.payload_sha256,
            shadow_runtime_state_fingerprint_sha256=(
                pre_runtime.state_fingerprint_sha256
            ),
        )
        transition = reconstruct_fast_paper_shadow_decision(
            manifest,
            execution_policy,
            binding,
            pre_checkpoint,
            pre_runtime,
            source_record.execution_input,
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof fresh BUY reconstruction failed"
        ) from exc

    successor = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
        manifest,
        binding,
        sequence=pre_checkpoint.sequence + 1,
    )
    successor_runtime = (
        load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
            manifest,
            binding,
            sequence=pre_checkpoint.sequence + 1,
        )
    )
    if successor is None or successor_runtime is None:
        return _unbooked(base, "MISSING_SUCCESSOR_COMMIT")
    try:
        _require_successor(
            transition,
            successor,
            successor_runtime,
            evidence,
            execution_policy,
        )
        new_entry = _single_new_ledger_entry(
            pre_checkpoint.state.ledger.entries,
            successor.state.ledger.entries,
            context="latency proof fresh BUY",
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof fresh BUY successor verification failed"
        ) from exc

    if (
        new_entry is not None
        and new_entry.ledger_reason_code
        is PaperLedgerReasonCode.POSITION_OPENED
    ):
        return _booked(
            base,
            status="BOOKED_IMMEDIATE",
            booked_at_unix_ms=new_entry.booked_at_unix_ms,
            retry_count=0,
        )

    if transition.next_pending_buy is None:
        return _unbooked(base, "TERMINAL_UNBOOKED")

    candidates = retry_index.get(evidence.source_event_id, ())
    if not candidates:
        return _unbooked(base, "PENDING_UNRESOLVED")

    retry_count = 0
    for path, bindings in candidates:
        retry_sequence = bindings["paper_checkpoint_sequence"]
        if retry_sequence < successor.sequence:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry source predates durable pending BUY"
            )
        retry_count += 1
        retry_pre = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=retry_sequence,
        )
        retry_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=retry_sequence,
            )
        )
        if retry_pre is None or retry_runtime is None:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry references missing historical pre-state"
            )
        if (
            retry_pre.payload_sha256
            != bindings["paper_checkpoint_payload_sha256"]
            or retry_runtime.state_fingerprint_sha256
            != bindings["shadow_runtime_state_fingerprint_sha256"]
        ):
            raise FastPaperShadowLatencyProofError(
                "latency proof retry historical binding mismatch"
            )
        expected_name = _retry_source_filename(
            retry_runtime.state_fingerprint_sha256,
            evidence.source_event_id,
        )
        if path.name != expected_name:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry source filename mismatch"
            )
        try:
            record = (
                read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint(
                    manifest,
                    binding,
                    execution_policy,
                    retry_pre,
                    retry_runtime,
                    retry_root,
                )
            )
            retry_transition = reconstruct_fast_paper_shadow_pending_buy_retry(
                manifest,
                execution_policy,
                binding,
                retry_pre,
                retry_runtime,
                record.retry_input,
            )
        except Exception as exc:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry reconstruction failed"
            ) from exc

        retry_successor = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=retry_pre.sequence + 1,
        )
        retry_successor_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=retry_pre.sequence + 1,
            )
        )
        if retry_successor is None or retry_successor_runtime is None:
            return _unbooked(
                base,
                "MISSING_RETRY_SUCCESSOR_COMMIT",
                retry_count=retry_count,
            )
        try:
            _require_retry_successor(
                retry_transition,
                retry_runtime,
                retry_successor,
                retry_successor_runtime,
                execution_policy,
            )
            retry_entry = _single_new_ledger_entry(
                retry_pre.state.ledger.entries,
                retry_successor.state.ledger.entries,
                context="latency proof retry BUY",
            )
        except Exception as exc:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry successor verification failed"
            ) from exc
        if (
            retry_entry is not None
            and retry_entry.ledger_reason_code
            is PaperLedgerReasonCode.POSITION_OPENED
        ):
            return _booked(
                base,
                status="BOOKED_RETRY",
                booked_at_unix_ms=retry_entry.booked_at_unix_ms,
                retry_count=retry_count,
            )
        if retry_transition.next_pending_buy is None:
            return _unbooked(
                base,
                "TERMINAL_UNBOOKED",
                retry_count=retry_count,
            )

    return _unbooked(
        base,
        "PENDING_UNRESOLVED",
        retry_count=retry_count,
    )


def _retry_index(
    root: Path,
) -> dict[str, tuple[tuple[Path, Mapping[str, object]], ...]]:
    grouped: dict[str, list[tuple[Path, Mapping[str, object]]]] = {}
    sequence_identity: set[tuple[str, int]] = set()
    for path in sorted(root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowLatencyProofError(
                "latency proof retry source must be a regular non-symlink file"
            )
        try:
            bindings = _probe_retry_source_bindings(path)
        except Exception as exc:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry source binding probe failed"
            ) from exc
        event_id = bindings["pending_source_event_id"]
        sequence = bindings["paper_checkpoint_sequence"]
        identity = (event_id, sequence)
        if identity in sequence_identity:
            raise FastPaperShadowLatencyProofError(
                "latency proof retry source checkpoint identity is duplicated"
            )
        sequence_identity.add(identity)
        grouped.setdefault(event_id, []).append((path, bindings))
    return {
        event_id: tuple(
            sorted(
                values,
                key=lambda item: (
                    item[1]["paper_checkpoint_sequence"],
                    item[0].name,
                ),
            )
        )
        for event_id, values in grouped.items()
    }


def _booked(
    base: Mapping[str, object],
    *,
    status: str,
    booked_at_unix_ms: int,
    retry_count: int,
) -> dict[str, object]:
    as_of = int(base["as_of_unix_ms"])
    evaluated = int(base["evaluated_at_unix_ms"])
    horizon = int(base["selected_horizon_ms"])
    if booked_at_unix_ms < evaluated:
        raise FastPaperShadowLatencyProofError(
            "latency proof booked entry predates decision evaluation"
        )
    event_to_booked = booked_at_unix_ms - as_of
    decision_to_booked = booked_at_unix_ms - evaluated
    ratio = float(event_to_booked) / float(horizon)
    return {
        **dict(base),
        "status": status,
        "retry_count": retry_count,
        "booked_at_unix_ms": booked_at_unix_ms,
        "decision_to_booked_entry_ms": float(decision_to_booked),
        "event_to_booked_entry_ms": float(event_to_booked),
        "event_to_booked_fraction_of_selected_horizon": ratio,
        "within_selected_horizon": event_to_booked <= horizon,
    }


def _unbooked(
    base: Mapping[str, object],
    status: str,
    *,
    retry_count: int = 0,
) -> dict[str, object]:
    return {
        **dict(base),
        "status": status,
        "retry_count": retry_count,
        "booked_at_unix_ms": None,
        "decision_to_booked_entry_ms": None,
        "event_to_booked_entry_ms": None,
        "event_to_booked_fraction_of_selected_horizon": None,
        "within_selected_horizon": None,
    }


def _summarize_observations(
    observations: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    booked = tuple(
        value for value in observations
        if value["booked_at_unix_ms"] is not None
    )
    horizons = {
        int(value["selected_horizon_ms"]) for value in observations
    }
    status_counts: dict[str, int] = {}
    for value in observations:
        status = str(value["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    event_to_evaluation = [
        float(value["event_to_evaluation_ms"]) for value in observations
    ]
    decision_compute = [
        float(value["decision_compute_ms"]) for value in observations
    ]
    decision_to_booked = [
        float(value["decision_to_booked_entry_ms"]) for value in booked
    ]
    event_to_booked = [
        float(value["event_to_booked_entry_ms"]) for value in booked
    ]
    horizon_fraction = [
        float(value["event_to_booked_fraction_of_selected_horizon"])
        for value in booked
    ]
    within = sum(
        1 for value in booked if value["within_selected_horizon"] is True
    )
    buy_count = len(observations)
    booked_count = len(booked)
    return {
        "buy_decision_count": buy_count,
        "booked_entry_count": booked_count,
        "unbooked_buy_count": buy_count - booked_count,
        "unbooked_buy_fraction": (
            None
            if buy_count == 0
            else float(buy_count - booked_count) / float(buy_count)
        ),
        "distinct_selected_horizon_count": len(horizons),
        "status_counts": {
            key: status_counts[key] for key in sorted(status_counts)
        },
        "event_to_evaluation_ms": _latency_summary(event_to_evaluation),
        "decision_compute_ms": _latency_summary(decision_compute),
        "decision_to_booked_entry_ms": _latency_summary(decision_to_booked),
        "event_to_booked_entry_ms": _latency_summary(event_to_booked),
        "event_to_booked_fraction_of_selected_horizon": _latency_summary(
            horizon_fraction
        ),
        "within_selected_horizon_count": within,
        "within_selected_horizon_rate": (
            None if booked_count == 0 else float(within) / float(booked_count)
        ),
    }


def _summarize_by_horizon(
    observations: tuple[Mapping[str, object], ...],
) -> tuple[dict[str, object], ...]:
    groups: dict[int, list[Mapping[str, object]]] = {}
    for value in observations:
        groups.setdefault(
            int(value["selected_horizon_ms"]),
            [],
        ).append(value)
    return tuple(
        {
            "selected_horizon_ms": horizon,
            **_summarize_observations(tuple(groups[horizon])),
        }
        for horizon in sorted(groups)
    )


def _reconcile_horizons(
    overall: Mapping[str, object],
    by_horizon: tuple[Mapping[str, object], ...],
) -> None:
    for name in (
        "buy_decision_count",
        "booked_entry_count",
        "unbooked_buy_count",
        "within_selected_horizon_count",
    ):
        if sum(int(value[name]) for value in by_horizon) != int(overall[name]):
            raise FastPaperShadowLatencyProofError(
                f"latency proof horizon {name} does not reconcile"
            )
    if len(by_horizon) != int(overall["distinct_selected_horizon_count"]):
        raise FastPaperShadowLatencyProofError(
            "latency proof distinct horizon count does not reconcile"
        )


def _gates(
    overall: Mapping[str, object],
    policy: FastPaperShadowLatencyProofPolicy,
) -> list[dict[str, object]]:
    ratio = overall["event_to_booked_fraction_of_selected_horizon"]
    p95 = ratio["p95"]
    p99 = ratio["p99"]
    return [
        _gate(
            "MIN_BUY_DECISION_COUNT",
            int(overall["buy_decision_count"]) >= policy.min_buy_decision_count,
            overall["buy_decision_count"],
            policy.min_buy_decision_count,
            ">=",
        ),
        _gate(
            "MIN_BOOKED_ENTRY_COUNT",
            int(overall["booked_entry_count"]) >= policy.min_booked_entry_count,
            overall["booked_entry_count"],
            policy.min_booked_entry_count,
            ">=",
        ),
        _gate(
            "MIN_DISTINCT_SELECTED_HORIZON_COUNT",
            int(overall["distinct_selected_horizon_count"])
            >= policy.min_distinct_selected_horizon_count,
            overall["distinct_selected_horizon_count"],
            policy.min_distinct_selected_horizon_count,
            ">=",
        ),
        _gate(
            "MAX_UNBOOKED_BUY_FRACTION",
            overall["unbooked_buy_fraction"] is not None
            and float(overall["unbooked_buy_fraction"])
            <= policy.max_unbooked_buy_fraction,
            overall["unbooked_buy_fraction"],
            policy.max_unbooked_buy_fraction,
            "<=",
        ),
        _gate(
            "MAX_P95_EVENT_TO_BOOKED_HORIZON_FRACTION",
            p95 is not None
            and float(p95)
            <= policy.max_p95_event_to_booked_horizon_fraction,
            p95,
            policy.max_p95_event_to_booked_horizon_fraction,
            "<=",
        ),
        _gate(
            "MAX_P99_EVENT_TO_BOOKED_HORIZON_FRACTION",
            p99 is not None
            and float(p99)
            <= policy.max_p99_event_to_booked_horizon_fraction,
            p99,
            policy.max_p99_event_to_booked_horizon_fraction,
            "<=",
        ),
    ]


def _gate(
    code: str,
    passed: bool,
    observed: object,
    threshold: object,
    comparator: str,
) -> dict[str, object]:
    return {
        "code": code,
        "status": "PASS" if passed else "FAIL",
        "observed_value": observed,
        "threshold_value": threshold,
        "comparator": comparator,
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(_finite_number("latency value", value) for value in values)
    return {
        "p50": _nearest_rank(ordered, 0.50),
        "p95": _nearest_rank(ordered, 0.95),
        "p99": _nearest_rank(ordered, 0.99),
        "max": ordered[-1],
    }


def _nearest_rank(values: list[float], percentile: float) -> float:
    rank = max(1, math.ceil(percentile * len(values)))
    return float(values[rank - 1])


def _directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowLatencyProofError(
            f"latency proof {label} directory must be regular and non-symlink"
        )
    return root


def _window(since: object, until: object) -> tuple[int, int]:
    if (
        isinstance(since, bool)
        or not isinstance(since, int)
        or since < 0
        or isinstance(until, bool)
        or not isinstance(until, int)
        or until <= since
    ):
        raise FastPaperShadowLatencyProofError(
            "latency proof window is invalid"
        )
    return since, until


def _finite_number(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _finalize(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    return {
        **document,
        "report_fingerprint_sha256": hashlib.sha256(
            canonical_fast_paper_shadow_latency_proof(document).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def _read_policy(path: str | Path) -> FastPaperShadowLatencyProofPolicy:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise FastPaperShadowLatencyProofError(
            "latency proof policy must be a regular non-symlink file"
        )
    try:
        return decode_fast_paper_shadow_latency_proof_policy(
            source.read_text(encoding="utf-8").strip()
        )
    except Exception as exc:
        raise FastPaperShadowLatencyProofError(
            "latency proof policy is malformed"
        ) from exc


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-latency-proof"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--execution-policy-path", required=True)
    parser.add_argument("--ledger-database-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision-evidence-directory", required=True)
    parser.add_argument("--execution-source-directory", required=True)
    parser.add_argument("--pending-buy-retry-source-directory", required=True)
    parser.add_argument("--sample-proof-path", required=True)
    parser.add_argument("--latency-policy-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--since-unix-ms", type=int, required=True)
    parser.add_argument("--until-unix-ms", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_latency_proof(
            manifest_path=args.manifest_path,
            execution_policy_path=args.execution_policy_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=args.decision_evidence_directory,
            execution_source_directory=args.execution_source_directory,
            pending_buy_retry_source_directory=(
                args.pending_buy_retry_source_directory
            ),
            sample_proof_path=args.sample_proof_path,
            latency_policy=_read_policy(args.latency_policy_path),
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
        )
    except (FastPaperShadowLatencyProofError, ValueError) as exc:
        print(
            canonical_fast_paper_shadow_latency_proof(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_latency_proof_failure"
                    ),
                    "schema_version": FAST_PAPER_SHADOW_LATENCY_PROOF_SCHEMA_VERSION,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "promotion_authority": "NOT_GRANTED",
                    "production_paper_cutover": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(canonical_fast_paper_shadow_latency_proof(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
