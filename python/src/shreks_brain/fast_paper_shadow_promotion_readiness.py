from __future__ import annotations

import argparse
from dataclasses import dataclass
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


FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_promotion_policy"
)
FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_VERSION = 1
FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_promotion_readiness"
)
FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_VERSION = 1

_SAMPLE_SCHEMA_NAME = "shreks.fast_paper_shadow_independent_sample"
_ECONOMICS_SCHEMA_NAME = "shreks.fast_paper_shadow_trade_economics"
_MISSED_SCHEMA_NAME = "shreks.fast_paper_shadow_missed_opportunity"
_LATENCY_SCHEMA_NAME = "shreks.fast_paper_shadow_latency_proof"
_FL11_SCHEMA_VERSION = 1

_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_IDENTITY_FIELDS = (
    "release_source_sha",
    "manifest_fingerprint_sha256",
    "champion_version",
    "champion_fingerprint_sha256",
    "action_policy_version",
    "binding_fingerprint_sha256",
    "window_since_unix_ms",
    "window_until_unix_ms",
    "window_duration_ms",
)

_POLICY_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "version",
        "min_net_expectancy_pct",
        "min_profit_factor",
        "max_drawdown_pct",
        "max_cost_burden_pct",
        "max_worst_loss_bps",
        "max_expected_realized_mae_bps",
        "max_entry_slippage_p95_bps",
        "max_entry_capital_utilization_p95_pct",
        "max_missed_opportunity_rate",
        "max_missed_opportunity_mean_bps",
        "policy_fingerprint_sha256",
    }
)


class FastPaperShadowPromotionReadinessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowPromotionPolicy:
    version: str
    min_net_expectancy_pct: float
    min_profit_factor: float
    max_drawdown_pct: float
    max_cost_burden_pct: float
    max_worst_loss_bps: float
    max_expected_realized_mae_bps: float
    max_entry_slippage_p95_bps: float
    max_entry_capital_utilization_p95_pct: float
    max_missed_opportunity_rate: float
    max_missed_opportunity_mean_bps: float

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("promotion policy version must be non-empty")
        _finite_policy("min_net_expectancy_pct", self.min_net_expectancy_pct)
        _non_negative_policy("min_profit_factor", self.min_profit_factor)
        _percent_policy("max_drawdown_pct", self.max_drawdown_pct)
        _non_negative_policy("max_cost_burden_pct", self.max_cost_burden_pct)
        _non_negative_policy("max_worst_loss_bps", self.max_worst_loss_bps)
        _non_negative_policy(
            "max_expected_realized_mae_bps",
            self.max_expected_realized_mae_bps,
        )
        _finite_policy(
            "max_entry_slippage_p95_bps",
            self.max_entry_slippage_p95_bps,
        )
        _percent_policy(
            "max_entry_capital_utilization_p95_pct",
            self.max_entry_capital_utilization_p95_pct,
        )
        _fraction_policy(
            "max_missed_opportunity_rate",
            self.max_missed_opportunity_rate,
        )
        _non_negative_policy(
            "max_missed_opportunity_mean_bps",
            self.max_missed_opportunity_mean_bps,
        )


