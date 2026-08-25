from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.observer_market.models import (
    OBSERVER_MARKET_SCHEMA_VERSION,
    ObservedMarketWindow,
    ObserverCandidateIdentity,
    ObserverMarketSnapshot,
)
from shreks_brain.observer_safety.assembler import (
    ObserverSafetyAssemblyError,
    assess_observer_safety,
    build_safety_inputs,
)
from shreks_brain.observer_safety.models import ObserverSafetyProbeIdentity
from shreks_brain.observer_safety.store import ObserverSafetyEvidenceStore
from shreks_brain.safety import (
    SafetyDecision,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    assess_safety,
)


_SCHEMA = """
CREATE TABLE token_candidates (
    id INTEGER PRIMARY KEY,
    mint TEXT NOT NULL
);
CREATE TABLE token_mint_states (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    owner_program TEXT NOT NULL,
    supply TEXT NOT NULL,
    decimals INTEGER NOT NULL,
    mint_authority TEXT,
    freeze_authority TEXT,
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL
);
CREATE TABLE token_holder_distributions (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    mint TEXT NOT NULL,
    last_indexed_slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    reported_total_accounts TEXT NOT NULL,
    accounts_scanned INTEGER NOT NULL,
    unique_owners INTEGER NOT NULL,
    pages_scanned INTEGER NOT NULL,
    complete INTEGER NOT NULL,
    total_balance_raw TEXT NOT NULL,
    largest_owner TEXT,
    largest_owner_balance_raw TEXT,
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
    route_labels_json TEXT NOT NULL,
    quoted_at_unix_ms INTEGER NOT NULL
);
"""


def _probe(**overrides) -> ObserverSafetyProbeIdentity:
    values = {
        "probe_policy_version": "probe-v1",
        "output_mint": "So11111111111111111111111111111111111111112",
        "input_amount": 1_000,
        "taker": "Taker111",
        "slippage_bps": 75,
    }
    values.update(overrides)
    return ObserverSafetyProbeIdentity(**values)


def _policy(**overrides) -> SafetyPolicy:
    values = {
        "version": "b1-v1",
        "min_liquidity_usd": 5_000.0,
        "soft_min_liquidity_usd": 10_000.0,
        "max_top_holder_concentration_pct": 40.0,
        "soft_max_top_holder_concentration_pct": 25.0,
        "soft_max_creator_concentration_pct": 15.0,
        "soft_max_exit_price_impact_pct": 8.0,
        "max_critical_data_age_ms": 10_000,
    }
    values.update(overrides)
    return SafetyPolicy(**values)


def _window(*, as_of_unix_ms: int = 100_000, observed_at_unix_ms: int = 99_000) -> ObservedMarketWindow:
    candidate = ObserverCandidateIdentity(
        candidate_id=7,
        mint="Mint111",
        pair_address="Pair111",
        discovery_source="pump",
        discovered_at_unix_ms=1_000,
        venue="pump_fun_bonding_curve",
    )
    current = ObserverMarketSnapshot(
        row_id=1,
        candidate_id=7,
        observed_at_unix_ms=observed_at_unix_ms,
        source="dexscreener",
        source_observed_at_unix_ms=observed_at_unix_ms,
        venue="pump_swap",
        pair_address="Pair111",
        price_usd=1.0,
        liquidity_usd=20_000.0,
        volume_m5_usd=None,
        volume_h1_usd=None,
        buys_m5=None,
        sells_m5=None,
        buys_h1=None,
        sells_h1=None,
        pair_created_at_unix_ms=1_000,
    )
    return ObservedMarketWindow(
        schema_version=OBSERVER_MARKET_SCHEMA_VERSION,
        policy_version="observer-market-v1",
        candidate=candidate,
        as_of_unix_ms=as_of_unix_ms,
        selected_source="dexscreener",
        selected_pair_address="Pair111",
        current=current,
        one_minute_ago=None,
        five_minutes_ago=None,
        fifteen_minutes_ago=None,
        pair_created_at_unix_ms=1_000,
        local_high_price_usd=1.0,
        local_low_price_usd=1.0,
    )


