from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Mapping

from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .fast_paper_runtime.shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_execution_source import (
    read_fast_paper_shadow_execution_input_source_record,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    load_fast_paper_shadow_ledger_checkpoint_at_or_before,
    load_fast_paper_shadow_ledger_checkpoint_by_sequence,
)
from .fast_paper_runtime.shadow_runtime_state import (
    load_fast_paper_shadow_runtime_state_by_checkpoint_sequence,
)


FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_independent_sample"
)
FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION = 1
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = ("BUY", "SKIP", "HOLD", "REDUCE", "SELL")


class FastPaperShadowSampleProofError(RuntimeError):
    pass


class FastPaperShadowSampleDecision(StrEnum):
    SUFFICIENT_SAMPLE = "SUFFICIENT_SAMPLE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class FastPaperShadowSampleGateStatus(StrEnum):
    PASS = "PASS"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class FastPaperShadowSamplePolicy:
    version: str
    min_decision_count: int
    min_distinct_market_count: int
    min_distinct_mint_count: int
    min_observation_span_ms: int
    min_closed_position_count: int
    min_distinct_traded_mint_count: int
    min_distinct_buy_regime_count: int
    min_distinct_selected_horizon_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("sample policy version must be non-empty")
        for name in (
            "min_decision_count",
            "min_distinct_market_count",
            "min_distinct_mint_count",
            "min_observation_span_ms",
            "min_closed_position_count",
            "min_distinct_traded_mint_count",
            "min_distinct_buy_regime_count",
            "min_distinct_selected_horizon_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


def collect_fast_paper_shadow_independent_sample(
    *,
    manifest_path: str | Path,
    execution_policy_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
    policy: FastPaperShadowSamplePolicy,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    if type(policy) is not FastPaperShadowSamplePolicy:
        raise FastPaperShadowSampleProofError(
            "sample policy must be exact FastPaperShadowSamplePolicy"
        )
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowSampleProofError(
            "shadow sample proof run id must be non-empty"
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
        raise FastPaperShadowSampleProofError(
            "shadow sample proof authority authentication failed"
        ) from exc

    if manifest.release_source_sha != expected_sha:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof release identity mismatch"
        )

    decisions = _read_window_decisions(
        manifest=manifest,
        decision_evidence_directory=decision_evidence_directory,
        since_unix_ms=since,
        until_unix_ms=until,
    )
    buy_regimes, missing_buy_sources = _read_buy_regimes(
        manifest=manifest,
        execution_policy=execution_policy,
        binding=binding,
        decisions=decisions,
        execution_source_directory=execution_source_directory,
    )
    try:
        checkpoint = load_fast_paper_shadow_ledger_checkpoint_at_or_before(
            manifest,
            binding,
            as_of_unix_ms=until - 1,
        )
    except Exception as exc:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof checkpoint read failed closed"
        ) from exc

    return summarize_fast_paper_shadow_independent_sample(
        decisions,
        buy_regimes=buy_regimes,
        missing_buy_execution_source_count=missing_buy_sources,
        checkpoint=checkpoint,
        policy=policy,
        expected_release_sha=expected_sha,
        binding_fingerprint_sha256=binding.binding_fingerprint_sha256,
        since_unix_ms=since,
        until_unix_ms=until,
    )


def summarize_fast_paper_shadow_independent_sample(
    decisions: tuple[object, ...],
    *,
    buy_regimes: Mapping[str, MarketRegime],
    missing_buy_execution_source_count: int,
    checkpoint: object | None,
    policy: FastPaperShadowSamplePolicy,
    expected_release_sha: str,
    binding_fingerprint_sha256: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    expected_sha = _validate_release_sha(expected_release_sha)
    since, until = _validate_window(since_unix_ms, until_unix_ms)
    if type(policy) is not FastPaperShadowSamplePolicy:
        raise FastPaperShadowSampleProofError(
            "sample policy must be exact FastPaperShadowSamplePolicy"
        )
    _require_sha256(
        "binding_fingerprint_sha256",
        binding_fingerprint_sha256,
    )
    if not isinstance(decisions, tuple):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof decisions must be a tuple"
        )
    if not isinstance(buy_regimes, Mapping):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof BUY regimes must be a mapping"
        )
    if (
        isinstance(missing_buy_execution_source_count, bool)
        or not isinstance(missing_buy_execution_source_count, int)
        or missing_buy_execution_source_count < 0
    ):
        raise FastPaperShadowSampleProofError(
            "missing BUY execution source count is invalid"
        )

    ordered = tuple(sorted(decisions, key=lambda value: value.source_sequence))
    identity = _validate_decisions(
        ordered,
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )
    action_counts = {action: 0 for action in _ACTIONS}
    horizon_counts: dict[str, int] = {}
    markets: set[str] = set()
    mints: set[str] = set()
    decision_times: list[int] = []
    buy_fingerprints: set[str] = set()

    for item in ordered:
        action = item.decision.action
        action_counts[action] += 1
        markets.add(item.market_key)
        mint = item.feature_record.mint
        if not isinstance(mint, str) or not mint:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision mint is invalid"
            )
        mints.add(mint)
        decision_times.append(item.as_of_unix_ms)
        horizon = item.decision.selected_horizon_ms
        if horizon is not None:
            if (
                isinstance(horizon, bool)
                or not isinstance(horizon, int)
                or horizon <= 0
            ):
                raise FastPaperShadowSampleProofError(
                    "shadow sample proof selected horizon is invalid"
                )
            key = str(horizon)
            horizon_counts[key] = horizon_counts.get(key, 0) + 1
        if action == "BUY":
            buy_fingerprints.add(item.evidence_fingerprint_sha256)

    supplied_regimes = set(buy_regimes)
    if not supplied_regimes.issubset(buy_fingerprints):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof contains regime evidence for a non-BUY decision"
        )
    regime_counts = {value.value: 0 for value in MarketRegime}
    for fingerprint, regime in buy_regimes.items():
        _require_sha256("BUY decision fingerprint", fingerprint)
        if type(regime) is not MarketRegime:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof BUY regime is invalid"
            )
        regime_counts[regime.value] += 1

    missing_total = len(buy_fingerprints - supplied_regimes)
    if missing_total != missing_buy_execution_source_count:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof missing BUY source count does not reconcile"
        )

    closed_positions = _closed_positions_in_window(
        checkpoint,
        since_unix_ms=since,
        until_unix_ms=until,
    )
    traded_mints = {position.mint for position in closed_positions}
    observed_span_ms = (
        0
        if len(decision_times) < 2
        else max(decision_times) - min(decision_times)
    )
    distinct_buy_regimes = sum(
        1 for count in regime_counts.values() if count > 0
    )
    distinct_horizons = len(horizon_counts)

    observed = {
        "decision_count": len(ordered),
        "distinct_market_count": len(markets),
        "distinct_mint_count": len(mints),
        "observation_span_ms": observed_span_ms,
        "closed_position_count": len(closed_positions),
        "distinct_traded_mint_count": len(traded_mints),
        "distinct_buy_regime_count": distinct_buy_regimes,
        "distinct_selected_horizon_count": distinct_horizons,
    }
    thresholds = {
        "decision_count": policy.min_decision_count,
        "distinct_market_count": policy.min_distinct_market_count,
        "distinct_mint_count": policy.min_distinct_mint_count,
        "observation_span_ms": policy.min_observation_span_ms,
        "closed_position_count": policy.min_closed_position_count,
        "distinct_traded_mint_count": policy.min_distinct_traded_mint_count,
        "distinct_buy_regime_count": policy.min_distinct_buy_regime_count,
        "distinct_selected_horizon_count": (
            policy.min_distinct_selected_horizon_count
        ),
    }

    gates = [
        _gate(
            "BUY_REGIME_EVIDENCE_COMPLETE",
            missing_buy_execution_source_count == 0,
            missing_buy_execution_source_count,
            0,
            "every BUY decision requires authenticated execution-source regime evidence",
        )
    ]
    for code, key in (
        ("MIN_DECISION_COUNT", "decision_count"),
        ("MIN_DISTINCT_MARKET_COUNT", "distinct_market_count"),
        ("MIN_DISTINCT_MINT_COUNT", "distinct_mint_count"),
        ("MIN_OBSERVATION_SPAN", "observation_span_ms"),
        ("MIN_CLOSED_POSITION_COUNT", "closed_position_count"),
        ("MIN_DISTINCT_TRADED_MINT_COUNT", "distinct_traded_mint_count"),
        ("MIN_DISTINCT_BUY_REGIME_COUNT", "distinct_buy_regime_count"),
        (
            "MIN_DISTINCT_SELECTED_HORIZON_COUNT",
            "distinct_selected_horizon_count",
        ),
    ):
        gates.append(
            _gate(
                code,
                observed[key] >= thresholds[key],
                observed[key],
                thresholds[key],
                "independent sample breadth threshold",
            )
        )
    gates = sorted(gates, key=lambda value: value["code"])
    decision = (
        FastPaperShadowSampleDecision.SUFFICIENT_SAMPLE
        if all(\n            value["status"] == FastPaperShadowSampleGateStatus.PASS.value\n            for value in gates\n        )
        else FastPaperShadowSampleDecision.INSUFFICIENT_SAMPLE
    )

    manifest_fingerprint = None if identity is None else identity[0]
    champion_version = None if identity is None else identity[1]
    champion_fingerprint = None if identity is None else identity[2]
    action_policy_version = None if identity is None else identity[3]
    first_sequence = None if not ordered else ordered[0].source_sequence
    last_sequence = None if not ordered else ordered[-1].source_sequence

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION,
        "policy_version": policy.version,
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": manifest_fingerprint,
        "champion_version": champion_version,
        "champion_fingerprint_sha256": champion_fingerprint,
        "action_policy_version": action_policy_version,
        "binding_fingerprint_sha256": binding_fingerprint_sha256,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        "first_source_sequence": first_sequence,
        "last_source_sequence": last_sequence,
        **observed,
        "missing_buy_execution_source_count": (
            missing_buy_execution_source_count
        ),
        "action_counts": action_counts,
        "selected_horizon_counts": {
            key: horizon_counts[key] for key in sorted(horizon_counts)
        },
        "buy_regime_counts": regime_counts,
        "gate_results": gates,
        "decision": decision.value,
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return {
        **material,
        "report_fingerprint_sha256": hashlib.sha256(
            canonical_fast_paper_shadow_sample_proof(material).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def canonical_fast_paper_shadow_sample_proof(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof document must be a mapping"
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
        raise FastPaperShadowSampleProofError(
            "shadow sample proof document is not canonicalizable"
        ) from exc


def _read_window_decisions(
    *,
    manifest: object,
    decision_evidence_directory: str | Path,
    since_unix_ms: int,
    until_unix_ms: int,
) -> tuple[FastPaperShadowDecisionEvidence, ...]:
    root = _directory(decision_evidence_directory, "decision evidence")
    records: list[FastPaperShadowDecisionEvidence] = []
    sequences: set[int] = set()
    fingerprints: set[str] = set()
    for path in sorted(root.glob("shadow-*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision path is not a regular file"
            )
        try:
            evidence = read_fast_paper_shadow_decision_evidence(path)
            validate_fast_paper_shadow_decision_evidence(evidence)
        except Exception as exc:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision authentication failed"
            ) from exc
        if evidence.release_source_sha != manifest.release_source_sha:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision release mismatch"
            )
        if (
            evidence.manifest_fingerprint_sha256
            != manifest.manifest_fingerprint_sha256
            or evidence.champion_version != manifest.champion_version
            or evidence.champion_fingerprint_sha256
            != manifest.champion_fingerprint_sha256
            or evidence.action_policy_version != manifest.action_policy.version
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision runtime identity mismatch"
            )
        if evidence.source_sequence in sequences:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision source sequence is duplicated"
            )
        if evidence.evidence_fingerprint_sha256 in fingerprints:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision fingerprint is duplicated"
            )
        sequences.add(evidence.source_sequence)
        fingerprints.add(evidence.evidence_fingerprint_sha256)
        if since_unix_ms <= evidence.as_of_unix_ms < until_unix_ms:
            records.append(evidence)
    return tuple(sorted(records, key=lambda value: value.source_sequence))


