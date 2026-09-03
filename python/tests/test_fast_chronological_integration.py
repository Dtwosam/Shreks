from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3

from fast_forecast_fixtures import WSOL, feature_record
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
    run_fast_chronological_validation,
)
from shreks_brain.research.counterfactual_parquet import write_counterfactual_parquet
from shreks_brain.research.counterfactuals import (
    EntryCounterfactualContext,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    read_fast_training_bundle,
    write_fast_training_bundle,
)


HORIZON_MS = 250
TRAIN_START = 1_000
TRAIN_END = 1_800
VALIDATION_START = 2_000
VALIDATION_END = 2_500
TEST_START = 3_000
TEST_END = 3_300
_TIMES = (
    1_000,
    1_100,
    1_200,
    1_300,
    1_400,
    1_500,
    1_600,
    1_700,
    2_000,
    2_100,
    2_200,
    2_300,
    2_400,
    3_000,
    3_100,
    3_200,
)


def _request(
    family: FastForecastModelFamily,
    target: FastForecastTarget,
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
        model_version=f"fl8-3-disk-{family.value.lower()}-{target.value}",
        model_family=family,
        target=target,
        horizon_ms=HORIZON_MS,
        training_policy=policy,
    )


def _policy() -> FastChronologicalValidationPolicy:
    return FastChronologicalValidationPolicy(
        version="fl8-3-disk-v1",
        folds=(
            FastChronologicalFold(
                name="disk-fold",
                training_started_at_unix_ms=TRAIN_START,
                training_ended_at_unix_ms=TRAIN_END,
                validation_started_at_unix_ms=VALIDATION_START,
                validation_ended_at_unix_ms=VALIDATION_END,
                test_started_at_unix_ms=TEST_START,
                test_ended_at_unix_ms=TEST_END,
            ),
        ),
    )


