from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_COMPARISON_HYDRATION_VERSION,
    FAST_OBSERVER_DIRECTIONAL_PROBE_EVIDENCE_VERSION,
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicComparisonHydrationInput,
    FastDeterministicComparisonHydrationResult,
    FastObserverDirectionalProbeEvidence,
    build_fast_observer_champion_entry_execution,
    hydrate_fast_deterministic_comparison_evidence,
    load_fast_observer_directional_probe,
    read_fast_deterministic_comparison_evidence_bundle,
    write_fast_deterministic_comparison_evidence_bundle,
)
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_comparison_catalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineMarketSnapshot,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
)
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
    feature_logical_fingerprint_sha256,
)


T0 = 90_000_000
TOKEN = "MintHydrator111"
QUOTE = "QuoteHydrator111"
CATALOG_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_comparison_catalog_v1.json"
)


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=0,
        sell_count=0,
        unique_buy_actors=0,
        unique_sell_actors=0,
        buy_arrival_rate_per_second=0.0,
        sell_arrival_rate_per_second=0.0,
        count_imbalance=0.0,
        buy_base_quantity=0.0,
        sell_base_quantity=0.0,
        buy_quote_quantity=0.0,
        sell_quote_quantity=0.0,
        net_quote_quantity=0.0,
        quote_flow_imbalance=0.0,
        quote_flow_velocity_per_second=0.0,
        quote_flow_acceleration_per_second2=0.0,
        local_high_price_quote=None,
        local_high_sequence=None,
        local_high_observed_at_unix_ms=None,
        local_low_price_quote=None,
        local_low_sequence=None,
        local_low_observed_at_unix_ms=None,
        post_high_low_price_quote=None,
        post_high_low_sequence=None,
        post_high_low_observed_at_unix_ms=None,
        last_price_quote=10.0,
        drawdown_from_local_high=0.0,
        recovery_from_local_low=0.0,
    )


def _record() -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature="hydrate-sig",
        decision_ordinal=0,
        decision_sequence=1,
        mint=TOKEN,
        quote_mint=QUOTE,
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=T0,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 - 1,
        decision_occurred_at_unix_ms=T0 - 2,
        decision_slot=700,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=T0,
        snapshot_last_sequence=1,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _dataset(record: FastTrainingFeatureRecord) -> FastTrainingFeatureDataset:
    records = (record,)
    return FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(records),
        source_sha256="b" * 64,
    )


def _catalog():
    return decode_fast_deterministic_comparison_catalog(
        CATALOG_FIXTURE.read_text(encoding="utf-8")
    )


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=30,
        expected_latency_bps=10,
        network_fee_quote=0.01,
        priority_fee_quote=0.02,
        expected_failure_cost_quote=0.03,
    )


def _execution() -> FastOfflineEntryExecution:
    return FastOfflineEntryExecution(
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=_leg(),
            exit=FastOfflineExecutionLegCost(
                effective_fee_bps=50,
                expected_impact_bps=20,
                expected_slippage_bps=20,
                expected_latency_bps=10,
                network_fee_quote=0.01,
                priority_fee_quote=0.0,
                expected_failure_cost_quote=0.0,
            ),
        ),
        trade=FastOfflineExecutionTrade(
            base_quantity=10.0,
            executable_entry_price_quote=10.0,
            forecast_exit_price_quote=12.0,
            exit_capacity_base=10.0,
            required_edge_bps=200,
            risk_margin_bps=100,
        ),
    )


def _snapshot(record: FastTrainingFeatureRecord) -> FastOfflineMarketSnapshot:
    return FastOfflineMarketSnapshot(
        mint=record.mint,
        quote_mint=record.quote_mint,
        venue=record.venue,
        as_of_unix_ms=record.snapshot_as_of_unix_ms,
        last_sequence=record.snapshot_last_sequence,
        last_price_quote=record.snapshot_last_price_quote,
        last_reserve_context=record.last_reserve_context,
        last_lifecycle_event=record.last_lifecycle_event,
        windows=record.windows,
    )


