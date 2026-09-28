from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import sys
from threading import Event
import time
from types import FrameType
from typing import Callable

from .authoritative_coordinator import (
    FastPaperAuthoritativeCoordinatorResult,
    run_fast_paper_authoritative_coordinated_cycle,
)
from .authoritative_file_authority import (
    FastPaperAuthoritativeAuthorityUnavailable,
    require_fast_paper_authoritative_reduction_source,
    resolve_fast_paper_authoritative_execution_authority,
    resolve_fast_paper_authoritative_pending_buy_retry,
)
from .authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionBootstrap,
    FastPaperAuthoritativeServiceExecutionConfig,
    bootstrap_fast_paper_authoritative_service_execution,
    load_fast_paper_authoritative_service_execution_config,
)
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
    FastPaperShadowServiceError,
    bootstrap_fast_paper_shadow_service,
)


_STATUS_SCHEMA_NAME = "shreks.fast_paper_authoritative_runtime_status"
_STATUS_SCHEMA_VERSION = 1
_DEFAULT_INTERVAL_SECONDS = 2.0


class FastPaperAuthoritativeRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeRuntimeConfig:
    decision_config: FastPaperShadowServiceConfig
    execution_config: FastPaperAuthoritativeServiceExecutionConfig
    buy_authority_source_directory: Path
    quote_usd_source_directory: Path
    reduction_source_directory: Path
    pending_buy_retry_source_directory: Path

    def __post_init__(self) -> None:
        if type(self.decision_config) is not FastPaperShadowServiceConfig:
            raise ValueError(
                "decision_config must be exact FastPaperShadowServiceConfig"
            )
        if (
            type(self.execution_config)
            is not FastPaperAuthoritativeServiceExecutionConfig
        ):
            raise ValueError(
                "execution_config must be exact FastPaperAuthoritativeServiceExecutionConfig"
            )
        for name in (
            "buy_authority_source_directory",
            "quote_usd_source_directory",
            "reduction_source_directory",
            "pending_buy_retry_source_directory",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be Path")
            if not value.is_absolute():
                raise ValueError(f"{name} must be absolute")


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeRuntimeBootstrap:
    decision_bootstrap: FastPaperShadowServiceBootstrap
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap

    def __post_init__(self) -> None:
        if type(self.decision_bootstrap) is not FastPaperShadowServiceBootstrap:
            raise ValueError(
                "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
            )
        if (
            type(self.execution_bootstrap)
            is not FastPaperAuthoritativeServiceExecutionBootstrap
        ):
            raise ValueError(
                "execution_bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
            )


def load_fast_paper_authoritative_runtime_config(
    environment: dict[str, str] | None = None,
) -> FastPaperAuthoritativeRuntimeConfig:
    env = dict(os.environ if environment is None else environment)

    def required_path(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise FastPaperAuthoritativeRuntimeError(
                f"missing required authoritative runtime setting {name}"
            )
        return Path(value).expanduser().resolve(strict=False)

    interval_text = env.get(
        "SHREKS_FAST_PAPER_INTERVAL_SECONDS",
        str(_DEFAULT_INTERVAL_SECONDS),
    )
    try:
        interval = float(interval_text)
    except ValueError as exc:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime interval is invalid"
        ) from exc
    if (
        isinstance(interval, bool)
        or not math.isfinite(interval)
        or not 0.0 < interval <= 3600.0
    ):
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime interval must be finite within (0,3600]"
        )

    try:
        decision_config = FastPaperShadowServiceConfig(
            manifest_path=required_path(
                "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"
            ),
            policy_path=required_path(
                "SHREKS_FAST_PAPER_SERVICE_POLICY_PATH"
            ),
            evidence_directory=required_path(
                "SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY"
            ),
            cycle_interval_seconds=interval,
            maximum_decisions=1,
            checkpoint_path=required_path(
                "SHREKS_FAST_PAPER_AUTHORITATIVE_DECISION_CHECKPOINT_PATH"
            ),
        )
        execution_config = (
            load_fast_paper_authoritative_service_execution_config(env)
        )
        return FastPaperAuthoritativeRuntimeConfig(
            decision_config=decision_config,
            execution_config=execution_config,
            buy_authority_source_directory=required_path(
                "SHREKS_FAST_PAPER_BUY_AUTHORITY_SOURCE_DIRECTORY"
            ),
            quote_usd_source_directory=required_path(
                "SHREKS_FAST_PAPER_QUOTE_USD_SOURCE_DIRECTORY"
            ),
            reduction_source_directory=required_path(
                "SHREKS_FAST_PAPER_REDUCTION_SOURCE_DIRECTORY"
            ),
            pending_buy_retry_source_directory=required_path(
                "SHREKS_FAST_PAPER_PENDING_BUY_RETRY_SOURCE_DIRECTORY"
            ),
        )
    except FastPaperAuthoritativeRuntimeError:
        raise
    except (TypeError, ValueError) as exc:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime configuration is invalid"
        ) from exc