def _read_buy_regimes(
    *,
    manifest: object,
    execution_policy: object,
    binding: object,
    decisions: tuple[FastPaperShadowDecisionEvidence, ...],
    execution_source_directory: str | Path,
) -> tuple[dict[str, MarketRegime], int]:
    root = _directory(execution_source_directory, "execution source")
    regimes: dict[str, MarketRegime] = {}
    missing = 0
    for evidence in decisions:
        if evidence.decision.action != "BUY":
            continue
        path = root / f"{evidence.evidence_fingerprint_sha256}.json"
        if path.is_symlink():
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source must not be a symlink"
            )
        if not path.exists():
            missing += 1
            continue
        if not path.is_file():
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source must be a regular file"
            )
        bindings = _probe_source_bindings(path)
        if (
            bindings["decision_evidence_fingerprint_sha256"]
            != evidence.evidence_fingerprint_sha256
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source decision fingerprint mismatch"
            )
        pre_sequence = bindings["paper_checkpoint_sequence"]
        try:
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
        except Exception as exc:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof historical pre-state read failed"
            ) from exc
        if pre_checkpoint is None or pre_runtime is None:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source references missing historical pre-state"
            )
        if (
            pre_checkpoint.payload_sha256
            != bindings["paper_checkpoint_payload_sha256"]
            or pre_runtime.state_fingerprint_sha256
            != bindings["shadow_runtime_state_fingerprint_sha256"]
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source historical binding mismatch"
            )
        try:
            source_record = read_fast_paper_shadow_execution_input_source_record(
                manifest,
                execution_policy,
                evidence,
                root,
                paper_checkpoint_sequence=pre_checkpoint.sequence,
                paper_checkpoint_payload_sha256=pre_checkpoint.payload_sha256,
                shadow_runtime_state_fingerprint_sha256=(
                    pre_runtime.state_fingerprint_sha256
                ),
            )
        except Exception as exc:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof execution source authentication failed"
            ) from exc
        regime = source_record.execution_input.market_regime
        if type(regime) is not MarketRegime:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof BUY execution source lacks market regime"
            )
        regimes[evidence.evidence_fingerprint_sha256] = regime
    return regimes, missing


