from __future__ import annotations

import sqlite3

import pytest

from shreks_brain.observer_campaign.assembler import (
    ObserverPaperAssemblyError,
    assemble_observer_paper_cycle,
)

from test_observer_campaign_assembler import (
    AS_OF,
    MINT,
    QUOTE_ASSET,
    _bundle,
    _environment,
    _seed,
    _state,
)


DYNAMIC_MODE = "exact_market_ratio"


def test_v2_dynamic_valuation_uses_same_current_market_row_and_records_provenance(
    tmp_path,
) -> None:
    path = tmp_path / "observer.db"
    _seed(path)

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        quote_usd_valuation_mode=DYNAMIC_MODE,
        global_risk_halt=False,
    )

    assert len(cycle.quotes) == 1
    quote = cycle.quotes[0]
    assert quote.execution_price_usd == 40.0
    assert quote.quoted_notional_usd == 160.0
    assert audit.quote_usd_valuation_mode == DYNAMIC_MODE
    assert audit.quote_usd_valuation_market_row_id == 4
    assert audit.quote_usd_valuation_evidence_fingerprint is not None
    assert len(audit.quote_usd_valuation_evidence_fingerprint) == 64


def test_v2_dynamic_valuation_selects_manifest_quote_pair_over_newer_other_pair(
    tmp_path,
) -> None:
    path = tmp_path / "observer.db"
    _seed(path)
    connection = sqlite3.connect(path)
    connection.execute(
        """INSERT INTO market_snapshots (
               id, candidate_id, observed_at_unix_ms, source,
               source_observed_at_unix_ms, venue, pair_address,
               base_mint, quote_mint, price_native, price_usd,
               liquidity_usd, volume_m5_usd, volume_h1_usd, volume_h24_usd,
               buys_m5, sells_m5, buys_h1, sells_h1,
               pair_created_at_unix_ms
           ) VALUES (
               6, 1, 995000, 'dexscreener', 994999, 'pump_fun',
               'PairAssemblerWrongQuote', ?, 'WrongQuote', '0.001625', 0.26,
               100.0, 50.0, 500.0, 5000.0,
               45, 5, 360, 140, 50000
           )""",
        (MINT,),
    )
    connection.commit()
    connection.close()

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        quote_usd_valuation_mode=DYNAMIC_MODE,
        global_risk_halt=False,
    )

    assert len(cycle.quotes) == 1
    assert audit.quote_usd_valuation_market_row_id == 4


def test_v2_dynamic_valuation_fails_closed_without_fresh_manifest_quote_pair(
    tmp_path,
) -> None:
    path = tmp_path / "observer.db"
    _seed(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE market_snapshots SET quote_mint = 'WrongQuote'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(
        ObserverPaperAssemblyError,
        match="quote mint|market|snapshot",
    ):
        assemble_observer_paper_cycle(
            path,
            _state(),
            AS_OF,
            _bundle(),
            _environment(),
            quote_usd_valuation_mode=DYNAMIC_MODE,
            global_risk_halt=False,
        )


def test_v1_static_valuation_remains_legacy_and_has_no_dynamic_evidence(
    tmp_path,
) -> None:
    path = tmp_path / "observer.db"
    _seed(path)

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )

    quote = cycle.quotes[0]
    assert quote.execution_price_usd == 0.25
    assert quote.quoted_notional_usd == 1.0
    assert audit.quote_usd_valuation_mode == "manifest_fixed"
    assert audit.quote_usd_valuation_market_row_id is None
    assert audit.quote_usd_valuation_evidence_fingerprint is None