def bootstrap_fast_paper_authoritative_runtime(
    config: FastPaperAuthoritativeRuntimeConfig,
) -> FastPaperAuthoritativeRuntimeBootstrap:
    if type(config) is not FastPaperAuthoritativeRuntimeConfig:
        raise FastPaperAuthoritativeRuntimeError(
            "config must be exact FastPaperAuthoritativeRuntimeConfig"
        )
    try:
        decision_bootstrap = bootstrap_fast_paper_shadow_service(
            config.decision_config
        )
        execution_bootstrap = (
            bootstrap_fast_paper_authoritative_service_execution(
                decision_bootstrap.manifest,
                config.execution_config,
            )
        )
        _validate_source_directories(config)
    except (
        FastPaperShadowServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime bootstrap failed closed"
        ) from exc
    return FastPaperAuthoritativeRuntimeBootstrap(
        decision_bootstrap=decision_bootstrap,
        execution_bootstrap=execution_bootstrap,
    )


def run_fast_paper_authoritative_runtime_cycle(
    bootstrap: FastPaperAuthoritativeRuntimeBootstrap,
    config: FastPaperAuthoritativeRuntimeConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
) -> tuple[FastPaperAuthoritativeRuntimeBootstrap, int, int]:
    if type(bootstrap) is not FastPaperAuthoritativeRuntimeBootstrap:
        raise FastPaperAuthoritativeRuntimeError(
            "bootstrap must be exact FastPaperAuthoritativeRuntimeBootstrap"
        )
    if type(config) is not FastPaperAuthoritativeRuntimeConfig:
        raise FastPaperAuthoritativeRuntimeError(
            "config must be exact FastPaperAuthoritativeRuntimeConfig"
        )
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    now = _clock_value(clock)
    manifest = bootstrap.decision_bootstrap.manifest
    reduction_cache: dict[str, object] = {}

    def reduction_record(record):
        market_key = f"{record.venue}:{record.mint}:{record.quote_mint}"
        cached = reduction_cache.get(market_key)
        if cached is not None:
            return cached
        value = require_fast_paper_authoritative_reduction_source(
            manifest,
            bootstrap.execution_bootstrap,
            market_key,
            reduction_source_directory=config.reduction_source_directory,
        )
        reduction_cache[market_key] = value
        return value

    def reduction_read_resolver(record, position):
        if position.kind == "FLAT":
            return ()
        return reduction_record(record).reduction_reads

    def exit_input_amount_resolver(record, position):
        if position.kind == "FLAT":
            raise ValueError(
                "FLAT posture has no authoritative OPEN full-exit input"
            )
        return reduction_record(record).exit_input_amount_raw

    def execution_authority_resolver(evidence, execution_bootstrap):
        return resolve_fast_paper_authoritative_execution_authority(
            manifest,
            execution_bootstrap,
            evidence,
            buy_authority_source_directory=(
                config.buy_authority_source_directory
            ),
            quote_usd_source_directory=(
                config.quote_usd_source_directory
            ),
        )

    def pending_buy_retry_resolver(execution_bootstrap, evidence):
        return resolve_fast_paper_authoritative_pending_buy_retry(
            manifest,
            execution_bootstrap,
            evidence,
            pending_buy_retry_source_directory=(
                config.pending_buy_retry_source_directory
            ),
        )

    try:
        result = run_fast_paper_authoritative_coordinated_cycle(
            bootstrap.decision_bootstrap,
            config.decision_config,
            config.execution_config,
            clock_unix_ms=lambda: now,
            reduction_read_resolver=reduction_read_resolver,
            exit_input_amount_resolver=exit_input_amount_resolver,
            execution_authority_resolver=execution_authority_resolver,
            pending_buy_retry_resolver=pending_buy_retry_resolver,
            committed_at_unix_ms=now,
        )
    except FastPaperAuthoritativeAuthorityUnavailable:
        return bootstrap, 0, 0
    except (
        FastPaperShadowServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime coordinated cycle failed closed"
        ) from exc

    if type(result) is not FastPaperAuthoritativeCoordinatorResult:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative coordinator returned incompatible result"
        )
    return (
        FastPaperAuthoritativeRuntimeBootstrap(
            decision_bootstrap=result.decision_bootstrap,
            execution_bootstrap=result.execution_bootstrap,
        ),
        result.decisions_produced,
        result.executions_committed,
    )


