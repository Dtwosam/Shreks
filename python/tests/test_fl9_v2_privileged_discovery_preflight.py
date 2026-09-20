from __future__ import annotations

import importlib
import os
from pathlib import Path
import stat

import pytest


def test_privileged_preflight_reads_nested_deploy_owned_marker_then_drops_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_privileged_discovery_preflight"
    )

    marker_root = tmp_path / "shm"
    marker_root.mkdir()
    request_id = "deploy-123-1"
    exchange = (
        marker_root
        / f"shreks-fl9-v2-discovery.{request_id}.result.d"
    )
    exchange.mkdir()
    exchange.chmod(0o733)
    marker = exchange / f"shreks-fl9-v2-discovery.{request_id}.request"
    marker.write_text("{}\n", encoding="utf-8")
    marker.chmod(0o644)

    events: list[object] = []
    result = {
        "schema_name": "shreks.fl9_v2_discovery_control_result",
        "schema_version": 1,
        "request_id": request_id,
        "expected_release_sha": "1" * 40,
        "observed_release_sha": "1" * 40,
        "status": "HOLD_NO_COMPATIBLE",
    }

    monkeypatch.setattr(
        preflight,
        "process_fl9_v2_discovery_request",
        lambda path, **kwargs: events.append(("process", Path(path), kwargs)) or result,
    )
    monkeypatch.setattr(
        preflight,
        "_drop_to_runtime_identity",
        lambda: events.append("drop"),
    )
    monkeypatch.setattr(
        preflight,
        "publish_fl9_v2_discovery_control_result",
        lambda value, **kwargs: events.append(("publish", value, kwargs)) or True,
    )
    monkeypatch.setattr(
        preflight,
        "emit_fl9_v2_discovery_control_result",
        lambda value: events.append(("emit", value)),
    )

    count = preflight.run_privileged_discovery_preflight(
        marker_directory=marker_root,
        expected_exchange_owner_uid=os.getuid(),
    )

    assert count == 1
    assert events[0][0] == "process"
    assert events[0][1] == marker
    assert events[0][2]["receipt_root"] is None
    assert events[1] == "drop"
    assert events[2][0] == "publish"
    assert events[2][2]["marker_directory"] == marker_root
    assert events[2][2]["expected_exchange_owner_uid"] == os.getuid()
    assert events[3] == ("emit", result)


def test_privileged_preflight_ignores_wrong_mode_and_symlink_exchanges(
    tmp_path: Path,
) -> None:
    preflight = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_privileged_discovery_preflight"
    )

    marker_root = tmp_path / "shm"
    marker_root.mkdir()

    wrong = marker_root / "shreks-fl9-v2-discovery.deploy-1-1.result.d"
    wrong.mkdir()
    wrong.chmod(0o755)
    (wrong / "shreks-fl9-v2-discovery.deploy-1-1.request").write_text(
        "{}\n",
        encoding="utf-8",
    )

    real = tmp_path / "real"
    real.mkdir()
    real.chmod(0o733)
    alias = marker_root / "shreks-fl9-v2-discovery.deploy-2-1.result.d"
    alias.symlink_to(real, target_is_directory=True)

    assert preflight._startup_request_markers(
        marker_root,
        expected_exchange_owner_uid=os.getuid(),
    ) == ()


def test_drop_to_runtime_identity_clears_groups_and_permanently_drops_uid_gid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_privileged_discovery_preflight"
    )

    class Account:
        pw_name = "shreks"
        pw_uid = 1234
        pw_gid = 2345

    events: list[object] = []
    monkeypatch.setattr(preflight.pwd, "getpwnam", lambda _name: Account())
    monkeypatch.setattr(preflight.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        preflight.os,
        "initgroups",
        lambda name, gid: events.append(("initgroups", name, gid)),
    )
    monkeypatch.setattr(
        preflight.os,
        "setgid",
        lambda gid: events.append(("setgid", gid)),
    )
    monkeypatch.setattr(
        preflight.os,
        "setuid",
        lambda uid: events.append(("setuid", uid)),
    )

    preflight._drop_to_runtime_identity()

    assert events == [
        ("initgroups", "shreks", 2345),
        ("setgid", 2345),
        ("setuid", 1234),
    ]
