use std::fs;
use std::path::{Path, PathBuf};

const G7_RUNBOOK: &str = include_str!("../../../deploy/systemd/G7_OPERATOR_CONTROLS.md");
const ENV_EXAMPLE: &str = include_str!("../../../.env.example");
const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");

fn repo_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

fn unit(name: &str) -> String {
    fs::read_to_string(repo_path(&format!("deploy/systemd/{name}")))
        .unwrap_or_else(|_| panic!("G7 unit must exist: {name}"))
}

#[test]
fn dashboard_service_can_write_only_durable_risk_control_directory() {
    let service = unit("shreks-dashboard.service");

    for required in [
        "Description=Shreks private operator dashboard with safety controls",
        "ReadOnlyPaths=/var/lib/shreks /etc/shreks",
        "ReadWritePaths=/var/lib/shreks/risk",
        "ExecStartPre=/usr/bin/test -r /var/lib/shreks/risk/operator-control.json",
        "ExecStartPre=/usr/bin/test -w /var/lib/shreks/risk",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
    ] {
        assert!(service.contains(required), "missing G7 dashboard sandbox contract: {required}");
    }

    for forbidden in [
        "ReadWritePaths=/var/lib/shreks\n",
        "ReadWritePaths=/etc/shreks",
        "ReadWritePaths=/opt/shreks",
        "PartOf=shreks.target",
        "Requires=shreks-paper-campaign.service",
        "Wants=shreks-paper-campaign.service",
    ] {
        assert!(!service.contains(forbidden), "dashboard write/coupling boundary broadened: {forbidden}");
    }
}

#[test]
fn paper_service_reads_same_control_state_without_dashboard_dependency() {
    let paper = unit("shreks-paper-campaign.service");

    assert!(paper.contains(
        "ExecStartPre=/usr/bin/test -r /var/lib/shreks/risk/operator-control.json"
    ));
    assert!(!paper.contains("shreks-dashboard.service"));
    assert!(!SHREKS_TARGET.contains("shreks-dashboard.service"));
}

#[test]
fn g7_units_introduce_no_service_management_or_live_authority() {
    for name in ["shreks-dashboard.service", "shreks-paper-campaign.service"] {
        let service = unit(name).to_lowercase();
        for forbidden in [
            "systemctl",
            "service restart",
            "service stop",
            "service start",
            "shutdown",
            "reboot",
            "shreks_mode=live",
            "--live",
            "submit_transaction",
            "submit-transaction",
            "sign_transaction",
            "sign-transaction",
        ] {
            assert!(!service.contains(forbidden), "{name} gained forbidden authority: {forbidden}");
        }
    }
}

#[test]
fn env_example_uses_standalone_g7_control_path_and_keeps_live_disabled() {
    assert!(ENV_EXAMPLE.contains(
        "SHREKS_RISK_CONTROL_STATE_PATH=/var/lib/shreks/risk/operator-control.json"
    ));
    assert!(!ENV_EXAMPLE.contains("SHREKS_PAPER_CAMPAIGN_RISK_CONTROL_PATH"));
    assert!(ENV_EXAMPLE.contains("SHREKS_MODE=observe"));
    assert!(!ENV_EXAMPLE.contains("SHREKS_MODE=live"));
}

#[test]
fn runbook_initializes_protects_resets_and_preserves_g7_control_state() {
    for required in [
        "/var/lib/shreks/risk/operator-control.json",
        "SHREKS_RISK_CONTROL_STATE_PATH=/var/lib/shreks/risk/operator-control.json",
        "python -m shreks_brain.risk_control.cli initialize",
        "python -m shreks_brain.risk_control.cli reset-kill-switch",
        "python -m shreks_brain.risk_control.cli clear-entry-halt",
        "RESET KILL SWITCH",
        "CLEAR ENTRY HALT",
        "expected revision",
        "0700",
        "0600",
        "rollback to a pre-G7 release",
        "preserve the G7 risk-control state",
        "browser controls are disabled",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(G7_RUNBOOK.contains(required), "missing G7 runbook evidence: {required}");
    }
}
