from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_buy_authority_evidence_adapter as adapter
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicComparisonExecutionPolicy,
)
from shreks_brain.fast_deterministic_offline import (
    FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION,
    FastChampionEntryExecutionEvidence,
)
from shreks_brain.fast_learning import (
    FastForecastPrediction,
    FastForecastTarget,
)
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowCycleInput,
    FastPaperShadowQuoteReadPolicy,
    produce_fast_paper_shadow_buy_authority_from_persisted_evidence,
)
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.regime import MarketRegime
from shreks_brain.safety import SafetyPolicy

from test_fast_paper_shadow_buy_authority_producer import (
    _execution,
    _fixture,
)
from test_fast_paper_shadow_execution_input import _usd
from test_regime_engine import policy as _regime_policy


def _quote_policy(manifest) -> FastPaperShadowQuoteReadPolicy:
    return FastPaperShadowQuoteReadPolicy(
        version=manifest.route_evidence_version,
        candidate_id=7,
        probe_policy_version="probe-v2",
        taker="Taker111",
        slippage_bps=75,
        entry_input_amount_raw=1_000_000_000,
        exit_input_amount_raw=2_000_000,
        max_quote_age_ms=2_000,
    )


def _market_policy() -> ObserverMarketReadPolicy:
    return ObserverMarketReadPolicy(
        version="shadow-buy-market-v1",
        source_priority=("dexscreener",),
        max_current_age_ms=2_000,
        local_range_lookback_ms=60_000,
    )


def _regime_read_policy(manifest, quote_policy) -> ObserverRegimeReadPolicy:
    return ObserverRegimeReadPolicy(
        version="shadow-buy-regime-read-v1",
        window_ms=600_000,
        max_snapshot_age_ms=60_000,
        source_priority=("dexscreener",),
        entry_probe_policy_version=quote_policy.probe_policy_version,
        quote_asset_mint=manifest.quote_mint,
        entry_input_amount=quote_policy.entry_input_amount_raw,
        taker=quote_policy.taker,
        slippage_bps=quote_policy.slippage_bps,
    )


def _safety_policy() -> SafetyPolicy:
    return SafetyPolicy(
        version="shadow-buy-safety-v1",
        min_liquidity_usd=25.0,
        soft_min_liquidity_usd=40.0,
        max_top_holder_concentration_pct=50.0,
        soft_max_top_holder_concentration_pct=40.0,
        soft_max_creator_concentration_pct=40.0,
        soft_max_exit_price_impact_pct=5.0,
        max_critical_data_age_ms=100_000,
    )


def _safety_probe(manifest, quote_policy) -> ObserverSafetyProbeIdentity:
    return ObserverSafetyProbeIdentity(
        probe_policy_version=quote_policy.probe_policy_version,
        output_mint=manifest.quote_mint,
        input_amount=quote_policy.exit_input_amount_raw,
        taker=quote_policy.taker,
        slippage_bps=quote_policy.slippage_bps,
    )


def _execution_policy(feature) -> FastDeterministicComparisonExecutionPolicy:
    execution = _execution(feature)
    return FastDeterministicComparisonExecutionPolicy(
        version="shadow-buy-execution-economics-v1",
        horizon_ms=250,
        cost_model=execution.cost_model,
        required_edge_bps=execution.trade.required_edge_bps,
        risk_margin_bps=execution.trade.risk_margin_bps,
    )


def _call(
    fixture,
    tmp_path: Path,
    *,
    quote_policy=None,
    data_healthy=True,
    execution_healthy=True,
    global_risk_halt=False,
):
    (
        manifest,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        feature,
        decision,
    ) = fixture
    quotes = _quote_policy(manifest) if quote_policy is None else quote_policy
    return produce_fast_paper_shadow_buy_authority_from_persisted_evidence(
        manifest,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        decision,
        feature,
        quotes,
        _market_policy(),
        _regime_read_policy(manifest, quotes),
        _regime_policy(),
        _safety_policy(),
        _safety_probe(manifest, quotes),
        _execution_policy(feature),
        quote_usd_source_directory=tmp_path / "quote-usd-sources",
        operator_risk_control_path=tmp_path / "operator-risk-control.json",
        entry_authority_binary_path=tmp_path / "shreks-fast-entry-authority",
        day_started_at_unix_ms=0,
        data_healthy=data_healthy,
        execution_healthy=execution_healthy,
        global_risk_halt=global_risk_halt,
    )


