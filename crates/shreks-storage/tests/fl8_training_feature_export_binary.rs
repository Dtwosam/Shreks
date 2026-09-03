use std::{fs, path::{Path, PathBuf}, process::{self, Command}, time::{SystemTime, UNIX_EPOCH}};

use shreks_storage::ShreksDb;

const BINARY_SOURCE: &str = include_str!("../src/bin/export_fast_training_features.rs");

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("shreks-fl8-export-bin-{label}-{}-{nanos}", process::id()))
}

fn cleanup_dir(path: &Path) { let _ = fs::remove_dir_all(path); }

#[test]
fn export_binary_has_no_provider_signer_trade_or_live_authority() {
    for forbidden in [
        "shreks_providers::",
        "TradeIntent",
        "send_transaction",
        "Signer",
        "private_key",
        "RuntimeMode::Live",
        "ShreksDb::open(",
    ] {
        assert!(!BINARY_SOURCE.contains(forbidden), "read-only FL8.1 exporter gained forbidden authority via {forbidden}");
    }
    assert!(BINARY_SOURCE.contains("open_existing_read_only"));
}

#[test]
fn export_binary_requires_exact_input_and_output_arguments() {
    let status = Command::new(env!("CARGO_BIN_EXE_export_fast_training_features"))
        .status()
        .unwrap();
    assert!(!status.success());
}

#[test]
fn export_binary_missing_database_fails_without_creating_output() {
    let root = unique_test_dir("missing");
    fs::create_dir_all(&root).unwrap();
    let input = root.join("missing.db");
    let output = root.join("features.jsonl");
    let status = Command::new(env!("CARGO_BIN_EXE_export_fast_training_features"))
        .arg(&input)
        .arg(&output)
        .status()
        .unwrap();
    assert!(!status.success());
    assert!(!input.exists());
    assert!(!output.exists());
    cleanup_dir(&root);
}

#[test]
fn export_binary_refuses_existing_output_without_mutating_it() {
    let root = unique_test_dir("collision");
    fs::create_dir_all(&root).unwrap();
    let input = root.join("shreks.db");
    let output = root.join("features.jsonl");
    let db = ShreksDb::open(&input).unwrap();
    drop(db);
    fs::write(&output, b"immutable-existing\n").unwrap();

    let status = Command::new(env!("CARGO_BIN_EXE_export_fast_training_features"))
        .arg(&input)
        .arg(&output)
        .status()
        .unwrap();
    assert!(!status.success());
    assert_eq!(fs::read(&output).unwrap(), b"immutable-existing\n");
    cleanup_dir(&root);
}
