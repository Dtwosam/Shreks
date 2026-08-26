use std::fs;
use std::path::{Path, PathBuf};

fn repo_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(relative)
}

#[test]
fn phase_g_runbook_documents_real_host_exit_drills_without_claiming_ci_is_a_vps() {
    let runbook = fs::read_to_string(repo_path("deploy/systemd/PHASE_G_HOST_ACCEPTANCE.md"))
        .expect("Phase G host acceptance runbook must exist");

    for required in [
        "99c5de232eb36e6fdd7777d089453f16c03ef38a",
        "non-numbered Phase G exit slice",
        "exact verified release",
        "BASELINE",
        "AFTER_PROCESS_RESTART",
        "AFTER_REBOOT",
        "AFTER_RESTORE_DRILL",
        "python -m shreks_brain.host_acceptance.runtime capture",
        "python -m shreks_brain.host_acceptance.runtime compare",
        "G6",
        "G7",
        "G8",
        "secret values are never copied into evidence",
        "routine harness has no lifecycle authority",
        "CI does not prove physical-host acceptance",
        "rollback",
        "release provenance",
        "F7",
        "LIVE TRADING: DISABLED",
    ] {
        assert!(runbook.contains(required), "missing host-acceptance runbook evidence: {required}");
    }
}

#[test]
fn host_acceptance_package_has_no_wallet_signing_submission_or_live_authority() {
    let source_dir = repo_path("python/src/shreks_brain/host_acceptance");
    let mut source = String::new();
    for entry in fs::read_dir(&source_dir).expect("host_acceptance source directory must exist") {
        let path = entry.expect("read source entry").path();
        if path.extension().and_then(|value| value.to_str()) == Some("py") {
            source.push_str(&fs::read_to_string(path).expect("read host_acceptance source"));
            source.push('\n');
        }
    }
    let source = source.to_lowercase();
    for forbidden in [
        "shreks_brain.wallet",
        "private_key",
        "seed_phrase",
        "sign_transaction",
        "submit_transaction",
        "send_transaction",
        "shreks_mode=live",
        "enable_live",
        "live_execution",
        "\"systemctl\", \"start\"",
        "\"systemctl\", \"stop\"",
        "\"systemctl\", \"restart\"",
        "\"systemctl\", \"enable\"",
        "\"systemctl\", \"disable\"",
        "\"systemctl\", \"reboot\"",
        "shutdown -",
    ] {
        assert!(!source.contains(forbidden), "host acceptance gained forbidden authority marker: {forbidden}");
    }

    let collector = fs::read_to_string(source_dir.join("collector.py")).expect("collector must exist");
    assert!(collector.contains("\"systemctl\""));
    assert!(collector.contains("\"show\""));
    assert!(collector.contains("\"is-enabled\""));
    assert!(!collector.contains("shell=True"));
}
