from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from shreks_brain.paper import (
    PaperExecutionState,
    PaperRiskAccountingFacts,
    derive_paper_risk_accounting_facts,
)
from shreks_brain.risk import TradeSide

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    load_fast_paper_shadow_ledger_checkpoint_at_or_before,
)


_SCHEMA_NAME = "shreks.fast_paper_shadow_outcome_telemetry"
_SCHEMA_VERSION = 1
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_WINDOW_MS = 86_400_000
_EXECUTION_STATES = ("FAILED", "PARTIAL", "FILLED")
_SIDES = ("BUY", "SELL")


class FastPaperShadowOutcomeTelemetryError(RuntimeError):
    pass


def collect_fast_paper_shadow_outcome_telemetry(
    *,
    manifest_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry run id must be non-empty"
        )

    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry runtime manifest authentication failed"
        ) from exc

    if manifest.release_source_sha != expected_sha:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry release identity mismatch"
        )

    try:
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=run_id,
            database_path=ledger_database_path,
        )
        checkpoint = (
            load_fast_paper_shadow_ledger_checkpoint_at_or_before(
                manifest,
                binding,
                as_of_unix_ms=until - 1,
            )
        )
    except Exception as exc:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry ledger authentication failed"
        ) from exc

    return summarize_fast_paper_shadow_outcome_telemetry(
        checkpoint,
        manifest=manifest,
        binding=binding,
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )


def summarize_fast_paper_shadow_outcome_telemetry(
    checkpoint: object | None,
    *,
    manifest: object,
    binding: object,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    provenance = _provenance(
        manifest,
        binding,
        expected_release_sha=expected_sha,
    )

    if checkpoint is None:
        material = {
            "schema_name": _SCHEMA_NAME,
            "schema_version": _SCHEMA_VERSION,
            **provenance,
            "window_since_unix_ms": since,
            "window_until_unix_ms": until,
            "window_duration_ms": until - since,
            **_empty_metrics(),
        }
        return _finalize(material)

    if getattr(checkpoint, "run_id", None) != provenance["run_id"]:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry checkpoint run identity mismatch"
        )
    checkpoint_sequence = _non_negative_int(
        "checkpoint sequence",
        getattr(checkpoint, "sequence", None),
    )
    checkpoint_payload = getattr(checkpoint, "payload_sha256", None)
    if (
        not isinstance(checkpoint_payload, str)
        or _SHA256_RE.fullmatch(checkpoint_payload) is None
    ):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry checkpoint payload fingerprint is invalid"
        )
    state_as_of = _non_negative_int(
        "checkpoint state timestamp",
        getattr(checkpoint, "state_as_of_unix_ms", None),
    )
    created_at = _non_negative_int(
        "checkpoint creation timestamp",
        getattr(checkpoint, "created_at_unix_ms", None),
    )
    if state_as_of >= until:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry checkpoint exceeds requested window"
        )
    if created_at < state_as_of:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry checkpoint creation precedes state"
        )

    state = getattr(checkpoint, "state", None)
    ledger = getattr(state, "ledger", None)
    if ledger is None:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry checkpoint ledger is missing"
        )
    entries = getattr(ledger, "entries", None)
    positions = getattr(ledger, "positions", None)
    processed = getattr(ledger, "processed_intent_keys", None)
    if not isinstance(entries, tuple):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry ledger entries must be a tuple"
        )
    if not isinstance(positions, tuple):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry ledger positions must be a tuple"
        )
    if not isinstance(processed, frozenset):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry processed intents must be a frozenset"
        )

    selected = tuple(
        entry
        for entry in entries
        if since
        <= _non_negative_int(
            "ledger entry booked timestamp",
            getattr(entry, "booked_at_unix_ms", None),
        )
        < until
    )
    metrics = _window_metrics(selected)

    try:
        facts = derive_paper_risk_accounting_facts(
            ledger,
            day_started_at_unix_ms=since,
        )
    except Exception as exc:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry risk accounting facts failed"
        ) from exc
    _require_risk_facts(facts)

    if not math.isclose(
        float(facts.daily_realized_pnl_usd),
        float(metrics["realized_pnl_delta_usd"]),
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry daily realized PnL does not match window ledger entries"
        )

    material = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        **provenance,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        **metrics,
        "checkpoint_sequence": checkpoint_sequence,
        "checkpoint_payload_sha256": checkpoint_payload,
        "checkpoint_state_as_of_unix_ms": state_as_of,
        "checkpoint_created_at_unix_ms": created_at,
        "starting_cash_usd": _finite_metric(
            "starting cash",
            getattr(ledger, "starting_cash_usd", None),
            non_negative=True,
        ),
        "cash_balance_usd": _finite_metric(
            "cash balance",
            getattr(ledger, "cash_balance_usd", None),
            non_negative=True,
        ),
        "realized_pnl_usd": _finite_metric(
            "realized PnL",
            getattr(ledger, "realized_pnl_usd", None),
        ),
        "unrealized_pnl_usd": _optional_finite_metric(
            "unrealized PnL",
            getattr(ledger, "unrealized_pnl_usd", None),
        ),
        "accumulated_costs_usd": _finite_metric(
            "accumulated costs",
            getattr(ledger, "accumulated_costs_usd", None),
            non_negative=True,
        ),
        "open_position_count": facts.open_position_count,
        "total_position_count": len(positions),
        "total_ledger_entry_count": len(entries),
        "processed_intent_count": len(processed),
        "aggregate_open_risk_usd": facts.aggregate_open_risk_usd,
        "daily_realized_pnl_usd": facts.daily_realized_pnl_usd,
        "rolling_drawdown_pct": facts.rolling_drawdown_pct,
        "consecutive_losses": facts.consecutive_losses,
        "last_loss_at_unix_ms": facts.last_loss_at_unix_ms,
    }
    return _finalize(material)


