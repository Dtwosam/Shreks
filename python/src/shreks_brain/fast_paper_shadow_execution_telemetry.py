from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .fast_paper_runtime.shadow_execution_input import (
    FastPaperShadowExecutionPolicy,
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_execution_source import (
    read_fast_paper_shadow_execution_input_source_record,
)
from .fast_paper_runtime.shadow_executor import (
    reconstruct_fast_paper_shadow_decision,
    reconstruct_fast_paper_shadow_pending_buy_retry,
)
from .fast_paper_runtime.shadow_pending_buy_retry_source import (
    read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint,
)
from .fast_paper_runtime.shadow_ledger import (
    FastPaperShadowLedgerBinding,
    build_fast_paper_shadow_ledger_binding,
    load_fast_paper_shadow_ledger_checkpoint_by_sequence,
)
from .fast_paper_runtime.shadow_runtime_state import (
    load_fast_paper_shadow_runtime_state_by_checkpoint_sequence,
)


_SCHEMA_NAME = "shreks.fast_paper_shadow_execution_telemetry"
_SCHEMA_VERSION = 2
_MAX_WINDOW_MS = 86_400_000
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = ("BUY", "SKIP", "HOLD", "REDUCE", "SELL")


class FastPaperShadowExecutionTelemetryError(RuntimeError):
    pass


def collect_fast_paper_shadow_execution_telemetry(
    *,
    manifest_path: str | Path,
    execution_policy_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path | None = None,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    _validate_window(since_unix_ms, until_unix_ms)
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry run id must be non-empty"
        )
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
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry authority authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry release identity mismatch"
        )
    return summarize_fast_paper_shadow_execution_telemetry(
        manifest=manifest,
        execution_policy=execution_policy,
        binding=binding,
        decision_evidence_directory=decision_evidence_directory,
        execution_source_directory=execution_source_directory,
        pending_buy_retry_source_directory=pending_buy_retry_source_directory,
        expected_release_sha=expected_sha,
        since_unix_ms=since_unix_ms,
        until_unix_ms=until_unix_ms,
    )