def _entry_identity() -> ObserverPaperQuoteIdentity:
    return ObserverPaperQuoteIdentity(
        candidate_id=7,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider="jupiter",
        probe_policy_version="probe-v2",
        input_mint=QUOTE,
        output_mint=TOKEN,
        taker="Taker111",
        input_amount=100_000_000,
        slippage_bps=75,
    )


def _exit_identity() -> ObserverPaperQuoteIdentity:
    return ObserverPaperQuoteIdentity(
        candidate_id=7,
        purpose=ObserverPaperQuotePurpose.EXIT,
        provider="jupiter",
        probe_policy_version="probe-v2",
        input_mint=TOKEN,
        output_mint=QUOTE,
        taker="Taker111",
        input_amount=10_000_000,
        slippage_bps=75,
    )


def _risk() -> FastDeterministicCampaignRiskEnvironment:
    return FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=20_000.0,
        day_started_at_unix_ms=T0 - 10_000,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.25,
        price_impact_notional_usd=100.0,
        market_observed_at_unix_ms=T0 + 50,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _input(record: FastTrainingFeatureRecord) -> FastDeterministicComparisonHydrationInput:
    execution = _execution()
    return FastDeterministicComparisonHydrationInput(
        source_event_id=f"{record.decision_signature}:{record.decision_ordinal}",
        observer_candidate_id=7,
        state_version="observer-state-v1",
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=_entry_identity(),
        exit_quote_identity=_exit_identity(),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
        impulse_scalp_evidence=FastOfflineImpulseScalpEvidence(execution=execution),
        micro_pullback_evidence=FastOfflineMicroPullbackEvidence(execution=execution),
        pre_graduation_evidence=FastOfflinePreGraduationEvidence(execution=execution),
        graduation_flow_evidence=FastOfflineGraduationFlowEvidence(
            pre_snapshot=_snapshot(record),
            boost_context=None,
            execution=execution,
        ),
        wallet_cohort_evidence=FastOfflineWalletCohortEvidence(evidence=None),
        longer_runner_evidence=FastOfflineLongerRunnerEvidence(
            protective=FastOfflineLongerRunnerProtective(
                hard_stop_triggered=False,
                risk_limit_exit_required=False,
                liquidity_exit_required=False,
            ),
            continuation=None,
        ),
        market_regime=MarketRegime.NORMAL,
        risk_environment=_risk(),
        entry_forecast_source_version="ridge-return-v3",
        entry_forecast_horizon_ms=30_000,
        execution_cost_source_version="fl3-cost-policy-v1",
        exit_capacity_source_version="jupiter-exit-probe-v2",
        wallet_source_version=None,
        graduation_context_source_version="fl8.1-current-snapshot-v1",
        continuation_forecast_source_version=None,
        regime_source_version="observer-regime-v1",
        risk_environment_source_version="observer-risk-v1",
    )


