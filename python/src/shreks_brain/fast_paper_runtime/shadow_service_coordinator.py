from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .persisted_quotes import FastPaperShadowReductionRead
from .shadow_executor import FastPaperShadowPendingBuyRetryInput
from .shadow_pending_buy_retry_source import (
    _record_filename as _pending_buy_retry_source_record_filename,
    read_fast_paper_shadow_pending_buy_retry_source_record,
)
from .shadow_reduction_source import (
    read_fast_paper_shadow_reduction_source_record,
)
from .shadow_runtime_state import fast_paper_shadow_decision_position
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
    run_fast_paper_shadow_service_cycle,
)
from .shadow_service_execution import (
    run_fast_paper_shadow_service_pending_buy_retry,
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
    reduction_read_resolver: (
        Callable[
            [FastTrainingFeatureRecord, FastCampaignDecisionPosition],
            tuple[FastPaperShadowReductionRead, ...],
        ]
        | None
    ) = None,
    reduction_source_directory: Path | None = None,
    pending_buy_retry_resolver: (
        Callable[
            [FastPaperShadowServiceExecutionBootstrap],
            FastPaperShadowPendingBuyRetryInput | None,
        ]
        | None
    ) = None,
    pending_buy_retry_source_directory: Path | None = None,
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
    if (
        reduction_read_resolver is not None
        and reduction_source_directory is not None
    ):
        raise ValueError(
            "coordinator accepts either reduction_read_resolver or reduction_source_directory, not both"
        )
    if (
        pending_buy_retry_resolver is not None
        and pending_buy_retry_source_directory is not None
    ):
        raise ValueError(
            "coordinator accepts either pending_buy_retry_resolver or pending_buy_retry_source_directory, not both"
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
        retry = None
        if pending_buy_retry_resolver is not None:
            retry = pending_buy_retry_resolver(execution_bootstrap)
        elif pending_buy_retry_source_directory is not None:
            source_directory = pending_buy_retry_source_directory
            if not isinstance(source_directory, Path):
                raise ValueError(
                    "pending_buy_retry_source_directory must be Path"
                )
            if source_directory.is_symlink() or not source_directory.is_dir():
                raise ValueError(
                    "pending BUY retry source directory must be an existing regular non-symlink directory"
                )
            source_directory = source_directory.resolve(strict=True)
            source_path = source_directory / (
                _pending_buy_retry_source_record_filename(
                    state.state_fingerprint_sha256,
                    state.pending_buy.source_event_id,
                )
            )
            if source_path.is_symlink():
                raise ValueError(
                    "pending BUY retry source record path must not be a symlink"
                )
            if not source_path.exists():
                return FastPaperShadowServiceCoordinatorResult(
                    decision_bootstrap=decision_bootstrap,
                    execution_bootstrap=execution_bootstrap,
                    decisions_produced=0,
                    executions_committed=0,
                )
            if not source_path.is_file():
                raise ValueError(
                    "pending BUY retry source record path must identify a regular file"
                )
            record = read_fast_paper_shadow_pending_buy_retry_source_record(
                manifest,
                execution_bootstrap.binding,
                execution_bootstrap.execution_policy,
                execution_bootstrap.checkpoint,
                state,
                source_directory,
            )
            retry = record.retry_input
        else:
            raise ValueError(
                "coordinator pending BUY requires explicit retry authority"
            )

        if retry is None:
            return FastPaperShadowServiceCoordinatorResult(
                decision_bootstrap=decision_bootstrap,
                execution_bootstrap=execution_bootstrap,
                decisions_produced=0,
                executions_committed=0,
            )

        previous_checkpoint_sequence = execution_bootstrap.checkpoint.sequence
        run_fast_paper_shadow_service_pending_buy_retry(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.execution_policy,
            retry,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        refreshed = bootstrap_fast_paper_shadow_service_execution(
            manifest,
            execution_config,
        )
        if (
            refreshed.checkpoint.sequence
            != previous_checkpoint_sequence + 1
        ):
            raise ValueError(
                "pending BUY retry checkpoint did not advance exactly once"
            )
        refreshed_sequence = _execution_sequence(refreshed)
        if refreshed_sequence != execution_sequence:
            raise ValueError(
                "pending BUY retry changed learned execution cursor"
            )
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=refreshed,
            decisions_produced=0,
            executions_committed=1,
        )

    resolved_reduction_source_directory = None
    if reduction_source_directory is not None:
        if not isinstance(reduction_source_directory, Path):
            raise ValueError(
                "reduction_source_directory must be Path"
            )
        if (
            reduction_source_directory.is_symlink()
            or not reduction_source_directory.is_dir()
        ):
            raise ValueError(
                "reduction source directory must be an existing regular non-symlink directory"
            )
        resolved_reduction_source_directory = (
            reduction_source_directory.resolve(strict=True)
        )
    if (
        state.market_positions
        and reduction_read_resolver is None
        and resolved_reduction_source_directory is None
    ):
        raise ValueError(
            "coordinator OPEN learned posture requires explicit reduction quote authority"
        )

    bounded_config = replace(
        decision_config,
        maximum_decisions=1,
    )

    def position_resolver(
        record: FastTrainingFeatureRecord,
    ) -> FastCampaignDecisionPosition:
        market_key = f"{record.venue}:{record.mint}:{record.quote_mint}"
        return fast_paper_shadow_decision_position(
            state,
            market_key,
        )

    def source_reduction_read_resolver(
        record: FastTrainingFeatureRecord,
        position: FastCampaignDecisionPosition,
    ) -> tuple[FastPaperShadowReductionRead, ...]:
        market_key = f"{record.venue}:{record.mint}:{record.quote_mint}"
        expected_position = fast_paper_shadow_decision_position(
            state,
            market_key,
        )
        if position != expected_position:
            raise ValueError(
                "coordinator reduction source posture does not match durable execution state"
            )
        if position.kind == "FLAT":
            return ()
        if resolved_reduction_source_directory is None:
            raise ValueError(
                "coordinator OPEN posture is missing reduction source authority"
            )
        source_record = read_fast_paper_shadow_reduction_source_record(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.checkpoint,
            state,
            market_key,
            resolved_reduction_source_directory,
        )
        return source_record.reduction_reads

    cycle_kwargs = {
        "clock_unix_ms": clock_unix_ms,
        "position_resolver": position_resolver,
    }
    if reduction_read_resolver is not None:
        cycle_kwargs["reduction_read_resolver"] = reduction_read_resolver
    elif resolved_reduction_source_directory is not None:
        cycle_kwargs["reduction_read_resolver"] = source_reduction_read_resolver
    updated, produced = run_fast_paper_shadow_service_cycle(
        decision_bootstrap,
        bounded_config,
        **cycle_kwargs,
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