def summarize_fast_paper_shadow_execution_telemetry(
    *,
    manifest: object,
    execution_policy: object,
    binding: object,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path | None = None,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    expected_sha = _validate_release_sha(expected_release_sha)
    provenance = _provenance(
        manifest,
        execution_policy,
        binding,
        expected_release_sha=expected_sha,
    )
    decision_root = _directory(
        decision_evidence_directory,
        "decision evidence",
    )
    source_root = _directory(
        execution_source_directory,
        "execution source",
    )

    decisions = []
    for path in sorted(decision_root.glob("shadow-*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry decision evidence path is not a regular file"
            )
        try:
            evidence = read_fast_paper_shadow_decision_evidence(path)
        except Exception as exc:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry decision evidence authentication failed"
            ) from exc
        _require_decision_binding(manifest, evidence)
        if since <= evidence.evaluated_at_unix_ms < until:
            decisions.append(evidence)

    decisions.sort(
        key=lambda value: (
            value.evaluated_at_unix_ms,
            value.source_sequence,
            value.evidence_fingerprint_sha256,
        )
    )
    fingerprints = tuple(
        value.evidence_fingerprint_sha256 for value in decisions
    )
    if len(fingerprints) != len(set(fingerprints)):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry decision evidence contains duplicate fingerprint"
        )

    action_counts = {action: 0 for action in _ACTIONS}
    outcome_counts: dict[str, int] = {}
    commit_latencies: list[float] = []
    booked_latencies: list[float] = []
    expected_price_costs: list[float] = []
    realized_price_costs: list[float] = []
    price_cost_deltas: list[float] = []
    explicit_cost_bps_values: list[float] = []
    total_burden_bps_values: list[float] = []
    missing_source = 0
    missing_successor = 0
    joined = 0
    max_entry_price_aborts = 0

    for evidence in decisions:
        action = evidence.decision.action
        if action not in action_counts:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry decision action is unsupported"
            )
        action_counts[action] += 1

        source_path = source_root / (
            f"{evidence.evidence_fingerprint_sha256}.json"
        )
        if source_path.is_symlink():
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry source path must not be a symlink"
            )
        if not source_path.exists():
            missing_source += 1
            continue
        if not source_path.is_file():
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry source path is not a regular file"
            )

        source_bindings = _probe_source_bindings(source_path)
        if (
            source_bindings["decision_evidence_fingerprint_sha256"]
            != evidence.evidence_fingerprint_sha256
        ):
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry source decision fingerprint mismatch"
            )
        pre_sequence = source_bindings["paper_checkpoint_sequence"]
        pre_checkpoint = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=pre_sequence,
        )
        pre_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=pre_sequence,
            )
        )
        if pre_checkpoint is None or pre_runtime is None:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry source references missing historical pre-state"
            )
        if (
            pre_checkpoint.payload_sha256
            != source_bindings["paper_checkpoint_payload_sha256"]
            or pre_runtime.state_fingerprint_sha256
            != source_bindings[
                "shadow_runtime_state_fingerprint_sha256"
            ]
        ):
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry source historical binding mismatch"
            )

        try:
            source_record = read_fast_paper_shadow_execution_input_source_record(
                manifest,
                execution_policy,
                evidence,
                source_root,
                paper_checkpoint_sequence=pre_checkpoint.sequence,
                paper_checkpoint_payload_sha256=(
                    pre_checkpoint.payload_sha256
                ),
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
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry historical reconstruction failed"
            ) from exc

        successor_sequence = pre_checkpoint.sequence + 1
        successor = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=successor_sequence,
        )
        successor_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=successor_sequence,
            )
        )
        if successor is None or successor_runtime is None:
            missing_successor += 1
            continue
        _require_successor(
            transition,
            successor,
            successor_runtime,
            evidence,
            execution_policy,
        )
        joined += 1

        commit_latency = (
            successor.created_at_unix_ms
            - evidence.evaluated_at_unix_ms
        )
        if commit_latency < 0:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry commit precedes decision evaluation"
            )
        commit_latencies.append(float(commit_latency))

        outcome, execution = _transition_outcome(
            transition,
            action=action,
        )
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        if outcome == "ABORTED_PRICE_ABOVE_MAXIMUM":
            max_entry_price_aborts += 1

        pre_entries = pre_checkpoint.state.ledger.entries
        post_entries = successor.state.ledger.entries
        if post_entries[: len(pre_entries)] != pre_entries:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry successor ledger is not an append-only continuation"
            )
        new_entries = post_entries[len(pre_entries) :]
        if len(new_entries) > 1:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry fresh transition appended multiple terminal ledger entries"
            )
        if new_entries:
            booked_latency = (
                new_entries[0].booked_at_unix_ms
                - evidence.evaluated_at_unix_ms
            )
            if booked_latency < 0:
                raise FastPaperShadowExecutionTelemetryError(
                    "shadow execution telemetry booked entry predates decision evaluation"
                )
            booked_latencies.append(float(booked_latency))

        if execution is None or execution.fill is None:
            continue
        fill = execution.fill
        expected = _expected_selected_price_cost_bps(evidence)
        if expected is None:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry filled action lacks selected price-cost evidence"
            )
        realized = _finite(
            "realized price cost bps",
            fill.signed_slippage_bps,
        )
        explicit = _finite(
            "realized explicit cost bps",
            fill.explicit_cost_usd
            / fill.filled_notional_usd
            * 10_000.0,
            non_negative=True,
        )
        expected_price_costs.append(expected)
        realized_price_costs.append(realized)
        price_cost_deltas.append(realized - expected)
        explicit_cost_bps_values.append(explicit)
        total_burden_bps_values.append(realized + explicit)

    retry_metrics = _pending_buy_retry_metrics(
        manifest=manifest,
        execution_policy=execution_policy,
        binding=binding,
        pending_buy_retry_source_directory=(
            pending_buy_retry_source_directory
        ),
        since_unix_ms=since,
        until_unix_ms=until,
    )

    material = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        **provenance,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        "decision_count": len(decisions),
        "joined_execution_count": joined,
        "missing_execution_source_count": missing_source,
        "missing_successor_commit_count": missing_successor,
        "action_counts": action_counts,
        "outcome_counts": {
            key: outcome_counts[key] for key in sorted(outcome_counts)
        },
        "max_entry_price_abort_count": max_entry_price_aborts,
        "decision_to_commit_latency_ms": _summary(commit_latencies),
        "decision_to_booked_entry_latency_ms": _summary(
            booked_latencies
        ),
        "expected_selected_price_cost_bps": _summary(
            expected_price_costs
        ),
        "realized_price_cost_bps": _summary(realized_price_costs),
        "realized_minus_expected_price_cost_bps": _summary(
            price_cost_deltas
        ),
        "realized_explicit_cost_bps": _summary(
            explicit_cost_bps_values
        ),
        "realized_total_execution_burden_bps": _summary(
            total_burden_bps_values
        ),
        **retry_metrics,
    }
    return _finalize(material)


