from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignReduceExecutionCost,
)
from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.fast_deterministic_campaign import (
    FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME,
    FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION,
    FastLearnedComparisonRequest,
    FastLearnedComparisonRowInput,
    build_fast_learned_comparison_request,
    decode_fast_learned_comparison_request,
    encode_fast_learned_comparison_request,
    run_fast_learned_comparison_request_file,
)
from shreks_brain.fast_policy_proof import FastPolicySuperiorityPolicy


def _action_policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000, 5_000),
        entry_exposure_candidates=(0.25, 0.5),
        reduce_target_exposure_candidates=(0.25,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=100.0,
        route_unavailability_penalty_bps=125.0,
        horizon_disagreement_weight=0.5,
        minimum_buy_value_bps=50.0,
        minimum_hold_value_bps=25.0,
        missing_forecast_open_action="SELL",
    )


def _constraints(*, buy: bool = True) -> FastCampaignActionConstraints:
    return FastCampaignActionConstraints(
        max_exposure_fraction=0.5,
        buy_economically_allowed=buy,
        expected_future_exit_cost_bps=25.0,
        reduce_execution_costs=(
            FastCampaignReduceExecutionCost(
                target_exposure_fraction=0.25,
                execution_cost_bps=30.0,
            ),
        ),
        sell_executable=True,
        sell_now_cost_bps=30.0,
        force_sell=False,
    )


def _entry(mint: str = "mint-a") -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint=mint,
        quote_mint="quote-a",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=100,
        expected_entry_fixed_cost_quote=0.01,
    )


def _superiority() -> FastPolicySuperiorityPolicy:
    return FastPolicySuperiorityPolicy(
        version="fl9-superiority-v1",
        required_baseline_versions=tuple(
            f"baseline-{index:02d}" for index in range(8)
        ),
        min_material_decision_count=10,
        min_distinct_market_count=2,
        min_evaluation_span_ms=1_000,
        min_trade_count=2,
        min_distinct_traded_mint_count=2,
        min_net_expectancy_pct=0.0,
        min_profit_factor=1.0,
        max_drawdown_pct=20.0,
        max_cost_burden_pct=20.0,
        max_single_winner_share_of_positive_pnl=0.8,
        min_baseline_expectancy_advantage_pct=0.0,
    )


def _row(
    source_event_id: str = "sig-a:0",
    *,
    entry: FastCampaignPaperEntryAuthority | None = None,
) -> FastLearnedComparisonRowInput:
    return FastLearnedComparisonRowInput(
        source_event_id=source_event_id,
        flat_constraints=_constraints(),
        open_constraints=_constraints(buy=False),
        entry_authority=_entry() if entry is None else entry,
    )


def _request(
    *,
    rows: tuple[FastLearnedComparisonRowInput, ...] | None = None,
    decision_binary_sha256: str = "a" * 64,
) -> FastLearnedComparisonRequest:
    return build_fast_learned_comparison_request(
        baseline_invocation_path="baseline.invocation",
        champion_path="champion.json",
        decision_binary_path="campaign-decision",
        decision_binary_sha256=decision_binary_sha256,
        proof_destination_path="learned-comparison-proof",
        paper_run_id="learned-paper-run",
        candidate_version="learned-continuous-v1",
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-continuous-v1",
        assessment_version="assessment-v1",
        action_policy=_action_policy(),
        rows=(_row(),) if rows is None else rows,
        superiority_policy=_superiority(),
    )


def test_learned_comparison_request_codec_is_canonical_and_authenticated() -> None:
    request = _request()
    payload = encode_fast_learned_comparison_request(request)

    assert payload == json.dumps(
        json.loads(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert decode_fast_learned_comparison_request(payload) == request
    assert request.schema_name == FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_NAME
    assert request.schema_version == FAST_LEARNED_COMPARISON_REQUEST_SCHEMA_VERSION

    document = json.loads(payload)
    document["request"]["paper_run_id"] = "tampered"
    tampered = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_learned_comparison_request(tampered)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_invocation(tmp_path: Path, champion: Path):
    return SimpleNamespace(
        path=tmp_path / "baseline.invocation",
        manifest=SimpleNamespace(
            campaign_directory_name="baseline-campaign",
            campaign_artifact_fingerprint_sha256="c" * 64,
        ),
        request_payload="sealed-baseline-request",
        sources=(
            SimpleNamespace(
                label="champion_path",
                components=(
                    SimpleNamespace(
                        role="file",
                        file_name=champion.name,
                        sha256=_sha(champion),
                    ),
                ),
            ),
        ),
    )


def _fake_baseline_request():
    return SimpleNamespace(
        starting_cash_usd=20_000.0,
        starting_ledger_as_of_unix_ms=1_000,
        fill_policy=object(),
        risk_policy=object(),
        position_policy=object(),
        evaluation_policy=object(),
    )


def _bundle_row(
    source_event_id: str = "sig-a:0",
    *,
    mint: str = "mint-a",
):
    signature, ordinal = source_event_id.split(":")
    return SimpleNamespace(
        record=SimpleNamespace(
            decision_signature=signature,
            decision_ordinal=int(ordinal),
            mint=mint,
            quote_mint="quote-a",
            decision_executable_entry_price_quote=10.0,
        ),
        state_version="state-v1",
        evaluated_at_unix_ms=2_000,
        quote=None,
        entry_quote=object(),
        exit_quote=object(),
        market_regime=object(),
        risk_environment=object(),
    )


def _fake_campaign(rows):
    return SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256="c" * 64,
            event_population_fingerprint_sha256="e" * 64,
        ),
        comparison_bundle=SimpleNamespace(rows=tuple(rows)),
    )