def _closed_positions_in_window(
    checkpoint: object | None,
    *,
    since_unix_ms: int,
    until_unix_ms: int,
) -> tuple[object, ...]:
    if checkpoint is None:
        return ()
    ledger = getattr(getattr(checkpoint, "state", None), "ledger", None)
    positions = getattr(ledger, "positions", None)
    if not isinstance(positions, tuple):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof checkpoint ledger positions are invalid"
        )
    selected = []
    for position in positions:
        if position.state is not PaperPositionState.CLOSED:
            continue
        closed_at = position.closed_at_unix_ms
        if (
            isinstance(closed_at, bool)
            or not isinstance(closed_at, int)
            or closed_at < 0
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof closed position timestamp is invalid"
            )
        if since_unix_ms <= closed_at < until_unix_ms:
            if not isinstance(position.mint, str) or not position.mint:
                raise FastPaperShadowSampleProofError(
                    "shadow sample proof closed position mint is invalid"
                )
            selected.append(position)
    return tuple(
        sorted(
            selected,
            key=lambda value: (value.closed_at_unix_ms, value.position_id),
        )
    )


def _validate_decisions(
    decisions: tuple[object, ...],
    *,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> tuple[object, ...] | None:
    sequences: set[int] = set()
    events: set[str] = set()
    fingerprints: set[str] = set()
    identity: tuple[object, ...] | None = None
    for item in decisions:
        sequence = getattr(item, "source_sequence", None)
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
            or sequence in sequences
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision source sequence is invalid or duplicated"
            )
        sequences.add(sequence)
        event_id = getattr(item, "source_event_id", None)
        if not isinstance(event_id, str) or not event_id or event_id in events:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof source event identity is invalid or duplicated"
            )
        events.add(event_id)
        fingerprint = getattr(item, "evidence_fingerprint_sha256", None)
        _require_sha256("decision evidence fingerprint", fingerprint)
        if fingerprint in fingerprints:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision fingerprint is duplicated"
            )
        fingerprints.add(fingerprint)
        if getattr(item, "release_source_sha", None) != expected_release_sha:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision release mismatch"
            )
        as_of = getattr(item, "as_of_unix_ms", None)
        if (
            isinstance(as_of, bool)
            or not isinstance(as_of, int)
            or not (since_unix_ms <= as_of < until_unix_ms)
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision is outside requested window"
            )
        market_key = getattr(item, "market_key", None)
        if not isinstance(market_key, str) or not market_key:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof market key is invalid"
            )
        action = getattr(getattr(item, "decision", None), "action", None)
        if action not in _ACTIONS:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof decision action is unsupported"
            )
        current = (
            getattr(item, "manifest_fingerprint_sha256", None),
            getattr(item, "champion_version", None),
            getattr(item, "champion_fingerprint_sha256", None),
            getattr(item, "action_policy_version", None),
        )
        if (
            not isinstance(current[0], str)
            or _SHA256_RE.fullmatch(current[0]) is None
            or not isinstance(current[1], str)
            or not current[1]
            or not isinstance(current[2], str)
            or _SHA256_RE.fullmatch(current[2]) is None
            or isinstance(current[3], bool)
            or not isinstance(current[3], int)
            or current[3] <= 0
        ):
            raise FastPaperShadowSampleProofError(
                "shadow sample proof runtime identity is invalid"
            )
        if identity is None:
            identity = current
        elif current != identity:
            raise FastPaperShadowSampleProofError(
                "shadow sample proof runtime identity changed within window"
            )
    return identity


