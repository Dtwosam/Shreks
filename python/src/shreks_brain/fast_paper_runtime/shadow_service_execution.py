from __future__ import annotations

from pathlib import Path

from .models import FastPaperRuntimeManifest
from .shadow_commit import (
    FastPaperShadowCommitResult,
    commit_fast_paper_shadow_transition_atomically,
)
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
)
from .shadow_execution_producer import (
    produce_fast_paper_shadow_execution_input_source_record,
)
from .shadow_execution_source import (
    read_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_execution_input_source_record,
)
from .shadow_executor import execute_fast_paper_shadow_decision
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    load_latest_fast_paper_shadow_runtime_state,
)


def run_fast_paper_shadow_service_execution(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    source: FastPaperShadowExecutionInput,
    *,
    source_directory: str | Path,
    source_observed_at_unix_ms: int,
    risk_day_started_at_unix_ms: int | None,
    committed_at_unix_ms: int,
) -> FastPaperShadowCommitResult:
    checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if checkpoint is None:
        raise ValueError(
            "shadow service execution requires a durable checkpoint"
        )
    runtime_state = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if runtime_state is None:
        raise ValueError(
            "shadow service execution requires durable runtime state"
        )

    record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        execution_policy,
        checkpoint,
        runtime_state,
        source,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
        risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )
    try:
        write_fast_paper_shadow_execution_input_source_record(
            record,
            source_directory,
        )
    except FileExistsError:
        pass

    restored = read_fast_paper_shadow_execution_input_source_record(
        manifest,
        execution_policy,
        source.decision_evidence,
        source_directory,
        paper_checkpoint_sequence=checkpoint.sequence,
        paper_checkpoint_payload_sha256=checkpoint.payload_sha256,
        shadow_runtime_state_fingerprint_sha256=(
            runtime_state.state_fingerprint_sha256
        ),
    )
    if restored != record:
        raise ValueError(
            "shadow service execution source read-back mismatch"
        )

    transition = execute_fast_paper_shadow_decision(
        manifest,
        execution_policy,
        binding,
        checkpoint,
        runtime_state,
        restored.execution_input,
    )
    if transition.replayed:
        raise ValueError(
            "shadow service execution refuses replayed transition"
        )

    return commit_fast_paper_shadow_transition_atomically(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        transition,
        sequence=checkpoint.sequence + 1,
        created_at_unix_ms=committed_at_unix_ms,
    )
