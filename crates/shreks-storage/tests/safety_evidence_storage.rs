use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, ProviderId, QuoteRequest, QuoteSnapshot, TokenHolderDistribution, VenueId,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-safety-evidence-storage-{label}-{}-{nanos}",
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
        discovered_at_unix_ms: 100,
        source: ProviderId::Helius,
    }
}

fn holder_distribution(mint: &str, observed_at_unix_ms: i64) -> TokenHolderDistribution {
    TokenHolderDistribution {
        provider: ProviderId::Helius,
        mint: mint.to_owned(),
        last_indexed_slot: u64::MAX,
        observed_at_unix_ms,
        reported_total_accounts: u64::MAX,
        accounts_scanned: 3,
        unique_owners: 2,
        pages_scanned: 1,
        complete: true,
        total_balance_raw: u64::MAX,
        largest_owner: Some("Owner111".to_owned()),
        largest_owner_balance_raw: Some(u64::MAX - 1),
        top_holder_concentration_pct: Some(99.999_999_999),
    }
}

fn quote_request(mint: &str) -> QuoteRequest {
    QuoteRequest::new(
        mint,
        "So11111111111111111111111111111111111111112",
        u64::MAX,
        "Taker111",
        75,
    )
    .unwrap()
}

fn quote_snapshot(request: &QuoteRequest, quoted_at_unix_ms: i64) -> QuoteSnapshot {
    QuoteSnapshot {
        provider: ProviderId::Jupiter,
        input_mint: request.input_mint.clone(),
        output_mint: request.output_mint.clone(),
        input_amount: request.amount,
        output_amount: u64::MAX - 10,
        minimum_output_amount: u64::MAX - 20,
        slippage_bps: request.slippage_bps,
        price_impact_pct: Some("0.0125".to_owned()),
        route_labels: vec!["Ray\"X".to_owned(), "Line\nBreak".to_owned()],
        route_available: true,
        quoted_at_unix_ms,
    }
}

#[test]
fn holder_distribution_persists_full_width_values_incomplete_state_and_restart_identity() {
    let root = unique_test_dir("holder-restart");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();

    let complete = holder_distribution("Mint111", 1_000);
    db.insert_holder_distribution(candidate_id, &complete).unwrap();
    db.insert_holder_distribution(candidate_id, &complete).unwrap();

    let mut incomplete = holder_distribution("Mint111", 2_000);
    incomplete.last_indexed_slot = u64::MAX - 1;
    incomplete.complete = false;
    incomplete.top_holder_concentration_pct = None;
    db.insert_holder_distribution(candidate_id, &incomplete).unwrap();
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.diagnostics().unwrap().schema_version, 11);
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM token_holder_distributions WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 2);

    let complete_row: (String, String, String, String, Option<String>, Option<f64>, i64) = connection
        .query_row(
            r#"SELECT last_indexed_slot, reported_total_accounts, total_balance_raw,
                      largest_owner_balance_raw, largest_owner, top_holder_concentration_pct, complete
               FROM token_holder_distributions
               WHERE candidate_id = ?1 AND observed_at_unix_ms = 1000"#,
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?, row.get(6)?)),
        )
        .unwrap();
    assert_eq!(complete_row.0, u64::MAX.to_string());
    assert_eq!(complete_row.1, u64::MAX.to_string());
    assert_eq!(complete_row.2, u64::MAX.to_string());
    assert_eq!(complete_row.3, (u64::MAX - 1).to_string());
    assert_eq!(complete_row.4.as_deref(), Some("Owner111"));
    assert_eq!(complete_row.5, Some(99.999_999_999));
    assert_eq!(complete_row.6, 1);

    let incomplete_row: (i64, Option<f64>) = connection
        .query_row(
            "SELECT complete, top_holder_concentration_pct FROM token_holder_distributions WHERE candidate_id = ?1 AND observed_at_unix_ms = 2000",
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(incomplete_row, (0, None));

    cleanup_dir(&root);
}

