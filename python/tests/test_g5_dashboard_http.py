from __future__ import annotations

import base64
from dataclasses import replace
import json
from pathlib import Path

import pytest

import shreks_brain.dashboard.http as http_module
from shreks_brain.dashboard import (
    DashboardEvidenceAvailability,
    DashboardLedgerEvent,
    DashboardSnapshotSource,
    DashboardTradeDetail,
    DashboardTradeSummary,
)
from shreks_brain.dashboard.config import load_dashboard_runtime_config
from shreks_brain.dashboard.http import DashboardApplication, DashboardHTTPResponse

from test_g4_telemetry_models import _snapshot
from test_g5_dashboard_config import _env


def _config(tmp_path: Path):
    env, password_file = _env(tmp_path)
    config = load_dashboard_runtime_config(env)
    return config, password_file


def _summary(position_id: str = "position-1") -> DashboardTradeSummary:
    return DashboardTradeSummary(
        candidate_version="candidate-v1",
        position_id=position_id,
        mint="MintOne",
        setup_name="fresh_launch_continuation",
        market_regime="NORMAL",
        opened_at_unix_ms=1_000,
        closed_at_unix_ms=2_000,
        entry_notional_usd=100.0,
        turnover_usd=210.0,
        gross_pnl_usd=12.0,
        execution_friction_usd=1.0,
        explicit_cost_usd=1.0,
        net_pnl_usd=10.0,
    )


def _detail(position_id: str = "position-1") -> DashboardTradeDetail:
    unavailable = DashboardEvidenceAvailability.NOT_PERSISTED
    return DashboardTradeDetail(
        summary=_summary(position_id),
        ledger_events=(
            DashboardLedgerEvent(
                sequence=1,
                side="BUY",
                execution_state="FILLED",
                paper_execution_reason_code="FILL_COMPLETE",
                ledger_reason_code="POSITION_OPENED",
                strategy_name="fresh_launch_continuation",
                strategy_version="candidate-v1",
                score_policy_version="score-v1",
                decision_policy_version="decision-v1",
                risk_policy_version="risk-v1",
                paper_policy_version="paper-v1",
                booked_at_unix_ms=1_000,
                filled_quantity=10.0,
                filled_notional_usd=100.0,
                explicit_cost_usd=1.0,
                realized_pnl_delta_usd=0.0,
            ),
        ),
        safety_assessment=unavailable,
        feature_vector=unavailable,
        score_assessment=unavailable,
        entry_decision=unavailable,
        risk_assessment=unavailable,
        entry_quote=unavailable,
        strategic_exit_reason=unavailable,
    )


def _source() -> DashboardSnapshotSource:
    return DashboardSnapshotSource(
        telemetry=replace(_snapshot(), mode="PAPER"),
        telemetry_file_mtime_ns=123,
        trades=(_summary(),),
    )


def _auth(username: str, password: bytes) -> str:
    payload = username.encode("ascii") + b":" + password
    return "Basic " + base64.b64encode(payload).decode("ascii")


def _headers(response: DashboardHTTPResponse) -> dict[str, str]:
    return {name.lower(): value for name, value in response.headers}


def _application(tmp_path: Path) -> tuple[DashboardApplication, object, bytes]:
    config, password_file = _config(tmp_path)
    password = password_file.read_bytes().rstrip(b"\r\n")
    return DashboardApplication(config, password), config, password


def test_every_route_requires_basic_auth_and_returns_security_headers(tmp_path: Path) -> None:
    app, _config_value, _password = _application(tmp_path)

    response = app.dispatch("GET", "/", {})

    assert response.status == 401
    headers = _headers(response)
    assert headers["www-authenticate"].startswith("Basic ")
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src" in headers["content-security-policy"]


