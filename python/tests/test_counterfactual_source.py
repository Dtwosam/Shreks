from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

import pytest

import shreks_brain.research.counterfactual_source as counterfactual_source_module
from shreks_brain.research.counterfactual_source import (
    CounterfactualSourceError,
    load_entry_counterfactual_from_sqlite,
    load_entry_counterfactual_provenance_batch_from_sqlite,
    load_open_position_counterfactual_from_sqlite,
)
from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    ExecutionStatus,
    label_entry_counterfactuals,
    label_open_position_counterfactuals,
)


def _create_source_db(path: Path, *, completeness: str = "complete") -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE fast_events (
            sequence INTEGER PRIMARY KEY,
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            provider TEXT NOT NULL,
            slot TEXT NOT NULL,
            source_observed_at_unix_ms INTEGER NOT NULL,
            occurred_at_unix_ms INTEGER NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            mint TEXT NOT NULL,
            quote_mint TEXT NOT NULL,
            venue TEXT NOT NULL,
            kind TEXT NOT NULL,
            actor TEXT,
            base_quantity REAL NOT NULL,
            quote_quantity REAL NOT NULL,
            price_quote REAL NOT NULL,
            base_decimals INTEGER NOT NULL,
            quote_decimals INTEGER NOT NULL,
            UNIQUE (signature, ordinal)
        );

        CREATE TABLE fast_future_path_labels (
            decision_signature TEXT NOT NULL,
            decision_ordinal INTEGER NOT NULL,
            decision_sequence INTEGER NOT NULL,
            decision_mint TEXT NOT NULL,
            decision_quote_mint TEXT NOT NULL,
            decision_venue TEXT NOT NULL,
            decision_observed_at_unix_ms INTEGER NOT NULL,
            decision_entry_price_quote REAL NOT NULL,
            decision_entry_total_quote REAL,
            coverage_complete_through_unix_ms INTEGER NOT NULL,
            coverage_contiguous INTEGER NOT NULL,
            horizon_ms INTEGER NOT NULL,
            label_version INTEGER NOT NULL,
            completeness TEXT NOT NULL,
            event_count INTEGER NOT NULL,
            no_trade_events INTEGER NOT NULL,
            endpoint_signature TEXT,
            endpoint_ordinal INTEGER,
            endpoint_observed_at_unix_ms INTEGER,
            endpoint_price_quote REAL,
            endpoint_return_bps REAL,
            mfe_bps REAL,
            mae_bps REAL,
            time_to_peak_ms INTEGER,
            time_to_trough_ms INTEGER,
            reversal_occurred INTEGER,
            first_reversal_after_ms INTEGER,
            min_exit_capacity_base REAL,
            endpoint_exit_capacity_base REAL,
            route_unavailability_observed INTEGER,
            best_cost_adjusted_return_bps REAL,
            endpoint_cost_adjusted_return_bps REAL,
            PRIMARY KEY (decision_signature, decision_ordinal, horizon_ms, label_version)
        );

        CREATE TABLE pump_trade_evidence_conflicts (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        CREATE TABLE pump_swap_trade_evidence_conflicts (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        CREATE TABLE pump_trade_execution_economics (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        CREATE TABLE pump_swap_execution_economics (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO fast_events VALUES (
            10, 'decision-sig', 1, 'solana_public', '100', 1000, 900, 1000,
            'mint-1', 'quote-1', 'pump_fun_bonding_curve', 'buy', 'actor-1',
            4.0, 0.20, 0.05, 6, 9
        )
        """
    )
    connection.execute(
        """
        INSERT INTO fast_events VALUES (
            11, 'endpoint-sig', 2, 'solana_public', '101', 1800, 1700, 1800,
            'mint-1', 'quote-1', 'pump_fun_bonding_curve', 'sell', 'actor-2',
            4.0, 0.24, 0.06, 6, 9
        )
        """
    )
    complete_through = 2000 if completeness == "complete" else 1500
    coverage_contiguous = 1
    event_count = 1 if completeness == "complete" else 0
    endpoint = (
        ("endpoint-sig", 2, 1800, 0.06, 2000.0, 4.0, 4.0, 1000.0)
        if completeness == "complete"
        else (None, None, None, None, None, None, None, None)
    )
    connection.execute(
        """
        INSERT INTO fast_future_path_labels (
            decision_signature, decision_ordinal, decision_sequence,
            decision_mint, decision_quote_mint, decision_venue,
            decision_observed_at_unix_ms, decision_entry_price_quote,
            decision_entry_total_quote, coverage_complete_through_unix_ms,
            coverage_contiguous, horizon_ms, label_version, completeness,
            event_count, no_trade_events, endpoint_signature, endpoint_ordinal,
            endpoint_observed_at_unix_ms, endpoint_price_quote,
            endpoint_return_bps, min_exit_capacity_base,
            endpoint_exit_capacity_base, endpoint_cost_adjusted_return_bps
        ) VALUES (
            'decision-sig', 1, 10, 'mint-1', 'quote-1', 'pump_fun_bonding_curve',
            1000, 0.05, 0.21, ?, ?, 1000, 1, ?, ?, 0,
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            complete_through,
            coverage_contiguous,
            completeness,
            event_count,
            *endpoint,
        ),
    )
    # Source-retained FL3 economics being present is intentionally insufficient:
    # the historical DB still does not prove an exact requested-quantity fill.
    connection.execute(
        "INSERT INTO pump_trade_execution_economics VALUES ('decision-sig', 1)"
    )
    connection.execute(
        "INSERT INTO pump_trade_execution_economics VALUES ('endpoint-sig', 2)"
    )
    connection.commit()
    connection.close()


def test_entry_loader_preserves_canonical_identity_version_and_horizon_without_fabricating_fills(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)

    loaded = load_entry_counterfactual_from_sqlite(
        db_path,
        decision_signature="decision-sig",
        decision_ordinal=1,
        horizon_ms=1000,
        label_version=1,
        base_quantity=2.0,
    )

    assert loaded.provenance.decision_signature == "decision-sig"
    assert loaded.provenance.decision_ordinal == 1
    assert loaded.provenance.decision_sequence == 10
    assert loaded.provenance.venue == "pump_fun_bonding_curve"
    assert loaded.provenance.future_path_label_version == 1
    assert loaded.provenance.endpoint_signature == "endpoint-sig"
    assert loaded.context.decision_id == "decision-sig:1:h1000:v1"
    assert loaded.context.mint == "mint-1"
    assert loaded.context.quote_mint == "quote-1"
    assert loaded.context.horizon_complete is True
    assert loaded.context.buy_now is None
    assert loaded.context.exit_at_horizon is None

    outcomes = label_entry_counterfactuals(loaded.context)
    assert outcomes[0].action is CounterfactualAction.BUY_NOW
    assert outcomes[0].execution_status is ExecutionStatus.UNKNOWN
    assert outcomes[0].net_pnl_quote is None
    assert outcomes[1].action is CounterfactualAction.SKIP
    assert outcomes[1].execution_status is ExecutionStatus.EXECUTABLE


def test_current_fl3_sidecars_and_fl4_cost_annotations_are_not_backfilled_into_execution_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)

    loaded = load_entry_counterfactual_from_sqlite(
        db_path,
        decision_signature="decision-sig",
        decision_ordinal=1,
        horizon_ms=1000,
        label_version=1,
        base_quantity=4.0,
    )

    assert loaded.provenance.decision_entry_total_quote == pytest.approx(0.21)
    assert loaded.provenance.endpoint_exit_capacity_base == pytest.approx(4.0)
    assert loaded.provenance.endpoint_cost_adjusted_return_bps == pytest.approx(1000.0)
    assert loaded.provenance.decision_execution_economics_present is True
    assert loaded.provenance.endpoint_execution_economics_present is True
    assert loaded.context.buy_now is None
    assert loaded.context.exit_at_horizon is None


def test_incomplete_fl4_horizon_cannot_become_hold_utility(tmp_path: Path) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path, completeness="incomplete")

    loaded = load_open_position_counterfactual_from_sqlite(
        db_path,
        decision_signature="decision-sig",
        decision_ordinal=1,
        horizon_ms=1000,
        label_version=1,
        position_base_quantity=4.0,
        position_cost_basis_quote=0.20,
    )

    assert loaded.context.horizon_complete is False
    outcomes = label_open_position_counterfactuals(loaded.context)
    assert outcomes[0].action is CounterfactualAction.HOLD
    assert outcomes[0].execution_status is ExecutionStatus.UNKNOWN
    assert outcomes[0].net_pnl_quote is None


def test_mismatched_duplicate_fl4_identity_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE fast_future_path_labels SET decision_mint = 'wrong-mint'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(CounterfactualSourceError, match="canonical decision"):
        load_entry_counterfactual_from_sqlite(
            db_path,
            decision_signature="decision-sig",
            decision_ordinal=1,
            horizon_ms=1000,
            label_version=1,
            base_quantity=4.0,
        )


def test_conflict_quarantined_source_event_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO pump_trade_evidence_conflicts VALUES ('decision-sig', 1)"
    )
    connection.commit()
    connection.close()

    with pytest.raises(CounterfactualSourceError, match="conflict-quarantined"):
        load_entry_counterfactual_from_sqlite(
            db_path,
            decision_signature="decision-sig",
            decision_ordinal=1,
            horizon_ms=1000,
            label_version=1,
            base_quantity=4.0,
        )


