from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

import shreks_brain.fast_paper_release_upgrade as upgrade


def _bootstrap(
    *,
    decision_sequence: int | None,
    execution_sequence: int | None,
    pending_buy: object | None = None,
):
    cursor = (
        None
        if decision_sequence is None
        else SimpleNamespace(decision_sequence=decision_sequence)
    )
    return SimpleNamespace(
        decision_bootstrap=SimpleNamespace(
            state=SimpleNamespace(cursor=cursor),
        ),
        execution_bootstrap=SimpleNamespace(
            checkpoint=SimpleNamespace(
                state=SimpleNamespace(pending_buy=pending_buy),
            ),
            runtime_state=SimpleNamespace(
                last_processed_source_sequence=execution_sequence,
            ),
        ),
    )


def test_clean_release_boundary_requires_equal_cursors_and_no_pending_buy() -> None:
    upgrade._require_clean_handoff_boundary(
        _bootstrap(
            decision_sequence=17,
            execution_sequence=17,
        )
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="equal decision/execution cursors",
    ):
        upgrade._require_clean_handoff_boundary(
            _bootstrap(
                decision_sequence=18,
                execution_sequence=17,
            )
        )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="pending BUY",
    ):
        upgrade._require_clean_handoff_boundary(
            _bootstrap(
                decision_sequence=17,
                execution_sequence=17,
                pending_buy=object(),
            )
        )


def test_materialize_target_fast_tools_uses_verified_wheel_payloads_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sha = "b" * 40
    release = tmp_path / sha
    (release / ".venv").mkdir(parents=True)
    wheel = release / "wheelhouse" / "shreks_brain.whl"
    wheel.parent.mkdir()

    payloads = {
        "shreks-fast-campaign-decision": b"decision",
        "shreks-fast-entry-authority": b"entry",
        "export_fast_training_features": b"training",
        upgrade.FAST_RUNTIME_FEATURE_TOOL_NAME: b"runtime",
    }
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in upgrade.FAST_PROOF_TOOL_NAMES:
            archive.writestr(
                "shreks_brain/_sealed_fast_tools/"
                f"{name}.bin",
                payloads[name],
            )
        archive.writestr(
            "shreks_brain/_sealed_fast_runtime_tools/"
            f"{upgrade.FAST_RUNTIME_FEATURE_TOOL_NAME}.bin",
            payloads[upgrade.FAST_RUNTIME_FEATURE_TOOL_NAME],
        )

    proof = SimpleNamespace(
        tools=tuple(
            SimpleNamespace(
                name=name,
                sha256=hashlib.sha256(payloads[name]).hexdigest(),
            )
            for name in upgrade.FAST_PROOF_TOOL_NAMES
        )
    )
    runtime = SimpleNamespace(
        sha256=hashlib.sha256(
            payloads[upgrade.FAST_RUNTIME_FEATURE_TOOL_NAME]
        ).hexdigest()
    )
    monkeypatch.setattr(
        upgrade,
        "verify_fast_proof_tools_wheel",
        lambda *_args, **_kwargs: proof,
    )
    monkeypatch.setattr(
        upgrade,
        "verify_fast_runtime_tools_wheel",
        lambda *_args, **_kwargs: runtime,
    )

    first = upgrade._materialize_target_fast_tools(
        release,
        wheel,
        expected_source_sha=sha,
        expected_platform="x86_64-unknown-linux-gnu",
    )
    second = upgrade._materialize_target_fast_tools(
        release,
        wheel,
        expected_source_sha=sha,
        expected_platform="x86_64-unknown-linux-gnu",
    )

    assert second == first
    assert set(first) == {
        *upgrade.FAST_PROOF_TOOL_NAMES,
        upgrade.FAST_RUNTIME_FEATURE_TOOL_NAME,
    }
    for name, path in first.items():
        assert path.read_bytes() == payloads[name]
        assert path.stat().st_mode & 0o777 == 0o755
        assert str(path).startswith(str((release / ".venv").resolve()))