def run_fast_paper_authoritative_runtime(
    config: FastPaperAuthoritativeRuntimeConfig,
    *,
    stop_event: Event | object | None = None,
    clock_unix_ms: Callable[[], int] | None = None,
    status_sink: Callable[[str], object] | None = None,
) -> tuple[int, int]:
    bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
    event = Event() if stop_event is None else stop_event
    sink = print if status_sink is None else status_sink
    completed_cycles = 0
    decisions_produced = 0
    executions_committed = 0

    while not event.is_set():
        bootstrap, produced, committed = (
            run_fast_paper_authoritative_runtime_cycle(
                bootstrap,
                config,
                clock_unix_ms=clock_unix_ms,
            )
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
        _emit_failure(
            FastPaperAuthoritativeRuntimeError("unsupported argument")
        )
        return 2
    try:
        config = load_fast_paper_authoritative_runtime_config()
        if args == ["--preflight"]:
            bootstrap = bootstrap_fast_paper_authoritative_runtime(config)
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
            run_fast_paper_authoritative_runtime(
                config,
                stop_event=event,
            )
        finally:
            _restore_signal_handlers(previous)
        return 0
    except FastPaperAuthoritativeRuntimeError as exc:
        _emit_failure(exc)
        return 1


def _validate_source_directories(
    config: FastPaperAuthoritativeRuntimeConfig,
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
                "authoritative runtime source roots must be existing regular non-symlink directories"
            )
        resolved.append(root.resolve(strict=True))
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if _paths_overlap(left, right):
                raise ValueError(
                    "authoritative runtime source roots must be distinct and non-overlapping"
                )


def _clock_value(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime clock failed"
        ) from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FastPaperAuthoritativeRuntimeError(
            "authoritative runtime clock must return a non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _status_line(
    bootstrap: FastPaperAuthoritativeRuntimeBootstrap,
    *,
    state: str,
    completed_cycles: int,
    decisions_produced: int,
    executions_committed: int,
) -> str:
    decision = bootstrap.decision_bootstrap
    execution = bootstrap.execution_bootstrap
    cursor = decision.state.cursor
    runtime = execution.runtime_state
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_AUTHORITATIVE_FAST",
        "state": state,
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live": "DISABLED",
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
            None if cursor is None else cursor.decision_sequence
        ),
        "execution_cursor_sequence": (
            runtime.last_processed_source_sequence
        ),
        "paper_checkpoint_sequence": execution.checkpoint.sequence,
        "pending_buy": execution.checkpoint.state.pending_buy is not None,
        "open_market_positions": len(runtime.market_positions),
    }
    return _canonical(document).rstrip("\n")


def _emit_failure(error: BaseException) -> None:
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_AUTHORITATIVE_FAST",
        "state": "FAILED",
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live": "DISABLED",
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