def _pending_buy_retry_metrics(
    *,
    manifest: object,
    execution_policy: object,
    binding: object,
    pending_buy_retry_source_directory: str | Path | None,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    empty = {
        "pending_buy_retry_joined": (
            pending_buy_retry_source_directory is not None
        ),
        "pending_buy_retry_count": 0,
        "joined_pending_buy_retry_count": 0,
        "missing_retry_successor_commit_count": 0,
        "pending_buy_retry_outcome_counts": {},
        "pending_buy_retry_terminal_count": 0,
        "pending_buy_retry_deferred_count": 0,
        "pending_buy_retry_max_entry_price_abort_count": 0,
        "retry_to_commit_latency_ms": _summary([]),
        "retry_to_booked_entry_latency_ms": _summary([]),
        "retry_quote_price_cost_bps": _summary([]),
        "retry_realized_price_cost_bps": _summary([]),
        "retry_realized_minus_quote_price_cost_bps": _summary([]),
        "retry_realized_explicit_cost_bps": _summary([]),
        "retry_realized_total_execution_burden_bps": _summary([]),
    }
    if pending_buy_retry_source_directory is None:
        return empty

    root = _directory(
        pending_buy_retry_source_directory,
        "pending BUY retry source",
    )
    records: list[tuple[object, object, object]] = []
    seen_fingerprints: set[str] = set()

    for path in sorted(root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source path is not a regular file"
            )
        bindings = _probe_retry_source_bindings(path)
        pre_sequence = bindings["paper_checkpoint_sequence"]
        pre_checkpoint = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=pre_sequence,
        )
        pre_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=pre_sequence,
            )
        )
        if pre_checkpoint is None or pre_runtime is None:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source references missing historical pre-state"
            )
        if (
            pre_checkpoint.payload_sha256
            != bindings["paper_checkpoint_payload_sha256"]
            or pre_runtime.state_fingerprint_sha256
            != bindings["shadow_runtime_state_fingerprint_sha256"]
        ):
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry historical binding mismatch"
            )
        expected_name = _retry_source_filename(
            pre_runtime.state_fingerprint_sha256,
            bindings["pending_source_event_id"],
        )
        if path.name != expected_name:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source filename mismatch"
            )
        try:
            record = (
                read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint(
                    manifest,
                    binding,
                    execution_policy,
                    pre_checkpoint,
                    pre_runtime,
                    root,
                )
            )
        except Exception as exc:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source authentication failed"
            ) from exc
        if (
            record.record_fingerprint_sha256
            != bindings["record_fingerprint_sha256"]
        ):
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source fingerprint mismatch"
            )
        if record.record_fingerprint_sha256 in seen_fingerprints:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry source fingerprint is duplicated"
            )
        seen_fingerprints.add(record.record_fingerprint_sha256)
        if (
            since_unix_ms
            <= record.retry_input.evaluated_at_unix_ms
            < until_unix_ms
        ):
            records.append((record, pre_checkpoint, pre_runtime))

    outcome_counts: dict[str, int] = {}
    commit_latencies: list[float] = []
    booked_latencies: list[float] = []
    quote_price_costs: list[float] = []
    realized_price_costs: list[float] = []
    price_cost_deltas: list[float] = []
    explicit_costs: list[float] = []
    total_burdens: list[float] = []
    joined = 0
    missing_successor = 0
    deferred = 0
    terminal = 0
    max_entry_price_aborts = 0

    for record, pre_checkpoint, pre_runtime in records:
        try:
            transition = reconstruct_fast_paper_shadow_pending_buy_retry(
                manifest,
                execution_policy,
                binding,
                pre_checkpoint,
                pre_runtime,
                record.retry_input,
            )
        except Exception as exc:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry pending BUY retry reconstruction failed"
            ) from exc

        successor_sequence = pre_checkpoint.sequence + 1
        successor = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
            manifest,
            binding,
            sequence=successor_sequence,
        )
        successor_runtime = (
            load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=successor_sequence,
            )
        )
        if successor is None or successor_runtime is None:
            missing_successor += 1
            continue

        _require_retry_successor(
            transition,
            pre_runtime,
            successor,
            successor_runtime,
            execution_policy,
        )
        joined += 1

        commit_latency = (
            successor.created_at_unix_ms
            - record.retry_input.evaluated_at_unix_ms
        )
        if commit_latency < 0:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry retry commit precedes retry evaluation"
            )
        commit_latencies.append(float(commit_latency))

        result = transition.buy_result
        if result is None or transition.position_result is not None:
            raise FastPaperShadowExecutionTelemetryError(
                "shadow execution telemetry retry transition result shape is invalid"
            )
        outcome = result.outcome.value
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        if outcome == "DEFERRED":
            deferred += 1
        else:
            terminal += 1
        if outcome == "ABORTED_PRICE_ABOVE_MAXIMUM":
            max_entry_price_aborts += 1

        new_entry = _single_new_ledger_entry(
            pre_checkpoint.state.ledger.entries,
            successor.state.ledger.entries,
            context="pending BUY retry",
        )
        if new_entry is not None:
            booked_latency = (
                new_entry.booked_at_unix_ms
                - record.retry_input.evaluated_at_unix_ms
            )
            if booked_latency < 0:
                raise FastPaperShadowExecutionTelemetryError(
                    "shadow execution telemetry retry ledger entry precedes retry evaluation"
                )
            booked_latencies.append(float(booked_latency))

        quote_cost = _retry_quote_price_cost_bps(record.retry_input.quote)
        if quote_cost is not None:
            quote_price_costs.append(quote_cost)

        execution = result.execution
        fill = None if execution is None else execution.fill
        if fill is not None:
            realized = _finite(
                "retry realized price cost",
                fill.signed_slippage_bps,
            )
            if quote_cost is None:
                raise FastPaperShadowExecutionTelemetryError(
                    "shadow execution telemetry filled retry lacks executable quote cost"
                )
            realized_price_costs.append(realized)
            price_cost_deltas.append(realized - quote_cost)
            filled_notional = _finite(
                "retry filled notional",
                fill.filled_notional_usd,
                non_negative=True,
            )
            if filled_notional <= 0.0:
                raise FastPaperShadowExecutionTelemetryError(
                    "shadow execution telemetry retry fill notional is not positive"
                )
            explicit = (
                _finite(
                    "retry explicit cost",
                    fill.explicit_cost_usd,
                    non_negative=True,
                )
                / filled_notional
                * 10_000.0
            )
            explicit_costs.append(explicit)
            total_burdens.append(realized + explicit)

    return {
        "pending_buy_retry_joined": True,
        "pending_buy_retry_count": len(records),
        "joined_pending_buy_retry_count": joined,
        "missing_retry_successor_commit_count": missing_successor,
        "pending_buy_retry_outcome_counts": {
            key: outcome_counts[key] for key in sorted(outcome_counts)
        },
        "pending_buy_retry_terminal_count": terminal,
        "pending_buy_retry_deferred_count": deferred,
        "pending_buy_retry_max_entry_price_abort_count": (
            max_entry_price_aborts
        ),
        "retry_to_commit_latency_ms": _summary(commit_latencies),
        "retry_to_booked_entry_latency_ms": _summary(booked_latencies),
        "retry_quote_price_cost_bps": _summary(quote_price_costs),
        "retry_realized_price_cost_bps": _summary(realized_price_costs),
        "retry_realized_minus_quote_price_cost_bps": _summary(
            price_cost_deltas
        ),
        "retry_realized_explicit_cost_bps": _summary(explicit_costs),
        "retry_realized_total_execution_burden_bps": _summary(
            total_burdens
        ),
    }