def canonical_fast_paper_shadow_outcome_telemetry(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry document must be a mapping"
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
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry document is not canonicalizable"
        ) from exc


def _provenance(
    manifest: object,
    binding: object,
    *,
    expected_release_sha: str,
) -> dict[str, object]:
    release = getattr(manifest, "release_source_sha", None)
    if release != expected_release_sha:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry release identity mismatch"
        )
    manifest_fingerprint = _sha256(
        "manifest fingerprint",
        getattr(manifest, "manifest_fingerprint_sha256", None),
    )
    champion_version = getattr(manifest, "champion_version", None)
    if not isinstance(champion_version, str) or not champion_version.strip():
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry champion version is invalid"
        )
    champion_fingerprint = _sha256(
        "champion fingerprint",
        getattr(manifest, "champion_fingerprint_sha256", None),
    )
    action_policy = getattr(manifest, "action_policy", None)
    action_policy_version = _positive_int(
        "action policy version",
        getattr(action_policy, "version", None),
    )
    run_id = getattr(binding, "run_id", None)
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry binding run id is invalid"
        )
    binding_fingerprint = _sha256(
        "binding fingerprint",
        getattr(binding, "binding_fingerprint_sha256", None),
    )
    return {
        "release_source_sha": release,
        "manifest_fingerprint_sha256": manifest_fingerprint,
        "champion_version": champion_version,
        "champion_fingerprint_sha256": champion_fingerprint,
        "action_policy_version": action_policy_version,
        "run_id": run_id,
        "binding_fingerprint_sha256": binding_fingerprint,
    }


