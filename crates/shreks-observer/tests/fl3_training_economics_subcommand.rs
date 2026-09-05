use std::{
    fs,
    path::{Path, PathBuf},
    process::{self, Command},
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FuturePathCompleteness,
    FuturePathCoverage, FuturePathDecision, FuturePathLabel, ProviderId, VenueId,
    FUTURE_PATH_LABEL_VERSION,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb};

const WSOL: &str = "So11111111111111111111111111111111111111112";
const MINT: &str = "mint-training-economics-cli";

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_shreks-observe")
}

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-training-economics-cli-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn seed_database(db_path: &Path, features_path: &Path) {
    let db = ShreksDb::open(db_path).unwrap();
    let raw = PumpTradeEvidenceWrite {
        provider: ProviderId::SolanaPublic,
        signature: "training-economics-cli-decision".to_owned(),
        ordinal: 0,
        slot: 100,
        observed_at_unix_ms: 980,
        mint: MINT.to_owned(),
        quote_mint: WSOL.to_owned(),
        user: "wallet-training-economics-cli".to_owned(),
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
        FastEventId::new(raw.signature.clone(), raw.ordinal).unwrap(),
        1,
        ProviderId::SolanaPublic,
        FastMarketKey::new(MINT, WSOL, VenueId::PumpFunBondingCurve).unwrap(),
        FastEventKind::Buy,
        Some(raw.user.clone()),
        raw.slot,
        1_000,
        1_000,
        2.0,
        0.1,
        0.05,
    )
    .unwrap();
    assert!(db.record_fast_event(&event, raw.observed_at_unix_ms, 6, 9).unwrap());

    let decision = FuturePathDecision::new(
        event.market.clone(),
        event.id.clone(),
        event.sequence,
        event.observed_at_unix_ms,
        event.price_quote,
    )
    .unwrap();
    let label = FuturePathLabel {
        version: FUTURE_PATH_LABEL_VERSION,
        horizon_ms: 250,
        completeness: FuturePathCompleteness::Complete,
        event_count: 0,
        no_trade_events: true,
        endpoint_event_id: None,
        endpoint_observed_at_unix_ms: None,
        endpoint_price_quote: None,
        endpoint_return_bps: None,
        mfe_bps: None,
        mae_bps: None,
        time_to_peak_ms: None,
        time_to_trough_ms: None,
        reversal_occurred: None,
        first_reversal_after_ms: None,
        min_exit_capacity_base: None,
        endpoint_exit_capacity_base: None,
        route_unavailability_observed: None,
        best_cost_adjusted_return_bps: None,
        endpoint_cost_adjusted_return_bps: None,
    };
    db.record_future_path_label(
        &decision,
        FuturePathCoverage::new(2_000, true).unwrap(),
        &label,
    )
    .unwrap();

    db.write_fast_training_feature_jsonl(
        FUTURE_PATH_LABEL_VERSION,
        features_path,
    )
    .unwrap();
}

#[test]
fn training_economics_subcommand_runs_read_only_without_runtime_environment() {
    let root = unique_test_dir("success");
    fs::create_dir_all(&root).unwrap();
    let db_path = root.join("shreks.db");
    let features_path = root.join("features.jsonl");
    let destination = root.join("training-economics");
    seed_database(&db_path, &features_path);

    let before = ShreksDb::open_existing_read_only(&db_path)
        .unwrap()
        .fast_training_future_path_logical_fingerprint_sha256(
            FUTURE_PATH_LABEL_VERSION,
        )
        .unwrap();

    let output = Command::new(binary())
        .env_clear()
        .args([
            "export-training-economics",
            "--database",
            db_path.to_str().unwrap(),
            "--feature-jsonl",
            features_path.to_str().unwrap(),
            "--future-path-label-version",
            "1",
            "--counterfactual-base-quantity",
            "2",
            "--pump-swap-fee-maximum-age-ms",
            "60000",
            "--output",
            destination.to_str().unwrap(),
        ])
        .output()
        .expect("training economics subcommand must launch");

    assert!(
        output.status.success(),
        "training economics subcommand failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("stdout must be UTF-8");
    assert_eq!(
        stdout.lines().count(),
        1,
        "expected one canonical JSON report: {stdout}"
    );
    assert!(stdout.contains(r#""schema_name":"shreks.fast_training_economics_overlay""#));
    assert!(stdout.contains(r#""schema_version":2"#));
    assert!(stdout.contains(r#""row_count":1"#));
    assert!(stdout.contains(r#""unsupported_venue":1"#));

    let mut names = fs::read_dir(&destination)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    names.sort();
    assert_eq!(names, vec!["manifest.json", "rows.jsonl"]);

    let after = ShreksDb::open_existing_read_only(&db_path)
        .unwrap()
        .fast_training_future_path_logical_fingerprint_sha256(
            FUTURE_PATH_LABEL_VERSION,
        )
        .unwrap();
    assert_eq!(before, after);

    cleanup_dir(&root);
}

#[test]
fn training_economics_subcommand_rejects_missing_arguments_before_runtime_config() {
    let output = Command::new(binary())
        .env_clear()
        .args([
            "export-training-economics",
            "--database",
            "/tmp/missing-shreks.db",
        ])
        .output()
        .expect("training economics subcommand must launch");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("feature-jsonl") && stderr.contains("usage:"),
        "unexpected stderr: {stderr}"
    );
}
