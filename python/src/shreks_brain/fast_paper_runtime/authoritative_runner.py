from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shreks_brain.fast_paper import (
    FastPaperBuyResult,
    FastPaperPositionActionResult,
)
from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .authoritative_commit import (
    FastPaperAuthoritativeTransition,
    commit_fast_paper_authoritative_transition_atomically,
)
from .authoritative_handoff import (
    FastPaperAuthoritativeBinding,
    load_fast_paper_authoritative_binding,
    load_latest_fast_paper_authoritative_checkpoint,
)
from .authoritative_runtime_state import (
    FastPaperAuthoritativeMarketPosition,
    FastPaperAuthoritativeRuntimeState,
    load_latest_fast_paper_authoritative_runtime_state,
)
from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowDecisionEvidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
    build_fast_paper_shadow_execution_policy,
    materialize_fast_paper_shadow_execution_evidence,
)
from .shadow_executor import (
    FastPaperShadowPendingBuyRetryInput,
    reconstruct_fast_paper_shadow_decision,
    reconstruct_fast_paper_shadow_pending_buy_retry,
)
from .shadow_ledger import build_fast_paper_shadow_ledger_binding
from .shadow_runtime_state import (
    FastPaperShadowMarketPosition,
    FastPaperShadowPendingBuy,
    _build_fast_paper_shadow_runtime_state_for_checkpoint,
)


FAST_PAPER_AUTHORITATIVE_RUNNER_VERSION = (
    "fast-paper-authoritative-runner-v1"
)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeRunnerResult:
    version: str
    replayed: bool
    committed: bool
    source_event_id: str
    buy_result: FastPaperBuyResult | None
    position_result: FastPaperPositionActionResult | None
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperAuthoritativeRuntimeState

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_AUTHORITATIVE_RUNNER_VERSION:
            raise ValueError(
                "unsupported authoritative Fast PAPER runner version"
            )
        if type(self.replayed) is not bool:
            raise ValueError("replayed must be bool")
        if type(self.committed) is not bool:
            raise ValueError("committed must be bool")
        if self.replayed == self.committed:
            raise ValueError(
                "authoritative runner result must be either replayed or committed"
            )
        _require_text("source_event_id", self.source_event_id)
        if (
            self.buy_result is not None
            and type(self.buy_result) is not FastPaperBuyResult
        ):
            raise ValueError(
                "buy_result must be exact FastPaperBuyResult or None"
            )
        if (
            self.position_result is not None
            and type(self.position_result)
            is not FastPaperPositionActionResult
        ):
            raise ValueError(
                "position_result must be exact FastPaperPositionActionResult or None"
            )
        if (
            self.buy_result is not None
            and self.position_result is not None
        ):
            raise ValueError(
                "authoritative runner result cannot carry BUY and position results together"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if (
            type(self.runtime_state)
            is not FastPaperAuthoritativeRuntimeState
        ):
            raise ValueError(
                "runtime_state must be exact FastPaperAuthoritativeRuntimeState"
            )
        if (
            self.runtime_state.paper_checkpoint_sequence
            != self.checkpoint.sequence
            or self.runtime_state.paper_checkpoint_payload_sha256
            != self.checkpoint.payload_sha256
        ):
            raise ValueError(
                "authoritative runner result checkpoint/runtime pair is torn"
            )


def run_fast_paper_authoritative_execution(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    source: FastPaperShadowExecutionInput,
    *,
    committed_at_unix_ms: int,
) -> FastPaperAuthoritativeRunnerResult:
    checkpoint, runtime_state = _load_exact_latest_pair(
        manifest,
        binding,
    )
    _require_execution_policy(
        manifest,
        binding,
        execution_policy,
        checkpoint,
    )
    _require_non_negative_int(
        "committed_at_unix_ms",
        committed_at_unix_ms,
    )
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )
    if checkpoint.state.pending_buy is not None:
        raise ValueError(
            "authoritative runner pending BUY must resolve before another learned decision is consumed"
        )

    # Reuse the sealed input materializer before reconstruction so even an
    # exact replay remains authenticated against this manifest and policy.
    materialize_fast_paper_shadow_execution_evidence(
        manifest,
        execution_policy,
        source,
    )

    adapter_binding = _build_adapter_binding(manifest, binding)
    adapter_state = _build_adapter_state(
        adapter_binding,
        checkpoint,
        runtime_state,
        pending_buy=None,
    )
    transition = reconstruct_fast_paper_shadow_decision(
        manifest,
        execution_policy,
        adapter_binding,
        checkpoint,
        adapter_state,
        source,
    )

    if transition.replayed:
        if (
            transition.next_paper_state != checkpoint.state
            or _authoritative_positions(
                transition.next_market_positions
            )
            != runtime_state.market_positions
        ):
            raise ValueError(
                "authoritative replay changed durable PAPER state"
            )
        return FastPaperAuthoritativeRunnerResult(
            version=FAST_PAPER_AUTHORITATIVE_RUNNER_VERSION,
            replayed=True,
            committed=False,
            source_event_id=transition.source_event_id,
            buy_result=transition.buy_result,
            position_result=transition.position_result,
            checkpoint=checkpoint,
            runtime_state=runtime_state,
        )

    commit = commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        _authoritative_transition(transition),
        sequence=checkpoint.sequence + 1,
        created_at_unix_ms=committed_at_unix_ms,
    )
    return FastPaperAuthoritativeRunnerResult(
        version=FAST_PAPER_AUTHORITATIVE_RUNNER_VERSION,
        replayed=False,
        committed=True,
        source_event_id=transition.source_event_id,
        buy_result=transition.buy_result,
        position_result=transition.position_result,
        checkpoint=commit.checkpoint,
        runtime_state=commit.runtime_state,
    )


