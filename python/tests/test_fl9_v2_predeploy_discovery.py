from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _REPO_ROOT
    / "python"
    / "src"
    / "shreks_brain"
    / "telemetry"
    / "fl9_v2_predeploy_discovery.py"
)


def test_privileged_predeploy_discovery_helper_exists() -> None:
    assert _MODULE_PATH.is_file()


@pytest.mark.skipif(not _MODULE_PATH.exists(), reason="intentional RED: helper not implemented")
def test_privileged_predeploy_helper_reads_before_irreversible_drop_then_publishes_as_shreks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_predeploy_discovery"
    )
    events: list[object] = []
    result = {
        "schema_name": "shreks.fl9_v2_discovery_control_result",
        "schema_version": 1,
        "request_id": "gha-123-1",
        "expected_release_sha": "1" * 40,
        "observed_release_sha": "1" * 40,
        "status": "HOLD_NO_COMPATIBLE",
    }

    def process(**kwargs):
        events.append(
            (
                "process",
                kwargs["marker_directory"],
                kwargs["persist_receipts"],
            )
        )
        return (result,)

    def publish(value, **kwargs):
        events.append(("publish", value, kwargs["marker_directory"]))
        return True

    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        helper.pwd,
        "getpwnam",
        lambda name: (
            events.append(("identity", name))
            or SimpleNamespace(pw_uid=1234, pw_gid=5678)
        ),
    )
    monkeypatch.setattr(helper.os, "setgroups", lambda groups: events.append(("groups", groups)))
    monkeypatch.setattr(helper.os, "setgid", lambda gid: events.append(("gid", gid)))
    monkeypatch.setattr(helper.os, "setuid", lambda uid: events.append(("uid", uid)))
    monkeypatch.setattr(
        helper,
        "process_pending_fl9_v2_discovery_requests",
        process,
    )
    monkeypatch.setattr(
        helper,
        "publish_fl9_v2_discovery_control_result",
        publish,
    )

    assert helper.run_predeploy_discovery() == 0
    assert events == [
        ("process", Path("/var/tmp"), False),
        ("identity", "shreks"),
        ("groups", []),
        ("gid", 5678),
        ("uid", 1234),
        ("publish", result, Path("/dev/shm")),
    ]


@pytest.mark.skipif(not _MODULE_PATH.exists(), reason="intentional RED: helper not implemented")
def test_privileged_predeploy_helper_is_fail_closed_and_non_mutating_without_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_predeploy_discovery"
    )
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        helper,
        "process_pending_fl9_v2_discovery_requests",
        lambda **kwargs: (),
    )
    monkeypatch.setattr(
        helper,
        "publish_fl9_v2_discovery_control_result",
        lambda *_args, **_kwargs: pytest.fail("nothing should be published"),
    )
    monkeypatch.setattr(
        helper.pwd,
        "getpwnam",
        lambda _name: pytest.fail("identity drop is unnecessary without controls"),
    )

    assert helper.run_predeploy_discovery() == 0


@pytest.mark.skipif(not _MODULE_PATH.exists(), reason="intentional RED: helper not implemented")
def test_privileged_predeploy_helper_reports_failure_without_exposing_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = importlib.import_module(
        "shreks_brain.telemetry.fl9_v2_predeploy_discovery"
    )
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)

    def fail(**_kwargs):
        raise RuntimeError("sensitive protected path detail")

    monkeypatch.setattr(
        helper,
        "process_pending_fl9_v2_discovery_requests",
        fail,
    )

    assert helper.run_predeploy_discovery() == 1
    captured = capsys.readouterr()
    assert "sensitive protected path detail" not in captured.out
    assert "sensitive protected path detail" not in captured.err