def _wire_reads(monkeypatch, fixture, *, halt=False, kill=False, control_at=20_014):
    (
        manifest,
        _binding,
        _execution_policy_value,
        _checkpoint,
        _runtime_state,
        feature,
        decision,
    ) = fixture
    quote_policy = _quote_policy(manifest)
    cycle = FastPaperShadowCycleInput(
        record=feature,
        position=decision.position,
        evaluated_at_unix_ms=decision.evaluated_at_unix_ms,
        max_exposure_fraction=decision.decision.target_exposure_fraction,
        entry_quote=decision.entry_quote,
        exit_quote=decision.exit_quote,
    )
    monkeypatch.setattr(
        adapter,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: cycle,
    )

    build_calls: dict[str, object] = {}

    def build_execution(**kwargs):
        build_calls.update(kwargs)
        return FastChampionEntryExecutionEvidence(
            version=FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION,
            champion_version=manifest.champion_version,
            champion_fingerprint_sha256=(
                manifest.champion_fingerprint_sha256
            ),
            member_key="endpoint_return_bps@250ms",
            validation_run_fingerprint_sha256="1" * 64,
            test_evaluation_report_fingerprint_sha256="2" * 64,
            prediction=FastForecastPrediction(
                model_version="endpoint-model-v1",
                target=FastForecastTarget.ENDPOINT_RETURN_BPS,
                horizon_ms=250,
                decision_identity=feature.decision_identity,
                predicted_value=2_000.0,
            ),
            execution=_execution(feature),
            forecast_source_version="forecast-source-v1",
            execution_policy_source_version=(
                "shadow-buy-execution-economics-v1"
            ),
            exit_capacity_source_version="persisted-exit-quote-v1",
        )

    monkeypatch.setattr(
        adapter,
        "build_fast_champion_entry_execution_evidence",
        build_execution,
    )

    market_window = SimpleNamespace(
        candidate=SimpleNamespace(
            candidate_id=quote_policy.candidate_id,
            mint=feature.mint,
        ),
        current=SimpleNamespace(
            row_id=41,
            observed_at_unix_ms=20_016,
            liquidity_usd=80_000.0,
            venue=feature.venue,
        ),
    )

    class MarketStore:
        def __init__(self, path):
            assert str(path) == manifest.observer_database_path

        def load_window(self, candidate_id, as_of_unix_ms, policy, *, required_quote_mint):
            assert candidate_id == quote_policy.candidate_id
            assert as_of_unix_ms == decision.evaluated_at_unix_ms
            assert required_quote_mint == manifest.quote_mint
            return market_window

    monkeypatch.setattr(adapter, "ObserverMarketStore", MarketStore)

    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=quote_policy.candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=quote_policy.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature.mint,
        taker=quote_policy.taker,
        input_amount=quote_policy.entry_input_amount_raw,
        slippage_bps=quote_policy.slippage_bps,
    )
    entry_raw = SimpleNamespace(
        identity=entry_identity,
        route_available=True,
        quoted_at_unix_ms=decision.entry_quote.observed_at_unix_ms,
        price_impact_pct="0.25",
    )
    regime_market = SimpleNamespace(source_observed_at_unix_ms=20_013)
    regime_calls: dict[str, object] = {}

    class CampaignStore:
        def __init__(self, path):
            assert str(path) == manifest.observer_database_path

        def latest_paper_quote(self, identity, as_of_unix_ms):
            assert identity == entry_identity
            assert as_of_unix_ms == decision.evaluated_at_unix_ms
            return entry_raw

        def build_regime_market_window(
            self,
            as_of_unix_ms,
            regime_read_policy,
            safety_policy,
            safety_probe_identity,
            *,
            global_risk_halt,
        ):
            regime_calls.update(
                as_of_unix_ms=as_of_unix_ms,
                global_risk_halt=global_risk_halt,
            )
            return regime_market

    monkeypatch.setattr(adapter, "ObserverCampaignStore", CampaignStore)
    monkeypatch.setattr(
        adapter,
        "assess_regime",
        lambda market, policy, performance=None: (
            SimpleNamespace(regime=MarketRegime.HOT)
        ),
    )

    usd = _usd(feature, observed_at=20_017)
    monkeypatch.setattr(
        adapter,
        "read_fast_paper_shadow_quote_usd_source_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            quote_usd_evidence=usd,
            record_fingerprint_sha256="e" * 64,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "load_operator_risk_control_state",
        lambda _path: SimpleNamespace(
            revision=3,
            updated_at_unix_ms=control_at,
            halt_new_entries=halt or kill,
            kill_switch_active=kill,
        ),
    )
    return build_calls, regime_calls


