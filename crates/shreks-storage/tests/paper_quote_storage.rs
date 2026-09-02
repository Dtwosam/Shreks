use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::{
    DiscoveredToken, ProviderId, QuotePurpose, QuoteRequest, QuoteSnapshot, VenueId,
};
use shreks_storage::ShreksDb;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-paper-quote-storage-{label}-{}-{nanos}",
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

fn quote_request(input_mint: &str, output_mint: &str) -> QuoteRequest {
    QuoteRequest::new(input_mint, output_mint, u64::MAX, "Taker111", 75).unwrap()
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
fn paper_quote_purpose_partitions_identity_and_preserves_exact_provenance() {
    let root = unique_test_dir("purpose-identity");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let request = quote_request("Mint111", "So11111111111111111111111111111111111111112");
    let snapshot = quote_snapshot(&request, 3_000);

    db.insert_paper_quote_snapshot(
        candidate_id,
        QuotePurpose::Entry,
        "probe-v1",
        &request,
        &snapshot,
    )
    .unwrap();
    db.insert_paper_quote_snapshot(
        candidate_id,
        QuotePurpose::Entry,
        "probe-v1",
        &request,
        &snapshot,
    )
    .unwrap();
    db.insert_paper_quote_snapshot(
        candidate_id,
        QuotePurpose::Exit,
        "probe-v1",
        &request,
        &snapshot,
    )
    .unwrap();
    drop(db);

    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(reopened.diagnostics().unwrap().schema_version, 15);
    drop(reopened);

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM paper_quote_snapshots WHERE candidate_id = ?1",
            [candidate_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 2);

    let rows = connection
        .prepare(
            r#"SELECT purpose, provider, probe_policy_version, input_mint, output_mint, taker,
                      input_amount, output_amount, minimum_output_amount, slippage_bps,
                      route_available, price_impact_pct, route_labels_json, quoted_at_unix_ms
               FROM paper_quote_snapshots
               WHERE candidate_id = ?1
               ORDER BY purpose ASC"#,
        )
        .unwrap()
        .query_map([candidate_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, String>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
                row.get::<_, i64>(9)?,
                row.get::<_, i64>(10)?,
                row.get::<_, Option<String>>(11)?,
                row.get::<_, String>(12)?,
                row.get::<_, i64>(13)?,
            ))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();

    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "entry");
    assert_eq!(rows[1].0, "exit");
    for row in rows {
        assert_eq!(row.1, "jupiter");
        assert_eq!(row.2, "probe-v1");
        assert_eq!(row.3, "Mint111");
        assert_eq!(row.4, "So11111111111111111111111111111111111111112");
        assert_eq!(row.5, "Taker111");
        assert_eq!(row.6, u64::MAX.to_string());
        assert_eq!(row.7, (u64::MAX - 10).to_string());
        assert_eq!(row.8, (u64::MAX - 20).to_string());
        assert_eq!(row.9, 75);
        assert_eq!(row.10, 1);
        assert_eq!(row.11.as_deref(), Some("0.0125"));
        assert_eq!(row.12, "[\"Ray\\\"X\",\"Line\\nBreak\"]");
        assert_eq!(row.13, 3_000);
    }

    cleanup_dir(&root);
}

#[test]
fn paper_quote_rejects_misattribution_mismatch_and_conflicting_replay() {
    let root = unique_test_dir("invalid");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let request = quote_request("Mint111", "So11111111111111111111111111111111111111112");
    let snapshot = quote_snapshot(&request, 3_000);

    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id,
            QuotePurpose::Entry,
            "   ",
            &request,
            &snapshot,
        )
        .is_err());
    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id + 10_000,
            QuotePurpose::Entry,
            "probe-v1",
            &request,
            &snapshot,
        )
        .is_err());

    let unrelated_request = quote_request("OtherMint", "OtherQuote");
    let unrelated_snapshot = quote_snapshot(&unrelated_request, 3_000);
    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id,
            QuotePurpose::Entry,
            "probe-v1",
            &unrelated_request,
            &unrelated_snapshot,
        )
        .is_err());

    let mut amount_mismatch = snapshot.clone();
    amount_mismatch.input_amount -= 1;
    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id,
            QuotePurpose::Entry,
            "probe-v1",
            &request,
            &amount_mismatch,
        )
        .is_err());

    let mut bad_time = snapshot.clone();
    bad_time.quoted_at_unix_ms = -1;
    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id,
            QuotePurpose::Entry,
            "probe-v1",
            &request,
            &bad_time,
        )
        .is_err());

    db.insert_paper_quote_snapshot(
        candidate_id,
        QuotePurpose::Entry,
        "probe-v1",
        &request,
        &snapshot,
    )
    .unwrap();
    let mut conflict = snapshot.clone();
    conflict.output_amount -= 1;
    assert!(db
        .insert_paper_quote_snapshot(
            candidate_id,
            QuotePurpose::Entry,
            "probe-v1",
            &request,
            &conflict,
        )
        .is_err());

    let connection = Connection::open(&db_path).unwrap();
    let count: i64 = connection
        .query_row("SELECT COUNT(*) FROM paper_quote_snapshots", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(count, 1);

    cleanup_dir(&root);
}

#[test]
fn paper_quote_preserves_explicit_unavailable_route_without_synthesizing_fill_values() {
    let root = unique_test_dir("unavailable");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();
    let candidate_id = db.upsert_candidate(&candidate("Mint111")).unwrap();
    let request = quote_request("So11111111111111111111111111111111111111112", "Mint111");
    let mut snapshot = quote_snapshot(&request, 4_000);
    snapshot.output_amount = 0;
    snapshot.minimum_output_amount = 0;
    snapshot.price_impact_pct = None;
    snapshot.route_labels.clear();
    snapshot.route_available = false;

    db.insert_paper_quote_snapshot(
        candidate_id,
        QuotePurpose::Entry,
        "probe-v1",
        &request,
        &snapshot,
    )
    .unwrap();

    let connection = Connection::open(&db_path).unwrap();
    let row: (i64, String, String, Option<String>) = connection
        .query_row(
            r#"SELECT route_available, output_amount, route_labels_json, price_impact_pct
               FROM paper_quote_snapshots WHERE candidate_id = ?1 AND purpose = 'entry'"#,
            [candidate_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .unwrap();
    assert_eq!(row, (0, "0".to_owned(), "[]".to_owned(), None));

    cleanup_dir(&root);
}
