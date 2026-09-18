from __future__ import annotations

from pathlib import Path
import re


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"
_DEPLOY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"
_VERIFY_PRODUCTION_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "verify-production-paper.yml"
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
        'python -m pip wheel "$PYTHON_BUILD_ROOT" --no-deps',
        'rm -rf "$RELEASE_OUT"',
        'target/release/shreks-observe',
        'target/release/shreks-paper-evidence',
        'deploy/systemd/shreks-observe.service',
        'deploy/systemd/shreks-paper-evidence.service',
        'deploy/systemd/shreks-paper-campaign.service',
        'deploy/systemd/shreks.target',
        'deploy/release/release_manager.py',
        'deploy/release/release_bundle.py',
        'shreks_brain/_sealed_deploy_control/release_manager.py',
        'shreks_brain/_sealed_deploy_control/release_bundle.py',
        'zipfile.ZipFile',
        'release_bundle.py build',
        'release_bundle.py verify',
        'x86_64-unknown-linux-gnu',
    ):
        assert required in script

    assert '"$STAGING/deploy/release"' not in script
    assert 'cp deploy/release/release_manager.py "$STAGING/' not in script
    assert 'cp deploy/release/release_bundle.py "$STAGING/' not in script

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


def test_deploy_workflow_supports_manual_and_automatic_sealed_release_delivery():
    workflow = _read(_DEPLOY_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow
    assert "required: true" in workflow
    assert "workflow_run:" in workflow
    assert 'workflows: ["Build sealed Shreks release"]' in workflow
    assert "types: [completed]" in workflow
    assert "branches: [main]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.event == 'workflow_run'" in workflow
    assert "github.event.workflow_run.head_sha" in workflow
    assert "source_sha:" in workflow
    assert "environment: production-paper" in workflow
    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert "contents: write" not in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "^shreks-[0-9a-f]{40}$" in workflow

    for required in (
        "gh api",
        "immutable",
        "target_commitish",
        "draft",
        "prerelease",
        "gh release download",
        'shreks-release-$SOURCE_SHA.tar.gz',
        'shreks-release-$SOURCE_SHA.tar.gz.sha256',
        "RELEASE_MANIFEST.json",
        "release_bundle.py verify",
    ):
        assert required in workflow

    release_check = workflow.index("gh api")
    host_tokens = [workflow.find(token) for token in ('ssh "', 'scp "') if workflow.find(token) != -1]
    assert host_tokens
    assert release_check < min(host_tokens)

    assert "gh release create" not in workflow
    assert "cargo build" not in workflow
    assert "pip wheel" not in workflow



def test_deploy_workflow_chains_reusable_verifier_after_successful_deploy():
    workflow = _read(_DEPLOY_WORKFLOW)

    for required in (
        "resolve:",
        "outputs:",
        "needs: resolve",
        "needs: [resolve, deploy]",
        "uses: ./.github/workflows/verify-production-paper.yml",
        "expected_release_sha:",
        'journal_minutes: "30"',
        "secrets: inherit",
    ):
        assert required in workflow

    assert "needs.resolve.outputs.source_sha" in workflow
    assert "needs.resolve.outputs.release_tag" in workflow


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


def test_production_verifier_is_manual_and_reusable_read_only_transport_boundary():
    workflow = _read(_VERIFY_PRODUCTION_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "workflow_call:" in workflow
    assert "expected_release_sha:" in workflow
    assert "journal_minutes:" in workflow
    assert 'default: "30"' in workflow
    assert "environment: production-paper" in workflow
    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow)) == _DEPLOY_SECRET_NAMES

    for required in (
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
        "BatchMode=yes",
        "readlink -f /opt/shreks/current",
        "RELEASE_MANIFEST.json",
        "shreks-observe.service",
        "shreks-paper-evidence.service",
        "shreks-paper-campaign.service",
        'systemctl show "$unit"',
        "NRestarts",
        "/proc/$pid/exe",
        "/proc/$pid/cwd",
        "journalctl",
        "DatabaseBusy",
        "database is locked",
        "InvalidResponse",
        "/var/lib/shreks/shreks.db",
        "mode=ro",
        "PRAGMA query_only = ON",
        "fast_future_path_labels",
        "/dev/shm/shreks-fl9-v2-discovery.",
        "shreks.fl9_v2_discovery_control_request",
        "shreks_brain.telemetry.fl9_v2_discovery_control",
        "systemctl is-active --quiet shreks-telemetry.timer",
        "journalctl -u shreks-telemetry.service -o cat",
        "HOLD_NO_REQUEST_AUTHORITY",
        "HOLD_AMBIGUOUS_REQUEST_AUTHORITY",
        "HOLD_NO_COMPATIBLE",
        "FOUND_COMPATIBLE",
        'rm -f "$DISCOVERY_MARKER"',
    ):
        assert required in workflow

    for forbidden in (
        "sudo ",
        "systemctl start",
        "systemctl stop",
        "systemctl restart",
        "systemctl enable",
        "systemctl disable",
        "systemctl kill",
        "shreks-fl9-v2-future-path-backfill",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "LIVE_TRADING",
        "chmod /etc/shreks",
        "chmod /var/lib/shreks",
        "chown /etc/shreks",
        "chown /var/lib/shreks",
        "setfacl",
    ):
        assert forbidden not in workflow


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


def test_release_runbook_documents_backward_compatible_sealed_control_plane_recovery():
    runbook = _read(_RELEASE_RUNBOOK)
    for required in (
        "shreks_brain/_sealed_deploy_control/release_manager.py",
        "shreks_brain/_sealed_deploy_control/release_bundle.py",
        "manifest-hashed wheel",
        "zipfile.ZipFile",
        "activate-existing",
        "process identity",
    ):
        assert required in runbook

    assert "/opt/shreks/current/deploy/release/release_manager.py" not in runbook
    assert "/opt/shreks/current/deploy/release/release_bundle.py" not in runbook


def test_release_runbook_documents_no_admin_shell_fl9_discovery_bridge():
    runbook = _read(_RELEASE_RUNBOOK)

    for required in (
        "/dev/shm/shreks-fl9-v2-discovery",
        "shreks-telemetry.timer",
        "journalctl -u shreks-telemetry.service -o cat",
        "shreks-deploy",
        "/etc/shreks",
        "/var/lib/shreks",
        "FOUND_COMPATIBLE",
        "HOLD_NO_REQUEST_AUTHORITY",
        "HOLD_AMBIGUOUS_REQUEST_AUTHORITY",
        "HOLD_NO_COMPATIBLE",
        "evidence only",
        "LIVE TRADING: DISABLED",
    ):
        assert required in runbook

    lower = runbook.lower()
    assert "do not add sudoers" in lower
    assert "do not relax" in lower
    assert "interactive administrator shell" in lower


def test_release_runbook_documents_automatic_sealed_release_delivery_chain():
    runbook = _read(_RELEASE_RUNBOOK)

    for required in (
        "seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery",
        "workflow_run.head_sha",
        "target_commitish",
        "immutable=true",
        "production-paper",
        "Manual controls remain available as fallbacks",
        "Verify production PAPER runtime",
        "LIVE TRADING: DISABLED",
    ):
        assert required in runbook

    lower = runbook.lower()
    assert "does not bypass" in lower
    assert "before host contact" in lower
