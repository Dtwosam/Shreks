from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shreks_brain.research.fast_training_targets import (
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
    load_future_path_training_labels_from_sqlite,
)


WSOL = "So11111111111111111111111111111111111111112"


def _db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE fast_events (
            sequence INTEGER NOT NULL,
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            mint TEXT NOT NULL,
            quote_mint TEXT NOT NULL,
            venue TEXT NOT NULL,
            observed_at_unix_ms INTEGER NOT NULL,
            price_quote REAL NOT NULL,
            PRIMARY KEY (signature, ordinal)
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
            endpoint_cost_adjusted_return_bps REAL
        );
        CREATE TABLE pump_trade_evidence_conflicts (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        CREATE TABLE pump_swap_trade_evidence_conflicts (
            signature TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        );
        """
    )
    return connection


def _seed(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (2, "decision", 0, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_100, 0.055),
            (3, "future", 0, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_300, 0.056),
        ],
    )
    connection.execute(
        """INSERT INTO fast_future_path_labels VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )""",
        (
            "decision", 0, 2, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_100,
            0.055, 0.11275, 2_000, 1, 250, 1, "complete", 1, 0,
            "future", 0, 1_300, 0.056, 181.8, 250.0, -30.0, 200, 50, 0,
            None, 8.0, 7.5, 0, 120.0, 80.0,
        ),
    )
    connection.execute(
        """INSERT INTO fast_future_path_labels VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )""",
        (
            "decision", 0, 2, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_100,
            0.055, 0.11275, 1_200, 0, 500, 1, "incomplete", 0, 0,
            None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None,
        ),
    )
    connection.commit()


def test_target_schema_constants_and_complete_incomplete_semantics(tmp_path: Path) -> None:
    assert FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME == "shreks.fast_future_path_training_labels"
    assert FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION == 1

    path = tmp_path / "labels.db"
    connection = _db(path)
    _seed(connection)
    connection.close()

    dataset = load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)
    assert len(dataset.labels) == 2
    complete, incomplete = dataset.labels
    assert complete.horizon_ms == 250
    assert complete.completeness == "complete"
    assert complete.endpoint_return_bps == pytest.approx(181.8)
    assert complete.best_cost_adjusted_return_bps == pytest.approx(120.0)
    assert incomplete.horizon_ms == 500
    assert incomplete.completeness == "incomplete"
    assert incomplete.endpoint_return_bps is None
    assert incomplete.mfe_bps is None
    assert incomplete.route_unavailability_observed is None
    assert len(dataset.logical_fingerprint_sha256) == 64


def test_loader_is_deterministic_and_orders_by_decision_then_horizon(tmp_path: Path) -> None:
    path = tmp_path / "labels.db"
    connection = _db(path)
    _seed(connection)
    connection.close()
    first = load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)
    second = load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)
    assert first == second
    assert [label.horizon_ms for label in first.labels] == [250, 500]


def test_canonical_decision_or_endpoint_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.db"
    connection = _db(path)
    _seed(connection)
    connection.execute(
        "UPDATE fast_future_path_labels SET decision_sequence = 99 WHERE horizon_ms = 250"
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="canonical decision|decision"):
        load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)

    path = tmp_path / "endpoint-mismatch.db"
    connection = _db(path)
    _seed(connection)
    connection.execute(
        "UPDATE fast_future_path_labels SET endpoint_price_quote = 9.99 WHERE horizon_ms = 250"
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="canonical endpoint|endpoint"):
        load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)


def test_conflict_quarantine_rejects_decision_and_endpoint_sources(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision-conflict.db"
    connection = _db(decision_path)
    _seed(connection)
    connection.execute("INSERT INTO pump_trade_evidence_conflicts VALUES ('decision', 0)")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="conflict"):
        load_future_path_training_labels_from_sqlite(decision_path, future_path_label_version=1)

    endpoint_path = tmp_path / "endpoint-conflict.db"
    connection = _db(endpoint_path)
    _seed(connection)
    connection.execute("INSERT INTO pump_trade_evidence_conflicts VALUES ('future', 0)")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="conflict"):
        load_future_path_training_labels_from_sqlite(endpoint_path, future_path_label_version=1)


def test_duplicate_decision_horizon_and_wrong_label_version_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.db"
    connection = _db(path)
    _seed(connection)
    row = connection.execute(
        "SELECT * FROM fast_future_path_labels WHERE horizon_ms = 250"
    ).fetchone()
    assert row is not None
    connection.execute(
        "INSERT INTO fast_future_path_labels VALUES (" + ",".join("?" for _ in row) + ")",
        row,
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="duplicate"):
        load_future_path_training_labels_from_sqlite(path, future_path_label_version=1)

    with pytest.raises(ValueError, match="label version|rows|empty"):
        load_future_path_training_labels_from_sqlite(path, future_path_label_version=2)
