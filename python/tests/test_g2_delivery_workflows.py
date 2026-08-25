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


def test_release_workflow_is_manual_exact_sha_retests_and_only_writes_contents():
    workflow = _read(_RELEASE_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "source_sha:" in workflow
    assert "required: true" in workflow
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
        'ref: ${{ inputs.source_sha }}',
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


# Task 4 extends this file with deploy-transport and bootstrap/runbook assertions.
