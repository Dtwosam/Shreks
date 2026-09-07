use std::{
    collections::VecDeque,
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, LifecycleEventKind, PairMarketData, ProviderId, TokenLifecycleEvent,
    TransactionWindow, VenueId,
};
use shreks_providers::{
    DiscoveryProvider, MarketDataProvider, ProviderError, ProviderErrorKind,
};
use shreks_storage::{OutcomeCheckpointStatus, ShreksDb};

#[path = "../src/bin/observer_v2/sampling.rs"]
mod sampling;
#[path = "../src/bin/observer_v2/sampler.rs"]
mod sampler;

use sampler::{HighResolutionSampler, SamplerProvider};
use sampling::SamplingPolicy;

const SECOND: i64 = 1_000;
const MINUTE: i64 = 60 * SECOND;
const HOUR: i64 = 60 * MINUTE;
const DAY: i64 = 24 * HOUR;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-observer-v2-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn discovered(mint: &str, at: i64) -> DiscoveredToken {
    DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: None,
        discovered_at_unix_ms: at,
        source: ProviderId::DexScreener,
    }
}

fn snapshot(
    provider: ProviderId,
    mint: &str,
    pair_address: &str,
    at: i64,
    price: f64,
    liquidity: f64,
) -> PairMarketData {
    PairMarketData {
        provider,
        venue: if provider == ProviderId::Meteora {
            VenueId::MeteoraDlmm
        } else {
            VenueId::PumpSwap
        },
        chain_id: "solana".to_owned(),
        dex_id: provider.as_str().to_owned(),
        pair_address: pair_address.to_owned(),
        base_mint: mint.to_owned(),
        base_name: None,
        base_symbol: None,
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        quote_name: None,
        quote_symbol: None,
        price_native: None,
        price_usd: Some(price.to_string()),
        liquidity_usd: Some(liquidity),
        volume_5m: Some(10_000.0),
        volume_1h: None,
        volume_6h: None,
        volume_24h: None,
        transactions: vec![TransactionWindow {
            window: "m5".to_owned(),
            buys: 20,
            sells: 10,
        }],
        fdv_usd: None,
        market_cap_usd: None,
        pair_created_at_unix_ms: Some(0),
        observed_at_unix_ms: at,
    }
}

fn migration_event(
    signature: &str,
    mint: &str,
    pool: &str,
    detected_at_unix_ms: i64,
) -> TokenLifecycleEvent {
    TokenLifecycleEvent {
        kind: LifecycleEventKind::PumpGraduation,
        provider: ProviderId::SolanaPublic,
        mint: mint.to_owned(),
        quote_mint: "So11111111111111111111111111111111111111112".to_owned(),
        from_venue: VenueId::PumpFunBondingCurve,
        to_venue: VenueId::PumpSwap,
        pool_address: pool.to_owned(),
        signature: signature.to_owned(),
        slot: 1,
        detected_at_unix_ms,
        occurred_at_unix_ms: Some(detected_at_unix_ms),
    }
}

#[derive(Clone)]
struct StaticDiscovery {
    candidates: Vec<DiscoveredToken>,
    calls: Arc<Mutex<usize>>,
}

impl StaticDiscovery {
    fn new(candidates: Vec<DiscoveredToken>) -> Self {
        Self {
            candidates,
            calls: Arc::new(Mutex::new(0)),
        }
    }
}

#[async_trait]
impl DiscoveryProvider for StaticDiscovery {
    fn provider_id(&self) -> ProviderId {
        ProviderId::DexScreener
    }

    async fn discover(&self) -> Result<Vec<DiscoveredToken>, ProviderError> {
        *self.calls.lock().unwrap() += 1;
        Ok(self.candidates.clone())
    }
}

#[derive(Clone)]
struct SequenceMarket {
    provider: ProviderId,
    responses: Arc<Mutex<VecDeque<Result<Vec<PairMarketData>, ProviderError>>>>,
    calls: Arc<Mutex<Vec<String>>>,
}

