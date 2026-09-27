from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Mapping

from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    ExecutionStatus,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingEconomicsOverlayManifest,
    FastTrainingEconomicsOverlayRow,
    FastTrainingExecutionCostPolicy,
    build_entry_counterfactual_context_from_training_economics,
    decode_fast_training_execution_cost_policy,
    fast_training_execution_cost_policy_fingerprint_sha256,
    read_fast_training_economics_overlay_for_horizon,
    validate_fast_training_economics_overlay,
)

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
)
from .fast_paper_shadow_sample_proof import _read_window_decisions
from .fast_paper_shadow_trade_economics import (
    _read_sample_proof,
    _require_sample_matches,
)


FAST_PAPER_SHADOW_COUNTERFACTUAL_ECONOMICS_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_counterfactual_economics"
)
FAST_PAPER_SHADOW_COUNTERFACTUAL_ECONOMICS_SCHEMA_VERSION = 1

_PINNED_SENSITIVITY_FIELDS = (
    "entry_latency_bps",
    "exit_latency_bps",
)
_SENSITIVE_COST_FIELDS = (
    "additional_entry_slippage_bps",
    "additional_exit_slippage_bps",
    "entry_network_fee_quote",
    "exit_network_fee_quote",
    "entry_priority_fee_quote",
    "exit_priority_fee_quote",
    "entry_expected_failure_cost_quote",
    "exit_expected_failure_cost_quote",
)


class FastPaperShadowCounterfactualEconomicsError(RuntimeError):
    pass


def collect_fast_paper_shadow_counterfactual_economics(
    *,
    manifest_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    sample_proof_path: str | Path,
    training_economics_overlay_path: str | Path,
    baseline_cost_policy_path: str | Path,
    sensitivity_cost_policy_paths: tuple[str | Path, ...],
    horizons_ms: tuple[int, ...],
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> dict[str, object]:
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics run id must be non-empty"
        )
    horizons = _horizons(horizons_ms)
    if (
        not isinstance(sensitivity_cost_policy_paths, tuple)
        or not sensitivity_cost_policy_paths
    ):
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics requires at least one sensitivity cost policy"
        )
    since, until = _window(since_unix_ms, until_unix_ms)

    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=run_id,
            database_path=ledger_database_path,
        )
    except Exception as exc:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics runtime authority authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_release_sha:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics release identity mismatch"
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
        if isinstance(exc, FastPaperShadowCounterfactualEconomicsError):
            raise
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics FL11.1 prerequisite failed"
        ) from exc

    try:
        decisions = _read_window_decisions(
            manifest=manifest,
            decision_evidence_directory=decision_evidence_directory,
            since_unix_ms=since,
            until_unix_ms=until,
        )
    except Exception as exc:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics learned decision evidence failed authentication"
        ) from exc
    skip_decisions = tuple(
        decision
        for decision in decisions
        if decision.decision.action == "SKIP"
    )

    overlay_manifest, row_index = _overlay_rows(
        training_economics_overlay_path,
        horizons,
    )
    baseline = _read_cost_policy(
        baseline_cost_policy_path,
        label="baseline",
    )
    sensitivity = tuple(
        _read_cost_policy(path, label=f"sensitivity[{index}]")
        for index, path in enumerate(sensitivity_cost_policy_paths)
    )
    _validate_policy_family(baseline, sensitivity)

    base_quantity = _counterfactual_base_quantity(overlay_manifest)
    policies = (baseline, *sensitivity)
    policy_results = tuple(
        _evaluate_policy(
            policy=policy,
            skip_decisions=skip_decisions,
            horizons_ms=horizons,
            row_index=row_index,
            overlay_manifest=overlay_manifest,
            base_quantity=base_quantity,
        )
        for policy in policies
    )
    baseline_result = policy_results[0]
    sensitivity_results = tuple(
        _attach_sensitivity_delta(
            baseline_result,
            result,
        )
        for result in policy_results[1:]
    )

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_COUNTERFACTUAL_ECONOMICS_SCHEMA_NAME,
        "schema_version": (
            FAST_PAPER_SHADOW_COUNTERFACTUAL_ECONOMICS_SCHEMA_VERSION
        ),
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
        "training_economics_overlay_manifest_fingerprint_sha256": (
            overlay_manifest.manifest_fingerprint_sha256
        ),
        "future_path_logical_fingerprint_sha256": (
            overlay_manifest.future_path_logical_fingerprint_sha256
        ),
        "future_path_label_version": (
            overlay_manifest.future_path_label_version
        ),
        "counterfactual_base_quantity": (
            overlay_manifest.counterfactual_base_quantity
        ),
        "horizons_ms": list(horizons),
        "skip_decision_count": len(skip_decisions),
        "baseline": baseline_result,
        "sensitivity": list(sensitivity_results),
        "actual_trade_fee_slippage_burden": "MEASURED_BY_FL11_2A",
        "latency_sensitivity": "NOT_INCLUDED_FL11_2B",
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(material)


