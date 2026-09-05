use std::{
    env,
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    project_entry, project_exit, FastEvent, FastEventId, FastEventKind, FastMarketKey,
    FastReserveContext, FuturePathCompleteness, FuturePathCoverage, FuturePathDecision,
    FuturePathLabel, ProviderId, VenueId, FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{
    decimal_quantity_to_raw, pump_swap_event_ordinal, EvidenceWriteOutcome,
    FastTrainingEconomicsStatus, PumpSwapExecutionEconomicsWrite, PumpSwapMarket,
    PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-training-economics";
const SWAP_MINT: &str = "mint-training-economics-swap";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-training-economics-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(
    signature: &str,
    observed_at: i64,
    is_buy: bool,
    token_raw: u64,
    sol_raw: u64,
    real_token: u64,
) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::Helius,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 77,
        observed_at_unix_ms: observed_at,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: format!("wallet-{signature}"),
        is_buy,
        token_amount_raw: token_raw,
        sol_amount_raw: sol_raw,
        quote_amount_raw: 0,
        timestamp_unix_seconds: observed_at / 1_000,
        virtual_sol_reserves_raw: 10_000_000_000 + sol_raw,
        virtual_token_reserves_raw: 20_000_000_000 + token_raw,
        real_sol_reserves_raw: 5_000_000_000 + sol_raw,
        real_token_reserves_raw: real_token,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: if is_buy { "buy" } else { "sell" }.to_owned(),
    }
}

fn event(
    signature: &str,
    sequence: u64,
    observed_at: i64,
    kind: FastEventKind,
    price: f64,
    base: f64,
) -> FastEvent {
    let source_observed_at = observed_at - 20;
    let occurred_at_unix_ms = (source_observed_at / 1_000) * 1_000;
    FastEvent::new(
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        ProviderId::Helius,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        kind,
        Some(format!("wallet-{signature}")),
        77,
        occurred_at_unix_ms,
        observed_at,
        base,
        base * price,
        price,
    )
    .unwrap()
}

fn store_event(
    db: &ShreksDb,
    signature: &str,
    sequence: u64,
    observed_at: i64,
    kind: FastEventKind,
    price: f64,
    real_token: u64,
) {
    let is_buy = kind == FastEventKind::Buy;
    let sol_raw = (2.0 * price * 1_000_000_000.0).round() as u64;
    let raw = raw_trade(
        signature,
        observed_at - 20,
        is_buy,
        2_000_000,
        sol_raw,
        real_token,
    );
    db.record_pump_trade_evidence(&raw).unwrap();
    db.record_fast_event(
        &event(signature, sequence, observed_at, kind, price, 2.0),
        observed_at - 20,
        6,
        9,
    )
    .unwrap();
}

fn decision(
    signature: &str,
    sequence: u64,
    observed_at_unix_ms: i64,
    executable_entry_price_quote: f64,
) -> FuturePathDecision {
    FuturePathDecision::new(
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventId::new(signature, 0).unwrap(),
        sequence,
        observed_at_unix_ms,
        executable_entry_price_quote,
    )
    .unwrap()
    .with_entry_total_quote(executable_entry_price_quote * 2.05)
    .unwrap()
}

fn complete_label(
    horizon_ms: u64,
    endpoint_signature: &str,
    endpoint_observed_at_unix_ms: i64,
    endpoint_price_quote: f64,
) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Complete,
        event_count: 1,
        no_trade_events: false,
        endpoint_event_id: Some(FastEventId::new(endpoint_signature, 0).unwrap()),
        endpoint_observed_at_unix_ms: Some(endpoint_observed_at_unix_ms),
        endpoint_price_quote: Some(endpoint_price_quote),
        endpoint_return_bps: Some(181.8),
        mfe_bps: Some(250.0),
        mae_bps: Some(-30.0),
        time_to_peak_ms: Some(200),
        time_to_trough_ms: Some(50),
        reversal_occurred: Some(false),
        first_reversal_after_ms: None,
        min_exit_capacity_base: Some(8.0),
        endpoint_exit_capacity_base: Some(7.5),
        route_unavailability_observed: Some(false),
        best_cost_adjusted_return_bps: Some(120.0),
        endpoint_cost_adjusted_return_bps: Some(80.0),
    }
}

