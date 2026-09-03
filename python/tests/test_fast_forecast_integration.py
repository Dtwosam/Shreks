from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from fast_forecast_fixtures import WSOL, feature_record
from shreks_brain.fast_learning.codec import (
    read_fast_forecast_artifact,
    write_fast_forecast_artifact,
)
from shreks_brain.fast_learning.inference import predict_fast_forecast
from shreks_brain.fast_learning.models import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_learning.trainer import train_fast_forecast_baseline
from shreks_brain.research.counterfactual_parquet import write_counterfactual_parquet
from shreks_brain.research.counterfactuals import (
    EntryCounterfactualContext,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    read_fast_training_bundle,
    write_fast_training_bundle,
)


MINT = "mint-fl8-2"


def _request(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
    *,
    model_version: str,
) -> FastForecastTrainingRequest:
    if family is FastForecastModelFamily.RIDGE_REGRESSION:
        policy = FastForecastTrainingPolicy(version="ridge-v1", ridge_alpha=1.0)
    elif family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        policy = FastForecastTrainingPolicy(
            version="logit-v1",
            logistic_regularization_c=1.0,
            logistic_max_iterations=2_000,
            logistic_tolerance=1e-10,
            logistic_balanced_class_weight=False,
        )
    else:
        policy = FastForecastTrainingPolicy(version="naive-v1")
    return FastForecastTrainingRequest(
        model_version=model_version,
        model_family=family,
        target=target,
        horizon_ms=250,
        training_policy=policy,
    )


def _write_fl81_bundle(root: Path, *, target_shift: float = 0.0) -> Path:
    root.mkdir()
    features_jsonl = root / "features.jsonl"
    database = root / "labels.db"
    counterfactual = root / "counterfactual.parquet"
    destination = root / "bundle"

    records = tuple(feature_record(index, float(index)) for index in range(6))
    with features_jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(asdict(record), separators=(",", ":"), ensure_ascii=False)
                + "\n"
            )

    connection = sqlite3.connect(database)
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

    for index, record in enumerate(records):
        connection.execute(
            "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.decision_sequence,
                record.decision_signature,
                record.decision_ordinal,
                record.mint,
                record.quote_mint,
                record.venue,
                record.decision_observed_at_unix_ms,
                record.decision_executable_entry_price_quote,
            ),
        )
        base_return = (-120.0 + index * 55.0) + target_shift
        for horizon_ms in (250, 500):
            if horizon_ms == 500 and index == 4:
                row = (
                    record.decision_signature,
                    0,
                    record.decision_sequence,
                    MINT,
                    WSOL,
                    "pump_fun_bonding_curve",
                    record.decision_observed_at_unix_ms,
                    record.decision_executable_entry_price_quote,
                    record.decision_entry_total_quote,
                    record.decision_observed_at_unix_ms + horizon_ms - 1,
                    0,
                    horizon_ms,
                    1,
                    "incomplete",
                    0,
                    0,
                    *([None] * 16),
                )
            elif horizon_ms == 500 and index == 5:
                row = (
                    record.decision_signature,
                    0,
                    record.decision_sequence,
                    MINT,
                    WSOL,
                    "pump_fun_bonding_curve",
                    record.decision_observed_at_unix_ms,
                    record.decision_executable_entry_price_quote,
                    record.decision_entry_total_quote,
                    record.decision_observed_at_unix_ms + horizon_ms + 100,
                    1,
                    horizon_ms,
                    1,
                    "complete",
                    0,
                    1,
                    *([None] * 16),
                )
            else:
                target = base_return if horizon_ms == 250 else base_return * 1.5
                endpoint_signature = f"endpoint-{index}-{horizon_ms}"
                endpoint_time = record.decision_observed_at_unix_ms + min(
                    200, horizon_ms - 50
                )
                endpoint_price = record.decision_executable_entry_price_quote * (
                    1.0 + target / 10_000.0
                )
                endpoint_sequence = 100 + index * 2 + (0 if horizon_ms == 250 else 1)
                connection.execute(
                    "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        endpoint_sequence,
                        endpoint_signature,
                        0,
                        MINT,
                        WSOL,
                        "pump_fun_bonding_curve",
                        endpoint_time,
                        endpoint_price,
                    ),
                )
                reversal = index % 2 == 1
                row = (
                    record.decision_signature,
                    0,
                    record.decision_sequence,
                    MINT,
                    WSOL,
                    "pump_fun_bonding_curve",
                    record.decision_observed_at_unix_ms,
                    record.decision_executable_entry_price_quote,
                    record.decision_entry_total_quote,
                    record.decision_observed_at_unix_ms + horizon_ms + 100,
                    1,
                    horizon_ms,
                    1,
                    "complete",
                    1,
                    0,
                    endpoint_signature,
                    0,
                    endpoint_time,
                    endpoint_price,
                    target,
                    target + 25.0,
                    target - 50.0,
                    100,
                    50,
                    1 if reversal else 0,
                    150 if reversal else None,
                    8.0,
                    7.5,
                    0,
                    target - 10.0,
                    target - 20.0,
                )
            assert len(row) == 32
            connection.execute(
                "INSERT INTO fast_future_path_labels VALUES ("
                + ",".join("?" for _ in row)
                + ")",
                row,
            )
    connection.commit()
    connection.close()

    first = records[0]
    outcome = label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id=f"{first.decision_signature}:0:h250:v1",
            mint=MINT,
            quote_mint=WSOL,
            decision_observed_at_unix_ms=first.decision_observed_at_unix_ms,
            base_quantity=2.0,
            horizon_ms=250,
            horizon_complete=True,
            buy_now=None,
            exit_at_horizon=None,
        )
    )
    write_counterfactual_parquet((outcome,), counterfactual)
    write_fast_training_bundle(
        feature_jsonl_path=features_jsonl,
        sqlite_path=database,
        counterfactual_parquet_path=counterfactual,
        destination=destination,
        future_path_label_version=1,
    )
    return destination


