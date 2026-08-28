use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::{self, Command},
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_storage::ShreksDb;

const MAIN_SOURCE: &str = include_str!("../src/bin/shreks-fast-lane-acceptance/main.rs");
const REPORT_SOURCE: &str = include_str!("../src/bin/shreks-fast-lane-acceptance/report.rs");

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-acceptance-binary-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_shreks-fast-lane-acceptance")
}

#[test]
fn cli_requires_exactly_database_start_and_as_of_arguments() {
    let no_args = Command::new(binary()).output().unwrap();
    assert!(!no_args.status.success());

    let too_many = Command::new(binary())
        .args(["db", "0", "1000", "extra"])
        .output()
        .unwrap();
    assert!(!too_many.status.success());

    let invalid_timestamp = Command::new(binary())
        .args(["db", "not-a-number", "1000"])
        .output()
        .unwrap();
    assert!(!invalid_timestamp.status.success());
}

#[test]
fn empty_schema_twelve_database_emits_stable_key_value_contract() {
    let root = unique_test_dir("output");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let output = Command::new(binary())
        .arg(&db_path)
        .args(["0", "1000"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "acceptance binary failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());

    let stdout = String::from_utf8(output.stdout).unwrap();
    let lines = stdout.lines().collect::<Vec<_>>();
    let expected_keys = [
        "window_start_unix_ms",
        "as_of_unix_ms",
        "window_duration_ms",
        "database_bytes",
        "wal_bytes",
        "pump_raw_events",
        "pumpswap_raw_events",
        "canonical_events",
        "pending_pump_events",
        "pending_pumpswap_events",
        "sequence_integrity_violations",
        "source_latency_samples",
        "source_latency_p50_ms",
        "source_latency_p95_ms",
        "source_latency_p99_ms",
        "source_latency_max_ms",
        "normalization_latency_samples",
        "normalization_latency_p50_ms",
        "normalization_latency_p95_ms",
        "normalization_latency_p99_ms",
        "normalization_latency_max_ms",
        "end_to_end_latency_samples",
        "end_to_end_latency_p50_ms",
        "end_to_end_latency_p95_ms",
        "end_to_end_latency_p99_ms",
        "end_to_end_latency_max_ms",
    ];
    assert_eq!(lines.len(), expected_keys.len());

    let mut parsed = BTreeMap::new();
    for (line, expected_key) in lines.iter().zip(expected_keys) {
        let (key, value) = line
            .split_once('=')
            .expect("every acceptance output line must be key=value");
        assert_eq!(key, expected_key, "output key order must remain stable");
        assert!(parsed.insert(key, value).is_none(), "output keys must be unique");
    }

    assert_eq!(parsed["window_start_unix_ms"], "0");
    assert_eq!(parsed["as_of_unix_ms"], "1000");
    assert_eq!(parsed["window_duration_ms"], "1000");
    assert_eq!(parsed["pump_raw_events"], "0");
    assert_eq!(parsed["pumpswap_raw_events"], "0");
    assert_eq!(parsed["canonical_events"], "0");
    assert_eq!(parsed["pending_pump_events"], "0");
    assert_eq!(parsed["pending_pumpswap_events"], "0");
    assert_eq!(parsed["sequence_integrity_violations"], "0");
    assert_eq!(parsed["source_latency_samples"], "0");
    assert_eq!(parsed["source_latency_p50_ms"], "none");
    assert_eq!(parsed["source_latency_p95_ms"], "none");
    assert_eq!(parsed["source_latency_p99_ms"], "none");
    assert_eq!(parsed["source_latency_max_ms"], "none");
    assert_eq!(parsed["normalization_latency_samples"], "0");
    assert_eq!(parsed["normalization_latency_p50_ms"], "none");
    assert_eq!(parsed["normalization_latency_p95_ms"], "none");
    assert_eq!(parsed["normalization_latency_p99_ms"], "none");
    assert_eq!(parsed["normalization_latency_max_ms"], "none");
    assert_eq!(parsed["end_to_end_latency_samples"], "0");
    assert_eq!(parsed["end_to_end_latency_p50_ms"], "none");
    assert_eq!(parsed["end_to_end_latency_p95_ms"], "none");
    assert_eq!(parsed["end_to_end_latency_p99_ms"], "none");
    assert_eq!(parsed["end_to_end_latency_max_ms"], "none");
    assert!(parsed["database_bytes"].parse::<u64>().unwrap() > 0);
    parsed["wal_bytes"].parse::<u64>().unwrap();

    cleanup_dir(&root);
}

#[test]
fn acceptance_binary_source_has_no_provider_or_capital_authority() {
    assert!(MAIN_SOURCE.contains("FastLaneAcceptanceStore::open"));
    assert!(MAIN_SOURCE.contains("report("));
    assert!(MAIN_SOURCE.contains("std::env::args_os"));

    let combined = format!("{MAIN_SOURCE}\n{REPORT_SOURCE}");
    for forbidden in [
        "shreks_providers::",
        "ShreksDb::open",
        "TradeIntent",
        "RuntimeMode::Live",
        "RuntimeMode::Paper",
        "send_transaction",
        "reqwest::",
        "tokio_tungstenite",
        "wallet::",
        "signing_key",
    ] {
        assert!(
            !combined.contains(forbidden),
            "read-only FL1.5 acceptance must not gain authority via {forbidden}"
        );
    }

    assert!(
        REPORT_SOURCE.contains("OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX"),
        "acceptance reporter must keep the proven read-only SQLite boundary"
    );
}
