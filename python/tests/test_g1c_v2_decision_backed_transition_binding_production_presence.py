from __future__ import annotations

from pathlib import Path


def test_g1c_v2_decision_backed_transition_binding_has_read_only_production_presence_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "verify-production-paper.yml"
    ).read_text(encoding="utf-8")
    runbook = (
        repo_root / "deploy" / "release" / "README.md"
    ).read_text(encoding="utf-8")

    script = "shreks-g1c-v2-decision-backed-transition-bind"

    assert (
        f'DECISION_BACKED_TRANSITION_BINDING="/opt/shreks/current/.venv/bin/{script}"'
        in workflow
    )
    assert 'test -f "$DECISION_BACKED_TRANSITION_BINDING"' in workflow
    assert 'test ! -L "$DECISION_BACKED_TRANSITION_BINDING"' in workflow
    assert 'test -x "$DECISION_BACKED_TRANSITION_BINDING"' in workflow
    assert (
        'DECISION_BACKED_TRANSITION_BINDING_RESOLVED="$(readlink -f '
        '"$DECISION_BACKED_TRANSITION_BINDING")"'
        in workflow
    )
    assert (
        f'test "$DECISION_BACKED_TRANSITION_BINDING_RESOLVED" = '
        f'"$EXPECTED/.venv/bin/{script}"'
        in workflow
    )
    assert (
        "import shreks_brain.g1c_v2_decision_backed_transition_binding "
        "as decision_backed_transition_binding"
        in workflow
    )
    assert (
        "decision-backed transition binding module is outside the exact deployed release"
        in workflow
    )
    assert "g1c_v2_decision_backed_transition_binding=present" in workflow
    assert "g1c_v2_decision_backed_transition_binding_path=%s" in workflow
    assert "g1c_v2_decision_backed_transition_binding_module=%s" in workflow

    assert 'exec "$DECISION_BACKED_TRANSITION_BINDING"' not in workflow
    assert "decision_backed_transition_binding.main(" not in workflow

    assert "### Bind one exact decision-backed G1C v2 transition" in runbook
    assert script in runbook
    assert "--source-runtime-manifest" in runbook
    assert "--candidate-runtime-manifest" in runbook
    assert "--decision-backed-candidate-authority" in runbook
    assert "--cohort" in runbook
    assert "--v2-host-request-authority" in runbook
    assert "--destination" in runbook
    assert (
        "COHORT=\"/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2\""
        in runbook
    )
    assert "The cohort input is the frozen cohort directory, not a single file." in runbook
    assert (
        "There are no raw paper-run, timestamp, quote, entry-amount, decision, review, or sizing inputs."
        in runbook
    )
    assert "writes the existing standard transition-binding schema" in runbook
    assert "rotation_authority=NOT_GRANTED" in runbook
    assert "paper_promotion_authority=BLOCKED" in runbook
    assert "live_authority=DISABLED" in runbook
    assert "does not execute rotation-readiness" in runbook

    heading = "### Bind one exact decision-backed G1C v2 transition"
    section = runbook.split(heading, 1)[1].split("\n### ", 1)[0]
    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'MANIFEST_SHA="$(' in section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'sudo test ! -e "$BINDING"' in section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in section
