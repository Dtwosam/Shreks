use std::{
    fs,
    path::{Path, PathBuf},
    process::{self, Command},
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, ProviderId, VenueId,
    FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-fl4-cli";

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_shreks-observe")
}

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fl4-population-cli-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn seed_database(path: &Path) -> u64 {
    let db = ShreksDb::open(path).unwrap();
    let session = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            900,
            54,
            "coverage-start",
        )
        .unwrap();
    let session = db
        .extend_fast_realtime_coverage_session(
            session.session_id,
            ProviderId::SolanaPublic,
            1,
            1_700,
            56,
            "coverage-end",
        )
        .unwrap();
    db.begin_fast_realtime_coverage_session(
        ProviderId::SolanaPublic,
        2,
        1_800,
        57,
        "coverage-latest",
    )
    .unwrap();

    let raw = PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "decision-cli".to_owned(),
        ordinal: 0,
        slot: 55,
        observed_at_unix_ms: 950,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-cli".to_owned(),
        is_buy: true,
        token_amount_raw: 2_000_000,
        sol_amount_raw: 100_000_000,
        quote_amount_raw: 100_000_000,
        timestamp_unix_seconds: 1,
        virtual_sol_reserves_raw: 10_000_000_000,
        virtual_token_reserves_raw: 20_000_000_000,
        real_sol_reserves_raw: 5_000_000_000,
        real_token_reserves_raw: 10_000_000_000,
        virtual_quote_reserves_raw: 10_000_000_000,
        real_quote_reserves_raw: 5_000_000_000,
        ix_name: "buy".to_owned(),
    };
    assert!(db.record_pump_trade_evidence(&raw).unwrap());
    let event = FastEvent::new(
        FastEventId::new("decision-cli", 0).unwrap(),
        1,
        ProviderId::SolanaPublic,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some("wallet-cli".to_owned()),
        55,
        1_000,
        1_000,
        2.0,
        0.1,
        0.05,
    )
    .unwrap();
    assert!(db.record_fast_event(&event, 950, 6, 9).unwrap());

    session.session_id
}

#[test]
fn population_subcommand_runs_without_runtime_provider_environment_and_prints_json() {
    let root = unique_test_dir("success");
    let db_path = root.join("shreks.db");
    let coverage_session_id = seed_database(&db_path);

    let output = Command::new(binary())
        .env_clear()
        .args([
            "populate-future-path-labels",
            "--database",
            db_path.to_str().unwrap(),
            "--coverage-session-id",
            &coverage_session_id.to_string(),
            "--from-observed-at-unix-ms",
            "1000",
            "--through-observed-at-unix-ms",
            "1000",
            "--maximum-decisions",
            "1",
        ])
        .output()
        .expect("population subcommand must launch");

    assert!(
        output.status.success(),
        "population subcommand failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("stdout must be UTF-8");
    assert_eq!(stdout.lines().count(), 1, "expected one JSON report: {stdout}");
    assert!(stdout.contains(r#""schema_name":"shreks.fast_covered_future_path_population""#));
    assert!(stdout.contains(r#""schema_version":1"#));
    assert!(stdout.contains(r#""decision_count":1"#));
    assert!(stdout.contains(r#""inserted_label_count":12"#));

    let db = ShreksDb::open(&db_path).unwrap();
    let rows = db
        .future_path_labels_for_decision("decision-cli", 0, FUTURE_PATH_LABEL_VERSION)
        .unwrap();
    assert_eq!(rows.len(), 12);

    cleanup_dir(&root);
}

#[test]
fn population_subcommand_rejects_missing_named_arguments_before_runtime_config() {
    let output = Command::new(binary())
        .env_clear()
        .args(["populate-future-path-labels", "--database", "/tmp/missing.db"])
        .output()
        .expect("population subcommand must launch");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("coverage-session-id") && stderr.contains("usage:"),
        "unexpected stderr: {stderr}"
    );
}