def _probe_retry_source_bindings(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry pending BUY retry source must have one trailing newline"
        )
    try:
        document = json.loads(
            payload[:-1].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry pending BUY retry source JSON is malformed"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry pending BUY retry source must be an object"
        )
    return {
        "paper_checkpoint_sequence": _non_negative_int(
            "retry source checkpoint sequence",
            document.get("paper_checkpoint_sequence"),
        ),
        "paper_checkpoint_payload_sha256": _sha256(
            "retry source checkpoint fingerprint",
            document.get("paper_checkpoint_payload_sha256"),
        ),
        "shadow_runtime_state_fingerprint_sha256": _sha256(
            "retry source runtime-state fingerprint",
            document.get("shadow_runtime_state_fingerprint_sha256"),
        ),
        "pending_source_event_id": _text(
            "retry pending source event id",
            document.get("pending_source_event_id"),
        ),
        "record_fingerprint_sha256": _sha256(
            "retry source record fingerprint",
            document.get("record_fingerprint_sha256"),
        ),
    }


def _retry_source_filename(
    runtime_state_fingerprint_sha256: str,
    pending_source_event_id: str,
) -> str:
    payload = json.dumps(
        {
            "pending_source_event_id": pending_source_event_id,
            "runtime_state_fingerprint_sha256": (
                runtime_state_fingerprint_sha256
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"{hashlib.sha256(payload).hexdigest()}.json"


def _require_retry_successor(
    transition: object,
    pre_runtime: object,
    successor: object,
    successor_runtime: object,
    execution_policy: object,
) -> None:
    if successor.state != transition.next_paper_state:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry retry successor PAPER state differs from reconstructed transition"
        )
    if (
        successor_runtime.paper_checkpoint_sequence
        != successor.sequence
        or successor_runtime.paper_checkpoint_payload_sha256
        != successor.payload_sha256
    ):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry retry successor checkpoint/runtime pair is torn"
        )
    if (
        successor_runtime.market_positions
        != transition.next_market_positions
        or successor_runtime.pending_buy
        != transition.next_pending_buy
        or successor_runtime.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry retry successor runtime differs from reconstruction"
        )
    actual_cursor = (
        successor_runtime.last_processed_source_sequence,
        successor_runtime.last_processed_source_event_id,
        successor_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    expected_cursor = (
        pre_runtime.last_processed_source_sequence,
        pre_runtime.last_processed_source_event_id,
        pre_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    if actual_cursor != expected_cursor:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry pending BUY retry changed learned decision cursor"
        )


def _single_new_ledger_entry(
    before: tuple[object, ...],
    after: tuple[object, ...],
    *,
    context: str,
) -> object | None:
    if after == before:
        return None
    if len(after) != len(before) + 1 or after[:-1] != before:
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {context} ledger delta is not exactly zero or one appended entry"
        )
    return after[-1]


def _retry_quote_price_cost_bps(quote: object) -> float | None:
    if getattr(quote, "state", None) != "EXECUTABLE":
        return None
    reference = _finite(
        "retry quote reference price",
        getattr(quote, "reference_price_quote", None),
        non_negative=True,
    )
    execution = _finite(
        "retry quote execution price",
        getattr(quote, "execution_price_quote", None),
        non_negative=True,
    )
    if reference <= 0.0 or execution <= 0.0:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry retry quote prices must be positive"
        )
    return max(0.0, execution / reference - 1.0) * 10_000.0


