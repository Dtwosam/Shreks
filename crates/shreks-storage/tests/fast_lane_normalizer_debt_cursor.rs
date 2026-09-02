use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{
    pump_swap_event_ordinal, PumpSwapTradeEvidenceWrite, PumpTradeEvidenceWrite, ShreksDb,
};

const SOL: &str = "So11111111111111111111111111111111111111112";

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-normalizer-debt-cursor-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn pump(signature: &str, observed_at_unix_ms: i64) -> PumpTradeEvidenceWrite {
    PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: 0,
        slot: 1,
        observed_at_unix_ms,
        mint: format!("mint-{signature}"),
        quote_mint: SOL.to_owned(),
        user: "user".to_owned(),
        is_buy: true,
        token_amount_raw: 1,
        sol_amount_raw: 1,
        quote_amount_raw: 1,
        timestamp_unix_seconds: observed_at_unix_ms / 1000,
        virtual_sol_reserves_raw: 1,
        virtual_token_reserves_raw: 1,
        real_sol_reserves_raw: 1,
        real_token_reserves_raw: 1,
        virtual_quote_reserves_raw: 1,
        real_quote_reserves_raw: 1,
        ix_name: "trade".to_owned(),
    }
}

fn pumpswap(signature: &str, observed_at_unix_ms: i64, log_index: u32) -> PumpSwapTradeEvidenceWrite {
    PumpSwapTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: signature.to_owned(),
        ordinal: pump_swap_event_ordinal(log_index).unwrap(),
        log_index,
        slot: 1,
        observed_at_unix_ms,
        pool: "pool-a".to_owned(),
        user: "user".to_owned(),
        is_buy: true,
        base_amount_raw: 1,
        quote_amount_raw: 1,
        user_quote_amount_raw: 1,
        timestamp_unix_seconds: observed_at_unix_ms / 1000,
        pool_base_reserves_raw: 1,
        pool_quote_reserves_raw: 1,
    }
}

#[test]
fn normalizer_debt_pages_advance_durable_keyset_cursors_across_reopen() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    for i in 0..6 {
        db.record_pump_trade_evidence(&pump(&format!("pump-{i}"), 1_000 + i))
            .unwrap();
        db.record_pump_swap_trade_evidence(&pumpswap(
            &format!("swap-{i}"),
            2_000 + i,
            i as u32,
        ))
        .unwrap();
    }

    let pump_first = db.paged_normalizer_pump_debt_evidence(2).unwrap();
    assert_eq!(
        pump_first
            .iter()
            .map(|row| row.signature.as_str())
            .collect::<Vec<_>>(),
        vec!["pump-0", "pump-1"]
    );

    let swap_first = db.paged_normalizer_pumpswap_debt_evidence(2).unwrap();
    assert_eq!(
        swap_first
            .iter()
            .map(|row| row.signature.as_str())
            .collect::<Vec<_>>(),
        vec!["swap-0", "swap-1"]
    );

    drop(db);
    let reopened = ShreksDb::open(&db_path).unwrap();

    let pump_second = reopened.paged_normalizer_pump_debt_evidence(2).unwrap();
    assert_eq!(
        pump_second
            .iter()
            .map(|row| row.signature.as_str())
            .collect::<Vec<_>>(),
        vec!["pump-2", "pump-3"]
    );

    let swap_second = reopened.paged_normalizer_pumpswap_debt_evidence(2).unwrap();
    assert_eq!(
        swap_second
            .iter()
            .map(|row| row.signature.as_str())
            .collect::<Vec<_>>(),
        vec!["swap-2", "swap-3"]
    );

    drop(reopened);
    cleanup_dir(&root);
}