def _write_request_file(
    tmp_path: Path,
    *,
    rows: tuple[FastLearnedComparisonRowInput, ...] | None = None,
):
    champion = tmp_path / "champion.json"
    champion.write_text("champion", encoding="utf-8")
    binary = tmp_path / "campaign-decision"
    binary.write_text("binary", encoding="utf-8")
    request = build_fast_learned_comparison_request(
        baseline_invocation_path="baseline.invocation",
        champion_path=champion.name,
        decision_binary_path=binary.name,
        decision_binary_sha256=_sha(binary),
        proof_destination_path="learned-comparison-proof",
        paper_run_id="learned-paper-run",
        candidate_version="learned-continuous-v1",
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-continuous-v1",
        assessment_version="assessment-v1",
        action_policy=_action_policy(),
        rows=(_row(),) if rows is None else rows,
        superiority_policy=_superiority(),
    )
    path = tmp_path / "learned-request.json"
    path.write_text(
        encode_fast_learned_comparison_request(request),
        encoding="utf-8",
    )
    return path, champion, binary


def _patch_baseline(monkeypatch, module, tmp_path: Path, champion: Path, rows):
    invocation = _fake_invocation(tmp_path, champion)
    campaign = _fake_campaign(rows)
    monkeypatch.setattr(
        module,
        "read_fast_deterministic_campaign_invocation_seal",
        lambda _: invocation,
    )
    monkeypatch.setattr(
        module,
        "decode_fast_deterministic_campaign_request",
        lambda _: _fake_baseline_request(),
    )
    monkeypatch.setattr(
        module,
        "read_fast_deterministic_campaign_artifact",
        lambda _: campaign,
    )
    return invocation, campaign


