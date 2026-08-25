from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.evaluation import (
    EvaluatedTrade,
    ProbabilityObservation,
    TradingEvaluationPolicy,
)
from shreks_brain.evaluation.codec import build_evidence, build_evidence_document, canonical_json
from shreks_brain.evaluation.store import TradingEvaluationEvidenceStore


CANDIDATE = "challenger-v1"


def _policy(*, version: str = "eval-v1") -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version=version,
        starting_equity_usd=1_000.0,
        calibration_bucket_count=4,
    )


def _trade(position_id: str, opened: int, closed: int, net: float) -> EvaluatedTrade:
    return EvaluatedTrade(
        candidate_version=CANDIDATE,
        position_id=position_id,
        candidate_mint=f"mint-{position_id}",
        setup_name="fresh",
        market_regime="NORMAL",
        opened_at_unix_ms=opened,
        closed_at_unix_ms=closed,
        entry_notional_usd=100.0,
        turnover_usd=200.0,
        gross_pnl_usd=net + 1.5,
        execution_friction_usd=1.0,
        explicit_cost_usd=0.5,
        net_pnl_usd=net,
    )


def _trades(*, second_net: float = -4.0) -> tuple[EvaluatedTrade, ...]:
    return (
        _trade("p2", 200, 400, second_net),
        _trade("p1", 100, 300, 8.0),
    )


def _observation(mint: str, as_of: int, probability: float, target: bool) -> ProbabilityObservation:
    return ProbabilityObservation(
        candidate_version=CANDIDATE,
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


def test_missing_store_loads_empty_and_get_returns_none(tmp_path: Path) -> None:
    store = TradingEvaluationEvidenceStore(tmp_path / "evaluations.json")

    assert store.load() == ()
    assert store.get(CANDIDATE, "a" * 64) is None


def test_append_round_trips_after_restart_and_reconstructs_report(tmp_path: Path) -> None:
    path = tmp_path / "evaluations.json"
    store = TradingEvaluationEvidenceStore(path)

    appended = store.append(CANDIDATE, _trades(), _observations(), _policy())
    expected = build_evidence(CANDIDATE, _trades(), _observations(), _policy())

    assert appended == (expected,)
    restarted = TradingEvaluationEvidenceStore(path)
    assert restarted.load() == (expected,)
    assert restarted.get(CANDIDATE, expected.report.evaluation_fingerprint_sha256) == expected


def test_exact_repeated_evaluation_is_idempotent(tmp_path: Path) -> None:
    store = TradingEvaluationEvidenceStore(tmp_path / "evaluations.json")

    first = store.append(CANDIDATE, _trades(), _observations(), _policy())
    second = store.append(CANDIDATE, _trades(), _observations(), _policy())

    assert first == second
    assert len(second) == 1


def test_distinct_evaluations_for_same_candidate_append_in_order(tmp_path: Path) -> None:
    store = TradingEvaluationEvidenceStore(tmp_path / "evaluations.json")

    first = store.append(CANDIDATE, _trades(), _observations(), _policy())[0]
    values = store.append(CANDIDATE, _trades(second_net=-2.0), _observations(), _policy())

    assert len(values) == 2
    assert values[0] == first
    assert values[1].report.evaluation_fingerprint_sha256 != first.report.evaluation_fingerprint_sha256


def test_store_writes_canonical_json_single_newline_and_no_tmp(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "evaluations.json"
    store = TradingEvaluationEvidenceStore(path)
    evidence = store.append(CANDIDATE, _trades(), _observations(), _policy())

    text = path.read_text(encoding="utf-8")
    assert text == canonical_json(build_evidence_document(evidence)) + "\n"
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not path.with_name(path.name + ".tmp").exists()


def test_load_wraps_malformed_json_as_invalid_evidence_file(tmp_path: Path) -> None:
    path = tmp_path / "evaluations.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="evaluation evidence file is invalid"):
        TradingEvaluationEvidenceStore(path).load()


def test_load_rejects_tampered_source_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "evaluations.json"
    TradingEvaluationEvidenceStore(path).append(CANDIDATE, _trades(), _observations(), _policy())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["evaluations"][0]["trades"][0]["setup_name"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="evaluation fingerprint"):
        TradingEvaluationEvidenceStore(path).load()


def test_get_requires_valid_identity_values(tmp_path: Path) -> None:
    store = TradingEvaluationEvidenceStore(tmp_path / "evaluations.json")

    for invalid_candidate in ("", "   ", 123, None):
        with pytest.raises(ValueError, match="candidate_version"):
            store.get(invalid_candidate, "a" * 64)  # type: ignore[arg-type]

    for invalid_fingerprint in ("", "abc", "A" * 64, 123, None):
        with pytest.raises(ValueError, match="fingerprint|SHA-256"):
            store.get(CANDIDATE, invalid_fingerprint)  # type: ignore[arg-type]


def test_append_requires_exact_e5_source_types(tmp_path: Path) -> None:
    store = TradingEvaluationEvidenceStore(tmp_path / "evaluations.json")

    with pytest.raises(ValueError, match="trades"):
        store.append(CANDIDATE, [], _observations(), _policy())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="probability_observations"):
        store.append(CANDIDATE, _trades(), [], _policy())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="policy"):
        store.append(CANDIDATE, _trades(), _observations(), object())  # type: ignore[arg-type]


def test_replace_failure_cleans_tmp_and_preserves_prior_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "evaluations.json"
    store = TradingEvaluationEvidenceStore(path)
    first = store.append(CANDIDATE, _trades(), _observations(), _policy())

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("shreks_brain.evaluation.store.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.append(CANDIDATE, _trades(second_net=-2.0), _observations(), _policy())

    assert not path.with_name(path.name + ".tmp").exists()
    assert TradingEvaluationEvidenceStore(path).load() == first
