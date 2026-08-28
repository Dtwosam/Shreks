from __future__ import annotations

from pathlib import Path
import re


_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"
_DEPLOY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"
_RELEASE_RUNBOOK = _REPO_ROOT / "deploy" / "release" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_workflow_auto_releases_only_successful_main_ci_seals():
    workflow = _read(_RELEASE_WORKFLOW)

    # Keep the proven manual release interface as a fallback/operator path.
    assert "workflow_dispatch:" in workflow
    assert "source_sha:" in workflow
    assert "platform:" in workflow

    # Add only a post-CI release trigger, scoped to completed CI on main.
    assert "workflow_run:" in workflow
    assert re.search(r'workflows:\s*\[\s*["\']CI["\']\s*\]', workflow)
    assert re.search(r"types:\s*\[\s*completed\s*\]", workflow)
    assert re.search(r"branches:\s*\[\s*main\s*\]", workflow)
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "startsWith(github.event.workflow_run.head_commit.message, 'seal:')" in workflow

    # The release identity must come from the exact CI-tested main commit.
    assert "github.event.workflow_run.head_sha" in workflow
    assert "aarch64-unknown-linux-gnu" in workflow
    assert "ubuntu-24.04-arm" in workflow

    # Existing immutable-release gates stay in force.
    for required in (
        "contents: write",
        "git rev-parse HEAD",
        "git log -1 --format=%s",
        "seal",
        "cargo test --workspace",
        "python -m pytest python/tests -q",
        "deploy/release/build_release.sh",
        "gh release view",
        "gh release create",
        '--target "$SOURCE_SHA"',
    ):
        assert required in workflow

    # Release creation still has no host/deployment/runtime-secret authority.
    assert "secrets." not in workflow
    assert "production-paper" not in workflow
    assert "scp " not in workflow
    assert re.search(r"\bssh\b", workflow, flags=re.IGNORECASE) is None


def test_production_deploy_remains_manual_only():
    workflow = _read(_DEPLOY_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "environment: production-paper" in workflow
    assert "release_tag:" in workflow

    for forbidden_trigger in (
        "workflow_run:",
        "workflow_call:",
        "release:",
        "push:",
        "pull_request:",
    ):
        assert forbidden_trigger not in workflow

    # Existing release-only and transport-only deployment boundary remains.
    assert "gh release download" in workflow
    assert "release_bundle.py verify" in workflow
    assert "sudo /usr/local/sbin/shreks-release-manager install" in workflow
    assert "gh release create" not in workflow


def test_release_runbook_distinguishes_auto_release_from_manual_deploy():
    runbook = _read(_RELEASE_RUNBOOK)

    for required in (
        "After a `seal:` commit lands on `main`",
        "CI",
        "starts automatically",
        "workflow_run.head_sha",
        "aarch64-unknown-linux-gnu",
        "manual `Build sealed Shreks release`",
        "same exact-SHA, seal, full-test, bundle-verification, and duplicate-tag gates",
        "does **not** contact the VPS",
        "Production deployment remains a separate manual action",
        "manual `Deploy verified Shreks release`",
        "LIVE TRADING: DISABLED",
    ):
        assert required in runbook