impl SequenceMarket {
    fn new(
        provider: ProviderId,
        responses: Vec<Result<Vec<PairMarketData>, ProviderError>>,
    ) -> Self {
        Self {
            provider,
            responses: Arc::new(Mutex::new(responses.into())),
            calls: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn call_count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}

#[async_trait]
impl MarketDataProvider for SequenceMarket {
    fn provider_id(&self) -> ProviderId {
        self.provider
    }

    async fn token_pairs(&self, token_mint: &str) -> Result<Vec<PairMarketData>, ProviderError> {
        self.calls.lock().unwrap().push(token_mint.to_owned());
        self.responses
            .lock()
            .unwrap()
            .pop_front()
            .expect("test market response exhausted")
    }
}

fn provider_error(provider: ProviderId) -> ProviderError {
    ProviderError::new(provider, ProviderErrorKind::RateLimited, "test rate limit")
}

fn scalar_i64(db_path: &Path, sql: &str) -> i64 {
    Connection::open(db_path)
        .unwrap()
        .query_row(sql, [], |row| row.get(0))
        .unwrap()
}

fn insert_test_fast_event(
    db_path: &Path,
    sequence: i64,
    mint: &str,
    observed_at_unix_ms: i64,
) {
    let connection = Connection::open(db_path).unwrap();
    let signature = format!("priority-sig-{sequence}");
    let log_index = sequence;
    let ordinal = 2_147_483_648_i64 + log_index;
    connection
        .execute(
            r#"INSERT INTO pump_swap_trade_evidence (
                   signature, ordinal, log_index, provider, slot,
                   observed_at_unix_ms, pool, user, is_buy,
                   base_amount_raw, quote_amount_raw, user_quote_amount_raw,
                   timestamp_unix_seconds, pool_base_reserves_raw,
                   pool_quote_reserves_raw
               ) VALUES (
                   ?1, ?2, ?3, 'solana_public', '1',
                   ?4, 'priority-pool', 'actor', 1,
                   '1000000', '1000000000', '1000000000',
                   ?5, '1000000', '1000000000'
               )"#,
            rusqlite::params![
                signature,
                ordinal,
                log_index,
                observed_at_unix_ms,
                observed_at_unix_ms / 1000,
            ],
        )
        .unwrap();
    connection
        .execute(
            r#"INSERT INTO fast_events (
                   sequence, signature, ordinal, provider, slot,
                   source_observed_at_unix_ms, occurred_at_unix_ms,
                   observed_at_unix_ms, mint, quote_mint, venue, kind,
                   actor, base_quantity, quote_quantity, price_quote,
                   base_decimals, quote_decimals
               ) VALUES (
                   ?1, ?2, ?3, 'solana_public', '1',
                   ?4, ?4, ?4, ?5,
                   'So11111111111111111111111111111111111111112',
                   'pump_swap', 'buy', 'actor', 1.0, 1.0, 1.0, 6, 9
               )"#,
            rusqlite::params![
                sequence,
                signature,
                ordinal,
                observed_at_unix_ms,
                mint,
            ],
        )
        .unwrap();
}

fn candidate_id(db_path: &Path, mint: &str) -> i64 {
    Connection::open(db_path)
        .unwrap()
        .query_row(
            "SELECT id FROM token_candidates WHERE mint = ?1 ORDER BY id LIMIT 1",
            [mint],
            |row| row.get(0),
        )
        .unwrap()
}

