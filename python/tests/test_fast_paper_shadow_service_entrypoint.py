from __future__ import annotations

import importlib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIT = _REPO_ROOT / "deploy" / "systemd" / "shreks-fast-paper-shadow.service"
_TARGET = _REPO_ROOT / "deploy" / "systemd" / "shreks.target"
_MODULE = (
    _REPO_ROOT
    / "python"
    / "src"
    / "shreks_brain"
    / "fast_paper_runtime"
    / "shadow_service.py"
)


def test_shadow_service_module_exposes_bounded_entrypoint_api() -> None:
    service = importlib.import_module(
        "shreks_brain.fast_paper_runtime.shadow_service"
    )

    for name in (
        "FastPaperShadowServiceConfig",
        "FastPaperShadowServicePolicy",
        "load_fast_paper_shadow_service_config",
        "read_fast_paper_shadow_service_policy",
        "bootstrap_fast_paper_shadow_service",
        "run_fast_paper_shadow_service_cycle",
        "run_fast_paper_shadow_service",
        "main",
    ):
        assert hasattr(service, name)


def test_shadow_service_composes_only_accepted_runtime_boundaries() -> None:
    source = _MODULE.read_text(encoding="utf-8")

    for required in (
        "fetch_fast_paper_runtime_feature_batch",
        "FastPaperShadowQuoteReadPolicy",
        "resolve_fast_paper_shadow_cycle_input",
        "run_fast_paper_shadow_batch",
        'FastCampaignDecisionPosition(kind="FLAT")',
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "PaperLedger",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
        "FastCampaignActionConstraints(",
    ):
        assert forbidden not in source


def test_shadow_service_policy_cannot_supply_prices_constraints_or_positions() -> None:
    source = _MODULE.read_text(encoding="utf-8")

    for forbidden in (
        "execution_price_quote",
        "reference_price_quote",
        "expected_future_exit_cost_bps",
        "sell_now_cost_bps",
        "buy_economically_allowed",
        "current_exposure_fraction",
        "position_kind",
        "score_threshold",
        "required_score_threshold",
    ):
        assert forbidden not in source


def test_shadow_service_systemd_is_detached_from_authoritative_campaign() -> None:
    payload = _UNIT.read_text(encoding="utf-8")

    assert "User=shreks" in payload
    assert "Group=shreks" in payload
    assert "EnvironmentFile=/etc/shreks/fast-paper-shadow.env" in payload
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in payload
    assert (
        "ExecStartPre=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_service --preflight"
    ) in payload
    assert (
        "ExecStart=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.fast_paper_runtime.shadow_service"
    ) in payload
    assert "ReadWritePaths=/var/lib/shreks/fast-paper-shadow" in payload
    assert "NoNewPrivileges=true" in payload
    assert "ProtectSystem=strict" in payload
    assert "ProtectHome=true" in payload

    assert "PartOf=shreks.target" not in payload
    assert "WantedBy=shreks.target" not in payload
    assert "shreks-paper-campaign.service" not in payload
    assert "wallet" not in payload.lower()
    assert "sign" not in payload.lower()
    assert "submit" not in payload.lower()
    assert "live" not in payload.lower()


def test_shadow_service_is_not_a_shreks_target_member() -> None:
    payload = _TARGET.read_text(encoding="utf-8")
    assert "shreks-fast-paper-shadow.service" not in payload