def _probe_source_bindings(path: Path) -> dict[str, object]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof execution source cannot be read"
        ) from exc
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof execution source must have one trailing newline"
        )
    try:
        document = json.loads(
            payload[:-1].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof execution source JSON is malformed"
        ) from exc
    if not isinstance(document, dict):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof execution source must be an object"
        )
    return {
        "decision_evidence_fingerprint_sha256": _sha256(
            "source decision fingerprint",
            document.get("decision_evidence_fingerprint_sha256"),
        ),
        "paper_checkpoint_sequence": _non_negative_int(
            "source checkpoint sequence",
            document.get("paper_checkpoint_sequence"),
        ),
        "paper_checkpoint_payload_sha256": _sha256(
            "source checkpoint fingerprint",
            document.get("paper_checkpoint_payload_sha256"),
        ),
        "shadow_runtime_state_fingerprint_sha256": _sha256(
            "source runtime-state fingerprint",
            document.get("shadow_runtime_state_fingerprint_sha256"),
        ),
    }


def _gate(
    code: str,
    passed: bool,
    observed: int,
    threshold: int,
    message: str,
) -> dict[str, object]:
    return {
        "code": code,
        "status": (
            FastPaperShadowSampleGateStatus.PASS.value
            if passed
            else FastPaperShadowSampleGateStatus.INSUFFICIENT.value
        ),
        "observed_value": observed,
        "threshold_value": threshold,
        "message": message,
    }


