from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_buy_authority_producer as producer
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignRiskEnvironment,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
)
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowBuyAuthoritySourceRecord,
    produce_fast_paper_shadow_buy_authority_source_record,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    feature_logical_fingerprint_sha256,
)

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _entry
from test_fast_paper_shadow_executor import _evidence_for, _runtime_fixture


def _execution(record) -> FastOfflineEntryExecution:
    leg = FastOfflineExecutionLegCost(
        effective_fee_bps=25,
        expected_impact_bps=10,
        expected_slippage_bps=20,
        expected_latency_bps=5,
        network_fee_quote=0.001,
        priority_fee_quote=0.0,
        expected_failure_cost_quote=0.0,
    )
    return FastOfflineEntryExecution(
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=leg,
            exit=leg,
        ),
        trade=FastOfflineExecutionTrade(
            base_quantity=1.5,
            executable_entry_price_quote=(
                record.decision_executable_entry_price_quote
            ),
            forecast_exit_price_quote=1.20,
            exit_capacity_base=2.0,
            required_edge_bps=50,
            risk_margin_bps=25,
        ),
    )


def _environment(
    *,
    trading_capital_usd: float = 20_000.0,
    market_observed_at_unix_ms: int = 20_018,
    active_intent_keys: frozenset[str] = frozenset(),
) -> FastDeterministicCampaignRiskEnvironment:
    return FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=trading_capital_usd,
        day_started_at_unix_ms=0,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.2,
        price_impact_notional_usd=10_000.0,
        market_observed_at_unix_ms=market_observed_at_unix_ms,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=active_intent_keys,
        operator_entry_halt_active=False,
    )


def _fixture(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(tmp_path)
    feature = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    assert evidence.feature_record_fingerprint_sha256 == (
        feature_logical_fingerprint_sha256((feature,))
    )
    return manifest, binding, policy, checkpoint, posture, feature, evidence


def _produce(
    manifest,
    binding,
    policy,
    checkpoint,
    posture,
    feature,
    evidence,
    tmp_path: Path,
    *,
    execution: FastOfflineEntryExecution | None = None,
    environment: FastDeterministicCampaignRiskEnvironment | None = None,
    market_regime: MarketRegime = MarketRegime.NORMAL,
    source_observed_at_unix_ms: int = 20_019,
):
    return produce_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        feature,
        _execution(feature) if execution is None else execution,
        _environment() if environment is None else environment,
        market_regime,
        entry_authority_binary_path=tmp_path / "shreks-fast-entry-authority",
        source_observed_at_unix_ms=source_observed_at_unix_ms,
        source_version="shadow-buy-authority-producer-fixture-v1",
        source_fingerprint_sha256="b" * 64,
    )


def test_buy_authority_producer_delegates_fl3_and_recomputes_ledger_risk(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        feature,
        evidence,
    ) = _fixture(monkeypatch, tmp_path)
    execution = _execution(feature)
    environment = _environment()
    authority = _entry(feature)
    captured: dict[str, object] = {}

    def derive(*, binary_path, record, execution):
        captured.update(
            binary_path=binary_path,
            record=record,
            execution=execution,
        )
        return authority

    monkeypatch.setattr(
        producer,
        "derive_fast_deterministic_entry_authority_offline",
        derive,
    )

    result = _produce(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        feature,
        evidence,
        tmp_path,
        execution=execution,
        environment=environment,
    )

    assert type(result) is FastPaperShadowBuyAuthoritySourceRecord
    assert captured["binary_path"] == tmp_path / "shreks-fast-entry-authority"
    assert captured["record"] is feature
    assert captured["execution"] is execution
    assert result.entry_authority is authority
    assert result.market_regime is MarketRegime.NORMAL
    assert result.risk_day_started_at_unix_ms == 0
    assert result.source_observed_at_unix_ms == 20_019

    risk = result.risk_context
    assert risk.as_of_unix_ms == evidence.evaluated_at_unix_ms
    assert risk.trading_capital_usd == checkpoint.state.ledger.starting_cash_usd
    assert risk.open_position_count == 0
    assert risk.aggregate_open_risk_usd == 0.0
    assert risk.daily_realized_pnl_usd == 0.0
    assert risk.rolling_drawdown_pct == 0.0
    assert risk.consecutive_losses == 0
    assert risk.last_loss_at_unix_ms is None
    assert risk.liquidity_usd == environment.liquidity_usd
    assert risk.expected_price_impact_pct == environment.expected_price_impact_pct
    assert risk.price_impact_notional_usd == environment.price_impact_notional_usd
    assert risk.market_data_age_ms == 2
    assert risk.data_healthy is True
    assert risk.execution_healthy is True
    assert risk.kill_switch_active is False
    assert risk.operator_entry_halt_active is False
    assert risk.active_intent_keys == frozenset()