fn incomplete_label(horizon_ms: u64) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Incomplete,
        event_count: 0,
        no_trade_events: false,
        endpoint_event_id: None,
        endpoint_observed_at_unix_ms: None,
        endpoint_price_quote: None,
        endpoint_return_bps: None,
        mfe_bps: None,
        mae_bps: None,
        time_to_peak_ms: None,
        time_to_trough_ms: None,
        reversal_occurred: None,
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    }
}

fn fixture(label: &str) -> (PathBuf, ShreksDb) {
    let root = unique_test_dir(label);
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    store_event(
        &db,
        "before",
        1,
        1_000,
        FastEventKind::Buy,
        0.050,
        12_000_000_000,
    );
    store_event(
        &db,
        "decision-a",
        2,
        1_100,
        FastEventKind::Buy,
        0.055,
        11_000_000_000,
    );
    store_event(
        &db,
        "future-a",
        3,
        1_300,
        FastEventKind::Sell,
        0.056,
        10_000_000_000,
    );
    store_event(
        &db,
        "decision-b",
        4,
        1_600,
        FastEventKind::Buy,
        0.060,
        9_000_000_000,
    );
    store_event(
        &db,
        "future-b",
        5,
        1_800,
        FastEventKind::Sell,
        0.058,
        8_000_000_000,
    );

    let decision_a = decision("decision-a", 2, 1_100, 0.055);
    db.record_future_path_label(
        &decision_a,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(250, "future-a", 1_300, 0.056),
    )
    .unwrap();
    db.record_future_path_label(
        &decision_a,
        FuturePathCoverage::new(1_500, true).unwrap(),
        &incomplete_label(500),
    )
    .unwrap();

    let decision_b = decision("decision-b", 4, 1_600, 0.060);
    db.record_future_path_label(
        &decision_b,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(250, "future-b", 1_800, 0.058),
    )
    .unwrap();
    db.record_future_path_label(
        &decision_b,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &incomplete_label(500),
    )
    .unwrap();

    (root, db)
}


fn complete_no_trade_label(horizon_ms: u64) -> FuturePathLabel {
    FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms,
        completeness: FuturePathCompleteness::Complete,
        event_count: 0,
        no_trade_events: true,
        endpoint_event_id: None,
        endpoint_observed_at_unix_ms: None,
        endpoint_price_quote: None,
        endpoint_return_bps: None,
        mfe_bps: None,
        mae_bps: None,
        time_to_peak_ms: None,
        time_to_trough_ms: None,
        reversal_occurred: None,
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    }
}

fn swap_market() -> PumpSwapMarket {
    PumpSwapMarket {
        mint: SWAP_MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        pool_address: "pool-training-economics".to_owned(),
    }
}

fn swap_raw(
    signature: &str,
    log_index: u32,
    is_buy: bool,
    observed_at_unix_ms: i64,
    pool_base_reserves_raw: u64,
    pool_quote_reserves_raw: u64,
    market_quote_amount_raw: u64,
    user_quote_amount_raw: u64,
) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 1_000 + u64::from(log_index),
        observed_at_unix_ms: observed_at_unix_ms.saturating_sub(20),
        pool: "pool-training-economics".to_owned(),
        user: format!("wallet-{signature}"),
        is_buy,
        base_amount_raw: 2_000_000,
        quote_amount_raw: market_quote_amount_raw,
        user_quote_amount_raw,
        timestamp_unix_seconds: observed_at_unix_ms / 1_000,
        pool_base_reserves_raw,
        pool_quote_reserves_raw,
    }
}

