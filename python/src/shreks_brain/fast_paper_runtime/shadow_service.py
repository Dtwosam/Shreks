from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import sys
from threading import Event
import time
from types import FrameType
from typing import Any, Callable

from shreks_brain.fast_campaign import FastCampaignDecisionPosition

from .codec import (
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
)
from .feed import fetch_fast_paper_runtime_feature_batch
from .models import FastPaperRuntimeManifest, FastPaperRuntimeState
from .persisted_quotes import (
    FastPaperShadowQuoteReadPolicy,
    resolve_fast_paper_shadow_cycle_input,
)
from .shadow_cycle import run_fast_paper_shadow_batch


FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_service_policy"
)
FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION = 1

_STATUS_SCHEMA_NAME = "shreks.fast_paper_shadow_service_status"
_STATUS_SCHEMA_VERSION = 1
_DEFAULT_INTERVAL_SECONDS = 2.0
_DEFAULT_MAXIMUM_DECISIONS = 64
_MAX_U64 = 2**64 - 1

_POLICY_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "route_evidence_version",
        "probe_policy_version",
        "taker",
        "slippage_bps",
        "entry_input_amount_raw",
        "exit_input_amount_raw",
        "max_quote_age_ms",
        "max_exposure_fraction",
    }
)


class FastPaperShadowServiceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowServicePolicy:
    schema_name: str
    schema_version: int
    route_evidence_version: str
    probe_policy_version: str
    taker: str
    slippage_bps: int
    entry_input_amount_raw: int
    exit_input_amount_raw: int
    max_quote_age_ms: int
    max_exposure_fraction: float

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME:
            raise ValueError("shadow service policy schema_name is incompatible")
        if self.schema_version != FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION:
            raise ValueError("shadow service policy schema_version is incompatible")
        for name in (
            "route_evidence_version",
            "probe_policy_version",
            "taker",
        ):
            _require_text(name, getattr(self, name))
        if (
            isinstance(self.slippage_bps, bool)
            or not isinstance(self.slippage_bps, int)
            or not 0 <= self.slippage_bps <= 10_000
        ):
            raise ValueError("slippage_bps must be an integer within [0,10000]")
        _require_u64(
            "entry_input_amount_raw",
            self.entry_input_amount_raw,
            positive=True,
        )
        _require_u64(
            "exit_input_amount_raw",
            self.exit_input_amount_raw,
            positive=True,
        )
        if (
            isinstance(self.max_quote_age_ms, bool)
            or not isinstance(self.max_quote_age_ms, int)
            or self.max_quote_age_ms < 0
        ):
            raise ValueError("max_quote_age_ms must be a non-negative integer")
        if (
            isinstance(self.max_exposure_fraction, bool)
            or not isinstance(self.max_exposure_fraction, (int, float))
            or not math.isfinite(float(self.max_exposure_fraction))
            or not 0.0 <= float(self.max_exposure_fraction) <= 1.0
        ):
            raise ValueError(
                "max_exposure_fraction must be finite within [0,1]"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowServiceConfig:
    manifest_path: Path
    policy_path: Path
    evidence_directory: Path
    cycle_interval_seconds: float
    maximum_decisions: int

    def __post_init__(self) -> None:
        for name in (
            "manifest_path",
            "policy_path",
            "evidence_directory",
        ):
            if type(getattr(self, name)) is not Path:
                raise ValueError(f"{name} must be exact Path")
        if (
            isinstance(self.cycle_interval_seconds, bool)
            or not isinstance(self.cycle_interval_seconds, (int, float))
            or not math.isfinite(float(self.cycle_interval_seconds))
            or not 0.0 < float(self.cycle_interval_seconds) <= 3600.0
        ):
            raise ValueError(
                "cycle_interval_seconds must be finite within (0,3600]"
            )
        if (
            isinstance(self.maximum_decisions, bool)
            or not isinstance(self.maximum_decisions, int)
            or not 1 <= self.maximum_decisions <= 10_000
        ):
            raise ValueError(
                "maximum_decisions must be an integer within [1,10000]"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowServiceBootstrap:
    manifest: FastPaperRuntimeManifest
    policy: FastPaperShadowServicePolicy
    state: FastPaperRuntimeState


def load_fast_paper_shadow_service_config(
    environment: dict[str, str] | None = None,
) -> FastPaperShadowServiceConfig:
    env = dict(os.environ if environment is None else environment)

    def required_path(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise FastPaperShadowServiceError(
                f"missing required shadow service setting {name}"
            )
        return Path(value).expanduser().resolve(strict=False)

    interval_text = env.get(
        "SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS",
        str(_DEFAULT_INTERVAL_SECONDS),
    )
    maximum_text = env.get(
        "SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS",
        str(_DEFAULT_MAXIMUM_DECISIONS),
    )
    try:
        interval = float(interval_text)
        maximum_decisions = int(maximum_text)
    except ValueError as exc:
        raise FastPaperShadowServiceError(
            "shadow service cadence or batch size is invalid"
        ) from exc

    try:
        return FastPaperShadowServiceConfig(
            manifest_path=required_path(
                "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"
            ),
            policy_path=required_path(
                "SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH"
            ),
            evidence_directory=required_path(
                "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY"
            ),
            cycle_interval_seconds=interval,
            maximum_decisions=maximum_decisions,
        )
    except ValueError as exc:
        raise FastPaperShadowServiceError(
            "shadow service configuration is invalid"
        ) from exc


def read_fast_paper_shadow_service_policy(
    path: str | Path,
) -> FastPaperShadowServicePolicy:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError(
            "shadow service policy source must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("shadow service policy JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("shadow service policy must be a JSON object")
    if frozenset(document) != _POLICY_KEYS:
        raise ValueError(
            "shadow service policy has unknown or missing fields"
        )
    if payload != _canonical(document):
        raise ValueError("shadow service policy must use canonical JSON")

    try:
        return FastPaperShadowServicePolicy(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            route_evidence_version=document["route_evidence_version"],
            probe_policy_version=document["probe_policy_version"],
            taker=document["taker"],
            slippage_bps=document["slippage_bps"],
            entry_input_amount_raw=document["entry_input_amount_raw"],
            exit_input_amount_raw=document["exit_input_amount_raw"],
            max_quote_age_ms=document["max_quote_age_ms"],
            max_exposure_fraction=document["max_exposure_fraction"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "shadow service policy content is incompatible"
        ) from exc


def bootstrap_fast_paper_shadow_service(
    config: FastPaperShadowServiceConfig,
) -> FastPaperShadowServiceBootstrap:
    if type(config) is not FastPaperShadowServiceConfig:
        raise FastPaperShadowServiceError(
            "config must be exact FastPaperShadowServiceConfig"
        )
    try:
        manifest = read_fast_paper_runtime_manifest(config.manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        policy = read_fast_paper_shadow_service_policy(config.policy_path)
        if policy.route_evidence_version != manifest.route_evidence_version:
            raise ValueError(
                "shadow service policy route evidence version does not match manifest"
            )
        _validate_service_paths(config, manifest)
        _verify_observer_candidate_table(manifest.observer_database_path)
        state = _load_service_state(manifest)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise FastPaperShadowServiceError(
            "shadow service bootstrap failed closed"
        ) from exc

    return FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=policy,
        state=state,
    )


def run_fast_paper_shadow_service_cycle(
    bootstrap: FastPaperShadowServiceBootstrap,
    config: FastPaperShadowServiceConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
) -> tuple[FastPaperShadowServiceBootstrap, int]:
    if type(bootstrap) is not FastPaperShadowServiceBootstrap:
        raise FastPaperShadowServiceError(
            "bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if type(config) is not FastPaperShadowServiceConfig:
        raise FastPaperShadowServiceError(
            "config must be exact FastPaperShadowServiceConfig"
        )

    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    current = bootstrap.state
    processed = 0

    try:
        _validate_service_paths(config, bootstrap.manifest)
        batch = fetch_fast_paper_runtime_feature_batch(
            bootstrap.manifest,
            current,
            maximum_decisions=config.maximum_decisions,
        )
        for record in batch.records:
            evaluated_at_unix_ms = _runtime_timestamp(
                clock,
                minimum=record.decision_observed_at_unix_ms,
            )
            candidate_id = _resolve_candidate_id(
                bootstrap.manifest.observer_database_path,
                mint=record.mint,
            )
            read_policy = FastPaperShadowQuoteReadPolicy(
                version=bootstrap.policy.route_evidence_version,
                candidate_id=candidate_id,
                probe_policy_version=bootstrap.policy.probe_policy_version,
                taker=bootstrap.policy.taker,
                slippage_bps=bootstrap.policy.slippage_bps,
                entry_input_amount_raw=(
                    bootstrap.policy.entry_input_amount_raw
                ),
                exit_input_amount_raw=(
                    bootstrap.policy.exit_input_amount_raw
                ),
                max_quote_age_ms=bootstrap.policy.max_quote_age_ms,
                reduction_reads=(),
            )
            cycle_input = resolve_fast_paper_shadow_cycle_input(
                bootstrap.manifest,
                record,
                FastCampaignDecisionPosition(kind="FLAT"),
                read_policy,
                evaluated_at_unix_ms=evaluated_at_unix_ms,
                max_exposure_fraction=(
                    bootstrap.policy.max_exposure_fraction
                ),
                force_sell=False,
            )
            current = run_fast_paper_shadow_batch(
                bootstrap.manifest,
                current,
                (cycle_input,),
                evidence_directory=config.evidence_directory,
            )
            processed += 1
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise FastPaperShadowServiceError(
            "shadow service cycle failed closed"
        ) from exc

    if current != batch.next_state:
        raise FastPaperShadowServiceError(
            "shadow service committed state does not match feature batch"
        )

    return (
        FastPaperShadowServiceBootstrap(
            manifest=bootstrap.manifest,
            policy=bootstrap.policy,
            state=current,
        ),
        processed,
    )


def run_fast_paper_shadow_service(
    config: FastPaperShadowServiceConfig,
    *,
    stop_event: Event | None = None,
    clock_unix_ms: Callable[[], int] | None = None,
    status_sink: Callable[[str], object] | None = None,
) -> int:
    bootstrap = bootstrap_fast_paper_shadow_service(config)
    event = Event() if stop_event is None else stop_event
    sink = print if status_sink is None else status_sink
    completed_cycles = 0
    processed_decisions = 0

    while not event.is_set():
        bootstrap, processed = run_fast_paper_shadow_service_cycle(
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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--preflight"]):
        _emit_failure(FastPaperShadowServiceError("unsupported argument"))
        return 2

    try:
        config = load_fast_paper_shadow_service_config()
        bootstrap = bootstrap_fast_paper_shadow_service(config)
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
        previous = _install_signal_handlers(event)
        try:
            run_fast_paper_shadow_service(
                config,
                stop_event=event,
            )
        finally:
            _restore_signal_handlers(previous)
        return 0
    except FastPaperShadowServiceError as exc:
        _emit_failure(exc)
        return 1


def _load_service_state(
    manifest: FastPaperRuntimeManifest,
) -> FastPaperRuntimeState:
    checkpoint = Path(manifest.checkpoint_path).expanduser()
    if checkpoint.is_symlink():
        raise ValueError("shadow service checkpoint must not be a symlink")
    if not checkpoint.exists():
        return build_fast_paper_runtime_state(manifest, cursor=None)
    if not checkpoint.is_file():
        raise ValueError("shadow service checkpoint must be a regular file")
    state = read_fast_paper_runtime_state(checkpoint)
    expected = build_fast_paper_runtime_state(
        manifest,
        cursor=state.cursor,
    )
    if state != expected:
        raise ValueError(
            "shadow service checkpoint does not authenticate against manifest"
        )
    return state


def _validate_service_paths(
    config: FastPaperShadowServiceConfig,
    manifest: FastPaperRuntimeManifest,
) -> None:
    root = config.evidence_directory
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow evidence directory must be an existing regular directory"
        )
    root = root.resolve(strict=True)

    checkpoint = Path(manifest.checkpoint_path).expanduser().resolve(
        strict=False
    )
    if not _is_within(checkpoint, root):
        raise ValueError(
            "shadow checkpoint must stay inside the dedicated shadow directory"
        )

    observer = Path(manifest.observer_database_path).expanduser().resolve(
        strict=False
    )
    if _is_within(observer, root):
        raise ValueError(
            "observer database must stay outside the writable shadow directory"
        )

    authoritative = Path(manifest.paper_evidence_path).expanduser().resolve(
        strict=False
    )
    if _paths_overlap(root, authoritative):
        raise ValueError(
            "shadow evidence directory must be separate from authoritative paper evidence"
        )


def _verify_observer_candidate_table(path_value: str) -> None:
    connection = _open_observer_database(path_value)
    try:
        rows = connection.execute(
            "PRAGMA table_info(token_candidates)"
        ).fetchall()
        columns = {str(row["name"]) for row in rows}
        if not {"id", "mint"}.issubset(columns):
            raise ValueError(
                "observer database token_candidates schema is incompatible"
            )
    finally:
        connection.close()


def _resolve_candidate_id(
    path_value: str,
    *,
    mint: str,
) -> int:
    _require_text("mint", mint)
    connection = _open_observer_database(path_value)
    try:
        rows = connection.execute(
            "SELECT id FROM token_candidates WHERE mint = ? ORDER BY id ASC",
            (mint,),
        ).fetchall()
    finally:
        connection.close()

    if len(rows) != 1:
        raise ValueError(
            "shadow feature mint candidate attribution is missing or ambiguous"
        )
    value = rows[0]["id"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("shadow feature candidate id is invalid")
    return value


def _open_observer_database(path_value: str) -> sqlite3.Connection:
    path = Path(path_value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "observer database must be an existing regular non-symlink file"
        )
    try:
        source = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("observer database could not be resolved") from exc

    try:
        connection = sqlite3.connect(
            f"file:{source}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        row = connection.execute("PRAGMA query_only").fetchone()
        if row is None or row[0] != 1:
            connection.close()
            raise ValueError(
                "observer database connection is not query-only"
            )
        return connection
    except ValueError:
        raise
    except sqlite3.Error as exc:
        raise ValueError(
            "observer database could not be opened read-only"
        ) from exc


def _runtime_timestamp(
    clock: Callable[[], int],
    *,
    minimum: int,
) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperShadowServiceError(
            "shadow service clock failed"
        ) from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise FastPaperShadowServiceError(
            "shadow service clock must not precede the decision"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _status_line(
    bootstrap: FastPaperShadowServiceBootstrap,
    *,
    state: str,
    completed_cycles: int,
    processed_decisions: int,
) -> str:
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
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
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_SHADOW",
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
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_u64(
    name: str,
    value: object,
    *,
    positive: bool,
) -> None:
    minimum = 1 if positive else 0
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= _MAX_U64
    ):
        raise ValueError(
            f"{name} must be an integer within [{minimum},{_MAX_U64}]"
        )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


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
