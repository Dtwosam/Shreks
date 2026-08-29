use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_storage::ShreksDb;

#[path = "../src/bin/shreks-fast-lane-acceptance/report.rs"]
mod report;

use report::FastLaneAcceptanceStore;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-late-conflict-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn acceptance_reports_canonical_identity_that_later_enters_quarantine() {
    let root = unique_test_dir("pump");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute_batch(
            r#"
            INSERT INTO pump_trade_evidence (
                signature, ordinal, provider, slot, observed_at_unix_ms,
                mint, quote_mint, user, is_buy,
                token_amount_raw, sol_amount_raw, quote_amount_raw,
                timestamp_unix_seconds,
                virtual_sol_reserves_raw, virtual_token_reserves_raw,
                real_sol_reserves_raw, real_token_reserves_raw,
                virtual_quote_reserves_raw, real_quote_reserves_raw, ix_name
            ) VALUES (
                'late-conflict', 0, 'chainstack', '500', 1100,
                'mint-a', 'So11111111111111111111111111111111111111112', 'wallet-a', 1,
                '500000000', '2500000000', '2500000000',
                1,
                '32000000000', '900000000000000',
                '10000000000', '600000000000000',
                '32000000000', '10000000000', 'buy'
            );

            INSERT INTO fast_events (
                sequence, signature, ordinal, provider, slot,
                source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
                mint, quote_mint, venue, kind, actor,
                base_quantity, quote_quantity, price_quote,
                base_decimals, quote_decimals
            ) VALUES (
                1, 'late-conflict', 0, 'chainstack', '500',
                1100, 1000, 1200,
                'mint-a', 'So11111111111111111111111111111111111111112',
                'pump_fun_bonding_curve', 'buy', 'wallet-a',
                500.0, 2.5, 0.005,
                6, 9
            );

            INSERT INTO pump_trade_evidence_conflicts (
                signature, ordinal, provider, slot, observed_at_unix_ms,
                mint, quote_mint, user, is_buy,
                token_amount_raw, sol_amount_raw, quote_amount_raw,
                timestamp_unix_seconds,
                virtual_sol_reserves_raw, virtual_token_reserves_raw,
                real_sol_reserves_raw, real_token_reserves_raw,
                virtual_quote_reserves_raw, real_quote_reserves_raw, ix_name
            ) VALUES (
                'late-conflict', 0, 'chainstack', '502', 1300,
                'mint-a', 'So11111111111111111111111111111111111111112', 'wallet-a', 1,
                '500000000', '2500000001', '2500000001',
                1,
                '32000000000', '900000000000000',
                '10000000000', '600000000000000',
                '32000000000', '10000000000', 'buy'
            );
            "#,
        )
        .unwrap();
    drop(connection);

    let store = FastLaneAcceptanceStore::open(&db_path).unwrap();
    let acceptance = store.report(1_000, 2_000).unwrap();
    assert_eq!(acceptance.canonical_events, 1);
    assert_eq!(acceptance.pump_conflict_quarantine_events, 1);
    assert_eq!(acceptance.canonical_conflict_quarantine_violations, 1);

    cleanup_dir(&root);
}
