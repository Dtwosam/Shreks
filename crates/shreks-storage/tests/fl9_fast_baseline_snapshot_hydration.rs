use shreks_core::{
    FastMarketKey, FastMarketSnapshot, FastReserveContext, FastWindowSummary, LifecycleEventKind,
    ProviderId, TokenLifecycleEvent, VenueId, DEFAULT_FAST_WINDOWS_MS,
};
use shreks_storage::{
    hydrate_fast_baseline_snapshot, FastBaselineSnapshotHydration, FastTrainingFeatureRecord,
    FastTrainingLifecycleEvent, FastTrainingReserveContext, FastTrainingWindowSummary,
    FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION, FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};

fn training_window(window_ms: u64, offset: u64) -> FastTrainingWindowSummary {
    let sequence = 30 + offset;
    let at = 9_000 + i64::try_from(offset).unwrap();
    FastTrainingWindowSummary {
        window_ms,
        buy_count: 10 + offset,
        sell_count: 3 + offset,
        unique_buy_actors: 6 + offset,
        unique_sell_actors: 2 + offset,
        buy_arrival_rate_per_second: 5.0 + offset as f64,
        sell_arrival_rate_per_second: 1.0 + offset as f64 / 10.0,
        count_imbalance: 0.25,
        buy_base_quantity: 100.0 + offset as f64,
        sell_base_quantity: 20.0 + offset as f64,
        buy_quote_quantity: 1.5 + offset as f64 / 100.0,
        sell_quote_quantity: 0.4 + offset as f64 / 100.0,
        net_quote_quantity: 1.1,
        quote_flow_imbalance: 0.55,
        quote_flow_velocity_per_second: 2.5 + offset as f64,
        quote_flow_acceleration_per_second2: 0.75 + offset as f64 / 10.0,
        local_high_price_quote: Some(0.012 + offset as f64 / 100_000.0),
        local_high_sequence: Some(sequence),
        local_high_observed_at_unix_ms: Some(at),
        local_low_price_quote: Some(0.009 + offset as f64 / 100_000.0),
        local_low_sequence: Some(sequence.saturating_sub(2)),
        local_low_observed_at_unix_ms: Some(at - 20),
        post_high_low_price_quote: Some(0.010 + offset as f64 / 100_000.0),
        post_high_low_sequence: Some(sequence + 1),
        post_high_low_observed_at_unix_ms: Some(at + 10),
        last_price_quote: Some(0.011 + offset as f64 / 100_000.0),
        drawdown_from_local_high: 0.08,
        recovery_from_local_low: 0.20,
    }
}

fn windows() -> Vec<FastTrainingWindowSummary> {
    DEFAULT_FAST_WINDOWS_MS
        .iter()
        .enumerate()
        .map(|(index, window_ms)| training_window(*window_ms, index as u64))
        .collect()
}

fn pump_curve_record() -> FastTrainingFeatureRecord {
    FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: "sig-hydration".to_owned(),
        decision_ordinal: 7,
        decision_sequence: 42,
        mint: "mint-hydration".to_owned(),
        quote_mint: "quote-hydration".to_owned(),
        venue: "pump_fun_bonding_curve".to_owned(),
        decision_observed_at_unix_ms: 10_000,
        decision_provider: "helius".to_owned(),
        decision_source_observed_at_unix_ms: 9_990,
        decision_occurred_at_unix_ms: 9_900,
        decision_slot: 777,
        decision_event_kind: "buy".to_owned(),
        decision_actor: Some("wallet-a".to_owned()),
        decision_executable_entry_price_quote: 0.0101,
        decision_entry_total_quote: Some(1.01),
        snapshot_as_of_unix_ms: 10_000,
        snapshot_last_sequence: Some(42),
        snapshot_last_price_quote: Some(0.0101),
        last_reserve_context: Some(FastTrainingReserveContext::PumpCurve {
            virtual_base_reserve_raw: 1_000_000,
            virtual_quote_reserve_raw: 2_000_000,
            real_base_reserve_raw: 900_000,
            real_quote_reserve_raw: 1_800_000,
            base_decimals: 6,
            quote_decimals: 9,
        }),
        last_lifecycle_event: Some(FastTrainingLifecycleEvent {
            kind: "pump_graduation".to_owned(),
            provider: "helius".to_owned(),
            mint: "mint-hydration".to_owned(),
            quote_mint: "quote-hydration".to_owned(),
            from_venue: "pump_fun_bonding_curve".to_owned(),
            to_venue: "pump_swap".to_owned(),
            pool_address: "pool-hydration".to_owned(),
            signature: "sig-graduation".to_owned(),
            slot: 700,
            detected_at_unix_ms: 9_800,
            occurred_at_unix_ms: Some(9_700),
        }),
        windows: windows(),
    }
}

