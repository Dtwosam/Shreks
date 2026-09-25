use std::{
    fs,
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

#[path = "../src/bin/shreks-paper-evidence/status.rs"]
mod status;

use status::{
    write_paper_evidence_runtime_status,
    PaperEvidenceRuntimeStatus,
    PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_NAME,
    PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_VERSION,
};

fn temp_status_path(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!(
        "shreks-paper-evidence-status-{label}-{}-{nonce}",
        std::process::id()
    ));
    fs::create_dir_all(&root).unwrap();
    root.join("paper-evidence-status.json")
}

#[test]
fn runtime_status_is_secret_free_canonical_mode_0600_and_atomically_replaceable() {
    let path = temp_status_path("canonical");
    let started = PaperEvidenceRuntimeStatus::started(
        1_000_000,
        60_000,
        900_000,
        540_000,
        500,
    )
    .unwrap();

    write_paper_evidence_runtime_status(&path, &started).unwrap();

    let metadata = fs::metadata(&path).unwrap();
    assert_eq!(metadata.permissions().mode() & 0o777, 0o600);
    let first = fs::read_to_string(&path).unwrap();
    assert!(first.ends_with('\n'));
    assert_eq!(first.lines().count(), 1);

    let document: serde_json::Value = serde_json::from_str(first.trim_end()).unwrap();
    assert_eq!(
        document["schema_name"],
        PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_NAME
    );
    assert_eq!(
        document["schema_version"],
        PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_VERSION
    );
    assert_eq!(document["state"], "STARTED");
    assert_eq!(document["process_started_at_unix_ms"], 1_000_000);
    assert_eq!(document["generated_at_unix_ms"], 1_000_000);
    assert_eq!(document["completed_cycle_count"], 0);
    assert!(document["cycle_as_of_unix_ms"].is_null());
    assert_eq!(document["evidence_cycle_interval_ms"], 60_000);
    assert_eq!(document["mint_state_max_age_ms"], 900_000);
    assert_eq!(document["mint_state_refresh_age_ms"], 540_000);
    assert_eq!(document["provider_failures_last_cycle"], 0);
    assert_eq!(document["helius_requests_attempted"], 0);
    assert_eq!(document["helius_requests_limit"], 500);
    assert_eq!(document["helius_requests_remaining"], 500);
    assert_eq!(document["helius_budget_exhausted"], false);
    assert_eq!(document["observation_authority"], "DERIVED_OPERATIONAL");
    assert_eq!(document["paper_promotion_authority"], "BLOCKED");
    assert_eq!(document["live_authority"], "DISABLED");

    for forbidden in [
        "api_key",
        "secret",
        "provider_url",
        "wallet",
        "mint_address",
        "candidate_mint",
    ] {
        assert!(!first.to_lowercase().contains(forbidden));
    }

    let completed = started
        .completed_cycle(
            1_060_000,
            1,
            1_060_000,
            0,
            7,
            500,
            493,
            false,
            2,
            1,
        )
        .unwrap();
    write_paper_evidence_runtime_status(&path, &completed).unwrap();

    let second = fs::read_to_string(&path).unwrap();
    let document: serde_json::Value = serde_json::from_str(second.trim_end()).unwrap();
    assert_eq!(document["state"], "CYCLE_COMPLETE");
    assert_eq!(document["generated_at_unix_ms"], 1_060_000);
    assert_eq!(document["completed_cycle_count"], 1);
    assert_eq!(document["cycle_as_of_unix_ms"], 1_060_000);
    assert_eq!(document["provider_failures_last_cycle"], 0);
    assert_eq!(document["helius_requests_attempted"], 7);
    assert_eq!(document["helius_requests_remaining"], 493);
    assert_eq!(document["candidates_selected_last_cycle"], 2);
    assert_eq!(document["mint_states_stored_last_cycle"], 1);

    fs::remove_dir_all(path.parent().unwrap()).unwrap();
}

#[test]
fn runtime_status_rejects_inconsistent_budget_and_time() {
    assert!(PaperEvidenceRuntimeStatus::started(
        1_000_000,
        60_000,
        900_000,
        540_000,
        0,
    )
    .is_err());

    let started = PaperEvidenceRuntimeStatus::started(
        1_000_000,
        60_000,
        900_000,
        540_000,
        500,
    )
    .unwrap();

    assert!(started
        .completed_cycle(
            999_999,
            1,
            999_999,
            0,
            1,
            500,
            499,
            false,
            1,
            0,
        )
        .is_err());

    assert!(started
        .completed_cycle(
            1_060_000,
            1,
            1_060_000,
            0,
            501,
            500,
            0,
            true,
            1,
            0,
        )
        .is_err());

    assert!(started
        .completed_cycle(
            1_060_000,
            1,
            1_060_000,
            0,
            7,
            500,
            494,
            false,
            1,
            0,
        )
        .is_err());
}
