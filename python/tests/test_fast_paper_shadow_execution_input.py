from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
from shreks_brain.fast_campaign import (
    FastCampaignDecisionPosition,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_campaign.models import FastCampaignActionCandidate
from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_NAME,
    FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_VERSION,
    FastPaperShadowExecutionInput,
    FastPaperShadowQuoteUsdEvidence,
    build_fast_paper_shadow_execution_policy,
    materialize_fast_paper_shadow_execution_evidence,
    read_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_execution_policy,
)
from shreks_brain.paper import PaperFillPolicy, PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext, RiskPolicy

from test_fast_paper_shadow_decision import (
    _fake_champion,
    _manifest,
    _quote,
    _record,
    _result_fingerprint,
)


def _fill_policy(manifest) -> PaperFillPolicy:
    return PaperFillPolicy(
        version=manifest.fill_policy_version,
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _risk_policy(manifest) -> RiskPolicy:
    return RiskPolicy(
        version=manifest.risk_policy_version,
        required_decision_policy_version=manifest.assessment_version,
        required_feature_schema_version=manifest.state_version,
        target_position_notional_usd=500.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=0.25,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=5_000.0,
        max_daily_realized_loss_usd=2_000.0,
        max_rolling_drawdown_pct=25.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=60,
        min_liquidity_usd=1_000.0,
        max_expected_price_impact_pct=5.0,
        max_slippage_bps=750,
        max_market_data_age_ms=2_000,
    )


def _position_policy(manifest) -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version=manifest.position_action_policy_version,
        max_slippage_bps=750,
    )


def _execution_policy(manifest):
    return build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=_risk_policy(manifest),
        fill_policy=_fill_policy(manifest),
        position_action_policy=_position_policy(manifest),
    )


def _usd(record, *, observed_at: int = 20_018) -> FastPaperShadowQuoteUsdEvidence:
    return FastPaperShadowQuoteUsdEvidence(
        quote_mint=record.quote_mint,
        observed_at_unix_ms=observed_at,
        quote_to_usd_rate=150.0,
        source_version="quote-usd-fixture-v1",
        source_fingerprint_sha256="d" * 64,
    )


def _risk(at: int) -> RiskContext:
    return RiskContext(
        as_of_unix_ms=at,
        trading_capital_usd=20_000.0,
        open_position_count=0,
        aggregate_open_risk_usd=0.0,
        daily_realized_pnl_usd=0.0,
        rolling_drawdown_pct=0.0,
        consecutive_losses=0,
        last_loss_at_unix_ms=None,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.2,
        price_impact_notional_usd=10_000.0,
        market_data_age_ms=10,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _entry(record) -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint=record.mint,
        quote_mint=record.quote_mint,
        intended_base_quantity=1.5,
        decision_executable_entry_price_quote=(
            record.decision_executable_entry_price_quote
        ),
        maximum_acceptable_entry_price_quote=1.05,
        expected_entry_variable_cost_bps=100,
        expected_entry_fixed_cost_quote=0.001,
    )


def _decision(manifest, request, *, action: str):
    if action == "BUY":
        current, target, reason = 0.0, 0.5, "BUY_SELECTED"
    elif action == "SKIP":
        current, target, reason = 0.0, 0.0, "SKIP_SELECTED"
    elif action == "HOLD":
        current, target, reason = 0.5, 0.5, "HOLD_SELECTED"
    elif action == "REDUCE":
        current, target, reason = 0.5, 0.25, "REDUCE_SELECTED"
    elif action == "SELL":
        current, target, reason = 0.5, 0.0, "SELL_SELECTED"
    else:
        raise AssertionError(action)

    decision = FastCampaignDecisionResult(
        source_event_id=request.source_event_id,
        market_key=request.market_key,
        source_sequence=request.source_sequence,
        as_of_unix_ms=request.as_of_unix_ms,
        policy_version=manifest.action_policy.version,
        action=action,
        reason=reason,
        selected_horizon_ms=(
            250 if action in {"BUY", "HOLD", "REDUCE"} else None
        ),
        current_exposure_fraction=current,
        target_exposure_fraction=target,
        selected_reward_bps=100.0 if action != "SELL" else 0.0,
        selected_risk_bps=25.0 if action != "SELL" else 0.0,
        selected_execution_cost_bps=(
            150.0 if action == "REDUCE" else 200.0 if action == "SELL" else 0.0
        ),
        selected_value_bps=20.0 if action in {"BUY", "HOLD", "REDUCE"} else 0.0,
        horizon_evidence=(),
        candidates=(
            FastCampaignActionCandidate(
                action=action,
                horizon_ms=(
                    250 if action in {"BUY", "HOLD", "REDUCE"} else None
                ),
                target_exposure_fraction=target,
                reward_bps=100.0 if action != "SELL" else 0.0,
                risk_bps=25.0 if action != "SELL" else 0.0,
                execution_cost_penalty_bps=(
                    37.5 if action == "REDUCE" else 100.0 if action == "SELL" else 0.0
                ),
                comparison_value_bps=(
                    20.0 if action in {"BUY", "HOLD", "REDUCE"} else 0.0
                ),
                eligible=True,
            ),
        ),
    )
    return FastCampaignDecisionResults(
        schema_name="shreks.fast_campaign_decision_results",
        schema_version=1,
        champion_version=manifest.champion_version,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        decisions=(decision,),
        batch_fingerprint_sha256=_result_fingerprint(
            manifest,
            decision,
        ),
    )