fn swap_economics(
    source: &PumpSwapTradeEvidenceWrite,
    virtual_quote_reserves_raw: Option<i128>,
) -> PumpSwapExecutionEconomicsWrite {
    let has_current_suffix = virtual_quote_reserves_raw.is_some();
    PumpSwapExecutionEconomicsWrite {
        signature: source.signature.clone(),
        ordinal: source.ordinal,
        lp_fee_basis_points: 20,
        lp_fee_raw: 1,
        protocol_fee_basis_points: 10,
        protocol_fee_raw: 1,
        quote_amount_with_or_without_lp_fee_raw: source.quote_amount_raw,
        coin_creator: has_current_suffix
            .then(|| "creator-training-economics".to_owned()),
        coin_creator_fee_basis_points: has_current_suffix.then_some(5),
        coin_creator_fee_raw: has_current_suffix.then_some(1),
        cashback_fee_basis_points: has_current_suffix.then_some(1),
        cashback_raw: has_current_suffix.then_some(0),
        buyback_fee_basis_points: has_current_suffix.then_some(1),
        buyback_fee_raw: has_current_suffix.then_some(0),
        virtual_quote_reserves_raw,
        can_boost: has_current_suffix.then_some(true),
        base_supply_raw: has_current_suffix.then_some(10_000_000_000),
    }
}

fn swap_event(
    source: &PumpSwapTradeEvidenceWrite,
    sequence: u64,
    observed_at_unix_ms: i64,
) -> FastEvent {
    let base_quantity = source.base_amount_raw as f64 / 1_000_000.0;
    let quote_quantity = source.quote_amount_raw as f64 / 1_000_000_000.0;
    FastEvent::new(
        FastEventId::new(source.signature.clone(), source.ordinal).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        FastMarketKey::new(SWAP_MINT, WSOL, VenueId::PumpSwap).unwrap(),
        if source.is_buy {
            FastEventKind::Buy
        } else {
            FastEventKind::Sell
        },
        Some(format!("wallet-{}", source.signature)),
        source.slot,
        source.timestamp_unix_seconds * 1_000,
        observed_at_unix_ms,
        base_quantity,
        quote_quantity,
        quote_quantity / base_quantity,
    )
    .unwrap()
}

fn store_swap_event(
    db: &ShreksDb,
    signature: &str,
    log_index: u32,
    is_buy: bool,
    sequence: u64,
    observed_at_unix_ms: i64,
    pool_base_reserves_raw: u64,
    pool_quote_reserves_raw: u64,
    market_quote_amount_raw: u64,
    user_quote_amount_raw: u64,
    virtual_quote_reserves_raw: Option<i128>,
) -> PumpSwapTradeEvidenceWrite {
    let source = swap_raw(
        signature,
        log_index,
        is_buy,
        observed_at_unix_ms,
        pool_base_reserves_raw,
        pool_quote_reserves_raw,
        market_quote_amount_raw,
        user_quote_amount_raw,
    );
    assert!(db.record_pump_swap_trade_evidence(&source).unwrap());
    assert!(db
        .record_pump_swap_execution_economics(&swap_economics(
            &source,
            virtual_quote_reserves_raw,
        ))
        .unwrap());
    assert!(db
        .record_pump_swap_fast_event_from_source(
            &swap_event(&source, sequence, observed_at_unix_ms),
            &source,
            &swap_market(),
            6,
            9,
        )
        .unwrap());
    source
}

fn swap_decision(
    source: &PumpSwapTradeEvidenceWrite,
    sequence: u64,
    observed_at_unix_ms: i64,
) -> FuturePathDecision {
    let event = swap_event(source, sequence, observed_at_unix_ms);
    FuturePathDecision::new(
        FastMarketKey::new(SWAP_MINT, WSOL, VenueId::PumpSwap).unwrap(),
        event.id,
        sequence,
        observed_at_unix_ms,
        event.price_quote,
    )
    .unwrap()
}