def _write_fl81_bundle(root: Path, *, evaluation_target_shift: float = 0.0) -> Path:
    root.mkdir()
    features_jsonl = root / "features.jsonl"
    database = root / "labels.db"
    counterfactual = root / "counterfactual.parquet"
    destination = root / "bundle"

    records = []
    for index, observed in enumerate(_TIMES):
        record = feature_record(
            index,
            float(index),
            signature=f"fl8-3-disk-decision-{index}",
            observed_at_unix_ms=observed,
            actor=f"fl8-3-disk-wallet-{index}",
        )
        records.append(replace(record, mint=f"fl8-3-disk-mint-{index}"))

    # Three deliberate cross-partition groups. Each affected row must be
    # quarantined from its fold, while enough clean data remains to fit all
    # four FL8.2 baseline families.
    records[8] = replace(records[8], mint=records[0].mint)
    records[13] = replace(records[13], decision_actor=records[1].decision_actor)
    records[9] = replace(
        records[9],
        decision_signature=records[2].decision_signature,
        decision_ordinal=1,
    )
    record_tuple = tuple(records)

    with features_jsonl.open("w", encoding="utf-8") as handle:
        for record in record_tuple:
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

    for index, record in enumerate(record_tuple):
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

        is_evaluation = record.decision_observed_at_unix_ms >= VALIDATION_START
        target = -100.0 + index * 20.0 + (
            evaluation_target_shift if is_evaluation else 0.0
        )

        if index == 7:
            row = (
                record.decision_signature,
                record.decision_ordinal,
                record.decision_sequence,
                record.mint,
                WSOL,
                "pump_fun_bonding_curve",
                record.decision_observed_at_unix_ms,
                record.decision_executable_entry_price_quote,
                record.decision_entry_total_quote,
                record.decision_observed_at_unix_ms + HORIZON_MS - 1,
                0,
                HORIZON_MS,
                1,
                "incomplete",
                0,
                0,
                *([None] * 16),
            )
        elif index == 15:
            # Complete no-trade evaluation label: valid FL4 evidence with null
            # path metrics. FL8.3 prediction must not inspect it.
            row = (
                record.decision_signature,
                record.decision_ordinal,
                record.decision_sequence,
                record.mint,
                WSOL,
                "pump_fun_bonding_curve",
                record.decision_observed_at_unix_ms,
                record.decision_executable_entry_price_quote,
                record.decision_entry_total_quote,
                record.decision_observed_at_unix_ms + HORIZON_MS + 100,
                1,
                HORIZON_MS,
                1,
                "complete",
                0,
                1,
                *([None] * 16),
            )
        else:
            endpoint_signature = f"fl8-3-disk-endpoint-{index}"
            endpoint_time = record.decision_observed_at_unix_ms + 200
            endpoint_price = record.decision_executable_entry_price_quote * (
                1.0 + target / 10_000.0
            )
            endpoint_sequence = 100 + index
            connection.execute(
                "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    endpoint_sequence,
                    endpoint_signature,
                    0,
                    record.mint,
                    WSOL,
                    "pump_fun_bonding_curve",
                    endpoint_time,
                    endpoint_price,
                ),
            )
            reversal = index % 2 == 1
            row = (
                record.decision_signature,
                record.decision_ordinal,
                record.decision_sequence,
                record.mint,
                WSOL,
                "pump_fun_bonding_curve",
                record.decision_observed_at_unix_ms,
                record.decision_executable_entry_price_quote,
                record.decision_entry_total_quote,
                record.decision_observed_at_unix_ms + HORIZON_MS + 100,
                1,
                HORIZON_MS,
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

    first = record_tuple[0]
    outcome = label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id=f"{first.decision_signature}:{first.decision_ordinal}:h250:v1",
            mint=first.mint,
            quote_mint=WSOL,
            decision_observed_at_unix_ms=first.decision_observed_at_unix_ms,
            base_quantity=2.0,
            horizon_ms=HORIZON_MS,
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


def test_real_fl81_bundle_runs_all_four_chronological_baselines(tmp_path: Path) -> None:
    bundle = read_fast_training_bundle(_write_fl81_bundle(tmp_path / "source"))
    requests = (
        _request(
            FastForecastModelFamily.MEAN_REGRESSOR,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        _request(
            FastForecastModelFamily.RIDGE_REGRESSION,
            FastForecastTarget.ENDPOINT_RETURN_BPS,
        ),
        _request(
            FastForecastModelFamily.PRIOR_CLASSIFIER,
            FastForecastTarget.REVERSAL_OCCURRED,
        ),
        _request(
            FastForecastModelFamily.LOGISTIC_REGRESSION,
            FastForecastTarget.REVERSAL_OCCURRED,
        ),
    )

    for request in requests:
        run = run_fast_chronological_validation(bundle, request, _policy())
        result = run.fold_results[0]
        assert result.quarantine.shared_mint_count == 1
        assert result.quarantine.shared_actor_count == 1
        assert result.quarantine.shared_signature_count == 1
        assert result.training_raw_row_count == 8
        assert result.training_row_count == 5
        assert result.model.training_row_count == 4
        assert result.training_target_unavailable_at_split_count == 1
        assert result.validation_raw_row_count == 5
        assert result.validation_row_count == 3
        assert result.test_raw_row_count == 3
        assert result.test_row_count == 2
        assert len(result.validation_predictions) == 3
        assert len(result.test_predictions) == 2


def test_real_bundle_evaluation_label_changes_preserve_fit_and_predictions(
    tmp_path: Path,
) -> None:
    original = read_fast_training_bundle(
        _write_fl81_bundle(tmp_path / "original", evaluation_target_shift=0.0)
    )
    changed = read_fast_training_bundle(
        _write_fl81_bundle(tmp_path / "changed", evaluation_target_shift=5_000.0)
    )
    assert (
        original.manifest.feature_logical_fingerprint_sha256
        == changed.manifest.feature_logical_fingerprint_sha256
    )
    request = _request(
        FastForecastModelFamily.RIDGE_REGRESSION,
        FastForecastTarget.ENDPOINT_RETURN_BPS,
    )
    first = run_fast_chronological_validation(original, request, _policy()).fold_results[0]
    second = run_fast_chronological_validation(changed, request, _policy()).fold_results[0]
    assert first.model.feature_transforms == second.model.feature_transforms
    assert first.model.coefficients == second.model.coefficients
    assert first.model.intercept == second.model.intercept
    assert first.validation_predictions == second.validation_predictions
    assert first.test_predictions == second.test_predictions
    assert first.model.training_bundle_fingerprint_sha256 != second.model.training_bundle_fingerprint_sha256
    assert first.model.artifact_fingerprint_sha256 != second.model.artifact_fingerprint_sha256