def assess_fast_paper_shadow_promotion_readiness(
    *,
    sample_report: Mapping[str, object],
    trade_economics_report: Mapping[str, object],
    missed_opportunity_report: Mapping[str, object],
    latency_report: Mapping[str, object],
    policy: FastPaperShadowPromotionPolicy,
) -> dict[str, object]:
    if type(policy) is not FastPaperShadowPromotionPolicy:
        raise FastPaperShadowPromotionReadinessError(
            "promotion policy must be exact FastPaperShadowPromotionPolicy"
        )

    sample = _validated_report(
        sample_report,
        label="FL11.1 sample proof",
        schema_name=_SAMPLE_SCHEMA_NAME,
    )
    economics = _validated_report(
        trade_economics_report,
        label="FL11.2a trade economics",
        schema_name=_ECONOMICS_SCHEMA_NAME,
    )
    missed = _validated_report(
        missed_opportunity_report,
        label="FL11.2b missed opportunity",
        schema_name=_MISSED_SCHEMA_NAME,
    )
    latency = _validated_report(
        latency_report,
        label="FL11.3 latency proof",
        schema_name=_LATENCY_SCHEMA_NAME,
    )

    for document, label in (
        (sample, "FL11.1 sample proof"),
        (economics, "FL11.2a trade economics"),
        (missed, "FL11.2b missed opportunity"),
        (latency, "FL11.3 latency proof"),
    ):
        _require_authority_firewall(document, label)

    identity = {name: sample.get(name) for name in _IDENTITY_FIELDS}
    _validate_identity(identity)

    for document, label in (
        (economics, "FL11.2a trade economics"),
        (missed, "FL11.2b missed opportunity"),
        (latency, "FL11.3 latency proof"),
    ):
        for name, expected in identity.items():
            if document.get(name) != expected:
                raise FastPaperShadowPromotionReadinessError(
                    f"{label} {name} mismatch"
                )
        if (
            document.get("sample_proof_fingerprint_sha256")
            != sample["report_fingerprint_sha256"]
        ):
            raise FastPaperShadowPromotionReadinessError(
                f"{label} sample proof fingerprint mismatch"
            )

    metrics = _require_mapping(
        _require_mapping(
            economics.get("sealed_e5_report"),
            "FL11.2a sealed_e5_report",
        ).get("metrics"),
        "FL11.2a sealed_e5_report metrics",
    )
    loss_tail = _require_mapping(
        economics.get("loss_tail"),
        "FL11.2a loss_tail",
    )
    calibration = _require_mapping(
        economics.get("expected_realized_value_bps"),
        "FL11.2a expected_realized_value_bps",
    )
    entry_efficiency = _require_mapping(
        economics.get("entry_efficiency"),
        "FL11.2a entry_efficiency",
    )
    slippage = _require_mapping(
        entry_efficiency.get("signed_slippage_bps"),
        "FL11.2a signed_slippage_bps",
    )
    capital = _require_mapping(
        economics.get("entry_capital_utilization"),
        "FL11.2a entry_capital_utilization",
    )
    utilization = _require_mapping(
        capital.get("entry_notional_to_trading_capital_pct"),
        "FL11.2a entry_notional_to_trading_capital_pct",
    )

    net_expectancy = _optional_finite(
        metrics.get("net_expectancy_pct"),
        "FL11.2a net_expectancy_pct",
    )
    profit_factor = _optional_finite(
        metrics.get("profit_factor"),
        "FL11.2a profit_factor",
    )
    drawdown = _optional_finite(
        metrics.get("maximum_drawdown_pct"),
        "FL11.2a maximum_drawdown_pct",
    )
    cost_burden = _optional_finite(
        metrics.get("cost_burden_pct"),
        "FL11.2a cost_burden_pct",
    )
    worst_return = _optional_finite(
        loss_tail.get("worst_net_return_bps"),
        "FL11.2a worst_net_return_bps",
    )
    if worst_return is None:
        loss_count = metrics.get("loss_count")
        if _optional_non_negative_int(loss_count, "FL11.2a loss_count") == 0:
            worst_loss_bps: float | None = 0.0
        else:
            worst_loss_bps = None
    else:
        worst_loss_bps = abs(worst_return)

    expected_realized_mae = _optional_finite(
        calibration.get("mean_absolute_error_bps"),
        "FL11.2a mean_absolute_error_bps",
    )
    slippage_p95 = _optional_finite(
        slippage.get("p95"),
        "FL11.2a signed_slippage_bps p95",
    )
    utilization_p95 = _optional_finite(
        utilization.get("p95"),
        "FL11.2a capital utilization p95",
    )

    missed_observed = _missed_opportunity_observed(missed)
    missed_rate = missed_observed["rate"]
    missed_mean = missed_observed["mean_bps"]
    missed_complete = missed_observed["complete"]

    sample_decision = sample.get("decision")
    if not isinstance(sample_decision, str):
        raise FastPaperShadowPromotionReadinessError(
            "FL11.1 sample proof decision is invalid"
        )
    latency_decision = latency.get("decision")
    if not isinstance(latency_decision, str):
        raise FastPaperShadowPromotionReadinessError(
            "FL11.3 latency proof decision is invalid"
        )

    gates = [
        _status_gate(
            "FL11_1_SUFFICIENT_SAMPLE",
            sample_decision == "SUFFICIENT_SAMPLE",
            sample_decision,
            "SUFFICIENT_SAMPLE",
            "FL11.1 must contain a sufficient independent sample",
        ),
        _minimum_gate(
            "MIN_NET_EXPECTANCY_PCT",
            net_expectancy,
            policy.min_net_expectancy_pct,
        ),
        _minimum_gate(
            "MIN_PROFIT_FACTOR",
            profit_factor,
            policy.min_profit_factor,
        ),
        _maximum_gate(
            "MAX_DRAWDOWN_PCT",
            drawdown,
            policy.max_drawdown_pct,
        ),
        _maximum_gate(
            "MAX_COST_BURDEN_PCT",
            cost_burden,
            policy.max_cost_burden_pct,
        ),
        _maximum_gate(
            "MAX_WORST_LOSS_BPS",
            worst_loss_bps,
            policy.max_worst_loss_bps,
        ),
        _maximum_gate(
            "MAX_EXPECTED_REALIZED_MAE_BPS",
            expected_realized_mae,
            policy.max_expected_realized_mae_bps,
        ),
        _maximum_gate(
            "MAX_ENTRY_SLIPPAGE_P95_BPS",
            slippage_p95,
            policy.max_entry_slippage_p95_bps,
        ),
        _maximum_gate(
            "MAX_ENTRY_CAPITAL_UTILIZATION_P95_PCT",
            utilization_p95,
            policy.max_entry_capital_utilization_p95_pct,
        ),
        _status_gate(
            "MISSED_OPPORTUNITY_EVIDENCE_COMPLETE",
            bool(missed_complete),
            missed.get("missed_opportunity_evidence_state"),
            "COMPLETE_OR_NO_SKIP_DECISIONS",
            "FL11.2b skipped-opportunity evidence must be fully scorable",
        ),
        _maximum_gate(
            "MAX_MISSED_OPPORTUNITY_RATE",
            missed_rate,
            policy.max_missed_opportunity_rate,
        ),
        _maximum_gate(
            "MAX_MISSED_OPPORTUNITY_MEAN_BPS",
            missed_mean,
            policy.max_missed_opportunity_mean_bps,
        ),
        _status_gate(
            "FL11_3_LATENCY_PROVEN",
            latency_decision == "LATENCY_PROVEN",
            latency_decision,
            "LATENCY_PROVEN",
            "FL11.3 must prove entry latency compatible with selected horizons",
        ),
    ]

    decision = (
        "PROMOTION_READY"
        if all(gate["status"] == "PASS" for gate in gates)
        else "PROMOTION_NOT_READY"
    )
    policy_fingerprint = (
        fast_paper_shadow_promotion_policy_fingerprint_sha256(policy)
    )
    observed_metrics = {
        "net_expectancy_pct": net_expectancy,
        "profit_factor": profit_factor,
        "maximum_drawdown_pct": drawdown,
        "cost_burden_pct": cost_burden,
        "worst_loss_bps": worst_loss_bps,
        "expected_realized_mae_bps": expected_realized_mae,
        "entry_slippage_p95_bps": slippage_p95,
        "entry_capital_utilization_p95_pct": utilization_p95,
        "missed_opportunity_rate": missed_rate,
        "missed_opportunity_mean_bps": missed_mean,
        "latency_decision": latency_decision,
    }

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_VERSION,
        "policy_version": policy.version,
        "policy_fingerprint_sha256": policy_fingerprint,
        **identity,
        "sample_proof_fingerprint_sha256": sample[
            "report_fingerprint_sha256"
        ],
        "trade_economics_report_fingerprint_sha256": economics[
            "report_fingerprint_sha256"
        ],
        "missed_opportunity_report_fingerprint_sha256": missed[
            "report_fingerprint_sha256"
        ],
        "latency_proof_report_fingerprint_sha256": latency[
            "report_fingerprint_sha256"
        ],
        "observed_metrics": observed_metrics,
        "gate_results": gates,
        "decision": decision,
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize_report(material)