def canonical_fast_paper_shadow_execution_telemetry(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry document must be a mapping"
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
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry document is not canonicalizable"
        ) from exc


def _probe_source_bindings(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry source record must have one trailing newline"
        )
    try:
        document = json.loads(
            payload[:-1].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry source record JSON is malformed"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry source record must be an object"
        )
    decision_fingerprint = _sha256(
        "source decision fingerprint",
        document.get("decision_evidence_fingerprint_sha256"),
    )
    checkpoint_sequence = _non_negative_int(
        "source checkpoint sequence",
        document.get("paper_checkpoint_sequence"),
    )
    checkpoint_sha = _sha256(
        "source checkpoint fingerprint",
        document.get("paper_checkpoint_payload_sha256"),
    )
    runtime_sha = _sha256(
        "source runtime-state fingerprint",
        document.get("shadow_runtime_state_fingerprint_sha256"),
    )
    return {
        "decision_evidence_fingerprint_sha256": decision_fingerprint,
        "paper_checkpoint_sequence": checkpoint_sequence,
        "paper_checkpoint_payload_sha256": checkpoint_sha,
        "shadow_runtime_state_fingerprint_sha256": runtime_sha,
    }


def _require_successor(
    transition: object,
    successor: object,
    successor_runtime: object,
    evidence: FastPaperShadowDecisionEvidence,
    execution_policy: object,
) -> None:
    if successor.state != transition.next_paper_state:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry successor PAPER state differs from reconstructed transition"
        )
    if (
        successor_runtime.paper_checkpoint_sequence
        != successor.sequence
        or successor_runtime.paper_checkpoint_payload_sha256
        != successor.payload_sha256
    ):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry successor checkpoint/runtime pair is torn"
        )
    if (
        successor_runtime.market_positions
        != transition.next_market_positions
        or successor_runtime.pending_buy
        != transition.next_pending_buy
        or successor_runtime.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry successor runtime state differs from reconstructed transition"
        )
    identity = (
        successor_runtime.last_processed_source_sequence,
        successor_runtime.last_processed_source_event_id,
        successor_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    expected = (
        evidence.source_sequence,
        evidence.source_event_id,
        evidence.evidence_fingerprint_sha256,
    )
    if identity != expected:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry successor processed identity mismatch"
        )


