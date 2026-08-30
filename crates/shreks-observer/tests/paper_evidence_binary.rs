#[test]
fn paper_evidence_binary_wires_only_the_bounded_read_only_evidence_path() {
    let source = include_str!("../src/bin/shreks-paper-evidence/main.rs");

    for required in [
        "PaperEvidenceRuntimeConfig::from_env",
        "require_providers",
        "EvidenceCandidateStore::open",
        "ShreksDb::open",
        "HeliusProvider::new",
        "with_request_budget(config.helius_max_requests_per_process)",
        "JupiterProvider::new",
        "SafetyEvidenceCollector::new",
        "with_chain_provider",
        "run_paper_evidence_cycle",
        "request_usage",
        "tokio::time::sleep",
        "tokio::signal::ctrl_c",
    ] {
        assert!(source.contains(required), "missing daemon wiring token: {required}");
    }

    for forbidden in [
        "trade_intent",
        "RegistryStore",
        "promotion",
        "live_execution",
        "sign_transaction",
        "submit_transaction",
        "private_key",
        "seed_phrase",
        "HELIUS_API_KEY=",
        "JUPITER_API_KEY=",
    ] {
        assert!(!source.contains(forbidden), "forbidden daemon authority token: {forbidden}");
    }
}

#[test]
fn paper_evidence_binary_logs_counts_and_budget_state_not_provider_keys() {
    let source = include_str!("../src/bin/shreks-paper-evidence/main.rs");
    assert!(source.contains("candidates_selected"));
    assert!(source.contains("mint_states_stored"));
    assert!(source.contains("holder_snapshots_stored"));
    assert!(source.contains("entry_quote_snapshots_stored"));
    assert!(source.contains("exit_quote_snapshots_stored"));
    assert!(source.contains("provider_failures"));
    assert!(source.contains("helius_requests_attempted"));
    assert!(source.contains("helius_requests_limit"));
    assert!(source.contains("helius_requests_remaining"));
    assert!(source.contains("helius_budget_exhausted"));

    for line in source.lines().filter(|line| line.contains("eprintln!")) {
        assert!(!line.contains("api_key"), "credential accessor appeared in log statement");
    }
    assert!(!source.contains("{helius_key}"));
    assert!(!source.contains("{jupiter_key}"));
}
