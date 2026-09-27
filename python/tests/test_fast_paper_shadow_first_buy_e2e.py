from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperRuntimeCursor,
    FastPaperShadowQuoteReadPolicy,
    FastPaperShadowQuoteUsdEvidence,
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    build_fast_paper_shadow_buy_writer_policy,
    build_fast_paper_shadow_execution_policy,
    build_fast_paper_shadow_quote_usd_source_record,
    resolve_fast_paper_shadow_cycle_input,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
    write_fast_paper_shadow_buy_writer_policy,
    write_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_quote_usd_source_record,
)
from shreks_brain.fast_paper_runtime.shadow import (
    evaluate_fast_paper_shadow_decision,
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_provision import (
    FastPaperShadowProvisionConfig,
    provision_fast_paper_shadow,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME,
    FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION,
    FastPaperShadowServiceConfig,
    FastPaperShadowServicePolicy,
)
from shreks_brain.fast_paper_runtime.shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionConfig,
    bootstrap_fast_paper_shadow_service_execution,
)
from shreks_brain.fast_paper_runtime.shadow_supervisor import (
    FastPaperShadowSupervisorConfig,
    bootstrap_fast_paper_shadow_supervisor,
    run_fast_paper_shadow_supervisor_cycle,
)
from shreks_brain.observer_campaign import ObserverRegimeReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.paper import PaperPositionState
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_fast_paper_shadow_buy_authority_evidence_adapter import (
    _execution_policy as _economics_policy,
    _market_policy,
    _safety_policy,
)
from test_fast_paper_shadow_decision import (
    _champion,
    _policy as _action_policy,
    _record,
)
from test_fast_paper_shadow_execution_input import (
    _execution_policy as _shadow_execution_policy,
    _decision,
)
from test_fast_paper_shadow_executor import _record_at
from test_regime_engine import policy as _regime_policy


_RELEASE_SHA = "a" * 40
_QUOTE_RATE_USD = 100.0
_ENTRY_QUOTE_RAW = 5_000_000_000
_BASE_RAW = 5_000_000
_DECISION_AT = 20_000
_ENTRY_AT = 20_010
_MARKET_AT = 20_012
_SAFETY_EXIT_AT = 20_014
_EXIT_AT = 20_015
_USD_AT = 20_017
_EVALUATED_AT = 20_020
_COMMITTED_AT = 20_030


def _executable(path: Path, payload: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o700)
    return path


def _entry_authority_binary(path: Path) -> Path:
    return _executable(
        path,
        """#!/usr/bin/env python3
import hashlib
import json
import sys

request = json.loads(open(sys.argv[1], encoding="utf-8").read())
entry = request["execution"]["cost_model"]["entry"]
trade = request["execution"]["trade"]
variable = (
    entry["effective_fee_bps"]
    + entry["expected_impact_bps"]
    + entry["expected_slippage_bps"]
    + entry["expected_latency_bps"]
)
fixed = (
    entry["network_fee_quote"]
    + entry["priority_fee_quote"]
    + entry["expected_failure_cost_quote"]
)
material = {
    "schema_name": "shreks.fast_deterministic_entry_authority_result",
    "schema_version": 1,
    "mint": request["mint"],
    "quote_mint": request["quote_mint"],
    "intended_base_quantity": trade["base_quantity"],
    "decision_executable_entry_price_quote": request[
        "decision_executable_entry_price_quote"
    ],
    "maximum_acceptable_entry_price_quote": (
        request["decision_executable_entry_price_quote"] * 1.10
    ),
    "expected_entry_variable_cost_bps": variable,
    "expected_entry_fixed_cost_quote": fixed,
}
fingerprint = hashlib.sha256(
    json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()
material["result_fingerprint_sha256"] = fingerprint
print(
    json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
)
""",
    )


