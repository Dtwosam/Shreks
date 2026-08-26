from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.dashboard.config import load_dashboard_runtime_config
from shreks_brain.dashboard.http import DashboardApplication
from shreks_brain.risk_control import (
    OperatorRiskControlCommand,
    OperatorRiskControlSource,
    initialize_operator_risk_control_state,
    load_operator_risk_control_state,
)

from test_g5_dashboard_config import _env
from test_g5_dashboard_http import _auth


_CSRF = "g7-test-csrf-token-with-sufficient-entropy-shape"


def _controlled_application(tmp_path: Path):
    state_path = tmp_path / "control" / "operator-risk-control.json"
    state_path.parent.mkdir()
    initialize_operator_risk_control_state(state_path, observed_at_unix_ms=100)
    env, password_file = _env(tmp_path)
    env["SHREKS_PAPER_CAMPAIGN_RISK_CONTROL_PATH"] = str(state_path)
    config = load_dashboard_runtime_config(env)
    password = password_file.read_bytes().rstrip(b"\r\n")
    app = DashboardApplication(
        config,
        password,
        csrf_token=_CSRF,
        clock_unix_ms=lambda: 200,
    )
    auth = {"Authorization": _auth(config.username, password)}
    return app, config, state_path, auth


def _post_headers(auth: dict[str, str], csrf: str = _CSRF) -> dict[str, str]:
    return {
        **auth,
        "Content-Type": "application/json",
        "X-Shreks-CSRF": csrf,
    }


def test_operator_controls_get_requires_auth_and_returns_revision_plus_csrf(tmp_path: Path) -> None:
    app, _config, _path, auth = _controlled_application(tmp_path)

    unauthenticated = app.dispatch("GET", "/api/v1/operator-controls", {})
    response = app.dispatch("GET", "/api/v1/operator-controls", auth)

    assert unauthenticated.status == 401
    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["revision"] == 0
    assert payload["halt_new_entries"] is False
    assert payload["kill_switch_active"] is False
    assert payload["csrf_token"] == _CSRF
    assert "password" not in response.body.decode("utf-8").lower()


def test_dashboard_halt_requires_valid_csrf_and_does_not_mutate_on_failure(tmp_path: Path) -> None:
    app, _config, state_path, auth = _controlled_application(tmp_path)
    body = b'{"expected_revision":0}'

    missing = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        {**auth, "Content-Type": "application/json"},
        body,
    )
    wrong = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        _post_headers(auth, "wrong-token"),
        body,
    )

    assert missing.status == 403
    assert wrong.status == 403
    assert load_operator_risk_control_state(state_path).revision == 0


def test_dashboard_halt_is_revision_checked_and_persists_fixed_audit_reason(tmp_path: Path) -> None:
    app, _config, state_path, auth = _controlled_application(tmp_path)
    headers = _post_headers(auth)

    response = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        headers,
        b'{"expected_revision":0}',
    )
    replay = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        headers,
        b'{"expected_revision":0}',
    )

    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["revision"] == 1
    assert payload["halt_new_entries"] is True
    assert payload["kill_switch_active"] is False
    assert "csrf_token" not in payload
    assert replay.status == 409

    persisted = load_operator_risk_control_state(state_path)
    assert persisted.revision == 1
    assert persisted.last_command is OperatorRiskControlCommand.HALT_NEW_ENTRIES
    assert persisted.last_source is OperatorRiskControlSource.DASHBOARD
    assert persisted.last_reason == "authenticated dashboard halt"


def test_dashboard_emergency_kill_latches_existing_halt_and_persists_fixed_reason(tmp_path: Path) -> None:
    app, _config, state_path, auth = _controlled_application(tmp_path)
    headers = _post_headers(auth)
    first = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        headers,
        b'{"expected_revision":0}',
    )
    assert first.status == 200

    response = app.dispatch(
        "POST",
        "/api/v1/operator-controls/emergency-kill",
        headers,
        b'{"expected_revision":1}',
    )

    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["revision"] == 2
    assert payload["halt_new_entries"] is True
    assert payload["kill_switch_active"] is True
    persisted = load_operator_risk_control_state(state_path)
    assert persisted.last_command is OperatorRiskControlCommand.EMERGENCY_KILL_SWITCH
    assert persisted.last_reason == "authenticated dashboard emergency kill"


@pytest.mark.parametrize(
    "body",
    (
        b"{}",
        b'{"expected_revision":true}',
        b'{"expected_revision":-1}',
        b'{"expected_revision":0,"reason":"browser supplied"}',
        b"not-json",
        b"[]",
    ),
)
def test_dashboard_control_body_is_exact_and_malformed_requests_do_not_mutate(
    tmp_path: Path,
    body: bytes,
) -> None:
    app, _config, state_path, auth = _controlled_application(tmp_path)

    response = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        _post_headers(auth),
        body,
    )

    assert response.status == 400
    assert load_operator_risk_control_state(state_path).revision == 0


@pytest.mark.parametrize(
    "target",
    (
        "/api/v1/operator-controls/reset-kill-switch",
        "/api/v1/operator-controls/clear-entry-halt",
        "/api/v1/operator-controls/resume",
        "/api/v1/operator-controls/live-enable",
    ),
)
def test_dashboard_exposes_no_authority_increasing_control_route(
    tmp_path: Path,
    target: str,
) -> None:
    app, _config, state_path, auth = _controlled_application(tmp_path)

    response = app.dispatch("POST", target, _post_headers(auth), b'{"expected_revision":0}')

    assert response.status == 405
    assert load_operator_risk_control_state(state_path).revision == 0


def test_unauthenticated_control_post_is_rejected_before_csrf_or_state_access(tmp_path: Path) -> None:
    app, _config, state_path, _auth_headers = _controlled_application(tmp_path)

    response = app.dispatch(
        "POST",
        "/api/v1/operator-controls/emergency-kill",
        {"Content-Type": "application/json", "X-Shreks-CSRF": _CSRF},
        b'{"expected_revision":0}',
    )

    assert response.status == 401
    assert load_operator_risk_control_state(state_path).revision == 0


def test_control_endpoints_are_unavailable_when_no_control_path_is_configured(tmp_path: Path) -> None:
    env, password_file = _env(tmp_path)
    config = load_dashboard_runtime_config(env)
    password = password_file.read_bytes().rstrip(b"\r\n")
    app = DashboardApplication(config, password, csrf_token=_CSRF, clock_unix_ms=lambda: 200)
    auth = {"Authorization": _auth(config.username, password)}

    get_response = app.dispatch("GET", "/api/v1/operator-controls", auth)
    post_response = app.dispatch(
        "POST",
        "/api/v1/operator-controls/halt-new-entries",
        _post_headers(auth),
        b'{"expected_revision":0}',
    )

    assert get_response.status == 503
    assert post_response.status == 503
