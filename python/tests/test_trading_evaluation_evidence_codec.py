from __future__ import annotations

from copy import deepcopy
import math

import pytest

from shreks_brain.evaluation import (
    EvaluatedTrade,
    ProbabilityObservation,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.evaluation.codec import (
    EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION,
    build_evidence,
    build_evidence_document,
    canonical_json,
    decode_evidence_document,
)
from shreks_brain.evaluation.evidence import TradingEvaluationEvidence


CANDIDATE = "challenger-v1"


def _policy() -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="eval-v1",
        starting_equity_usd=1_000.0,
        calibration_bucket_count=4,
    )


def _trade(
    position_id: str,
    opened: int,
    closed: int,
    net: float,
    *,
    setup: str = "fresh",
    regime: str = "NORMAL",
    candidate_version: str = CANDIDATE,
) -> EvaluatedTrade:
    friction = 1.0
    explicit = 0.5
    return EvaluatedTrade(
        candidate_version=candidate_version,
        position_id=position_id,
        candidate_mint=f"mint-{position_id}",
        setup_name=setup,
        market_regime=regime,
        opened_at_unix_ms=opened,
        closed_at_unix_ms=closed,
        entry_notional_usd=100.0,
        turnover_usd=200.0,
        gross_pnl_usd=net + friction + explicit,
        execution_friction_usd=friction,
        explicit_cost_usd=explicit,
        net_pnl_usd=net,
    )


def _trades() -> tuple[EvaluatedTrade, ...]:
    return (
        _trade("p2", 200, 400, -4.0, setup="graduation", regime="HOT"),
        _trade("p1", 100, 300, 8.0),
    )


def _observation(
    mint: str,
    as_of: int,
    probability: float,
    target: bool,
    *,
    candidate_version: str = CANDIDATE,
) -> ProbabilityObservation:
    return ProbabilityObservation(
        candidate_version=candidate_version,
        model_version="model-v1",
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        positive_probability=probability,
        target_positive=target,
        setup_name="fresh",
        market_regime="NORMAL",
        fold_name="fold-1",
    )


def _observations() -> tuple[ProbabilityObservation, ...]:
    return (
        _observation("mint-b", 200, 0.7, True),
        _observation("mint-a", 100, 0.2, False),
    )


def _evidence() -> TradingEvaluationEvidence:
    return build_evidence(CANDIDATE, _trades(), _observations(), _policy())


def _document() -> dict[str, object]:
    return build_evidence_document((_evidence(),))


def _record(document: dict[str, object]) -> dict[str, object]:
    evaluations = document["evaluations"]
    assert isinstance(evaluations, list)
    record = evaluations[0]
    assert isinstance(record, dict)
    return record


def test_build_evidence_reconstructs_exact_e5_report_and_canonical_sources() -> None:
    evidence = _evidence()
    expected = evaluate_trading_performance(
        _trades(), _observations(), _policy(), CANDIDATE
    )

    assert evidence.candidate_version == CANDIDATE
    assert evidence.report == expected
    assert tuple(value.position_id for value in evidence.trades) == ("p1", "p2")
    assert tuple(value.candidate_mint for value in evidence.probability_observations) == (
        "mint-a",
        "mint-b",
    )


def test_source_evidence_document_round_trips_exact_bundle() -> None:
    evidence = _evidence()

    document = build_evidence_document((evidence,))

    assert document["schema_version"] == EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION
    assert decode_evidence_document(document) == (evidence,)


def test_document_persists_only_source_evidence_and_e5_fingerprint() -> None:
    record = _record(_document())

    assert set(record) == {
        "candidate_version",
        "evaluation_fingerprint_sha256",
        "policy",
        "trades",
        "probability_observations",
    }
    assert "report" not in record
    assert "metrics" not in record
    assert "calibration" not in record
    assert record["evaluation_fingerprint_sha256"] == _evidence().report.evaluation_fingerprint_sha256