def test_auth_uses_constant_time_exact_basic_credentials(tmp_path: Path, monkeypatch) -> None:
    app, config, password = _application(tmp_path)
    calls: list[tuple[object, object]] = []
    real_compare = http_module.hmac.compare_digest

    def recording_compare(left, right):
        calls.append((left, right))
        return real_compare(left, right)

    monkeypatch.setattr(http_module.hmac, "compare_digest", recording_compare)
    monkeypatch.setattr(http_module, "load_dashboard_snapshot", lambda *_args, **_kwargs: _source())

    good = app.dispatch(
        "GET",
        "/api/v1/snapshot",
        {"Authorization": _auth(config.username, password)},
    )
    wrong_password = app.dispatch(
        "GET",
        "/api/v1/snapshot",
        {"Authorization": _auth(config.username, password + b"x")},
    )
    wrong_username = app.dispatch(
        "GET",
        "/api/v1/snapshot",
        {"Authorization": _auth(config.username + "x", password)},
    )

    assert good.status == 200
    assert wrong_password.status == 401
    assert wrong_username.status == 401
    assert len(calls) >= 3


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer abc",
        "Basic !!!",
        "Basic",
        "Basic Zm9v",
        "basic Zm9vOmJhcg==",
    ],
)
def test_malformed_or_noncanonical_authorization_is_rejected(
    tmp_path: Path,
    authorization: str,
) -> None:
    app, _config_value, _password = _application(tmp_path)

    response = app.dispatch("GET", "/api/v1/snapshot", {"Authorization": authorization})

    assert response.status == 401


def test_authenticated_json_routes_are_read_only_and_bounded(tmp_path: Path, monkeypatch) -> None:
    app, config, password = _application(tmp_path)
    authorization = {"Authorization": _auth(config.username, password)}
    calls: list[tuple[str, object]] = []

    def fake_snapshot(source_config, *, max_trades: int):
        calls.append(("snapshot", max_trades))
        return _source()

    def fake_trade(source_config, position_id: str):
        calls.append(("trade", position_id))
        return _detail(position_id) if position_id == "position-1" else None

    monkeypatch.setattr(http_module, "load_dashboard_snapshot", fake_snapshot)
    monkeypatch.setattr(http_module, "load_dashboard_trade", fake_trade)

    snapshot_response = app.dispatch("GET", "/api/v1/snapshot", authorization)
    trades_response = app.dispatch("GET", "/api/v1/trades", authorization)
    detail_response = app.dispatch("GET", "/api/v1/trades/position-1", authorization)
    missing_response = app.dispatch("GET", "/api/v1/trades/missing", authorization)

    assert snapshot_response.status == 200
    assert trades_response.status == 200
    assert detail_response.status == 200
    assert missing_response.status == 404
    assert ("snapshot", config.max_trades) in calls
    assert ("trade", "position-1") in calls

    snapshot_payload = json.loads(snapshot_response.body)
    trades_payload = json.loads(trades_response.body)
    detail_payload = json.loads(detail_response.body)
    assert snapshot_payload["telemetry"]["mode"] == "PAPER"
    assert snapshot_payload["telemetry_file_mtime_ns"] == 123
    assert trades_payload["trades"][0]["position_id"] == "position-1"
    assert detail_payload["summary"]["position_id"] == "position-1"
    assert detail_payload["safety_assessment"] == "NOT_PERSISTED"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_methods_are_never_routed(tmp_path: Path, method: str) -> None:
    app, config, password = _application(tmp_path)

    response = app.dispatch(
        method,
        "/api/v1/trades/position-1",
        {"Authorization": _auth(config.username, password)},
    )

    assert response.status == 405
    assert _headers(response)["allow"] == "GET"


def test_source_failures_map_to_generic_503_without_secret_or_exception_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, config, password = _application(tmp_path)
    secret = password.decode("ascii")

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"sensitive internal failure: {secret}")

    monkeypatch.setattr(http_module, "load_dashboard_snapshot", fail)

    response = app.dispatch(
        "GET",
        "/api/v1/snapshot",
        {"Authorization": _auth(config.username, password)},
    )

    assert response.status == 503
    body = response.body.decode("utf-8")
    assert secret not in body
    assert str(config.password_file) not in body
    assert "sensitive internal failure" not in body
    assert json.loads(body) == {"error": "SOURCE_UNAVAILABLE"}


def test_unknown_get_route_is_authenticated_404(tmp_path: Path) -> None:
    app, config, password = _application(tmp_path)

    response = app.dispatch(
        "GET",
        "/api/v1/unknown",
        {"Authorization": _auth(config.username, password)},
    )

    assert response.status == 404