def test_request_rejects_population_drift_before_learned_binary_launch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_deterministic_campaign.learned_request as module

    request_path, champion, _ = _write_request_file(
        tmp_path,
        rows=(_row("other:0"),),
    )
    _patch_baseline(
        monkeypatch,
        module,
        tmp_path,
        champion,
        (_bundle_row("sig-a:0"),),
    )
    launched = False

    def _launch(**_kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("learned binary must not launch")

    monkeypatch.setattr(module, "run_fast_learned_chronological_campaign", _launch)

    with pytest.raises(ValueError, match="population|source_event"):
        run_fast_learned_comparison_request_file(request_path)

    assert not launched


def test_request_authenticates_binary_and_sealed_champion_before_launch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_deterministic_campaign.learned_request as module

    request_path, champion, binary = _write_request_file(tmp_path)
    _patch_baseline(
        monkeypatch,
        module,
        tmp_path,
        champion,
        (_bundle_row(),),
    )
    launched = False

    def _launch(**_kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("tampered source must not launch")

    monkeypatch.setattr(module, "run_fast_learned_chronological_campaign", _launch)

    binary.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="binary|fingerprint|sha"):
        run_fast_learned_comparison_request_file(request_path)
    assert not launched

    binary.write_text("binary", encoding="utf-8")
    request = decode_fast_learned_comparison_request(
        request_path.read_text(encoding="utf-8")
    )
    request = replace(request, decision_binary_sha256=_sha(binary))
    # Rebuild so the request fingerprint remains truthful.
    rebuilt = build_fast_learned_comparison_request(
        baseline_invocation_path=request.baseline_invocation_path,
        champion_path=request.champion_path,
        decision_binary_path=request.decision_binary_path,
        decision_binary_sha256=request.decision_binary_sha256,
        proof_destination_path=request.proof_destination_path,
        paper_run_id=request.paper_run_id,
        candidate_version=request.candidate_version,
        strategy_family=request.strategy_family,
        strategy_version=request.strategy_version,
        assessment_version=request.assessment_version,
        action_policy=request.action_policy,
        rows=request.rows,
        superiority_policy=request.superiority_policy,
    )
    request_path.write_text(
        encode_fast_learned_comparison_request(rebuilt),
        encoding="utf-8",
    )
    champion.write_text("tampered champion", encoding="utf-8")
    with pytest.raises(ValueError, match="champion|fingerprint|sha"):
        run_fast_learned_comparison_request_file(request_path)
    assert not launched


def test_request_runs_exact_baseline_population_and_writes_proof(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_deterministic_campaign.learned_request as module

    request_path, champion, binary = _write_request_file(tmp_path)
    invocation, campaign = _patch_baseline(
        monkeypatch,
        module,
        tmp_path,
        champion,
        (_bundle_row(),),
    )

    baseline_request = _fake_baseline_request()
    monkeypatch.setattr(
        module,
        "decode_fast_deterministic_campaign_request",
        lambda _: baseline_request,
    )

    captured = {}
    ledger = object()
    identity = object()
    learned_run = SimpleNamespace(
        event_population_fingerprint_sha256=(
            campaign.manifest.event_population_fingerprint_sha256
        )
    )
    final_proof = object()

    monkeypatch.setattr(module, "create_paper_ledger", lambda cash, at: ledger)
    monkeypatch.setattr(
        module,
        "FastDeterministicCampaignPaperEvidence",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        module,
        "FastLearnedCampaignRow",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    def _identity(**kwargs):
        captured["identity"] = kwargs
        return identity

    def _run(**kwargs):
        captured["run"] = kwargs
        return SimpleNamespace(run_evidence=learned_run)

    def _write(**kwargs):
        captured["proof"] = kwargs
        return object()

    monkeypatch.setattr(module, "build_fast_learned_campaign_identity", _identity)
    monkeypatch.setattr(module, "run_fast_learned_chronological_campaign", _run)
    monkeypatch.setattr(module, "write_fast_policy_comparison_artifact", _write)
    monkeypatch.setattr(
        module,
        "read_fast_policy_comparison_artifact",
        lambda _: final_proof,
    )

    result = run_fast_learned_comparison_request_file(request_path)

    assert result is final_proof
    assert captured["identity"]["champion_path"] == champion.resolve()
    assert captured["run"]["decision_binary_path"] == binary.resolve()
    assert captured["run"]["champion_path"] == champion.resolve()
    assert captured["run"]["identity"] is identity
    assert captured["run"]["starting_ledger"] is ledger
    assert captured["run"]["fill_policy"] is baseline_request.fill_policy
    assert captured["run"]["risk_policy"] is baseline_request.risk_policy
    assert captured["run"]["position_policy"] is baseline_request.position_policy
    assert captured["run"]["evaluation_policy"] is baseline_request.evaluation_policy

    learned_rows = captured["run"]["rows"]
    assert len(learned_rows) == 1
    assert learned_rows[0].record is campaign.comparison_bundle.rows[0].record
    assert learned_rows[0].paper_evidence.entry_quote is (
        campaign.comparison_bundle.rows[0].entry_quote
    )
    assert learned_rows[0].paper_evidence.exit_quote is (
        campaign.comparison_bundle.rows[0].exit_quote
    )
    assert learned_rows[0].paper_evidence.risk_environment is (
        campaign.comparison_bundle.rows[0].risk_environment
    )

    assert captured["proof"]["baseline_invocation_path"] == invocation.path
    assert captured["proof"]["learned_run"] is learned_run
    assert captured["proof"]["superiority_policy"] == _superiority()
    assert captured["proof"]["destination"] == (
        tmp_path / "learned-comparison-proof"
    ).resolve()


def test_learned_comparison_request_source_has_no_provider_promotion_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "learned_request.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "httpx",
        "sqlite3",
        "promotion",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source


def test_request_rejects_decision_binary_change_during_run_before_proof(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_deterministic_campaign.learned_request as module

    request_path, champion, binary = _write_request_file(tmp_path)
    _patch_baseline(
        monkeypatch,
        module,
        tmp_path,
        champion,
        (_bundle_row(),),
    )

    monkeypatch.setattr(module, "create_paper_ledger", lambda *_args: object())
    monkeypatch.setattr(
        module,
        "FastDeterministicCampaignPaperEvidence",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        module,
        "FastLearnedCampaignRow",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        module,
        "build_fast_learned_campaign_identity",
        lambda **_kwargs: object(),
    )

    def _run(**_kwargs):
        binary.write_text("changed-during-run", encoding="utf-8")
        return SimpleNamespace(
            run_evidence=SimpleNamespace(
                event_population_fingerprint_sha256="e" * 64
            )
        )

    wrote_proof = False

    def _write(**_kwargs):
        nonlocal wrote_proof
        wrote_proof = True
        raise AssertionError("proof must not publish after source drift")

    monkeypatch.setattr(module, "run_fast_learned_chronological_campaign", _run)
    monkeypatch.setattr(module, "write_fast_policy_comparison_artifact", _write)

    with pytest.raises(ValueError, match="binary|fingerprint|SHA"):
        run_fast_learned_comparison_request_file(request_path)

    assert not wrote_proof
