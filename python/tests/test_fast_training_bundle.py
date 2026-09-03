from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pyarrow.parquet as pq
import pytest

from shreks_brain.research.counterfactual_parquet import write_counterfactual_parquet
from shreks_brain.research.counterfactuals import (
    EntryCounterfactualContext,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    FAST_TRAINING_BUNDLE_SCHEMA_NAME,
    FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
    read_fast_training_bundle,
    write_fast_training_bundle,
)


WSOL = "So11111111111111111111111111111111111111112"
WINDOWS = (100, 250, 500, 1_000, 2_000, 5_000, 10_000)


def _window(window_ms: int) -> dict[str, object]:
    return {
        "window_ms": window_ms,
        "buy_count": 2,
        "sell_count": 0,
        "unique_buy_actors": 2,
        "unique_sell_actors": 0,
        "buy_arrival_rate_per_second": 2.0,
        "sell_arrival_rate_per_second": 0.0,
        "count_imbalance": 1.0,
        "buy_base_quantity": 4.0,
        "sell_base_quantity": 0.0,
        "buy_quote_quantity": 0.21,
        "sell_quote_quantity": 0.0,
        "net_quote_quantity": 0.21,
        "quote_flow_imbalance": 1.0,
        "quote_flow_velocity_per_second": 0.84,
        "quote_flow_acceleration_per_second2": 1.5,
        "local_high_price_quote": 0.055,
        "local_high_sequence": 2,
        "local_high_observed_at_unix_ms": 1_100,
        "local_low_price_quote": 0.05,
        "local_low_sequence": 1,
        "local_low_observed_at_unix_ms": 1_000,
        "post_high_low_price_quote": None,
        "post_high_low_sequence": None,
        "post_high_low_observed_at_unix_ms": None,
        "last_price_quote": 0.055,
        "drawdown_from_local_high": 0.0,
        "recovery_from_local_low": 0.1,
    }


