from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.assembler import assemble_observer_paper_cycle

from test_observer_campaign_assembler import (
    AS_OF,
    _bundle,
    _environment,
    _seed,
    _state,
)


def test_persisted_quotes_without_token_decimals_defer_without_crashing(tmp_path):
    path = tmp_path / "observer.db"
    _seed(path)

    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM token_mint_states")
    connection.commit()
    connection.close()

    cycle, audit = assemble_observer_paper_cycle(
        path,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        global_risk_halt=False,
    )

    # Raw Jupiter evidence is still visible for audit/safety provenance, but
    # without token decimals it cannot be converted into an economic PaperQuote.
    # The candidate must therefore remain fail-closed and unfillable rather than
    # terminating the whole PAPER campaign.
    assert audit.entry_quote_observed_at_unix_ms == 988_000
    assert audit.exit_quote_observed_at_unix_ms == 989_000
    assert audit.entry_quote_evidence_fingerprint is not None
    assert audit.exit_quote_evidence_fingerprint is not None
    assert cycle.quotes == ()

    candidate = cycle.entry_candidates[0]
    assert candidate.risk_context.expected_price_impact_pct is None
    assert candidate.risk_context.price_impact_notional_usd is None