fn record_swap_path(
    db: &ShreksDb,
    decision_source: &PumpSwapTradeEvidenceWrite,
    decision_sequence: u64,
    decision_observed_at_unix_ms: i64,
    endpoint_source: Option<&PumpSwapTradeEvidenceWrite>,
    endpoint_observed_at_unix_ms: Option<i64>,
    horizon_ms: u64,
) {
    let decision = swap_decision(
        decision_source,
        decision_sequence,
        decision_observed_at_unix_ms,
    );
    let coverage = FuturePathCoverage::new(
        decision_observed_at_unix_ms + i64::try_from(horizon_ms).unwrap() + 1_000,
        true,
    )
    .unwrap();
    let label = match (endpoint_source, endpoint_observed_at_unix_ms) {
        (Some(source), Some(endpoint_time)) => {
            let endpoint_event = swap_event(source, decision_sequence + 1, endpoint_time);
            FuturePathLabel {
                version: FUTURE_PATH_LABEL_VERSION,
                horizon_ms,
                completeness: FuturePathCompleteness::Complete,
                event_count: 1,
                no_trade_events: false,
                endpoint_event_id: Some(
                    FastEventId::new(source.signature.clone(), source.ordinal).unwrap(),
                ),
                endpoint_observed_at_unix_ms: Some(endpoint_time),
                endpoint_price_quote: Some(endpoint_event.price_quote),
                endpoint_return_bps: Some(100.0),
                mfe_bps: Some(150.0),
                mae_bps: Some(-25.0),
                time_to_peak_ms: Some(horizon_ms.min(200)),
                time_to_trough_ms: Some(horizon_ms.min(50)),
                reversal_occurred: Some(false),
                first_reversal_after_ms: None,
                min_exit_capacity_base: None,
                endpoint_exit_capacity_base: None,
                route_unavailability_observed: None,
                best_cost_adjusted_return_bps: None,
                endpoint_cost_adjusted_return_bps: None,
            }
        }
        (None, None) => complete_no_trade_label(horizon_ms),
        _ => panic!("endpoint source/time must be present together"),
    };
    db.record_future_path_label(&decision, coverage, &label)
        .unwrap();
}

fn overlay_rows(db: &ShreksDb, quantity: &str, maximum_age_ms: u64) -> Vec<shreks_storage::FastTrainingEconomicsOverlayRow> {
    let features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    db.fast_training_economics_overlay_rows(
        &features,
        FUTURE_PATH_LABEL_VERSION,
        quantity,
        maximum_age_ms,
    )
    .unwrap()
}

#[test]
fn training_economics_overlay_has_exact_fl4_population() {
    let (root, db) = fixture("population");
    let features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();

    let rows = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
        )
        .unwrap();

    assert_eq!(rows.len(), 4);
    assert!(rows
        .iter()
        .all(|row| row.status == FastTrainingEconomicsStatus::UnsupportedVenue));
    assert!(rows.windows(2).all(|pair| {
        (
            pair[0].decision_sequence,
            pair[0].horizon_ms,
            pair[0].decision_signature.as_str(),
            pair[0].decision_ordinal,
        ) <= (
            pair[1].decision_sequence,
            pair[1].horizon_ms,
            pair[1].decision_signature.as_str(),
            pair[1].decision_ordinal,
        )
    }));
    assert_eq!(
        rows.iter()
            .map(|row| (
                row.decision_signature.as_str(),
                row.decision_ordinal,
                row.horizon_ms,
            ))
            .collect::<Vec<_>>(),
        vec![
            ("decision-a", 0, 250),
            ("decision-a", 0, 500),
            ("decision-b", 0, 250),
            ("decision-b", 0, 500),
        ]
    );

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn training_economics_overlay_rejects_feature_identity_drift() {
    let (root, db) = fixture("identity-drift");
    let mut features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    features[0].decision_sequence += 99;

    let error = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
        )
        .unwrap_err();

    assert!(error
        .to_string()
        .contains("training economics feature/FL4 decision identity mismatch"));

    drop(db);
    cleanup_dir(&root);
}


#[test]
fn counterfactual_decimal_quantity_is_never_rounded() {
    assert_eq!(decimal_quantity_to_raw("2.5", 6).unwrap(), 2_500_000);
    assert_eq!(decimal_quantity_to_raw("2e0", 6).unwrap(), 2_000_000);
    assert!(decimal_quantity_to_raw("0.0000001", 6).is_err());
    assert!(decimal_quantity_to_raw("2e-7", 6).is_err());
}