def encode_fast_paper_shadow_promotion_policy(
    policy: FastPaperShadowPromotionPolicy,
) -> str:
    if type(policy) is not FastPaperShadowPromotionPolicy:
        raise ValueError(
            "policy must be exact FastPaperShadowPromotionPolicy"
        )
    material = _promotion_policy_material(policy)
    return _canonical(
        {
            **material,
            "policy_fingerprint_sha256": hashlib.sha256(
                _canonical(material).encode("utf-8")
            ).hexdigest(),
        }
    )


def decode_fast_paper_shadow_promotion_policy(
    payload: str,
) -> FastPaperShadowPromotionPolicy:
    document = _decode_canonical_json(
        payload,
        "Fast PAPER shadow promotion policy",
    )
    if frozenset(document) != _POLICY_FIELDS:
        raise ValueError(
            "Fast PAPER shadow promotion policy has unknown or missing fields"
        )
    if (
        document.get("schema_name")
        != FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_NAME
        or document.get("schema_version")
        != FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_VERSION
    ):
        raise ValueError(
            "Fast PAPER shadow promotion policy schema is incompatible"
        )
    try:
        policy = FastPaperShadowPromotionPolicy(
            version=document["version"],
            min_net_expectancy_pct=document["min_net_expectancy_pct"],
            min_profit_factor=document["min_profit_factor"],
            max_drawdown_pct=document["max_drawdown_pct"],
            max_cost_burden_pct=document["max_cost_burden_pct"],
            max_worst_loss_bps=document["max_worst_loss_bps"],
            max_expected_realized_mae_bps=document[
                "max_expected_realized_mae_bps"
            ],
            max_entry_slippage_p95_bps=document[
                "max_entry_slippage_p95_bps"
            ],
            max_entry_capital_utilization_p95_pct=document[
                "max_entry_capital_utilization_p95_pct"
            ],
            max_missed_opportunity_rate=document[
                "max_missed_opportunity_rate"
            ],
            max_missed_opportunity_mean_bps=document[
                "max_missed_opportunity_mean_bps"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Fast PAPER shadow promotion policy content is incompatible"
        ) from exc

    claimed = document.get("policy_fingerprint_sha256")
    _require_sha256_value("policy_fingerprint_sha256", claimed)
    expected = fast_paper_shadow_promotion_policy_fingerprint_sha256(policy)
    if claimed != expected:
        raise ValueError(
            "Fast PAPER shadow promotion policy fingerprint mismatch"
        )
    return policy


def fast_paper_shadow_promotion_policy_fingerprint_sha256(
    policy: FastPaperShadowPromotionPolicy,
) -> str:
    if type(policy) is not FastPaperShadowPromotionPolicy:
        raise ValueError(
            "policy must be exact FastPaperShadowPromotionPolicy"
        )
    return hashlib.sha256(
        _canonical(_promotion_policy_material(policy)).encode("utf-8")
    ).hexdigest()


def canonical_fast_paper_shadow_promotion_readiness(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness document must be a mapping"
        )
    try:
        return _canonical(dict(document))
    except (TypeError, ValueError) as exc:
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness document is not canonicalizable"
        ) from exc


