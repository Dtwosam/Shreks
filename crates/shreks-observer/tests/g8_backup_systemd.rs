use std::fs;
use std::path::{Path, PathBuf};

const G8_RUNBOOK: &str = include_str!("../../../deploy/systemd/G8_BACKUP_RESTORE.md");
const ENV_EXAMPLE: &str = include_str!("../../../.env.example");
const SHREKS_TARGET: &str = include_str!("../../../deploy/systemd/shreks.target");

fn repo_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

fn unit(name: &str) -> String {
    fs::read_to_string(repo_path(&format!("deploy/systemd/{name}")))
        .unwrap_or_else(|_| panic!("G8 unit must exist: {name}"))
}

#[test]
fn backup_service_is_oneshot_private_and_can_write_only_backup_storage() {
    let service = unit("shreks-backup.service");

    for required in [
        "Description=Shreks verified backup snapshot",
        "Type=oneshot",
        "User=shreks",
        "Group=shreks",
        "WorkingDirectory=/opt/shreks/current",
        "EnvironmentFile=/etc/shreks/shreks.env",
        "ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.backup.runtime backup",
        "ReadOnlyPaths=/var/lib/shreks /etc/shreks",
        "ReadWritePaths=/var/lib/shreks/backups",
        "PrivateNetwork=true",
        "RestrictAddressFamilies=AF_UNIX",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ProtectKernelTunables=true",
        "ProtectKernelModules=true",
        "ProtectKernelLogs=true",
        "ProtectControlGroups=true",
        "RestrictSUIDSGID=true",
        "LockPersonality=true",
        "MemoryDenyWriteExecute=true",
        "UMask=0077",
    ] {
        assert!(service.contains(required), "missing G8 backup sandbox contract: {required}");
    }

    for forbidden in [
        "ReadWritePaths=/var/lib/shreks\n",
        "ReadWritePaths=/etc/shreks",
        "ReadWritePaths=/opt/shreks",
        "PartOf=shreks.target",
        "Requires=shreks-paper-campaign.service",
        "Wants=shreks-paper-campaign.service",
        "Requires=shreks-dashboard.service",
        "Wants=shreks-dashboard.service",
        "Requires=shreks-alerts.service",
        "Wants=shreks-alerts.service",
    ] {
        assert!(!service.contains(forbidden), "G8 backup write/coupling boundary broadened: {forbidden}");
    }
    assert!(!SHREKS_TARGET.contains("shreks-backup.service"));
}

#[test]
fn backup_timer_is_hourly_persistent_and_bounded() {
    let timer = unit("shreks-backup.timer");
    for required in [
        "Description=Run Shreks verified backup snapshot hourly",
        "OnCalendar=hourly",
        "Persistent=true",
        "RandomizedDelaySec=10m",
        "AccuracySec=1m",
        "Unit=shreks-backup.service",
        "WantedBy=timers.target",
    ] {
        assert!(timer.contains(required), "missing G8 timer contract: {required}");
    }
}

#[test]
fn g8_units_have_no_network_service_management_or_live_authority() {
    for name in ["shreks-backup.service", "shreks-backup.timer"] {
        let contents = unit(name).to_lowercase();
        for forbidden in [
            "systemctl",
            "service restart",
            "service stop",
            "service start",
            "shutdown",
            "reboot",
            "shreks_mode=live",
            "--live",
            "wallet",
            "private_key",
            "seed_phrase",
            "submit_transaction",
            "submit-transaction",
            "sign_transaction",
            "sign-transaction",
            "af_inet",
            "af_inet6",
        ] {
            assert!(!contents.contains(forbidden), "{name} gained forbidden authority: {forbidden}");
        }
    }
}

#[test]
fn env_example_has_only_bounded_g8_operational_backup_keys() {
    for required in [
        "SHREKS_BACKUP_ROOT=/var/lib/shreks/backups",
        "SHREKS_BACKUP_RETENTION_COUNT=168",
        "SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS=3",
    ] {
        assert!(ENV_EXAMPLE.contains(required), "missing G8 environment example: {required}");
    }
    for forbidden in [
        "SHREKS_BACKUP_STRATEGY",
        "SHREKS_BACKUP_RISK",
        "SHREKS_BACKUP_LIVE",
        "SHREKS_BACKUP_PRIVATE_KEY",
    ] {
        assert!(!ENV_EXAMPLE.contains(forbidden), "G8 env namespace gained forbidden key: {forbidden}");
    }
    assert!(ENV_EXAMPLE.contains("SHREKS_MODE=observe"));
    assert!(!ENV_EXAMPLE.contains("SHREKS_MODE=live"));
}

#[test]
fn runbook_documents_verified_staging_recovery_and_separate_activation() {
    for required in [
        "/var/lib/shreks/backups",
        "0700",
        "0600",
        "df -h /var/lib/shreks/backups",
        "python -m shreks_brain.backup.runtime verify",
        "python -m shreks_brain.backup.runtime restore",
        "empty staging directory",
        "systemctl stop shreks-paper-campaign.service",
        "preflight",
        "systemctl start shreks-paper-campaign.service",
        "G7 operator risk-control state",
        "secrets are not backed up",
        "off-host",
        "rollback",
        "onchain reconciliation",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(G8_RUNBOOK.contains(required), "missing G8 runbook evidence: {required}");
    }
}