def test_persisted_evidence_adapter_composes_exact_buy_authority_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    build_calls, regime_calls = _wire_reads(monkeypatch, fixture)
    captured: dict[str, object] = {}
    sentinel = object()

    def produce(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(
        adapter,
        "produce_fast_paper_shadow_buy_authority_source_record",
        produce,
    )

    result = _call(fixture, tmp_path)

    assert result is sentinel
    assert build_calls["champion_path"] == fixture[0].champion_path
    assert build_calls["record"] is fixture[5]
    assert build_calls["horizon_ms"] == fixture[6].decision.selected_horizon_ms
    assert build_calls["base_quantity"] == fixture[6].entry_quote.quoted_base_quantity
    assert build_calls["exit_capacity_base"] == fixture[6].exit_quote.available_base_quantity

    args = captured["args"]
    environment = args[8]
    assert environment.trading_capital_usd == (
        fixture[3].state.ledger.starting_cash_usd
    )
    assert environment.liquidity_usd == 80_000.0
    assert environment.expected_price_impact_pct == 0.25
    assert environment.price_impact_notional_usd == 150.0
    assert environment.market_observed_at_unix_ms == 20_010
    assert environment.data_healthy is True
    assert environment.execution_healthy is True
    assert environment.kill_switch_active is False
    assert environment.operator_entry_halt_active is False
    assert environment.active_intent_keys == frozenset()
    assert args[9] is MarketRegime.HOT

    kwargs = captured["kwargs"]
    assert kwargs["source_observed_at_unix_ms"] == 20_017
    assert kwargs["source_version"] == (
        adapter.FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION
    )
    assert len(kwargs["source_fingerprint_sha256"]) == 64
    int(kwargs["source_fingerprint_sha256"], 16)
    assert regime_calls["global_risk_halt"] is False


def test_persisted_evidence_adapter_propagates_operator_halt_and_kill(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _build_calls, regime_calls = _wire_reads(
        monkeypatch,
        fixture,
        kill=True,
    )
    captured: dict[str, object] = {}

    def produce(*args, **kwargs):
        captured["environment"] = args[8]
        return object()

    monkeypatch.setattr(
        adapter,
        "produce_fast_paper_shadow_buy_authority_source_record",
        produce,
    )

    _call(fixture, tmp_path)

    environment = captured["environment"]
    assert environment.kill_switch_active is True
    assert environment.operator_entry_halt_active is True
    assert regime_calls["global_risk_halt"] is False


def test_persisted_evidence_adapter_refuses_quote_drift_before_economics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    decision = fixture[6]
    cycle = FastPaperShadowCycleInput(
        record=fixture[5],
        position=decision.position,
        evaluated_at_unix_ms=decision.evaluated_at_unix_ms,
        max_exposure_fraction=decision.decision.target_exposure_fraction,
        entry_quote=decision.entry_quote,
        exit_quote=replace(
            decision.exit_quote,
            observed_at_unix_ms=decision.exit_quote.observed_at_unix_ms - 1,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: cycle,
    )
    monkeypatch.setattr(
        adapter,
        "build_fast_champion_entry_execution_evidence",
        lambda **_kwargs: pytest.fail(
            "quote drift must fail before execution economics"
        ),
    )

    with pytest.raises(ValueError, match="quote|drift|sealed"):
        _call(fixture, tmp_path)


def test_persisted_evidence_adapter_rejects_future_operator_control(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _wire_reads(monkeypatch, fixture, control_at=20_021)
    monkeypatch.setattr(
        adapter,
        "produce_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: pytest.fail(
            "future operator control must not be backdated"
        ),
    )

    with pytest.raises(ValueError, match="operator|control|future|evaluation"):
        _call(fixture, tmp_path)


def test_persisted_evidence_adapter_has_read_only_bounded_authority() -> None:
    payload = Path(adapter.__file__).read_text(encoding="utf-8")

    for required in (
        "resolve_fast_paper_shadow_cycle_input",
        "build_fast_champion_entry_execution_evidence",
        "ObserverMarketStore",
        "ObserverCampaignStore",
        "assess_regime",
        "read_fast_paper_shadow_quote_usd_source_record",
        "load_operator_risk_control_state",
        "produce_fast_paper_shadow_buy_authority_source_record",
    ):
        assert required in payload

    for forbidden in (
        "write_fast_paper_shadow_buy_authority_source_record",
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        "produce_fast_paper_shadow_execution_input_source_record",
        "execute_fast_paper_buy",
        "execute_fast_paper_shadow_decision(",
        "assess_fast_entry_risk(",
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