def _transition_outcome(
    transition: object,
    *,
    action: str,
) -> tuple[str, object | None]:
    buy_result = transition.buy_result
    position_result = transition.position_result
    if action == "SKIP":
        if buy_result is not None or position_result is not None:
            raise FastPaperShadowExecutionTelemetryError(
                "SKIP transition unexpectedly carries execution result"
            )
        return "SKIP", None
    if action == "BUY":
        if buy_result is None or position_result is not None:
            raise FastPaperShadowExecutionTelemetryError(
                "BUY transition result shape is invalid"
            )
        return buy_result.outcome.value, buy_result.execution
    if position_result is None or buy_result is not None:
        raise FastPaperShadowExecutionTelemetryError(
            "OPEN-position transition result shape is invalid"
        )
    return position_result.outcome.value, position_result.execution


def _expected_selected_price_cost_bps(
    evidence: FastPaperShadowDecisionEvidence,
) -> float | None:
    action = evidence.decision.action
    if action == "BUY":
        return _optional_non_negative_finite(
            "BUY selected price cost",
            evidence.entry_execution_cost_bps,
        )
    if action == "SELL":
        return _optional_non_negative_finite(
            "SELL selected price cost",
            evidence.exit_execution_cost_bps,
        )
    if action == "REDUCE":
        target = evidence.decision.target_exposure_fraction
        matches = tuple(
            item.execution_cost_bps
            for item in evidence.constraints.reduce_execution_costs
            if math.isclose(
                item.target_exposure_fraction,
                target,
                rel_tol=1e-12,
                abs_tol=1e-15,
            )
        )
        if len(matches) != 1:
            raise FastPaperShadowExecutionTelemetryError(
                "REDUCE selected price cost is not uniquely bound to target exposure"
            )
        return _finite(
            "REDUCE selected price cost",
            matches[0],
            non_negative=True,
        )
    return None


def _require_decision_binding(
    manifest: object,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    expected = (
        manifest.release_source_sha,
        manifest.manifest_fingerprint_sha256,
        manifest.champion_version,
        manifest.champion_fingerprint_sha256,
        manifest.action_policy.version,
    )
    actual = (
        evidence.release_source_sha,
        evidence.manifest_fingerprint_sha256,
        evidence.champion_version,
        evidence.champion_fingerprint_sha256,
        evidence.action_policy_version,
    )
    if actual != expected:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry decision evidence does not match runtime manifest"
        )


