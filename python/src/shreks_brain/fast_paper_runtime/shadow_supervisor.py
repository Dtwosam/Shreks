from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event
import time
from types import FrameType
from typing import Callable

from .shadow_buy_authority_writer import (
    run_fast_paper_shadow_buy_authority_writer_cycle,
)
from .shadow_buy_source_publisher import (
    run_fast_paper_shadow_buy_source_publisher_cycle,
)
from .shadow_buy_writer_policy import (
    FastPaperShadowBuyWriterPolicy,
    read_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
)
from .shadow_open_quote_writer import (
    run_fast_paper_shadow_open_quote_writer_cycle,
)
from .shadow_open_source_publisher import (
    run_fast_paper_shadow_open_source_publisher_cycle,
)
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
    FastPaperShadowServiceError,
    bootstrap_fast_paper_shadow_service,
    load_fast_paper_shadow_service_config,
)
from .shadow_service_coordinator import (
    FastPaperShadowServiceCoordinatorResult,
    run_fast_paper_shadow_service_coordinated_cycle,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
    FastPaperShadowServiceExecutionConfig,
    bootstrap_fast_paper_shadow_service_execution,
    load_fast_paper_shadow_service_execution_config,
)
from .shadow_skip_source_publisher import (
    run_fast_paper_shadow_skip_source_publisher_cycle,
)


_STATUS_SCHEMA_NAME = "shreks.fast_paper_shadow_supervisor_status"
_STATUS_SCHEMA_VERSION = 1


class FastPaperShadowSupervisorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowSupervisorConfig:
    decision_config: FastPaperShadowServiceConfig
    execution_config: FastPaperShadowServiceExecutionConfig
    buy_authority_source_directory: Path
    quote_usd_source_directory: Path
    reduction_source_directory: Path
    pending_buy_retry_source_directory: Path
    buy_writer_policy_path: Path

    def __post_init__(self) -> None:
        if type(self.decision_config) is not FastPaperShadowServiceConfig:
            raise ValueError(
                "decision_config must be exact FastPaperShadowServiceConfig"
            )
        if (
            type(self.execution_config)
            is not FastPaperShadowServiceExecutionConfig
        ):
            raise ValueError(
                "execution_config must be exact FastPaperShadowServiceExecutionConfig"
            )
        for name in (
            "buy_authority_source_directory",
            "quote_usd_source_directory",
            "reduction_source_directory",
            "pending_buy_retry_source_directory",
            "buy_writer_policy_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be Path")
            if not value.is_absolute():
                raise ValueError(f"{name} must be absolute")


@dataclass(frozen=True, slots=True)
class FastPaperShadowSupervisorBootstrap:
    decision_bootstrap: FastPaperShadowServiceBootstrap
    execution_bootstrap: FastPaperShadowServiceExecutionBootstrap
    buy_writer_policy: FastPaperShadowBuyWriterPolicy


def load_fast_paper_shadow_supervisor_config(
    environment: dict[str, str] | None = None,
) -> FastPaperShadowSupervisorConfig:
    env = dict(os.environ if environment is None else environment)

    def required_path(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise FastPaperShadowSupervisorError(
                f"missing required shadow supervisor setting {name}"
            )
        return Path(value).expanduser().resolve(strict=False)

    try:
        decision_config = load_fast_paper_shadow_service_config(env)
        execution_config = load_fast_paper_shadow_service_execution_config(env)
        return FastPaperShadowSupervisorConfig(
            decision_config=decision_config,
            execution_config=execution_config,
            buy_authority_source_directory=required_path(
                "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY"
            ),
            quote_usd_source_directory=required_path(
                "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY"
            ),
            reduction_source_directory=required_path(
                "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY"
            ),
            pending_buy_retry_source_directory=required_path(
                "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY"
            ),
            buy_writer_policy_path=required_path(
                "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH"
            ),
        )
    except FastPaperShadowSupervisorError:
        raise
    except (FastPaperShadowServiceError, TypeError, ValueError) as exc:
        raise FastPaperShadowSupervisorError(
            "shadow supervisor configuration is invalid"
        ) from exc


def bootstrap_fast_paper_shadow_supervisor(
    config: FastPaperShadowSupervisorConfig,
) -> FastPaperShadowSupervisorBootstrap:
    if type(config) is not FastPaperShadowSupervisorConfig:
        raise FastPaperShadowSupervisorError(
            "config must be exact FastPaperShadowSupervisorConfig"
        )
    try:
        decision_bootstrap = bootstrap_fast_paper_shadow_service(
            config.decision_config,
        )
        execution_bootstrap = (
            bootstrap_fast_paper_shadow_service_execution(
                decision_bootstrap.manifest,
                config.execution_config,
            )
        )
        buy_writer_policy = read_fast_paper_shadow_buy_writer_policy(
            config.buy_writer_policy_path
        )
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            decision_bootstrap.manifest,
            decision_bootstrap.policy,
            buy_writer_policy,
        )
        _validate_source_directories(config)
    except (
        FastPaperShadowServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperShadowSupervisorError(
            "shadow supervisor bootstrap failed closed"
        ) from exc
    return FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=decision_bootstrap,
        execution_bootstrap=execution_bootstrap,
        buy_writer_policy=buy_writer_policy,
    )