def _write_service_policy(
    path: Path,
    policy: FastPaperShadowServicePolicy,
) -> None:
    path.write_text(
        json.dumps(
            asdict(policy),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _observer_database(
    path: Path,
    *,
    feature,
    service: FastPaperShadowServicePolicy,
) -> None:
    connection = sqlite3.connect(path)
    try:
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
                base_mint TEXT NOT NULL,
                quote_mint TEXT NOT NULL,
                price_native TEXT,
                price_usd REAL,
                liquidity_usd REAL,
                volume_m5_usd REAL,
                volume_h1_usd REAL,
                volume_h24_usd REAL,
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
            """
            INSERT INTO token_candidates
                (id, mint, pair_address, discovery_source,
                 discovered_at_unix_ms, venue)
            VALUES (7, ?, 'pair-first-buy', 'pump', 19000, ?)
            """,
            (feature.mint, feature.venue),
        )
        connection.execute(
            """
            INSERT INTO token_mint_states
                (id, candidate_id, provider, decimals, mint_authority,
                 freeze_authority, slot, observed_at_unix_ms)
            VALUES (1, 7, 'helius', 6, NULL, NULL, '1', 20008)
            """
        )
        connection.execute(
            """
            INSERT INTO token_holder_distributions
                (id, candidate_id, provider, mint, last_indexed_slot,
                 observed_at_unix_ms, complete, top_holder_concentration_pct)
            VALUES (1, 7, 'helius', ?, '1', 20009, 1, 10.0)
            """,
            (feature.mint,),
        )
        connection.execute(
            """
            INSERT INTO market_snapshots
                (id, candidate_id, observed_at_unix_ms, source,
                 source_observed_at_unix_ms, venue, pair_address,
                 base_mint, quote_mint, price_native, price_usd,
                 liquidity_usd, volume_m5_usd, volume_h1_usd,
                 volume_h24_usd, buys_m5, sells_m5, buys_h1, sells_h1,
                 pair_created_at_unix_ms)
            VALUES
                (1, 7, ?, 'dexscreener', ?, ?, 'pair-first-buy',
                 ?, ?, '1.0', 100.0, 100000.0, 25000.0, 50000.0,
                 100000.0, 20, 5, 100, 30, 19000)
            """,
            (
                _MARKET_AT,
                _MARKET_AT - 1,
                feature.venue,
                feature.mint,
                feature.quote_mint,
            ),
        )
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots
                (id, candidate_id, purpose, provider, probe_policy_version,
                 input_mint, output_mint, taker, input_amount,
                 output_amount, minimum_output_amount, slippage_bps,
                 route_available, price_impact_pct, route_labels_json,
                 quoted_at_unix_ms)
            VALUES
                (1, 7, 'entry', 'jupiter', ?, ?, ?, ?, ?, ?, ?, ?,
                 1, '0.2', '["route-a"]', ?)
            """,
            (
                service.probe_policy_version,
                feature.quote_mint,
                feature.mint,
                service.taker,
                str(service.entry_input_amount_raw),
                str(_BASE_RAW),
                str(_BASE_RAW),
                service.slippage_bps,
                _ENTRY_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots
                (id, candidate_id, purpose, provider, probe_policy_version,
                 input_mint, output_mint, taker, input_amount,
                 output_amount, minimum_output_amount, slippage_bps,
                 route_available, price_impact_pct, route_labels_json,
                 quoted_at_unix_ms)
            VALUES
                (2, 7, 'exit', 'jupiter', ?, ?, ?, ?, ?, ?, ?, ?,
                 1, '0.2', '["route-a"]', ?)
            """,
            (
                service.probe_policy_version,
                feature.mint,
                feature.quote_mint,
                service.taker,
                str(service.exit_input_amount_raw),
                str(_ENTRY_QUOTE_RAW),
                str(_ENTRY_QUOTE_RAW),
                service.slippage_bps,
                _EXIT_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO exit_quote_snapshots
                (id, candidate_id, provider, probe_policy_version,
                 input_mint, output_mint, taker, input_amount,
                 output_amount, minimum_output_amount, slippage_bps,
                 route_available, price_impact_pct, quoted_at_unix_ms)
            VALUES
                (1, 7, 'jupiter', ?, ?, ?, ?, ?, ?, ?, ?,
                 1, '0.2', ?)
            """,
            (
                service.probe_policy_version,
                feature.mint,
                feature.quote_mint,
                service.taker,
                str(service.exit_input_amount_raw),
                str(_ENTRY_QUOTE_RAW),
                str(_ENTRY_QUOTE_RAW),
                service.slippage_bps,
                _SAFETY_EXIT_AT,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _runtime_fixture(tmp_path: Path):
    authority = tmp_path / "authority"
    binaries = authority / "bin"
    shadow_root = tmp_path / "shadow"
    authority.mkdir()
    binaries.mkdir()
    shadow_root.mkdir()

    feature = _record_at(
        _record(),
        signature="first-learned-buy",
        sequence=1,
        at=_DECISION_AT,
    )
    champion_path = _champion(authority)
    decision_binary = _executable(
        binaries / "shreks-fast-campaign-decision"
    )
    feature_binary = _executable(
        binaries / "export_fast_runtime_features"
    )
    entry_authority_binary = _entry_authority_binary(
        binaries / "shreks-fast-entry-authority"
    )

    observer_database = authority / "observer.sqlite3"
    authoritative_paper = authority / "authoritative-paper.sqlite3"
    authoritative_bytes = b"authoritative-paper-sentinel\n"
    authoritative_paper.write_bytes(authoritative_bytes)

    decision_directory = shadow_root / "decision"
    manifest = build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=champion_path,
        decision_binary_path=decision_binary,
        feature_feed_binary_path=feature_binary,
        action_policy=_action_policy(),
        state_version="fast-state-v1",
        risk_policy_version="fast-risk-v1",
        fill_policy_version="paper-fill-v1",
        position_action_policy_version="fl7.4-v1",
        strategy_family="fast-lane-learned",
        strategy_version="fast-lane-learned-v1",
        assessment_version="fast-paper-assessment-v1",
        observer_database_path=observer_database,
        paper_evidence_path=authoritative_paper,
        checkpoint_path=decision_directory / "runtime-state.json",
        quote_provider="jupiter",
        quote_mint=feature.quote_mint,
        quote_decimals=9,
        route_evidence_version="observer-paper-quote-v1",
    )
    manifest_path = authority / "runtime-manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)

    service = FastPaperShadowServicePolicy(
        schema_name=FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION,
        route_evidence_version=manifest.route_evidence_version,
        probe_policy_version="probe-v2",
        taker="Taker111",
        slippage_bps=75,
        entry_input_amount_raw=_ENTRY_QUOTE_RAW,
        exit_input_amount_raw=_BASE_RAW,
        max_quote_age_ms=2_000,
        max_exposure_fraction=0.75,
    )
    service_path = authority / "service-policy.json"
    _write_service_policy(service_path, service)

    _observer_database(
        observer_database,
        feature=feature,
        service=service,
    )

    base_execution = _shadow_execution_policy(manifest)
    execution_policy = build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=base_execution.risk_policy,
        fill_policy=replace(
            base_execution.fill_policy,
            assumed_latency_ms=0,
        ),
        position_action_policy=base_execution.position_action_policy,
    )
    execution_policy_path = authority / "execution-policy.json"
    write_fast_paper_shadow_execution_policy(
        execution_policy,
        execution_policy_path,
    )

    operator = authority / "risk" / "operator-control.json"
    operator.parent.mkdir()
    initialize_operator_risk_control_state(
        operator,
        observed_at_unix_ms=19_000,
    )

    quote_policy = FastPaperShadowQuoteReadPolicy(
        version=service.route_evidence_version,
        candidate_id=7,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        exit_input_amount_raw=service.exit_input_amount_raw,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    regime_read = ObserverRegimeReadPolicy(
        version="shadow-first-buy-regime-read-v1",
        window_ms=600_000,
        max_snapshot_age_ms=60_000,
        source_priority=("dexscreener",),
        entry_probe_policy_version=service.probe_policy_version,
        quote_asset_mint=manifest.quote_mint,
        entry_input_amount=service.entry_input_amount_raw,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
    )
    safety_probe = ObserverSafetyProbeIdentity(
        probe_policy_version=service.probe_policy_version,
        output_mint=manifest.quote_mint,
        input_amount=service.exit_input_amount_raw,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
    )
    buy_writer_policy = build_fast_paper_shadow_buy_writer_policy(
        market_read_policy=_market_policy(),
        regime_read_policy=regime_read,
        regime_policy=_regime_policy(min_candidate_samples=1),
        safety_policy=_safety_policy(),
        safety_probe_identity=safety_probe,
        execution_economics_policies=(
            _economics_policy(feature),
        ),
        operator_risk_control_path=operator,
        entry_authority_binary_path=entry_authority_binary,
        entry_authority_binary_sha256=hashlib.sha256(
            entry_authority_binary.read_bytes()
        ).hexdigest(),
        day_started_at_unix_ms=19_000,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )
    buy_writer_policy_path = authority / "buy-writer-policy.json"
    write_fast_paper_shadow_buy_writer_policy(
        buy_writer_policy,
        buy_writer_policy_path,
    )

    decision_config = FastPaperShadowServiceConfig(
        manifest_path=manifest_path.resolve(),
        policy_path=service_path.resolve(),
        evidence_directory=decision_directory.resolve(),
        cycle_interval_seconds=2.0,
        maximum_decisions=1,
    )
    execution_config = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=execution_policy_path.resolve(),
        source_directory=(shadow_root / "execution-sources").resolve(),
        ledger_database_path=(shadow_root / "ledger.sqlite3").resolve(),
        run_id="first-learned-buy-e2e",
    )
    supervisor_config = FastPaperShadowSupervisorConfig(
        decision_config=decision_config,
        execution_config=execution_config,
        buy_authority_source_directory=(
            shadow_root / "buy-authority-sources"
        ).resolve(),
        quote_usd_source_directory=(
            shadow_root / "quote-usd-sources"
        ).resolve(),
        reduction_source_directory=(
            shadow_root / "reduction-sources"
        ).resolve(),
        pending_buy_retry_source_directory=(
            shadow_root / "pending-buy-retry-sources"
        ).resolve(),
        buy_writer_policy_path=buy_writer_policy_path.resolve(),
    )
    provision = FastPaperShadowProvisionConfig(
        supervisor_config=supervisor_config,
        starting_cash_usd=20_000.0,
    )
    return (
        manifest,
        service,
        feature,
        quote_policy,
        execution_policy,
        supervisor_config,
        provision,
        authoritative_paper,
        authoritative_bytes,
    )


def test_first_learned_buy_reaches_isolated_ledger_end_to_end(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        service,
        feature,
        quote_policy,
        execution_policy,
        supervisor_config,
        provision_config,
        authoritative_paper,
        authoritative_bytes,
    ) = _runtime_fixture(tmp_path)

    provisioned = provision_fast_paper_shadow(
        provision_config,
        clock_unix_ms=lambda: 19_000,
    )
    assert provisioned.created is True
    assert provisioned.supervisor_bootstrap.execution_bootstrap.checkpoint.sequence == 0

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        FastCampaignDecisionPosition(kind="FLAT"),
        quote_policy,
        evaluated_at_unix_ms=_EVALUATED_AT,
        max_exposure_fraction=service.max_exposure_fraction,
    )
    assert cycle.entry_quote.execution_price_quote == pytest.approx(1.0)
    assert cycle.entry_quote.quoted_base_quantity == pytest.approx(5.0)
    assert cycle.entry_quote.available_base_quantity == pytest.approx(5.0)
    assert cycle.exit_quote.execution_price_quote == pytest.approx(1.0)

    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _decision(manifest, batch.decisions[0], action="BUY")
        ),
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(shadow.time, "monotonic_ns", lambda: next(ticks))

    evidence = evaluate_fast_paper_shadow_decision(
        manifest,
        feature,
        FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at_unix_ms=_EVALUATED_AT,
        max_exposure_fraction=service.max_exposure_fraction,
        entry_quote=cycle.entry_quote,
        exit_quote=cycle.exit_quote,
    )
    evidence_path = (
        supervisor_config.decision_config.evidence_directory
        / f"shadow-{evidence.source_sequence:020d}-first-buy.json"
    )
    write_fast_paper_shadow_decision_evidence(evidence, evidence_path)

    decision_state = build_fast_paper_runtime_state(
        manifest,
        cursor=FastPaperRuntimeCursor(
            decision_sequence=feature.decision_sequence,
            decision_signature=feature.decision_signature,
            decision_ordinal=feature.decision_ordinal,
            decision_observed_at_unix_ms=(
                feature.decision_observed_at_unix_ms
            ),
        ),
    )
    write_fast_paper_runtime_state(
        decision_state,
        manifest.checkpoint_path,
    )

    quote_usd = FastPaperShadowQuoteUsdEvidence(
        quote_mint=manifest.quote_mint,
        observed_at_unix_ms=_USD_AT,
        quote_to_usd_rate=_QUOTE_RATE_USD,
        source_version="first-buy-e2e-usd-v1",
        source_fingerprint_sha256="d" * 64,
    )
    usd_record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        quote_usd,
    )
    write_fast_paper_shadow_quote_usd_source_record(
        usd_record,
        supervisor_config.quote_usd_source_directory,
    )

    before_authoritative = authoritative_paper.read_bytes()
    bootstrap = bootstrap_fast_paper_shadow_supervisor(supervisor_config)
    updated, decisions_produced, executions_committed = (
        run_fast_paper_shadow_supervisor_cycle(
            bootstrap,
            supervisor_config,
            clock_unix_ms=lambda: _COMMITTED_AT,
        )
    )

    assert decisions_produced == 0
    assert executions_committed == 1

    execution = updated.execution_bootstrap
    assert execution.checkpoint.sequence == 1
    assert (
        execution.runtime_state.last_processed_source_sequence
        == feature.decision_sequence
    )
    assert execution.runtime_state.pending_buy is None
    assert len(execution.runtime_state.market_positions) == 1
    mapping = execution.runtime_state.market_positions[0]
    assert mapping.market_key == evidence.market_key
    assert mapping.mint == feature.mint
    assert mapping.current_exposure_fraction == pytest.approx(0.5)

    ledger = execution.checkpoint.state.ledger
    assert ledger.starting_cash_usd == pytest.approx(20_000.0)
    assert ledger.cash_balance_usd < ledger.starting_cash_usd
    assert len(ledger.entries) == 1
    assert len(ledger.processed_intent_keys) == 1
    assert len(ledger.positions) == 1
    position = ledger.positions[0]
    assert position.state is PaperPositionState.OPEN
    assert position.mint == feature.mint
    assert position.quantity == pytest.approx(5.0)
    assert position.buy_fill_count == 1
    assert position.sell_fill_count == 0

    authority_path = supervisor_config.buy_authority_source_directory / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    source_path = supervisor_config.execution_config.source_directory / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    assert authority_path.is_file()
    assert source_path.is_file()

    restarted = bootstrap_fast_paper_shadow_service_execution(
        manifest,
        supervisor_config.execution_config,
    )
    assert restarted.checkpoint == execution.checkpoint
    assert restarted.runtime_state == execution.runtime_state
    assert restarted.checkpoint.state.ledger == ledger
    assert len(restarted.checkpoint.state.ledger.positions) == 1
    assert restarted.checkpoint.state.ledger.positions[0].state is (
        PaperPositionState.OPEN
    )

    assert authoritative_paper.read_bytes() == before_authoritative
    assert before_authoritative == authoritative_bytes
    assert manifest.runtime_mode == "PAPER"
    assert execution.execution_policy == execution_policy