def collect_fast_paper_shadow_promotion_readiness(
    *,
    manifest_path: str | Path,
    sample_proof_path: str | Path,
    trade_economics_path: str | Path,
    missed_opportunity_path: str | Path,
    latency_proof_path: str | Path,
    promotion_policy_path: str | Path,
    expected_release_sha: str,
) -> dict[str, object]:
    if (
        not isinstance(expected_release_sha, str)
        or _SOURCE_SHA_RE.fullmatch(expected_release_sha) is None
    ):
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness expected release SHA is invalid"
        )
    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness runtime manifest authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_release_sha:
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness release identity mismatch"
        )

    policy_path = _regular_file(
        promotion_policy_path,
        "promotion policy",
    )
    try:
        policy = decode_fast_paper_shadow_promotion_policy(
            policy_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness policy authentication failed"
        ) from exc

    sample = _read_report_file(sample_proof_path, "FL11.1 sample proof")
    economics = _read_report_file(
        trade_economics_path,
        "FL11.2a trade economics",
    )
    missed = _read_report_file(
        missed_opportunity_path,
        "FL11.2b missed opportunity",
    )
    latency = _read_report_file(latency_proof_path, "FL11.3 latency proof")

    report = assess_fast_paper_shadow_promotion_readiness(
        sample_report=sample,
        trade_economics_report=economics,
        missed_opportunity_report=missed,
        latency_report=latency,
        policy=policy,
    )
    expected_manifest_identity = {
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "action_policy_version": manifest.action_policy.version,
    }
    for name, expected in expected_manifest_identity.items():
        if report.get(name) != expected:
            raise FastPaperShadowPromotionReadinessError(
                f"promotion-readiness manifest {name} mismatch"
            )
    return report


def _validated_report(
    value: Mapping[str, object],
    *,
    label: str,
    schema_name: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be a mapping"
        )
    document = dict(value)
    if (
        document.get("schema_name") != schema_name
        or document.get("schema_version") != _FL11_SCHEMA_VERSION
    ):
        raise FastPaperShadowPromotionReadinessError(
            f"{label} schema is incompatible"
        )
    claimed = document.get("report_fingerprint_sha256")
    _require_sha256(claimed, f"{label} report fingerprint")
    material = dict(document)
    material.pop("report_fingerprint_sha256", None)
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} report fingerprint mismatch"
        )
    return document


