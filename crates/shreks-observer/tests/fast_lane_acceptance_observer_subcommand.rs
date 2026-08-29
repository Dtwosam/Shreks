use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    process::{self, Command},
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_storage::ShreksDb;

const OBSERVER_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");
const REPORT_SOURCE: &str = include_str!("../src/bin/shreks-fast-lane-acceptance/report.rs");

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-observer-subcommand-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn observer_binary() -> &'static str {
    env!("CARGO_BIN_EXE_shreks-observe")
}

fn acceptance_command() -> Command {
    let mut command = Command::new(observer_binary());
    command
        .env_clear()
        // The legacy observer path must fail immediately on this value. The
        // acceptance subcommand is required to dispatch before runtime config.
        .env("SHREKS_OBSERVER_INTERVAL_SECONDS", "0");
    command
}

#[test]
fn acceptance_dispatch_precedes_runtime_and_provider_configuration() {
    let dispatch = OBSERVER_SOURCE
        .find("run_fast_lane_acceptance_subcommand_if_requested")
        .expect("observer must expose the Fast Lane acceptance subcommand");
    let runtime_config = OBSERVER_SOURCE
        .find("ObserverRuntimeConfig::from_env")
        .expect("observer runtime config load must remain explicit");

    assert!(
        dispatch < runtime_config,
        "read-only acceptance dispatch must happen before runtime/provider configuration"
    );
    assert!(
        REPORT_SOURCE.contains(
            "OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX"
        ),
        "shared acceptance report must keep the proven read-only SQLite boundary"
    );
}

#[test]
fn observer_acceptance_subcommand_emits_the_stable_report_without_valid_runtime_env() {
    let root = unique_test_dir("output");
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let output = acceptance_command()
        .arg("fast-lane-acceptance")
        .arg(&db_path)
        .args(["0", "1000"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "observer acceptance subcommand failed: {}",
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
        "pump_conflict_quarantine_total",
        "pumpswap_conflict_quarantine_total",
        "pump_conflict_quarantine_events",
        "pumpswap_conflict_quarantine_events",
        "canonical_conflict_quarantine_violations",
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
    assert_eq!(parsed["pump_conflict_quarantine_total"], "0");
    assert_eq!(parsed["pumpswap_conflict_quarantine_total"], "0");
    assert_eq!(parsed["pump_conflict_quarantine_events"], "0");
    assert_eq!(parsed["pumpswap_conflict_quarantine_events"], "0");
    assert_eq!(parsed["canonical_conflict_quarantine_violations"], "0");
    assert_eq!(parsed["sequence_integrity_violations"], "0");
    assert_eq!(parsed["source_latency_samples"], "0");
    assert_eq!(parsed["normalization_latency_samples"], "0");
    assert_eq!(parsed["end_to_end_latency_samples"], "0");

    cleanup_dir(&root);
}

#[test]
fn observer_acceptance_subcommand_fails_closed_on_bad_arguments() {
    for args in [
        vec!["fast-lane-acceptance"],
        vec!["fast-lane-acceptance", "db", "0"],
        vec!["fast-lane-acceptance", "db", "not-a-number", "1000"],
        vec!["fast-lane-acceptance", "db", "0", "1000", "extra"],
    ] {
        let output = acceptance_command().args(args).output().unwrap();
        assert!(!output.status.success());
    }
}