#[test]
fn holder_distribution_rejects_candidate_mismatch_invalid_invariants_and_conflicting_replay() {
    let root = unique_test_dir("holder-invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();

    let mut mismatch = holder_distribution("OtherMint", 1_000);
    assert!(db.insert_holder_distribution(candidate_id, &mismatch).is_err());

    mismatch.mint = "Mint111".to_owned();
    mismatch.observed_at_unix_ms = -1;
    assert!(db.insert_holder_distribution(candidate_id, &mismatch).is_err());

    let mut invalid_pair = holder_distribution("Mint111", 1_000);
    invalid_pair.largest_owner_balance_raw = None;
    assert!(db.insert_holder_distribution(candidate_id, &invalid_pair).is_err());

    let mut invalid_incomplete = holder_distribution("Mint111", 1_000);
    invalid_incomplete.complete = false;
    assert!(db.insert_holder_distribution(candidate_id, &invalid_incomplete).is_err());

    let mut invalid_pct = holder_distribution("Mint111", 1_000);
    invalid_pct.top_holder_concentration_pct = Some(f64::NAN);
    assert!(db.insert_holder_distribution(candidate_id, &invalid_pct).is_err());

    let original = holder_distribution("Mint111", 1_000);
    db.insert_holder_distribution(candidate_id, &original).unwrap();
    let mut conflict = original.clone();
    conflict.total_balance_raw -= 1;
    assert!(db.insert_holder_distribution(candidate_id, &conflict).is_err());

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row("SELECT COUNT(*) FROM token_holder_distributions", [], |row| row.get(0))
        .unwrap();
    assert_eq!(count, 1);

    cleanup_dir(&root);
}

#[test]
fn exit_quote_persists_exact_request_response_provenance_canonical_labels_and_restart_identity() {
    let root = unique_test_dir("quote-restart");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let request = quote_request("Mint111");
    let snapshot = quote_snapshot(&request, 3_000);

    db.insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &snapshot)
        .unwrap();
    db.insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &snapshot)
        .unwrap();
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM exit_quote_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 1);

    let row: (
        String,
        String,
        String,
        String,
        String,
        String,
        String,
        i64,
        i64,
        Option<String>,
        String,
        i64,
    ) = connection
        .query_row(
            r#"SELECT provider, probe_policy_version, input_mint, output_mint, taker,
                      input_amount, output_amount, slippage_bps, route_available,
                      price_impact_pct, route_labels_json, quoted_at_unix_ms
               FROM exit_quote_snapshots
               WHERE candidate_id = ?1"#,
            [candidate_id],
            |row| {
                Ok((
                    row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?,
                    row.get(6)?, row.get(7)?, row.get(8)?, row.get(9)?, row.get(10)?, row.get(11)?,
                ))
            },
        )
        .unwrap();
    assert_eq!(row.0, "jupiter");
    assert_eq!(row.1, "probe-v1");
    assert_eq!(row.2, "Mint111");
    assert_eq!(row.3, "So11111111111111111111111111111111111111112");
    assert_eq!(row.4, "Taker111");
    assert_eq!(row.5, u64::MAX.to_string());
    assert_eq!(row.6, (u64::MAX - 10).to_string());
    assert_eq!(row.7, 75);
    assert_eq!(row.8, 1);
    assert_eq!(row.9.as_deref(), Some("0.0125"));
    assert_eq!(row.10, "[\"Ray\\\"X\",\"Line\\nBreak\"]");
    assert_eq!(row.11, 3_000);

    let minimum_output: String = connection
        .query_row(
            "SELECT minimum_output_amount FROM exit_quote_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(minimum_output, (u64::MAX - 20).to_string());

    cleanup_dir(&root);
}

#[test]
fn exit_quote_rejects_invalid_probe_candidate_or_request_response_mismatch_and_conflicting_replay() {
    let root = unique_test_dir("quote-invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let request = quote_request("Mint111");
    let snapshot = quote_snapshot(&request, 3_000);

    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "   ", &request, &snapshot)
        .is_err());
    assert!(db
        .insert_exit_quote_snapshot(candidate_id + 10_000, "probe-v1", &request, &snapshot)
        .is_err());

    let foreign_request = quote_request("OtherMint");
    let foreign_snapshot = quote_snapshot(&foreign_request, 3_000);
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &foreign_request, &foreign_snapshot)
        .is_err());

    let mut amount_mismatch = snapshot.clone();
    amount_mismatch.input_amount -= 1;
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &amount_mismatch)
        .is_err());

    let mut output_mint_mismatch = snapshot.clone();
    output_mint_mismatch.output_mint = "OtherOutput".to_owned();
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &output_mint_mismatch)
        .is_err());

    let mut slippage_mismatch = snapshot.clone();
    slippage_mismatch.slippage_bps += 1;
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &slippage_mismatch)
        .is_err());

    let mut bad_time = snapshot.clone();
    bad_time.quoted_at_unix_ms = -1;
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &bad_time)
        .is_err());

    let mut bad_impact = snapshot.clone();
    bad_impact.price_impact_pct = Some("NaN".to_owned());
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &bad_impact)
        .is_err());

    db.insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &snapshot)
        .unwrap();
    let mut conflict = snapshot.clone();
    conflict.output_amount -= 1;
    assert!(db
        .insert_exit_quote_snapshot(candidate_id, "probe-v1", &request, &conflict)
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row("SELECT COUNT(*) FROM exit_quote_snapshots", [], |row| row.get(0))
        .unwrap();
    assert_eq!(count, 1);

    cleanup_dir(&root);
}
