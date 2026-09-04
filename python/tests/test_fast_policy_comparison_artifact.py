from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.evaluation import (
    EvaluatedTrade,
    TradingEvaluationEvidence,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.fast_deterministic_campaign import (
    FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME,
    FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION,
    FastPolicyComparisonArtifact,
    FastPolicyComparisonArtifactManifest,
    read_fast_policy_comparison_artifact,
    write_fast_policy_comparison_artifact,
)
from shreks_brain.fast_paper import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperEventRecord,
    FastPaperLoopState,
    FastPaperMarketCursor,
)
from shreks_brain.fast_policy_proof import (
    FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_NAME,
    FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_VERSION,
    FastPolicyProofDecision,
    FastPolicySuperiorityPolicy,
    build_fast_policy_run_evidence,
    decode_fast_policy_superiority_policy,
    encode_fast_policy_superiority_policy,
)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run(candidate: str, sha: str, pnls: tuple[float, float]):
    records = tuple(
        FastPaperEventRecord(
            source_event_id=f"event-{index}",
            update_fingerprint=str(index) * 64,
            market_key="market-a",
            source_sequence=index,
            as_of_unix_ms=1_000 + index * 500,
            is_material=True,
            assessment=FastPaperActionAssessment(
                version="assessment-v1",
                source_event_id=f"event-{index}",
                market_key="market-a",
                source_sequence=index,
                as_of_unix_ms=1_000 + index * 500,
                strategy_family=candidate,
                strategy_version=f"{candidate}-v1",
                action=(
                    FastPaperAction.BUY
                    if index == 1
                    else FastPaperAction.SELL
                ),
                reasons=("fixture",),
            ),
        )
        for index in (1, 2)
    )
    loop = FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(FastPaperMarketCursor("market-a", 2, 2_000),),
        records=records,
    )
    evaluation_policy = TradingEvaluationPolicy(
        "eval-v1",
        10_000.0,
        10,
    )
    trades = tuple(
        EvaluatedTrade(
            candidate_version=candidate,
            position_id=f"{candidate}-{index}",
            candidate_mint=f"mint-{index}",
            setup_name="fast-policy",
            market_regime="NORMAL",
            opened_at_unix_ms=1_550,
            closed_at_unix_ms=1_700 + index * 100,
            entry_notional_usd=100.0,
            turnover_usd=210.0,
            gross_pnl_usd=pnl + 2.0,
            execution_friction_usd=1.0,
            explicit_cost_usd=1.0,
            net_pnl_usd=pnl,
        )
        for index, pnl in enumerate(pnls, start=1)
    )
    report = evaluate_trading_performance(
        trades,
        (),
        evaluation_policy,
        candidate,
    )
    evaluation = TradingEvaluationEvidence(
        candidate,
        evaluation_policy,
        trades,
        (),
        report,
    )
    return build_fast_policy_run_evidence(
        paper_run_id=f"run-{candidate}",
        candidate_fingerprint_sha256=sha,
        strategy_version=f"{candidate}-strategy-v1",
        loop_state=loop,
        trading_evaluation=evaluation,
    )


def _baselines():
    return tuple(
        _run(
            f"baseline-{index:02d}",
            f"{index + 1:064x}",
            (5.0, -5.0),
        )
        for index in range(8)
    )


def _learned():
    return _run(
        "learned-v1",
        "a" * 64,
        (25.0, -5.0),
    )


def _policy() -> FastPolicySuperiorityPolicy:
    versions = tuple(
        f"baseline-{index:02d}"
        for index in range(8)
    )
    return FastPolicySuperiorityPolicy(
        version="proof-v1",
        required_baseline_versions=versions,
        min_material_decision_count=2,
        min_distinct_market_count=1,
        min_evaluation_span_ms=500,
        min_trade_count=2,
        min_distinct_traded_mint_count=2,
        min_net_expectancy_pct=-100.0,
        min_profit_factor=0.0,
        max_drawdown_pct=100.0,
        max_cost_burden_pct=100.0,
        max_single_winner_share_of_positive_pnl=1.0,
        min_baseline_expectancy_advantage_pct=-100.0,
    )


def _fake_baseline_chain(monkeypatch, tmp_path: Path):
    invocation_path = tmp_path / "campaign.invocation"
    invocation_path.mkdir()
    campaign_path = tmp_path / "campaign"
    campaign_path.mkdir()
    baselines = _baselines()
    population = baselines[0].event_population_fingerprint_sha256
    invocation_manifest = SimpleNamespace(
        request_fingerprint_sha256="b" * 64,
        campaign_artifact_fingerprint_sha256="c" * 64,
        campaign_directory_name="campaign",
        invocation_fingerprint_sha256="d" * 64,
    )
    invocation = SimpleNamespace(
        path=invocation_path,
        manifest=invocation_manifest,
    )
    candidates = tuple(
        SimpleNamespace(candidate_version=value.candidate_version)
        for value in baselines
    )
    campaign_manifest = SimpleNamespace(
        artifact_fingerprint_sha256="c" * 64,
        catalog_fingerprint_sha256="e" * 64,
        run_batch_fingerprint_sha256="f" * 64,
        event_population_fingerprint_sha256=population,
        run_count=8,
    )
    campaign = SimpleNamespace(
        manifest=campaign_manifest,
        catalog=SimpleNamespace(candidates=candidates),
        runs=baselines,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.proof_artifact."
        "read_fast_deterministic_campaign_invocation_seal",
        lambda path: invocation,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.proof_artifact."
        "read_fast_deterministic_campaign_artifact",
        lambda path: campaign,
    )
    return invocation, campaign


