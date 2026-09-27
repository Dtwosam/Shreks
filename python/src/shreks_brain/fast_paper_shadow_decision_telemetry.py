from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable, Mapping

from .fast_paper_runtime.shadow import (
    read_fast_paper_shadow_decision_evidence,
)


_SCHEMA_NAME = "shreks.fast_paper_shadow_decision_telemetry"
_SCHEMA_VERSION = 1
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_EVIDENCE_NAME_RE = re.compile(
    r"^shadow-(?P<sequence>[0-9]{20})-(?P<digest>[0-9a-f]{16})\.json$"
)
_MAX_WINDOW_MS = 86_400_000
_ACTIONS = ("BUY", "SKIP", "HOLD", "REDUCE", "SELL")


class FastPaperShadowDecisionTelemetryError(RuntimeError):
    pass


def collect_fast_paper_shadow_decision_telemetry(
    *,
    evidence_directory: str | Path,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    root = Path(evidence_directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry evidence directory must be a regular non-symlink directory"
        )

    records: list[object] = []
    try:
        members = tuple(sorted(root.iterdir(), key=lambda value: value.name))
    except OSError as exc:
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry evidence directory cannot be read"
        ) from exc

    for member in members:
        if member.name.startswith("."):
            continue
        if member.is_symlink():
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry member must not be a symlink"
            )
        if not member.is_file():
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry member must be a regular file"
            )
        match = _EVIDENCE_NAME_RE.fullmatch(member.name)
        if match is None:
            continue
        try:
            evidence = read_fast_paper_shadow_decision_evidence(member)
        except Exception as exc:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry evidence authentication failed"
            ) from exc
        if int(match.group("sequence")) != evidence.source_sequence:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry filename/source sequence mismatch"
            )
        if since <= evidence.as_of_unix_ms < until:
            records.append(evidence)

    return summarize_fast_paper_shadow_decision_evidence(
        tuple(records),
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )


