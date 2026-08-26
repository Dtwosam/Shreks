const TELEMETRY_SERVICE: &str = include_str!("../../../deploy/systemd/shreks-telemetry.service");
const TELEMETRY_TIMER: &str = include_str!("../../../deploy/systemd/shreks-telemetry.timer");
const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");
const README: &str = include_str!("../../../deploy/systemd/README.md");

#[test]
fn telemetry_service_is_read_only_oneshot_and_isolated_from_paper_target() {
    for required in [
        "Type=oneshot",
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        "After=network-online.target",
        "Wants=network-online.target",
        "RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current",
        "ExecStartPre=/usr/bin/test -d /var/lib/shreks/telemetry",
        "ExecStartPre=/usr/bin/test -w /var/lib/shreks/telemetry",
        "ExecStartPre=/opt/shreks/current/.venv/bin/python -m shreks_brain.telemetry.runtime --preflight",
        "ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.telemetry.runtime",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ReadWritePaths=/var/lib/shreks/telemetry",
        "UMask=0077",
    ] {
        assert!(TELEMETRY_SERVICE.contains(required), "missing telemetry service contract: {required}");
    }

    for forbidden in [
        "PartOf=shreks.target",
        "WantedBy=shreks.target",
        "Restart=",
        "HELIUS_API_KEY=",
        "JUPITER_API_KEY=",
        concat!("PRIVATE_", "KEY="),
        concat!("SEED_", "PHRASE="),
        "SHREKS_MODE=live",
        "--live",
        "submit-transaction",
        "submit_transaction",
    ] {
        assert!(!TELEMETRY_SERVICE.contains(forbidden), "telemetry gained forbidden coupling/authority: {forbidden}");
    }
}

#[test]
fn telemetry_timer_runs_independently_and_persists_across_reboot() {
    for required in [
        "Unit=shreks-telemetry.service",
        "OnBootSec=60s",
        "OnUnitActiveSec=60s",
        "AccuracySec=5s",
        "Persistent=true",
        "WantedBy=timers.target",
    ] {
        assert!(TELEMETRY_TIMER.contains(required), "missing telemetry timer contract: {required}");
    }
    assert!(!TELEMETRY_TIMER.contains("shreks.target"));
}

#[test]
fn paper_target_does_not_depend_on_telemetry() {
    assert!(!SHREKS_TARGET.contains("shreks-telemetry.service"));
    assert!(!SHREKS_TARGET.contains("shreks-telemetry.timer"));
}

#[test]
fn runbook_documents_private_local_telemetry_without_control_authority() {
    for required in [
        "/var/lib/shreks/telemetry",
        "/var/lib/shreks/telemetry/current.json",
        "systemctl enable --now shreks-telemetry.timer",
        "systemctl status shreks-telemetry.timer",
        "journalctl -u shreks-telemetry.service",
        "telemetry failure does not stop shreks.target",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(README.contains(required), "missing G4 telemetry runbook instruction: {required}");
    }
}