def test_entry_provenance_batch_reuses_one_read_only_connection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)
    baseline = load_entry_counterfactual_from_sqlite(
        db_path,
        decision_signature="decision-sig",
        decision_ordinal=1,
        horizon_ms=1000,
        label_version=1,
        base_quantity=2.0,
    ).provenance

    open_count = 0
    original_open = counterfactual_source_module._open_read_only

    def counted_open(path: Path):
        nonlocal open_count
        open_count += 1
        return original_open(path)

    seen_connections: list[int] = []

    def fake_load_provenance(
        db_path,
        *,
        decision_signature,
        decision_ordinal,
        horizon_ms,
        label_version,
        connection=None,
    ):
        assert connection is not None
        seen_connections.append(id(connection))
        return baseline

    monkeypatch.setattr(
        counterfactual_source_module,
        "_open_read_only",
        counted_open,
    )
    monkeypatch.setattr(
        counterfactual_source_module,
        "_load_provenance",
        fake_load_provenance,
    )

    identities = (
        ("decision-sig", 1, 1000, 1),
        ("other-sig", 2, 500, 1),
    )
    loaded = load_entry_counterfactual_provenance_batch_from_sqlite(
        db_path,
        lookup_identities=identities,
    )

    assert tuple(loaded) == identities
    assert open_count == 1
    assert len(seen_connections) == 2
    assert len(set(seen_connections)) == 1


def test_entry_provenance_batch_rejects_duplicate_lookup_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)
    identity = ("decision-sig", 1, 1000, 1)

    with pytest.raises(CounterfactualSourceError, match="duplicate"):
        load_entry_counterfactual_provenance_batch_from_sqlite(
            db_path,
            lookup_identities=(identity, identity),
        )


def test_source_adapter_is_byte_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "source.sqlite"
    _create_source_db(db_path)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    load_entry_counterfactual_from_sqlite(
        db_path,
        decision_signature="decision-sig",
        decision_ordinal=1,
        horizon_ms=1000,
        label_version=1,
        base_quantity=4.0,
    )

    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert after == before


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.sqlite"

    with pytest.raises(CounterfactualSourceError, match="read-only"):
        load_entry_counterfactual_from_sqlite(
            db_path,
            decision_signature="decision-sig",
            decision_ordinal=1,
            horizon_ms=1000,
            label_version=1,
            base_quantity=4.0,
        )

    assert not db_path.exists()
