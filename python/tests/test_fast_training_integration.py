from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess

from shreks_brain.research.counterfactual_parquet import write_counterfactual_parquet
from shreks_brain.research.counterfactuals import (
    EntryCounterfactualContext,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    read_fast_training_bundle,
    write_fast_training_bundle,
)


WSOL = "So11111111111111111111111111111111111111112"


def _counterfactual(decision_id: str, observed_at_unix_ms: int):
    return label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id=decision_id,
            mint="mint-fl8-training",
            quote_mint=WSOL,
            decision_observed_at_unix_ms=observed_at_unix_ms,
            base_quantity=2.0,
            horizon_ms=250,
            horizon_complete=True,
            buy_now=None,
            exit_at_horizon=None,
        )
    )


def test_rust_export_fl4_fl5_assemble_into_immutable_training_bundle(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = tmp_path / "rust-fixture"
    env = os.environ.copy()
    env["SHREKS_FL8_INTEGRATION_DIR"] = str(fixture_root)

    subprocess.run(
        [
            "cargo",
            "test",
            "-p",
            "shreks-storage",
            "--test",
            "fl8_training_fixture",
            "write_fl8_python_integration_fixture",
            "--",
            "--ignored",
            "--exact",
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )

    database = fixture_root / "shreks.db"
    features = fixture_root / "features.jsonl"
    assert database.is_file()
    assert features.is_file()

    counterfactual = tmp_path / "counterfactual.parquet"
    write_counterfactual_parquet(
        (
            _counterfactual("decision-a:0:h250:v1", 1_100),
            _counterfactual("decision-b:0:h250:v1", 1_600),
        ),
        counterfactual,
    )

    destination = tmp_path / "bundle"
    manifest = write_fast_training_bundle(
        feature_jsonl_path=features,
        sqlite_path=database,
        counterfactual_parquet_path=counterfactual,
        destination=destination,
        future_path_label_version=1,
    )
    loaded = read_fast_training_bundle(destination)

    assert loaded.manifest == manifest
    assert manifest.decision_count == 2
    assert manifest.future_path_label_row_count == 4
    assert manifest.counterfactual_row_count == 4
    assert len(manifest.bundle_fingerprint_sha256) == 64

    repeated_destination = tmp_path / "bundle-repeated"
    repeated_manifest = write_fast_training_bundle(
        feature_jsonl_path=features,
        sqlite_path=database,
        counterfactual_parquet_path=counterfactual,
        destination=repeated_destination,
        future_path_label_version=1,
    )
    assert repeated_manifest == manifest
    assert read_fast_training_bundle(repeated_destination).manifest == manifest

    first, second = loaded.features.records
    assert first.decision_signature == "decision-a"
    assert first.decision_sequence == 2
    assert first.snapshot_last_sequence == 2
    first_window_250 = next(value for value in first.windows if value.window_ms == 250)
    assert first_window_250.buy_count == 2
    assert first_window_250.sell_count == 0
    assert first.last_lifecycle_event is None

    assert second.decision_signature == "decision-b"
    assert second.decision_sequence == 4
    assert second.last_lifecycle_event is not None
    assert second.last_lifecycle_event.signature == "graduation-between-decisions"
    assert second.last_lifecycle_event.detected_at_unix_ms == 1_400

    labels = loaded.future_path_labels.labels
    assert {
        (label.decision_signature, label.horizon_ms, label.completeness)
        for label in labels
    } == {
        ("decision-a", 250, "complete"),
        ("decision-a", 500, "incomplete"),
        ("decision-b", 250, "complete"),
        ("decision-b", 500, "incomplete"),
    }
    incomplete = [label for label in labels if label.completeness == "incomplete"]
    assert len(incomplete) == 2
    assert all(label.endpoint_return_bps is None for label in incomplete)
    assert all(label.mfe_bps is None for label in incomplete)
    assert all(label.mae_bps is None for label in incomplete)

    statuses = {str(row["execution_status"]) for row in loaded.counterfactual_rows}
    assert statuses.intersection({"unknown", "not_executable"})

    feature_fingerprint = manifest.feature_logical_fingerprint_sha256
    future_path_fingerprint = manifest.future_path_logical_fingerprint_sha256
    bundle_fingerprint = manifest.bundle_fingerprint_sha256

    connection = sqlite3.connect(database)
    connection.execute(
        """UPDATE fast_future_path_labels
              SET best_cost_adjusted_return_bps = best_cost_adjusted_return_bps + 1.0
            WHERE decision_signature = 'decision-a'
              AND decision_ordinal = 0
              AND horizon_ms = 250
              AND label_version = 1"""
    )
    connection.commit()
    connection.close()

    changed_destination = tmp_path / "bundle-label-changed"
    changed_manifest = write_fast_training_bundle(
        feature_jsonl_path=features,
        sqlite_path=database,
        counterfactual_parquet_path=counterfactual,
        destination=changed_destination,
        future_path_label_version=1,
    )
    changed = read_fast_training_bundle(changed_destination)

    assert changed_manifest.feature_logical_fingerprint_sha256 == feature_fingerprint
    assert changed_manifest.future_path_logical_fingerprint_sha256 != future_path_fingerprint
    assert changed_manifest.bundle_fingerprint_sha256 != bundle_fingerprint
    assert changed.features.logical_fingerprint_sha256 == loaded.features.logical_fingerprint_sha256
