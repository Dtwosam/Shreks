from __future__ import annotations

import sqlite3

from shreks_brain.observer_campaign.coordinator import (
    ObserverPaperCampaignSelectionPolicy,
    assemble_observer_paper_campaign_cycle,
)

from test_observer_campaign_coordinator_assembly import (
    SECOND_MINT,
    _seed_two_candidates,
)
from test_observer_campaign_runner import (
    AS_OF,
    MINT,
    _bundle,
    _environment,
    _state,
)


def test_missing_current_reference_price_defers_quote_without_killing_campaign(tmp_path) -> None:
    database = tmp_path / "observer.db"
    _seed_two_candidates(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE market_snapshots
           SET price_usd = NULL
           WHERE candidate_id = 2
             AND observed_at_unix_ms = (
                 SELECT MAX(observed_at_unix_ms)
                 FROM market_snapshots
                 WHERE candidate_id = 2
                   AND observed_at_unix_ms <= ?
             )""",
        (AS_OF,),
    )
    connection.commit()
    connection.close()

    cycle, audit = assemble_observer_paper_campaign_cycle(
        database,
        _state(),
        AS_OF,
        _bundle(),
        _environment(),
        ObserverPaperCampaignSelectionPolicy(
            recent_lookback_ms=100_000,
            max_entry_candidates=2,
        ),
        global_risk_halt=False,
    )

    assert audit.selected_candidate_ids == (1, 2)
    assert audit.selected_mints == (MINT, SECOND_MINT)
    assert {item.mint for item in cycle.entry_candidates} == {MINT, SECOND_MINT}
    assert MINT in {quote.mint for quote in cycle.quotes}
    assert SECOND_MINT not in {quote.mint for quote in cycle.quotes}
