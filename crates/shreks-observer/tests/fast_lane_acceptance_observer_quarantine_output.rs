use std::{fs, path::PathBuf, process::{self, Command}, time::{SystemTime, UNIX_EPOCH}};

use shreks_storage::ShreksDb;

fn unique_test_dir() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-lane-observer-quarantine-output-{}-{nanos}",
        process::id()
    ))
}

#[test]
fn observer_acceptance_subcommand_prints_quarantine_integrity_fields() {
    let root = unique_test_dir();
    let db_path = root.join("shreks.db");
    drop(ShreksDb::open(&db_path).unwrap());

    let output = Command::new(env!("CARGO_BIN_EXE_shreks-observe"))
        .env_clear()
        .env("SHREKS_OBSERVER_INTERVAL_SECONDS", "0")
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

    let stdout = String::from_utf8(output.stdout).unwrap();
    for expected in [
        "pump_conflict_quarantine_total=0",
        "pumpswap_conflict_quarantine_total=0",
        "pump_conflict_quarantine_events=0",
        "pumpswap_conflict_quarantine_events=0",
        "canonical_conflict_quarantine_violations=0",
    ] {
        assert!(
            stdout.lines().any(|line| line == expected),
            "observer acceptance subcommand missing stable field: {expected}\nstdout:\n{stdout}"
        );
    }

    let _ = fs::remove_dir_all(root);
}