def _window_metrics(entries: tuple[object, ...]) -> dict[str, object]:
    state_counts = {name: 0 for name in _EXECUTION_STATES}
    side_counts = {name: 0 for name in _SIDES}
    paper_reasons: dict[str, int] = {}
    ledger_reasons: dict[str, int] = {}
    notionals: list[float] = []
    costs: list[float] = []
    realized: list[float] = []
    cash_flows: list[float] = []
    realized_cost_bps: list[float] = []
    fills = 0
    failures = 0

    previous_sequence: int | None = None
    for entry in entries:
        sequence = _positive_int(
            "ledger entry sequence",
            getattr(entry, "sequence", None),
        )
        if previous_sequence is not None and sequence <= previous_sequence:
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry ledger entry sequence did not advance"
            )
        previous_sequence = sequence

        state = getattr(entry, "execution_state", None)
        state_value = getattr(state, "value", None)
        if state_value not in state_counts:
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry execution state is invalid"
            )
        state_counts[state_value] += 1
        if state is PaperExecutionState.FAILED:
            failures += 1
        elif state in (
            PaperExecutionState.PARTIAL,
            PaperExecutionState.FILLED,
        ):
            fills += 1

        side = getattr(entry, "side", None)
        side_value = getattr(side, "value", None)
        if side_value not in side_counts or side not in (
            TradeSide.BUY,
            TradeSide.SELL,
        ):
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry trade side is invalid"
            )
        side_counts[side_value] += 1

        paper_reason = getattr(
            getattr(entry, "paper_execution_reason_code", None),
            "value",
            None,
        )
        ledger_reason = getattr(
            getattr(entry, "ledger_reason_code", None),
            "value",
            None,
        )
        if not isinstance(paper_reason, str) or not paper_reason:
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry paper execution reason is invalid"
            )
        if not isinstance(ledger_reason, str) or not ledger_reason:
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry ledger reason is invalid"
            )
        paper_reasons[paper_reason] = paper_reasons.get(paper_reason, 0) + 1
        ledger_reasons[ledger_reason] = ledger_reasons.get(ledger_reason, 0) + 1

        filled_notional = _finite_metric(
            "filled notional",
            getattr(entry, "filled_notional_usd", None),
            non_negative=True,
        )
        explicit_cost = _finite_metric(
            "explicit cost",
            getattr(entry, "explicit_cost_usd", None),
            non_negative=True,
        )
        realized_delta = _finite_metric(
            "realized PnL delta",
            getattr(entry, "realized_pnl_delta_usd", None),
        )
        cash_flow = _finite_metric(
            "cash flow",
            getattr(entry, "cash_flow_usd", None),
        )
        notionals.append(filled_notional)
        costs.append(explicit_cost)
        realized.append(realized_delta)
        cash_flows.append(cash_flow)

        if state in (
            PaperExecutionState.PARTIAL,
            PaperExecutionState.FILLED,
        ):
            if filled_notional <= 0.0:
                raise FastPaperShadowOutcomeTelemetryError(
                    "shadow outcome telemetry filled execution has non-positive notional"
                )
            realized_cost_bps.append(
                explicit_cost / filled_notional * 10_000.0
            )

    return {
        "terminal_ledger_entry_count": len(entries),
        "fill_count": fills,
        "failed_execution_count": failures,
        "execution_state_counts": state_counts,
        "side_counts": side_counts,
        "paper_execution_reason_counts": {
            key: paper_reasons[key] for key in sorted(paper_reasons)
        },
        "ledger_reason_counts": {
            key: ledger_reasons[key] for key in sorted(ledger_reasons)
        },
        "filled_notional_usd": math.fsum(notionals),
        "explicit_cost_usd": math.fsum(costs),
        "realized_pnl_delta_usd": math.fsum(realized),
        "cash_flow_usd": math.fsum(cash_flows),
        "realized_explicit_cost_bps": _economic_summary(
            realized_cost_bps
        ),
    }


def _empty_metrics() -> dict[str, object]:
    return {
        "terminal_ledger_entry_count": 0,
        "fill_count": 0,
        "failed_execution_count": 0,
        "execution_state_counts": {
            "FAILED": 0,
            "PARTIAL": 0,
            "FILLED": 0,
        },
        "side_counts": {"BUY": 0, "SELL": 0},
        "paper_execution_reason_counts": {},
        "ledger_reason_counts": {},
        "filled_notional_usd": 0.0,
        "explicit_cost_usd": 0.0,
        "realized_pnl_delta_usd": 0.0,
        "cash_flow_usd": 0.0,
        "realized_explicit_cost_bps": {
            "mean": None,
            "p50": None,
            "p95": None,
        },
        "checkpoint_sequence": None,
        "checkpoint_payload_sha256": None,
        "checkpoint_state_as_of_unix_ms": None,
        "checkpoint_created_at_unix_ms": None,
        "starting_cash_usd": None,
        "cash_balance_usd": None,
        "realized_pnl_usd": None,
        "unrealized_pnl_usd": None,
        "accumulated_costs_usd": None,
        "open_position_count": None,
        "total_position_count": None,
        "total_ledger_entry_count": None,
        "processed_intent_count": None,
        "aggregate_open_risk_usd": None,
        "daily_realized_pnl_usd": None,
        "rolling_drawdown_pct": None,
        "consecutive_losses": None,
        "last_loss_at_unix_ms": None,
    }


