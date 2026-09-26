from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .models import FastPaperRuntimeManifest
from .shadow_execution_input import (
    FastPaperShadowExecutionPolicy,
    read_fast_paper_shadow_execution_policy,
)
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    build_fast_paper_shadow_ledger_binding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FastPaperShadowRuntimeState,
    load_latest_fast_paper_shadow_runtime_state,
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowServiceExecutionConfig:
    execution_policy_path: Path
    source_directory: Path
    ledger_database_path: Path
    run_id: str

    def __post_init__(self) -> None:
        for name in (
            "execution_policy_path",
            "source_directory",
            "ledger_database_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be Path")
            if not value.is_absolute():
                raise ValueError(f"{name} must be absolute")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class FastPaperShadowServiceExecutionBootstrap:
    binding: FastPaperShadowLedgerBinding
    execution_policy: FastPaperShadowExecutionPolicy
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperShadowRuntimeState
    source_directory: Path

    def __post_init__(self) -> None:
        if type(self.binding) is not FastPaperShadowLedgerBinding:
            raise ValueError(
                "binding must be exact FastPaperShadowLedgerBinding"
            )
        if type(self.execution_policy) is not FastPaperShadowExecutionPolicy:
            raise ValueError(
                "execution_policy must be exact FastPaperShadowExecutionPolicy"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if type(self.runtime_state) is not FastPaperShadowRuntimeState:
            raise ValueError(
                "runtime_state must be exact FastPaperShadowRuntimeState"
            )
        if not isinstance(self.source_directory, Path):
            raise ValueError("source_directory must be Path")
        if (
            self.runtime_state.paper_checkpoint_sequence
            != self.checkpoint.sequence
            or self.runtime_state.paper_checkpoint_payload_sha256
            != self.checkpoint.payload_sha256
        ):
            raise ValueError(
                "execution bootstrap durable checkpoint/runtime pair is torn"
            )
        if (
            self.runtime_state.execution_policy_fingerprint_sha256
            != self.execution_policy.policy_fingerprint_sha256
        ):
            raise ValueError(
                "execution bootstrap runtime execution policy fingerprint mismatch"
            )


def load_fast_paper_shadow_service_execution_config(
    environment: dict[str, str] | None = None,
) -> FastPaperShadowServiceExecutionConfig:
    env = dict(os.environ if environment is None else environment)

    def required_path(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise ValueError(f"missing required execution setting {name}")
        return Path(value).expanduser().resolve(strict=False)

    run_id_name = "SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID"
    run_id = env.get(run_id_name)
    if run_id is None or not run_id.strip():
        raise ValueError(f"missing required execution setting {run_id_name}")

    return FastPaperShadowServiceExecutionConfig(
        execution_policy_path=required_path(
            "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH"
        ),
        source_directory=required_path(
            "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY"
        ),
        ledger_database_path=required_path(
            "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH"
        ),
        run_id=run_id,
    )


def bootstrap_fast_paper_shadow_service_execution(
    manifest: FastPaperRuntimeManifest,
    config: FastPaperShadowServiceExecutionConfig,
) -> FastPaperShadowServiceExecutionBootstrap:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(config) is not FastPaperShadowServiceExecutionConfig:
        raise ValueError(
            "config must be exact FastPaperShadowServiceExecutionConfig"
        )

    source_directory = config.source_directory
    if source_directory.is_symlink() or not source_directory.is_dir():
        raise ValueError(
            "execution source directory must be an existing regular non-symlink directory"
        )
    source_directory = source_directory.resolve(strict=True)

    policy_path = config.execution_policy_path
    if policy_path.is_symlink() or not policy_path.is_file():
        raise ValueError(
            "execution policy source must be an existing regular non-symlink file"
        )
    policy_path = policy_path.resolve(strict=True)
    if _is_within(policy_path, source_directory):
        raise ValueError(
            "execution policy source must stay outside the execution source directory"
        )

    database = config.ledger_database_path
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "shadow ledger database must be an existing regular non-symlink file"
        )
    database = database.resolve(strict=True)

    execution_policy = read_fast_paper_shadow_execution_policy(
        manifest,
        policy_path,
    )
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id=config.run_id,
        database_path=database,
    )
    checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if checkpoint is None:
        raise ValueError(
            "execution bootstrap requires an existing shadow checkpoint"
        )
    runtime_state = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if runtime_state is None:
        raise ValueError(
            "execution bootstrap requires existing shadow runtime state"
        )
    if (
        runtime_state.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "execution bootstrap execution policy fingerprint mismatch"
        )

    return FastPaperShadowServiceExecutionBootstrap(
        binding=binding,
        execution_policy=execution_policy,
        checkpoint=checkpoint,
        runtime_state=runtime_state,
        source_directory=source_directory,
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