#[tokio::test]
async fn active_pumpswap_priority_samples_dex_without_waiting_for_meteora_broad_work() {
    let root = unique_test_dir("active-pumpswap-priority");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered(
        "mint-priority",
        0,
    )]));
    let dex = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-priority",
                "pair-dex-initial",
                0,
                100.0,
                50_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-priority",
                "pair-dex-priority",
                100_000,
                101.0,
                55_000.0,
            )]),
        ],
    ));
    let meteora = Arc::new(SequenceMarket::new(
        ProviderId::Meteora,
        vec![Ok(vec![snapshot(
            ProviderId::Meteora,
            "mint-priority",
            "pair-meteora-initial",
            0,
            100.0,
            60_000.0,
        )])],
    ));

    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![
            SamplerProvider::unpaced(dex.clone()),
            SamplerProvider::unpaced(meteora.clone()),
        ],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let initial = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(initial.sampled_candidate_count, 1);
    assert_eq!(dex.call_count(), 1);
    assert_eq!(meteora.call_count(), 1);

    insert_test_fast_event(&db_path, 1, "mint-priority", 99_000);

    let priority = sampler.run_cycle_at(100_000).await.unwrap();
    assert_eq!(priority.priority_candidate_count, 1);
    assert_eq!(priority.priority_persisted_snapshot_count, 1);
    assert_eq!(priority.sampled_candidate_count, 0);
    assert_eq!(dex.call_count(), 2);
    assert_eq!(meteora.call_count(), 1);
    assert_eq!(
        scalar_i64(
            &db_path,
            "SELECT COUNT(*) FROM market_snapshots
             WHERE source='dexscreener'
               AND base_mint='mint-priority'"
        ),
        2
    );

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn broad_sampling_is_bounded_to_one_due_candidate_per_cycle() {
    let root = unique_test_dir("bounded-broad");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![
        discovered("mint-broad-a", 0),
        discovered("mint-broad-b", 0),
    ]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-broad-a",
                "pair-a",
                0,
                100.0,
                50_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-broad-b",
                "pair-b",
                1,
                100.0,
                50_000.0,
            )]),
        ],
    ));

    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let first = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(sampler.registry().len(), 2);
    assert_eq!(first.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 1);

    let second = sampler.run_cycle_at(1).await.unwrap();
    assert_eq!(second.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 2);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn discovery_is_persisted_scheduled_and_sampled_before_first_checkpoint() {
    let root = unique_test_dir("early-resample");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-a", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-a",
                "pair-a",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-a",
                "pair-a",
                10 * SECOND,
                102.0,
                105_000.0,
            )]),
        ],
    ));

    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let first = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(first.discovered_candidate_count, 1);
    assert_eq!(first.sampled_candidate_count, 1);
    assert_eq!(first.persisted_snapshot_count, 1);
    assert_eq!(market.call_count(), 1);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM candidate_outcome_checkpoints"), 7);

    let second = sampler.run_cycle_at(10 * SECOND).await.unwrap();
    assert_eq!(second.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 2);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM market_snapshots"), 2);
    assert!(10 * SECOND < MINUTE);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn hot_price_path_shortens_next_sampling_interval() {
    let root = unique_test_dir("hot-cadence");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-hot", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-hot",
                "pair-hot",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-hot",
                "pair-hot",
                10 * SECOND,
                400.0,
                120_000.0,
            )]),
        ],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(sampler.registry().candidates()[0].next_due_at_unix_ms, 10 * SECOND);
    sampler.run_cycle_at(10 * SECOND).await.unwrap();
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.high_price_usd, Some(400.0));
    assert_eq!(tracked.next_due_at_unix_ms, 15 * SECOND);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn all_provider_snapshots_are_persisted_and_representative_path_is_deterministic() {
    let root = unique_test_dir("multi-provider");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-multi", 0)]));
    let dex = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-multi",
            "pair-dex",
            0,
            100.0,
            50_000.0,
        )])],
    ));
    let meteora = Arc::new(SequenceMarket::new(
        ProviderId::Meteora,
        vec![Ok(vec![snapshot(
            ProviderId::Meteora,
            "mint-multi",
            "pair-meteora",
            0,
            105.0,
            200_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![
            SamplerProvider::unpaced(dex),
            SamplerProvider::unpaced(meteora),
        ],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(report.persisted_snapshot_count, 2);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM market_snapshots"), 2);
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.first_price_usd, Some(105.0));
    assert_eq!(tracked.high_price_usd, Some(105.0));

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn one_provider_failure_does_not_backoff_when_another_provider_succeeds() {
    let root = unique_test_dir("partial-provider-success");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-partial", 0)]));
    let failing = Arc::new(SequenceMarket::new(
        ProviderId::Meteora,
        vec![Err(provider_error(ProviderId::Meteora))],
    ));
    let working = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-partial",
            "pair-working",
            0,
            100.0,
            100_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![
            SamplerProvider::unpaced(failing),
            SamplerProvider::unpaced(working),
        ],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(0).await.unwrap();
    assert_eq!(report.market_provider_failure_count, 1);
    assert_eq!(report.persisted_snapshot_count, 1);
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.consecutive_failures, 0);
    assert_eq!(tracked.next_due_at_unix_ms, 10 * SECOND);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn all_provider_failure_backs_off_without_deleting_candidate() {
    let root = unique_test_dir("all-provider-failure");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-fail", 0)]));
    let failing = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Err(provider_error(ProviderId::DexScreener))],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(failing)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    let tracked = &sampler.registry().candidates()[0];
    assert_eq!(tracked.consecutive_failures, 1);
    assert_eq!(tracked.next_due_at_unix_ms, 20 * SECOND);
    assert_eq!(sampler.registry().len(), 1);
    assert_eq!(scalar_i64(&db_path, "SELECT COUNT(*) FROM token_candidates"), 1);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn dense_sample_finalizes_existing_a9_checkpoint() {
    let root = unique_test_dir("checkpoint-finalization");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-label", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-label",
                "pair-label",
                0,
                100.0,
                100_000.0,
            )]),
            Ok(vec![snapshot(
                ProviderId::DexScreener,
                "mint-label",
                "pair-label",
                MINUTE,
                120.0,
                110_000.0,
            )]),
        ],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    sampler.run_cycle_at(0).await.unwrap();
    let report = sampler.run_cycle_at(MINUTE).await.unwrap();
    assert_eq!(report.completed_checkpoint_count, 1);

    let id = candidate_id(&db_path, "mint-label");
    let check = ShreksDb::open(&db_path).unwrap()
        .outcome_checkpoints(id)
        .unwrap()
        .into_iter()
        .find(|checkpoint| checkpoint.horizon_seconds == 60)
        .unwrap();
    assert_eq!(check.status, OutcomeCheckpointStatus::Completed);
    assert!((check.return_pct.unwrap() - 20.0).abs() < 1e-9);
    assert!((check.mfe_pct.unwrap() - 20.0).abs() < 1e-9);
    assert_eq!(check.mae_pct.unwrap(), 0.0);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn registry_restoration_resumes_tracking_after_database_reopen() {
    let root = unique_test_dir("restart");
    let db_path = root.join("shreks.db");
    let discovery = Arc::new(StaticDiscovery::new(vec![discovered("mint-restart", 0)]));
    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-restart",
            "pair-restart",
            0,
            100.0,
            100_000.0,
        )])],
    ));
    let mut first = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        Some(discovery),
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();
    first.run_cycle_at(0).await.unwrap();
    assert_eq!(first.registry().len(), 1);
    drop(first);

    let resumed_market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-restart",
            "pair-restart",
            10 * SECOND,
            110.0,
            100_000.0,
        )])],
    ));
    let mut resumed = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(resumed_market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();
    resumed.restore_registry().unwrap();
    assert_eq!(resumed.registry().len(), 1);
    assert_eq!(resumed.registry().candidates()[0].first_price_usd, Some(100.0));
    resumed.run_cycle_at(10 * SECOND).await.unwrap();
    assert_eq!(resumed_market.call_count(), 1);
    assert_eq!(resumed.registry().candidates()[0].high_price_usd, Some(110.0));

    drop(resumed);
    cleanup_dir(&root);
}