#[test]
fn pumpswap_available_row_uses_exact_quantity_projection_and_causal_fees() {
    let root = unique_test_dir("swap-available");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision = store_swap_event(
        &db,
        "swap-decision",
        2,
        true,
        1,
        1_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-endpoint",
        4,
        false,
        2,
        1_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 1_000, Some(&endpoint), Some(1_200), 500);

    let rows = overlay_rows(&db, "2", 1_000);
    assert_eq!(rows.len(), 1);
    let row = &rows[0];
    assert_eq!(row.status, FastTrainingEconomicsStatus::Available);
    assert_eq!(row.requested_base_quantity_raw, Some(2_000_000));
    assert_eq!(row.entry_fee.as_ref().unwrap().effective_fee_bps, 50);
    assert_eq!(row.exit_fee.as_ref().unwrap().effective_fee_bps, 50);
    assert_eq!(row.entry_fee.as_ref().unwrap().source_sequence, 1);
    assert_eq!(row.exit_fee.as_ref().unwrap().source_sequence, 2);

    let replay = db
        .fast_events_for_market_with_reserve_context(SWAP_MINT, WSOL, VenueId::PumpSwap)
        .unwrap();
    let entry_reserve = replay[0].event.reserve_context.as_ref().unwrap();
    let exit_reserve = replay[1].event.reserve_context.as_ref().unwrap();
    let expected_entry = project_entry(entry_reserve, 2_000_000).unwrap();
    let expected_exit = project_exit(exit_reserve, 2_000_000).unwrap();
    let actual_entry = row.entry_projection.as_ref().unwrap();
    let actual_exit = row.exit_projection.as_ref().unwrap();
    assert_eq!(actual_entry.base_quantity_raw, expected_entry.base_quantity_raw);
    assert_eq!(actual_entry.quote_input_raw, expected_entry.quote_input_raw);
    assert_eq!(actual_entry.quote_input, expected_entry.quote_input);
    assert_eq!(actual_entry.average_price_quote, expected_entry.average_price_quote);
    assert_eq!(actual_exit.base_quantity_raw, expected_exit.base_quantity_raw);
    assert_eq!(actual_exit.quote_output_raw, expected_exit.quote_output_raw);
    assert_eq!(actual_exit.quote_output, expected_exit.quote_output);
    assert_eq!(actual_exit.average_price_quote, expected_exit.average_price_quote);

    let FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw,
        pool_quote_reserve_raw,
        base_decimals,
        quote_decimals,
        ..
    } = entry_reserve
    else {
        panic!("expected PumpSwap entry reserve");
    };
    let zero_virtual_entry = FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: *pool_base_reserve_raw,
        pool_quote_reserve_raw: *pool_quote_reserve_raw,
        virtual_quote_reserve_raw: Some(0),
        base_decimals: *base_decimals,
        quote_decimals: *quote_decimals,
    };
    assert_ne!(
        expected_entry.quote_input_raw,
        project_entry(&zero_virtual_entry, 2_000_000)
            .unwrap()
            .quote_input_raw
    );

    let FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw,
        pool_quote_reserve_raw,
        base_decimals,
        quote_decimals,
        ..
    } = exit_reserve
    else {
        panic!("expected PumpSwap exit reserve");
    };
    let zero_virtual_exit = FastReserveContext::PumpSwapPool {
        pool_base_reserve_raw: *pool_base_reserve_raw,
        pool_quote_reserve_raw: *pool_quote_reserve_raw,
        virtual_quote_reserve_raw: Some(0),
        base_decimals: *base_decimals,
        quote_decimals: *quote_decimals,
    };
    assert_ne!(
        expected_exit.quote_output_raw,
        project_exit(&zero_virtual_exit, 2_000_000)
            .unwrap()
            .quote_output_raw
    );

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_complete_no_trade_horizon_is_explicitly_no_endpoint() {
    let root = unique_test_dir("swap-no-endpoint");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision = store_swap_event(
        &db,
        "swap-no-endpoint-decision",
        6,
        true,
        1,
        2_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 2_000, None, None, 500);

    let rows = overlay_rows(&db, "2", 1_000);
    assert_eq!(rows[0].status, FastTrainingEconomicsStatus::NoEndpoint);
    assert!(rows[0].endpoint_signature.is_none());
    assert!(rows[0].exit_projection.is_none());

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_missing_virtual_reserve_maps_to_entry_or_exit_unavailable() {
    let root = unique_test_dir("swap-reserve-unavailable-entry");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-entry-reserve-missing",
        8,
        true,
        1,
        3_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        None,
    );
    let endpoint = store_swap_event(
        &db,
        "swap-entry-reserve-endpoint",
        10,
        false,
        2,
        3_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 3_000, Some(&endpoint), Some(3_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::EntryReserveUnavailable
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-reserve-unavailable-exit");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-exit-reserve-decision",
        12,
        true,
        1,
        4_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-exit-reserve-missing",
        14,
        false,
        2,
        4_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        None,
    );
    record_swap_path(&db, &decision, 1, 4_000, Some(&endpoint), Some(4_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::ExitReserveUnavailable
    );
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_projection_limits_are_explicit_unavailable_statuses() {
    let root = unique_test_dir("swap-entry-projection");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-projection-decision",
        16,
        true,
        1,
        5_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-projection-endpoint",
        18,
        false,
        2,
        5_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 5_000, Some(&endpoint), Some(5_200), 500);
    assert_eq!(
        overlay_rows(&db, "20000", 1_000)[0].status,
        FastTrainingEconomicsStatus::EntryProjectionUnavailable
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-exit-projection");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-exit-projection-decision",
        20,
        true,
        1,
        6_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-exit-projection-endpoint",
        22,
        false,
        2,
        6_200,
        9_500_000_000,
        1,
        1,
        1,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 6_000, Some(&endpoint), Some(6_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::ExitProjectionUnavailable
    );
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_zero_quote_exit_projection_is_unavailable_before_fee_classification() {
    let root = unique_test_dir("swap-zero-quote-exit");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision = store_swap_event(
        &db,
        "swap-zero-quote-decision",
        23,
        true,
        1,
        6_500,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-zero-quote-endpoint",
        24,
        false,
        2,
        6_700,
        9_500_000_000,
        1,
        1,
        1,
        Some(0),
    );

    record_swap_path(
        &db,
        &decision,
        1,
        6_500,
        Some(&endpoint),
        Some(6_700),
        500,
    );

    let row = &overlay_rows(&db, "2", 1_000)[0];
    assert_eq!(
        row.status,
        FastTrainingEconomicsStatus::ExitProjectionUnavailable
    );
    assert!(row.entry_projection.is_some());
    assert!(row.exit_projection.is_none());
    assert!(row.entry_fee.is_none());
    assert!(row.exit_fee.is_none());

    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_fee_missing_stale_and_rate_unknown_map_without_fallback() {
    let root = unique_test_dir("swap-entry-fee-missing");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-entry-fee-missing-decision",
        24,
        false,
        1,
        7_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        99_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-entry-fee-missing-endpoint",
        26,
        false,
        2,
        7_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 7_000, Some(&endpoint), Some(7_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::EntryFeeMissing
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-entry-fee-stale");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let _older_buy = store_swap_event(
        &db,
        "swap-old-buy",
        28,
        true,
        1,
        8_000,
        10_500_000_000,
        4_900_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let decision = store_swap_event(
        &db,
        "swap-stale-decision",
        30,
        false,
        2,
        8_300,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        99_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-stale-endpoint",
        32,
        false,
        3,
        8_400,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 2, 8_300, Some(&endpoint), Some(8_400), 500);
    assert_eq!(
        overlay_rows(&db, "2", 100)[0].status,
        FastTrainingEconomicsStatus::EntryFeeStale
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-entry-fee-unknown");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let _older_buy = store_swap_event(
        &db,
        "swap-exact-buy",
        34,
        true,
        1,
        9_000,
        10_500_000_000,
        4_900_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let decision = store_swap_event(
        &db,
        "swap-unknown-buy",
        36,
        true,
        2,
        9_100,
        10_000_000_000,
        5_000_000_000,
        3,
        4,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-unknown-buy-endpoint",
        38,
        false,
        3,
        9_300,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 2, 9_100, Some(&endpoint), Some(9_300), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::EntryFeeRateUnknown
    );
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn pumpswap_exit_fee_missing_stale_and_rate_unknown_map_exactly() {
    let root = unique_test_dir("swap-exit-fee-missing");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-exit-fee-missing-decision",
        40,
        true,
        1,
        10_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-exit-fee-missing-endpoint",
        42,
        true,
        2,
        10_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        120_600_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 10_000, Some(&endpoint), Some(10_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::ExitFeeMissing
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-exit-fee-stale");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let _older_sell = store_swap_event(
        &db,
        "swap-old-sell",
        44,
        false,
        1,
        11_000,
        10_500_000_000,
        4_900_000_000,
        100_000_000,
        99_500_000,
        Some(1_000_000_000),
    );
    let decision = store_swap_event(
        &db,
        "swap-exit-stale-decision",
        46,
        true,
        2,
        11_100,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-exit-stale-endpoint",
        48,
        true,
        3,
        11_300,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        120_600_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 2, 11_100, Some(&endpoint), Some(11_300), 500);
    assert_eq!(
        overlay_rows(&db, "2", 100)[0].status,
        FastTrainingEconomicsStatus::ExitFeeStale
    );
    drop(db);
    cleanup_dir(&root);

    let root = unique_test_dir("swap-exit-fee-unknown");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-exit-unknown-decision",
        50,
        true,
        1,
        12_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-exit-unknown-endpoint",
        52,
        false,
        2,
        12_200,
        9_500_000_000,
        5_500_000_000,
        3,
        4,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 12_000, Some(&endpoint), Some(12_200), 500);
    assert_eq!(
        overlay_rows(&db, "2", 1_000)[0].status,
        FastTrainingEconomicsStatus::ExitFeeRateUnknown
    );
    drop(db);
    cleanup_dir(&root);
}

#[test]
fn conflict_quarantined_pumpswap_source_aborts_overlay() {
    let root = unique_test_dir("swap-conflict");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let decision = store_swap_event(
        &db,
        "swap-conflict-decision",
        54,
        true,
        1,
        13_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let endpoint = store_swap_event(
        &db,
        "swap-conflict-endpoint",
        56,
        false,
        2,
        13_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 13_000, Some(&endpoint), Some(13_200), 500);

    let features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();

    let mut conflict = decision.clone();
    conflict.quote_amount_raw += 1;
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    let error = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            1_000,
        )
        .unwrap_err();
    assert!(error.to_string().contains("conflict-quarantined"));

    drop(db);
    cleanup_dir(&root);
}


#[test]
fn nonrepresentable_quantity_fails_closed_before_missing_virtual_reserve_status() {
    let root = unique_test_dir("swap-invalid-quantity-before-reserve");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let decision = store_swap_event(
        &db,
        "swap-invalid-quantity-decision",
        58,
        true,
        1,
        14_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        None,
    );
    let endpoint = store_swap_event(
        &db,
        "swap-invalid-quantity-endpoint",
        60,
        false,
        2,
        14_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(&db, &decision, 1, 14_000, Some(&endpoint), Some(14_200), 500);

    let features = db
        .fast_training_feature_records(FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    let error = db
        .fast_training_economics_overlay_rows(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "0.0000001",
            1_000,
        )
        .unwrap_err();

    assert!(error
        .to_string()
        .contains("cannot be represented exactly in raw base units"));

    drop(db);
    cleanup_dir(&root);
}


#[test]
fn immutable_overlay_writer_creates_exact_two_file_artifact_and_never_overwrites() {
    let (root, db) = fixture("writer");
    let features_path = root.join("features.jsonl");
    let destination = root.join("training-economics");
    db.write_fast_training_feature_jsonl(
        FUTURE_PATH_LABEL_VERSION,
        &features_path,
    )
    .unwrap();

    let before_fl4 = db
        .fast_training_future_path_logical_fingerprint_sha256(
            FUTURE_PATH_LABEL_VERSION,
        )
        .unwrap();

    let manifest = db
        .write_fast_training_economics_overlay(
            &features_path,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
            &destination,
        )
        .unwrap();

    assert_eq!(manifest.row_count, 4);
    assert_eq!(manifest.available_row_count, 0);
    assert_eq!(
        manifest.status_counts.get("unsupported_venue"),
        Some(&4)
    );
    assert_eq!(
        manifest.status_counts.values().copied().sum::<u64>(),
        manifest.row_count
    );

    let mut names = fs::read_dir(&destination)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    names.sort();
    assert_eq!(names, vec!["manifest.json", "rows.jsonl"]);

    let rows_before = fs::read(destination.join("rows.jsonl")).unwrap();
    let manifest_before = fs::read(destination.join("manifest.json")).unwrap();

    let error = db
        .write_fast_training_economics_overlay(
            &features_path,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
            &destination,
        )
        .unwrap_err();
    assert!(error
        .to_string()
        .contains("training economics overlay destination already exists"));
    assert_eq!(
        fs::read(destination.join("rows.jsonl")).unwrap(),
        rows_before
    );
    assert_eq!(
        fs::read(destination.join("manifest.json")).unwrap(),
        manifest_before
    );

    let after_fl4 = db
        .fast_training_future_path_logical_fingerprint_sha256(
            FUTURE_PATH_LABEL_VERSION,
        )
        .unwrap();
    assert_eq!(before_fl4, after_fl4);

    drop(db);
    cleanup_dir(&root);
}


#[test]
#[ignore = "invoked explicitly by the Python FL8.1 mixed economics integration proof"]
fn write_mixed_training_economics_python_integration_fixture() {
    let root = PathBuf::from(
        env::var("SHREKS_TRAINING_ECONOMICS_INTEGRATION_DIR")
            .expect("SHREKS_TRAINING_ECONOMICS_INTEGRATION_DIR must be set"),
    );
    assert!(
        !root.exists(),
        "mixed training economics fixture destination must be fresh"
    );
    fs::create_dir_all(&root).unwrap();

    let database = root.join("shreks.db");
    let features = root.join("features.jsonl");
    let overlay = root.join("training-economics");
    let db = ShreksDb::open(&database).unwrap();

    // Unsupported Pump bonding-curve decision/horizon.
    store_event(
        &db,
        "mixed-pump-decision",
        1,
        1_000,
        FastEventKind::Buy,
        0.050,
        10_000_000_000,
    );
    store_event(
        &db,
        "mixed-pump-endpoint",
        2,
        1_200,
        FastEventKind::Sell,
        0.055,
        9_000_000_000,
    );
    let pump_decision = decision("mixed-pump-decision", 1, 1_000, 0.050);
    db.record_future_path_label(
        &pump_decision,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &complete_label(500, "mixed-pump-endpoint", 1_200, 0.055),
    )
    .unwrap();

    // Fully source-backed PumpSwap decision/horizon with exact 50 bps BUY/SELL
    // user-vs-market fee deltas and migration-15 virtual quote reserves.
    let swap_decision_source = store_swap_event(
        &db,
        "mixed-swap-decision",
        2,
        true,
        3,
        2_000,
        10_000_000_000,
        5_000_000_000,
        100_000_000,
        100_500_000,
        Some(1_000_000_000),
    );
    let swap_endpoint_source = store_swap_event(
        &db,
        "mixed-swap-endpoint",
        4,
        false,
        4,
        2_200,
        9_500_000_000,
        5_500_000_000,
        120_000_000,
        119_400_000,
        Some(1_000_000_000),
    );
    record_swap_path(
        &db,
        &swap_decision_source,
        3,
        2_000,
        Some(&swap_endpoint_source),
        Some(2_200),
        500,
    );

    let feature_manifest = db
        .write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &features)
        .unwrap();
    assert_eq!(feature_manifest.row_count, 2);

    let economics_manifest = db
        .write_fast_training_economics_overlay(
            &features,
            FUTURE_PATH_LABEL_VERSION,
            "2",
            60_000,
            &overlay,
        )
        .unwrap();
    assert_eq!(economics_manifest.row_count, 2);
    assert_eq!(economics_manifest.available_row_count, 1);
    assert_eq!(
        economics_manifest.status_counts.get("available"),
        Some(&1)
    );
    assert_eq!(
        economics_manifest.status_counts.get("unsupported_venue"),
        Some(&1)
    );

    drop(db);
    assert!(database.is_file());
    assert!(features.is_file());
    assert!(overlay.join("rows.jsonl").is_file());
    assert!(overlay.join("manifest.json").is_file());
}