def _create_observer_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE token_candidates (
            id INTEGER PRIMARY KEY,
            mint TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            discovery_source TEXT NOT NULL,
            discovered_at_unix_ms INTEGER NOT NULL,
            venue TEXT
        );
        CREATE TABLE token_mint_states (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            decimals INTEGER NOT NULL,
            mint_authority TEXT,
            freeze_authority TEXT,
            slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL
        );
        CREATE TABLE paper_quote_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            provider TEXT NOT NULL,
            probe_policy_version TEXT NOT NULL,
            input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL,
            taker TEXT NOT NULL,
            input_amount TEXT NOT NULL,
            output_amount TEXT NOT NULL,
            minimum_output_amount TEXT NOT NULL,
            slippage_bps INTEGER NOT NULL,
            route_available INTEGER NOT NULL,
            price_impact_pct TEXT,
            route_labels_json TEXT NOT NULL,
            quoted_at_unix_ms INTEGER NOT NULL
        );
        CREATE TABLE market_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_observed_at_unix_ms INTEGER,
            venue TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            price_usd REAL,
            liquidity_usd REAL,
            volume_m5_usd REAL,
            volume_h1_usd REAL,
            buys_m5 INTEGER,
            sells_m5 INTEGER,
            buys_h1 INTEGER,
            sells_h1 INTEGER,
            pair_created_at_unix_ms INTEGER
        );
        CREATE TABLE token_holder_distributions (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            mint TEXT NOT NULL,
            last_indexed_slot TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            complete INTEGER NOT NULL,
            top_holder_concentration_pct REAL
        );
        CREATE TABLE exit_quote_snapshots (
            id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            probe_policy_version TEXT NOT NULL,
            input_mint TEXT NOT NULL,
            output_mint TEXT NOT NULL,
            taker TEXT NOT NULL,
            input_amount TEXT NOT NULL,
            output_amount TEXT NOT NULL,
            minimum_output_amount TEXT NOT NULL,
            slippage_bps INTEGER NOT NULL,
            route_available INTEGER NOT NULL,
            price_impact_pct TEXT,
            quoted_at_unix_ms INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        """INSERT INTO token_candidates
           (id, mint, pair_address, discovery_source, discovered_at_unix_ms, venue)
           VALUES (7, ?, 'Pair111', 'pump', ?, 'pump_fun')""",
        (TOKEN, T0 - 10_000),
    )
    connection.execute(
        """INSERT INTO token_mint_states
           (id, candidate_id, provider, decimals, mint_authority, freeze_authority, slot, observed_at_unix_ms)
           VALUES (1, 7, 'helius', 6, NULL, NULL, '10', ?)""",
        (T0 - 100,),
    )
    connection.execute(
        """INSERT INTO paper_quote_snapshots (
               id, candidate_id, purpose, provider, probe_policy_version,
               input_mint, output_mint, taker, input_amount, output_amount,
               minimum_output_amount, slippage_bps, route_available,
               price_impact_pct, route_labels_json, quoted_at_unix_ms
           ) VALUES
               (1, 7, 'entry', 'jupiter', 'probe-v2', ?, ?, 'Taker111',
                '100000000', '10000000', '9900000', 75, 1, '0.25',
                '["Raydium"]', ?),
               (2, 7, 'exit', 'jupiter', 'probe-v2', ?, ?, 'Taker111',
                '10000000', '99000000', '98000000', 75, 1, '0.30',
                '["Raydium"]', ?)""",
        (QUOTE, TOKEN, T0 + 60, TOKEN, QUOTE, T0 + 70),
    )
    connection.commit()
    connection.close()


