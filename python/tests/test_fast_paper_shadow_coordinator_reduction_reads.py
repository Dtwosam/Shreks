from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_coordinator as coordinator
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime.persisted_quotes import (
    FastPaperShadowReductionRead,
)

from test_fast_paper_shadow_service_coordinator import (
    _decision_bootstrap,
    _decision_config,
    _execution_bootstrap,
    _execution_config,
)


def test_coordinator_allows_open_posture_with_explicit_reduction_read_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    decision_config = _decision_config(tmp_path)
    execution_config = _execution_config(tmp_path)
    execution_bootstrap = _execution_bootstrap(
        None,
        market_positions=(
            SimpleNamespace(
                market_key="pump_fun_bonding_curve:Mint111:Quote111",
            ),
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )

    record = SimpleNamespace(
        venue="pump_fun_bonding_curve",
        mint="Mint111",
        quote_mint="Quote111",
    )
    open_position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )
    monkeypatch.setattr(
        coordinator,
        "fast_paper_shadow_decision_position",
        lambda state, market_key: open_position,
    )

    reads = (
        FastPaperShadowReductionRead(
            target_exposure_fraction=0.25,
            input_amount_raw=10_000_000,
        ),
    )

    def reduction_resolver(supplied_record, supplied_position):
        assert supplied_record is record
        assert supplied_position == open_position
        return reads

    captured: dict[str, object] = {}
    updated = SimpleNamespace(
        manifest=decision_bootstrap.manifest,
        policy=decision_bootstrap.policy,
        state=SimpleNamespace(
            cursor=SimpleNamespace(decision_sequence=1),
        ),
    )

    def run_decision(
        supplied_bootstrap,
        supplied_config,
        *,
        clock_unix_ms,
        position_resolver,
        reduction_read_resolver,
    ):
        captured["position"] = position_resolver(record)
        captured["reduction_resolver"] = reduction_read_resolver
        return updated, 1

    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        run_decision,
    )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        decision_config,
        execution_config,
        reduction_read_resolver=reduction_resolver,
        committed_at_unix_ms=20_000,
    )

    assert result.decision_bootstrap is updated
    assert result.decisions_produced == 1
    assert result.executions_committed == 0
    assert captured["position"] == open_position
    assert captured["reduction_resolver"] is reduction_resolver


def test_coordinator_open_posture_requires_explicit_reduction_read_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap()
    execution_bootstrap = _execution_bootstrap(
        None,
        market_positions=(
            SimpleNamespace(market_key="market-open"),
        ),
    )
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: execution_bootstrap,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "OPEN without reduction authority must fail before decision production"
        ),
    )

    with pytest.raises(ValueError, match="OPEN|reduction|authority"):
        coordinator.run_fast_paper_shadow_service_coordinated_cycle(
            decision_bootstrap,
            _decision_config(tmp_path),
            _execution_config(tmp_path),
            committed_at_unix_ms=20_000,
        )


def test_coordinator_execution_catchup_does_not_use_reduction_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision_bootstrap = _decision_bootstrap(1)
    before = _execution_bootstrap(None)
    after = _execution_bootstrap(1)
    bootstraps = iter((before, after))
    monkeypatch.setattr(
        coordinator,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda *_args: next(bootstraps),
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_execution_cycle",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        coordinator,
        "run_fast_paper_shadow_service_cycle",
        lambda *_args, **_kwargs: pytest.fail(
            "execution catch-up must not produce a decision"
        ),
    )

    def forbidden_resolver(*_args):
        pytest.fail(
            "execution catch-up must not request reduction-read authority"
        )

    result = coordinator.run_fast_paper_shadow_service_coordinated_cycle(
        decision_bootstrap,
        _decision_config(tmp_path),
        _execution_config(tmp_path),
        reduction_read_resolver=forbidden_resolver,
        committed_at_unix_ms=20_000,
    )

    assert result.decisions_produced == 0
    assert result.executions_committed == 1


def test_coordinator_reduction_authority_is_forwarded_not_derived() -> None:
    source = Path(coordinator.__file__).read_text(encoding="utf-8")
    forbidden = (
        "FastPaperShadowReductionRead(",
        "decimal_quantity_to_raw",
        "input_amount_raw=",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
