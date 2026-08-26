from __future__ import annotations

import base64
from pathlib import Path

import shreks_brain.dashboard.http as http_module
from shreks_brain.dashboard.config import load_dashboard_runtime_config
from shreks_brain.dashboard.http import DashboardApplication
from shreks_brain.dashboard.page import render_dashboard_page

from test_g5_dashboard_config import _env


def _authorization(username: str, password: bytes) -> str:
    payload = username.encode("ascii") + b":" + password
    return "Basic " + base64.b64encode(payload).decode("ascii")


def _page_source() -> str:
    payload = render_dashboard_page()
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


def test_page_is_dependency_free_mobile_operator_dashboard() -> None:
    source = _page_source()
    lowered = source.lower()

    assert "Shreks Operator Dashboard" in source
    assert "LIVE TRADING: DISABLED" in source
    assert '<meta name="viewport"' in source
    assert 'id="system-layer"' in source
    assert 'id="trading-layer"' in source
    assert 'id="money-layer"' in source
    assert 'id="proof-risk-layer"' in source
    assert 'id="recent-trades"' in source
    assert 'id="trade-detail"' in source
    assert "System" in source
    assert "Trading" in source
    assert "Money" in source
    assert "Proof / Risk" in source
    assert "Recent trades" in source

    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "cdn" not in lowered
    assert "analytics" not in lowered
    assert "<link" not in lowered
    assert "<img" not in lowered
    assert "src=\"" not in lowered


def test_page_uses_same_origin_fetches_and_safe_dom_writes() -> None:
    source = _page_source()

    assert 'fetch("/api/v1/snapshot", {credentials: "same-origin"})' in source
    assert 'fetch("/api/v1/trades", {credentials: "same-origin"})' in source
    assert 'fetch(`/api/v1/trades/${encodeURIComponent(positionId)}`, {credentials: "same-origin"})' in source
    assert ".textContent" in source
    assert "innerHTML" not in source
    for forbidden_method in ("PUT", "PATCH", "DELETE"):
        assert f'method: "{forbidden_method}"' not in source
    for forbidden_endpoint in (
        "/api/v1/operator-controls/reset-kill-switch",
        "/api/v1/operator-controls/clear-entry-halt",
        "/api/v1/operator-controls/resume",
        "/api/v1/operator-controls/live-enable",
        "/api/v1/buy",
        "/api/v1/sell",
    ):
        assert forbidden_endpoint not in source


def test_page_displays_authoritative_server_metrics_without_profitability_formulas() -> None:
    source = _page_source()

    for authoritative_field in (
        "net_pnl_usd",
        "unrealized_pnl_usd",
        "net_expectancy_pct",
        "profit_factor",
        "maximum_drawdown_pct",
        "total_cost_usd",
        "cost_burden_pct",
        "proof_trade_count",
        "proof_distinct_mint_count",
        "proof_decision",
        "promotion_decision",
        "global_risk_halt",
        "accounting_integrity",
    ):
        assert authoritative_field in source

    assert "calculateExpectancy" not in source
    assert "calculateProfitFactor" not in source
    assert "calculateDrawdown" not in source
    assert "calculateCosts" not in source
    assert "calculateProof" not in source


def test_page_has_explicit_unavailable_and_source_error_rendering() -> None:
    source = _page_source()

    assert "UNAVAILABLE" in source
    assert "SOURCE_UNAVAILABLE" in source
    assert "NOT_PERSISTED" in source


def test_authenticated_root_serves_static_html_without_source_interpolation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env, password_file = _env(tmp_path)
    config = load_dashboard_runtime_config(env)
    password = password_file.read_bytes().rstrip(b"\r\n")
    app = DashboardApplication(config, password)

    def forbidden_source_call(*_args, **_kwargs):
        raise AssertionError("root page must not load or interpolate authoritative source data")

    monkeypatch.setattr(http_module, "load_dashboard_snapshot", forbidden_source_call)
    monkeypatch.setattr(http_module, "load_dashboard_trade", forbidden_source_call)

    response = app.dispatch(
        "GET",
        "/",
        {"Authorization": _authorization(config.username, password)},
    )

    assert response.status == 200
    headers = {name.lower(): value for name, value in response.headers}
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert response.body == render_dashboard_page()
    assert b"LIVE TRADING: DISABLED" in response.body
