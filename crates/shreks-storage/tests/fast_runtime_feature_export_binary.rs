use std::{
    fs,
    path::{Path, PathBuf},
    process::{self, Command},
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_storage::ShreksDb;

const BINARY_SOURCE: &str = include_str!("../src/bin/export_fast_runtime_features.rs");

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-runtime-export-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn runtime_feature_export_binary_has_read_only_feature_authority_only() {
    for forbidden in [
        "shreks_providers::",
        "TradeIntent",
        "PaperLedger",
        "send_transaction",
        "Signer",
        "private_key",
        "RuntimeMode::Live",
        "fast_future_path_labels",
        "record_future_path_label",
        "score_candidate",
        "decide_entry",
        "ShreksDb::open(",
    ] {
        assert!(
            !BINARY_SOURCE.contains(forbidden),
            "runtime feature exporter gained forbidden authority via {forbidden}"
        );
    }
    assert!(BINARY_SOURCE.contains("open_existing_read_only"));
    assert!(BINARY_SOURCE.contains("fast_runtime_feature_batch"));
}

#[test]
fn runtime_feature_export_binary_requires_exact_argument_shape() {
    let status = Command::new(env!("CARGO_BIN_EXE_export_fast_runtime_features"))
        .status()
        .unwrap();
    assert!(!status.success());
}

#[test]
fn runtime_feature_export_missing_database_fails_without_creating_it() {
    let root = unique_test_dir("missing");
    fs::create_dir_all(&root).unwrap();
    let input = root.join("missing.db");

    let output = Command::new(env!("CARGO_BIN_EXE_export_fast_runtime_features"))
        .arg(&input)
        .arg("10")
        .output()
        .unwrap();

    assert!(!output.status.success());
    assert!(!input.exists());
    assert!(output.stdout.is_empty());
    cleanup_dir(&root);
}

#[test]
fn runtime_feature_export_accepts_empty_current_schema_database_read_only() {
    let root = unique_test_dir("empty");
    fs::create_dir_all(&root).unwrap();
    let input = root.join("shreks.db");
    let db = ShreksDb::open(&input).unwrap();
    drop(db);

    let before = fs::read(&input).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_export_fast_runtime_features"))
        .arg(&input)
        .arg("10")
        .output()
        .unwrap();

    assert!(
        output.status.success(),
        "runtime feature exporter failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(fs::read(&input).unwrap(), before);
    assert!(output.stderr.is_empty());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains(r#""records":[]"#));
    assert!(stdout.ends_with('\n'));

    cleanup_dir(&root);
}
