use std::{
    fs,
    path::{Path, PathBuf},
    process,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

use async_trait::async_trait;
use shreks_core::{ProviderId, TokenMintState};
use shreks_observer::Observer;
use shreks_providers::{pump_quote::SYSTEM_SOL_QUOTE_MINT, ChainDataProvider, ProviderError};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const MINT: &str = "HydrateMint11111111111111111111111111111111";
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

fn raw_trade(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 42,
        observed_at_unix_ms: OBSERVED_MS,
        mint: MINT.to_owned(),
        quote_mint: SYSTEM_SOL_QUOTE_MINT.to_owned(),
        user: "user-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 2_500_000_000,
        timestamp_unix_seconds: OBSERVED_MS / 1_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 32_000_000_000,
        real_quote_reserves_raw: 10_000_000_000,
        ix_name: "buy".to_owned(),
    }
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
            observed_at_unix_ms: OBSERVED_MS + 100,
        })
    }
}

#[tokio::test]
async fn raw_fast_lane_mint_without_state_is_hydrated_once_from_public_solana() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    db.record_pump_trade_evidence(&raw_trade("sig-hydrate"))
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
