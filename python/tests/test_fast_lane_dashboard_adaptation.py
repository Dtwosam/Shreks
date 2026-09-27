from __future__ import annotations

import base64
from pathlib import Path

import pytest

import shreks_brain.dashboard.http as http_module
import shreks_brain.dashboard.source as source_module
from shreks_brain.dashboard.config import (
    DashboardFastLaneConfig,
    DashboardRuntimeConfigError,
    load_dashboard_runtime_config,
)
from shreks_brain.dashboard.http import DashboardApplication
from shreks_brain.dashboard.page import render_dashboard_page
from shreks_brain.dashboard.source import (
    DashboardSourceError,
    load_dashboard_fast_lane_snapshot,
)

from test_g5_dashboard_config import _env


_SHA = "a" * 40
_MANIFEST = "b" * 64
_CHAMPION = "c" * 64
_BINDING = "d" * 64
_EXECUTION_POLICY = "e" * 64


def _fast_lane_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    env, password = _env(tmp_path)
    root = tmp_path / "fast-lane"
    env.update(
        {
            "SHREKS_DASHBOARD_FAST_LANE_MANIFEST_PATH": str(
                root / "manifest.json"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_EXECUTION_POLICY_PATH": str(
                root / "execution-policy.json"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_LEDGER_DATABASE_PATH": str(
                root / "ledger.sqlite3"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_RUN_ID": "shadow-run-1",
            "SHREKS_DASHBOARD_FAST_LANE_DECISION_EVIDENCE_DIRECTORY": str(
                root / "decision"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_EXECUTION_SOURCE_DIRECTORY": str(
                root / "execution-sources"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_PENDING_BUY_RETRY_SOURCE_DIRECTORY": str(
                root / "pending-buy-retry-sources"
            ),
            "SHREKS_DASHBOARD_FAST_LANE_EXPECTED_RELEASE_SHA": _SHA,
            "SHREKS_DASHBOARD_FAST_LANE_WINDOW_SECONDS": "900",
        }
    )
    return env, password


def _auth(username: str, password: bytes) -> str:
    payload = username.encode("ascii") + b":" + password
    return "Basic " + base64.b64encode(payload).decode("ascii")


def _decision(since: int, until: int) -> dict[str, object]:
    return {
        "release_source_sha": _SHA,
        "manifest_fingerprint_sha256": _MANIFEST,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": _CHAMPION,
        "action_policy_version": 4,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "decision_evidence_count": 5,
        "decision_evidence_rate_per_second": 0.1,
        "action_counts": {
            "BUY": 1,
            "SKIP": 1,
            "HOLD": 1,
            "REDUCE": 1,
            "SELL": 1,
        },
        "selected_value_bps": {
            "mean": 12.0,
            "p50": 10.0,
            "p95": 20.0,
        },
        "event_to_evaluation_lag_ms": {
            "p50": 20.0,
            "p95": 30.0,
            "p99": 35.0,
            "max": 40.0,
        },
        "decision_latency_ms": {
            "p50": 2.0,
            "p95": 3.0,
            "p99": 4.0,
            "max": 5.0,
        },
    }


def _execution(since: int, until: int) -> dict[str, object]:
    return {
        "release_source_sha": _SHA,
        "manifest_fingerprint_sha256": _MANIFEST,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": _CHAMPION,
        "action_policy_version": 4,
        "execution_policy_fingerprint_sha256": _EXECUTION_POLICY,
        "run_id": "shadow-run-1",
        "binding_fingerprint_sha256": _BINDING,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "decision_to_commit_latency_ms": {
            "mean": 8.0,
            "p50": 7.0,
            "p95": 12.0,
        },
        "decision_to_booked_entry_latency_ms": {
            "mean": 5.0,
            "p50": 4.0,
            "p95": 9.0,
        },
        "max_entry_price_abort_count": 2,
        "pending_buy_retry_outcome_counts": {"FILLED": 1},
        "pending_buy_retry_max_entry_price_abort_count": 1,
        "expected_selected_price_cost_bps": {
            "mean": 25.0,
            "p50": 20.0,
            "p95": 35.0,
        },
        "realized_price_cost_bps": {
            "mean": 30.0,
            "p50": 25.0,
            "p95": 40.0,
        },
        "realized_explicit_cost_bps": {
            "mean": 8.0,
            "p50": 8.0,
            "p95": 8.0,
        },
    }


def _outcome(since: int, until: int) -> dict[str, object]:
    return {
        "release_source_sha": _SHA,
        "manifest_fingerprint_sha256": _MANIFEST,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": _CHAMPION,
        "action_policy_version": 4,
        "run_id": "shadow-run-1",
        "binding_fingerprint_sha256": _BINDING,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "realized_pnl_delta_usd": 15.0,
        "cash_balance_usd": 20_015.0,
        "rolling_drawdown_pct": 1.5,
        "aggregate_open_risk_usd": 250.0,
    }


def test_fast_lane_dashboard_config_is_optional_all_or_nothing(
    tmp_path: Path,
) -> None:
    base, _password = _env(tmp_path / "base")
    assert load_dashboard_runtime_config(base).fast_lane is None

    complete, _password = _fast_lane_env(tmp_path / "complete")
    config = load_dashboard_runtime_config(complete)
    assert type(config.fast_lane) is DashboardFastLaneConfig
    assert config.fast_lane.run_id == "shadow-run-1"
    assert config.fast_lane.expected_release_sha == _SHA
    assert config.fast_lane.window_seconds == 900
    assert config.fast_lane.manifest_path.is_absolute()
    assert config.fast_lane.pending_buy_retry_source_directory.is_absolute()

    partial, _password = _env(tmp_path / "partial")
    partial[
        "SHREKS_DASHBOARD_FAST_LANE_MANIFEST_PATH"
    ] = "/tmp/manifest.json"
    with pytest.raises(
        DashboardRuntimeConfigError,
        match="Fast Lane|fast lane|FAST_LANE|missing",
    ):
        load_dashboard_runtime_config(partial)

    complete["SHREKS_DASHBOARD_FAST_LANE_EXPECTED_RELEASE_SHA"] = "A" * 40
    with pytest.raises(DashboardRuntimeConfigError, match="release|SHA|sha"):
        load_dashboard_runtime_config(complete)


def test_fast_lane_source_composes_sealed_collectors_and_cross_checks_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, _password = _fast_lane_env(tmp_path)
    fast = load_dashboard_runtime_config(env).fast_lane
    assert fast is not None
    calls: list[tuple[str, dict[str, object]]] = []

    def decision(**kwargs):
        calls.append(("decision", kwargs))
        return _decision(100_000, 1_000_000)

    def execution(**kwargs):
        calls.append(("execution", kwargs))
        return _execution(100_000, 1_000_000)

    def outcome(**kwargs):
        calls.append(("outcome", kwargs))
        return _outcome(100_000, 1_000_000)

    monkeypatch.setattr(
        source_module,
        "collect_fast_paper_shadow_decision_telemetry",
        decision,
        raising=False,
    )
    monkeypatch.setattr(
        source_module,
        "collect_fast_paper_shadow_execution_telemetry",
        execution,
        raising=False,
    )
    monkeypatch.setattr(
        source_module,
        "collect_fast_paper_shadow_outcome_telemetry",
        outcome,
        raising=False,
    )

    result = load_dashboard_fast_lane_snapshot(
        fast,
        until_unix_ms=1_000_000,
    )

    assert result["window_since_unix_ms"] == 100_000
    assert result["window_until_unix_ms"] == 1_000_000
    assert result["expected_release_sha"] == _SHA
    assert result["decision"]["decision_evidence_count"] == 5
    assert result["execution"]["max_entry_price_abort_count"] == 2
    assert result["outcome"]["realized_pnl_delta_usd"] == 15.0
    assert [name for name, _kwargs in calls] == [
        "decision",
        "execution",
        "outcome",
    ]
    for _name, kwargs in calls:
        assert kwargs["expected_release_sha"] == _SHA
        assert kwargs["since_unix_ms"] == 100_000
        assert kwargs["until_unix_ms"] == 1_000_000

    monkeypatch.setattr(
        source_module,
        "collect_fast_paper_shadow_execution_telemetry",
        lambda **_kwargs: {
            **_execution(100_000, 1_000_000),
            "champion_fingerprint_sha256": "f" * 64,
        },
        raising=False,
    )
    with pytest.raises(DashboardSourceError, match="identity|Fast Lane|fast lane"):
        load_dashboard_fast_lane_snapshot(
            fast,
            until_unix_ms=1_000_000,
        )


def test_authenticated_fast_lane_route_is_read_only_and_generic_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, password_file = _fast_lane_env(tmp_path)
    config = load_dashboard_runtime_config(env)
    password = password_file.read_bytes().rstrip(b"\r\n")
    app = DashboardApplication(
        config,
        password,
        clock_unix_ms=lambda: 1_000_000,
    )
    auth = {"Authorization": _auth(config.username, password)}
    expected = {
        "window_since_unix_ms": 100_000,
        "window_until_unix_ms": 1_000_000,
        "expected_release_sha": _SHA,
        "decision": _decision(100_000, 1_000_000),
        "execution": _execution(100_000, 1_000_000),
        "outcome": _outcome(100_000, 1_000_000),
    }
    observed: list[tuple[object, int]] = []
    monkeypatch.setattr(
        http_module,
        "load_dashboard_fast_lane_snapshot",
        lambda fast, *, until_unix_ms: (
            observed.append((fast, until_unix_ms)) or expected
        ),
        raising=False,
    )

    unauthorized = app.dispatch("GET", "/api/v1/fast-lane", {})
    response = app.dispatch("GET", "/api/v1/fast-lane", auth)
    mutation = app.dispatch("POST", "/api/v1/fast-lane", auth)

    assert unauthorized.status == 401
    assert response.status == 200
    assert mutation.status == 405
    assert observed == [(config.fast_lane, 1_000_000)]

    def fail(*_args, **_kwargs):
        raise RuntimeError(
            f"sensitive {config.fast_lane.manifest_path}"
        )

    monkeypatch.setattr(
        http_module,
        "load_dashboard_fast_lane_snapshot",
        fail,
        raising=False,
    )
    failed = app.dispatch("GET", "/api/v1/fast-lane", auth)
    assert failed.status == 503
    body = failed.body.decode("utf-8")
    assert "sensitive" not in body
    assert str(config.fast_lane.manifest_path) not in body
    assert '"SOURCE_UNAVAILABLE"' in body

    base_env, base_password_file = _env(tmp_path / "legacy")
    legacy = load_dashboard_runtime_config(base_env)
    legacy_password = base_password_file.read_bytes().rstrip(b"\r\n")
    legacy_app = DashboardApplication(legacy, legacy_password)
    unavailable = legacy_app.dispatch(
        "GET",
        "/api/v1/fast-lane",
        {
            "Authorization": _auth(
                legacy.username,
                legacy_password,
            )
        },
    )
    assert unavailable.status == 503
    assert b"FAST_LANE_UNAVAILABLE" in unavailable.body


def test_page_surfaces_fast_lane_action_ev_latency_and_cost_evidence() -> None:
    source = render_dashboard_page().decode("utf-8")

    assert 'id="fast-lane-layer"' in source
    assert "Fast Lane PAPER shadow" in source
    assert 'fetch("/api/v1/fast-lane", {credentials: "same-origin"})' in source

    for field in (
        "decision_evidence_count",
        "decision_evidence_rate_per_second",
        "action_counts",
        "selected_value_bps",
        "event_to_evaluation_lag_ms",
        "decision_latency_ms",
        "decision_to_commit_latency_ms",
        "decision_to_booked_entry_latency_ms",
        "max_entry_price_abort_count",
        "pending_buy_retry_outcome_counts",
        "pending_buy_retry_max_entry_price_abort_count",
        "expected_selected_price_cost_bps",
        "realized_price_cost_bps",
        "realized_explicit_cost_bps",
        "realized_pnl_delta_usd",
        "cash_balance_usd",
        "rolling_drawdown_pct",
        "aggregate_open_risk_usd",
    ):
        assert field in source

    for forbidden in (
        "calculateFastLane",
        "calculateExpectancy",
        "calculateProfitFactor",
        "calculateDrawdown",
        "selectAction",
        "/api/v1/fast-lane/buy",
        "/api/v1/fast-lane/sell",
        "/api/v1/fast-lane/live-enable",
    ):
        assert forbidden not in source


def test_dashboard_fast_lane_source_has_no_new_trading_or_live_authority() -> None:
    source = Path(source_module.__file__).read_text(encoding="utf-8")
    for required in (
        "collect_fast_paper_shadow_decision_telemetry",
        "collect_fast_paper_shadow_execution_telemetry",
        "collect_fast_paper_shadow_outcome_telemetry",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "execute_fast_paper_shadow_decision",
        "retry_fast_paper_shadow_pending_buy",
        "commit_fast_paper_shadow_transition_atomically",
        "save_fast_paper",
        "write_fast_paper_shadow",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
