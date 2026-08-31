use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use rusqlite::Connection;
use shreks_core::ProviderId;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};

const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-invalid-economics-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn valid_pump_trade(signature: &str) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 500,
        observed_at_unix_ms: 1_780_000_001_000,
        mint: "mint-a".to_owned(),
        quote_mint: WRAPPED_SOL_MINT.to_owned(),
        user: "wallet-a".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1_780_000_000,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    }
}

#[test]
fn pump_runtime_writer_rejects_zero_executed_quantities() {
    let root = unique_test_dir("ingress");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let mut zero_base = valid_pump_trade("zero-base");
    zero_base.token_amount_raw = 0;
    assert!(matches!(
        db.record_pump_trade_evidence(&zero_base),
        Err(StorageError::InvalidData(_))
    ));
    assert!(matches!(
        db.record_pump_trade_evidence_or_quarantine(&zero_base),
        Err(StorageError::InvalidData(_))
    ));

    let mut zero_sol_quote = valid_pump_trade("zero-sol-quote");
    zero_sol_quote.sol_amount_raw = 0;
    assert!(matches!(
        db.record_pump_trade_evidence(&zero_sol_quote),
        Err(StorageError::InvalidData(_))
    ));
    assert!(matches!(
        db.record_pump_trade_evidence_or_quarantine(&zero_sol_quote),
        Err(StorageError::InvalidData(_))
    ));

    let mut zero_token_quote = valid_pump_trade("zero-token-quote");
    zero_token_quote.quote_mint = "quote-mint-a".to_owned();
    zero_token_quote.quote_amount_raw = 0;
    assert!(matches!(
        db.record_pump_trade_evidence(&zero_token_quote),
        Err(StorageError::InvalidData(_))
    ));
    assert!(matches!(
        db.record_pump_trade_evidence_or_quarantine(&zero_token_quote),
        Err(StorageError::InvalidData(_))
    ));

    cleanup_dir(&root);
}

#[test]
fn legacy_zero_economics_row_is_retained_but_excluded_from_canonical_pending_frontier() {
    let root = unique_test_dir("legacy");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let connection = Connection::open(&db_path).unwrap();
    connection
        .execute(
            r#"INSERT INTO pump_trade_evidence (
                   signature, ordinal, provider, slot, observed_at_unix_ms,
                   mint, quote_mint, user, is_buy,
                   token_amount_raw, sol_amount_raw, quote_amount_raw,
                   timestamp_unix_seconds,
                   virtual_sol_reserves_raw, virtual_token_reserves_raw,
                   real_sol_reserves_raw, real_token_reserves_raw,
                   virtual_quote_reserves_raw, real_quote_reserves_raw,
                   ix_name
               ) VALUES (
                   'legacy-zero-quote', 0, 'solana_public', '500', 1780000001000,
                   'mint-a', ?1, 'wallet-a', 1,
                   '500000000', '0', '0',
                   1780000000,
                   '32000000000', '900000000000000',
                   '10000000000', '600000000000000',
                   '0', '0', 'buy'
               )"#,
            [WRAPPED_SOL_MINT],
        )
        .unwrap();
    drop(connection);

    let db = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        db.pump_trade_evidence_for_signature("legacy-zero-quote")
            .unwrap()
            .len(),
        1,
        "legacy raw evidence must remain available for audit"
    );
    assert!(
        db.pending_pump_trade_evidence(10).unwrap().is_empty(),
        "legacy invalid economics must not poison the generic pending frontier"
    );
    assert!(
        db.pending_unambiguous_pump_trade_evidence(10)
            .unwrap()
            .is_empty(),
        "legacy invalid economics must not poison conflict-free normalization"
    );
    assert!(
        db.pending_normalizable_pump_trade_evidence(10)
            .unwrap()
            .is_empty(),
        "legacy invalid economics must not re-enter the ready fallback"
    );

    cleanup_dir(&root);
}