def canonical_fast_paper_shadow_counterfactual_economics(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics document must be a mapping"
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
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics document is not canonicalizable"
        ) from exc


def _overlay_rows(
    path: str | Path,
    horizons_ms: tuple[int, ...],
) -> tuple[
    FastTrainingEconomicsOverlayManifest,
    dict[tuple[str, int, int], FastTrainingEconomicsOverlayRow],
]:
    try:
        manifest = validate_fast_training_economics_overlay(path)
    except Exception as exc:
        raise FastPaperShadowCounterfactualEconomicsError(
            "training economics overlay authentication failed"
        ) from exc
    rows: dict[tuple[str, int, int], FastTrainingEconomicsOverlayRow] = {}
    for horizon in horizons_ms:
        try:
            selection = read_fast_training_economics_overlay_for_horizon(
                path,
                horizon_ms=horizon,
                label_version=manifest.future_path_label_version,
            )
        except Exception as exc:
            raise FastPaperShadowCounterfactualEconomicsError(
                f"training economics overlay lacks requested horizon {horizon}"
            ) from exc
        if selection.manifest != manifest:
            raise FastPaperShadowCounterfactualEconomicsError(
                "training economics overlay manifest changed across horizon scans"
            )
        for row in selection.rows:
            key = (
                row.decision_signature,
                row.decision_ordinal,
                row.horizon_ms,
            )
            if key in rows:
                raise FastPaperShadowCounterfactualEconomicsError(
                    "training economics overlay row identity is duplicated"
                )
            rows[key] = row
    return manifest, rows