def run_fast_paper_authoritative_pending_buy_retry(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    retry: FastPaperShadowPendingBuyRetryInput,
    pending_decision_evidence: FastPaperShadowDecisionEvidence,
    *,
    committed_at_unix_ms: int,
) -> FastPaperAuthoritativeRunnerResult:
    checkpoint, runtime_state = _load_exact_latest_pair(
        manifest,
        binding,
    )
    _require_execution_policy(
        manifest,
        binding,
        execution_policy,
        checkpoint,
    )
    _require_non_negative_int(
        "committed_at_unix_ms",
        committed_at_unix_ms,
    )
    if type(retry) is not FastPaperShadowPendingBuyRetryInput:
        raise ValueError(
            "retry must be exact FastPaperShadowPendingBuyRetryInput"
        )

    approval = checkpoint.state.pending_buy
    if approval is None:
        raise ValueError(
            "authoritative pending BUY retry requires durable pending approval"
        )
    pending = _pending_buy_from_evidence(
        manifest,
        runtime_state,
        approval,
        pending_decision_evidence,
    )

    adapter_binding = _build_adapter_binding(manifest, binding)
    adapter_state = _build_adapter_state(
        adapter_binding,
        checkpoint,
        runtime_state,
        pending_buy=pending,
    )
    transition = reconstruct_fast_paper_shadow_pending_buy_retry(
        manifest,
        execution_policy,
        adapter_binding,
        checkpoint,
        adapter_state,
        retry,
    )
    if transition.replayed:
        raise ValueError(
            "pending BUY retry cannot be reported as an event replay"
        )

    commit = commit_fast_paper_authoritative_transition_atomically(
        manifest,
        binding,
        checkpoint,
        runtime_state,
        _authoritative_transition(transition),
        sequence=checkpoint.sequence + 1,
        created_at_unix_ms=committed_at_unix_ms,
    )
    return FastPaperAuthoritativeRunnerResult(
        version=FAST_PAPER_AUTHORITATIVE_RUNNER_VERSION,
        replayed=False,
        committed=True,
        source_event_id=transition.source_event_id,
        buy_result=transition.buy_result,
        position_result=transition.position_result,
        checkpoint=commit.checkpoint,
        runtime_state=commit.runtime_state,
    )


def _load_exact_latest_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
) -> tuple[
    FastPaperCheckpointRecord,
    FastPaperAuthoritativeRuntimeState,
]:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperAuthoritativeBinding:
        raise ValueError(
            "binding must be exact FastPaperAuthoritativeBinding"
        )
    persisted_binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=binding.fast_run_id,
        database_path=binding.database_path,
    )
    if persisted_binding != binding:
        raise ValueError(
            "authoritative runner binding changed"
        )
    checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        binding,
    )
    runtime_state = load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
    )
    if checkpoint is None or runtime_state is None:
        raise ValueError(
            "authoritative runner requires initialized checkpoint/runtime state"
        )
    if (
        runtime_state.paper_checkpoint_sequence != checkpoint.sequence
        or runtime_state.paper_checkpoint_payload_sha256
        != checkpoint.payload_sha256
    ):
        raise ValueError(
            "authoritative runner latest checkpoint/runtime pair is torn"
        )
    return checkpoint, runtime_state