def _provenance(
    manifest: object,
    execution_policy: object,
    binding: object,
    *,
    expected_release_sha: str,
) -> dict[str, object]:
    if manifest.release_source_sha != expected_release_sha:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry release identity mismatch"
        )
    return {
        "release_source_sha": expected_release_sha,
        "manifest_fingerprint_sha256": _sha256(
            "manifest fingerprint",
            manifest.manifest_fingerprint_sha256,
        ),
        "champion_version": _text(
            "champion version",
            manifest.champion_version,
        ),
        "champion_fingerprint_sha256": _sha256(
            "champion fingerprint",
            manifest.champion_fingerprint_sha256,
        ),
        "action_policy_version": _positive_int(
            "action policy version",
            manifest.action_policy.version,
        ),
        "execution_policy_fingerprint_sha256": _sha256(
            "execution policy fingerprint",
            execution_policy.policy_fingerprint_sha256,
        ),
        "run_id": _text("run id", binding.run_id),
        "binding_fingerprint_sha256": _sha256(
            "binding fingerprint",
            binding.binding_fingerprint_sha256,
        ),
    }


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "p50": None, "p95": None}
    ordered = sorted(values)
    return {
        "mean": math.fsum(ordered) / len(ordered),
        "p50": _nearest_rank(ordered, 0.50),
        "p95": _nearest_rank(ordered, 0.95),
    }


def _nearest_rank(values: list[float], percentile: float) -> float:
    rank = max(1, math.ceil(percentile * len(values)))
    return float(values[rank - 1])


def _directory(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_dir():
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {label} directory must be an existing regular non-symlink directory"
        )
    return path.resolve(strict=True)


def _finalize(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    return {
        **document,
        "telemetry_fingerprint_sha256": hashlib.sha256(
            canonical_fast_paper_shadow_execution_telemetry(
                document
            ).encode("utf-8")
        ).hexdigest(),
    }


def _validate_window(
    since_unix_ms: object,
    until_unix_ms: object,
) -> tuple[int, int]:
    if (
        isinstance(since_unix_ms, bool)
        or not isinstance(since_unix_ms, int)
        or since_unix_ms < 0
        or isinstance(until_unix_ms, bool)
        or not isinstance(until_unix_ms, int)
        or until_unix_ms < 0
        or since_unix_ms >= until_unix_ms
        or until_unix_ms - since_unix_ms > _MAX_WINDOW_MS
    ):
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry window is invalid or exceeds 24 hours"
        )
    return since_unix_ms, until_unix_ms


def _validate_release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowExecutionTelemetryError(
            "shadow execution telemetry expected release SHA is invalid"
        )
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} is invalid"
        )
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} is invalid"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} is invalid"
        )
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} is invalid"
        )
    return value


def _finite(
    name: str,
    value: object,
    *,
    non_negative: bool = False,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} is invalid"
        )
    result = float(value)
    if non_negative and result < 0.0:
        raise FastPaperShadowExecutionTelemetryError(
            f"shadow execution telemetry {name} must be non-negative"
        )
    return result


def _optional_non_negative_finite(
    name: str,
    value: object,
) -> float | None:
    if value is None:
        return None
    return _finite(name, value, non_negative=True)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-execution-telemetry"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("--manifest-path", required=True)
    summarize.add_argument("--execution-policy-path", required=True)
    summarize.add_argument("--ledger-database-path", required=True)
    summarize.add_argument("--run-id", required=True)
    summarize.add_argument("--decision-evidence-directory", required=True)
    summarize.add_argument("--execution-source-directory", required=True)
    summarize.add_argument("--pending-buy-retry-source-directory")
    summarize.add_argument("--expected-release-sha", required=True)
    summarize.add_argument("--since-unix-ms", type=int, required=True)
    summarize.add_argument("--until-unix-ms", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_execution_telemetry(
            manifest_path=args.manifest_path,
            execution_policy_path=args.execution_policy_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=(
                args.decision_evidence_directory
            ),
            execution_source_directory=args.execution_source_directory,
            pending_buy_retry_source_directory=(
                args.pending_buy_retry_source_directory
            ),
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
        )
    except FastPaperShadowExecutionTelemetryError as exc:
        failure = {
            "schema_name": (
                "shreks.fast_paper_shadow_execution_telemetry_failure"
            ),
            "schema_version": _SCHEMA_VERSION,
            "state": "FAILED",
            "error_type": type(exc).__name__,
            "paper_cutover_authority": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        print(
            canonical_fast_paper_shadow_execution_telemetry(
                failure
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(
        canonical_fast_paper_shadow_execution_telemetry(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
