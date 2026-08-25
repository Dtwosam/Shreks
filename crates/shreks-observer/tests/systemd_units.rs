const OBSERVE_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-observe.service");
const EVIDENCE_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-paper-evidence.service");
const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");
const README: &str = include_str!("../../../deploy/systemd/README.md");

fn assert_common_service_contract(unit: &str) {
    for required in [
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "Restart=on-failure",
        "After=network-online.target",
        "Wants=network-online.target",
    ] {
        assert!(unit.contains(required), "missing service contract: {required}");
    }

    for forbidden in [
        "HELIUS_API_KEY=",
        "JUPITER_API_KEY=",
        concat!("PRIVATE_", "KEY="),
        concat!("SEED_", "PHRASE="),
        "SHREKS_MODE=live",
        "--live",
        "submit-transaction",
        "submit_transaction",
    ] {
        assert!(!unit.contains(forbidden), "embedded authority/secret: {forbidden}");
    }
}

#[test]
fn observe_service_runs_existing_observer_under_non_root_supervision() {
    assert_common_service_contract(OBSERVE_SERVICE);
    assert!(OBSERVE_SERVICE.contains("ExecStart=/opt/shreks/current/target/release/shreks-observe"));
    assert!(OBSERVE_SERVICE.contains("WantedBy=shreks.target"));
}

#[test]
fn paper_evidence_service_runs_new_daemon_under_non_root_supervision() {
    assert_common_service_contract(EVIDENCE_SERVICE);
    assert!(EVIDENCE_SERVICE.contains(
        "ExecStart=/opt/shreks/current/target/release/shreks-paper-evidence"
    ));
    assert!(EVIDENCE_SERVICE.contains("WantedBy=shreks.target"));
}

#[test]
fn target_groups_observer_and_paper_evidence_services() {
    assert!(SHREKS_TARGET.contains("Wants=shreks-observe.service shreks-paper-evidence.service"));
    assert!(SHREKS_TARGET.contains("After=network-online.target"));
    assert!(SHREKS_TARGET.contains("WantedBy=multi-user.target"));
}

#[test]
fn operator_runbook_preserves_persistent_paths_and_runtime_secret_boundary() {
    for required in [
        "/opt/shreks/current",
        "/etc/shreks/shreks.env",
        "chmod 600 /etc/shreks/shreks.env",
        "systemctl daemon-reload",
        "systemctl enable --now shreks.target",
        "systemctl status shreks-observe",
        "systemctl status shreks-paper-evidence",
        "journalctl -u shreks-observe",
        "journalctl -u shreks-paper-evidence",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(README.contains(required), "missing runbook instruction: {required}");
    }
    assert!(!README.contains("HELIUS_API_KEY=example"));
    assert!(!README.contains("JUPITER_API_KEY=example"));
}