fn expected_window(value: &FastTrainingWindowSummary) -> FastWindowSummary {
    FastWindowSummary {
        window_ms: value.window_ms,
        buy_count: value.buy_count,
        sell_count: value.sell_count,
        unique_buy_actors: value.unique_buy_actors,
        unique_sell_actors: value.unique_sell_actors,
        buy_arrival_rate_per_second: value.buy_arrival_rate_per_second,
        sell_arrival_rate_per_second: value.sell_arrival_rate_per_second,
        count_imbalance: value.count_imbalance,
        buy_base_quantity: value.buy_base_quantity,
        sell_base_quantity: value.sell_base_quantity,
        buy_quote_quantity: value.buy_quote_quantity,
        sell_quote_quantity: value.sell_quote_quantity,
        net_quote_quantity: value.net_quote_quantity,
        quote_flow_imbalance: value.quote_flow_imbalance,
        quote_flow_velocity_per_second: value.quote_flow_velocity_per_second,
        quote_flow_acceleration_per_second2: value.quote_flow_acceleration_per_second2,
        local_high_price_quote: value.local_high_price_quote,
        local_high_sequence: value.local_high_sequence,
        local_high_observed_at_unix_ms: value.local_high_observed_at_unix_ms,
        local_low_price_quote: value.local_low_price_quote,
        local_low_sequence: value.local_low_sequence,
        local_low_observed_at_unix_ms: value.local_low_observed_at_unix_ms,
        post_high_low_price_quote: value.post_high_low_price_quote,
        post_high_low_sequence: value.post_high_low_sequence,
        post_high_low_observed_at_unix_ms: value.post_high_low_observed_at_unix_ms,
        last_price_quote: value.last_price_quote,
        drawdown_from_local_high: value.drawdown_from_local_high,
        recovery_from_local_low: value.recovery_from_local_low,
    }
}

fn expected_pump_curve_hydration(
    record: &FastTrainingFeatureRecord,
) -> FastBaselineSnapshotHydration {
    FastBaselineSnapshotHydration {
        version: FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
        source_event_id: "sig-hydration:7".to_owned(),
        market_key: "pump_fun_bonding_curve:mint-hydration:quote-hydration".to_owned(),
        source_sequence: 42,
        as_of_unix_ms: 10_000,
        decision_executable_entry_price_quote: 0.0101,
        decision_entry_total_quote: Some(1.01),
        snapshot: FastMarketSnapshot {
            market: FastMarketKey::new(
                "mint-hydration",
                "quote-hydration",
                VenueId::PumpFunBondingCurve,
            )
            .unwrap(),
            as_of_unix_ms: 10_000,
            last_sequence: Some(42),
            last_price_quote: Some(0.0101),
            last_reserve_context: Some(FastReserveContext::PumpCurve {
                virtual_base_reserve_raw: 1_000_000,
                virtual_quote_reserve_raw: 2_000_000,
                real_base_reserve_raw: 900_000,
                real_quote_reserve_raw: 1_800_000,
                base_decimals: 6,
                quote_decimals: 9,
            }),
            last_lifecycle_event: Some(TokenLifecycleEvent {
                kind: LifecycleEventKind::PumpGraduation,
                provider: ProviderId::Helius,
                mint: "mint-hydration".to_owned(),
                quote_mint: "quote-hydration".to_owned(),
                from_venue: VenueId::PumpFunBondingCurve,
                to_venue: VenueId::PumpSwap,
                pool_address: "pool-hydration".to_owned(),
                signature: "sig-graduation".to_owned(),
                slot: 700,
                detected_at_unix_ms: 9_800,
                occurred_at_unix_ms: Some(9_700),
            }),
            windows: record.windows.iter().map(expected_window).collect(),
        },
    }
}