def _read_cost_policy(
    path: str | Path,
    *,
    label: str,
) -> FastTrainingExecutionCostPolicy:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise FastPaperShadowCounterfactualEconomicsError(
            f"{label} cost policy must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        policy = decode_fast_training_execution_cost_policy(payload.strip())
    except Exception as exc:
        raise FastPaperShadowCounterfactualEconomicsError(
            f"{label} cost policy is malformed"
        ) from exc
    return policy


def _validate_policy_family(
    baseline: FastTrainingExecutionCostPolicy,
    sensitivity: tuple[FastTrainingExecutionCostPolicy, ...],
) -> None:
    if type(baseline) is not FastTrainingExecutionCostPolicy:
        raise FastPaperShadowCounterfactualEconomicsError(
            "baseline cost policy must be exact FastTrainingExecutionCostPolicy"
        )
    seen_versions = {baseline.version}
    seen_assumptions = {_cost_assumption_tuple(baseline)}
    for policy in sensitivity:
        if type(policy) is not FastTrainingExecutionCostPolicy:
            raise FastPaperShadowCounterfactualEconomicsError(
                "sensitivity cost policy must be exact FastTrainingExecutionCostPolicy"
            )
        if policy.version in seen_versions:
            raise FastPaperShadowCounterfactualEconomicsError(
                "cost policy versions must be unique"
            )
        seen_versions.add(policy.version)
        for field_name in _PINNED_SENSITIVITY_FIELDS:
            if getattr(policy, field_name) != getattr(baseline, field_name):
                raise FastPaperShadowCounterfactualEconomicsError(
                    "FL11.2b sensitivity may not change latency assumptions"
                )
        assumptions = _cost_assumption_tuple(policy)
        if assumptions in seen_assumptions:
            raise FastPaperShadowCounterfactualEconomicsError(
                "sensitivity policy must change at least one fee/slippage assumption"
            )
        seen_assumptions.add(assumptions)


def _cost_assumption_tuple(
    policy: FastTrainingExecutionCostPolicy,
) -> tuple[object, ...]:
    return tuple(
        getattr(policy, name)
        for name in (*_PINNED_SENSITIVITY_FIELDS, *_SENSITIVE_COST_FIELDS)
    )


def _evaluate_policy(
    *,
    policy: FastTrainingExecutionCostPolicy,
    skip_decisions: tuple[object, ...],
    horizons_ms: tuple[int, ...],
    row_index: Mapping[
        tuple[str, int, int],
        FastTrainingEconomicsOverlayRow,
    ],
    overlay_manifest: FastTrainingEconomicsOverlayManifest,
    base_quantity: float,
) -> dict[str, object]:
    observations: list[dict[str, object]] = []
    for decision in skip_decisions:
        feature = decision.feature_record
        for horizon in horizons_ms:
            key = (
                feature.decision_signature,
                feature.decision_ordinal,
                horizon,
            )
            row = row_index.get(key)
            observation_key = (
                f"{decision.evidence_fingerprint_sha256}:h{horizon}"
            )
            if row is None:
                observations.append(
                    _unavailable_observation(
                        decision,
                        horizon_ms=horizon,
                        observation_key=observation_key,
                        coverage="MISSING_ROW",
                        overlay_status=None,
                    )
                )
                continue
            _require_row_matches_decision(row, decision, horizon_ms=horizon)
            try:
                context = (
                    build_entry_counterfactual_context_from_training_economics(
                        row,
                        policy=policy,
                        overlay_manifest_fingerprint_sha256=(
                            overlay_manifest.manifest_fingerprint_sha256
                        ),
                        base_quantity=base_quantity,
                        horizon_complete=(
                            row.endpoint_observed_at_unix_ms is not None
                        ),
                    )
                )
                outcome_set = label_entry_counterfactuals(context)
            except Exception as exc:
                raise FastPaperShadowCounterfactualEconomicsError(
                    "sealed counterfactual economics evaluation failed"
                ) from exc
            buy_now = tuple(
                value
                for value in outcome_set
                if value.action is CounterfactualAction.BUY_NOW
            )
            if len(buy_now) != 1:
                raise FastPaperShadowCounterfactualEconomicsError(
                    "counterfactual labeler did not produce one BUY_NOW outcome"
                )
            outcome = buy_now[0]
            if outcome.execution_status is not ExecutionStatus.EXECUTABLE:
                observations.append(
                    _unavailable_observation(
                        decision,
                        horizon_ms=horizon,
                        observation_key=observation_key,
                        coverage=outcome.execution_status.value.upper(),
                        overlay_status=row.status.value,
                    )
                )
                continue
            if outcome.net_pnl_quote is None or outcome.return_bps is None:
                raise FastPaperShadowCounterfactualEconomicsError(
                    "executable BUY_NOW counterfactual lacks economics"
                )
            pnl = _finite(
                "counterfactual net_pnl_quote",
                outcome.net_pnl_quote,
            )
            return_bps = _finite(
                "counterfactual return_bps",
                outcome.return_bps,
            )
            observations.append(
                {
                    "observation_key": observation_key,
                    "decision_evidence_fingerprint_sha256": (
                        decision.evidence_fingerprint_sha256
                    ),
                    "source_event_id": decision.source_event_id,
                    "source_sequence": decision.source_sequence,
                    "decision_signature": feature.decision_signature,
                    "decision_ordinal": feature.decision_ordinal,
                    "horizon_ms": horizon,
                    "overlay_status": row.status.value,
                    "execution_status": ExecutionStatus.EXECUTABLE.value,
                    "classification": _classification(pnl),
                    "counterfactual_net_pnl_quote_vs_skip": pnl,
                    "counterfactual_return_bps": return_bps,
                    "entry_evidence_id": outcome.entry_evidence_id,
                    "exit_evidence_id": outcome.exit_evidence_id,
                }
            )

    observations.sort(
        key=lambda value: (
            value["source_sequence"],
            value["horizon_ms"],
            value["observation_key"],
        )
    )
    overall = _summarize_observations(tuple(observations))
    by_horizon = []
    for horizon in horizons_ms:
        subset = tuple(
            value
            for value in observations
            if value["horizon_ms"] == horizon
        )
        summary = _summarize_observations(subset)
        by_horizon.append(
            {
                "horizon_ms": horizon,
                **summary,
            }
        )
    _reconcile_horizons(overall, tuple(by_horizon))
    return {
        "cost_policy": asdict(policy),
        "cost_policy_fingerprint_sha256": (
            fast_training_execution_cost_policy_fingerprint_sha256(policy)
        ),
        "overall": overall,
        "by_horizon": by_horizon,
        "observations": observations,
    }


def _require_row_matches_decision(
    row: FastTrainingEconomicsOverlayRow,
    decision: object,
    *,
    horizon_ms: int,
) -> None:
    feature = decision.feature_record
    actual = (
        row.decision_signature,
        row.decision_ordinal,
        row.decision_sequence,
        row.decision_observed_at_unix_ms,
        row.mint,
        row.quote_mint,
        row.venue,
        row.horizon_ms,
    )
    expected = (
        feature.decision_signature,
        feature.decision_ordinal,
        feature.decision_sequence,
        feature.decision_observed_at_unix_ms,
        feature.mint,
        feature.quote_mint,
        feature.venue,
        horizon_ms,
    )
    if actual != expected:
        raise FastPaperShadowCounterfactualEconomicsError(
            "training economics overlay row conflicts with learned decision identity"
        )
    if decision.source_sequence != feature.decision_sequence:
        raise FastPaperShadowCounterfactualEconomicsError(
            "learned decision source sequence conflicts with feature identity"
        )
    if decision.as_of_unix_ms != feature.decision_observed_at_unix_ms:
        raise FastPaperShadowCounterfactualEconomicsError(
            "learned decision timestamp conflicts with feature identity"
        )


def _unavailable_observation(
    decision: object,
    *,
    horizon_ms: int,
    observation_key: str,
    coverage: str,
    overlay_status: str | None,
) -> dict[str, object]:
    feature = decision.feature_record
    return {
        "observation_key": observation_key,
        "decision_evidence_fingerprint_sha256": (
            decision.evidence_fingerprint_sha256
        ),
        "source_event_id": decision.source_event_id,
        "source_sequence": decision.source_sequence,
        "decision_signature": feature.decision_signature,
        "decision_ordinal": feature.decision_ordinal,
        "horizon_ms": horizon_ms,
        "overlay_status": overlay_status,
        "execution_status": coverage,
        "classification": "UNAVAILABLE",
        "counterfactual_net_pnl_quote_vs_skip": None,
        "counterfactual_return_bps": None,
        "entry_evidence_id": None,
        "exit_evidence_id": None,
    }


def _summarize_observations(
    observations: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    executable = tuple(
        value
        for value in observations
        if value["execution_status"] == ExecutionStatus.EXECUTABLE.value
    )
    missing = sum(
        1 for value in observations if value["execution_status"] == "MISSING_ROW"
    )
    unavailable = len(observations) - len(executable) - missing
    profitable = tuple(
        value
        for value in executable
        if value["classification"] == "MISSED_PROFIT"
    )
    losses = tuple(
        value
        for value in executable
        if value["classification"] == "AVOIDED_LOSS"
    )
    flat = tuple(
        value
        for value in executable
        if value["classification"] == "FLAT"
    )
    pnl_values = [
        float(value["counterfactual_net_pnl_quote_vs_skip"])
        for value in executable
    ]
    return_values = [
        float(value["counterfactual_return_bps"])
        for value in executable
    ]
    positive_total = math.fsum(
        float(value["counterfactual_net_pnl_quote_vs_skip"])
        for value in profitable
    )
    avoided_total = math.fsum(
        -float(value["counterfactual_net_pnl_quote_vs_skip"])
        for value in losses
    )
    signed_total = math.fsum(pnl_values)
    return {
        "observation_count": len(observations),
        "executable_count": len(executable),
        "missing_row_count": missing,
        "unavailable_count": unavailable,
        "profitable_missed_opportunity_count": len(profitable),
        "avoided_loss_count": len(losses),
        "flat_count": len(flat),
        "missed_positive_opportunity_quote": positive_total,
        "avoided_loss_quote": avoided_total,
        "signed_net_opportunity_quote": signed_total,
        "return_bps": _summary(return_values),
    }


def _attach_sensitivity_delta(
    baseline: Mapping[str, object],
    sensitivity: Mapping[str, object],
) -> dict[str, object]:
    base_observations = {
        value["observation_key"]: value
        for value in baseline["observations"]
    }
    sensitivity_observations = {
        value["observation_key"]: value
        for value in sensitivity["observations"]
    }
    if set(base_observations) != set(sensitivity_observations):
        raise FastPaperShadowCounterfactualEconomicsError(
            "sensitivity observation identity differs from baseline"
        )
    sign_flips = 0
    comparable = 0
    for key in sorted(base_observations):
        base = base_observations[key]
        other = sensitivity_observations[key]
        if base["execution_status"] != other["execution_status"]:
            raise FastPaperShadowCounterfactualEconomicsError(
                "cost sensitivity changed counterfactual evidence availability"
            )
        if base["execution_status"] != ExecutionStatus.EXECUTABLE.value:
            continue
        comparable += 1
        base_value = float(base["counterfactual_net_pnl_quote_vs_skip"])
        other_value = float(other["counterfactual_net_pnl_quote_vs_skip"])
        if _sign(base_value) != _sign(other_value):
            sign_flips += 1

    base_overall = baseline["overall"]
    other_overall = sensitivity["overall"]
    delta = {
        "comparable_executable_count": comparable,
        "sign_flip_count": sign_flips,
        "signed_net_opportunity_quote_delta": (
            other_overall["signed_net_opportunity_quote"]
            - base_overall["signed_net_opportunity_quote"]
        ),
        "missed_positive_opportunity_quote_delta": (
            other_overall["missed_positive_opportunity_quote"]
            - base_overall["missed_positive_opportunity_quote"]
        ),
        "avoided_loss_quote_delta": (
            other_overall["avoided_loss_quote"]
            - base_overall["avoided_loss_quote"]
        ),
        "profitable_missed_opportunity_count_delta": (
            other_overall["profitable_missed_opportunity_count"]
            - base_overall["profitable_missed_opportunity_count"]
        ),
        "avoided_loss_count_delta": (
            other_overall["avoided_loss_count"]
            - base_overall["avoided_loss_count"]
        ),
    }
    return {
        **dict(sensitivity),
        "delta_vs_baseline": delta,
    }


def _reconcile_horizons(
    overall: Mapping[str, object],
    by_horizon: tuple[Mapping[str, object], ...],
) -> None:
    for name in (
        "observation_count",
        "executable_count",
        "missing_row_count",
        "unavailable_count",
        "profitable_missed_opportunity_count",
        "avoided_loss_count",
        "flat_count",
    ):
        if sum(int(value[name]) for value in by_horizon) != int(overall[name]):
            raise FastPaperShadowCounterfactualEconomicsError(
                f"counterfactual horizon {name} does not reconcile"
            )
    for name in (
        "missed_positive_opportunity_quote",
        "avoided_loss_quote",
        "signed_net_opportunity_quote",
    ):
        expected = math.fsum(float(value[name]) for value in by_horizon)
        if not math.isclose(
            expected,
            float(overall[name]),
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise FastPaperShadowCounterfactualEconomicsError(
                f"counterfactual horizon {name} does not reconcile"
            )


def _classification(value: float) -> str:
    if value > 0.0:
        return "MISSED_PROFIT"
    if value < 0.0:
        return "AVOIDED_LOSS"
    return "FLAT"


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "mean": None,
            "p50": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(_finite("summary value", value) for value in values)
    return {
        "mean": math.fsum(ordered) / len(ordered),
        "p50": _nearest_rank(ordered, 50),
        "p95": _nearest_rank(ordered, 95),
        "min": ordered[0],
        "max": ordered[-1],
    }


def _nearest_rank(values: list[float], percentile: int) -> float:
    rank = max(1, math.ceil(percentile * len(values) / 100.0))
    return float(values[min(rank - 1, len(values) - 1)])


def _counterfactual_base_quantity(
    manifest: FastTrainingEconomicsOverlayManifest,
) -> float:
    try:
        value = float(manifest.counterfactual_base_quantity)
    except ValueError as exc:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual base quantity is invalid"
        ) from exc
    if not math.isfinite(value) or value <= 0.0:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual base quantity is invalid"
        )
    return value


def _horizons(value: object) -> tuple[int, ...]:
    if not isinstance(value, tuple) or not value:
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual horizons must be a non-empty tuple"
        )
    normalized = []
    for horizon in value:
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
            raise FastPaperShadowCounterfactualEconomicsError(
                "counterfactual horizons must be positive integers"
            )
        normalized.append(horizon)
    if len(set(normalized)) != len(normalized):
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual horizons must be unique"
        )
    return tuple(sorted(normalized))