def test_valid_source_tamper_with_stale_fingerprint_fails_closed() -> None:
    document = _document()
    record = _record(document)
    trades = record["trades"]
    assert isinstance(trades, list)
    trade = trades[0]
    assert isinstance(trade, dict)
    trade["setup_name"] = "tampered-setup"

    with pytest.raises(ValueError, match="evaluation fingerprint"):
        decode_evidence_document(document)


def test_probability_source_tamper_with_stale_fingerprint_fails_closed() -> None:
    document = _document()
    record = _record(document)
    observations = record["probability_observations"]
    assert isinstance(observations, list)
    observation = observations[0]
    assert isinstance(observation, dict)
    observation["fold_name"] = "tampered-fold"

    with pytest.raises(ValueError, match="evaluation fingerprint"):
        decode_evidence_document(document)


def test_decode_rejects_unknown_fields_at_every_layer() -> None:
    document = _document()
    document["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_evidence_document(document)

    document = _document()
    _record(document)["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_evidence_document(document)

    document = _document()
    policy = _record(document)["policy"]
    assert isinstance(policy, dict)
    policy["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_evidence_document(document)

    document = _document()
    trades = _record(document)["trades"]
    assert isinstance(trades, list)
    assert isinstance(trades[0], dict)
    trades[0]["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_evidence_document(document)

    document = _document()
    observations = _record(document)["probability_observations"]
    assert isinstance(observations, list)
    assert isinstance(observations[0], dict)
    observations[0]["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        decode_evidence_document(document)


def test_decode_rejects_wrong_schema_and_bad_fingerprint_shape() -> None:
    document = _document()
    document["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema"):
        decode_evidence_document(document)

    document = _document()
    _record(document)["evaluation_fingerprint_sha256"] = "bad"
    with pytest.raises(ValueError, match="SHA-256|fingerprint"):
        decode_evidence_document(document)


def test_decode_rejects_non_finite_numeric_source() -> None:
    document = _document()
    policy = _record(document)["policy"]
    assert isinstance(policy, dict)
    policy["starting_equity_usd"] = math.inf

    with pytest.raises(ValueError, match="finite"):
        decode_evidence_document(document)


def test_decode_rejects_candidate_version_mismatch() -> None:
    document = _document()
    trades = _record(document)["trades"]
    assert isinstance(trades, list)
    assert isinstance(trades[0], dict)
    trades[0]["candidate_version"] = "other"

    with pytest.raises(ValueError, match="candidate_version"):
        decode_evidence_document(document)


def test_decode_rejects_duplicate_trade_and_observation_identities() -> None:
    document = _document()
    trades = _record(document)["trades"]
    assert isinstance(trades, list)
    trades.append(deepcopy(trades[0]))
    with pytest.raises(ValueError, match="duplicate trade position_id"):
        decode_evidence_document(document)

    document = _document()
    observations = _record(document)["probability_observations"]
    assert isinstance(observations, list)
    observations.append(deepcopy(observations[0]))
    with pytest.raises(ValueError, match="duplicate probability observation identity"):
        decode_evidence_document(document)


def test_decode_rejects_non_canonical_persisted_source_order() -> None:
    document = _document()
    trades = _record(document)["trades"]
    assert isinstance(trades, list)
    trades.reverse()
    with pytest.raises(ValueError, match="canonical order"):
        decode_evidence_document(document)

    document = _document()
    observations = _record(document)["probability_observations"]
    assert isinstance(observations, list)
    observations.reverse()
    with pytest.raises(ValueError, match="canonical order"):
        decode_evidence_document(document)


def test_decode_rejects_duplicate_evaluation_identity() -> None:
    document = _document()
    evaluations = document["evaluations"]
    assert isinstance(evaluations, list)
    evaluations.append(deepcopy(evaluations[0]))

    with pytest.raises(ValueError, match="duplicate evaluation identity"):
        decode_evidence_document(document)


def test_canonical_json_is_compact_sorted_utf8_and_rejects_nan() -> None:
    assert canonical_json({"b": 2, "a": "é"}) == '{"a":"é","b":2}'

    with pytest.raises(ValueError, match="canonical-JSON"):
        canonical_json({"x": math.nan})
