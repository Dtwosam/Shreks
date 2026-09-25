from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import shreks_brain.telemetry.g1c_v2_mint_state_acceptance_control as control


NOW = 2_000_000


def _document(**overrides) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_name": "shreks.paper_evidence_runtime_status",
        "schema_version": 1,
        "state": "CYCLE_COMPLETE",
        "process_started_at_unix_ms": 1_000_000,
        "generated_at_unix_ms": NOW - 10_000,
        "completed_cycle_count": 7,
        "cycle_as_of_unix_ms": NOW - 10_000,
        "evidence_cycle_interval_ms": 60_000,
        "mint_state_max_age_ms": 900_000,
        "mint_state_refresh_age_ms": 540_000,
        "provider_failures_last_cycle": 0,
        "helius_requests_attempted": 21,
        "helius_requests_limit": 500,
        "helius_requests_remaining": 479,
        "helius_budget_exhausted": False,
        "candidates_selected_last_cycle": 2,
        "mint_states_stored_last_cycle": 1,
        "observation_authority": "DERIVED_OPERATIONAL",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    document.update(overrides)
    return document


def _write(path: Path, document: dict[str, object], *, mode: int = 0o600) -> None:
    path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def _read(path: Path, *, now_unix_ms: int = NOW) -> dict[str, object]:
    return control._read_paper_evidence_runtime_status(
        path,
        expected_owner_uid=os.getuid(),
        now_unix_ms=now_unix_ms,
        expected_evidence_cycle_interval_ms=60_000,
        expected_mint_state_max_age_ms=900_000,
        expected_mint_state_refresh_age_ms=540_000,
    )


def test_runtime_status_accepts_fresh_cycle_complete_operational_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper-evidence-status.json"
    _write(path, _document())

    status = _read(path)

    assert status["state"] == "CYCLE_COMPLETE"
    assert status["evidence_cycle_interval_ms"] == 60_000
    assert status["mint_state_max_age_ms"] == 900_000
    assert status["mint_state_refresh_age_ms"] == 540_000
    assert status["provider_failures_last_cycle"] == 0
    assert status["helius_requests_limit"] == 500
    assert status["helius_requests_remaining"] == 479
    assert status["helius_budget_exhausted"] is False


@pytest.mark.parametrize(
    ("overrides", "match"),
    (
        ({"generated_at_unix_ms": NOW + 30_001}, "future"),
        ({"generated_at_unix_ms": NOW - 240_001}, "stale"),
        ({"state": "STARTED", "completed_cycle_count": 0, "cycle_as_of_unix_ms": None}, "cycle"),
        ({"provider_failures_last_cycle": 1}, "provider"),
        (
            {
                "helius_requests_attempted": 500,
                "helius_requests_remaining": 0,
                "helius_budget_exhausted": True,
            },
            "budget",
        ),
        ({"evidence_cycle_interval_ms": 30_000}, "interval"),
        ({"mint_state_max_age_ms": 899_999}, "max age"),
        ({"mint_state_refresh_age_ms": 539_999}, "refresh age"),
        ({"helius_requests_remaining": 478}, "budget"),
    ),
)
def test_runtime_status_rejects_untrusted_or_unhealthy_operational_state(
    tmp_path: Path,
    overrides: dict[str, object],
    match: str,
) -> None:
    path = tmp_path / "paper-evidence-status.json"
    _write(path, _document(**overrides))

    with pytest.raises(control.MintStateAcceptanceControlError, match=match):
        _read(path)


def test_runtime_status_requires_private_regular_current_user_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper-evidence-status.json"
    _write(path, _document(), mode=0o644)

    with pytest.raises(control.MintStateAcceptanceControlError, match="0600"):
        _read(path)


def test_runtime_status_rejects_unknown_fields_and_noncanonical_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper-evidence-status.json"
    document = _document(unexpected="nope")
    _write(path, document)

    with pytest.raises(control.MintStateAcceptanceControlError, match="keys"):
        _read(path)

    path.write_text(json.dumps(_document(), indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(control.MintStateAcceptanceControlError, match="canonical"):
        _read(path)