#[test]
fn pump_curve_row_hydrates_exact_campaign_identity_and_snapshot() {
    let record = pump_curve_record();

    let actual = hydrate_fast_baseline_snapshot(&record).unwrap();

    assert_eq!(actual, expected_pump_curve_hydration(&record));
    assert_eq!(actual.version, FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION);
    assert_eq!(actual.source_event_id, "sig-hydration:7");
    assert_eq!(
        actual.market_key,
        "pump_fun_bonding_curve:mint-hydration:quote-hydration"
    );
    assert_eq!(actual.source_sequence, record.decision_sequence);
    assert_eq!(actual.as_of_unix_ms, record.decision_observed_at_unix_ms);
    assert_eq!(actual.snapshot.as_of_unix_ms, actual.as_of_unix_ms);
    assert_eq!(actual.snapshot.last_sequence, Some(actual.source_sequence));
}

#[test]
fn all_sealed_window_and_ordered_path_fields_are_copied_without_recomputation() {
    let record = pump_curve_record();
    let actual = hydrate_fast_baseline_snapshot(&record).unwrap();

    assert_eq!(actual.snapshot.windows.len(), DEFAULT_FAST_WINDOWS_MS.len());
    for (source, hydrated) in record.windows.iter().zip(&actual.snapshot.windows) {
        assert_eq!(hydrated, &expected_window(source));
        assert_eq!(hydrated.window_ms, source.window_ms);
        assert_eq!(hydrated.local_high_sequence, source.local_high_sequence);
        assert_eq!(
            hydrated.local_high_observed_at_unix_ms,
            source.local_high_observed_at_unix_ms
        );
        assert_eq!(hydrated.local_low_sequence, source.local_low_sequence);
        assert_eq!(
            hydrated.post_high_low_sequence,
            source.post_high_low_sequence
        );
        assert_eq!(
            hydrated.post_high_low_observed_at_unix_ms,
            source.post_high_low_observed_at_unix_ms
        );
    }
}

#[test]
fn pumpswap_pool_reserve_context_is_preserved_exactly() {
    let mut record = pump_curve_record();
    record.venue = "pump_swap".to_owned();
    record.last_reserve_context = Some(FastTrainingReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 500_000,
        pool_quote_reserve_raw: 800_000,
        virtual_quote_reserve_raw: Some(-12_345),
        base_decimals: 6,
        quote_decimals: 9,
    });

    let actual = hydrate_fast_baseline_snapshot(&record).unwrap();

    assert_eq!(
        actual.market_key,
        "pump_swap:mint-hydration:quote-hydration"
    );
    assert_eq!(actual.snapshot.market.venue, VenueId::PumpSwap);
    assert_eq!(
        actual.snapshot.last_reserve_context,
        Some(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: 500_000,
            pool_quote_reserve_raw: 800_000,
            virtual_quote_reserve_raw: Some(-12_345),
            base_decimals: 6,
            quote_decimals: 9,
        })
    );
    assert_eq!(
        actual.snapshot.last_lifecycle_event.as_ref().unwrap().to_venue,
        VenueId::PumpSwap
    );
}

