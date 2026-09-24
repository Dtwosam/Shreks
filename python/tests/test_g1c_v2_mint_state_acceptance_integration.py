from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.telemetry.runtime as telemetry_runtime


_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERIFY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "verify-production-paper.yml"


def test_telemetry_runtime_processes_mint_acceptance_control_before_normal_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    monkeypatch.setattr(
        telemetry_runtime,
        "_process_mint_state_acceptance_controls",
        lambda: events.append("mint-acceptance"),
    )
    monkeypatch.setattr(
        telemetry_runtime,
        "_process_discovery_controls",
        lambda: events.append("discovery"),
    )
    monkeypatch.setattr(
        telemetry_runtime,
        "load_telemetry_runtime_config",
        lambda: events.append("config") or object(),
    )
    monkeypatch.setattr(
        telemetry_runtime,
        "run_telemetry_once",
        lambda _config, *, as_of_unix_ms: events.append("snapshot"),
    )

    assert telemetry_runtime.main([]) == 0
    assert events == ["mint-acceptance", "discovery", "config", "snapshot"]


def test_production_verifier_requests_sanitized_mint_acceptance_without_permission_widening() -> None:
    workflow = _VERIFY_WORKFLOW.read_text(encoding="utf-8")

    for required in (
        "shreks.g1c_v2_mint_state_acceptance_control_request",
        "/dev/shm/shreks-g1c-v2-mint-state-acceptance.",
        "g1c_v2_mint_state_acceptance_status=%s",
        "HOLD_INSUFFICIENT_EVIDENCE",
        'mint_state_max_age=900000ms',
        'mint_state_refresh_age=540000ms',
        "provider_failures=",
        "helius_budget_exhausted=true",
    ):
        assert required in workflow

    for forbidden in (
        "sudo ",
        "setfacl",
        "chmod /var/lib/shreks",
        "chown /var/lib/shreks",
    ):
        assert forbidden not in workflow

    marker_index = workflow.index(
        "shreks.g1c_v2_mint_state_acceptance_control_request"
    )
    result_index = workflow.index(
        "g1c_v2_mint_state_acceptance_status=%s",
        marker_index,
    )
    evidence_slice = workflow[marker_index:result_index]
    assert "sqlite3.connect" not in evidence_slice
    assert "cat /var/lib/shreks" not in evidence_slice


def test_production_verifier_treats_hold_as_nonfatal_and_failed_as_terminal() -> None:
    workflow = _VERIFY_WORKFLOW.read_text(encoding="utf-8")

    hold_branch = workflow.index(
        'if [[ "$MINT_ACCEPTANCE_STATUS" == "HOLD_INSUFFICIENT_EVIDENCE" ]]'
    )
    failed_branch = workflow.index(
        'if [[ "$MINT_ACCEPTANCE_STATUS" == "FAILED" ]]',
        hold_branch,
    )
    next_section = workflow.index("fl9_v2_discovery_bridge=available", failed_branch)
    hold_text = workflow[hold_branch:failed_branch]
    failed_text = workflow[failed_branch:next_section]

    assert "exit 1" not in hold_text
    assert "exit 1" in failed_text
