from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime

import shreks_brain.fast_paper_shadow_sample_proof as proof

from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _record,
    _runtime_fixture,
    _source,
)


_SHA = "a" * 40
_MANIFEST = "b" * 64
_CHAMPION = "c" * 64
_BINDING = "d" * 64


def _policy(**overrides):
    values = {
        "version": "fl11-sample-v1",
        "min_decision_count": 4,
        "min_distinct_market_count": 3,
        "min_distinct_mint_count": 3,
        "min_observation_span_ms": 2_000,
        "min_closed_position_count": 2,
        "min_distinct_traded_mint_count": 2,
        "min_distinct_buy_regime_count": 2,
        "min_distinct_selected_horizon_count": 2,
    }
    values.update(overrides)
    return proof.FastPaperShadowSamplePolicy(**values)


def _decision(
    sequence: int,
    *,
    action: str,
    mint: str,
    market: str,
    as_of: int,
    horizon: int | None,
    fingerprint: str | None = None,
    champion_version: str = "champion-v1",
):
    digest = (
        hashlib.sha256(f"decision-{sequence}".encode()).hexdigest()
        if fingerprint is None
        else fingerprint
    )
    return SimpleNamespace(
        release_source_sha=_SHA,
        manifest_fingerprint_sha256=_MANIFEST,
        champion_version=champion_version,
        champion_fingerprint_sha256=_CHAMPION,
        action_policy_version=4,
        source_event_id=f"event-{sequence}",
        source_sequence=sequence,
        as_of_unix_ms=as_of,
        market_key=market,
        evidence_fingerprint_sha256=digest,
        feature_record=SimpleNamespace(mint=mint),
        decision=SimpleNamespace(
            action=action,
            selected_horizon_ms=horizon,
        ),
    )


def _checkpoint():
    positions = (
        SimpleNamespace(
            position_id="position-1",
            mint="mint-a",
            state=PaperPositionState.CLOSED,
            closed_at_unix_ms=2_500,
        ),
        SimpleNamespace(
            position_id="position-2",
            mint="mint-b",
            state=PaperPositionState.CLOSED,
            closed_at_unix_ms=3_500,
        ),
        SimpleNamespace(
            position_id="position-open",
            mint="mint-c",
            state=PaperPositionState.OPEN,
            closed_at_unix_ms=None,
        ),
    )
    return SimpleNamespace(
        state=SimpleNamespace(
            ledger=SimpleNamespace(positions=positions)
        )
    )


def test_sample_policy_requires_explicit_positive_thresholds() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _policy(min_decision_count=0)
    with pytest.raises(ValueError, match="positive integer"):
        _policy(min_distinct_buy_regime_count=True)
    with pytest.raises(ValueError, match="version"):
        _policy(version="")


def test_independent_sample_passes_only_with_broad_authenticated_sample() -> None:
    decisions = (
        _decision(
            1,
            action="BUY",
            mint="mint-a",
            market="market-a",
            as_of=1_000,
            horizon=1_000,
        ),
        _decision(
            2,
            action="SKIP",
            mint="mint-b",
            market="market-b",
            as_of=2_000,
            horizon=None,
        ),
        _decision(
            3,
            action="BUY",
            mint="mint-c",
            market="market-c",
            as_of=3_000,
            horizon=5_000,
        ),
        _decision(
            4,
            action="HOLD",
            mint="mint-a",
            market="market-a",
            as_of=4_000,
            horizon=5_000,
        ),
    )
    regimes = {
        decisions[0].evidence_fingerprint_sha256: MarketRegime.HOT,
        decisions[2].evidence_fingerprint_sha256: MarketRegime.WEAK,
    }

    result = proof.summarize_fast_paper_shadow_independent_sample(
        decisions,
        buy_regimes=regimes,
        missing_buy_execution_source_count=0,
        checkpoint=_checkpoint(),
        policy=_policy(),
        expected_release_sha=_SHA,
        binding_fingerprint_sha256=_BINDING,
        since_unix_ms=500,
        until_unix_ms=5_000,
    )

    assert result["decision"] == "SUFFICIENT_SAMPLE"
    assert result["decision_count"] == 4
    assert result["distinct_market_count"] == 3
    assert result["distinct_mint_count"] == 3
    assert result["observation_span_ms"] == 3_000
    assert result["closed_position_count"] == 2
    assert result["distinct_traded_mint_count"] == 2
    assert result["distinct_buy_regime_count"] == 2
    assert result["distinct_selected_horizon_count"] == 2
    assert result["action_counts"] == {
        "BUY": 2,
        "SKIP": 1,
        "HOLD": 1,
        "REDUCE": 0,
        "SELL": 0,
    }
    assert result["selected_horizon_counts"] == {
        "1000": 1,
        "5000": 2,
    }
    assert result["buy_regime_counts"] == {
        "HOT": 1,
        "NORMAL": 0,
        "WEAK": 1,
        "DEAD": 0,
    }
    assert {gate["status"] for gate in result["gate_results"]} == {"PASS"}
    assert result["promotion_authority"] == "NOT_GRANTED"
    assert result["production_paper_cutover"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"

    fingerprint = result["report_fingerprint_sha256"]
    material = dict(result)
    material.pop("report_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        proof.canonical_fast_paper_shadow_sample_proof(material).encode(
            "utf-8"
        )
    ).hexdigest()