def run_fast_paper_shadow_supervisor_cycle(
    bootstrap: FastPaperShadowSupervisorBootstrap,
    config: FastPaperShadowSupervisorConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
) -> tuple[FastPaperShadowSupervisorBootstrap, int, int]:
    if type(bootstrap) is not FastPaperShadowSupervisorBootstrap:
        raise FastPaperShadowSupervisorError(
            "bootstrap must be exact FastPaperShadowSupervisorBootstrap"
        )
    if type(config) is not FastPaperShadowSupervisorConfig:
        raise FastPaperShadowSupervisorError(
            "config must be exact FastPaperShadowSupervisorConfig"
        )
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    now = _clock_value(clock)
    try:
        run_fast_paper_shadow_skip_source_publisher_cycle(
            bootstrap.decision_bootstrap.manifest,
            bootstrap.execution_bootstrap,
            decision_evidence_directory=(
                config.decision_config.evidence_directory
            ),
        )
        writer_policy = bootstrap.buy_writer_policy
        run_fast_paper_shadow_buy_authority_writer_cycle(
            bootstrap.decision_bootstrap,
            bootstrap.execution_bootstrap,
            decision_evidence_directory=(
                config.decision_config.evidence_directory
            ),
            buy_authority_source_directory=(
                config.buy_authority_source_directory
            ),
            quote_usd_source_directory=(
                config.quote_usd_source_directory
            ),
            market_read_policy=writer_policy.market_read_policy,
            regime_read_policy=writer_policy.regime_read_policy,
            regime_policy=writer_policy.regime_policy,
            safety_policy=writer_policy.safety_policy,
            safety_probe_identity=writer_policy.safety_probe_identity,
            execution_economics_policies=(
                writer_policy.execution_economics_policies
            ),
            operator_risk_control_path=(
                writer_policy.operator_risk_control_path
            ),
            entry_authority_binary_path=(
                writer_policy.entry_authority_binary_path
            ),
            day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
            data_healthy=writer_policy.data_healthy,
            execution_healthy=writer_policy.execution_healthy,
            global_risk_halt=writer_policy.global_risk_halt,
        )
        run_fast_paper_shadow_buy_source_publisher_cycle(
            bootstrap.decision_bootstrap.manifest,
            bootstrap.execution_bootstrap,
            decision_evidence_directory=(
                config.decision_config.evidence_directory
            ),
            buy_authority_source_directory=(
                config.buy_authority_source_directory
            ),
            quote_usd_source_directory=(
                config.quote_usd_source_directory
            ),
        )
        run_fast_paper_shadow_open_quote_writer_cycle(
            bootstrap.decision_bootstrap,
            bootstrap.execution_bootstrap,
            reduction_source_directory=(
                config.reduction_source_directory
            ),
            clock_unix_ms=lambda: now,
        )
        run_fast_paper_shadow_open_source_publisher_cycle(
            bootstrap.decision_bootstrap.manifest,
            bootstrap.execution_bootstrap,
            decision_evidence_directory=(
                config.decision_config.evidence_directory
            ),
            quote_usd_source_directory=(
                config.quote_usd_source_directory
            ),
        )
        result = run_fast_paper_shadow_service_coordinated_cycle(
            bootstrap.decision_bootstrap,
            config.decision_config,
            config.execution_config,
            clock_unix_ms=lambda: now,
            reduction_source_directory=(
                config.reduction_source_directory
            ),
            pending_buy_retry_source_directory=(
                config.pending_buy_retry_source_directory
            ),
            committed_at_unix_ms=now,
        )
    except (
        FastPaperShadowServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperShadowSupervisorError(
            "shadow supervisor coordinated cycle failed closed"
        ) from exc
    if type(result) is not FastPaperShadowServiceCoordinatorResult:
        raise FastPaperShadowSupervisorError(
            "coordinator returned incompatible result"
        )
    return (
        FastPaperShadowSupervisorBootstrap(
            decision_bootstrap=result.decision_bootstrap,
            execution_bootstrap=result.execution_bootstrap,
            buy_writer_policy=bootstrap.buy_writer_policy,
        ),
        result.decisions_produced,
        result.executions_committed,
    )


def run_fast_paper_shadow_supervisor(
    config: FastPaperShadowSupervisorConfig,
    *,
    stop_event: Event | object | None = None,
    clock_unix_ms: Callable[[], int] | None = None,
    status_sink: Callable[[str], object] | None = None,
) -> tuple[int, int]:
    bootstrap = bootstrap_fast_paper_shadow_supervisor(config)
    event = Event() if stop_event is None else stop_event
    sink = print if status_sink is None else status_sink
    completed_cycles = 0
    decisions_produced = 0
    executions_committed = 0

    while not event.is_set():
        (
            bootstrap,
            produced,
            committed,
        ) = run_fast_paper_shadow_supervisor_cycle(
            bootstrap,
            config,
            clock_unix_ms=clock_unix_ms,
        )
        completed_cycles += 1
        decisions_produced += produced
        executions_committed += committed
        sink(
            _status_line(
                bootstrap,
                state="RUNNING",
                completed_cycles=completed_cycles,
                decisions_produced=decisions_produced,
                executions_committed=executions_committed,
            )
        )
        if event.wait(config.decision_config.cycle_interval_seconds):
            break

    return decisions_produced, executions_committed


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--preflight"]):
        _emit_failure(FastPaperShadowSupervisorError("unsupported argument"))
        return 2

    try:
        config = load_fast_paper_shadow_supervisor_config()
        if args == ["--preflight"]:
            bootstrap = bootstrap_fast_paper_shadow_supervisor(config)
            print(
                _status_line(
                    bootstrap,
                    state="READY",
                    completed_cycles=0,
                    decisions_produced=0,
                    executions_committed=0,
                )
            )
            return 0

        event = Event()
        previous = _install_signal_handlers(event)
        try:
            run_fast_paper_shadow_supervisor(
                config,
                stop_event=event,
            )
        finally:
            _restore_signal_handlers(previous)
        return 0
    except FastPaperShadowSupervisorError as exc:
        _emit_failure(exc)
        return 1


def _validate_source_directories(
    config: FastPaperShadowSupervisorConfig,
) -> None:
    roots = (
        config.decision_config.evidence_directory,
        config.execution_config.source_directory,
        config.buy_authority_source_directory,
        config.quote_usd_source_directory,
        config.reduction_source_directory,
        config.pending_buy_retry_source_directory,
    )
    resolved: list[Path] = []
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise ValueError(
                "shadow supervisor source roots must be existing regular non-symlink directories"
            )
        resolved.append(root.resolve(strict=True))
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if _paths_overlap(left, right):
                raise ValueError(
                    "shadow supervisor decision/execution source roots must be distinct and non-overlapping"
                )


def _clock_value(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperShadowSupervisorError(
            "shadow supervisor clock failed"
        ) from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FastPaperShadowSupervisorError(
            "shadow supervisor clock must return a non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _status_line(
    bootstrap: FastPaperShadowSupervisorBootstrap,
    *,
    state: str,
    completed_cycles: int,
    decisions_produced: int,
    executions_committed: int,
) -> str:
    decision = bootstrap.decision_bootstrap
    execution = bootstrap.execution_bootstrap
    decision_cursor = decision.state.cursor
    execution_state = execution.runtime_state
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_SHADOW_COORDINATED",
        "state": state,
        "manifest_fingerprint_sha256": (
            decision.manifest.manifest_fingerprint_sha256
        ),
        "champion_version": decision.manifest.champion_version,
        "champion_fingerprint_sha256": (
            decision.manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": decision.manifest.action_policy.version,
        "completed_cycles": completed_cycles,
        "decisions_produced": decisions_produced,
        "executions_committed": executions_committed,
        "decision_cursor_sequence": (
            None
            if decision_cursor is None
            else decision_cursor.decision_sequence
        ),
        "execution_cursor_sequence": (
            execution_state.last_processed_source_sequence
        ),
        "paper_checkpoint_sequence": execution.checkpoint.sequence,
        "pending_buy": execution_state.pending_buy is not None,
        "open_market_positions": len(execution_state.market_positions),
    }
    return _canonical(document).rstrip("\n")


def _emit_failure(error: BaseException) -> None:
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_SHADOW_COORDINATED",
        "state": "FAILED",
        "error_type": type(error).__name__,
    }
    print(_canonical(document).rstrip("\n"), file=sys.stderr)


def _install_signal_handlers(
    event: Event,
) -> dict[signal.Signals, object]:
    previous: dict[signal.Signals, object] = {}

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)
    return previous


def _restore_signal_handlers(
    previous: dict[signal.Signals, object],
) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