def test_fl81_disk_bundle_trains_round_trips_and_predicts_all_fl82_families(
    tmp_path: Path,
) -> None:
    bundle_path = _write_fl81_bundle(tmp_path / "source")
    bundle = read_fast_training_bundle(bundle_path)
    requests = (
        _request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
            model_version="mean-h250-v1",
        ),
        _request(
            FastForecastModelFamily.RIDGE_REGRESSION,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
            model_version="ridge-h250-v1",
        ),
        _request(
            FastForecastModelFamily.PRIOR_CLASSIFIER,
            FastForecastTarget.REVERSAL_OCCURRED,
            model_version="prior-h250-v1",
        ),
        _request(
            FastForecastModelFamily.LOGISTIC_REGRESSION,
            FastForecastTarget.REVERSAL_OCCURRED,
            model_version="logistic-h250-v1",
        ),
    )

    for request in requests:
        artifact = train_fast_forecast_baseline(bundle, request)
        artifact_path = tmp_path / f"{artifact.model_version}.json"
        write_fast_forecast_artifact(artifact, artifact_path)
        loaded = read_fast_forecast_artifact(artifact_path)
        assert loaded == artifact
        prediction = predict_fast_forecast(loaded, bundle.features.records[-1])
        assert prediction.model_version == artifact.model_version
        assert prediction.horizon_ms == 250


def test_disk_bundle_target_only_change_preserves_features_but_changes_model_fingerprints(
    tmp_path: Path,
) -> None:
    original = read_fast_training_bundle(
        _write_fl81_bundle(tmp_path / "original", target_shift=0.0)
    )
    changed = read_fast_training_bundle(
        _write_fl81_bundle(tmp_path / "changed", target_shift=7.0)
    )
    assert (
        original.manifest.feature_logical_fingerprint_sha256
        == changed.manifest.feature_logical_fingerprint_sha256
    )
    request = _request(
        FastForecastModelFamily.RIDGE_REGRESSION,
        FastForecastTarget.ENDPOINT_RETURN_BPS,
        model_version="ridge-fingerprint-v1",
    )
    original_artifact = train_fast_forecast_baseline(original, request)
    changed_artifact = train_fast_forecast_baseline(changed, request)
    assert (
        original_artifact.training_data_fingerprint_sha256
        != changed_artifact.training_data_fingerprint_sha256
    )
    assert (
        original_artifact.artifact_fingerprint_sha256
        != changed_artifact.artifact_fingerprint_sha256
    )