#[test]
fn reserve_context_venue_contradiction_fails_closed() {
    let mut record = pump_curve_record();
    record.last_reserve_context = Some(FastTrainingReserveContext::PumpSwapPool {
        pool_base_reserve_raw: 1,
        pool_quote_reserve_raw: 1,
        virtual_quote_reserve_raw: None,
        base_decimals: 6,
        quote_decimals: 9,
    });

    let error = hydrate_fast_baseline_snapshot(&record).unwrap_err();
    assert!(
        error.to_string().contains("reserve")
            && error.to_string().contains("venue")
    );
}

#[test]
fn malformed_lifecycle_evidence_fails_closed() {
    let base = pump_curve_record();

    for (name, mutate, expected) in [
        (
            "provider",
            0_u8,
            "provider",
        ),
        (
            "kind",
            1_u8,
            "kind",
        ),
        (
            "transition",
            2_u8,
            "transition",
        ),
        (
            "market",
            3_u8,
            "market",
        ),
    ] {
        let mut record = base.clone();
        let event = record.last_lifecycle_event.as_mut().unwrap();
        match mutate {
            0 => event.provider = "unknown_provider".to_owned(),
            1 => event.kind = "unknown_kind".to_owned(),
            2 => event.to_venue = "pump_fun_bonding_curve".to_owned(),
            3 => event.mint = "different-mint".to_owned(),
            _ => unreachable!(),
        }

        let error = hydrate_fast_baseline_snapshot(&record)
            .unwrap_err()
            .to_string();
        assert!(
            error.contains(expected),
            "{name} defect should mention {expected}; got {error}"
        );
    }
}

#[test]
fn existing_fl8_point_in_time_guard_remains_authoritative() {
    let mut future_sequence = pump_curve_record();
    future_sequence.windows[0].local_high_sequence = Some(43);
    let error = hydrate_fast_baseline_snapshot(&future_sequence)
        .unwrap_err()
        .to_string();
    assert!(error.contains("future sequence"), "{error}");

    let mut future_timestamp = pump_curve_record();
    future_timestamp.windows[0].local_high_observed_at_unix_ms = Some(10_001);
    let error = hydrate_fast_baseline_snapshot(&future_timestamp)
        .unwrap_err()
        .to_string();
    assert!(error.contains("future path timestamp"), "{error}");

    let mut future_lifecycle = pump_curve_record();
    future_lifecycle
        .last_lifecycle_event
        .as_mut()
        .unwrap()
        .detected_at_unix_ms = 10_001;
    let error = hydrate_fast_baseline_snapshot(&future_lifecycle)
        .unwrap_err()
        .to_string();
    assert!(error.contains("future lifecycle"), "{error}");
}

#[test]
fn hydration_is_deterministic_for_identical_fl8_rows() {
    let record = pump_curve_record();

    let first = hydrate_fast_baseline_snapshot(&record).unwrap();
    let second = hydrate_fast_baseline_snapshot(&record).unwrap();

    assert_eq!(first, second);
}

#[test]
fn hydration_source_has_no_future_execution_or_runtime_authority() {
    let source = include_str!("../src/fast_baseline_hydration.rs");

    for forbidden in [
        "rusqlite",
        "reqwest",
        "std::fs",
        "std::net",
        "shreks_providers",
        "FuturePathLabel",
        "Counterfactual",
        "Paper",
        "RiskContext",
        "TradeIntent",
        "RuntimeMode::Live",
        "sign",
        "submit",
        "registry",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "snapshot hydration must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "FastTrainingFeatureRecord",
        "FastMarketSnapshot",
        "FastWindowSummary",
        "FastReserveContext",
        "TokenLifecycleEvent",
        "validate_record",
        "parse_training_venue",
    ] {
        assert!(
            source.contains(required),
            "snapshot hydration must preserve the sealed source seam: {required}"
        );
    }
}
