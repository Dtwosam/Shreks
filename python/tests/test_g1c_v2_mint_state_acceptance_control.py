from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import shreks_brain.telemetry.g1c_v2_mint_state_acceptance_control as control
from shreks_brain.telemetry.g1c_v2_mint_state_acceptance import (
    MintStateAcceptanceError,
)


SHA = "1" * 40
REQUEST_ID = "gha-123-1-mint"
NOW = 2_000_000


def _release_tree(tmp_path: Path) -> Path:
    releases = tmp_path / "opt" / "shreks" / "releases"
    release = releases / SHA
    release.mkdir(parents=True)
    (release / "RELEASE_MANIFEST.json").write_text(
        json.dumps(
            {
                "schema_version": "g2-release-manifest-v1",
                "source_sha": SHA,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(release)
    return current


def _write_request(marker_directory: Path, *, mode: int = 0o644) -> Path:
    document = {
        "schema_name": control.CONTROL_REQUEST_SCHEMA_NAME,
        "schema_version": control.CONTROL_REQUEST_SCHEMA_VERSION,
        "request_id": REQUEST_ID,
        "expected_release_sha": SHA,
        "created_at_unix_ms": NOW,
        "window_start_unix_ms": NOW - 60_000,
        "window_end_unix_ms": NOW,
    }
    path = marker_directory / (
        f"shreks-g1c-v2-mint-state-acceptance.{REQUEST_ID}.request"
    )
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
    return path


def _runtime_status(path: Path) -> Path:
    document = {
        "release_source_sha": SHA,
        "schema_name": "shreks.paper_evidence_runtime_status",
        "schema_version": 1,
        "state": "CYCLE_COMPLETE",
        "process_started_at_unix_ms": 1_000_000,
        "generated_at_unix_ms": NOW - 10_000,
        "completed_cycle_count": 3,
        "cycle_as_of_unix_ms": NOW - 10_000,
        "evidence_cycle_interval_ms": 60_000,
        "mint_state_max_age_ms": 900_000,
        "mint_state_refresh_age_ms": 540_000,
        "provider_failures_last_cycle": 0,
        "helius_requests_attempted": 7,
        "helius_requests_limit": 500,
        "helius_requests_remaining": 493,
        "helius_budget_exhausted": False,
        "candidates_selected_last_cycle": 2,
        "mint_states_stored_last_cycle": 1,
        "observation_authority": "DERIVED_OPERATIONAL",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
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
    path.chmod(0o600)
    return path


def _analysis() -> dict[str, object]:
    return {
        "schema_name": "shreks.g1c_v2_mint_state_acceptance",
        "schema_version": 1,
        "status": "PASS",
        "max_critical_data_age_ms": 900_000,
        "evidence_cycle_interval_ms": 60_000,
        "mint_state_refresh_age_ms": 540_000,
        "selected_observation_count": 2,
        "proactive_refresh_count": 1,
        "selected_missing_mint_count": 0,
        "selected_stale_mint_count": 0,
        "invalid_observation_count": 0,
        "max_selected_mint_age_ms": 500_000,
        "paper_run_id": "paper-run",
        "reconstructed_checkpoint_count": 1,
        "window_start_unix_ms": NOW - 60_000,
        "window_end_unix_ms": NOW,
    }


def test_trusted_request_is_release_bound_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_directory = tmp_path / "markers"
    marker_directory.mkdir()
    _write_request(marker_directory)
    current = _release_tree(tmp_path)
    runtime_status_path = _runtime_status(tmp_path / "paper-evidence-status.json")
    calls: list[tuple[object, ...]] = []

    def analyze(*args, **kwargs):
        calls.append((args, kwargs))
        return _analysis()

    monkeypatch.setattr(control, "analyze_mint_state_acceptance", analyze)

    results = control.process_pending_mint_state_acceptance_requests(
        marker_directory=marker_directory,
        database_path=tmp_path / "protected.sqlite",
        manifest_path=tmp_path / "paper-campaign.json",
        current_release_link=current,
        expected_owner_uid=os.getuid(),
        expected_marker_directory_owner_uid=os.getuid(),
        evidence_cycle_interval_ms=60_000,
        runtime_status_path=runtime_status_path,
        now_unix_ms=NOW,
    )

    assert len(results) == 1
    result = results[0]
    assert result["status"] == "PASS"
    assert result["expected_release_sha"] == SHA
    assert result["observed_release_sha"] == SHA
    assert result["observation_authority"] == "READ_ONLY"
    assert result["manifest_rotation_authority"] == "NOT_GRANTED"
    assert result["scoring_authority"] == "NOT_GRANTED"
    assert result["paper_promotion_authority"] == "BLOCKED"
    assert result["live_authority"] == "DISABLED"
    assert result["runtime_status"]["release_source_sha"] == SHA
    assert result["runtime_status"]["state"] == "CYCLE_COMPLETE"
    assert result["runtime_status"]["provider_failures_last_cycle"] == 0
    assert result["runtime_status"]["helius_budget_exhausted"] is False
    assert calls


def test_untrusted_marker_fails_without_running_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_directory = tmp_path / "markers"
    marker_directory.mkdir()
    _write_request(marker_directory, mode=0o600)

    monkeypatch.setattr(
        control,
        "analyze_mint_state_acceptance",
        lambda *_args, **_kwargs: pytest.fail("untrusted request must not analyze"),
    )

    result = control.process_pending_mint_state_acceptance_requests(
        marker_directory=marker_directory,
        expected_owner_uid=os.getuid(),
        expected_marker_directory_owner_uid=os.getuid(),
        evidence_cycle_interval_ms=60_000,
        now_unix_ms=NOW,
    )[0]

    assert result["status"] == "FAILED"
    assert result["error"]["code"] == "UNTRUSTED_MARKER"


def test_analysis_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_directory = tmp_path / "markers"
    marker_directory.mkdir()
    _write_request(marker_directory)
    current = _release_tree(tmp_path)

    def fail(*_args, **_kwargs):
        raise MintStateAcceptanceError("secret path and provider detail")

    monkeypatch.setattr(control, "analyze_mint_state_acceptance", fail)

    result = control.process_pending_mint_state_acceptance_requests(
        marker_directory=marker_directory,
        database_path=tmp_path / "protected.sqlite",
        manifest_path=tmp_path / "paper-campaign.json",
        current_release_link=current,
        expected_owner_uid=os.getuid(),
        expected_marker_directory_owner_uid=os.getuid(),
        evidence_cycle_interval_ms=60_000,
        now_unix_ms=NOW,
    )[0]

    encoded = json.dumps(result)
    assert result["status"] == "FAILED"
    assert result["error"]["code"] == "ANALYSIS_FAILED"
    assert "secret path" not in encoded


def test_result_exchange_is_canonical_and_write_once(tmp_path: Path) -> None:
    result = {
        "schema_name": control.CONTROL_RESULT_SCHEMA_NAME,
        "schema_version": control.CONTROL_RESULT_SCHEMA_VERSION,
        "request_id": REQUEST_ID,
        "status": "HOLD_INSUFFICIENT_EVIDENCE",
    }
    exchange = tmp_path / (
        f"shreks-g1c-v2-mint-state-acceptance.{REQUEST_ID}.result.d"
    )
    exchange.mkdir(mode=0o733)
    exchange.chmod(0o733)

    assert control.publish_mint_state_acceptance_control_result(
        result,
        marker_directory=tmp_path,
        expected_exchange_owner_uid=os.getuid(),
    )
    path = exchange / "result.json"
    assert path.stat().st_mode & 0o777 == 0o644
    text = path.read_text(encoding="utf-8")
    assert text == json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"

    assert control.publish_mint_state_acceptance_control_result(
        result,
        marker_directory=tmp_path,
        expected_exchange_owner_uid=os.getuid(),
    )


def test_idle_control_needs_no_paper_interval_or_deploy_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker_directory = tmp_path / "markers"
    marker_directory.mkdir()
    monkeypatch.delenv("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS", raising=False)
    monkeypatch.setattr(
        control.pwd,
        "getpwnam",
        lambda _name: pytest.fail("idle control must not resolve deploy user"),
    )

    assert control.process_pending_mint_state_acceptance_requests(
        marker_directory=marker_directory,
        expected_marker_directory_owner_uid=os.getuid(),
    ) == ()
