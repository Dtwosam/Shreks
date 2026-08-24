from dataclasses import replace

import pytest

from shreks_brain.decision import DecisionAction
from shreks_brain.exits import (
    ExitAssessment,
    ExitFinding,
    ExitPolicy,
    ExitReasonCode,
    ExitState,
    TakeProfitLevel,
)
from shreks_brain.paper_loop.models import ManagedPaperPosition


def _policy(version: str = "exit-v1-test") -> ExitPolicy:
    return ExitPolicy(
        version=version,
        required_feature_schema_version="b2-v1",
        max_market_data_age_ms=5_000,
        max_execution_evidence_age_ms=5_000,
        hard_stop_loss_pct=10.0,
        take_profit_levels=(TakeProfitLevel("tp1", 20.0, 0.5),),
        trailing_activation_return_pct=15.0,
        trailing_stop_drawdown_pct=8.0,
        max_hold_seconds=1_800,
        flow_exit_max_buy_fraction_m5=0.40,
        flow_exit_max_buy_pressure_acceleration=-0.10,
        momentum_exit_max_return_1m_pct=-5.0,
        momentum_exit_max_return_5m_pct=-8.0,
        min_liquidity_usd=10_000.0,
        max_exit_price_impact_pct=8.0,
        min_exit_capacity_fraction=0.50,
        wallet_distribution_enabled=False,
    )


def _state(
    *,
    policy_version: str = "exit-v1-test",
    position_id: str = "position-1",
    mint: str = "Mint111",
    last_evaluated_at_unix_ms: int = 1_000_000,
) -> ExitState:
    return ExitState(
        policy_version=policy_version,
        position_id=position_id,
        mint=mint,
        initialized_at_unix_ms=900_000,
        last_evaluated_at_unix_ms=last_evaluated_at_unix_ms,
        high_water_price_usd=1.25,
        high_water_at_unix_ms=950_000,
        completed_take_profit_levels=frozenset(),
    )


def _assessment(
    *,
    action: DecisionAction = DecisionAction.REDUCE,
    reason: ExitReasonCode = ExitReasonCode.TAKE_PROFIT_TRIGGERED,
    policy_version: str = "exit-v1-test",
    position_id: str = "position-1",
    mint: str = "Mint111",
    as_of_unix_ms: int = 1_000_000,
    target_fraction: float = 0.5,
    target_quantity: float = 5.0,
    next_state: ExitState | None = None,
) -> ExitAssessment:
    state = next_state or _state(
        policy_version=policy_version,
        position_id=position_id,
        mint=mint,
        last_evaluated_at_unix_ms=as_of_unix_ms,
    )
    return ExitAssessment(
        policy_version=policy_version,
        feature_schema_version="b2-v1",
        position_id=position_id,
        mint=mint,
        as_of_unix_ms=as_of_unix_ms,
        action=action,
        primary_reason=reason,
        target_reduction_fraction=target_fraction,
        target_quantity=target_quantity,
        position_age_seconds=100.0,
        current_price_usd=1.20,
        current_market_value_usd=12.0,
        price_return_pct=20.0,
        drawdown_from_high_water_pct=4.0,
        exit_capacity_fraction=1.0,
        triggered_take_profit_level=(
            "tp1" if reason is ExitReasonCode.TAKE_PROFIT_TRIGGERED else None
        ),
        next_state=state,
        findings=(ExitFinding(reason, "test exit", True),),
    )


def test_managed_position_accepts_matching_pending_reduce() -> None:
    pending = _assessment()
    managed = ManagedPaperPosition(
        position_id="position-1",
        exit_policy=_policy(),
        exit_state=_state(),
        pending_exit=pending,
    )
    assert managed.pending_exit is pending


def test_managed_position_accepts_matching_pending_full_exit() -> None:
    pending = _assessment(
        action=DecisionAction.EXIT,
        reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        target_fraction=1.0,
        target_quantity=10.0,
    )
    managed = ManagedPaperPosition(
        position_id="position-1",
        exit_policy=_policy(),
        exit_state=_state(),
        pending_exit=pending,
    )
    assert managed.pending_exit.action is DecisionAction.EXIT


def test_pending_hold_is_rejected() -> None:
    pending = _assessment(
        action=DecisionAction.HOLD,
        reason=ExitReasonCode.NO_EXIT_TRIGGERED,
        target_fraction=0.0,
        target_quantity=0.0,
    )
    with pytest.raises(ValueError, match="REDUCE or EXIT"):
        ManagedPaperPosition("position-1", _policy(), _state(), pending)


@pytest.mark.parametrize(
    "pending",
    (
        _assessment(position_id="other-position"),
        _assessment(mint="OtherMint"),
        _assessment(policy_version="other-policy"),
    ),
)
def test_pending_exit_identity_and_policy_must_match_managed_state(
    pending: ExitAssessment,
) -> None:
    with pytest.raises(ValueError):
        ManagedPaperPosition("position-1", _policy(), _state(), pending)


def test_pending_exit_cannot_be_later_than_current_managed_exit_state() -> None:
    pending = _assessment(as_of_unix_ms=1_000_001)
    with pytest.raises(ValueError, match="later"):
        ManagedPaperPosition("position-1", _policy(), _state(), pending)


def test_pending_exit_can_be_older_than_latest_evolving_exit_state() -> None:
    pending = _assessment(as_of_unix_ms=1_000_000)
    newer_state = replace(
        _state(),
        last_evaluated_at_unix_ms=1_010_000,
        high_water_at_unix_ms=1_010_000,
    )
    managed = ManagedPaperPosition("position-1", _policy(), newer_state, pending)
    assert managed.pending_exit.as_of_unix_ms == 1_000_000
    assert managed.exit_state.last_evaluated_at_unix_ms == 1_010_000