def _require_execution_policy(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    checkpoint: FastPaperCheckpointRecord,
) -> None:
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    expected = build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=execution_policy.risk_policy,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=(
            execution_policy.position_action_policy
        ),
    )
    if execution_policy != expected:
        raise ValueError(
            "authoritative runner execution policy does not authenticate against runtime manifest"
        )
    if (
        execution_policy.policy_fingerprint_sha256
        != binding.execution_policy_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative runner execution policy fingerprint conflicts with binding"
        )
    if checkpoint.state.fill_policy != execution_policy.fill_policy:
        raise ValueError(
            "authoritative runner fill policy conflicts with checkpoint"
        )
    if (
        checkpoint.state.position_action_policy
        != execution_policy.position_action_policy
    ):
        raise ValueError(
            "authoritative runner position-action policy conflicts with checkpoint"
        )


def _build_adapter_binding(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
):
    database = Path(binding.database_path)
    adapter_database = database.parent / (
        ".fast-paper-authoritative-runner-adapter-"
        f"{binding.binding_fingerprint_sha256}.sqlite3"
    )
    return build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id=binding.fast_run_id,
        database_path=adapter_database,
    )


def _build_adapter_state(
    adapter_binding,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
    *,
    pending_buy: FastPaperShadowPendingBuy | None,
):
    return _build_fast_paper_shadow_runtime_state_for_checkpoint(
        adapter_binding,
        checkpoint,
        market_positions=tuple(
            FastPaperShadowMarketPosition(
                market_key=value.market_key,
                position_id=value.position_id,
                mint=value.mint,
                current_exposure_fraction=(
                    value.current_exposure_fraction
                ),
                current_base_quantity_raw=(
                    value.current_base_quantity_raw
                ),
            )
            for value in runtime_state.market_positions
        ),
        execution_policy_fingerprint_sha256=(
            runtime_state.execution_policy_fingerprint_sha256
        ),
        pending_buy=pending_buy,
        last_processed_source_sequence=(
            runtime_state.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            runtime_state.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            runtime_state.last_processed_decision_evidence_fingerprint_sha256
        ),
    )


def _pending_buy_from_evidence(
    manifest: FastPaperRuntimeManifest,
    runtime_state: FastPaperAuthoritativeRuntimeState,
    approval,
    evidence: FastPaperShadowDecisionEvidence,
) -> FastPaperShadowPendingBuy:
    if type(evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "pending_decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    validate_fast_paper_shadow_decision_evidence(evidence)
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "pending BUY decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "pending BUY decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "pending BUY decision champion fingerprint mismatch"
        )
    expected_identity = (
        runtime_state.last_processed_source_sequence,
        runtime_state.last_processed_source_event_id,
        runtime_state.last_processed_decision_evidence_fingerprint_sha256,
    )
    actual_identity = (
        evidence.source_sequence,
        evidence.source_event_id,
        evidence.evidence_fingerprint_sha256,
    )
    if expected_identity != actual_identity:
        raise ValueError(
            "pending BUY decision evidence does not match durable learned identity"
        )
    if evidence.decision.action != "BUY":
        raise ValueError(
            "pending BUY retry requires original BUY decision evidence"
        )
    assessment = approval.assessment
    if (
        evidence.source_sequence != assessment.source_sequence
        or evidence.source_event_id != assessment.source_event_id
        or evidence.market_key != assessment.market_key
        or evidence.entry_quote.mint != approval.mint
        or evidence.entry_quote.quote_mint != approval.quote_mint
    ):
        raise ValueError(
            "pending BUY decision evidence conflicts with durable approval"
        )
    return FastPaperShadowPendingBuy(
        market_key=assessment.market_key,
        mint=approval.mint,
        source_event_id=assessment.source_event_id,
        target_exposure_fraction=(
            evidence.decision.target_exposure_fraction
        ),
    )


def _authoritative_transition(
    transition,
) -> FastPaperAuthoritativeTransition:
    return FastPaperAuthoritativeTransition(
        next_paper_state=transition.next_paper_state,
        next_market_positions=_authoritative_positions(
            transition.next_market_positions
        ),
        execution_policy_fingerprint_sha256=(
            transition.execution_policy_fingerprint_sha256
        ),
        last_processed_source_sequence=(
            transition.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            transition.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            transition.last_processed_decision_evidence_fingerprint_sha256
        ),
    )


def _authoritative_positions(
    values,
) -> tuple[FastPaperAuthoritativeMarketPosition, ...]:
    return tuple(
        FastPaperAuthoritativeMarketPosition(
            market_key=value.market_key,
            position_id=value.position_id,
            mint=value.mint,
            current_exposure_fraction=(
                value.current_exposure_fraction
            ),
            current_base_quantity_raw=(
                value.current_base_quantity_raw
            ),
        )
        for value in values
    )


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