def test_superiority_policy_codec_is_canonical_and_authenticated() -> None:
    policy = _policy()

    payload = encode_fast_policy_superiority_policy(policy)
    document = json.loads(payload)

    assert document["schema_name"] == (
        FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_NAME
    )
    assert document["schema_version"] == (
        FAST_POLICY_SUPERIORITY_POLICY_SCHEMA_VERSION
    )
    assert payload == _canonical(document)
    assert decode_fast_policy_superiority_policy(payload) == policy

    tampered = dict(document)
    tampered["min_trade_count"] += 1
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_policy_superiority_policy(_canonical(tampered))


def test_comparison_artifact_binds_invocation_learned_run_policy_and_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    invocation, campaign = _fake_baseline_chain(monkeypatch, tmp_path)
    destination = tmp_path / "comparison.proof"

    manifest = write_fast_policy_comparison_artifact(
        baseline_invocation_path=invocation.path,
        learned_run=_learned(),
        superiority_policy=_policy(),
        destination=destination,
    )

    assert type(manifest) is FastPolicyComparisonArtifactManifest
    assert manifest.schema_name == (
        FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME
    )
    assert manifest.schema_version == (
        FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION
    )
    assert manifest.baseline_invocation_fingerprint_sha256 == (
        invocation.manifest.invocation_fingerprint_sha256
    )
    assert manifest.baseline_campaign_artifact_fingerprint_sha256 == (
        campaign.manifest.artifact_fingerprint_sha256
    )
    assert manifest.baseline_run_count == 8
    assert manifest.learned_candidate_version == "learned-v1"
    assert manifest.decision == FastPolicyProofDecision.SUPERIOR.value
    assert len(manifest.artifact_fingerprint_sha256) == 64

    assert {path.name for path in destination.iterdir()} == {
        "learned_run.json",
        "superiority_policy.json",
        "superiority_report.json",
        "manifest.json",
    }
    for name in (
        "learned_run.json",
        "superiority_policy.json",
        "superiority_report.json",
        "manifest.json",
    ):
        payload = (destination / name).read_text(encoding="utf-8")
        assert payload == _canonical(json.loads(payload))

    artifact = read_fast_policy_comparison_artifact(destination)
    assert type(artifact) is FastPolicyComparisonArtifact
    assert artifact.manifest == manifest
    assert artifact.learned_run.candidate_version == "learned-v1"
    assert artifact.baseline_runs == campaign.runs
    assert artifact.superiority_policy == _policy()
    assert artifact.superiority_report.decision is (
        FastPolicyProofDecision.SUPERIOR
    )


def test_comparison_artifact_requires_exact_catalog_baseline_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    invocation, _ = _fake_baseline_chain(monkeypatch, tmp_path)
    policy = replace(
        _policy(),
        required_baseline_versions=(
            *tuple(
                f"baseline-{index:02d}"
                for index in range(7)
            ),
            "other-baseline",
        ),
    )
    destination = tmp_path / "comparison-invalid"

    with pytest.raises(ValueError, match="baseline|catalog|required"):
        write_fast_policy_comparison_artifact(
            baseline_invocation_path=invocation.path,
            learned_run=_learned(),
            superiority_policy=policy,
            destination=destination,
        )

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".comparison-invalid-*"))


def test_comparison_artifact_reader_rejects_child_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    invocation, _ = _fake_baseline_chain(monkeypatch, tmp_path)
    destination = tmp_path / "comparison-tamper"
    write_fast_policy_comparison_artifact(
        baseline_invocation_path=invocation.path,
        learned_run=_learned(),
        superiority_policy=_policy(),
        destination=destination,
    )

    run_path = destination / "learned_run.json"
    payload = run_path.read_text(encoding="utf-8")
    run_path.write_text(payload + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint|file|run|canonical"):
        read_fast_policy_comparison_artifact(destination)


def test_comparison_manifest_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="path component"):
        FastPolicyComparisonArtifactManifest(
            schema_name=FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME,
            schema_version=FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION,
            baseline_invocation_directory_name="../campaign.invocation",
            baseline_invocation_fingerprint_sha256="a" * 64,
            baseline_request_fingerprint_sha256="b" * 64,
            baseline_campaign_artifact_fingerprint_sha256="c" * 64,
            baseline_catalog_fingerprint_sha256="d" * 64,
            baseline_run_batch_fingerprint_sha256="e" * 64,
            baseline_run_count=8,
            baseline_event_population_fingerprint_sha256="f" * 64,
            learned_candidate_version="learned-v1",
            learned_candidate_fingerprint_sha256="1" * 64,
            learned_run_evidence_fingerprint_sha256="2" * 64,
            learned_run_batch_fingerprint_sha256="3" * 64,
            learned_event_population_fingerprint_sha256="4" * 64,
            superiority_policy_version="proof-v1",
            superiority_policy_fingerprint_sha256="5" * 64,
            superiority_report_fingerprint_sha256="6" * 64,
            decision="SUPERIOR",
            learned_run_file_sha256="7" * 64,
            superiority_policy_file_sha256="8" * 64,
            superiority_report_file_sha256="9" * 64,
            artifact_fingerprint_sha256="a" * 64,
        )


def test_comparison_artifact_source_has_no_promotion_network_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "proof_artifact.py"
    ).read_text(encoding="utf-8")

    assert "evaluate_fast_policy_superiority(" in source
    for forbidden in (
        "promotion",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "requests.",
        "httpx",
        "sqlite3",
    ):
        assert forbidden not in source
