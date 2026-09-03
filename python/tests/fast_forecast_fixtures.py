from __future__ import annotations

from dataclasses import replace

from shreks_brain.research.counterfactual_parquet import (
    COUNTERFACTUAL_DATASET_SCHEMA_NAME,
    COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
    CounterfactualDatasetManifest,
)
from shreks_brain.research.counterfactuals import COUNTERFACTUAL_ACTION_LABEL_VERSION
from shreks_brain.research.fast_training_bundle import (
    FAST_TRAINING_BUNDLE_SCHEMA_NAME,
    FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
    FastTrainingBundle,
    FastTrainingBundleManifest,
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
    FastTrainingLifecycleEvent,
    FastTrainingReserveContext,
    FastTrainingWindowSummary,
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
    FuturePathTrainingLabel,
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
)

WSOL = "So11111111111111111111111111111111111111112"


def window(window_ms: int, signal: float, *, decision_sequence: int, decision_time: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=max(0, int(3 + signal)),
        sell_count=max(0, int(1 - signal / 4)),
        unique_buy_actors=max(1, int(2 + signal / 2)),
        unique_sell_actors=1,
        buy_arrival_rate_per_second=4.0 + signal,
        sell_arrival_rate_per_second=max(0.0, 1.0 - signal / 10),
        count_imbalance=0.3 + signal / 20,
        buy_base_quantity=4.0 + signal,
        sell_base_quantity=1.0,
        buy_quote_quantity=0.2 + signal / 100,
        sell_quote_quantity=0.05,
        net_quote_quantity=0.15 + signal / 100,
        quote_flow_imbalance=0.4 + signal / 20,
        quote_flow_velocity_per_second=0.5 + signal / 10,
        quote_flow_acceleration_per_second2=0.1 + signal / 20,
        local_high_price_quote=0.05 + signal / 1000,
        local_high_sequence=decision_sequence,
        local_high_observed_at_unix_ms=decision_time,
        local_low_price_quote=0.045 + signal / 2000,
        local_low_sequence=max(1, decision_sequence - 1),
        local_low_observed_at_unix_ms=max(0, decision_time - 50),
        post_high_low_price_quote=None,
        post_high_low_sequence=None,
        post_high_low_observed_at_unix_ms=None,
        last_price_quote=0.05 + signal / 1000,
        drawdown_from_local_high=max(0.0, 0.05 - signal / 100),
        recovery_from_local_low=0.1 + signal / 100,
    )


def feature_record(
    index: int,
    signal: float,
    *,
    signature: str | None = None,
    observed_at_unix_ms: int | None = None,
    actor: str | None = "wallet",
    with_context: bool = False,
) -> FastTrainingFeatureRecord:
    sequence = index + 1
    observed = observed_at_unix_ms if observed_at_unix_ms is not None else 1_000 + index * 100
    price = 0.05 + signal / 1000
    reserve = None
    lifecycle = None
    if with_context:
        reserve = FastTrainingReserveContext(
            kind="pump_curve",
            virtual_base_reserve_raw=20_000_000_000 + index,
            virtual_quote_reserve_raw=10_000_000_000 + index,
            real_base_reserve_raw=9_000_000_000 + index,
            real_quote_reserve_raw=5_000_000_000 + index,
            base_decimals=6,
            quote_decimals=9,
        )
        lifecycle = FastTrainingLifecycleEvent(
            kind="pump_graduation",
            provider="helius",
            mint="mint-fl8-2",
            quote_mint=WSOL,
            from_venue="pump_fun_bonding_curve",
            to_venue="pump_swap",
            pool_address="pool-fl8-2",
            signature="grad-fl8-2",
            slot=99,
            detected_at_unix_ms=observed - 40,
            occurred_at_unix_ms=observed - 60,
        )
    return FastTrainingFeatureRecord(
        schema_name=FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version=FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature=signature or f"decision-{index}",
        decision_ordinal=0,
        decision_sequence=sequence,
        mint="mint-fl8-2",
        quote_mint=WSOL,
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=observed,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=observed - 20,
        decision_occurred_at_unix_ms=observed - 30,
        decision_slot=77 + index,
        decision_event_kind="buy" if index % 2 == 0 else "sell",
        decision_actor=actor,
        decision_executable_entry_price_quote=price,
        decision_entry_total_quote=price * 2.05,
        snapshot_as_of_unix_ms=observed,
        snapshot_last_sequence=sequence,
        snapshot_last_price_quote=price,
        last_reserve_context=reserve,
        last_lifecycle_event=lifecycle,
        windows=tuple(
            window(value, signal, decision_sequence=sequence, decision_time=observed)
            for value in DEFAULT_FAST_WINDOWS_MS
        ),
    )


