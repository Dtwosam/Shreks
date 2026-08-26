use std::fs;
use std::path::{Path, PathBuf};

const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");
const README: &str = include_str!("../../../deploy/systemd/README.md");

fn repo_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

fn dashboard_service() -> String {
    fs::read_to_string(repo_path("deploy/systemd/shreks-dashboard.service"))
        .expect("G5/G7 dashboard service must exist")
}

#[test]
fn dashboard_service_is_loopback_hardened_and_restart_bounded() {
    let service = dashboard_service();
    for required in [
        "Description=Shreks private operator dashboard with safety controls",
        "After=network-online.target",
        "Wants=network-online.target",
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        "RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current",
        "ExecStartPre=/usr/bin/test -r /etc/shreks/dashboard-password",
        "ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.dashboard.runtime",
        "Restart=on-failure",
        "RestartSec=5s",
        "StartLimitIntervalSec=60s",
        "StartLimitBurst=5",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ProtectProc=invisible",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
        "ReadOnlyPaths=/var/lib/shreks /etc/shreks",
        "ReadWritePaths=/var/lib/shreks/risk",
        "UMask=0077",
        "WantedBy=multi-user.target",
    ] {
        assert!(service.contains(required), "missing dashboard service contract: {required}");
    }

    for forbidden in [
        "ReadWritePaths=/var/lib/shreks\n",
        "ReadWritePaths=/etc/shreks",
        "ReadWritePaths=/opt/shreks",
        "PartOf=shreks.target",
        "WantedBy=shreks.target",
        "Requires=shreks.target",
        "HELIUS_API_KEY=",
        "JUPITER_API_KEY=",
        concat!("PRIVATE_", "KEY="),
        concat!("SEED_", "PHRASE="),
        "SHREKS_MODE=live",
        "--live",
        "submit-transaction",
        "submit_transaction",
        "sign-transaction",
        "sign_transaction",
        "wallet-command",
    ] {
        assert!(!service.contains(forbidden), "dashboard gained forbidden authority/coupling: {forbidden}");
    }
}

#[test]
fn paper_target_does_not_depend_on_dashboard() {
    assert!(!SHREKS_TARGET.contains("shreks-dashboard.service"));
}

#[test]
fn dashboard_runbook_keeps_remote_access_private_and_g5_history_intact() {
    for required in [
        "/etc/shreks/dashboard-password",
        "root:shreks 0640",
        "loopback only",
        "plain HTTP port",
        "same-host TLS reverse proxy",
        "authenticated private overlay/tunnel",
        "systemctl enable --now shreks-dashboard.service",
        "systemctl status shreks-dashboard.service",
        "journalctl -u shreks-dashboard.service",
        "dashboard failure cannot stop the PAPER runtime",
        "no operator controls until G7",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(README.contains(required), "missing G5 dashboard runbook instruction: {required}");
    }
}