def _validate_identity(identity: Mapping[str, object]) -> None:
    release = identity.get("release_source_sha")
    if not isinstance(release, str) or _SOURCE_SHA_RE.fullmatch(release) is None:
        raise FastPaperShadowPromotionReadinessError(
            "FL11.1 sample proof release_source_sha is invalid"
        )
    for name in (
        "manifest_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "binding_fingerprint_sha256",
    ):
        _require_sha256(
            identity.get(name),
            f"FL11.1 sample proof {name}",
        )
    for name in ("champion_version", "action_policy_version"):
        value = identity.get(name)
        if not isinstance(value, str) or not value.strip():
            raise FastPaperShadowPromotionReadinessError(
                f"FL11.1 sample proof {name} is invalid"
            )
    since = _non_negative_int(
        identity.get("window_since_unix_ms"),
        "FL11.1 sample proof window_since_unix_ms",
    )
    until = _non_negative_int(
        identity.get("window_until_unix_ms"),
        "FL11.1 sample proof window_until_unix_ms",
    )
    duration = _non_negative_int(
        identity.get("window_duration_ms"),
        "FL11.1 sample proof window_duration_ms",
    )
    if until <= since or duration != until - since:
        raise FastPaperShadowPromotionReadinessError(
            "FL11.1 sample proof window identity is inconsistent"
        )


def _require_authority_firewall(
    document: Mapping[str, object],
    label: str,
) -> None:
    for name in (
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
    ):
        if document.get(name) != "NOT_GRANTED":
            raise FastPaperShadowPromotionReadinessError(
                f"{label} {name} boundary is incompatible"
            )
    if document.get("live_authority") != "DISABLED":
        raise FastPaperShadowPromotionReadinessError(
            f"{label} LIVE authority boundary is incompatible"
        )


def _missed_opportunity_observed(
    document: Mapping[str, object],
) -> dict[str, object]:
    skip_count = _non_negative_int(
        document.get("skip_decision_count"),
        "FL11.2b skip_decision_count",
    )
    fully_scorable = _non_negative_int(
        document.get("fully_scorable_skip_count"),
        "FL11.2b fully_scorable_skip_count",
    )
    partial = _non_negative_int(
        document.get("partially_or_unscorable_skip_count"),
        "FL11.2b partially_or_unscorable_skip_count",
    )
    state = document.get("missed_opportunity_evidence_state")
    if not isinstance(state, str):
        raise FastPaperShadowPromotionReadinessError(
            "FL11.2b missed_opportunity_evidence_state is invalid"
        )
    if fully_scorable + partial != skip_count:
        raise FastPaperShadowPromotionReadinessError(
            "FL11.2b skip scorable counts do not reconcile"
        )

    if skip_count == 0:
        complete = state == "NO_SKIP_DECISIONS" and partial == 0
        return {
            "complete": complete,
            "rate": 0.0,
            "mean_bps": 0.0,
        }

    complete = (
        state == "COMPLETE"
        and partial == 0
        and fully_scorable == skip_count
    )
    rate = _optional_finite(
        document.get("positive_missed_opportunity_rate"),
        "FL11.2b positive_missed_opportunity_rate",
    )
    if rate is not None and not 0.0 <= rate <= 1.0:
        raise FastPaperShadowPromotionReadinessError(
            "FL11.2b positive_missed_opportunity_rate is outside [0, 1]"
        )
    best = _require_mapping(
        document.get("best_missed_opportunity_bps"),
        "FL11.2b best_missed_opportunity_bps",
    )
    mean_bps = _optional_finite(
        best.get("mean"),
        "FL11.2b missed-opportunity mean",
    )
    return {
        "complete": complete,
        "rate": rate,
        "mean_bps": mean_bps,
    }