def _window(since: object, until: object) -> tuple[int, int]:
    if (
        isinstance(since, bool)
        or not isinstance(since, int)
        or since < 0
        or isinstance(until, bool)
        or not isinstance(until, int)
        or until <= since
    ):
        raise FastPaperShadowCounterfactualEconomicsError(
            "counterfactual economics window is invalid"
        )
    return since, until


def _finite(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowCounterfactualEconomicsError(
            f"{name} must be finite"
        )
    return float(value)


def _finalize(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    fingerprint = hashlib.sha256(
        canonical_fast_paper_shadow_counterfactual_economics(
            document
        ).encode("utf-8")
    ).hexdigest()
    return {
        **document,
        "report_fingerprint_sha256": fingerprint,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-counterfactual-economics"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--ledger-database-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision-evidence-directory", required=True)
    parser.add_argument("--sample-proof-path", required=True)
    parser.add_argument("--training-economics-overlay-path", required=True)
    parser.add_argument("--baseline-cost-policy-path", required=True)
    parser.add_argument(
        "--sensitivity-cost-policy-path",
        action="append",
        required=True,
    )
    parser.add_argument(
        "--horizon-ms",
        action="append",
        type=int,
        required=True,
    )
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--since-unix-ms", type=int, required=True)
    parser.add_argument("--until-unix-ms", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_counterfactual_economics(
            manifest_path=args.manifest_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=args.decision_evidence_directory,
            sample_proof_path=args.sample_proof_path,
            training_economics_overlay_path=(
                args.training_economics_overlay_path
            ),
            baseline_cost_policy_path=args.baseline_cost_policy_path,
            sensitivity_cost_policy_paths=tuple(
                args.sensitivity_cost_policy_path
            ),
            horizons_ms=tuple(args.horizon_ms),
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
        )
    except (FastPaperShadowCounterfactualEconomicsError, ValueError) as exc:
        print(
            canonical_fast_paper_shadow_counterfactual_economics(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_counterfactual_economics_failure"
                    ),
                    "schema_version": (
                        FAST_PAPER_SHADOW_COUNTERFACTUAL_ECONOMICS_SCHEMA_VERSION
                    ),
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
    print(
        canonical_fast_paper_shadow_counterfactual_economics(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
