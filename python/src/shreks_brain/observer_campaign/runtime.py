from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import signal
import sys
from threading import Event
import time
from types import FrameType

from shreks_brain.paper_loop import PaperLoopState
from shreks_brain.risk_control import (
    RiskControlStateError,
    load_operator_risk_control_state,
)
from shreks_brain.risk_control.paper_runtime import (
    ControlledObserverPaperCampaignCoordinatorRunner,
)

from .coordinator import (
    ObserverCampaignCoordinatorError,
    ObserverPaperCampaignCoordinatorRunner,
)
from .runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
    ObserverPaperCampaignRuntimeConfigError,
    load_observer_paper_campaign_runtime_config,
)
from .runtime_manifest import (
    ObserverPaperCampaignRuntimeManifest,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION = "g1c-paper-runtime-status-v1"


class ObserverPaperCampaignRuntimeError(RuntimeError):
    """Raised when the G1C PAPER runtime cannot continue safely."""


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignRuntimeBootstrap:
    manifest: ObserverPaperCampaignRuntimeManifest
    runner: ObserverPaperCampaignCoordinatorRunner
    restored_state: PaperLoopState

    def __post_init__(self) -> None:
        if type(self.manifest) is not ObserverPaperCampaignRuntimeManifest:
            raise ObserverPaperCampaignRuntimeError(
                "bootstrap manifest must be an exact ObserverPaperCampaignRuntimeManifest"
            )
        if type(self.runner) is not ObserverPaperCampaignCoordinatorRunner:
            raise ObserverPaperCampaignRuntimeError(
                "bootstrap runner must be an exact ObserverPaperCampaignCoordinatorRunner"
            )
        if type(self.restored_state) is not PaperLoopState:
            raise ObserverPaperCampaignRuntimeError(
                "bootstrap restored_state must be an exact PaperLoopState"
            )


def bootstrap_observer_paper_campaign_runtime(
    config: ObserverPaperCampaignRuntimeConfig,
) -> ObserverPaperCampaignRuntimeBootstrap:
    if type(config) is not ObserverPaperCampaignRuntimeConfig:
        raise ObserverPaperCampaignRuntimeError(
            "runtime config must be an exact ObserverPaperCampaignRuntimeConfig"
        )

    try:
        payload = config.manifest_path.read_bytes()
    except OSError as error:
        raise ObserverPaperCampaignRuntimeError(
            "campaign manifest could not be read"
        ) from error

    try:
        manifest = decode_observer_paper_campaign_runtime_manifest(payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise ObserverPaperCampaignRuntimeError(
            "campaign manifest validation failed"
        ) from error

    try:
        runner = ObserverPaperCampaignCoordinatorRunner(
            config.observer_database_path,
            config.evidence_path,
            manifest.candidate,
            manifest.paper_run_id,
            manifest.initial_state,
            manifest.policy_bundle,
            manifest.risk_environment,
            manifest.selection_policy,
            recent_performance=manifest.recent_performance,
            global_risk_halt=manifest.global_risk_halt,
        )
        restored_state = runner.load_state()
    except (ObserverCampaignCoordinatorError, OSError, TypeError, ValueError) as error:
        raise ObserverPaperCampaignRuntimeError(
            "paper campaign runtime bootstrap failed"
        ) from error

    return ObserverPaperCampaignRuntimeBootstrap(
        manifest=manifest,
        runner=runner,
        restored_state=restored_state,
    )


def preflight_observer_paper_campaign_runtime(
    config: ObserverPaperCampaignRuntimeConfig,
    *,
    status_sink: Callable[[str], object] | None = None,
) -> ObserverPaperCampaignRuntimeBootstrap:
    """Validate durable PAPER recovery state without advancing the campaign."""

    bootstrap = bootstrap_observer_paper_campaign_runtime(config)
    sink = print if status_sink is None else status_sink
    sink(_preflight_status_line(bootstrap))
    return bootstrap


def run_observer_paper_campaign_runtime(
    config: ObserverPaperCampaignRuntimeConfig,
    *,
    stop_event: Event | None = None,
    clock_unix_ms: Callable[[], int] | None = None,
    status_sink: Callable[[str], object] | None = None,
) -> int:
    if type(config) is not ObserverPaperCampaignRuntimeConfig:
        raise ObserverPaperCampaignRuntimeError(
            "runtime config must be an exact ObserverPaperCampaignRuntimeConfig"
        )

    bootstrap = bootstrap_observer_paper_campaign_runtime(config)
    event = Event() if stop_event is None else stop_event
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    sink = print if status_sink is None else status_sink
    completed_cycles = 0

    while not event.is_set():
        as_of_unix_ms = _runtime_timestamp(clock)
        try:
            cycle_runner: ObserverPaperCampaignCoordinatorRunner
            if config.risk_control_path is None:
                cycle_runner = bootstrap.runner
            else:
                halt_new_entries, kill_switch_active = _current_operator_controls(
                    config.risk_control_path
                )
                cycle_runner = _controlled_runner(
                    config,
                    bootstrap.manifest,
                    halt_new_entries=halt_new_entries,
                    kill_switch_active=kill_switch_active,
                )
            result = cycle_runner.run_cycle(as_of_unix_ms, as_of_unix_ms)
            evaluated_trade_count = len(cycle_runner.evaluated_trades())
        except (ObserverCampaignCoordinatorError, OSError, TypeError, ValueError) as error:
            raise ObserverPaperCampaignRuntimeError(
                "paper campaign cycle failed closed"
            ) from error

        completed_cycles += 1
        sink(
            _status_line(
                bootstrap.manifest,
                completed_cycles,
                as_of_unix_ms,
                result.next_state.last_cycle_at_unix_ms,
                evaluated_trade_count,
            )
        )

        if config.max_cycles is not None and completed_cycles >= config.max_cycles:
            break
        if event.wait(config.cycle_interval_seconds):
            break

    return completed_cycles


def _current_operator_controls(path) -> tuple[bool, bool]:
    try:
        state = load_operator_risk_control_state(path)
    except (RiskControlStateError, OSError, TypeError, ValueError):
        # Missing/corrupt configured state blocks entries but does not invent an
        # emergency liquidation signal. The next cycle re-reads the file.
        return True, False
    return state.halt_new_entries, state.kill_switch_active


def _controlled_runner(
    config: ObserverPaperCampaignRuntimeConfig,
    manifest: ObserverPaperCampaignRuntimeManifest,
    *,
    halt_new_entries: bool,
    kill_switch_active: bool,
) -> ControlledObserverPaperCampaignCoordinatorRunner:
    return ControlledObserverPaperCampaignCoordinatorRunner(
        config.observer_database_path,
        config.evidence_path,
        manifest.candidate,
        manifest.paper_run_id,
        manifest.initial_state,
        manifest.policy_bundle,
        manifest.risk_environment,
        manifest.selection_policy,
        recent_performance=manifest.recent_performance,
        global_risk_halt=manifest.global_risk_halt,
        operator_entry_halt_active=halt_new_entries,
        operator_kill_switch_active=kill_switch_active,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--preflight"]):
        _emit_failure_status(
            ObserverPaperCampaignRuntimeError("unsupported paper runtime argument")
        )
        return 2

    try:
        config = load_observer_paper_campaign_runtime_config()
    except (ObserverPaperCampaignRuntimeConfigError, OSError, TypeError, ValueError) as error:
        _emit_failure_status(error)
        return 1

    if args == ["--preflight"]:
        try:
            preflight_observer_paper_campaign_runtime(config)
        except ObserverPaperCampaignRuntimeError as error:
            _emit_failure_status(error)
            return 1
        return 0

    stop_event = Event()
    previous_handlers = _install_signal_handlers(stop_event)
    try:
        run_observer_paper_campaign_runtime(config, stop_event=stop_event)
    except ObserverPaperCampaignRuntimeError as error:
        _emit_failure_status(error)
        return 1
    finally:
        _restore_signal_handlers(previous_handlers)
    return 0


def _runtime_timestamp(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as error:
        raise ObserverPaperCampaignRuntimeError("runtime clock failed") from error
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverPaperCampaignRuntimeError(
            "runtime clock must return a non-negative integer millisecond timestamp"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _preflight_status_line(
    bootstrap: ObserverPaperCampaignRuntimeBootstrap,
) -> str:
    document = {
        "schema_version": OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION,
        "mode": "PAPER",
        "state": "READY",
        "paper_run_id": bootstrap.manifest.paper_run_id,
        "candidate_version": bootstrap.manifest.candidate.candidate_version,
        "manifest_fingerprint_sha256": bootstrap.manifest.manifest_fingerprint_sha256,
        "state_as_of_unix_ms": bootstrap.restored_state.last_cycle_at_unix_ms,
        "global_risk_halt": bootstrap.manifest.global_risk_halt,
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _status_line(
    manifest: ObserverPaperCampaignRuntimeManifest,
    completed_cycles: int,
    cycle_as_of_unix_ms: int,
    state_as_of_unix_ms: int,
    evaluated_trade_count: int,
) -> str:
    document = {
        "schema_version": OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION,
        "mode": "PAPER",
        "paper_run_id": manifest.paper_run_id,
        "candidate_version": manifest.candidate.candidate_version,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "completed_cycles": completed_cycles,
        "cycle_as_of_unix_ms": cycle_as_of_unix_ms,
        "state_as_of_unix_ms": state_as_of_unix_ms,
        "evaluated_trade_count": evaluated_trade_count,
        "global_risk_halt": manifest.global_risk_halt,
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _install_signal_handlers(stop_event: Event) -> dict[signal.Signals, object]:
    previous: dict[signal.Signals, object] = {}

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)
    return previous


def _restore_signal_handlers(previous: dict[signal.Signals, object]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _emit_failure_status(error: BaseException) -> None:
    document = {
        "schema_version": OBSERVER_PAPER_CAMPAIGN_RUNTIME_STATUS_SCHEMA_VERSION,
        "mode": "PAPER",
        "state": "FAILED",
        "error_type": type(error).__name__,
    }
    print(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