def _shadow_evidence(monkeypatch, tmp_path: Path, *, action: str):
    manifest = _manifest(tmp_path)
    record = _record()
    position = (
        FastCampaignDecisionPosition(kind="FLAT")
        if action in {"BUY", "SKIP"}
        else FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        )
    )

    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda _path: _fake_champion(manifest),
    )
    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _decision(manifest, batch.decisions[0], action=action)
        ),
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(
        shadow.time,
        "monotonic_ns",
        lambda: next(ticks),
    )

    kwargs = {}
    if action == "REDUCE":
        from shreks_brain.fast_paper_runtime import FastPaperShadowReductionQuote

        kwargs["reduction_quotes"] = (
            FastPaperShadowReductionQuote(
                target_exposure_fraction=0.25,
                quote=_quote(
                    record,
                    observed_at=20_012,
                    execution_price=0.985,
                ),
            ),
        )

    evidence = shadow.evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        position,
        evaluated_at_unix_ms=20_020,
        max_exposure_fraction=0.75,
        entry_quote=_quote(
            record,
            observed_at=20_010,
            execution_price=1.01,
        ),
        exit_quote=_quote(
            record,
            observed_at=20_015,
            execution_price=0.98,
        ),
        **kwargs,
    )
    return manifest, record, evidence


