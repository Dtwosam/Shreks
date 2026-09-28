from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

import shreks_brain.fast_paper_shadow_promotion_readiness as readiness


_SHA = "a" * 40
_MANIFEST = "b" * 64
_CHAMPION = "c" * 64
_BINDING = "d" * 64


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _finalize(material: dict[str, object]) -> dict[str, object]:
    return {
        **material,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _identity() -> dict[str, object]:
    return {
        "release_source_sha": _SHA,
        "manifest_fingerprint_sha256": _MANIFEST,
        "champion_version": "fast-champion-v1",
        "champion_fingerprint_sha256": _CHAMPION,
        "action_policy_version": "fast-action-v1",
        "binding_fingerprint_sha256": _BINDING,
        "window_since_unix_ms": 1_000,
        "window_until_unix_ms": 2_000,
        "window_duration_ms": 1_000,
    }


def _sample() -> dict[str, object]:
    return _finalize(
        {
            "schema_name": "shreks.fast_paper_shadow_independent_sample",
            "schema_version": 1,
            "policy_version": "sample-v1",
            **_identity(),
            "decision_count": 20,
            "closed_position_count": 10,
            "decision": "SUFFICIENT_SAMPLE",
            "promotion_authority": "NOT_GRANTED",
            "production_paper_cutover": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _economics(sample: dict[str, object]) -> dict[str, object]:
    return _finalize(
        {
            "schema_name": "shreks.fast_paper_shadow_trade_economics",
            "schema_version": 1,
            **_identity(),
            "sample_proof_fingerprint_sha256": sample[
                "report_fingerprint_sha256"
            ],
            "closed_trade_count": 10,
            "sealed_e5_report": {
                "metrics": {
                    "trade_count": 10,
                    "net_expectancy_pct": 1.25,
                    "profit_factor": 1.8,
                    "maximum_drawdown_pct": 4.0,
                    "cost_burden_pct": 0.8,
                }
            },
            "loss_tail": {
                "worst_net_return_bps": -80.0,
            },
            "expected_realized_value_bps": {
                "mean_absolute_error_bps": 25.0,
            },
            "entry_efficiency": {
                "signed_slippage_bps": {
                    "p95": 12.0,
                }
            },
            "entry_capital_utilization": {
                "entry_notional_to_trading_capital_pct": {
                    "p95": 20.0,
                }
            },
            "promotion_authority": "NOT_GRANTED",
            "production_paper_cutover": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _missed(sample: dict[str, object]) -> dict[str, object]:
    return _finalize(
        {
            "schema_name": "shreks.fast_paper_shadow_missed_opportunity",
            "schema_version": 1,
            **_identity(),
            "sample_proof_fingerprint_sha256": sample[
                "report_fingerprint_sha256"
            ],
            "skip_decision_count": 5,
            "missed_opportunity_evidence_state": "COMPLETE",
            "fully_scorable_skip_count": 5,
            "partially_or_unscorable_skip_count": 0,
            "positive_missed_opportunity_rate": 0.2,
            "best_missed_opportunity_bps": {
                "mean": 15.0,
            },
            "promotion_authority": "NOT_GRANTED",
            "production_paper_cutover": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _latency(sample: dict[str, object]) -> dict[str, object]:
    return _finalize(
        {
            "schema_name": "shreks.fast_paper_shadow_latency_proof",
            "schema_version": 1,
            **_identity(),
            "sample_proof_fingerprint_sha256": sample[
                "report_fingerprint_sha256"
            ],
            "decision": "LATENCY_PROVEN",
            "promotion_authority": "NOT_GRANTED",
            "production_paper_cutover": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _policy(**changes: object) -> readiness.FastPaperShadowPromotionPolicy:
    values: dict[str, object] = {
        "version": "fl11.4-test-v1",
        "min_net_expectancy_pct": 0.5,
        "min_profit_factor": 1.2,
        "max_drawdown_pct": 10.0,
        "max_cost_burden_pct": 2.0,
        "max_worst_loss_bps": 150.0,
        "max_expected_realized_mae_bps": 50.0,
        "max_entry_slippage_p95_bps": 25.0,
        "max_entry_capital_utilization_p95_pct": 50.0,
        "max_missed_opportunity_rate": 0.5,
        "max_missed_opportunity_mean_bps": 30.0,
    }
    values.update(changes)
    return readiness.FastPaperShadowPromotionPolicy(**values)


def _assess(
    *,
    economics_mutator=None,
    missed_mutator=None,
    latency_mutator=None,
    policy: readiness.FastPaperShadowPromotionPolicy | None = None,
):
    sample = _sample()
    economics = _economics(sample)
    missed = _missed(sample)
    latency = _latency(sample)
    if economics_mutator is not None:
        economics = economics_mutator(economics)
    if missed_mutator is not None:
        missed = missed_mutator(missed)
    if latency_mutator is not None:
        latency = latency_mutator(latency)
    return readiness.assess_fast_paper_shadow_promotion_readiness(
        sample_report=sample,
        trade_economics_report=economics,
        missed_opportunity_report=missed,
        latency_report=latency,
        policy=_policy() if policy is None else policy,
    )


def _refinalize(document: dict[str, object]) -> dict[str, object]:
    material = dict(document)
    material.pop("report_fingerprint_sha256", None)
    return _finalize(material)


def test_passing_bound_chain_is_promotion_ready() -> None:
    report = _assess()

    assert report["decision"] == "PROMOTION_READY"
    assert {gate["status"] for gate in report["gate_results"]} == {"PASS"}
    assert report["champion_version"] == "fast-champion-v1"
    assert report["champion_fingerprint_sha256"] == _CHAMPION
    assert report["promotion_authority"] == "NOT_GRANTED"
    assert report["production_paper_cutover"] == "NOT_GRANTED"
    assert report["signing_submission_authority"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"

    fingerprint = report["report_fingerprint_sha256"]
    material = dict(report)
    material.pop("report_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        readiness.canonical_fast_paper_shadow_promotion_readiness(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_economic_threshold_breach_is_not_ready() -> None:
    report = _assess(policy=_policy(min_net_expectancy_pct=2.0))

    assert report["decision"] == "PROMOTION_NOT_READY"
    by_code = {gate["code"]: gate for gate in report["gate_results"]}
    assert by_code["MIN_NET_EXPECTANCY_PCT"]["status"] == "FAIL"
    assert by_code["MIN_NET_EXPECTANCY_PCT"]["observed_value"] == pytest.approx(
        1.25
    )


def test_non_proven_latency_is_not_ready() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["decision"] = "LATENCY_NOT_PROVEN"
        return _refinalize(document)

    report = _assess(latency_mutator=mutate)

    assert report["decision"] == "PROMOTION_NOT_READY"
    by_code = {gate["code"]: gate for gate in report["gate_results"]}
    assert by_code["FL11_3_LATENCY_PROVEN"]["status"] == "FAIL"


def test_unavailable_required_metric_fails_closed() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["sealed_e5_report"]["metrics"]["profit_factor"] = None
        return _refinalize(document)

    report = _assess(economics_mutator=mutate)

    assert report["decision"] == "PROMOTION_NOT_READY"
    by_code = {gate["code"]: gate for gate in report["gate_results"]}
    assert by_code["MIN_PROFIT_FACTOR"]["status"] == "FAIL"
    assert by_code["MIN_PROFIT_FACTOR"]["observed_value"] is None


def test_partial_missed_opportunity_evidence_fails_readiness() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["missed_opportunity_evidence_state"] = "PARTIAL"
        document["fully_scorable_skip_count"] = 4
        document["partially_or_unscorable_skip_count"] = 1
        return _refinalize(document)

    report = _assess(missed_mutator=mutate)

    assert report["decision"] == "PROMOTION_NOT_READY"
    by_code = {gate["code"]: gate for gate in report["gate_results"]}
    assert by_code["MISSED_OPPORTUNITY_EVIDENCE_COMPLETE"]["status"] == "FAIL"


def test_zero_skip_decisions_are_explicit_zero_missed_opportunity() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["skip_decision_count"] = 0
        document["missed_opportunity_evidence_state"] = "NO_SKIP_DECISIONS"
        document["fully_scorable_skip_count"] = 0
        document["partially_or_unscorable_skip_count"] = 0
        document["positive_missed_opportunity_rate"] = None
        document["best_missed_opportunity_bps"] = {
            "mean": None,
        }
        return _refinalize(document)

    report = _assess(missed_mutator=mutate)

    assert report["decision"] == "PROMOTION_READY"
    observed = report["observed_metrics"]
    assert observed["missed_opportunity_rate"] == 0.0
    assert observed["missed_opportunity_mean_bps"] == 0.0


def test_report_fingerprint_drift_is_rejected() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["report_fingerprint_sha256"] = "0" * 64
        return document

    with pytest.raises(
        readiness.FastPaperShadowPromotionReadinessError,
        match="fingerprint",
    ):
        _assess(economics_mutator=mutate)


def test_cross_report_champion_drift_is_rejected() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["champion_fingerprint_sha256"] = "e" * 64
        return _refinalize(document)

    with pytest.raises(
        readiness.FastPaperShadowPromotionReadinessError,
        match="champion_fingerprint_sha256 mismatch",
    ):
        _assess(missed_mutator=mutate)


def test_cross_report_sample_fingerprint_drift_is_rejected() -> None:
    def mutate(document: dict[str, object]) -> dict[str, object]:
        document["sample_proof_fingerprint_sha256"] = "f" * 64
        return _refinalize(document)

    with pytest.raises(
        readiness.FastPaperShadowPromotionReadinessError,
        match="sample proof fingerprint mismatch",
    ):
        _assess(latency_mutator=mutate)


def test_policy_codec_is_canonical_fingerprinted_and_strict() -> None:
    policy = _policy()
    payload = readiness.encode_fast_paper_shadow_promotion_policy(policy)
    decoded = readiness.decode_fast_paper_shadow_promotion_policy(payload)

    assert decoded == policy
    document = json.loads(payload)
    assert document["policy_fingerprint_sha256"] == (
        readiness.fast_paper_shadow_promotion_policy_fingerprint_sha256(policy)
    )

    document["unknown"] = True
    with pytest.raises(ValueError, match="unknown or missing"):
        readiness.decode_fast_paper_shadow_promotion_policy(
            _canonical(document)
        )


def test_packaging_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_paper_shadow_promotion_readiness.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "python" / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-promotion-readiness = '
        '"shreks_brain.fast_paper_shadow_promotion_readiness:main"'
    ) in pyproject

    forbidden = (
        "shreks_brain.registry",
        "shreks_brain.promotion",
        "score_candidate",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "LIVE_ENABLED",
    )
    for token in forbidden:
        assert token not in source