def _promotion_policy_material(
    policy: FastPaperShadowPromotionPolicy,
) -> dict[str, object]:
    return {
        "schema_name": FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_PROMOTION_POLICY_SCHEMA_VERSION,
        "version": policy.version,
        "min_net_expectancy_pct": policy.min_net_expectancy_pct,
        "min_profit_factor": policy.min_profit_factor,
        "max_drawdown_pct": policy.max_drawdown_pct,
        "max_cost_burden_pct": policy.max_cost_burden_pct,
        "max_worst_loss_bps": policy.max_worst_loss_bps,
        "max_expected_realized_mae_bps": (
            policy.max_expected_realized_mae_bps
        ),
        "max_entry_slippage_p95_bps": policy.max_entry_slippage_p95_bps,
        "max_entry_capital_utilization_p95_pct": (
            policy.max_entry_capital_utilization_p95_pct
        ),
        "max_missed_opportunity_rate": policy.max_missed_opportunity_rate,
        "max_missed_opportunity_mean_bps": (
            policy.max_missed_opportunity_mean_bps
        ),
    }


def _minimum_gate(
    code: str,
    observed: float | None,
    threshold: float,
) -> dict[str, object]:
    return _status_gate(
        code,
        observed is not None and observed >= threshold,
        observed,
        threshold,
        "observed metric must meet or exceed the explicit minimum",
    )


def _maximum_gate(
    code: str,
    observed: float | None,
    threshold: float,
) -> dict[str, object]:
    return _status_gate(
        code,
        observed is not None and observed <= threshold,
        observed,
        threshold,
        "observed metric must not exceed the explicit maximum",
    )


def _status_gate(
    code: str,
    passed: bool,
    observed: object,
    threshold: object,
    message: str,
) -> dict[str, object]:
    return {
        "code": code,
        "status": "PASS" if passed else "FAIL",
        "observed_value": observed,
        "threshold_value": threshold,
        "message": message,
    }


def _finalize_report(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    if "report_fingerprint_sha256" in document:
        raise FastPaperShadowPromotionReadinessError(
            "promotion-readiness material may not predefine fingerprint"
        )
    return {
        **document,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(document).encode("utf-8")
        ).hexdigest(),
    }


def _read_report_file(
    path: str | Path,
    label: str,
) -> dict[str, object]:
    file_path = _regular_file(path, label)
    try:
        payload = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} read failed"
        ) from exc
    try:
        return _decode_canonical_json(payload, label)
    except ValueError as exc:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} is malformed or non-canonical"
        ) from exc


def _regular_file(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser()
    if value.is_symlink() or not value.is_file():
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be a regular non-symlink file"
        )
    return value


def _decode_canonical_json(
    payload: str,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} payload must be non-empty")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} JSON is malformed") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} JSON must be an object")
    if payload != _canonical(document):
        raise ValueError(f"{label} JSON must be canonical")
    return document


def _require_mapping(
    value: object,
    label: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be an object"
        )
    return value


def _optional_finite(value: object, label: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be finite or null"
        )
    return float(value)


def _optional_non_negative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be a non-negative integer or null"
        )
    return value


def _non_negative_int(value: object, label: str) -> int:
    result = _optional_non_negative_int(value, label)
    if result is None:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must not be null"
        )
    return result


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowPromotionReadinessError(
            f"{label} must be lowercase SHA-256"
        )
    return value


def _require_sha256_value(label: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _finite_policy(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _non_negative_policy(name: str, value: object) -> float:
    number = _finite_policy(name, value)
    if number < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _percent_policy(name: str, value: object) -> float:
    number = _finite_policy(name, value)
    if not 0.0 <= number <= 100.0:
        raise ValueError(f"{name} must be within [0, 100]")
    return number


def _fraction_policy(name: str, value: object) -> float:
    number = _finite_policy(name, value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
    return number


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
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


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
        prog="shreks-fast-paper-shadow-promotion-readiness"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--sample-proof-path", required=True)
    parser.add_argument("--trade-economics-path", required=True)
    parser.add_argument("--missed-opportunity-path", required=True)
    parser.add_argument("--latency-proof-path", required=True)
    parser.add_argument("--promotion-policy-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = collect_fast_paper_shadow_promotion_readiness(
            manifest_path=args.manifest_path,
            sample_proof_path=args.sample_proof_path,
            trade_economics_path=args.trade_economics_path,
            missed_opportunity_path=args.missed_opportunity_path,
            latency_proof_path=args.latency_proof_path,
            promotion_policy_path=args.promotion_policy_path,
            expected_release_sha=args.expected_release_sha,
        )
    except (FastPaperShadowPromotionReadinessError, ValueError) as exc:
        print(
            _canonical(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_promotion_readiness_failure"
                    ),
                    "schema_version": (
                        FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_VERSION
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
        canonical_fast_paper_shadow_promotion_readiness(report),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