def test_execution_policy_is_manifest_bound_canonical_private_and_score_free(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    policy = _execution_policy(manifest)

    assert policy.schema_name == FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_NAME
    assert policy.schema_version == FAST_PAPER_SHADOW_EXECUTION_POLICY_SCHEMA_VERSION
    assert policy.manifest_fingerprint_sha256 == manifest.manifest_fingerprint_sha256
    assert policy.risk_policy.version == manifest.risk_policy_version
    assert policy.fill_policy.version == manifest.fill_policy_version
    assert (
        policy.position_action_policy.version
        == manifest.position_action_policy_version
    )
    assert len(policy.policy_fingerprint_sha256) == 64

    path = tmp_path / "shadow-execution-policy.json"
    write_fast_paper_shadow_execution_policy(policy, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read_fast_paper_shadow_execution_policy(manifest, path) == policy

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_execution_policy(policy, path)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    polluted = tmp_path / "polluted.json"
    polluted.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing"):
        read_fast_paper_shadow_execution_policy(manifest, polluted)


def test_execution_policy_rejects_policy_version_or_compatibility_drift(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)

    with pytest.raises(ValueError, match="risk.*version|manifest"):
        build_fast_paper_shadow_execution_policy(
            manifest,
            risk_policy=replace(
                _risk_policy(manifest),
                version="wrong-risk",
            ),
            fill_policy=_fill_policy(manifest),
            position_action_policy=_position_policy(manifest),
        )

    with pytest.raises(ValueError, match="assessment|decision|risk"):
        build_fast_paper_shadow_execution_policy(
            manifest,
            risk_policy=replace(
                _risk_policy(manifest),
                required_decision_policy_version="wrong-assessment",
            ),
            fill_policy=_fill_policy(manifest),
            position_action_policy=_position_policy(manifest),
        )


def test_buy_materialization_requires_explicit_size_risk_regime_and_usd(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, record, evidence = _shadow_evidence(
        monkeypatch,
        tmp_path,
        action="BUY",
    )
    policy = _execution_policy(manifest)
    source = FastPaperShadowExecutionInput(
        decision_evidence=evidence,
        entry_authority=_entry(record),
        risk_context=_risk(evidence.evaluated_at_unix_ms),
        market_regime=MarketRegime.NORMAL,
        quote_usd_evidence=_usd(record),
    )

    materialized = materialize_fast_paper_shadow_execution_evidence(
        manifest,
        policy,
        source,
    )

    assert materialized.source_event_id == evidence.source_event_id
    assert materialized.state_version == manifest.state_version
    assert materialized.quote is not None
    assert materialized.quote.state is PaperQuoteState.EXECUTABLE
    assert materialized.quote.execution_price_quote == pytest.approx(1.01)
    assert materialized.quote.quote_to_usd_rate == pytest.approx(150.0)
    assert materialized.entry_authority == source.entry_authority
    assert materialized.risk_context == source.risk_context
    assert materialized.market_regime is MarketRegime.NORMAL

    for missing in ("entry_authority", "risk_context", "market_regime", "quote_usd_evidence"):
        values = dict(
            decision_evidence=evidence,
            entry_authority=_entry(record),
            risk_context=_risk(evidence.evaluated_at_unix_ms),
            market_regime=MarketRegime.NORMAL,
            quote_usd_evidence=_usd(record),
        )
        values[missing] = None
        with pytest.raises(ValueError, match="BUY|authority|risk|regime|USD"):
            FastPaperShadowExecutionInput(**values)


def test_non_buy_actions_forbid_buy_authority_and_select_exact_quote(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for action in ("HOLD", "REDUCE", "SELL"):
        manifest, record, evidence = _shadow_evidence(
            monkeypatch,
            tmp_path,
            action=action,
        )
        policy = _execution_policy(manifest)
        source = FastPaperShadowExecutionInput(
            decision_evidence=evidence,
            entry_authority=None,
            risk_context=None,
            market_regime=None,
            quote_usd_evidence=_usd(record),
        )
        materialized = materialize_fast_paper_shadow_execution_evidence(
            manifest,
            policy,
            source,
        )
        assert materialized.quote is not None
        assert materialized.quote.quote_to_usd_rate == pytest.approx(150.0)
        if action == "REDUCE":
            assert materialized.quote.execution_price_quote == pytest.approx(0.985)
        else:
            assert materialized.quote.execution_price_quote == pytest.approx(0.98)

        with pytest.raises(ValueError, match="non-BUY|BUY|authority"):
            FastPaperShadowExecutionInput(
                decision_evidence=evidence,
                entry_authority=_entry(record),
                risk_context=None,
                market_regime=None,
                quote_usd_evidence=_usd(record),
            )


def test_skip_materialization_has_no_execution_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, record, evidence = _shadow_evidence(
        monkeypatch,
        tmp_path,
        action="SKIP",
    )
    policy = _execution_policy(manifest)
    source = FastPaperShadowExecutionInput(
        decision_evidence=evidence,
        entry_authority=None,
        risk_context=None,
        market_regime=None,
        quote_usd_evidence=None,
    )

    materialized = materialize_fast_paper_shadow_execution_evidence(
        manifest,
        policy,
        source,
    )
    assert materialized.quote is None
    assert materialized.entry_authority is None
    assert materialized.risk_context is None
    assert materialized.market_regime is None

    with pytest.raises(ValueError, match="SKIP|authority|USD"):
        FastPaperShadowExecutionInput(
            decision_evidence=evidence,
            entry_authority=None,
            risk_context=None,
            market_regime=None,
            quote_usd_evidence=_usd(record),
        )


def test_execution_input_rejects_future_usd_or_entry_price_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, record, evidence = _shadow_evidence(
        monkeypatch,
        tmp_path,
        action="BUY",
    )

    with pytest.raises(ValueError, match="future|USD|timestamp"):
        FastPaperShadowExecutionInput(
            decision_evidence=evidence,
            entry_authority=_entry(record),
            risk_context=_risk(evidence.evaluated_at_unix_ms),
            market_regime=MarketRegime.NORMAL,
            quote_usd_evidence=_usd(
                record,
                observed_at=evidence.evaluated_at_unix_ms + 1,
            ),
        )

    drifted = replace(
        _entry(record),
        decision_executable_entry_price_quote=0.99,
    )
    with pytest.raises(ValueError, match="price|entry|provenance"):
        FastPaperShadowExecutionInput(
            decision_evidence=evidence,
            entry_authority=drifted,
            risk_context=_risk(evidence.evaluated_at_unix_ms),
            market_regime=MarketRegime.NORMAL,
            quote_usd_evidence=_usd(record),
        )


def test_shadow_execution_input_module_has_input_authority_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_execution_input.py"
    ).read_text(encoding="utf-8")

    for required in (
        "FastCampaignPaperDecisionEvidence",
        "FastCampaignPaperEntryAuthority",
        "RiskPolicy",
        "PaperFillPolicy",
        "FastPaperPositionActionPolicy",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "ScorePolicy",
        "DecisionPolicy",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "sqlite3",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
