use std::{fs, path::{Path, PathBuf}, process, time::{SystemTime, UNIX_EPOCH}};

use shreks_core::{DiscoveredToken, ProviderId, TokenHolderDistribution};
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-paper-evidence/candidate_store.rs"]
mod candidate_store;

use candidate_store::EvidenceCandidateStore;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("shreks-holder-freshness-{}-{nanos}", process::id()))
}

fn cleanup(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn holder_freshness_uses_durable_observation_timestamp() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "MintFresh".to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: None,
            discovered_at_unix_ms: 100,
            source: ProviderId::Helius,
        })
        .unwrap();
    db.insert_holder_distribution(
        candidate_id,
        &TokenHolderDistribution {
            provider: ProviderId::Helius,
            mint: "MintFresh".to_owned(),
            last_indexed_slot: 123,
            observed_at_unix_ms: 10_000,
            reported_total_accounts: 2,
            accounts_scanned: 2,
            unique_owners: 2,
            pages_scanned: 1,
            complete: true,
            total_balance_raw: 1_000,
            largest_owner: Some("Owner111".to_owned()),
            largest_owner_balance_raw: Some(600),
            top_holder_concentration_pct: Some(60.0),
        },
    )
    .unwrap();
    drop(db);

    let store = EvidenceCandidateStore::open(&db_path).unwrap();
    assert!(store
        .has_holder_distribution_since(candidate_id, 9_500, 10_000)
        .unwrap());
    assert!(store
        .has_holder_distribution_since(candidate_id, 10_000, 10_000)
        .unwrap());
    assert!(!store
        .has_holder_distribution_since(candidate_id, 10_001, 11_000)
        .unwrap());
    assert!(!store
        .has_holder_distribution_since(candidate_id + 1, 0, 10_000)
        .unwrap());

    cleanup(&root);
}

#[test]
fn holder_freshness_rejects_invalid_time_window() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    ShreksDb::open(&db_path).unwrap();
    let store = EvidenceCandidateStore::open(&db_path).unwrap();

    for (minimum, as_of) in [(-1, 10_000), (10_001, 10_000), (0, -1)] {
        assert!(store
            .has_holder_distribution_since(1, minimum, as_of)
            .is_err());
    }

    cleanup(&root);
}