def test_missing_buy_regime_or_narrow_sample_is_insufficient_not_promotable() -> None:
    first = _decision(
        1,
        action="BUY",
        mint="mint-a",
        market="market-a",
        as_of=1_000,
        horizon=1_000,
    )
    second = _decision(
        2,
        action="SKIP",
        mint="mint-a",
        market="market-a",
        as_of=1_100,
        horizon=None,
    )

    result = proof.summarize_fast_paper_shadow_independent_sample(
        (first, second),
        buy_regimes={},
        missing_buy_execution_source_count=1,
        checkpoint=None,
        policy=_policy(),
        expected_release_sha=_SHA,
        binding_fingerprint_sha256=_BINDING,
        since_unix_ms=500,
        until_unix_ms=2_000,
    )

    assert result["decision"] == "INSUFFICIENT_SAMPLE"
    by_code = {gate["code"]: gate for gate in result["gate_results"]}
    assert by_code["BUY_REGIME_EVIDENCE_COMPLETE"]["status"] == "INSUFFICIENT"
    assert by_code["MIN_CLOSED_POSITION_COUNT"]["status"] == "INSUFFICIENT"
    assert by_code["MIN_DISTINCT_MARKET_COUNT"]["status"] == "INSUFFICIENT"
    assert result["promotion_authority"] == "NOT_GRANTED"


def test_sample_proof_rejects_identity_drift_and_regime_for_non_buy() -> None:
    first = _decision(
        1,
        action="BUY",
        mint="mint-a",
        market="market-a",
        as_of=1_000,
        horizon=1_000,
    )
    changed = _decision(
        2,
        action="SKIP",
        mint="mint-b",
        market="market-b",
        as_of=2_000,
        horizon=None,
        champion_version="champion-v2",
    )
    with pytest.raises(proof.FastPaperShadowSampleProofError, match="identity"):
        proof.summarize_fast_paper_shadow_independent_sample(
            (first, changed),
            buy_regimes={
                first.evidence_fingerprint_sha256: MarketRegime.HOT
            },
            missing_buy_execution_source_count=0,
            checkpoint=None,
            policy=_policy(),
            expected_release_sha=_SHA,
            binding_fingerprint_sha256=_BINDING,
            since_unix_ms=500,
            until_unix_ms=3_000,
        )

    skip = _decision(
        2,
        action="SKIP",
        mint="mint-b",
        market="market-b",
        as_of=2_000,
        horizon=None,
    )
    with pytest.raises(
        proof.FastPaperShadowSampleProofError,
        match="non-BUY",
    ):
        proof.summarize_fast_paper_shadow_independent_sample(
            (first, skip),
            buy_regimes={
                first.evidence_fingerprint_sha256: MarketRegime.HOT,
                skip.evidence_fingerprint_sha256: MarketRegime.NORMAL,
            },
            missing_buy_execution_source_count=0,
            checkpoint=None,
            policy=_policy(),
            expected_release_sha=_SHA,
            binding_fingerprint_sha256=_BINDING,
            since_unix_ms=500,
            until_unix_ms=3_000,
        )


def test_collector_authenticates_real_shadow_buy_regime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, binding, execution_policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=__import__(
            "shreks_brain.fast_campaign",
            fromlist=["FastCampaignDecisionPosition"],
        ).FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_020,
        exit_observed_at=20_015,
    )
    source = _source(record, evidence)

    decisions = tmp_path / "decisions"
    sources = tmp_path / "execution-sources"
    decisions.mkdir()
    sources.mkdir()

    from shreks_brain.fast_paper_runtime import (
        produce_fast_paper_shadow_execution_input_source_record,
        write_fast_paper_runtime_manifest,
        write_fast_paper_shadow_decision_evidence,
        write_fast_paper_shadow_execution_input_source_record,
        write_fast_paper_shadow_execution_policy,
        execute_fast_paper_shadow_decision,
    )

    decision_path = (
        decisions
        / f"shadow-{evidence.source_sequence:020d}-"
        f"{evidence.evidence_fingerprint_sha256[:16]}.json"
    )
    write_fast_paper_shadow_decision_evidence(evidence, decision_path)
    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        execution_policy,
        checkpoint,
        posture,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        sources,
    )
    manifest_path = tmp_path / "manifest.json"
    execution_policy_path = tmp_path / "execution-policy.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    write_fast_paper_shadow_execution_policy(
        execution_policy,
        execution_policy_path,
    )

    transition = execute_fast_paper_shadow_decision(
        manifest,
        execution_policy,
        binding,
        checkpoint,
        posture,
        source,
    )
    _persist(
        manifest,
        binding,
        transition,
        sequence=1,
        created_at=20_060,
    )

    result = proof.collect_fast_paper_shadow_independent_sample(
        manifest_path=manifest_path,
        execution_policy_path=execution_policy_path,
        ledger_database_path=Path(binding.database_path),
        run_id=binding.run_id,
        decision_evidence_directory=decisions,
        execution_source_directory=sources,
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
        policy=_policy(
            min_decision_count=1,
            min_distinct_market_count=1,
            min_distinct_mint_count=1,
            min_observation_span_ms=1,
            min_closed_position_count=1,
            min_distinct_traded_mint_count=1,
            min_distinct_buy_regime_count=1,
            min_distinct_selected_horizon_count=1,
        ),
    )

    assert result["decision_count"] == 1
    assert result["missing_buy_execution_source_count"] == 0
    assert sum(result["buy_regime_counts"].values()) == 1
    assert result["distinct_buy_regime_count"] == 1
    assert result["decision"] == "INSUFFICIENT_SAMPLE"
    by_code = {gate["code"]: gate for gate in result["gate_results"]}
    assert by_code["BUY_REGIME_EVIDENCE_COMPLETE"]["status"] == "PASS"
    assert by_code["MIN_CLOSED_POSITION_COUNT"]["status"] == "INSUFFICIENT"


def test_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(proof.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-sample-proof = '
        '"shreks_brain.fast_paper_shadow_sample_proof:main"'
    ) in pyproject

    for forbidden in (
        "promote",
        "ChampionChallengerRegistry",
        "score_candidate",
        "shreks_brain.scoring",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
