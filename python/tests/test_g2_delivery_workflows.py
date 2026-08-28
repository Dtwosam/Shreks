from __future__ import annotations

from pathlib import Path
import re


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"
_DEPLOY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"
_BUILD_SCRIPT = _REPO_ROOT / "deploy" / "release" / "build_release.sh"
_RELEASE_BUNDLE = _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
_RELEASE_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"

_FORBIDDEN_RELEASE_TEXT = (
    "WALLET",
    "SEED_PHRASE",
    "SIGNING_KEY",
    "HELIUS_API_KEY",
    "JUPITER_API_KEY",
    "LIVE_TRADING=ENABLED",
)
_DEPLOY_SECRET_NAMES = {
    "SHREKS_DEPLOY_HOST",
    "SHREKS_DEPLOY_PORT",
    "SHREKS_DEPLOY_USER",
    "SHREKS_DEPLOY_SSH_KEY",
    "SHREKS_DEPLOY_KNOWN_HOSTS",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_build_script_is_fail_closed_allowlisted_and_locally_verified():
    script = _read(_BUILD_SCRIPT)

    for required in (
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "^[0-9a-f]{40}$",
        'git rev-parse HEAD',
        'cargo build --release --bin shreks-observe --bin shreks-paper-evidence',
        'python -m pip wheel ./python --no-deps',
        'rm -rf "$RELEASE_OUT"',
        'target/release/shreks-observe',
        'target/release/shreks-paper-evidence',
        'deploy/systemd/shreks-observe.service',
        'deploy/systemd/shreks-paper-evidence.service',
        'deploy/systemd/shreks-paper-campaign.service',
        'deploy/systemd/shreks.target',
        'release_bundle.py build',
        'release_bundle.py verify',
        'x86_64-unknown-linux-gnu',
    ):
        assert required in script

    for forbidden in _FORBIDDEN_RELEASE_TEXT:
        assert forbidden not in script


def test_release_bundle_has_build_and_verify_cli_without_third_party_dependencies():
    source = _read(_RELEASE_BUNDLE)

    assert "import argparse" in source
    assert 'add_parser("build")' in source
    assert 'add_parser("verify")' in source
    assert "build_release_manifest(" in source
    assert "write_release_archive(" in source
    assert "verify_release_archive(" in source
    assert 'if __name__ == "__main__":' in source
    assert "requests" not in source
    assert "yaml" not in source.lower()


def test_release_workflow_keeps_manual_and_auto_exact_sha_retests_and_only_writes_contents():
    workflow = _read(_RELEASE_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "source_sha:" in workflow
    assert "required: true" in workflow
    assert "workflow_run:" in workflow
    assert re.search(r"permissions:\s*\n\s+contents: write", workflow)
    assert "packages: write" not in workflow
    assert "actions: write" not in workflow
    assert "id-token: write" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow

    for required in (
        "actions/checkout@v7",
        "actions/setup-python@v7",
        "dtolnay/rust-toolchain@stable",
        "inputs.source_sha",
        "github.event.workflow_run.head_sha",
        "github.event.workflow_run.conclusion == 'success'",
        "fetch-depth: 0",
        "^[0-9a-f]{40}$",
        'git rev-parse HEAD',
        'git log -1 --format=%s',
        "seal",
        "Reject committed secret assignments",
        "cargo test --workspace",
        "python-version: \"3.12\"",
        "python -m pip install -e './python[dev]'",
        "python -m pytest python/tests -q",
        "deploy/release/build_release.sh",
        'TAG="shreks-$SOURCE_SHA"',
        "gh release view",
        "gh release create",
        '--target "$SOURCE_SHA"',
        "dist/release/RELEASE_MANIFEST.json",
    ):
        assert required in workflow

    for forbidden in _FORBIDDEN_RELEASE_TEXT:
        assert forbidden not in workflow


def test_release_workflow_does_not_consume_deployment_or_runtime_secrets():
    workflow = _read(_RELEASE_WORKFLOW)
    assert "secrets." not in workflow
    assert "production-paper" not in workflow
    assert "ssh" not in workflow.lower()


def test_deploy_workflow_is_manual_existing_release_only_and_minimum_permission():
    workflow = _read(_DEPLOY_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow
    assert "required: true" in workflow
    assert "environment: production-paper" in workflow
    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert "contents: write" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "^shreks-[0-9a-f]{40}$" in workflow
    assert "gh release download" in workflow
    assert 'shreks-release-$SOURCE_SHA.tar.gz' in workflow
    assert 'shreks-release-$SOURCE_SHA.tar.gz.sha256' in workflow
    assert "RELEASE_MANIFEST.json" in workflow
    assert "release_bundle.py verify" in workflow
    assert "gh release create" not in workflow
    assert "cargo build" not in workflow
    assert "pip wheel" not in workflow


def test_deploy_workflow_uses_only_transport_secrets_and_strict_host_verification():
    workflow = _read(_DEPLOY_WORKFLOW)
    consumed = set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow))
    assert consumed == _DEPLOY_SECRET_NAMES

    for required in (
        "mktemp -d",
        'chmod 600 "$KEY_FILE"',
        "SHREKS_DEPLOY_KNOWN_HOSTS",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
        "BatchMode=yes",
        "scp",
        "ssh",
        "sudo /usr/local/sbin/shreks-release-manager install",
    ):
        assert required in workflow

    assert "ssh-keyscan" not in workflow
    for forbidden in _FORBIDDEN_RELEASE_TEXT:
        assert forbidden not in workflow


def test_deploy_workflow_copies_only_release_assets_and_does_not_mutate_runtime_state():
    workflow = _read(_DEPLOY_WORKFLOW)
    for protected in (
        "/etc/shreks/shreks.env",
        "/etc/shreks/paper-campaign.json",
        "/var/lib/shreks",
    ):
        assert protected not in workflow

    assert workflow.count("scp ") == 3
    for forbidden in (
        "systemctl start",
        "systemctl stop",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
        "systemctl kill",
        "activate-existing",
        "LIVE_TRADING",
    ):
        assert forbidden not in workflow


def test_deploy_workflow_reports_read_only_host_diagnostics_on_release_manager_failure():
    workflow = _read(_DEPLOY_WORKFLOW)

    for required in (
        'DEPLOY_RC=$?',
        "release manager failed; collecting read-only host diagnostics",
        "readlink -f /opt/shreks/current",
        "candidate_release_present=",
        "systemctl is-active shreks.target",
        "systemctl show shreks-observe.service",
        "-p ActiveState",
        "-p SubState",
        "-p NRestarts",
        "-p MainPID",
        "-p ExecMainStatus",
        'exit "$DEPLOY_RC"',
    ):
        assert required in workflow

    assert "sudo systemctl" not in workflow
    assert "journalctl" not in workflow


def test_release_runbook_bootstraps_root_owned_manager_and_narrow_deploy_account():
    runbook = _read(_RELEASE_RUNBOOK)

    for required in (
        "install -o root -g root -m 0755",
        "/usr/local/sbin/shreks-release-manager",
        "/usr/local/sbin/release_bundle.py",
        "shreks-deploy",
        "/etc/sudoers.d/shreks-release-manager",
        "NOPASSWD",
        "production-paper",
        "SHREKS_DEPLOY_HOST",
        "SHREKS_DEPLOY_PORT",
        "SHREKS_DEPLOY_USER",
        "SHREKS_DEPLOY_SSH_KEY",
        "SHREKS_DEPLOY_KNOWN_HOSTS",
        "readlink -f /opt/shreks/current",
        "cat /opt/shreks/current/RELEASE_MANIFEST.json",
        "/etc/shreks/shreks.env",
        "/etc/shreks/paper-campaign.json",
        "/var/lib/shreks",
        "rollback",
        "earlier GitHub Release tag",
        "LIVE TRADING: DISABLED",
    ):
        assert required in runbook

    lower = runbook.lower()
    assert "deploy ssh key" in lower
    assert "trading key" in lower
    assert "never" in lower
