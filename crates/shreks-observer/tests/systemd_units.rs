const OBSERVE_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-observe.service");
const EVIDENCE_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-paper-evidence.service");
const CAMPAIGN_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-paper-campaign.service");
const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");
const README: &str = include_str!("../../../deploy/systemd/README.md");

fn assert_common_service_contract(unit: &str) {
    for required in [
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "Restart=on-failure",
        "RestartSec=5s",
        "After=network-online.target",
        "Wants=network-online.target",
        "PartOf=shreks.target",
        "RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current",
        "StartLimitIntervalSec=300",
        "StartLimitBurst=5",
        "ExecStartPre=/usr/bin/test -d /var/lib/shreks",
        "ExecStartPre=/usr/bin/test -w /var/lib/shreks",
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
fn observe_service_runs_existing_observer_under_non_root_bounded_supervision() {
    assert_common_service_contract(OBSERVE_SERVICE);
    assert!(OBSERVE_SERVICE.contains("ExecStart=/opt/shreks/current/target/release/shreks-observe"));
    assert!(OBSERVE_SERVICE.contains("WantedBy=shreks.target"));
}

#[test]
fn paper_evidence_service_runs_daemon_under_non_root_bounded_supervision() {
    assert_common_service_contract(EVIDENCE_SERVICE);
    assert!(EVIDENCE_SERVICE.contains(
        "ExecStart=/opt/shreks/current/target/release/shreks-paper-evidence"
    ));
    assert!(EVIDENCE_SERVICE.contains("WantedBy=shreks.target"));
}

#[test]
fn paper_campaign_service_preflights_recovery_before_sealed_runtime() {
    assert_common_service_contract(CAMPAIGN_SERVICE);
    assert!(CAMPAIGN_SERVICE.contains(
        "ExecStartPre=/opt/shreks/current/.venv/bin/python -m shreks_brain.observer_campaign.runtime --preflight"
    ));
    assert!(CAMPAIGN_SERVICE.contains(
        "ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.observer_campaign.runtime"
    ));
    assert!(CAMPAIGN_SERVICE.contains("Environment=PYTHONDONTWRITEBYTECODE=1"));
    assert!(CAMPAIGN_SERVICE.contains("ReadWritePaths=/var/lib/shreks"));
    assert!(CAMPAIGN_SERVICE.contains("WantedBy=shreks.target"));
    assert!(!CAMPAIGN_SERVICE.contains("SHREKS_PAPER_CAMPAIGN_MAX_CYCLES="));
}

#[test]
fn target_starts_all_runtime_services_without_cascading_member_restart_into_target_shutdown() {
    assert!(SHREKS_TARGET.contains(
        "Wants=shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service"
    ));
    assert!(!SHREKS_TARGET.contains(
        "Requires=shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service"
    ));
    assert!(SHREKS_TARGET.contains("After=network-online.target"));
    assert!(SHREKS_TARGET.contains("WantedBy=multi-user.target"));
}

#[test]
fn operator_runbook_preserves_persistent_paths_runtime_secret_boundary_and_release_python() {
    for required in [
        "/opt/shreks/current",
        "/opt/shreks/current/.venv/bin/python",
        "python3 -m venv .venv",
        ".venv/bin/python -m pip install ./python",
        "/etc/shreks/shreks.env",
        "chmod 600 /etc/shreks/shreks.env",
        "SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH=/var/lib/shreks/shreks.db",
        "SHREKS_PAPER_CAMPAIGN_E11_PATH=/var/lib/shreks/paper-evaluation-e11.json",
        "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH=/etc/shreks/paper-campaign.json",
        "systemctl daemon-reload",
        "systemctl enable --now shreks.target",
        "systemctl status shreks-observe",
        "systemctl status shreks-paper-evidence",
        "systemctl status shreks-paper-campaign",
        "journalctl -u shreks-observe",
        "journalctl -u shreks-paper-evidence",
        "journalctl -u shreks-paper-campaign",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(README.contains(required), "missing runbook instruction: {required}");
    }
    assert!(!README.contains("HELIUS_API_KEY=example"));
    assert!(!README.contains("JUPITER_API_KEY=example"));
    assert!(!README.contains("SHREKS_PAPER_CAMPAIGN_MAX_SLIPPAGE_BPS="));
    assert!(!README.contains("SHREKS_PAPER_CAMPAIGN_RISK_LIMIT_USD="));
}

#[test]
fn operator_runbook_exposes_restart_reboot_health_and_fail_closed_recovery_evidence() {
    for required in [
        "systemctl is-enabled shreks.target",
        "ActiveState",
        "SubState",
        "NRestarts",
        "ExecMainStatus",
        "ActiveEnterTimestamp",
        "systemctl show shreks-observe.service",
        "systemctl show shreks-paper-evidence.service",
        "systemctl show shreks-paper-campaign.service",
        "systemctl reset-failed shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service",
        "only after the root cause is resolved",
        "readlink -f /opt/shreks/current",
        "test -r /etc/shreks/paper-campaign.json",
        "test -r /var/lib/shreks/shreks.db",
        "test -r /var/lib/shreks/paper-evaluation-e11.json",
        "do not bypass the campaign preflight",
        "do not launch the campaign runtime manually",
    ] {
        assert!(README.contains(required), "missing G3 recovery instruction: {required}");
    }
}
