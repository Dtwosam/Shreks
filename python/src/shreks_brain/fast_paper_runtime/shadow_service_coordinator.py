from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .shadow_runtime_state import fast_paper_shadow_decision_position
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
    run_fast_paper_shadow_service_cycle,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
    FastPaperShadowServiceExecutionConfig,
    bootstrap_fast_paper_shadow_service_execution,
)
from .shadow_service_execution_cycle import (
    run_fast_paper_shadow_service_execution_cycle,
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowServiceCoordinatorResult:
    decision_bootstrap: FastPaperShadowServiceBootstrap
    execution_bootstrap: FastPaperShadowServiceExecutionBootstrap
    decisions_produced: int
    executions_committed: int

    def __post_init__(self) -> None:
        for name in ("decisions_produced", "executions_committed"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value not in {0, 1}
            ):
                raise ValueError(f"{name} must be 0 or 1")
        if self.decisions_produced and self.executions_committed:
            raise ValueError(
                "coordinator invocation cannot produce and execute a decision together"
            )


def run_fast_paper_shadow_service_coordinated_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    decision_config: FastPaperShadowServiceConfig,
    execution_config: FastPaperShadowServiceExecutionConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
    committed_at_unix_ms: int,
) -> FastPaperShadowServiceCoordinatorResult:
    if type(decision_bootstrap) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if type(decision_config) is not FastPaperShadowServiceConfig:
        raise ValueError(
            "decision_config must be exact FastPaperShadowServiceConfig"
        )
    if type(execution_config) is not FastPaperShadowServiceExecutionConfig:
        raise ValueError(
            "execution_config must be exact FastPaperShadowServiceExecutionConfig"
        )
    if (
        isinstance(committed_at_unix_ms, bool)
        or not isinstance(committed_at_unix_ms, int)
        or committed_at_unix_ms < 0
    ):
        raise ValueError(
            "committed_at_unix_ms must be a non-negative integer"
        )

    manifest = decision_bootstrap.manifest
    execution_bootstrap = bootstrap_fast_paper_shadow_service_execution(
        manifest,
        execution_config,
    )
    decision_sequence = _decision_sequence(decision_bootstrap)
    execution_sequence = _execution_sequence(execution_bootstrap)
    _require_cursor_relationship(
        decision_sequence,
        execution_sequence,
    )

    if decision_sequence == execution_sequence + 1:
        committed = run_fast_paper_shadow_service_execution_cycle(
            manifest,
            execution_bootstrap,
            decision_evidence_directory=decision_config.evidence_directory,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        if type(committed) is not int or committed not in {0, 1}:
            raise ValueError(
                "execution cycle must report zero or one committed execution"
            )
        if committed == 0:
            return FastPaperShadowServiceCoordinatorResult(
                decision_bootstrap=decision_bootstrap,
                execution_bootstrap=execution_bootstrap,
                decisions_produced=0,
                executions_committed=0,
            )

        refreshed = bootstrap_fast_paper_shadow_service_execution(
            manifest,
            execution_config,
        )
        refreshed_sequence = _execution_sequence(refreshed)
        if refreshed_sequence != decision_sequence:
            raise ValueError(
                "durable execution cursor did not catch up to decision cursor"
            )
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=refreshed,
            decisions_produced=0,
            executions_committed=1,
        )

    state = execution_bootstrap.runtime_state
    if state.pending_buy is not None:
        raise ValueError(
            "coordinator cannot produce a new decision while pending BUY exists"
        )
    if state.market_positions:
        raise ValueError(
            "coordinator OPEN learned posture requires sealed reduction quote authority"
        )

    bounded_config = replace(
        decision_config,
        maximum_decisions=1,
    )

    def position_resolver(
        record: FastTrainingFeatureRecord,
    ) -> FastCampaignDecisionPosition:
        market_key = f"{record.venue}:{record.mint}:{record.quote_mint}"
        position = fast_paper_shadow_decision_position(
            state,
            market_key,
        )
        if position.kind != "FLAT":
            raise ValueError(
                "coordinator expected FLAT posture before OPEN authority is enabled"
            )
        return position

    updated, produced = run_fast_paper_shadow_service_cycle(
        decision_bootstrap,
        bounded_config,
        clock_unix_ms=clock_unix_ms,
        position_resolver=position_resolver,
    )
    if type(produced) is not int or produced not in {0, 1}:
        raise ValueError(
            "bounded decision cycle must report zero or one produced decision"
        )

    updated_sequence = _decision_sequence(updated)
    if produced == 0:
        if updated_sequence != decision_sequence:
            raise ValueError(
                "decision cursor advanced without a produced decision"
            )
    elif updated_sequence != decision_sequence + 1:
        raise ValueError(
            "decision cursor did not advance exactly once"
        )

    return FastPaperShadowServiceCoordinatorResult(
        decision_bootstrap=updated,
        execution_bootstrap=execution_bootstrap,
        decisions_produced=produced,
        executions_committed=0,
    )


def _decision_sequence(
    bootstrap: FastPaperShadowServiceBootstrap,
) -> int:
    cursor = bootstrap.state.cursor
    if cursor is None:
        return 0
    value = cursor.decision_sequence
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("decision cursor sequence must be positive")
    return value


def _execution_sequence(
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
) -> int:
    value = bootstrap.runtime_state.last_processed_source_sequence
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("execution cursor sequence must be positive")
    return value


def _require_cursor_relationship(
    decision_sequence: int,
    execution_sequence: int,
) -> None:
    if execution_sequence > decision_sequence:
        raise ValueError(
            "execution cursor cannot be ahead of decision cursor"
        )
    if decision_sequence - execution_sequence > 1:
        raise ValueError(
            "decision/execution cursor gap exceeds one"
        )
