use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{
    LifecycleEventKind, ProviderId, TokenLifecycleEvent, TokenMintState, VenueId,
};
use shreks_observer::Observer;
use shreks_providers::{pump_quote::SYSTEM_SOL_QUOTE_MINT, ChainDataProvider, ProviderError};
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const MINT: &str = "HydrateMint11111111111111111111111111111111";
const PUMPSWAP_MINT: &str = "HydratePumpSwapMint1111111111111111111111111";
const PUMPSWAP_POOL: &str = "HydratePumpSwapPool1111111111111111111111111";
const OBSERVED_MS: i64 = 1_788_193_719_960;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-metadata-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn raw_trade(signature: &str, mint: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 42,
        observed_at_unix_ms,
        mint: mint.to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: observed_at_unix_ms / 1_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
}

fn raw_pumpswap_trade(signature: &str, observed_at_unix_ms: i64) -> PumpSwapTradeEvidenceWrite {
    let log_index = 7;
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 84,
        observed_at_unix_ms,
        pool: PUMPSWAP_POOL.to_owned(),
        user: "swap-user-a".to_owned(),
        is_buy: true,
        base_amount_raw: 500_000_000,
        quote_amount_raw: 2_500_000_000,
        user_quote_amount_raw: 2_530_000_000,
        timestamp_unix_seconds: observed_at_unix_ms / 1_000,
        pool_base_reserves_raw: 600_000_000_000_000,
        pool_quote_reserves_raw: 32_000_000_000,
    }
}

fn verify_pumpswap_market(db: &ShreksDb, signature: &str) {
    db.record_pump_migration_signal(signature, 80, OBSERVED_MS - 2_000)
        .unwrap();
    db.complete_pump_migration(
        signature,
        OBSERVED_MS - 1_000,
        &[TokenLifecycleEvent {
            kind: LifecycleEventKind::PumpGraduation,
            provider: ProviderId::SolanaPublic,
            mint: PUMPSWAP_MINT.to_owned(),
            quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
            from_venue: VenueId::PumpFunBondingCurve,
            to_venue: VenueId::PumpSwap,
            pool_address: PUMPSWAP_POOL.to_owned(),
            signature: signature.to_owned(),
            slot: 80,
            detected_at_unix_ms: OBSERVED_MS - 2_000,
            occurred_at_unix_ms: Some(OBSERVED_MS - 3_000),
        }],
    )
    .unwrap();
}

struct RecordingPublicChain {
    requests: Arc<Mutex<Vec<String>>>,
}

#[async_trait]
impl ChainDataProvider for RecordingPublicChain {
    fn provider_id(&self) -> ProviderId {
        ProviderId::SolanaPublic
    }

    async fn token_mint_state(&self, mint: &str) -> Result<TokenMintState, ProviderError> {
        self.requests.lock().unwrap().push(mint.to_owned());
        Ok(TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 43,
            observed_at_unix_ms: OBSERVED_MS + 100_000,
        })
    }
}

#[test]
fn selector_bounds_raw_frontiers_before_deduplicating_missing_mints() {
    let source = include_str!("../src/fast_lane_metadata.rs");
    assert!(source.contains("FAST_LANE_METADATA_RAW_SCAN_LIMIT"));
    assert!(source.contains("recent_pump_rows"));
    assert!(source.contains("recent_pumpswap_rows"));
    assert!(!source.contains("ROW_NUMBER() OVER"));
}

#[tokio::test]
async fn raw_fast_lane_mint_without_state_is_hydrated_once_from_public_solana() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-hydrate", MINT, OBSERVED_MS))
        .unwrap();

    let requests = Arc::new(Mutex::new(Vec::new()));
    let mut observer = Observer::new(db).with_chain_provider(Arc::new(RecordingPublicChain {
        requests: Arc::clone(&requests),
    }));

    let first = observer.run_cycle().await.unwrap();
    assert_eq!(requests.lock().unwrap().as_slice(), &[MINT.to_owned()]);
    assert_eq!(first.mint_states_stored, 1);

    let second = observer.run_cycle().await.unwrap();
    assert_eq!(requests.lock().unwrap().as_slice(), &[MINT.to_owned()]);
    assert_eq!(second.mint_states_stored, 0);

    drop(observer);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.verified_mint_decimals(MINT).unwrap(), Some(6));

    cleanup_dir(&root);
}

#[tokio::test]
async fn hydration_is_capped_at_eight_and_prioritizes_freshest_distinct_mints() {
    let root = unique_test_dir("budget");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let mut inserted = Vec::new();
    for index in 0..10_i64 {
        let mint = format!("HydrateBudgetMint{index:02}111111111111111111111111");
        let signature = format!("sig-budget-{index:02}");
        db.record_pump_trade_evidence(&raw_trade(
            &signature,
            &mint,
            OBSERVED_MS + index,
        ))
        .unwrap();
        inserted.push(mint);
    }

    let requests = Arc::new(Mutex::new(Vec::new()));
    let mut observer = Observer::new(db).with_chain_provider(Arc::new(RecordingPublicChain {
        requests: Arc::clone(&requests),
    }));
    let report = observer.run_cycle().await.unwrap();

    let expected = inserted[2..].iter().rev().cloned().collect::<Vec<_>>();
    assert_eq!(requests.lock().unwrap().as_slice(), expected.as_slice());
    assert_eq!(report.mint_states_stored, 8);

    cleanup_dir(&root);
}

#[tokio::test]
async fn pumpswap_raw_evidence_hydrates_only_the_verified_lifecycle_base_mint() {
    let root = unique_test_dir("pumpswap");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    verify_pumpswap_market(&db, "sig-pumpswap-migration");
    db.record_pump_swap_trade_evidence(&raw_pumpswap_trade(
        "sig-pumpswap-trade",
        OBSERVED_MS,
    ))
    .unwrap();

    let requests = Arc::new(Mutex::new(Vec::new()));
    let mut observer = Observer::new(db).with_chain_provider(Arc::new(RecordingPublicChain {
        requests: Arc::clone(&requests),
    }));
    let report = observer.run_cycle().await.unwrap();

    assert_eq!(
        requests.lock().unwrap().as_slice(),
        &[PUMPSWAP_MINT.to_owned()]
    );
    assert_eq!(report.mint_states_stored, 1);

    cleanup_dir(&root);
}