def _fake_authority_binary(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        "from pathlib import Path\n"
        "request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "entry = request['execution']['cost_model']['entry']\n"
        "variable = sum(entry[k] for k in ('effective_fee_bps','expected_impact_bps','expected_slippage_bps','expected_latency_bps'))\n"
        "fixed = sum(entry[k] for k in ('network_fee_quote','priority_fee_quote','expected_failure_cost_quote'))\n"
        "material = {\n"
        " 'schema_name': 'shreks.fast_deterministic_entry_authority_result',\n"
        " 'schema_version': 1,\n"
        " 'mint': request['mint'],\n"
        " 'quote_mint': request['quote_mint'],\n"
        " 'intended_base_quantity': request['execution']['trade']['base_quantity'],\n"
        " 'decision_executable_entry_price_quote': request['decision_executable_entry_price_quote'],\n"
        " 'maximum_acceptable_entry_price_quote': 11.4,\n"
        " 'expected_entry_variable_cost_bps': variable,\n"
        " 'expected_entry_fixed_cost_quote': fixed,\n"
        "}\n"
        "canonical = json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)\n"
        "material['result_fingerprint_sha256'] = hashlib.sha256(canonical.encode()).hexdigest()\n"
        "print(json.dumps(material, separators=(',', ':'), ensure_ascii=False, allow_nan=False), end='')\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)


def test_observer_probe_derives_exact_entry_size_and_exit_capacity(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer-probe.db"
    _create_observer_db(database)

    probe = load_fast_observer_directional_probe(
        database_path=database,
        record=record,
        observer_candidate_id=7,
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=_entry_identity(),
        exit_quote_identity=_exit_identity(),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
    )

    assert type(probe) is FastObserverDirectionalProbeEvidence
    assert probe.version == FAST_OBSERVER_DIRECTIONAL_PROBE_EVIDENCE_VERSION
    assert probe.source_event_id == "hydrate-sig:0"
    assert probe.token_decimals == 6
    assert probe.entry_quote.state is PaperQuoteState.EXECUTABLE
    assert probe.entry_quote.execution_price_quote == pytest.approx(10.0)
    assert probe.exit_quote.state is PaperQuoteState.EXECUTABLE
    assert probe.exit_quote.execution_price_quote == pytest.approx(9.9)
    assert probe.intended_base_quantity == pytest.approx(10.0)
    assert probe.exit_capacity_base == pytest.approx(10.0)
    assert probe.entry_quote_source_version == "observer:jupiter:probe-v2:entry"
    assert probe.exit_quote_source_version == "observer:jupiter:probe-v2:exit"


def test_observer_probe_supplies_champion_size_and_capacity_without_caller_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer-probe-build.db"
    _create_observer_db(database)
    probe = load_fast_observer_directional_probe(
        database_path=database,
        record=record,
        observer_candidate_id=7,
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=_entry_identity(),
        exit_quote_identity=_exit_identity(),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
    )
    captured = {}
    sentinel = object()

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.observer_probe."
        "build_fast_champion_entry_execution_evidence",
        fake_builder,
    )

    result = build_fast_observer_champion_entry_execution(
        probe=probe,
        champion_path=tmp_path / "champion.json",
        record=record,
        horizon_ms=30_000,
        cost_model=_execution().cost_model,
        required_edge_bps=200,
        risk_margin_bps=100,
        execution_policy_source_version="fl3-economic-policy-v1",
    )

    assert result is sentinel
    assert captured["base_quantity"] == pytest.approx(10.0)
    assert captured["exit_capacity_base"] == pytest.approx(10.0)
    assert (
        captured["exit_capacity_source_version"]
        == probe.exit_quote_source_version
    )
    assert "base_quantity" not in {
        "probe",
        "champion_path",
        "record",
        "horizon_ms",
        "cost_model",
        "required_edge_bps",
        "risk_margin_bps",
        "execution_policy_source_version",
    }


@pytest.mark.parametrize("purpose", ("entry", "exit"))
def test_unavailable_direction_produces_no_champion_execution_evidence(
    purpose: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / f"observer-unavailable-{purpose}.db"
    _create_observer_db(database)
    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE paper_quote_snapshots
           SET output_amount = '0',
               minimum_output_amount = '0',
               route_available = 0,
               price_impact_pct = NULL,
               route_labels_json = '[]'
           WHERE purpose = ?""",
        (purpose,),
    )
    connection.commit()
    connection.close()

    probe = load_fast_observer_directional_probe(
        database_path=database,
        record=record,
        observer_candidate_id=7,
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=_entry_identity(),
        exit_quote_identity=_exit_identity(),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
    )

    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("champion inference must not run without both routes")

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.observer_probe."
        "build_fast_champion_entry_execution_evidence",
        should_not_run,
    )

    assert build_fast_observer_champion_entry_execution(
        probe=probe,
        champion_path=tmp_path / "missing-champion.json",
        record=record,
        horizon_ms=30_000,
        cost_model=_execution().cost_model,
        required_edge_bps=200,
        risk_margin_bps=100,
        execution_policy_source_version="fl3-economic-policy-v1",
    ) is None
    assert called is False


def test_observer_probe_preserves_positive_but_undersized_exit_capacity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer-undersized-exit.db"
    _create_observer_db(database)
    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE paper_quote_snapshots
           SET input_amount = '5000000',
               output_amount = '49500000',
               minimum_output_amount = '49000000'
           WHERE purpose = 'exit'"""
    )
    connection.commit()
    connection.close()
    smaller_exit = replace(_exit_identity(), input_amount=5_000_000)

    probe = load_fast_observer_directional_probe(
        database_path=database,
        record=record,
        observer_candidate_id=7,
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=_entry_identity(),
        exit_quote_identity=smaller_exit,
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
    )
    assert probe.intended_base_quantity == pytest.approx(10.0)
    assert probe.exit_capacity_base == pytest.approx(5.0)

    captured = {}
    sentinel = object()

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.observer_probe."
        "build_fast_champion_entry_execution_evidence",
        fake_builder,
    )
    assert build_fast_observer_champion_entry_execution(
        probe=probe,
        champion_path=tmp_path / "champion.json",
        record=record,
        horizon_ms=30_000,
        cost_model=_execution().cost_model,
        required_edge_bps=200,
        risk_margin_bps=100,
        execution_policy_source_version="fl3-economic-policy-v1",
    ) is sentinel
    assert captured["base_quantity"] == pytest.approx(10.0)
    assert captured["exit_capacity_base"] == pytest.approx(5.0)