def summarize_fast_paper_shadow_decision_evidence(
    evidence: tuple[object, ...],
    *,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    if not isinstance(evidence, tuple):
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry evidence must be a tuple"
        )

    selected = sorted(evidence, key=lambda value: value.source_sequence)
    _validate_population(
        selected,
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )

    duration_ms = until - since
    count = len(selected)
    action_counts = {action: 0 for action in _ACTIONS}
    reason_counts: dict[str, int] = {}
    horizon_counts: dict[str, int] = {}

    lags_ms: list[float] = []
    latencies_ms: list[float] = []
    rewards: list[float] = []
    risks: list[float] = []
    costs: list[float] = []
    values: list[float] = []

    entry_unavailable = 0
    exit_unavailable = 0
    buy_disallowed = 0
    sell_non_executable = 0
    force_sell = 0

    for item in selected:
        decision = item.decision
        action = decision.action
        if action not in action_counts:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry action is unsupported"
            )
        action_counts[action] += 1
        reason = decision.reason
        if not isinstance(reason, str) or not reason:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry reason is invalid"
            )
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        horizon = decision.selected_horizon_ms
        if horizon is None:
            horizon_key = "NONE"
        else:
            if (
                isinstance(horizon, bool)
                or not isinstance(horizon, int)
                or horizon <= 0
            ):
                raise FastPaperShadowDecisionTelemetryError(
                    "shadow decision telemetry selected horizon is invalid"
                )
            horizon_key = str(horizon)
        horizon_counts[horizon_key] = horizon_counts.get(horizon_key, 0) + 1

        lag = item.evaluated_at_unix_ms - item.as_of_unix_ms
        if lag < 0:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry event/evaluation lag regressed"
            )
        lags_ms.append(float(lag))

        latency_ns = item.decision_latency_ns
        if (
            isinstance(latency_ns, bool)
            or not isinstance(latency_ns, int)
            or latency_ns < 0
        ):
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry decision latency is invalid"
            )
        latencies_ms.append(float(latency_ns) / 1_000_000.0)

        rewards.append(
            _finite_metric(
                "selected reward",
                decision.selected_reward_bps,
            )
        )
        risks.append(
            _finite_metric(
                "selected risk",
                decision.selected_risk_bps,
            )
        )
        costs.append(
            _finite_metric(
                "selected execution cost",
                decision.selected_execution_cost_bps,
            )
        )
        values.append(
            _finite_metric(
                "selected value",
                decision.selected_value_bps,
            )
        )

        if item.entry_quote.state == "UNAVAILABLE":
            entry_unavailable += 1
        elif item.entry_quote.state != "EXECUTABLE":
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry entry quote state is invalid"
            )
        if item.exit_quote.state == "UNAVAILABLE":
            exit_unavailable += 1
        elif item.exit_quote.state != "EXECUTABLE":
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry exit quote state is invalid"
            )

        constraints = item.constraints
        if type(constraints.buy_economically_allowed) is not bool:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry BUY constraint is invalid"
            )
        if type(constraints.sell_executable) is not bool:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry SELL constraint is invalid"
            )
        if type(constraints.force_sell) is not bool:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry force-sell constraint is invalid"
            )
        buy_disallowed += int(not constraints.buy_economically_allowed)
        sell_non_executable += int(not constraints.sell_executable)
        force_sell += int(constraints.force_sell)

    sequence_gaps = _source_sequence_gaps(selected)

    if selected:
        first = selected[0]
        identity = _runtime_identity(first)
        first_sequence: int | None = first.source_sequence
        last_sequence: int | None = selected[-1].source_sequence
        first_as_of: int | None = min(item.as_of_unix_ms for item in selected)
        last_as_of: int | None = max(item.as_of_unix_ms for item in selected)
        manifest_fingerprint: str | None = identity[0]
        champion_version: str | None = identity[1]
        champion_fingerprint: str | None = identity[2]
        action_policy_version: int | None = identity[3]
    else:
        first_sequence = None
        last_sequence = None
        first_as_of = None
        last_as_of = None
        manifest_fingerprint = None
        champion_version = None
        champion_fingerprint = None
        action_policy_version = None

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": manifest_fingerprint,
        "champion_version": champion_version,
        "champion_fingerprint_sha256": champion_fingerprint,
        "action_policy_version": action_policy_version,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": duration_ms,
        "decision_evidence_count": count,
        "decision_evidence_rate_per_second": (
            float(count) / (float(duration_ms) / 1000.0)
        ),
        "first_source_sequence": first_sequence,
        "last_source_sequence": last_sequence,
        "first_as_of_unix_ms": first_as_of,
        "last_as_of_unix_ms": last_as_of,
        "source_sequence_gap_count": sequence_gaps[0],
        "source_sequence_gap_total": sequence_gaps[1],
        "event_to_evaluation_lag_ms": _latency_summary(lags_ms),
        "decision_latency_ms": _latency_summary(latencies_ms),
        "action_counts": action_counts,
        "reason_counts": {
            key: reason_counts[key] for key in sorted(reason_counts)
        },
        "selected_horizon_counts": {
            key: horizon_counts[key] for key in sorted(horizon_counts)
        },
        "selected_reward_bps": _economic_summary(rewards),
        "selected_risk_bps": _economic_summary(risks),
        "selected_execution_cost_bps": _economic_summary(costs),
        "selected_value_bps": _economic_summary(values),
        "entry_quote_unavailable_count": entry_unavailable,
        "exit_quote_unavailable_count": exit_unavailable,
        "buy_economically_disallowed_count": buy_disallowed,
        "sell_non_executable_count": sell_non_executable,
        "force_sell_count": force_sell,
    }
    return {
        **material,
        "telemetry_fingerprint_sha256": hashlib.sha256(
            canonical_fast_paper_shadow_decision_telemetry(material).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def canonical_fast_paper_shadow_decision_telemetry(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry document must be a mapping"
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
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry document is not canonicalizable"
        ) from exc


def _validate_population(
    records: list[object],
    *,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> None:
    sequences: set[int] = set()
    event_ids: set[str] = set()
    fingerprints: set[str] = set()
    identity: tuple[object, ...] | None = None

    for item in records:
        if item.release_source_sha != expected_release_sha:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry release identity mismatch"
            )
        if not (
            since_unix_ms <= item.as_of_unix_ms < until_unix_ms
        ):
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry evidence is outside requested window"
            )
        sequence = item.source_sequence
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry source sequence is invalid"
            )
        if sequence in sequences:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry source sequence is duplicated"
            )
        sequences.add(sequence)

        event_id = item.source_event_id
        if not isinstance(event_id, str) or not event_id:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry source event identity is invalid"
            )
        if event_id in event_ids:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry source event identity is duplicated"
            )
        event_ids.add(event_id)

        fingerprint = item.evidence_fingerprint_sha256
        if not isinstance(fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ) is None:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry evidence fingerprint is invalid"
            )
        if fingerprint in fingerprints:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry evidence fingerprint is duplicated"
            )
        fingerprints.add(fingerprint)

        current_identity = _runtime_identity(item)
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise FastPaperShadowDecisionTelemetryError(
                "shadow decision telemetry runtime identity changed within window"
            )