def test_materialize_target_fast_tools_rejects_symlinked_tool_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sha = "b" * 40
    release = tmp_path / sha
    (release / ".venv").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (release / ".venv" / "fast-paper-tools").symlink_to(outside)
    wheel = release / "wheelhouse" / "shreks_brain.whl"
    wheel.parent.mkdir()
    wheel.write_bytes(b"unused")

    monkeypatch.setattr(
        upgrade,
        "verify_fast_proof_tools_wheel",
        lambda *_args, **_kwargs: SimpleNamespace(tools=()),
    )
    monkeypatch.setattr(
        upgrade,
        "verify_fast_runtime_tools_wheel",
        lambda *_args, **_kwargs: SimpleNamespace(sha256="0" * 64),
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="symlinked tool root",
    ):
        upgrade._materialize_target_fast_tools(
            release,
            wheel,
            expected_source_sha=sha,
            expected_platform="x86_64-unknown-linux-gnu",
        )


def test_target_file_retargets_release_local_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / ("a" * 40)
    target = tmp_path / ("b" * 40)
    relative = Path("python/bin/fast-decision")
    (source / relative).parent.mkdir(parents=True)
    (target / relative).parent.mkdir(parents=True)
    (source / relative).write_text("same", encoding="utf-8")
    (target / relative).write_text("same", encoding="utf-8")

    resolved = upgrade._target_file(
        source / relative,
        source,
        target,
        allow_external=False,
    )

    assert resolved == (target / relative).resolve()


def test_target_file_rejects_external_binary_but_allows_external_champion(
    tmp_path: Path,
) -> None:
    source = tmp_path / ("a" * 40)
    target = tmp_path / ("b" * 40)
    source.mkdir()
    target.mkdir()
    external = tmp_path / "champion.json"
    external.write_text("{}", encoding="utf-8")

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="escaped current release",
    ):
        upgrade._target_file(
            external,
            source,
            target,
            allow_external=False,
        )

    assert (
        upgrade._target_file(
            external,
            source,
            target,
            allow_external=True,
        )
        == external.resolve()
    )


def test_archive_release_bound_sources_moves_everything_except_checkpoint(
    tmp_path: Path,
) -> None:
    roots = {}
    for name in (
        "decision",
        "execution",
        "buy",
        "usd",
        "reduction",
        "retry",
    ):
        root = tmp_path / "active" / name
        root.mkdir(parents=True)
        roots[name] = root
    checkpoint = roots["decision"] / "runtime-state.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    evidence = roots["decision"] / "shadow-1.json"
    evidence.write_text("{}\n", encoding="utf-8")
    source = roots["execution"] / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    config = SimpleNamespace(
        decision_config=SimpleNamespace(
            evidence_directory=roots["decision"],
            checkpoint_path=checkpoint,
        ),
        execution_config=SimpleNamespace(
            source_directory=roots["execution"],
        ),
        buy_authority_source_directory=roots["buy"],
        quote_usd_source_directory=roots["usd"],
        reduction_source_directory=roots["reduction"],
        pending_buy_retry_source_directory=roots["retry"],
    )
    archive = tmp_path / "history" / "run-1"

    moved = upgrade._archive_release_bound_sources(
        config,
        archive,
    )

    assert checkpoint.is_file()
    assert not evidence.exists()
    assert not source.exists()
    assert len(moved) == 2
    assert (archive / "decision" / evidence.name).is_file()
    assert (archive / "execution" / source.name).is_file()


def test_release_upgrade_command_runner_rejects_unreviewed_systemd_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    for forbidden in (
        ("systemctl", "restart", upgrade._UNIT),
        ("systemctl", "enable", upgrade._UNIT),
        ("systemctl", "stop", "other.service"),
        ("systemctl", "start", upgrade._UNIT),
        ("systemctl", "show", "other.service", "--property=MainPID", "--no-pager"),
    ):
        with pytest.raises(
            upgrade.FastPaperReleaseUpgradeError,
            match="allowlist",
        ):
            upgrade._default_command_runner(forbidden)


def test_release_upgrade_source_has_no_legacy_trade_or_live_authority() -> None:
    source = Path(upgrade.__file__).read_text(encoding="utf-8")

    for required in (
        "initialize_fast_paper_authoritative_release_handoff",
        "build_fast_paper_release_authorization",
        "REVOKED_MANUAL_RECOVERY",
        "signing_submission_authority",
        "live_authority",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.observer_campaign.runtime",
        "score_candidate",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        '("systemctl", "restart"',
        '("systemctl", "enable"',
        '("systemctl", "disable"',
    ):
        assert forbidden not in source


