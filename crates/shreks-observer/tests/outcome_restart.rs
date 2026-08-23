use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{DiscoveredToken, PairMarketData, ProviderId, TransactionWindow, VenueId};
use shreks_observer::Observer;
use shreks_providers::{MarketDataProvider, ProviderError};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-outcome-restart-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn candidate(mint: &str) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: Some("pumpfun".to_owned()),
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: 0,
        source: ProviderId::Helius,
    }
}

fn snapshot(mint: &str, pair: &str, observed_at_unix_ms: i64, price_usd: f64) -> PairMarketData {
    PairMarketData {
        provider: ProviderId::DexScreener,
        venue: VenueId::PumpSwap,
        chain_id: "solana".to_owned(),
        dex_id: "pumpswap".to_owned(),
        pair_address: pair.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price_usd.to_string()),
        liquidity_usd: Some(10_000.0),
        volume_5m: Some(1_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 10,
            sells: 5,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: None,
        observed_at_unix_ms,
    }
}

#[derive(Clone)]
struct StaticMarket {
    snapshot: PairMarketData,
}

#[async_trait]
impl MarketDataProvider for StaticMarket {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        assert_eq!(token_mint, self.snapshot.base_mint);
        Ok(vec![self.snapshot.clone()])
    }
}

#[tokio::test(start_paused = true)]
async fn pending_outcome_schedule_survives_restart_and_completes_exactly_once() {
    let root = unique_test_dir("complete-once");
    let db_path = root.join("shreks.db");
    let mint = "mint-restart";

    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate(mint)).unwrap();
    db.ensure_outcome_checkpoints(candidate_id, 0).unwrap();
    db.insert_market_snapshot(candidate_id, &snapshot(mint, "baseline", 1_000, 10.0))
        .unwrap();
    assert_eq!(db.outcome_checkpoints(candidate_id).unwrap().len(), 7);
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.outcome_checkpoints(candidate_id).unwrap().len(), 7);
    let mut observer = Observer::new(reopened).with_market_provider(Arc::new(StaticMarket {
        snapshot: snapshot(mint, "checkpoint", 61_000, 12.0),
    }));
    observer.run_cycle().await.unwrap();
    drop(observer);

    let connection = Connection::open(&db_path).unwrap();
    let row: (String, Option<f64>) = connection
        .query_row(
            "SELECT status, return_pct FROM candidate_outcome_checkpoints WHERE candidate_id = ?1 AND horizon_seconds = 60",
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row.0, "completed");
    assert!((row.1.unwrap() - 20.0).abs() < 1e-9);

    let completed_count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM candidate_outcome_checkpoints WHERE candidate_id = ?1 AND horizon_seconds = 60 AND status = 'completed'",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(completed_count, 1);
    drop(connection);

    let reopened_again = ShreksDb::open(&db_path).unwrap();
    let mut observer_again = Observer::new(reopened_again).with_market_provider(Arc::new(StaticMarket {
        snapshot: snapshot(mint, "later", 62_000, 13.0),
    }));
    observer_again.run_cycle().await.unwrap();
    drop(observer_again);

    let connection = Connection::open(&db_path).unwrap();
    let row_after: (String, Option<f64>) = connection
        .query_row(
            "SELECT status, return_pct FROM candidate_outcome_checkpoints WHERE candidate_id = ?1 AND horizon_seconds = 60",
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(row_after.0, "completed");
    assert!((row_after.1.unwrap() - 20.0).abs() < 1e-9);

    cleanup_dir(&root);
}
