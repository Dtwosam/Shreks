use std::{fs, path::PathBuf, process, time::{SystemTime, UNIX_EPOCH}};

#[path = "../src/fast_event_normalizer.rs"]
mod fast_event_normalizer;

use fast_event_normalizer::normalize_pending_pump_trade_evidence_at;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};
use shreks_providers::pump::WRAPPED_SOL_MINT;
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-solana-public-normalizer-{}-{nanos}",
        process::id()
    ))
}

#[test]
fn solana_public_trade_normalizes_without_changing_provenance_or_economics() {
    let root = unique_test_dir();
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let candidate_id = db
        .upsert_candidate(&DiscoveredToken {
            mint: "mint-public".to_owned(),
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms: 1_000,
            source: ProviderId::SolanaPublic,
        })
        .unwrap();
    db.insert_mint_state(
        candidate_id,
        &TokenMintState {
            provider: ProviderId::SolanaPublic,
            mint: "mint-public".to_owned(),
            owner_program: "TokenProgram".to_owned(),
            supply: 1_000_000_000_000,
            decimals: 6,
            mint_authority: None,
            freeze_authority: None,
            slot: 40,
            observed_at_unix_ms: 1_050,
        },
    )
    .unwrap();
    db.record_pump_trade_evidence(&PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "sig-public-canonical".to_owned(),
        ordinal: 0,
        slot: 41,
        observed_at_unix_ms: 1_100,
        mint: "mint-public".to_owned(),
        quote_mint: WRAPPED_SOL_MINT.to_owned(),
        user: "wallet-public".to_owned(),
        is_buy: true,
        token_amount_raw: 500_000_000,
        sol_amount_raw: 2_500_000_000,
        quote_amount_raw: 0,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 32_000_000_000,
        virtual_token_reserves_raw: 900_000_000_000_000,
        real_sol_reserves_raw: 10_000_000_000,
        real_token_reserves_raw: 600_000_000_000_000,
        virtual_quote_reserves_raw: 0,
        real_quote_reserves_raw: 0,
        ix_name: "buy".to_owned(),
    })
    .unwrap();

    let report = normalize_pending_pump_trade_evidence_at(&db, 32, 1_250).unwrap();
    assert_eq!(report.normalized, 1);

    let rows = db
        .fast_events_for_market(
            "mint-public",
            WRAPPED_SOL_MINT,
            VenueId::PumpFunBondingCurve,
        )
        .unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].event.provider, ProviderId::SolanaPublic);
    assert_eq!(rows[0].event.id.signature, "sig-public-canonical");
    assert!((rows[0].event.base_quantity - 500.0).abs() < 1e-12);
    assert!((rows[0].event.quote_quantity - 2.5).abs() < 1e-12);
    assert!((rows[0].event.price_quote - 0.005).abs() < 1e-12);

    drop(db);
    let _ = fs::remove_dir_all(root);
}