def test_pre_start_restore_recovers_stopped_source_bytes_archive_and_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_release = tmp_path / ("a" * 40)
    target_release = tmp_path / ("b" * 40)
    source_release.mkdir()
    target_release.mkdir()
    current = tmp_path / "current"
    current.symlink_to(target_release)

    systemd = tmp_path / "systemd"
    systemd.mkdir()
    protected_path = tmp_path / "protected.json"
    protected_path.write_bytes(b"target")
    unit_path = systemd / upgrade._UNIT
    unit_path.write_bytes(b"target-unit")
    archive_source = tmp_path / "active" / "decision.json"
    archive_source.parent.mkdir()
    archive = tmp_path / "history" / "run-1" / "decision" / "decision.json"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"source-evidence")

    paths = upgrade.FastPaperReleaseUpgradePaths(
        current_link=current,
        systemd_dir=systemd,
        authoritative_config_path=tmp_path / "authoritative.env",
        history_root=tmp_path / "history",
        receipt_root=tmp_path / "receipts",
        proc_root=tmp_path / "proc",
    )
    uid = os.geteuid()
    gid = os.getegid()
    monkeypatch.setattr(upgrade.os, "fchown", lambda *_args: None)
    protected = (
        upgrade.ProtectedFileSnapshot(
            path=protected_path,
            payload=b"source",
            uid=uid,
            gid=gid,
            mode=0o600,
        ),
    )
    units = (
        upgrade.ProtectedFileSnapshot(
            path=unit_path,
            payload=b"source-unit",
            uid=uid,
            gid=gid,
            mode=0o644,
        ),
    )
    archived = (
        upgrade.ArchivedMember(
            source=archive_source,
            archive=archive,
        ),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return upgrade.HostCommandResult(0, "", "")

    upgrade._restore_pre_start(
        paths,
        protected=protected,
        units=units,
        archived=archived,
        source_release=source_release,
        runner=runner,
        current_switched=True,
        artifacts_rotated=True,
    )

    assert protected_path.read_bytes() == b"source"
    assert unit_path.read_bytes() == b"source-unit"
    assert archive_source.read_bytes() == b"source-evidence"
    assert not archive.exists()
    assert current.resolve() == source_release.resolve()
    assert calls == [
        ("systemctl", "daemon-reload"),
        ("systemctl", "start", upgrade._TARGET),
        *[
            ("systemctl", "is-active", "--quiet", unit)
            for unit in upgrade._RUNTIME_UNITS
        ],
    ]


def test_post_start_recovery_helpers_quiesce_every_runtime_and_revoke_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_text("{}\n", encoding="utf-8")
    authorization.chmod(0o600)
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return upgrade.HostCommandResult(0, "", "")

    monkeypatch.setattr(
        upgrade,
        "_replace_preserving_metadata",
        lambda path, payload: path.write_bytes(payload),
    )

    upgrade._stop_all_runtime(runner)
    upgrade._write_revoked_authorization(
        authorization,
        target_release_source_sha="b" * 40,
        target_fast_run_id="fast-paper-release-" + "b" * 40,
        handoff_fingerprint_sha256="c" * 64,
        error=RuntimeError("boom"),
    )

    assert calls == [
        (
            "systemctl",
            "stop",
            upgrade._UNIT,
            upgrade._EVIDENCE_UNIT,
            upgrade._OBSERVE_UNIT,
        ),
        ("systemctl", "stop", upgrade._TARGET),
    ]
    payload = __import__("json").loads(
        authorization.read_text(encoding="utf-8")
    )
    assert payload["state"] == "REVOKED_MANUAL_RECOVERY"
    assert (
        payload["production_paper_cutover"]
        == "STOPPED_MANUAL_RECOVERY"
    )
    assert payload["signing_submission_authority"] == "NOT_GRANTED"
    assert payload["live_authority"] == "DISABLED"


def test_paper_show_allowlist_accepts_only_exact_provenance_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    upgrade._default_command_runner(upgrade._SHOW_COMMAND)

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="allowlist",
    ):
        upgrade._default_command_runner(
            (
                "systemctl",
                "show",
                upgrade._UNIT,
                "--property=Environment",
                "--no-pager",
            )
        )