def _runtime_identity(item: object) -> tuple[object, ...]:
    manifest = item.manifest_fingerprint_sha256
    champion_version = item.champion_version
    champion_fingerprint = item.champion_fingerprint_sha256
    policy_version = item.action_policy_version
    if (
        not isinstance(manifest, str)
        or re.fullmatch(r"[0-9a-f]{64}", manifest) is None
        or not isinstance(champion_version, str)
        or not champion_version
        or not isinstance(champion_fingerprint, str)
        or re.fullmatch(r"[0-9a-f]{64}", champion_fingerprint) is None
        or isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version <= 0
    ):
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry runtime identity is invalid"
        )
    return (
        manifest,
        champion_version,
        champion_fingerprint,
        policy_version,
    )


def _source_sequence_gaps(records: list[object]) -> tuple[int, int]:
    gap_count = 0
    gap_total = 0
    previous: int | None = None
    for item in records:
        sequence = item.source_sequence
        if previous is not None and sequence > previous + 1:
            gap_count += 1
            gap_total += sequence - previous - 1
        previous = sequence
    return gap_count, gap_total


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)
    return {
        "p50": _nearest_rank(ordered, 0.50),
        "p95": _nearest_rank(ordered, 0.95),
        "p99": _nearest_rank(ordered, 0.99),
        "max": float(ordered[-1]),
    }


def _economic_summary(values: list[float]) -> dict[str, float | None]:
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
        raise FastPaperShadowDecisionTelemetryError(
            "nearest-rank percentile requires evidence"
        )
    rank = max(1, math.ceil(percentile * len(values)))
    return float(values[rank - 1])


def _finite_metric(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowDecisionTelemetryError(
            f"shadow decision telemetry {name} is invalid"
        )
    return float(value)


def _validate_release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry expected release SHA is invalid"
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
        raise FastPaperShadowDecisionTelemetryError(
            "shadow decision telemetry window is invalid or exceeds 24 hours"
        )
    return since_unix_ms, until_unix_ms


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-decision-telemetry"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("--evidence-directory", required=True)
    summarize.add_argument("--expected-release-sha", required=True)
    summarize.add_argument("--since-unix-ms", type=int, required=True)
    summarize.add_argument("--until-unix-ms", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_decision_telemetry(
            evidence_directory=Path(args.evidence_directory),
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
        )
    except FastPaperShadowDecisionTelemetryError as exc:
        failure = {
            "schema_name": "shreks.fast_paper_shadow_decision_telemetry_failure",
            "schema_version": 1,
            "state": "FAILED",
            "error_type": type(exc).__name__,
            "paper_cutover_authority": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
        print(
            canonical_fast_paper_shadow_decision_telemetry(failure),
            end="",
            file=sys.stderr,
        )
        return 1
    print(
        canonical_fast_paper_shadow_decision_telemetry(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