def future_label(
    record: FastTrainingFeatureRecord,
    horizon_ms: int,
    *,
    endpoint_return_bps: float | None,
    reversal_occurred: bool | None,
    completeness: str = "complete",
) -> FuturePathTrainingLabel:
    complete = completeness == "complete"
    return FuturePathTrainingLabel(
        decision_signature=record.decision_signature,
        decision_ordinal=record.decision_ordinal,
        decision_sequence=record.decision_sequence,
        decision_mint=record.mint,
        decision_quote_mint=record.quote_mint,
        decision_venue=record.venue,
        decision_observed_at_unix_ms=record.decision_observed_at_unix_ms,
        decision_entry_price_quote=record.decision_executable_entry_price_quote,
        decision_entry_total_quote=record.decision_entry_total_quote,
        coverage_complete_through_unix_ms=record.decision_observed_at_unix_ms + horizon_ms,
        coverage_contiguous=complete,
        horizon_ms=horizon_ms,
        label_version=1,
        completeness=completeness,
        event_count=1 if complete else 0,
        no_trade_events=False,
        endpoint_signature=None,
        endpoint_ordinal=None,
        endpoint_observed_at_unix_ms=None,
        endpoint_price_quote=None,
        endpoint_return_bps=endpoint_return_bps if complete else None,
        mfe_bps=(None if endpoint_return_bps is None or not complete else endpoint_return_bps + 25.0),
        mae_bps=(None if endpoint_return_bps is None or not complete else min(-5.0, endpoint_return_bps - 50.0)),
        time_to_peak_ms=100 if complete else None,
        time_to_trough_ms=50 if complete else None,
        reversal_occurred=reversal_occurred if complete else None,
        first_reversal_after_ms=150 if complete and reversal_occurred else None,
        min_exit_capacity_base=8.0 if complete else None,
        endpoint_exit_capacity_base=7.5 if complete else None,
        route_unavailability_observed=False if complete else None,
        best_cost_adjusted_return_bps=(None if endpoint_return_bps is None or not complete else endpoint_return_bps - 10.0),
        endpoint_cost_adjusted_return_bps=(None if endpoint_return_bps is None or not complete else endpoint_return_bps - 20.0),
    )


def training_bundle(*, target_shift: float = 0.0) -> FastTrainingBundle:
    records = tuple(feature_record(index, float(index)) for index in range(6))
    features = FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(records),
        source_sha256="1" * 64,
    )
    labels: list[FuturePathTrainingLabel] = []
    for index, record in enumerate(records):
        return_bps = (-120.0 + index * 55.0) + target_shift
        labels.append(
            future_label(
                record,
                250,
                endpoint_return_bps=return_bps,
                reversal_occurred=index % 2 == 1,
            )
        )
        labels.append(
            future_label(
                record,
                500,
                endpoint_return_bps=(return_bps * 1.5 if index != 5 else None),
                reversal_occurred=index % 3 == 0,
                completeness="incomplete" if index == 4 else "complete",
            )
        )
    label_tuple = tuple(labels)
    future_path = FuturePathTrainingLabelDataset(
        labels=label_tuple,
        logical_fingerprint_sha256=future_path_logical_fingerprint_sha256(label_tuple),
        label_version=1,
    )
    counterfactual_manifest = CounterfactualDatasetManifest(
        schema_name=COUNTERFACTUAL_DATASET_SCHEMA_NAME,
        schema_version=COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        row_count=1,
        min_action_observed_at_unix_ms=records[0].decision_observed_at_unix_ms,
        max_action_observed_at_unix_ms=records[0].decision_observed_at_unix_ms,
        dataset_fingerprint_sha256="2" * 64,
    )
    provisional = FastTrainingBundleManifest(
        schema_name=FAST_TRAINING_BUNDLE_SCHEMA_NAME,
        schema_version=FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
        feature_schema_name=FAST_TRAINING_FEATURE_SCHEMA_NAME,
        feature_schema_version=FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        future_path_schema_name=FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
        future_path_schema_version=FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
        future_path_label_version=1,
        counterfactual_schema_name=COUNTERFACTUAL_DATASET_SCHEMA_NAME,
        counterfactual_schema_version=COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        counterfactual_label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_count=len(records),
        future_path_label_row_count=len(label_tuple),
        counterfactual_row_count=1,
        min_decision_observed_at_unix_ms=records[0].decision_observed_at_unix_ms,
        max_decision_observed_at_unix_ms=records[-1].decision_observed_at_unix_ms,
        feature_logical_fingerprint_sha256=features.logical_fingerprint_sha256,
        feature_source_jsonl_sha256=features.source_sha256,
        future_path_logical_fingerprint_sha256=future_path.logical_fingerprint_sha256,
        counterfactual_logical_fingerprint_sha256=counterfactual_manifest.dataset_fingerprint_sha256,
        bundle_fingerprint_sha256="0" * 64,
    )
    manifest = replace(
        provisional,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(provisional),
    )
    return FastTrainingBundle(
        manifest=manifest,
        features=features,
        future_path_labels=future_path,
        counterfactual_rows=({"placeholder": True},),
        counterfactual_manifest=counterfactual_manifest,
    )
