use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const OBSERVED_MS: i64 = 1_788_193_719_960;

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-metadata-debt-{label}-{}-{nanos}",
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
        quote_mint: SYSTEM_SOL_MINT.to_owned(),
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

fn mark_mint_hydrated(db: &ShreksDb, mint: &str) {
    let candidate = DiscoveredToken {
        mint: mint.to_owned(),
        pair_address: None,
        dex_id: None,
        venue: Some(VenueId::PumpFunBondingCurve),
        discovered_at_unix_ms: OBSERVED_MS,
        source: ProviderId::SolanaPublic,
    };
    let candidate_id = db.upsert_candidate(&candidate).unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: mint.to_owned(),
            owner_program: "Tokenkeg1111111111111111111111111111111111".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 43,
            observed_at_unix_ms: OBSERVED_MS + 1,
        },
    )
    .unwrap();
}

#[test]
fn selector_pages_past_resolved_oldest_chunk_to_find_metadata_debt() {
    let root = unique_test_dir("pagination");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let resolved_old_mint = "HydrateResolvedOld1111111111111111111111111111";
    for index in 0..2048_i64 {
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-resolved-old-{index:04}"),
            resolved_old_mint,
            OBSERVED_MS + index,
        ))
        .unwrap();
    }
    mark_mint_hydrated(&db, resolved_old_mint);

    let debt_a = "HydratePagedDebtA111111111111111111111111111111";
    let debt_b = "HydratePagedDebtB111111111111111111111111111111";
    db.record_pump_trade_evidence(&raw_trade(
        "sig-paged-debt-a",
        debt_a,
        OBSERVED_MS + 3_000,
    ))
    .unwrap();
    db.record_pump_trade_evidence(&raw_trade(
        "sig-paged-debt-b",
        debt_b,
        OBSERVED_MS + 3_001,
    ))
    .unwrap();

    let mut newest = Vec::new();
    for index in 0..2050_i64 {
        let mint = format!("HydratePagedFresh{index:04}1111111111111111111111");
        db.record_pump_trade_evidence(&raw_trade(
            &format!("sig-paged-fresh-{index:04}"),
            &mint,
            OBSERVED_MS + 10_000 + index,
        ))
        .unwrap();
        newest.push(mint);
    }

    let selected = db.fast_lane_mints_missing_state(8).unwrap();
    let selected_mints = selected
        .into_iter()
        .map(|candidate| candidate.mint)
        .collect::<Vec<_>>();

    let mut expected = newest.iter().rev().take(6).cloned().collect::<Vec<_>>();
    expected.push(debt_a.to_owned());
    expected.push(debt_b.to_owned());
    assert_eq!(selected_mints, expected);

    cleanup_dir(&root);
}
