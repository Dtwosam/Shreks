use std::fs;
use std::path::{Path, PathBuf};

const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");
const README: &str = include_str!("../../../deploy/systemd/README.md");

fn repo_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

fn read_required(relative: &str, label: &str) -> String {
    fs::read_to_string(repo_path(relative)).unwrap_or_else(|_| panic!("{label} must exist"))
}

#[test]
fn alerts_service_is_isolated_hardened_and_outbound_only() {
    let service = read_required("deploy/systemd/shreks-alerts.service", "G6 alert service");
    for required in [
        "Description=Shreks outbound alert notifications",
        "After=network-online.target",
        "Wants=network-online.target",
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        "RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current",
        "ExecStartPre=/usr/bin/test -r /etc/shreks/telegram-bot-token",
        "ExecStartPre=/usr/bin/test -d /var/lib/shreks/alerts",
        "ExecStartPre=/usr/bin/test -w /var/lib/shreks/alerts",
        "ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.alerts.runtime",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "ReadWritePaths=/var/lib/shreks/alerts",
        "UMask=0077",
    ] {
        assert!(service.contains(required), "missing G6 alert service contract: {required}");
    }

    for forbidden in [
        "PartOf=shreks.target",
        "WantedBy=shreks.target",
        "Requires=shreks.target",
        "SHREKS_MODE=live",
        "--live",
        "submit_transaction",
        "sign_transaction",
        "wallet-command",
        "getUpdates",
        "setWebhook",
    ] {
        assert!(!service.contains(forbidden), "G6 alert service gained forbidden authority/coupling: {forbidden}");
    }
}

#[test]
fn alerts_timer_has_bounded_independent_retry_cadence() {
    let timer = read_required("deploy/systemd/shreks-alerts.timer", "G6 alert timer");
    for required in [
        "Unit=shreks-alerts.service",
        "OnBootSec=90s",
        "OnUnitActiveSec=60s",
        "AccuracySec=5s",
        "Persistent=true",
        "WantedBy=timers.target",
    ] {
        assert!(timer.contains(required), "missing G6 alert timer contract: {required}");
    }
    assert!(!timer.contains("shreks.target"));
}

#[test]
fn paper_target_does_not_depend_on_alerting() {
    assert!(!SHREKS_TARGET.contains("shreks-alerts.service"));
    assert!(!SHREKS_TARGET.contains("shreks-alerts.timer"));
}

#[test]
fn alert_runbook_documents_secret_delivery_retry_and_independence() {
    for required in [
        "/etc/shreks/telegram-bot-token",
        "root:shreks 0640",
        "never stored in the environment file or GitHub",
        "outbound notifications only",
        "no commands or trading controls through Telegram",
        "systemctl enable --now shreks-alerts.timer",
        "/var/lib/shreks/alerts/state.json",
        "failed event and all later events remain queued",
        "systemctl status shreks-alerts.timer",
        "journalctl -u shreks-alerts.service",
        "alert failure cannot stop the PAPER runtime",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(README.contains(required), "missing G6 alert runbook instruction: {required}");
    }
}
