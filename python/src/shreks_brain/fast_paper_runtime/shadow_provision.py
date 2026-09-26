from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Callable

from .codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    build_initial_fast_paper_shadow_ledger_state,
    initialize_fast_paper_shadow_ledger_database,
    save_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    build_fast_paper_shadow_runtime_state,
    save_fast_paper_shadow_runtime_state,
)
from .shadow_service import (
    FastPaperShadowServiceError,
    bootstrap_fast_paper_shadow_service,
    read_fast_paper_shadow_service_policy,
)
from .shadow_service_execution_bootstrap import (
    bootstrap_fast_paper_shadow_service_execution,
)
from .shadow_supervisor import (
    FastPaperShadowSupervisorBootstrap,
    FastPaperShadowSupervisorConfig,
    FastPaperShadowSupervisorError,
    load_fast_paper_shadow_supervisor_config,
)


_STATUS_SCHEMA_NAME = "shreks.fast_paper_shadow_provision_status"
_STATUS_SCHEMA_VERSION = 1


class FastPaperShadowProvisionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperShadowProvisionConfig:
    supervisor_config: FastPaperShadowSupervisorConfig
    starting_cash_usd: float

    def __post_init__(self) -> None:
        if type(self.supervisor_config) is not FastPaperShadowSupervisorConfig:
            raise ValueError(
                "supervisor_config must be exact FastPaperShadowSupervisorConfig"
            )
        if (
            isinstance(self.starting_cash_usd, bool)
            or not isinstance(self.starting_cash_usd, (int, float))
            or not math.isfinite(float(self.starting_cash_usd))
            or float(self.starting_cash_usd) <= 0.0
        ):
            raise ValueError(
                "starting_cash_usd must be finite and strictly positive"
            )
        object.__setattr__(
            self,
            "starting_cash_usd",
            float(self.starting_cash_usd),
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowProvisionResult:
    created: bool
    supervisor_bootstrap: FastPaperShadowSupervisorBootstrap


def load_fast_paper_shadow_provision_config(
    environment: dict[str, str] | None = None,
) -> FastPaperShadowProvisionConfig:
    env = dict(os.environ if environment is None else environment)
    name = "SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD"
    value = env.get(name)
    if value is None or not value.strip():
        raise FastPaperShadowProvisionError(
            f"missing required shadow provision setting {name}"
        )
    try:
        starting_cash = float(value)
        supervisor_config = load_fast_paper_shadow_supervisor_config(env)
        return FastPaperShadowProvisionConfig(
            supervisor_config=supervisor_config,
            starting_cash_usd=starting_cash,
        )
    except (
        FastPaperShadowSupervisorError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperShadowProvisionError(
            "shadow provision configuration is invalid"
        ) from exc


def provision_fast_paper_shadow(
    config: FastPaperShadowProvisionConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
) -> FastPaperShadowProvisionResult:
    if type(config) is not FastPaperShadowProvisionConfig:
        raise FastPaperShadowProvisionError(
            "config must be exact FastPaperShadowProvisionConfig"
        )
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    now = _clock_value(clock)
    supervisor_config = config.supervisor_config
    decision_config = supervisor_config.decision_config
    execution_config = supervisor_config.execution_config

    try:
        manifest = read_fast_paper_runtime_manifest(
            decision_config.manifest_path,
        )
        verify_fast_paper_runtime_bindings(manifest)
        service_policy = read_fast_paper_shadow_service_policy(
            decision_config.policy_path,
        )
        if service_policy.route_evidence_version != manifest.route_evidence_version:
            raise ValueError(
                "shadow provision service policy route evidence version does not match manifest"
            )
        execution_policy = read_fast_paper_shadow_execution_policy(
            manifest,
            execution_config.execution_policy_path,
        )
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=execution_config.run_id,
            database_path=execution_config.ledger_database_path,
        )

        _validate_root_separation(supervisor_config)
        for directory in (
            decision_config.evidence_directory,
            execution_config.source_directory,
            supervisor_config.quote_usd_source_directory,
            supervisor_config.reduction_source_directory,
            supervisor_config.pending_buy_retry_source_directory,
        ):
            _ensure_private_leaf_directory(directory)
        _require_existing_regular_parent(
            execution_config.ledger_database_path,
        )

        database = execution_config.ledger_database_path
        if database.is_symlink():
            raise ValueError(
                "shadow provision ledger database must not be a symlink"
            )
        created = not database.exists()

        if created:
            initialize_fast_paper_shadow_ledger_database(
                manifest,
                binding,
            )
            initial = build_initial_fast_paper_shadow_ledger_state(
                manifest,
                binding,
                starting_cash_usd=config.starting_cash_usd,
                as_of_unix_ms=now,
                fill_policy=execution_policy.fill_policy,
                position_action_policy=(
                    execution_policy.position_action_policy
                ),
            )
            checkpoint = save_fast_paper_shadow_ledger_checkpoint(
                manifest,
                binding,
                initial,
                sequence=0,
                created_at_unix_ms=now,
            )
            runtime_state = build_fast_paper_shadow_runtime_state(
                manifest,
                binding,
                checkpoint,
                market_positions=(),
                execution_policy_fingerprint_sha256=(
                    execution_policy.policy_fingerprint_sha256
                ),
            )
            save_fast_paper_shadow_runtime_state(
                manifest,
                binding,
                runtime_state,
                created_at_unix_ms=now,
            )
        elif not database.is_file():
            raise ValueError(
                "shadow provision ledger database must be a regular file"
            )

        execution_bootstrap = (
            bootstrap_fast_paper_shadow_service_execution(
                manifest,
                execution_config,
            )
        )
        if (
            execution_bootstrap.checkpoint.state.ledger.starting_cash_usd
            != config.starting_cash_usd
        ):
            raise ValueError(
                "existing shadow run starting cash does not match provision configuration"
            )
        decision_bootstrap = bootstrap_fast_paper_shadow_service(
            decision_config,
        )
    except (
        FastPaperShadowServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise FastPaperShadowProvisionError(
            "shadow provision failed closed"
        ) from exc

    return FastPaperShadowProvisionResult(
        created=created,
        supervisor_bootstrap=FastPaperShadowSupervisorBootstrap(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=execution_bootstrap,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--initialize"]:
        _emit_failure(
            FastPaperShadowProvisionError(
                "explicit --initialize is required"
            )
        )
        return 2
    try:
        config = load_fast_paper_shadow_provision_config()
        result = provision_fast_paper_shadow(config)
        print(_status_line(result))
        return 0
    except FastPaperShadowProvisionError as exc:
        _emit_failure(exc)
        return 1


def _validate_root_separation(
    config: FastPaperShadowSupervisorConfig,
) -> None:
    roots = tuple(
        path.resolve(strict=False)
        for path in (
            config.decision_config.evidence_directory,
            config.execution_config.source_directory,
            config.quote_usd_source_directory,
            config.reduction_source_directory,
            config.pending_buy_retry_source_directory,
        )
    )
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _paths_overlap(left, right):
                raise ValueError(
                    "shadow provision source roots must be distinct and non-overlapping"
                )


def _ensure_private_leaf_directory(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError(
            "shadow provision directory must be an absolute Path"
        )
    if path.is_symlink():
        raise ValueError(
            "shadow provision directory must not be a symlink"
        )
    if path.exists():
        if not path.is_dir():
            raise ValueError(
                "shadow provision path must identify a regular directory"
            )
        if stat_mode(path) != 0o700:
            raise ValueError(
                "existing shadow provision directory must use mode 0700"
            )
        return

    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(
            "shadow provision directory parent must already exist as a regular non-symlink directory"
        )
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    _fsync_directory(parent)


def _require_existing_regular_parent(path: Path) -> None:
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(
            "shadow provision ledger parent must already exist as a regular non-symlink directory"
        )


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _clock_value(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise FastPaperShadowProvisionError(
            "shadow provision clock failed"
        ) from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise FastPaperShadowProvisionError(
            "shadow provision clock must return a non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _status_line(result: FastPaperShadowProvisionResult) -> str:
    bootstrap = result.supervisor_bootstrap
    decision = bootstrap.decision_bootstrap
    execution = bootstrap.execution_bootstrap
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_SHADOW_PROVISION",
        "state": "CREATED" if result.created else "VERIFIED",
        "manifest_fingerprint_sha256": (
            decision.manifest.manifest_fingerprint_sha256
        ),
        "run_id": execution.binding.run_id,
        "binding_fingerprint_sha256": (
            execution.binding.binding_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": execution.checkpoint.sequence,
        "database_path": execution.binding.database_path,
    }
    return _canonical(document).rstrip("\n")


def _emit_failure(error: BaseException) -> None:
    document = {
        "schema_name": _STATUS_SCHEMA_NAME,
        "schema_version": _STATUS_SCHEMA_VERSION,
        "mode": "PAPER_SHADOW_PROVISION",
        "state": "FAILED",
        "error_type": type(error).__name__,
    }
    print(_canonical(document).rstrip("\n"), file=sys.stderr)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