def _economic_summary(
    values: list[float],
) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "p50": None, "p95": None}
    ordered = sorted(values)
    return {
        "mean": math.fsum(ordered) / float(len(ordered)),
        "p50": _nearest_rank(ordered, 0.50),
        "p95": _nearest_rank(ordered, 0.95),
    }


def _nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry percentile requires values"
        )
    rank = max(1, math.ceil(percentile * len(values)))
    return float(values[rank - 1])


def _require_risk_facts(facts: object) -> None:
    for name in (
        "open_position_count",
        "aggregate_open_risk_usd",
        "daily_realized_pnl_usd",
        "rolling_drawdown_pct",
        "consecutive_losses",
        "last_loss_at_unix_ms",
    ):
        if not hasattr(facts, name):
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry risk accounting facts are incomplete"
            )
    _non_negative_int(
        "open position count",
        facts.open_position_count,
    )
    _finite_metric(
        "aggregate open risk",
        facts.aggregate_open_risk_usd,
        non_negative=True,
    )
    _finite_metric(
        "daily realized PnL",
        facts.daily_realized_pnl_usd,
    )
    if facts.rolling_drawdown_pct is not None:
        drawdown = _finite_metric(
            "rolling drawdown",
            facts.rolling_drawdown_pct,
            non_negative=True,
        )
        if drawdown > 100.0:
            raise FastPaperShadowOutcomeTelemetryError(
                "shadow outcome telemetry rolling drawdown exceeds 100 percent"
            )
    _non_negative_int(
        "consecutive losses",
        facts.consecutive_losses,
    )
    if facts.last_loss_at_unix_ms is not None:
        _non_negative_int(
            "last loss timestamp",
            facts.last_loss_at_unix_ms,
        )


def _finalize(
    material: Mapping[str, object],
) -> dict[str, object]:
    document = dict(material)
    if "telemetry_fingerprint_sha256" in document:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry material may not predefine fingerprint"
        )
    return {
        **document,
        "telemetry_fingerprint_sha256": hashlib.sha256(
            canonical_fast_paper_shadow_outcome_telemetry(
                document
            ).encode("utf-8")
        ).hexdigest(),
    }


def _validate_release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry expected release SHA is invalid"
        )
    return value


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
        raise FastPaperShadowOutcomeTelemetryError(
            "shadow outcome telemetry window is invalid or exceeds 24 hours"
        )
    return since_unix_ms, until_unix_ms


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowOutcomeTelemetryError(
            f"shadow outcome telemetry {name} is invalid"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperShadowOutcomeTelemetryError(
            f"shadow outcome telemetry {name} is invalid"
        )
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowOutcomeTelemetryError(
            f"shadow outcome telemetry {name} is invalid"
        )
    return value


def _finite_metric(
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
        raise FastPaperShadowOutcomeTelemetryError(
            f"shadow outcome telemetry {name} is invalid"
        )
    scalar = float(value)
    if non_negative and scalar < 0.0:
        raise FastPaperShadowOutcomeTelemetryError(
            f"shadow outcome telemetry {name} must be non-negative"
        )
    return scalar


def _optional_finite_metric(
    name: str,
    value: object,
) -> float | None:
    if value is None:
        return None
    return _finite_metric(name, value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-outcome-telemetry"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("--manifest-path", required=True)
    summarize.add_argument("--ledger-database-path", required=True)
    summarize.add_argument("--run-id", required=True)
    summarize.add_argument("--expected-release-sha", required=True)
    summarize.add_argument("--since-unix-ms", type=int, required=True)
    summarize.add_argument("--until-unix-ms", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_outcome_telemetry(
            manifest_path=Path(args.manifest_path),
            ledger_database_path=Path(args.ledger_database_path),
            run_id=args.run_id,
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
        )
    except FastPaperShadowOutcomeTelemetryError as exc:
        failure = {
            "schema_name": (
                "shreks.fast_paper_shadow_outcome_telemetry_failure"
            ),
            "schema_version": _SCHEMA_VERSION,
            "state": "FAILED",
            "error_type": type(exc).__name__,
            "paper_cutover_authority": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        print(
            canonical_fast_paper_shadow_outcome_telemetry(
                failure
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(
        canonical_fast_paper_shadow_outcome_telemetry(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
