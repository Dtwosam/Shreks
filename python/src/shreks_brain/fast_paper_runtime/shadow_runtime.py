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
from typing import Any, Callable

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignDecisionPosition,
    FastCampaignReduceExecutionCost,
)

from .codec import (
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
    write_fast_paper_runtime_state,
)
from .feed import fetch_fast_paper_runtime_feature_batch
from .models import FastPaperRuntimeManifest, FastPaperRuntimeState
from .shadow import (
    FastPaperShadowDecisionInput,
    evaluate_fast_paper_shadow_batch,
)
from .shadow_store import FastPaperShadowEvidenceStore


_SHADOW_INPUT_SCHEMA_NAME = "shreks.fast_paper_shadow_runtime_inputs"
_SHADOW_INPUT_SCHEMA_VERSION = 1
_STATUS_SCHEMA = "shreks.fast_paper_shadow_runtime_status"
_STATUS_VERSION = 1
_DEFAULT_INTERVAL_SECONDS = 2.0
_DEFAULT_MAXIMUM_DECISIONS = 64


class FastPaperShadowRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowRuntimeConfig:
    manifest_path: Path
    shadow_state_path: Path
    shadow_evidence_path: Path
    shadow_input_path: Path
    cycle_interval_seconds: float
    maximum_decisions: int

    def __post_init__(self) -> None:
        for name in (
            "manifest_path",
            "shadow_state_path",
            "shadow_evidence_path",
            "shadow_input_path",
        ):
            if type(getattr(self, name)) is not Path:
                raise ValueError(f"{name} must be exact Path")
        if (
            not isinstance(self.cycle_interval_seconds, (int, float))
            or isinstance(self.cycle_interval_seconds, bool)
            or not 0.0 < float(self.cycle_interval_seconds) <= 3600.0
        ):
            raise ValueError(
                "cycle_interval_seconds must be finite within (0, 3600]"
            )
        if (
            isinstance(self.maximum_decisions, bool)
            or not isinstance(self.maximum_decisions, int)
            or not 1 <= self.maximum_decisions <= 10_000
        ):
            raise ValueError(
                "maximum_decisions must be an integer within [1, 10000]"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowRuntimeBootstrap:
    manifest: FastPaperRuntimeManifest
    state: FastPaperRuntimeState
    store: FastPaperShadowEvidenceStore


def load_fast_paper_shadow_runtime_config(
    environment: dict[str, str] | None = None,
) -> FastPaperShadowRuntimeConfig:
    env = dict(os.environ if environment is None else environment)

    def required(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise FastPaperShadowRuntimeError(
                f"missing required shadow runtime setting {name}"
            )
        return Path(value).expanduser().resolve(strict=False)

    interval_text = env.get(
        "SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS",
        str(_DEFAULT_INTERVAL_SECONDS),
    )
    limit_text = env.get(
        "SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS",
        str(_DEFAULT_MAXIMUM_DECISIONS),
    )
    try:
        interval = float(interval_text)
        maximum_decisions = int(limit_text)
    except ValueError as exc:
        raise FastPaperShadowRuntimeError(
            "shadow runtime cadence/batch settings are invalid"
        ) from exc

    return FastPaperShadowRuntimeConfig(
        manifest_path=required("SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"),
        shadow_state_path=required("SHREKS_FAST_PAPER_SHADOW_STATE_PATH"),
        shadow_evidence_path=required(
            "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_PATH"
        ),
        shadow_input_path=required("SHREKS_FAST_PAPER_SHADOW_INPUT_PATH"),
        cycle_interval_seconds=interval,
        maximum_decisions=maximum_decisions,
    )


def bootstrap_fast_paper_shadow_runtime(
    config: FastPaperShadowRuntimeConfig,
) -> FastPaperShadowRuntimeBootstrap:
    if type(config) is not FastPaperShadowRuntimeConfig:
        raise FastPaperShadowRuntimeError(
            "config must be exact FastPaperShadowRuntimeConfig"
        )
    try:
        manifest = read_fast_paper_runtime_manifest(config.manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        _require_shadow_paths(config, manifest)
        if config.shadow_state_path.exists():
            state = read_fast_paper_runtime_state(config.shadow_state_path)
            _require_state_manifest_alignment(state, manifest)
        else:
            state = build_fast_paper_runtime_state(manifest, cursor=None)
        store = FastPaperShadowEvidenceStore(
            config.shadow_evidence_path,
            manifest=manifest,
        )
        store.load()
        _load_shadow_inputs(config.shadow_input_path)
    except (OSError, TypeError, ValueError) as exc:
        raise FastPaperShadowRuntimeError(
            "learned shadow runtime bootstrap failed closed"
        ) from exc
    return FastPaperShadowRuntimeBootstrap(
        manifest=manifest,
        state=state,
        store=store,
    )


def run_fast_paper_shadow_cycle(
    bootstrap: FastPaperShadowRuntimeBootstrap,
    config: FastPaperShadowRuntimeConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
) -> tuple[FastPaperShadowRuntimeBootstrap, int]:
    if type(bootstrap) is not FastPaperShadowRuntimeBootstrap:
        raise FastPaperShadowRuntimeError(
            "bootstrap must be exact FastPaperShadowRuntimeBootstrap"
        )
    if type(config) is not FastPaperShadowRuntimeConfig:
        raise FastPaperShadowRuntimeError(
            "config must be exact FastPaperShadowRuntimeConfig"
        )
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    try:
        batch = fetch_fast_paper_runtime_feature_batch(
            bootstrap.manifest,
            bootstrap.state,
            maximum_decisions=config.maximum_decisions,
        )
        if not batch.records:
            return bootstrap, 0

        source_inputs = _load_shadow_inputs(config.shadow_input_path)
        decision_inputs = []
        for record in batch.records:
            source_event_id = (
                f"{record.decision_signature}:{record.decision_ordinal}"
            )
            raw = source_inputs.get(source_event_id)
            if raw is None:
                raise ValueError(
                    "exact shadow constraint evidence is missing for "
                    f"{source_event_id}"
                )
            evaluated_at = _runtime_timestamp(clock)
            decision_inputs.append(
                _decision_input(
                    record,
                    raw,
                    evaluated_at_unix_ms=evaluated_at,
                )
            )

        evidence = evaluate_fast_paper_shadow_batch(
            bootstrap.manifest,
            tuple(decision_inputs),
        )
        bootstrap.store.append_ledger(evidence)

        _write_shadow_state(
            batch.next_state,
            config.shadow_state_path,
            bootstrap.manifest,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise FastPaperShadowRuntimeError(
            "learned shadow runtime cycle failed closed"
        ) from exc

    return (
        FastPaperShadowRuntimeBootstrap(
            manifest=bootstrap.manifest,
            state=batch.next_state,
            store=bootstrap.store,
        ),
        len(batch.records),
    )


def run_fast_paper_shadow_runtime(
    config: FastPaperShadowRuntimeConfig,
    *,
    stop_event: Event | None = None,
    clock_unix_ms: Callable[[], int] | None = None,
    status_sink: Callable[[str], object] | None = None,
) -> int:
    bootstrap = bootstrap_fast_paper_shadow_runtime(config)
    event = Event() if stop_event is None else stop_event
    sink = print if status_sink is None else status_sink
    completed_cycles = 0
    processed_decisions = 0

    while not event.is_set():
        bootstrap, processed = run_fast_paper_shadow_cycle(
            bootstrap,
            config,
            clock_unix_ms=clock_unix_ms,
        )
        completed_cycles += 1
        processed_decisions += processed
        sink(
            _status_line(
                bootstrap,
                state="RUNNING",
                completed_cycles=completed_cycles,
                processed_decisions=processed_decisions,
            )
        )
        if event.wait(config.cycle_interval_seconds):
            break
    return processed_decisions


def _decision_input(
    record: Any,
    raw: dict[str, Any],
    *,
    evaluated_at_unix_ms: int,
) -> FastPaperShadowDecisionInput:
    expected = {
        "source_event_id",
        "quote_state",
        "position",
        "constraints",
    }
    if set(raw) != expected:
        raise ValueError(
            "shadow constraint input has unknown or missing fields"
        )
    expected_source = (
        f"{record.decision_signature}:{record.decision_ordinal}"
    )
    if raw["source_event_id"] != expected_source:
        raise ValueError("shadow constraint input source identity mismatch")
    position = _position(raw["position"])
    constraints = _constraints(raw["constraints"])
    return FastPaperShadowDecisionInput(
        record=record,
        position=position,
        constraints=constraints,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        quote_state=_text(raw["quote_state"], "quote_state"),
    )


def _position(value: object) -> FastCampaignDecisionPosition:
    if not isinstance(value, dict):
        raise ValueError("shadow position input must be an object")
    if set(value) not in ({"kind"}, {"kind", "current_exposure_fraction"}):
        raise ValueError("shadow position input fields are incompatible")
    kind = _text(value["kind"], "position.kind")
    current = value.get("current_exposure_fraction")
    return FastCampaignDecisionPosition(
        kind=kind,
        current_exposure_fraction=current,
    )


def _constraints(value: object) -> FastCampaignActionConstraints:
    if not isinstance(value, dict):
        raise ValueError("shadow constraints input must be an object")
    expected = {
        "max_exposure_fraction",
        "buy_economically_allowed",
        "expected_future_exit_cost_bps",
        "reduce_execution_costs",
        "sell_executable",
        "sell_now_cost_bps",
        "force_sell",
    }
    if set(value) != expected:
        raise ValueError("shadow constraints input fields are incompatible")
    raw_reduce = value["reduce_execution_costs"]
    if not isinstance(raw_reduce, list):
        raise ValueError("reduce_execution_costs must be a list")
    reduce = []
    for item in raw_reduce:
        if not isinstance(item, dict) or set(item) != {
            "target_exposure_fraction",
            "execution_cost_bps",
        }:
            raise ValueError("reduce execution cost fields are incompatible")
        reduce.append(
            FastCampaignReduceExecutionCost(
                target_exposure_fraction=item[
                    "target_exposure_fraction"
                ],
                execution_cost_bps=item["execution_cost_bps"],
            )
        )
    return FastCampaignActionConstraints(
        max_exposure_fraction=value["max_exposure_fraction"],
        buy_economically_allowed=value["buy_economically_allowed"],
        expected_future_exit_cost_bps=value[
            "expected_future_exit_cost_bps"
        ],
        reduce_execution_costs=tuple(reduce),
        sell_executable=value["sell_executable"],
        sell_now_cost_bps=value["sell_now_cost_bps"],
        force_sell=value["force_sell"],
    )


def _load_shadow_inputs(path: Path) -> dict[str, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow input source must be an existing regular non-symlink file"
        )
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("shadow input document is invalid") from exc
    if payload != _canonical(document):
        raise ValueError("shadow input document must use canonical JSON")
    if not isinstance(document, dict) or set(document) != {
        "schema_name",
        "schema_version",
        "inputs",
    }:
        raise ValueError("shadow input document fields are incompatible")
    if (
        document["schema_name"] != _SHADOW_INPUT_SCHEMA_NAME
        or document["schema_version"] != _SHADOW_INPUT_SCHEMA_VERSION
    ):
        raise ValueError("shadow input document schema is incompatible")
    raw_inputs = document["inputs"]
    if not isinstance(raw_inputs, list):
        raise ValueError("shadow inputs must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_inputs:
        if not isinstance(raw, dict):
            raise ValueError("shadow input must be an object")
        source_event_id = _text(
            raw.get("source_event_id"),
            "source_event_id",
        )
        if source_event_id in by_id:
            raise ValueError("shadow input source identity is duplicated")
        by_id[source_event_id] = raw
    return by_id


def _write_shadow_state(
    state: FastPaperRuntimeState,
    destination: Path,
    manifest: FastPaperRuntimeManifest,
) -> None:
    if destination in {
        Path(manifest.checkpoint_path).resolve(strict=False),
        Path(manifest.paper_evidence_path).resolve(strict=False),
    }:
        raise ValueError(
            "shadow state path must not target authoritative PAPER state"
        )
    write_fast_paper_runtime_state(state, destination)


def _require_shadow_paths(
    config: FastPaperShadowRuntimeConfig,
    manifest: FastPaperRuntimeManifest,
) -> None:
    shadow = {
        config.shadow_state_path,
        config.shadow_evidence_path,
        config.shadow_input_path,
    }
    if len(shadow) != 3:
        raise ValueError("shadow runtime paths must be distinct")
    authoritative = {
        Path(manifest.checkpoint_path).resolve(strict=False),
        Path(manifest.paper_evidence_path).resolve(strict=False),
        Path(manifest.observer_database_path).resolve(strict=False),
    }
    if config.shadow_state_path in authoritative:
        raise ValueError(
            "shadow state path must not target authoritative PAPER state"
        )
    if config.shadow_evidence_path in authoritative:
        raise ValueError(
            "shadow evidence path must not target authoritative PAPER state"
        )
    if config.shadow_input_path in authoritative:
        raise ValueError(
            "shadow input path must not target authoritative runtime sources"
        )


def _require_state_manifest_alignment(
    state: FastPaperRuntimeState,
    manifest: FastPaperRuntimeManifest,
) -> None:
    expected = build_fast_paper_runtime_state(
        manifest,
        cursor=state.cursor,
    )
    if expected != state:
        raise ValueError(
            "shadow runtime state does not bind the exact active manifest"
        )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--preflight"]):
        _emit_failure(FastPaperShadowRuntimeError("unsupported argument"))
        return 2
    try:
        config = load_fast_paper_shadow_runtime_config()
        bootstrap = bootstrap_fast_paper_shadow_runtime(config)
        if args == ["--preflight"]:
            print(
                _status_line(
                    bootstrap,
                    state="READY",
                    completed_cycles=0,
                    processed_decisions=0,
                )
            )
            return 0
        event = Event()
        handlers = _install_signal_handlers(event)
        try:
            run_fast_paper_shadow_runtime(config, stop_event=event)
        finally:
            _restore_signal_handlers(handlers)
        return 0
    except FastPaperShadowRuntimeError as exc:
        _emit_failure(exc)
        return 1


def _status_line(
    bootstrap: FastPaperShadowRuntimeBootstrap,
    *,
    state: str,
    completed_cycles: int,
    processed_decisions: int,
) -> str:
    document = {
        "schema_name": _STATUS_SCHEMA,
        "schema_version": _STATUS_VERSION,
        "mode": "PAPER_SHADOW",
        "state": state,
        "manifest_fingerprint_sha256": (
            bootstrap.manifest.manifest_fingerprint_sha256
        ),
        "champion_version": bootstrap.manifest.champion_version,
        "champion_fingerprint_sha256": (
            bootstrap.manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": bootstrap.manifest.action_policy.version,
        "completed_cycles": completed_cycles,
        "processed_decisions": processed_decisions,
        "cursor_sequence": (
            None
            if bootstrap.state.cursor is None
            else bootstrap.state.cursor.decision_sequence
        ),
    }
    return _canonical(document).rstrip("\n")


def _emit_failure(error: BaseException) -> None:
    document = {
        "schema_name": _STATUS_SCHEMA,
        "schema_version": _STATUS_VERSION,
        "mode": "PAPER_SHADOW",
        "state": "FAILED",
        "error_type": type(error).__name__,
    }
    print(_canonical(document).rstrip("\n"), file=sys.stderr)


def _runtime_timestamp(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperShadowRuntimeError("shadow runtime clock failed") from exc
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowRuntimeError(
            "shadow runtime clock must return non-negative milliseconds"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


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


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