def test_hydrates_real_directional_observer_quotes_and_fl3_authority(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    result = hydrate_fast_deterministic_comparison_evidence(
        database_path=database,
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        hydration_inputs=(_input(record),),
        entry_authority_binary_path=authority_binary,
    )

    assert type(result) is FastDeterministicComparisonHydrationResult
    assert result.version == FAST_DETERMINISTIC_COMPARISON_HYDRATION_VERSION
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.quote is None
    assert row.entry_quote.state is PaperQuoteState.EXECUTABLE
    assert row.entry_quote.execution_price_quote == pytest.approx(10.0)
    assert row.entry_quote.quoted_base_quantity == pytest.approx(10.0)
    assert row.exit_quote.state is PaperQuoteState.EXECUTABLE
    assert row.exit_quote.execution_price_quote == pytest.approx(9.9)
    assert row.exit_quote.quoted_base_quantity == pytest.approx(10.0)
    assert len(row.candidate_authorities) == 8
    assert all(
        item.entry_authority is not None
        and item.entry_authority.maximum_acceptable_entry_price_quote
        == pytest.approx(11.4)
        for item in row.candidate_authorities
    )

    provenance = result.provenance[0]
    assert provenance.source_event_id == "hydrate-sig:0"
    assert provenance.entry_quote_source_version == "observer:jupiter:probe-v2:entry"
    assert provenance.exit_quote_source_version == "observer:jupiter:probe-v2:exit"
    assert provenance.entry_forecast_source_version == "ridge-return-v3"
    assert provenance.entry_forecast_horizon_ms == 30_000
    assert provenance.entry_authority_source_version == "fl3-execution-economics-v1"

    destination = tmp_path / "real-comparison-bundle"
    manifest = write_fast_deterministic_comparison_evidence_bundle(
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        rows=result.rows,
        provenance=result.provenance,
        destination=destination,
    )
    loaded = read_fast_deterministic_comparison_evidence_bundle(destination)
    assert loaded.manifest == manifest
    assert loaded.rows == result.rows
    assert loaded.provenance == result.provenance


def test_hydrator_preserves_unavailable_entry_route_without_inventing_price(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE paper_quote_snapshots
           SET output_amount = '0',
               minimum_output_amount = '0',
               route_available = 0,
               price_impact_pct = NULL,
               route_labels_json = '[]'
           WHERE purpose = 'entry'"""
    )
    connection.commit()
    connection.close()

    risk = replace(
        _risk(),
        expected_price_impact_pct=None,
        price_impact_notional_usd=None,
    )
    result = hydrate_fast_deterministic_comparison_evidence(
        database_path=database,
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        hydration_inputs=(replace(_input(record), risk_environment=risk),),
        entry_authority_binary_path=authority_binary,
    )

    row = result.rows[0]
    assert row.entry_quote.state is PaperQuoteState.UNAVAILABLE
    assert row.entry_quote.execution_price_quote is None
    assert row.entry_quote.quoted_base_quantity is None
    assert row.exit_quote.state is PaperQuoteState.EXECUTABLE


def test_hydrator_preserves_insufficient_exit_capacity_as_no_buy_authority(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    source = _input(record)
    execution = source.impulse_scalp_evidence.execution
    assert execution is not None
    insufficient = replace(
        execution,
        trade=replace(
            execution.trade,
            exit_capacity_base=execution.trade.base_quantity - 1.0,
        ),
    )
    hydrated_input = replace(
        source,
        impulse_scalp_evidence=FastOfflineImpulseScalpEvidence(
            execution=insufficient
        ),
        micro_pullback_evidence=FastOfflineMicroPullbackEvidence(
            execution=insufficient
        ),
        pre_graduation_evidence=FastOfflinePreGraduationEvidence(
            execution=insufficient
        ),
        graduation_flow_evidence=FastOfflineGraduationFlowEvidence(
            pre_snapshot=source.graduation_flow_evidence.pre_snapshot,
            boost_context=source.graduation_flow_evidence.boost_context,
            execution=insufficient,
        ),
    )

    result = hydrate_fast_deterministic_comparison_evidence(
        database_path=database,
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        hydration_inputs=(hydrated_input,),
        entry_authority_binary_path=authority_binary,
    )

    assert all(
        item.entry_authority is None
        for item in result.rows[0].candidate_authorities
    )


def test_hydrator_rejects_execution_size_or_capacity_drift_from_observer_probe(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer-size-drift.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    source = _input(record)
    execution = source.impulse_scalp_evidence.execution
    assert execution is not None

    for drift_trade, message in (
        (
            replace(execution.trade, base_quantity=9.0),
            "size|quantity|probe",
        ),
        (
            replace(execution.trade, exit_capacity_base=11.0),
            "capacity|probe",
        ),
    ):
        drift_execution = replace(execution, trade=drift_trade)
        drift = replace(
            source,
            impulse_scalp_evidence=FastOfflineImpulseScalpEvidence(
                execution=drift_execution
            ),
            micro_pullback_evidence=FastOfflineMicroPullbackEvidence(
                execution=drift_execution
            ),
            pre_graduation_evidence=FastOfflinePreGraduationEvidence(
                execution=drift_execution
            ),
            graduation_flow_evidence=FastOfflineGraduationFlowEvidence(
                pre_snapshot=source.graduation_flow_evidence.pre_snapshot,
                boost_context=source.graduation_flow_evidence.boost_context,
                execution=drift_execution,
            ),
        )
        with pytest.raises(ValueError, match=message):
            hydrate_fast_deterministic_comparison_evidence(
                database_path=database,
                feature_dataset=_dataset(record),
                catalog=_catalog(),
                hydration_inputs=(drift,),
                entry_authority_binary_path=authority_binary,
            )

    with pytest.raises(ValueError, match="capacity|source|provenance|probe"):
        hydrate_fast_deterministic_comparison_evidence(
            database_path=database,
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            hydration_inputs=(
                replace(
                    source,
                    exit_capacity_source_version="invented-capacity-v9",
                ),
            ),
            entry_authority_binary_path=authority_binary,
        )


def test_hydrator_rejects_family_specific_execution_economics_drift(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    input_row = _input(record)
    different = replace(
        input_row.micro_pullback_evidence.execution.trade,
        forecast_exit_price_quote=13.0,
    )
    drift_execution = replace(
        input_row.micro_pullback_evidence.execution,
        trade=different,
    )
    drift = replace(
        input_row,
        micro_pullback_evidence=FastOfflineMicroPullbackEvidence(
            execution=drift_execution
        ),
    )

    with pytest.raises(ValueError, match="shared|execution|economics|entry"):
        hydrate_fast_deterministic_comparison_evidence(
            database_path=database,
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            hydration_inputs=(drift,),
            entry_authority_binary_path=authority_binary,
        )


def test_hydrator_rejects_population_and_risk_quote_provenance_drift(
    tmp_path: Path,
) -> None:
    record = _record()
    database = tmp_path / "observer.db"
    authority_binary = tmp_path / "authority"
    _create_observer_db(database)
    _fake_authority_binary(authority_binary)

    with pytest.raises(ValueError, match="source|population|identity"):
        hydrate_fast_deterministic_comparison_evidence(
            database_path=database,
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            hydration_inputs=(
                replace(_input(record), source_event_id="wrong:0"),
            ),
            entry_authority_binary_path=authority_binary,
        )

    bad_risk = replace(_risk(), expected_price_impact_pct=0.5)
    with pytest.raises(ValueError, match="risk|impact|quote|provenance"):
        hydrate_fast_deterministic_comparison_evidence(
            database_path=database,
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            hydration_inputs=(
                replace(_input(record), risk_environment=bad_risk),
            ),
            entry_authority_binary_path=authority_binary,
        )


def test_hydrator_source_has_no_future_label_write_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "hydration.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "future_path",
        "counterfactual",
        "sqlite3",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "requests.",
        "httpx",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "evaluate_fast_policy_superiority",
        "promotion",
    ):
        assert forbidden not in source
