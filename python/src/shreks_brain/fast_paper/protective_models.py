from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from shreks_brain.exits import ExitAssessment, ExitPolicy, ExitState

from .models import (
    FastPaperEventOutcome,
    FastPaperEventResult,
    FastPaperMaterialUpdate,
)
from .position_models import FastPaperPositionActionApproval


FAST_PAPER_PROTECTIVE_EXIT_VERSION = "fl7.6-v1"
FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY = "protective-risk"


class FastPaperProtectiveExitError(ValueError):
    """Raised when FL7.6 protective exit evidence or authority is contradictory."""


FastPaperPositionApprovalEvaluator = Callable[
    [FastPaperMaterialUpdate],
    FastPaperPositionActionApproval,
]


@dataclass(frozen=True, slots=True)
class FastPaperProtectiveExitPolicy:
    version: str
    exit_policy: ExitPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        if not isinstance(self.exit_policy, ExitPolicy):
            raise ValueError("exit_policy must be an ExitPolicy")
        policy = self.exit_policy
        if policy.take_profit_levels:
            raise ValueError("protective exit policy must disable take-profit exits")
        if (
            policy.flow_exit_max_buy_fraction_m5 is not None
            or policy.flow_exit_max_buy_pressure_acceleration is not None
        ):
            raise ValueError("protective exit policy must disable flow exits")
        if (
            policy.momentum_exit_max_return_1m_pct is not None
            or policy.momentum_exit_max_return_5m_pct is not None
        ):
            raise ValueError("protective exit policy must disable momentum exits")
        if policy.wallet_distribution_enabled:
            raise ValueError("protective exit policy must disable wallet-distribution exits")


@dataclass(frozen=True, slots=True)
class FastPaperProtectiveEventResult:
    version: str
    event_result: FastPaperEventResult
    strategy_approval: FastPaperPositionActionApproval | None
    applied_approval: FastPaperPositionActionApproval | None
    protective_assessment: ExitAssessment | None
    next_protective_state: ExitState
    protective_triggered: bool

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_PROTECTIVE_EXIT_VERSION:
            raise ValueError("unsupported Fast PAPER protective-exit result version")
        if not isinstance(self.event_result, FastPaperEventResult):
            raise ValueError("event_result must be a FastPaperEventResult")
        if self.strategy_approval is not None and not isinstance(
            self.strategy_approval,
            FastPaperPositionActionApproval,
        ):
            raise ValueError(
                "strategy_approval must be FastPaperPositionActionApproval or None"
            )
        if self.applied_approval is not None and not isinstance(
            self.applied_approval,
            FastPaperPositionActionApproval,
        ):
            raise ValueError(
                "applied_approval must be FastPaperPositionActionApproval or None"
            )
        if self.protective_assessment is not None and not isinstance(
            self.protective_assessment,
            ExitAssessment,
        ):
            raise ValueError("protective_assessment must be ExitAssessment or None")
        if not isinstance(self.next_protective_state, ExitState):
            raise ValueError("next_protective_state must be an ExitState")
        if not isinstance(self.protective_triggered, bool):
            raise ValueError("protective_triggered must be a bool")

        if self.event_result.outcome is FastPaperEventOutcome.ASSESSED:
            if (
                self.strategy_approval is None
                or self.applied_approval is None
                or self.protective_assessment is None
            ):
                raise ValueError(
                    "ASSESSED protective result requires strategy, applied, and C4 assessments"
                )
            if self.event_result.assessment != self.applied_approval.assessment:
                raise ValueError(
                    "event_result assessment must equal applied protective arbitration authority"
                )
        else:
            if (
                self.strategy_approval is not None
                or self.applied_approval is not None
                or self.protective_assessment is not None
            ):
                raise ValueError(
                    "replay/non-material protective result cannot carry fresh evaluation authority"
                )
            if self.protective_triggered:
                raise ValueError(
                    "replay/non-material protective result cannot report a fresh trigger"
                )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