def test_buy_authority_producer_returns_none_when_fl3_refuses_buy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        producer,
        "derive_fast_deterministic_entry_authority_offline",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        producer,
        "build_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "FL3 refusal must not manufacture BUY authority"
        ),
    )

    assert _produce(*fixture, tmp_path) is None


def test_buy_authority_producer_binds_exact_feature_before_fl3(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        feature,
        evidence,
    ) = fixture
    drifted = replace(feature, decision_signature="different-signature")

    monkeypatch.setattr(
        producer,
        "derive_fast_deterministic_entry_authority_offline",
        lambda **_kwargs: pytest.fail(
            "feature drift must fail before FL3 derivation"
        ),
    )

    with pytest.raises(ValueError, match="feature|fingerprint|identity"):
        _produce(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            drifted,
            evidence,
            tmp_path,
            execution=_execution(drifted),
        )


def test_buy_authority_producer_rejects_untruthful_external_risk_facts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    authority = _entry(fixture[5])
    monkeypatch.setattr(
        producer,
        "derive_fast_deterministic_entry_authority_offline",
        lambda **_kwargs: authority,
    )

    with pytest.raises(ValueError, match="trading capital|starting cash|ledger"):
        _produce(
            *fixture,
            tmp_path,
            environment=_environment(trading_capital_usd=19_999.0),
        )

    with pytest.raises(ValueError, match="active intent|external"):
        _produce(
            *fixture,
            tmp_path,
            environment=_environment(
                active_intent_keys=frozenset({"external-intent"})
            ),
        )

    with pytest.raises(ValueError, match="market|source|observation|future"):
        _produce(
            *fixture,
            tmp_path,
            environment=_environment(
                market_observed_at_unix_ms=20_021,
            ),
        )

    with pytest.raises(ValueError, match="source|market|observation"):
        _produce(
            *fixture,
            tmp_path,
            environment=_environment(
                market_observed_at_unix_ms=20_019,
            ),
            source_observed_at_unix_ms=20_018,
        )


def test_buy_authority_producer_forwards_explicit_regime_and_source_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    authority = _entry(fixture[5])
    monkeypatch.setattr(
        producer,
        "derive_fast_deterministic_entry_authority_offline",
        lambda **_kwargs: authority,
    )

    result = _produce(
        *fixture,
        tmp_path,
        market_regime=MarketRegime.HOT,
    )

    assert result is not None
    assert result.market_regime is MarketRegime.HOT
    assert result.source_version == "shadow-buy-authority-producer-fixture-v1"
    assert result.source_fingerprint_sha256 == "b" * 64


def test_buy_authority_producer_has_no_persistence_network_scoring_or_execution_authority() -> None:
    payload = Path(producer.__file__).read_text(encoding="utf-8")

    for required in (
        "derive_fast_deterministic_entry_authority_offline",
        "build_fast_deterministic_campaign_risk_context",
        "feature_logical_fingerprint_sha256",
        "build_fast_paper_shadow_buy_authority_source_record",
    ):
        assert required in payload

    for forbidden in (
        "write_fast_paper_shadow_buy_authority_source_record",
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        "produce_fast_paper_shadow_execution_input_source_record",
        "execute_fast_paper_buy",
        "execute_fast_paper_shadow_decision(",
        "assess_fast_entry_risk(",
        "ObserverCampaignStore",
        "ObserverMarketStore",
        "sqlite3",
        "requests.",
        "httpx",
        "aiohttp",
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in payload
