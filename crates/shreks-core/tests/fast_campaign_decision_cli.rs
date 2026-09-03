use std::{fs, process::Command};

const CHAMPION_JSON: &str = include_str!("fixtures/fl9_campaign_champion.json");
const REQUEST_JSON: &str = include_str!("fixtures/fl9_campaign_decision_request.json");
const EXPECTED_RESULTS_JSON: &str = include_str!("fixtures/fl9_campaign_decision_results.json");

#[test]
fn campaign_decision_binary_exists_and_fails_closed_without_required_paths() {
    let binary = env!("CARGO_BIN_EXE_shreks-fast-campaign-decision");
    let output = Command::new(binary).output().unwrap();
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("champion") || stderr.contains("request") || stderr.contains("usage"));
}

#[test]
fn campaign_decision_binary_is_deterministic_and_emits_fingerprint_valid_buy_result() {
    let binary = env!("CARGO_BIN_EXE_shreks-fast-campaign-decision");
    let temp = std::env::temp_dir();
    let process_id = std::process::id();
    let champion_path = temp.join(format!("shreks-fl9-campaign-{process_id}-champion.json"));
    let request_path = temp.join(format!("shreks-fl9-campaign-{process_id}-request.json"));
    fs::write(&champion_path, CHAMPION_JSON).unwrap();
    fs::write(&request_path, REQUEST_JSON).unwrap();

    let first = Command::new(binary)
        .arg(&champion_path)
        .arg(&request_path)
        .output()
        .unwrap();
    assert!(first.status.success(), "{}", String::from_utf8_lossy(&first.stderr));
    assert!(first.stderr.is_empty());
    assert!(!first.stdout.ends_with(b"\n"));

    let second = Command::new(binary)
        .arg(&champion_path)
        .arg(&request_path)
        .output()
        .unwrap();
    assert!(second.status.success(), "{}", String::from_utf8_lossy(&second.stderr));
    assert_eq!(first.stdout, second.stdout);
    assert_eq!(first.stdout, EXPECTED_RESULTS_JSON.as_bytes());

    let document: serde_json::Value = serde_json::from_slice(&first.stdout).unwrap();
    assert_eq!(
        document["schema_name"],
        "shreks.fast_campaign_decision_results"
    );
    assert_eq!(document["schema_version"], 1);
    assert_eq!(document["champion_version"], "fl9-campaign-cli-fixture-v1");
    assert_eq!(
        document["champion_fingerprint_sha256"],
        "a5cd91e4053175465ee7512f8c2882c37ab82c05a5bf3c92fbfb6115dfa03efb"
    );
    assert_eq!(document["decisions"].as_array().unwrap().len(), 1);
    assert_eq!(document["decisions"][0]["source_event_id"], "sig-cli:0");
    assert_eq!(document["decisions"][0]["action"], "BUY");
    assert_eq!(document["decisions"][0]["selected_horizon_ms"], 1000);
    assert_eq!(document["decisions"][0]["target_exposure_fraction"], 1.0);
    assert_eq!(
        document["batch_fingerprint_sha256"]
            .as_str()
            .unwrap()
            .len(),
        64
    );

    let _ = fs::remove_file(champion_path);
    let _ = fs::remove_file(request_path);
}
