from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from fast_forecast_fixtures import feature_record
from shreks_brain.fast_campaign import (
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
)
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowQuoteReadPolicy,
    FastPaperShadowReductionRead,
    build_fast_paper_runtime_manifest,
    resolve_fast_paper_shadow_cycle_input,
)


_RELEASE_SHA = "a" * 40
_QUOTE_MINT = "So11111111111111111111111111111111111111112"


def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(250,),
        entry_exposure_candidates=(0.25, 0.5),
        reduce_target_exposure_candidates=(0.25,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=2.0,
        route_unavailability_penalty_bps=3.0,
        horizon_disagreement_weight=0.5,
        minimum_buy_value_bps=4.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )


def _champion(tmp_path: Path) -> Path:
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="persisted-quote-resolver-v1",
        decision_reference="persisted-quote-resolver-fixture",
        decided_at_unix_ms=1_000,
        reason="fixture",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    return path


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "observer.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE token_candidates (
                id INTEGER PRIMARY KEY,
                mint TEXT NOT NULL
            );
            CREATE TABLE token_mint_states (
                id INTEGER PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                decimals INTEGER NOT NULL,
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
            """
        )
        connection.execute(
            "INSERT INTO token_candidates (id, mint) VALUES (?, ?)",
            (7, "mint-fl8-2"),
        )
        connection.execute(
            """
            INSERT INTO token_mint_states
                (id, candidate_id, decimals, observed_at_unix_ms)
            VALUES (?, ?, ?, ?)
            """,
            (1, 7, 6, 1_990),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _manifest(tmp_path: Path):
    database = _database(tmp_path)
    return build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=_champion(tmp_path),
        decision_binary_path=_executable(
            tmp_path / "shreks-fast-campaign-decision"
        ),
        feature_feed_binary_path=_executable(
            tmp_path / "export_fast_runtime_features"
        ),
        action_policy=_policy(),
        state_version="fast-state-v1",
        risk_policy_version="fast-risk-v1",
        fill_policy_version="paper-fill-v1",
        position_action_policy_version="fl7.4-v1",
        strategy_family="fast-lane-learned",
        strategy_version="fast-lane-learned-v1",
        assessment_version="fast-paper-assessment-v1",
        observer_database_path=database,
        paper_evidence_path=tmp_path / "paper-evidence.sqlite3",
        checkpoint_path=tmp_path / "fast-paper-runtime-state.json",
        quote_provider="jupiter",
        quote_mint=_QUOTE_MINT,
        quote_decimals=9,
        route_evidence_version="shadow-persisted-quote-v1",
    )


def _record():
    return replace(
        feature_record(
            0,
            0.0,
            signature="persisted-quote-event",
            observed_at_unix_ms=2_000,
            with_context=True,
        ),
        decision_executable_entry_price_quote=0.05,
    )


def _read_policy(
    *,
    reductions: tuple[FastPaperShadowReductionRead, ...] = (),
    max_quote_age_ms: int = 100,
) -> FastPaperShadowQuoteReadPolicy:
    return FastPaperShadowQuoteReadPolicy(
        version="shadow-persisted-quote-v1",
        candidate_id=7,
        probe_policy_version="probe-v1",
        taker="paper-taker",
        slippage_bps=100,
        entry_input_amount_raw=1_000_000_000,
        exit_input_amount_raw=20_000_000,
        max_quote_age_ms=max_quote_age_ms,
        reduction_reads=reductions,
    )


def _insert_quote(
    database: str,
    *,
    row_id: int,
    purpose: str,
    input_mint: str,
    output_mint: str,
    input_amount: int,
    output_amount: int,
    minimum_output_amount: int,
    quoted_at: int,
    route_available: bool = True,
) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots (
                id, candidate_id, purpose, provider, probe_policy_version,
                input_mint, output_mint, taker, input_amount, output_amount,
                minimum_output_amount, slippage_bps, route_available,
                price_impact_pct, route_labels_json, quoted_at_unix_ms
            ) VALUES (?, 7, ?, 'jupiter', 'probe-v1', ?, ?, 'paper-taker',
                      ?, ?, ?, 100, ?, NULL, ?, ?)
            """,
            (
                row_id,
                purpose,
                input_mint,
                output_mint,
                str(input_amount),
                str(output_amount),
                str(minimum_output_amount),
                1 if route_available else 0,
                '["route-a"]' if route_available else "[]",
                quoted_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_persisted_quote_resolver_builds_exact_cycle_input_without_mutating_db(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    record = _record()
    database = manifest.observer_database_path
    _insert_quote(
        database,
        row_id=1,
        purpose="entry",
        input_mint=_QUOTE_MINT,
        output_mint=record.mint,
        input_amount=1_000_000_000,
        output_amount=20_000_000,
        minimum_output_amount=19_000_000,
        quoted_at=2_010,
    )
    _insert_quote(
        database,
        row_id=2,
        purpose="exit",
        input_mint=record.mint,
        output_mint=_QUOTE_MINT,
        input_amount=20_000_000,
        output_amount=980_000_000,
        minimum_output_amount=970_000_000,
        quoted_at=2_015,
    )

    before = Path(database).read_bytes()
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        _read_policy(),
        evaluated_at_unix_ms=2_020,
        max_exposure_fraction=0.5,
    )
    assert Path(database).read_bytes() == before

    assert cycle.record == record
    assert cycle.position.kind == "FLAT"
    assert cycle.entry_quote.state == "EXECUTABLE"
    assert cycle.entry_quote.reference_price_quote == pytest.approx(0.05)
    assert cycle.entry_quote.execution_price_quote == pytest.approx(0.05)
    assert cycle.entry_quote.quoted_base_quantity == pytest.approx(20.0)
    assert cycle.entry_quote.available_base_quantity == pytest.approx(19.0)
    assert cycle.exit_quote.execution_price_quote == pytest.approx(0.049)
    assert cycle.exit_quote.quoted_base_quantity == pytest.approx(20.0)
    assert cycle.exit_quote.available_base_quantity == pytest.approx(20.0)
    assert cycle.reduction_quotes == ()


def test_persisted_quote_resolver_resolves_ordered_reduction_quotes_for_open_position(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    record = _record()
    database = manifest.observer_database_path
    for args in (
        dict(
            row_id=1,
            purpose="entry",
            input_mint=_QUOTE_MINT,
            output_mint=record.mint,
            input_amount=1_000_000_000,
            output_amount=20_000_000,
            minimum_output_amount=19_000_000,
            quoted_at=2_010,
        ),
        dict(
            row_id=2,
            purpose="exit",
            input_mint=record.mint,
            output_mint=_QUOTE_MINT,
            input_amount=20_000_000,
            output_amount=980_000_000,
            minimum_output_amount=970_000_000,
            quoted_at=2_015,
        ),
        dict(
            row_id=3,
            purpose="exit",
            input_mint=record.mint,
            output_mint=_QUOTE_MINT,
            input_amount=10_000_000,
            output_amount=495_000_000,
            minimum_output_amount=490_000_000,
            quoted_at=2_012,
        ),
    ):
        _insert_quote(database, **args)

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        _read_policy(
            reductions=(
                FastPaperShadowReductionRead(
                    target_exposure_fraction=0.25,
                    input_amount_raw=10_000_000,
                ),
            )
        ),
        evaluated_at_unix_ms=2_020,
        max_exposure_fraction=0.75,
    )

    assert len(cycle.reduction_quotes) == 1
    reduction = cycle.reduction_quotes[0]
    assert reduction.target_exposure_fraction == pytest.approx(0.25)
    assert reduction.quote.execution_price_quote == pytest.approx(0.0495)
    assert reduction.quote.quoted_base_quantity == pytest.approx(10.0)


def test_persisted_quote_resolver_preserves_explicit_unavailable_evidence(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    record = _record()
    database = manifest.observer_database_path
    _insert_quote(
        database,
        row_id=1,
        purpose="entry",
        input_mint=_QUOTE_MINT,
        output_mint=record.mint,
        input_amount=1_000_000_000,
        output_amount=20_000_000,
        minimum_output_amount=19_000_000,
        quoted_at=2_010,
    )
    _insert_quote(
        database,
        row_id=2,
        purpose="exit",
        input_mint=record.mint,
        output_mint=_QUOTE_MINT,
        input_amount=20_000_000,
        output_amount=0,
        minimum_output_amount=0,
        quoted_at=2_015,
        route_available=False,
    )

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        _read_policy(),
        evaluated_at_unix_ms=2_020,
        max_exposure_fraction=0.5,
    )

    assert cycle.exit_quote.state == "UNAVAILABLE"
    assert cycle.exit_quote.reference_price_quote is None
    assert cycle.exit_quote.execution_price_quote is None
    assert cycle.exit_quote.quoted_base_quantity is None
    assert cycle.exit_quote.available_base_quantity is None


def test_persisted_quote_resolver_fails_closed_on_stale_missing_or_conflicting_evidence(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    record = _record()
    database = manifest.observer_database_path
    _insert_quote(
        database,
        row_id=1,
        purpose="entry",
        input_mint=_QUOTE_MINT,
        output_mint=record.mint,
        input_amount=1_000_000_000,
        output_amount=20_000_000,
        minimum_output_amount=19_000_000,
        quoted_at=2_001,
    )
    _insert_quote(
        database,
        row_id=2,
        purpose="exit",
        input_mint=record.mint,
        output_mint=_QUOTE_MINT,
        input_amount=20_000_000,
        output_amount=980_000_000,
        minimum_output_amount=970_000_000,
        quoted_at=2_015,
    )

    with pytest.raises(ValueError, match="ENTRY.*evidence|stale|missing"):
        resolve_fast_paper_shadow_cycle_input(
            manifest,
            record,
            FastCampaignDecisionPosition(kind="FLAT"),
            _read_policy(max_quote_age_ms=10),
            evaluated_at_unix_ms=2_020,
            max_exposure_fraction=0.5,
        )

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO token_mint_states
                (id, candidate_id, decimals, observed_at_unix_ms)
            VALUES (2, 7, 7, 1_995)
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="decimals.*conflict|conflicting.*decimals"):
        resolve_fast_paper_shadow_cycle_input(
            manifest,
            record,
            FastCampaignDecisionPosition(kind="FLAT"),
            _read_policy(max_quote_age_ms=100),
            evaluated_at_unix_ms=2_020,
            max_exposure_fraction=0.5,
        )


def test_persisted_quote_resolver_rejects_policy_or_candidate_drift(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    record = _record()

    with pytest.raises(ValueError, match="version.*route|route.*version"):
        resolve_fast_paper_shadow_cycle_input(
            manifest,
            record,
            FastCampaignDecisionPosition(kind="FLAT"),
            replace(_read_policy(), version="wrong-version"),
            evaluated_at_unix_ms=2_020,
            max_exposure_fraction=0.5,
        )

    with pytest.raises(ValueError, match="candidate.*mint|candidate"):
        resolve_fast_paper_shadow_cycle_input(
            manifest,
            replace(record, mint="different-mint"),
            FastCampaignDecisionPosition(kind="FLAT"),
            _read_policy(),
            evaluated_at_unix_ms=2_020,
            max_exposure_fraction=0.5,
        )


def test_persisted_quote_resolver_source_has_no_score_network_ledger_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime.persisted_quotes as resolver

    source = Path(resolver.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "PaperLedger",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "urllib",
        "socket",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source

    assert "mode=ro" in source
    assert "PRAGMA query_only = ON" in source