def _write_features(path: Path) -> None:
    row = {
        "schema_name": "shreks.fast_lane_training_features",
        "schema_version": 1,
        "decision_signature": "decision",
        "decision_ordinal": 0,
        "decision_sequence": 2,
        "mint": "mint-fl8",
        "quote_mint": WSOL,
        "venue": "pump_fun_bonding_curve",
        "decision_observed_at_unix_ms": 1_100,
        "decision_provider": "helius",
        "decision_source_observed_at_unix_ms": 1_080,
        "decision_occurred_at_unix_ms": 1_000,
        "decision_slot": 77,
        "decision_event_kind": "buy",
        "decision_actor": "wallet-decision",
        "decision_executable_entry_price_quote": 0.055,
        "decision_entry_total_quote": 0.11275,
        "snapshot_as_of_unix_ms": 1_100,
        "snapshot_last_sequence": 2,
        "snapshot_last_price_quote": 0.055,
        "last_reserve_context": {
            "kind": "pump_curve",
            "virtual_base_reserve_raw": 20_002_000_000,
            "virtual_quote_reserve_raw": 10_110_000_000,
            "real_base_reserve_raw": 11_000_000_000,
            "real_quote_reserve_raw": 5_110_000_000,
            "base_decimals": 6,
            "quote_decimals": 9,
        },
        "last_lifecycle_event": None,
        "windows": [_window(value) for value in WINDOWS],
    }
    path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_labels_db(path: Path) -> None:
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
        CREATE TABLE pump_trade_evidence_conflicts (signature TEXT, ordinal INTEGER);
        CREATE TABLE pump_swap_trade_evidence_conflicts (signature TEXT, ordinal INTEGER);
        """
    )
    connection.executemany(
        "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (2, "decision", 0, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_100, 0.055),
            (3, "future", 0, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_300, 0.056),
        ],
    )
    connection.execute(
        "INSERT INTO fast_future_path_labels VALUES (" + ",".join("?" for _ in range(32)) + ")",
        (
            "decision", 0, 2, "mint-fl8", WSOL, "pump_fun_bonding_curve", 1_100,
            0.055, 0.11275, 2_000, 1, 250, 1, "complete", 1, 0,
            "future", 0, 1_300, 0.056, 181.8, 250.0, -30.0, 200, 50, 0,
            None, 8.0, 7.5, 0, 120.0, 80.0,
        ),
    )
    connection.commit()
    connection.close()


def _write_counterfactual(path: Path, *, decision_id: str = "decision:0:h250:v1", horizon_ms: int = 250) -> None:
    outcome_set = label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id=decision_id,
            mint="mint-fl8",
            quote_mint=WSOL,
            decision_observed_at_unix_ms=1_100,
            base_quantity=2.0,
            horizon_ms=horizon_ms,
            horizon_complete=True,
            buy_now=None,
            exit_at_horizon=None,
        )
    )
    write_counterfactual_parquet((outcome_set,), path)


def _sources(tmp_path: Path, *, decision_id: str = "decision:0:h250:v1", horizon_ms: int = 250) -> tuple[Path, Path, Path]:
    features = tmp_path / "features.jsonl"
    labels = tmp_path / "labels.db"
    counterfactual = tmp_path / "counterfactual.parquet"
    _write_features(features)
    _write_labels_db(labels)
    _write_counterfactual(counterfactual, decision_id=decision_id, horizon_ms=horizon_ms)
    return features, labels, counterfactual


def test_bundle_constants_and_round_trip_are_stable_and_immutable(tmp_path: Path) -> None:
    assert FAST_TRAINING_BUNDLE_SCHEMA_NAME == "shreks.fast_lane_training_bundle"
    assert FAST_TRAINING_BUNDLE_SCHEMA_VERSION == 1
    features, labels, counterfactual = _sources(tmp_path)
    destination = tmp_path / "bundle"

    manifest = write_fast_training_bundle(
        feature_jsonl_path=features,
        sqlite_path=labels,
        counterfactual_parquet_path=counterfactual,
        destination=destination,
        future_path_label_version=1,
    )
    assert manifest.decision_count == 1
    assert manifest.future_path_label_row_count == 1
    assert manifest.counterfactual_row_count == 2
    assert len(manifest.bundle_fingerprint_sha256) == 64
    assert {path.name for path in destination.iterdir()} == {
        "features.parquet",
        "future_path_labels.parquet",
        "counterfactual_action_labels.parquet",
        "manifest.json",
    }

    loaded = read_fast_training_bundle(destination)
    assert loaded.manifest == manifest
    assert len(loaded.features.records) == 1
    assert len(loaded.future_path_labels.labels) == 1
    assert len(loaded.counterfactual_rows) == 2

    with pytest.raises((FileExistsError, ValueError), match="exist|immutable|destination"):
        write_fast_training_bundle(
            feature_jsonl_path=features,
            sqlite_path=labels,
            counterfactual_parquet_path=counterfactual,
            destination=destination,
            future_path_label_version=1,
        )


def test_feature_parquet_contains_no_future_path_target_columns(tmp_path: Path) -> None:
    features, labels, counterfactual = _sources(tmp_path)
    destination = tmp_path / "bundle"
    write_fast_training_bundle(
        feature_jsonl_path=features,
        sqlite_path=labels,
        counterfactual_parquet_path=counterfactual,
        destination=destination,
        future_path_label_version=1,
    )
    columns = set(pq.read_schema(destination / "features.parquet").names)
    assert "endpoint_return_bps" not in columns
    assert "mfe_bps" not in columns
    assert "mae_bps" not in columns
    assert "best_cost_adjusted_return_bps" not in columns


def test_counterfactual_decision_identity_or_horizon_mismatch_fails_atomically(tmp_path: Path) -> None:
    features, labels, counterfactual = _sources(tmp_path, decision_id="wrong:0:h250:v1")
    destination = tmp_path / "wrong-id-bundle"
    with pytest.raises(ValueError, match="counterfactual|decision"):
        write_fast_training_bundle(
            feature_jsonl_path=features,
            sqlite_path=labels,
            counterfactual_parquet_path=counterfactual,
            destination=destination,
            future_path_label_version=1,
        )
    assert not destination.exists()

    other = tmp_path / "other"
    other.mkdir()
    features, labels, counterfactual = _sources(other, decision_id="decision:0:h500:v1", horizon_ms=500)
    destination = tmp_path / "wrong-horizon-bundle"
    with pytest.raises(ValueError, match="counterfactual|horizon|decision"):
        write_fast_training_bundle(
            feature_jsonl_path=features,
            sqlite_path=labels,
            counterfactual_parquet_path=counterfactual,
            destination=destination,
            future_path_label_version=1,
        )
    assert not destination.exists()


def test_feature_to_fl4_join_mismatch_fails_atomically(tmp_path: Path) -> None:
    features, labels, counterfactual = _sources(tmp_path)
    row = json.loads(features.read_text(encoding="utf-8"))
    row["decision_sequence"] = 99
    row["snapshot_last_sequence"] = 99
    for window in row["windows"]:
        if window["local_high_sequence"] == 2:
            window["local_high_sequence"] = 99
    features.write_text(json.dumps(row) + "\n", encoding="utf-8")

    destination = tmp_path / "join-mismatch"
    with pytest.raises(ValueError, match="feature|FL4|decision|identity"):
        write_fast_training_bundle(
            feature_jsonl_path=features,
            sqlite_path=labels,
            counterfactual_parquet_path=counterfactual,
            destination=destination,
            future_path_label_version=1,
        )
    assert not destination.exists()