def _create_evidence_database(
    path: Path,
    *,
    include_mint: bool = True,
    include_holder: bool = True,
    holder_complete: bool = True,
    include_quote: bool = True,
    route_available: bool = True,
    mint_authority: str | None = None,
    freeze_authority: str | None = None,
    mint_observed_at_unix_ms: int = 98_000,
    holder_observed_at_unix_ms: int = 97_000,
    quote_observed_at_unix_ms: int = 96_000,
    quote_probe_policy_version: str = "probe-v1",
    quote_taker: str = "Taker111",
    price_impact_pct: str | None = "2.5",
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT INTO token_candidates (id, mint) VALUES (?, ?)",
            (7, "Mint111"),
        )
        if include_mint:
            connection.execute(
                """INSERT INTO token_mint_states (
                       id, candidate_id, provider, owner_program, supply, decimals,
                       mint_authority, freeze_authority, slot, observed_at_unix_ms
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    1,
                    7,
                    "helius",
                    "Token",
                    "1000",
                    6,
                    mint_authority,
                    freeze_authority,
                    "10",
                    mint_observed_at_unix_ms,
                ),
            )
        if include_holder:
            connection.execute(
                """INSERT INTO token_holder_distributions (
                       id, candidate_id, provider, mint, last_indexed_slot,
                       observed_at_unix_ms, reported_total_accounts, accounts_scanned,
                       unique_owners, pages_scanned, complete, total_balance_raw,
                       largest_owner, largest_owner_balance_raw, top_holder_concentration_pct
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    1,
                    7,
                    "helius",
                    "Mint111",
                    "11",
                    holder_observed_at_unix_ms,
                    "2",
                    2,
                    2,
                    1,
                    1 if holder_complete else 0,
                    "1000",
                    "Owner111",
                    "200",
                    20.0 if holder_complete else 88.0,
                ),
            )
        if include_quote:
            connection.execute(
                """INSERT INTO exit_quote_snapshots (
                       id, candidate_id, provider, probe_policy_version, input_mint,
                       output_mint, taker, input_amount, output_amount,
                       minimum_output_amount, slippage_bps, route_available,
                       price_impact_pct, route_labels_json, quoted_at_unix_ms
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    1,
                    7,
                    "jupiter",
                    quote_probe_policy_version,
                    "Mint111",
                    _probe().output_mint,
                    quote_taker,
                    "1000",
                    "900" if route_available else "0",
                    "850" if route_available else "0",
                    75,
                    1 if route_available else 0,
                    price_impact_pct if route_available else None,
                    '["PumpSwap"]' if route_available else "[]",
                    quote_observed_at_unix_ms,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _store(path: Path) -> ObserverSafetyEvidenceStore:
    return ObserverSafetyEvidenceStore(path)


def _codes(assessment) -> tuple[SafetyReasonCode, ...]:
    return tuple(finding.code for finding in assessment.findings)


def test_clean_persisted_evidence_builds_exact_b1_inputs(tmp_path):
    path = tmp_path / "clean.sqlite3"
    _create_evidence_database(path)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)

    assert inputs == SafetyInputs(
        as_of_unix_ms=100_000,
        mint_authority_active=False,
        freeze_authority_active=False,
        liquidity_usd=20_000.0,
        top_holder_concentration_pct=20.0,
        creator_concentration_pct=None,
        exit_quote_available=True,
        exit_price_impact_pct=2.5,
        execution_trap_detected=False,
        critical_data_observed_at_unix_ms=96_000,
        critical_data_contradictory=False,
        global_risk_halt=False,
    )


def test_assessment_wrapper_delegates_to_sealed_b1_evaluator(tmp_path):
    path = tmp_path / "delegate.sqlite3"
    _create_evidence_database(path)
    window = _window()
    store = _store(path)
    probe = _probe()
    policy = _policy()

    inputs = build_safety_inputs(window, store, probe, False)
    expected = assess_safety(inputs, policy)
    actual = assess_observer_safety(
        window,
        store,
        probe,
        policy,
        global_risk_halt=False,
    )

    assert actual == expected
    assert actual.decision is SafetyDecision.PASS


def test_missing_mint_state_keeps_authorities_unknown_and_b1_incomplete(tmp_path):
    path = tmp_path / "missing-mint.sqlite3"
    _create_evidence_database(path, include_mint=False)

    assessment = assess_observer_safety(
        _window(), _store(path), _probe(), _policy(), global_risk_halt=False
    )

    assert assessment.decision is SafetyDecision.INCOMPLETE
    assert SafetyReasonCode.MINT_AUTHORITY_UNKNOWN in _codes(assessment)
    assert SafetyReasonCode.FREEZE_AUTHORITY_UNKNOWN in _codes(assessment)


@pytest.mark.parametrize("include_holder", [False, True])
def test_missing_or_incomplete_holder_evidence_stays_unknown(tmp_path, include_holder):
    path = tmp_path / f"holder-{include_holder}.sqlite3"
    _create_evidence_database(
        path,
        include_holder=include_holder,
        holder_complete=False if include_holder else True,
    )

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy())

    assert inputs.top_holder_concentration_pct is None
    assert assessment.decision is SafetyDecision.INCOMPLETE
    assert SafetyReasonCode.HOLDER_CONCENTRATION_UNKNOWN in _codes(assessment)


def test_no_exact_probe_quote_stays_unknown_and_b1_incomplete(tmp_path):
    path = tmp_path / "wrong-probe.sqlite3"
    _create_evidence_database(path, quote_taker="OtherTaker")

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy())

    assert inputs.exit_quote_available is None
    assert inputs.exit_price_impact_pct is None
    assert assessment.decision is SafetyDecision.INCOMPLETE
    assert SafetyReasonCode.EXIT_QUOTE_UNKNOWN in _codes(assessment)


def test_explicit_route_unavailable_is_hard_rejection_not_unknown(tmp_path):
    path = tmp_path / "no-route.sqlite3"
    _create_evidence_database(path, route_available=False)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy())

    assert inputs.exit_quote_available is False
    assert inputs.exit_price_impact_pct is None
    assert assessment.decision is SafetyDecision.REJECT
    assert SafetyReasonCode.EXIT_QUOTE_UNAVAILABLE in _codes(assessment)


def test_active_mint_authority_is_hard_rejection(tmp_path):
    path = tmp_path / "authority.sqlite3"
    _create_evidence_database(path, mint_authority="Authority111")

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy())

    assert inputs.mint_authority_active is True
    assert assessment.decision is SafetyDecision.REJECT
    assert SafetyReasonCode.MINT_AUTHORITY_ACTIVE in _codes(assessment)


def test_oldest_consumed_critical_evidence_controls_freshness(tmp_path):
    path = tmp_path / "stale.sqlite3"
    _create_evidence_database(path, mint_observed_at_unix_ms=80_000)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy(max_critical_data_age_ms=10_000))

    assert inputs.critical_data_observed_at_unix_ms == 80_000
    assert assessment.decision is SafetyDecision.INCOMPLETE
    assert SafetyReasonCode.CRITICAL_DATA_STALE in _codes(assessment)


def test_future_evidence_is_invisible_to_point_in_time_assembly(tmp_path):
    path = tmp_path / "future.sqlite3"
    _create_evidence_database(path, mint_observed_at_unix_ms=100_001)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)
    assessment = assess_safety(inputs, _policy())

    assert inputs.mint_authority_active is None
    assert inputs.freeze_authority_active is None
    assert assessment.decision is SafetyDecision.INCOMPLETE


def test_explicit_global_risk_halt_is_preserved_and_rejects(tmp_path):
    path = tmp_path / "halt.sqlite3"
    _create_evidence_database(path)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), True)
    assessment = assess_safety(inputs, _policy())

    assert inputs.global_risk_halt is True
    assert assessment.decision is SafetyDecision.REJECT
    assert SafetyReasonCode.GLOBAL_RISK_HALT in _codes(assessment)


def test_creator_concentration_and_execution_trap_are_never_guessed(tmp_path):
    path = tmp_path / "unknown-unimplemented.sqlite3"
    _create_evidence_database(path)

    inputs = build_safety_inputs(_window(), _store(path), _probe(), False)

    assert inputs.creator_concentration_pct is None
    assert inputs.execution_trap_detected is False
    assert inputs.critical_data_contradictory is False


@pytest.mark.parametrize("raw", ["not-a-number", "nan", "inf", "-0.1", "101"])
def test_malformed_nonfinite_or_out_of_range_price_impact_fails_closed(tmp_path, raw):
    path = tmp_path / "bad-impact.sqlite3"
    _create_evidence_database(path, price_impact_pct=raw)

    with pytest.raises(ObserverSafetyAssemblyError, match="price impact"):
        build_safety_inputs(_window(), _store(path), _probe(), False)
