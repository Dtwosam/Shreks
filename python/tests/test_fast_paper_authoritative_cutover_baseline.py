from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_authoritative_cutover_baseline as baseline
from shreks_brain.fast_paper_runtime.codec import (
    build_fast_paper_runtime_state,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
)

from test_fast_paper_shadow_decision import _manifest


_RELEASE_SHA = "a" * 40


def _quiescent() -> baseline.HostCommandResult:
    return baseline.HostCommandResult(
        returncode=0,
        stdout=(
            "ActiveState=inactive\n"
            "SubState=dead\n"
            "MainPID=0\n"
            "NRestarts=0\n"
            "InvocationID=\n"
        ),
        stderr="",
    )


def _active() -> baseline.HostCommandResult:
    return baseline.HostCommandResult(
        returncode=0,
        stdout=(
            "ActiveState=active\n"
            "SubState=running\n"
            "MainPID=123\n"
            "NRestarts=0\n"
            "InvocationID=abcd\n"
        ),
        stderr="",
    )


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    manifest = _manifest(tmp_path)
    write_fast_paper_runtime_manifest(
        manifest,
        tmp_path / "manifest.json",
    )
    source_state = build_fast_paper_runtime_state(
        manifest,
        cursor=None,
    )
    write_fast_paper_runtime_state(
        source_state,
        manifest.checkpoint_path,
    )
    decision_root = tmp_path / "authoritative-decision"
    decision_root.mkdir()
    destination = decision_root / "runtime-state.json"
    env_path = tmp_path / "authoritative.env"
    env_path.write_text("sealed\n", encoding="utf-8")

    monkeypatch.setattr(
        baseline,
        "read_fast_paper_authoritative_cutover_environment",
        lambda _path: {"sealed": "environment"},
    )
    monkeypatch.setattr(
        baseline,
        "validate_fast_paper_authoritative_cutover_environment",
        lambda _env, _manifest, authoritative_database_path: SimpleNamespace(
            decision_config=SimpleNamespace(
                checkpoint_path=destination,
                evidence_directory=decision_root,
            )
        ),
    )
    monkeypatch.setattr(baseline, "_require_root", lambda: None)
    monkeypatch.setattr(
        baseline,
        "_service_identity",
        lambda: (os.geteuid(), os.getegid()),
    )
    monkeypatch.setattr(baseline.os, "fchown", lambda *_args: None)
    return manifest, source_state, env_path, decision_root, destination


def test_provision_baseline_copies_exact_authenticated_state_write_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        manifest,
        source_state,
        env_path,
        decision_root,
        destination,
    ) = _setup(tmp_path, monkeypatch)
    receipt_path = tmp_path / "receipts" / "baseline.json"
    calls: list[tuple[str, ...]] = []

    def command_runner(command: tuple[str, ...]):
        calls.append(command)
        return _quiescent()

    receipt = baseline.provision_fast_paper_authoritative_cutover_baseline(
        fast_manifest_path=tmp_path / "manifest.json",
        authoritative_runtime_env_path=env_path,
        receipt_path=receipt_path,
        expected_release_sha=_RELEASE_SHA,
        command_runner=command_runner,
        clock_unix_ms=lambda: 12_345,
    )

    assert destination.read_bytes() == Path(
        manifest.checkpoint_path
    ).read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert receipt["state"] == "AUTHORITATIVE_DECISION_BASELINE_PROVISIONED"
    assert (
        receipt["decision_state_fingerprint_sha256"]
        == source_state.state_fingerprint_sha256
    )
    assert receipt["decision_cursor_sequence"] is None
    assert receipt["baseline_replayed"] is False
    assert receipt["shadow_active_state"] == "inactive"
    assert receipt["shadow_main_pid"] == 0
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert receipt["service_control_authority"] == "NOT_GRANTED"
    assert receipt["authoritative_paper_mutation"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"
    assert calls == [
        baseline._SHOW_COMMAND,
        baseline._SHOW_COMMAND,
        baseline._SHOW_COMMAND,
    ]

    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    material = dict(document)
    claimed = material.pop("receipt_fingerprint_sha256")
    assert claimed == hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert tuple(decision_root.iterdir()) == (destination,)

    replay = baseline.provision_fast_paper_authoritative_cutover_baseline(
        fast_manifest_path=tmp_path / "manifest.json",
        authoritative_runtime_env_path=env_path,
        receipt_path=tmp_path / "receipts" / "second.json",
        expected_release_sha=_RELEASE_SHA,
        command_runner=command_runner,
        clock_unix_ms=lambda: 12_346,
    )
    assert replay["baseline_replayed"] is True
    assert destination.read_bytes() == Path(
        manifest.checkpoint_path
    ).read_bytes()


def test_active_shadow_fails_before_authoritative_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _manifest_value,
        _source_state,
        env_path,
        _decision_root,
        destination,
    ) = _setup(tmp_path, monkeypatch)

    with pytest.raises(
        baseline.FastPaperAuthoritativeCutoverBaselineError,
        match="inactive/dead",
    ):
        baseline.provision_fast_paper_authoritative_cutover_baseline(
            fast_manifest_path=tmp_path / "manifest.json",
            authoritative_runtime_env_path=env_path,
            receipt_path=tmp_path / "receipt.json",
            expected_release_sha=_RELEASE_SHA,
            command_runner=lambda _command: _active(),
        )

    assert not destination.exists()


def test_shadow_state_change_during_authentication_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        manifest,
        _source_state,
        env_path,
        _decision_root,
        destination,
    ) = _setup(tmp_path, monkeypatch)
    source = Path(manifest.checkpoint_path)
    calls = {"count": 0}

    def command_runner(_command: tuple[str, ...]):
        calls["count"] += 1
        if calls["count"] == 2:
            source.touch()
        return _quiescent()

    with pytest.raises(
        baseline.FastPaperAuthoritativeCutoverBaselineError,
        match="changed during",
    ):
        baseline.provision_fast_paper_authoritative_cutover_baseline(
            fast_manifest_path=tmp_path / "manifest.json",
            authoritative_runtime_env_path=env_path,
            receipt_path=tmp_path / "receipt.json",
            expected_release_sha=_RELEASE_SHA,
            command_runner=command_runner,
        )

    assert not destination.exists()


def test_authoritative_decision_root_must_be_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _manifest_value,
        _source_state,
        env_path,
        decision_root,
        destination,
    ) = _setup(tmp_path, monkeypatch)
    (decision_root / "shadow-stale.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        baseline.FastPaperAuthoritativeCutoverBaselineError,
        match="must be empty",
    ):
        baseline.provision_fast_paper_authoritative_cutover_baseline(
            fast_manifest_path=tmp_path / "manifest.json",
            authoritative_runtime_env_path=env_path,
            receipt_path=tmp_path / "receipt.json",
            expected_release_sha=_RELEASE_SHA,
            command_runner=lambda _command: _quiescent(),
        )

    assert not destination.exists()


def test_baseline_provisioner_has_read_only_systemd_authority() -> None:
    source = Path(baseline.__file__).read_text(encoding="utf-8")

    assert '"systemctl",' in source
    assert '"show",' in source
    for forbidden in (
        '"start"',
        '"stop"',
        '"restart"',
        '"daemon-reload"',
        "subprocess.Popen",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "run_fast_paper_authoritative_execution",
        "commit_fast_paper_authoritative_transition_atomically",
    ):
        assert forbidden not in source