#[tokio::test]
async fn verified_migration_bootstraps_missing_dexscreener_candidate_and_samples() {
    let root = unique_test_dir("migration-bootstrap");
    let db_path = root.join("shreks.db");
    let migration_at = 2 * DAY;

    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_migration_signal("sig-bootstrap", 1, migration_at)
        .unwrap();
    let lifecycle = migration_event(
        "sig-bootstrap",
        "mint-bootstrap",
        "pool-bootstrap",
        migration_at,
    );
    db.complete_pump_migration(
        "sig-bootstrap",
        migration_at + 1,
        std::slice::from_ref(&lifecycle),
    )
    .unwrap();
    assert_eq!(
        scalar_i64(
            &db_path,
            "SELECT COUNT(*) FROM token_candidates WHERE mint='mint-bootstrap'"
        ),
        0
    );
    drop(db);

    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-bootstrap",
            "pair-bootstrap",
            migration_at,
            1.0,
            10_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(migration_at).await.unwrap();
    assert_eq!(report.migration_registered_candidate_count, 1);
    assert_eq!(report.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 1);

    let connection = Connection::open(&db_path).unwrap();
    let candidate: (i64, String, Option<String>, String) = connection
        .query_row(
            "SELECT id, discovery_source, venue, pair_address
             FROM token_candidates
             WHERE mint='mint-bootstrap'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(candidate.1, "dexscreener");
    assert_eq!(candidate.2.as_deref(), Some("pump_swap"));
    assert_eq!(candidate.3, "");
    assert_eq!(
        scalar_i64(
            &db_path,
            "SELECT COUNT(*) FROM candidate_outcome_checkpoints
             WHERE candidate_id = (
                 SELECT id FROM token_candidates WHERE mint='mint-bootstrap'
             )"
        ),
        7
    );
    assert_eq!(
        sampler
            .registry()
            .candidate_for_mint("mint-bootstrap")
            .unwrap()
            .candidate_id,
        candidate.0
    );

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn migration_sync_prefers_unique_dexscreener_candidate_without_snapshots() {
    let root = unique_test_dir("migration-ownerless-dex");
    let db_path = root.join("shreks.db");
    let migration_at = 2 * DAY;

    let db = ShreksDb::open(&db_path).unwrap();
    let _chain_candidate = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-ownerless-dex".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: migration_at - HOUR,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
    let dex_candidate = db
        .upsert_candidate(&discovered(
            "mint-ownerless-dex",
            migration_at - MINUTE,
        ))
        .unwrap();

    db.record_pump_migration_signal("sig-ownerless-dex", 1, migration_at)
        .unwrap();
    let lifecycle = migration_event(
        "sig-ownerless-dex",
        "mint-ownerless-dex",
        "pool-ownerless-dex",
        migration_at,
    );
    db.complete_pump_migration(
        "sig-ownerless-dex",
        migration_at + 1,
        std::slice::from_ref(&lifecycle),
    )
    .unwrap();
    drop(db);

    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-ownerless-dex",
            "pair-ownerless-dex",
            migration_at,
            1.0,
            10_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(migration_at).await.unwrap();
    assert_eq!(report.migration_registered_candidate_count, 1);
    let tracked = sampler
        .registry()
        .candidate_for_mint("mint-ownerless-dex")
        .unwrap();
    assert_eq!(tracked.candidate_id, dex_candidate);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn verified_migration_registers_existing_candidate_and_reanchors_sampling() {
    let root = unique_test_dir("migration-register");
    let db_path = root.join("shreks.db");
    let migration_at = 2 * DAY;

    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-migrated".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 0,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
    db.record_pump_migration_signal("sig-migrated", 1, migration_at)
        .unwrap();
    let lifecycle = migration_event(
        "sig-migrated",
        "mint-migrated",
        "pool-migrated",
        migration_at,
    );
    db.complete_pump_migration(
        "sig-migrated",
        migration_at + 1,
        std::slice::from_ref(&lifecycle),
    )
    .unwrap();
    drop(db);

    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-migrated",
            "pair-migrated",
            migration_at,
            1.0,
            10_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(market.clone())],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(migration_at).await.unwrap();
    assert_eq!(report.migration_registered_candidate_count, 1);
    assert_eq!(report.sampled_candidate_count, 1);
    assert_eq!(market.call_count(), 1);

    let tracked = sampler
        .registry()
        .candidate_for_mint("mint-migrated")
        .unwrap();
    assert_eq!(tracked.candidate_id, candidate_id);
    assert_eq!(tracked.discovered_at_unix_ms, migration_at);

    drop(sampler);
    cleanup_dir(&root);
}

#[tokio::test]
async fn migration_sync_prefers_unique_snapshot_owner_for_multi_candidate_mint() {
    let root = unique_test_dir("migration-snapshot-owner");
    let db_path = root.join("shreks.db");
    let migration_at = 10 * MINUTE;

    let db = ShreksDb::open(&db_path).unwrap();
    let _empty_candidate = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-owner".to_owned(),
            pair_address: None,
            dex_id: None,
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 0,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
    let owner_candidate = db
        .upsert_candidate(&discovered("mint-owner", MINUTE))
        .unwrap();
    db.insert_market_snapshot(
        owner_candidate,
        &snapshot(
            ProviderId::DexScreener,
            "mint-owner",
            "pair-owner-old",
            migration_at - SECOND,
            1.0,
            10_000.0,
        ),
    )
    .unwrap();

    db.record_pump_migration_signal("sig-owner", 1, migration_at)
        .unwrap();
    let lifecycle = migration_event(
        "sig-owner",
        "mint-owner",
        "pool-owner",
        migration_at,
    );
    db.complete_pump_migration(
        "sig-owner",
        migration_at + 1,
        std::slice::from_ref(&lifecycle),
    )
    .unwrap();
    drop(db);

    let market = Arc::new(SequenceMarket::new(
        ProviderId::DexScreener,
        vec![Ok(vec![snapshot(
            ProviderId::DexScreener,
            "mint-owner",
            "pair-owner-new",
            migration_at,
            1.1,
            12_000.0,
        )])],
    ));
    let mut sampler = HighResolutionSampler::new(
        ShreksDb::open(&db_path).unwrap(),
        None,
        vec![SamplerProvider::unpaced(market)],
        SamplingPolicy::default_v1(),
    )
    .unwrap();

    let report = sampler.run_cycle_at(migration_at).await.unwrap();
    assert_eq!(report.migration_registered_candidate_count, 1);
    let tracked = sampler.registry().candidate_for_mint("mint-owner").unwrap();
    assert_eq!(tracked.candidate_id, owner_candidate);

    drop(sampler);
    cleanup_dir(&root);
}

