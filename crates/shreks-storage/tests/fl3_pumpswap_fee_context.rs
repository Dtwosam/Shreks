use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, ProviderId, VenueId,
};
use shreks_storage::{
    pump_swap_event_ordinal, EvidenceWriteOutcome, PumpSwapEffectiveFeeContext,
    PumpSwapMarket, PumpSwapTradeEvidenceWrite, ShreksDb, StorageError,
};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-fee-context";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl3-pumpswap-fee-context-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn market() -> PumpSwapMarket {
    PumpSwapMarket {
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        pool_address: "pool-fee-context".to_owned(),
    }
}

fn raw(
    signature: &str,
    log_index: u32,
    is_buy: bool,
    observed_at_unix_ms: i64,
    market_quote_amount_raw: u64,
    user_quote_amount_raw: u64,
) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 1_000 + u64::from(log_index),
        observed_at_unix_ms,
        pool: "pool-fee-context".to_owned(),
        user: "wallet-fee-context".to_owned(),
        is_buy,
        base_amount_raw: 500_000_000,
        quote_amount_raw: market_quote_amount_raw,
        user_quote_amount_raw,
        timestamp_unix_seconds: observed_at_unix_ms / 1_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn event(source: &PumpSwapTradeEvidenceWrite, sequence: u64, observed_at_unix_ms: i64) -> FastEvent {
    FastEvent::new(
        FastEventId::new(source.signature.clone(), source.ordinal).unwrap(),
        sequence,
        ProviderId::SolanaPublic,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpSwap).unwrap(),
        if source.is_buy {
            FastEventKind::Buy
        } else {
            FastEventKind::Sell
        },
        Some("wallet-fee-context".to_owned()),
        source.slot,
        source.timestamp_unix_seconds * 1_000,
        observed_at_unix_ms,
        500.0,
        source.quote_amount_raw as f64 / 1_000_000_000.0,
        source.quote_amount_raw as f64 / 1_000_000_000.0 / 500.0,
    )
    .unwrap()
}

fn seed(
    db: &ShreksDb,
    signature: &str,
    log_index: u32,
    is_buy: bool,
    sequence: u64,
    observed_at_unix_ms: i64,
    market_quote_amount_raw: u64,
    user_quote_amount_raw: u64,
) -> PumpSwapTradeEvidenceWrite {
    let source = raw(
        signature,
        log_index,
        is_buy,
        observed_at_unix_ms.saturating_sub(100),
        market_quote_amount_raw,
        user_quote_amount_raw,
    );
    assert!(db.record_pump_swap_trade_evidence(&source).unwrap());
    assert!(db
        .record_pump_swap_fast_event_from_source(
            &event(&source, sequence, observed_at_unix_ms),
            &source,
            &market(),
            6,
            9,
        )
        .unwrap());
    source
}

#[test]
fn latest_same_side_context_is_selected_and_opposite_side_is_ignored() {
    let root = unique_test_dir("latest-side");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let older_buy = seed(&db, "buy-old", 2, true, 1, 1_000, 1_000_000, 1_010_000);
    let _newer_sell = seed(&db, "sell-new", 4, false, 2, 1_100, 1_000_000, 990_000);
    let newer_buy = seed(&db, "buy-new", 6, true, 3, 1_200, 1_000_000, 1_020_000);

    let context = db
        .pump_swap_effective_fee_context(MINT, WSOL, true, 3, 1_250, 100)
        .unwrap();

    match context {
        PumpSwapEffectiveFeeContext::Available(value) => {
            assert_eq!(value.source_sequence, 3);
            assert_eq!(value.source_observed_at_unix_ms, 1_200);
            assert_eq!(value.age_ms, 50);
            assert_eq!(value.evidence.signature, newer_buy.signature);
            assert_eq!(value.evidence.effective_fee_bps, Some(200));
            assert_ne!(value.evidence.signature, older_buy.signature);
            assert!(value.evidence.is_buy);
        }
        other => panic!("expected available latest BUY context, got {other:?}"),
    }

    cleanup_dir(&root);
}

#[test]
fn future_events_are_never_used_and_exact_age_boundary_is_available() {
    let root = unique_test_dir("causal");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let causal = seed(&db, "buy-causal", 8, true, 1, 2_000, 1_000_000, 1_010_000);
    let _future = seed(&db, "buy-future", 10, true, 2, 2_100, 1_000_000, 1_020_000);

    let context = db
        .pump_swap_effective_fee_context(MINT, WSOL, true, 1, 2_100, 100)
        .unwrap();
    match context {
        PumpSwapEffectiveFeeContext::Available(value) => {
            assert_eq!(value.source_sequence, 1);
            assert_eq!(value.age_ms, 100);
            assert_eq!(value.evidence.signature, causal.signature);
        }
        other => panic!("expected causal exact-boundary context, got {other:?}"),
    }

    cleanup_dir(&root);
}

#[test]
fn stale_latest_context_is_reported_without_fallback() {
    let root = unique_test_dir("stale");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let latest = seed(&db, "buy-stale", 12, true, 1, 3_000, 1_000_000, 1_010_000);

    let context = db
        .pump_swap_effective_fee_context(MINT, WSOL, true, 1, 3_101, 100)
        .unwrap();
    match context {
        PumpSwapEffectiveFeeContext::Stale(value) => {
            assert_eq!(value.age_ms, 101);
            assert_eq!(value.evidence.signature, latest.signature);
        }
        other => panic!("expected stale context, got {other:?}"),
    }

    cleanup_dir(&root);
}

#[test]
fn latest_unknown_rate_does_not_fall_back_to_older_exact_rate() {
    let root = unique_test_dir("unknown");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let older = seed(&db, "buy-exact", 14, true, 1, 4_000, 1_000_000, 1_010_000);
    let latest = seed(&db, "buy-unknown", 16, true, 2, 4_050, 3, 4);

    let context = db
        .pump_swap_effective_fee_context(MINT, WSOL, true, 2, 4_060, 100)
        .unwrap();
    match context {
        PumpSwapEffectiveFeeContext::RateUnknown(value) => {
            assert_eq!(value.source_sequence, 2);
            assert_eq!(value.evidence.signature, latest.signature);
            assert_eq!(value.evidence.effective_fee_bps, None);
            assert_ne!(value.evidence.signature, older.signature);
        }
        other => panic!("expected rate_unknown context, got {other:?}"),
    }

    cleanup_dir(&root);
}

#[test]
fn selected_conflict_fails_closed_and_missing_side_is_explicit() {
    let root = unique_test_dir("conflict-missing");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    assert_eq!(
        db.pump_swap_effective_fee_context(MINT, WSOL, false, 10, 9_000, 1_000)
            .unwrap(),
        PumpSwapEffectiveFeeContext::Missing
    );

    let source = seed(&db, "buy-conflict-context", 18, true, 1, 5_000, 1_000_000, 1_010_000);
    let mut conflict = source.clone();
    conflict.quote_amount_raw += 1;
    assert_eq!(
        db.record_pump_swap_trade_evidence_or_quarantine(&conflict)
            .unwrap(),
        EvidenceWriteOutcome::QuarantinedConflict
    );

    let error = db
        .pump_swap_effective_fee_context(MINT, WSOL, true, 1, 5_050, 100)
        .unwrap_err();
    assert!(matches!(error, StorageError::InvalidData(_)));
    assert!(error.to_string().contains("conflict"));

    cleanup_dir(&root);
}