def _directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowSampleProofError(
            f"shadow sample proof {label} directory must be a regular non-symlink directory"
        )
    return root


def _validate_release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowSampleProofError(
            "shadow sample proof expected release SHA is invalid"
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
        or until_unix_ms <= since_unix_ms
    ):
        raise FastPaperShadowSampleProofError(
            "shadow sample proof window is invalid"
        )
    return since_unix_ms, until_unix_ms


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowSampleProofError(f"{name} must be lowercase SHA-256")


def _sha256(name: str, value: object) -> str:
    _require_sha256(name, value)
    assert isinstance(value, str)
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowSampleProofError(
            f"{name} must be a non-negative integer"
        )
    return value


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
        prog="shreks-fast-paper-shadow-sample-proof"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--execution-policy-path", required=True)
    parser.add_argument("--ledger-database-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision-evidence-directory", required=True)
    parser.add_argument("--execution-source-directory", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--since-unix-ms", type=int, required=True)
    parser.add_argument("--until-unix-ms", type=int, required=True)
    parser.add_argument("--policy-version", required=True)
    parser.add_argument("--min-decisions", type=int, required=True)
    parser.add_argument("--min-distinct-markets", type=int, required=True)
    parser.add_argument("--min-distinct-mints", type=int, required=True)
    parser.add_argument("--min-observation-span-ms", type=int, required=True)
    parser.add_argument("--min-closed-positions", type=int, required=True)
    parser.add_argument("--min-distinct-traded-mints", type=int, required=True)
    parser.add_argument("--min-distinct-buy-regimes", type=int, required=True)
    parser.add_argument("--min-distinct-horizons", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = FastPaperShadowSamplePolicy(
            version=args.policy_version,
            min_decision_count=args.min_decisions,
            min_distinct_market_count=args.min_distinct_markets,
            min_distinct_mint_count=args.min_distinct_mints,
            min_observation_span_ms=args.min_observation_span_ms,
            min_closed_position_count=args.min_closed_positions,
            min_distinct_traded_mint_count=args.min_distinct_traded_mints,
            min_distinct_buy_regime_count=args.min_distinct_buy_regimes,
            min_distinct_selected_horizon_count=args.min_distinct_horizons,
        )
        result = collect_fast_paper_shadow_independent_sample(
            manifest_path=args.manifest_path,
            execution_policy_path=args.execution_policy_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=args.decision_evidence_directory,
            execution_source_directory=args.execution_source_directory,
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
            policy=policy,
        )
    except (FastPaperShadowSampleProofError, ValueError) as exc:
        print(
            canonical_fast_paper_shadow_sample_proof(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_independent_sample_failure"
                    ),
                    "schema_version": FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION,
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
    print(canonical_fast_paper_shadow_sample_proof(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
