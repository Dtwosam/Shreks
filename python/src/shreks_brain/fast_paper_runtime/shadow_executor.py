from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.fast_campaign import (
    fast_campaign_result_to_paper_assessment,
)
from shreks_brain.fast_campaign_paper import FastCampaignPaperQuoteEvidence
from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperAction,
    FastPaperBuyApproval,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    FastPaperBuyResult,
    FastPaperEventOutcome,
    FastPaperMaterialUpdate,
    FastPaperPositionActionApproval,
    FastPaperPositionActionResult,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_position_action_state,
    execute_fast_paper_buy,
    run_fast_paper_event,
)
from shreks_brain.paper import (
    PaperLedger,
    PaperPosition,
    PaperPositionState,
    PaperQuoteState,
)
from shreks_brain.paper_validation import (
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperCheckpointRecord,
    FastPaperRuntimeState,
)
from shreks_brain.risk import RiskContext

from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowQuoteEvidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
    FastPaperShadowQuoteUsdEvidence,
    build_fast_paper_shadow_execution_policy,
    materialize_fast_paper_shadow_execution_evidence,
)
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    build_fast_paper_shadow_ledger_binding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FastPaperShadowMarketPosition,
    FastPaperShadowPendingBuy,
    FastPaperShadowRuntimeState,
    build_fast_paper_shadow_runtime_state,
    fast_paper_shadow_decision_position,
    load_latest_fast_paper_shadow_runtime_state,
)


FAST_PAPER_SHADOW_EXECUTOR_VERSION = "fl10-fast-paper-shadow-executor-v1"

_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class FastPaperShadowPendingBuyRetryInput:
    evaluated_at_unix_ms: int
    quote: FastPaperShadowQuoteEvidence
    risk_context: RiskContext
    quote_usd_evidence: FastPaperShadowQuoteUsdEvidence

    def __post_init__(self) -> None:
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if type(self.quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "quote must be exact FastPaperShadowQuoteEvidence"
            )
        if type(self.risk_context) is not RiskContext:
            raise ValueError(
                "risk_context must be exact RiskContext"
            )
        if (
            type(self.quote_usd_evidence)
            is not FastPaperShadowQuoteUsdEvidence
        ):
            raise ValueError(
                "quote_usd_evidence must be exact FastPaperShadowQuoteUsdEvidence"
            )
        if self.risk_context.as_of_unix_ms != self.evaluated_at_unix_ms:
            raise ValueError(
                "pending BUY retry risk timestamp must equal evaluation time"
            )
        if self.quote.observed_at_unix_ms > self.evaluated_at_unix_ms:
            raise ValueError(
                "pending BUY retry cannot consume a future quote"
            )
        if (
            self.quote_usd_evidence.observed_at_unix_ms
            > self.evaluated_at_unix_ms
        ):
            raise ValueError(
                "pending BUY retry cannot consume future USD evidence"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowExecutionTransition:
    version: str
    replayed: bool
    source_event_id: str
    buy_result: FastPaperBuyResult | None
    position_result: FastPaperPositionActionResult | None
    next_paper_state: FastPaperRuntimeState
    next_market_positions: tuple[FastPaperShadowMarketPosition, ...]
    next_pending_buy: FastPaperShadowPendingBuy | None
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    last_processed_decision_evidence_fingerprint_sha256: str | None

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_SHADOW_EXECUTOR_VERSION:
            raise ValueError(
                "unsupported Fast PAPER shadow executor version"
            )
        if type(self.replayed) is not bool:
            raise ValueError("replayed must be bool")
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
                "shadow execution transition cannot carry BUY and position results together"
            )
        if type(self.next_paper_state) is not FastPaperRuntimeState:
            raise ValueError(
                "next_paper_state must be exact FastPaperRuntimeState"
            )
        if (
            not isinstance(self.next_market_positions, tuple)
            or not all(
                type(value) is FastPaperShadowMarketPosition
                for value in self.next_market_positions
            )
        ):
            raise ValueError(
                "next_market_positions must contain exact FastPaperShadowMarketPosition values"
            )
        if (
            self.next_pending_buy is not None
            and type(self.next_pending_buy) is not FastPaperShadowPendingBuy
        ):
            raise ValueError(
                "next_pending_buy must be exact FastPaperShadowPendingBuy or None"
            )
        identity = (
            self.last_processed_source_sequence,
            self.last_processed_source_event_id,
            self.last_processed_decision_evidence_fingerprint_sha256,
        )
        if any(value is None for value in identity):
            if any(value is not None for value in identity):
                raise ValueError(
                    "transition last processed identity must be all present or all absent"
                )
        else:
            _require_positive_int(
                "last_processed_source_sequence",
                self.last_processed_source_sequence,
            )
            _require_text(
                "last_processed_source_event_id",
                self.last_processed_source_event_id,
            )
            _require_sha256(
                "last_processed_decision_evidence_fingerprint_sha256",
                self.last_processed_decision_evidence_fingerprint_sha256,
            )


def execute_fast_paper_shadow_decision(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    shadow_state: FastPaperShadowRuntimeState,
    source: FastPaperShadowExecutionInput,
) -> FastPaperShadowExecutionTransition:
    _require_authority_bindings(
        manifest,
        execution_policy,
        binding,
        paper_checkpoint,
        shadow_state,
    )
    if paper_checkpoint.state.pending_buy is not None:
        raise ValueError(
            "pending BUY must resolve through retry before another learned decision is consumed"
        )
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )

    evidence = source.decision_evidence
    validate_fast_paper_shadow_decision_evidence(evidence)
    assessment = fast_campaign_result_to_paper_assessment(
        evidence.decision,
        assessment_version=manifest.assessment_version,
        strategy_family=manifest.strategy_family,
        strategy_version=manifest.strategy_version,
    )
    event = run_fast_paper_event(
        paper_checkpoint.state.event_loop_state,
        FastPaperMaterialUpdate(
            source_event_id=evidence.source_event_id,
            market_key=evidence.market_key,
            source_sequence=evidence.source_sequence,
            as_of_unix_ms=evidence.as_of_unix_ms,
            state_version=manifest.state_version,
            is_material=True,
            material_reason="learned_shadow_execution",
        ),
        lambda _update: assessment,
    )

    if event.outcome is FastPaperEventOutcome.REPLAYED:
        _require_exact_processed_replay(shadow_state, source)
        return _transition(
            replayed=True,
            source_event_id=evidence.source_event_id,
            buy_result=None,
            position_result=None,
            paper_state=paper_checkpoint.state,
            market_positions=shadow_state.market_positions,
            pending_buy=shadow_state.pending_buy,
            last_sequence=shadow_state.last_processed_source_sequence,
            last_event_id=shadow_state.last_processed_source_event_id,
            last_fingerprint=(
                shadow_state.last_processed_decision_evidence_fingerprint_sha256
            ),
        )

    if event.outcome is not FastPaperEventOutcome.ASSESSED:
        raise ValueError(
            "learned shadow execution requires a material assessed Fast PAPER event"
        )
    _require_new_decision_order(shadow_state, evidence.source_sequence)
    _require_learned_posture(shadow_state, source)
    if evidence.decision.action == "BUY":
        _require_new_buy_mint_available(
            paper_checkpoint.state.ledger,
            shadow_state,
            evidence.entry_quote.mint,
        )

    point = materialize_fast_paper_shadow_execution_evidence(
        manifest,
        execution_policy,
        source,
    )
    action = assessment.action
    base_state = paper_checkpoint.state

    if action is FastPaperAction.SKIP:
        next_state = _paper_state(
            base_state,
            event_loop_state=event.next_state,
            ledger=base_state.ledger,
            as_of_unix_ms=max(
                base_state.as_of_unix_ms,
                evidence.evaluated_at_unix_ms,
            ),
            pending_buy=None,
            position_action_states=base_state.position_action_states,
        )
        return _fresh_transition(
            source,
            next_state,
            shadow_state.market_positions,
            pending_buy=None,
        )

    if action is FastPaperAction.BUY:
        return _execute_fresh_buy(
            manifest,
            execution_policy,
            source,
            point,
            event.next_state,
            base_state,
            shadow_state,
            assessment,
        )

    return _execute_position_action(
        execution_policy,
        source,
        point,
        event.next_state,
        base_state,
        shadow_state,
        assessment,
    )


def retry_fast_paper_shadow_pending_buy(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    shadow_state: FastPaperShadowRuntimeState,
    retry: FastPaperShadowPendingBuyRetryInput,
) -> FastPaperShadowExecutionTransition:
    _require_authority_bindings(
        manifest,
        execution_policy,
        binding,
        paper_checkpoint,
        shadow_state,
    )
    if type(retry) is not FastPaperShadowPendingBuyRetryInput:
        raise ValueError(
            "retry must be exact FastPaperShadowPendingBuyRetryInput"
        )
    approval = paper_checkpoint.state.pending_buy
    pending = shadow_state.pending_buy
    if approval is None or pending is None:
        raise ValueError(
            "pending BUY retry requires persisted checkpoint and learned target authority"
        )
    if retry.evaluated_at_unix_ms < paper_checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "pending BUY retry evaluation cannot precede checkpoint time"
        )
    _validate_pending_retry_quote(
        manifest,
        approval,
        retry,
    )

    result = execute_fast_paper_buy(
        paper_checkpoint.state.ledger,
        approval,
        retry.risk_context,
        execution_policy.risk_policy,
        execution_policy.fill_policy,
        evaluated_at_unix_ms=retry.evaluated_at_unix_ms,
        quote=_buy_quote_from_shadow(
            retry.quote,
            retry.quote_usd_evidence.quote_to_usd_rate,
        ),
    )
    ledger = result.next_ledger
    position_states = list(
        paper_checkpoint.state.position_action_states
    )
    mappings = list(shadow_state.market_positions)
    next_pending = pending if result.outcome is FastPaperBuyOutcome.DEFERRED else None
    canonical_pending = approval if result.outcome is FastPaperBuyOutcome.DEFERRED else None

    if result.outcome is FastPaperBuyOutcome.FILLED:
        position_id = _filled_position_id(result, ledger)
        position_states.append(
            create_fast_paper_position_action_state(
                position_id,
                ledger.as_of_unix_ms,
            )
        )
        mappings.append(
            FastPaperShadowMarketPosition(
                market_key=pending.market_key,
                position_id=position_id,
                mint=pending.mint,
                current_exposure_fraction=(
                    pending.target_exposure_fraction
                ),
            )
        )

    next_state = _paper_state(
        paper_checkpoint.state,
        event_loop_state=paper_checkpoint.state.event_loop_state,
        ledger=ledger,
        as_of_unix_ms=max(
            paper_checkpoint.state.as_of_unix_ms,
            retry.evaluated_at_unix_ms,
            ledger.as_of_unix_ms,
        ),
        pending_buy=canonical_pending,
        position_action_states=tuple(position_states),
    )
    return _transition(
        replayed=False,
        source_event_id=approval.assessment.source_event_id,
        buy_result=result,
        position_result=None,
        paper_state=next_state,
        market_positions=_canonical_mappings(tuple(mappings)),
        pending_buy=next_pending,
        last_sequence=shadow_state.last_processed_source_sequence,
        last_event_id=shadow_state.last_processed_source_event_id,
        last_fingerprint=(
            shadow_state.last_processed_decision_evidence_fingerprint_sha256
        ),
    )


def build_fast_paper_shadow_runtime_state_from_transition(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    transition: FastPaperShadowExecutionTransition,
) -> FastPaperShadowRuntimeState:
    if type(transition) is not FastPaperShadowExecutionTransition:
        raise ValueError(
            "transition must be exact FastPaperShadowExecutionTransition"
        )
    if paper_checkpoint.state != transition.next_paper_state:
        raise ValueError(
            "persisted paper checkpoint does not match shadow execution transition"
        )
    return build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        paper_checkpoint,
        market_positions=transition.next_market_positions,
        pending_buy=transition.next_pending_buy,
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


def _execute_fresh_buy(
    manifest,
    execution_policy,
    source,
    point,
    event_loop_state,
    base_state,
    shadow_state,
    assessment,
) -> FastPaperShadowExecutionTransition:
    authority = point.entry_authority
    risk_context = point.risk_context
    quote = point.quote
    if authority is None or risk_context is None or quote is None:
        raise ValueError(
            "materialized BUY evidence is incomplete"
        )
    approval = FastPaperBuyApproval(
        version=FAST_PAPER_BUY_VERSION,
        assessment=assessment,
        mint=authority.mint,
        quote_mint=authority.quote_mint,
        state_version=point.state_version,
        intended_base_quantity=authority.intended_base_quantity,
        decision_executable_entry_price_quote=(
            authority.decision_executable_entry_price_quote
        ),
        maximum_acceptable_entry_price_quote=(
            authority.maximum_acceptable_entry_price_quote
        ),
        expected_entry_variable_cost_bps=(
            authority.expected_entry_variable_cost_bps
        ),
        expected_entry_fixed_cost_quote=(
            authority.expected_entry_fixed_cost_quote
        ),
    )
    result = execute_fast_paper_buy(
        base_state.ledger,
        approval,
        risk_context,
        execution_policy.risk_policy,
        execution_policy.fill_policy,
        evaluated_at_unix_ms=point.evaluated_at_unix_ms,
        quote=_buy_quote(quote),
    )
    ledger = result.next_ledger
    position_states = list(base_state.position_action_states)
    mappings = list(shadow_state.market_positions)
    pending = None
    canonical_pending = None

    if result.outcome is FastPaperBuyOutcome.DEFERRED:
        canonical_pending = approval
        pending = FastPaperShadowPendingBuy(
            market_key=source.decision_evidence.market_key,
            mint=authority.mint,
            source_event_id=source.decision_evidence.source_event_id,
            target_exposure_fraction=(
                source.decision_evidence.decision.target_exposure_fraction
            ),
        )
    elif result.outcome is FastPaperBuyOutcome.FILLED:
        position_id = _filled_position_id(result, ledger)
        position_states.append(
            create_fast_paper_position_action_state(
                position_id,
                ledger.as_of_unix_ms,
            )
        )
        mappings.append(
            FastPaperShadowMarketPosition(
                market_key=source.decision_evidence.market_key,
                position_id=position_id,
                mint=authority.mint,
                current_exposure_fraction=(
                    source.decision_evidence.decision.target_exposure_fraction
                ),
            )
        )

    next_state = _paper_state(
        base_state,
        event_loop_state=event_loop_state,
        ledger=ledger,
        as_of_unix_ms=max(
            base_state.as_of_unix_ms,
            point.evaluated_at_unix_ms,
            ledger.as_of_unix_ms,
        ),
        pending_buy=canonical_pending,
        position_action_states=tuple(position_states),
    )
    return _fresh_transition(
        source,
        next_state,
        _canonical_mappings(tuple(mappings)),
        pending_buy=pending,
        buy_result=result,
    )


def _execute_position_action(
    execution_policy,
    source,
    point,
    event_loop_state,
    base_state,
    shadow_state,
    assessment,
) -> FastPaperShadowExecutionTransition:
    if point.quote is None:
        raise ValueError(
            "materialized OPEN-position action evidence is missing quote"
        )
    mapping = _mapping_for_market(
        shadow_state,
        source.decision_evidence.market_key,
    )
    position = _open_position(
        base_state.ledger,
        mapping.position_id,
    )
    action_state = _position_state(
        base_state,
        mapping.position_id,
    )
    quote = _position_execution_quote_evidence(
        source,
        point.quote,
        action_state,
        position,
        mapping.current_exposure_fraction,
    )
    target_quantity = _position_exit_quantity(
        source,
        position,
        mapping.current_exposure_fraction,
    )
    result = apply_fast_paper_position_action(
        state=action_state,
        approval=FastPaperPositionActionApproval(
            version=FAST_PAPER_POSITION_ACTION_VERSION,
            assessment=assessment,
            position_id=position.position_id,
            mint=position.mint,
            quote_mint=quote.quote_mint,
            state_version=point.state_version,
            target_base_quantity=target_quantity,
        ),
        ledger=base_state.ledger,
        quote=_position_quote(quote),
        fill_policy=execution_policy.fill_policy,
        policy=execution_policy.position_action_policy,
        evaluated_at_unix_ms=point.evaluated_at_unix_ms,
    )

    states = {
        value.position_id: value
        for value in base_state.position_action_states
    }
    mappings = {
        value.market_key: value
        for value in shadow_state.market_positions
    }
    ledger = result.next_ledger

    if result.outcome is FastPaperPositionOutcome.SOLD:
        states.pop(position.position_id, None)
        mappings.pop(mapping.market_key, None)
    else:
        states[position.position_id] = result.next_state
        if result.outcome is FastPaperPositionOutcome.REDUCED:
            after = _open_position(ledger, position.position_id)
            ratio = after.quantity / position.quantity
            exposure = mapping.current_exposure_fraction * ratio
            if (
                not math.isfinite(exposure)
                or exposure <= 0.0
                or exposure > mapping.current_exposure_fraction
            ):
                raise ValueError(
                    "authoritative REDUCE quantity produced invalid learned exposure"
                )
            mappings[mapping.market_key] = FastPaperShadowMarketPosition(
                market_key=mapping.market_key,
                position_id=mapping.position_id,
                mint=mapping.mint,
                current_exposure_fraction=exposure,
            )

    next_state = _paper_state(
        base_state,
        event_loop_state=event_loop_state,
        ledger=ledger,
        as_of_unix_ms=max(
            base_state.as_of_unix_ms,
            point.evaluated_at_unix_ms,
            ledger.as_of_unix_ms,
        ),
        pending_buy=None,
        position_action_states=tuple(
            states[key] for key in sorted(states)
        ),
    )
    return _fresh_transition(
        source,
        next_state,
        _canonical_mappings(tuple(mappings.values())),
        pending_buy=None,
        position_result=result,
    )


def _fresh_transition(
    source,
    paper_state,
    market_positions,
    *,
    pending_buy,
    buy_result=None,
    position_result=None,
) -> FastPaperShadowExecutionTransition:
    evidence = source.decision_evidence
    return _transition(
        replayed=False,
        source_event_id=evidence.source_event_id,
        buy_result=buy_result,
        position_result=position_result,
        paper_state=paper_state,
        market_positions=market_positions,
        pending_buy=pending_buy,
        last_sequence=evidence.source_sequence,
        last_event_id=evidence.source_event_id,
        last_fingerprint=evidence.evidence_fingerprint_sha256,
    )


def _transition(
    *,
    replayed,
    source_event_id,
    buy_result,
    position_result,
    paper_state,
    market_positions,
    pending_buy,
    last_sequence,
    last_event_id,
    last_fingerprint,
):
    return FastPaperShadowExecutionTransition(
        version=FAST_PAPER_SHADOW_EXECUTOR_VERSION,
        replayed=replayed,
        source_event_id=source_event_id,
        buy_result=buy_result,
        position_result=position_result,
        next_paper_state=paper_state,
        next_market_positions=_canonical_mappings(market_positions),
        next_pending_buy=pending_buy,
        last_processed_source_sequence=last_sequence,
        last_processed_source_event_id=last_event_id,
        last_processed_decision_evidence_fingerprint_sha256=last_fingerprint,
    )


def _require_authority_bindings(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    binding: FastPaperShadowLedgerBinding,
    checkpoint: FastPaperCheckpointRecord,
    shadow_state: FastPaperShadowRuntimeState,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    expected_policy = build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=execution_policy.risk_policy,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=(
            execution_policy.position_action_policy
        ),
    )
    if execution_policy != expected_policy:
        raise ValueError(
            "shadow executor execution policy does not authenticate against runtime manifest"
        )
    expected_binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id=binding.run_id,
        database_path=binding.database_path,
    )
    if binding != expected_binding:
        raise ValueError(
            "shadow executor ledger binding does not authenticate against runtime manifest"
        )
    if shadow_state.binding_fingerprint_sha256 != binding.binding_fingerprint_sha256:
        raise ValueError(
            "shadow executor learned posture binding fingerprint mismatch"
        )
    if checkpoint.state.fill_policy != execution_policy.fill_policy:
        raise ValueError(
            "shadow executor fill policy conflicts with checkpoint-pinned policy"
        )
    if (
        checkpoint.state.position_action_policy
        != execution_policy.position_action_policy
    ):
        raise ValueError(
            "shadow executor position-action policy conflicts with checkpoint-pinned policy"
        )
    if checkpoint.run_id != binding.run_id:
        raise ValueError(
            "shadow executor paper checkpoint run_id does not match ledger binding"
        )
    latest_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest_checkpoint is None or latest_checkpoint != checkpoint:
        raise ValueError(
            "shadow executor requires the exact latest durable paper checkpoint"
        )
    latest_shadow_state = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_shadow_state is None or latest_shadow_state != shadow_state:
        raise ValueError(
            "shadow executor requires the exact latest durable learned posture state"
        )
    _require_checkpoint_pair(
        checkpoint,
        shadow_state,
    )


def _require_checkpoint_pair(
    checkpoint: FastPaperCheckpointRecord,
    shadow_state: FastPaperShadowRuntimeState,
) -> None:
    if type(checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if type(shadow_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "shadow_state must be exact FastPaperShadowRuntimeState"
        )
    if (
        shadow_state.paper_checkpoint_sequence != checkpoint.sequence
        or shadow_state.paper_checkpoint_payload_sha256
        != checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow executor checkpoint and learned posture state are torn"
        )
    open_positions = {
        value.position_id: value
        for value in checkpoint.state.ledger.positions
        if value.state is PaperPositionState.OPEN
    }
    mapped = {
        value.position_id: value
        for value in shadow_state.market_positions
    }
    if set(mapped) != set(open_positions):
        raise ValueError(
            "shadow executor learned posture does not exactly cover OPEN PAPER positions"
        )
    for position_id, mapping in mapped.items():
        if mapping.mint != open_positions[position_id].mint:
            raise ValueError(
                "shadow executor learned posture mint conflicts with PAPER position"
            )
    approval = checkpoint.state.pending_buy
    pending = shadow_state.pending_buy
    if (approval is None) != (pending is None):
        raise ValueError(
            "shadow executor pending BUY checkpoint/posture state is torn"
        )
    if approval is not None:
        assert pending is not None
        if (
            pending.market_key != approval.assessment.market_key
            or pending.mint != approval.mint
            or pending.source_event_id
            != approval.assessment.source_event_id
        ):
            raise ValueError(
                "shadow executor pending BUY learned target identity mismatch"
            )


def _require_new_decision_order(
    shadow_state: FastPaperShadowRuntimeState,
    source_sequence: int,
) -> None:
    previous = shadow_state.last_processed_source_sequence
    if previous is not None and source_sequence <= previous:
        raise ValueError(
            "new learned shadow decision sequence must strictly advance"
        )


def _require_exact_processed_replay(
    shadow_state: FastPaperShadowRuntimeState,
    source: FastPaperShadowExecutionInput,
) -> None:
    evidence = source.decision_evidence
    expected = (
        evidence.source_sequence,
        evidence.source_event_id,
        evidence.evidence_fingerprint_sha256,
    )
    actual = (
        shadow_state.last_processed_source_sequence,
        shadow_state.last_processed_source_event_id,
        shadow_state.last_processed_decision_evidence_fingerprint_sha256,
    )
    if actual != expected:
        raise ValueError(
            "Fast PAPER event replay conflicts with learned decision checkpoint identity"
        )


def _require_learned_posture(
    shadow_state: FastPaperShadowRuntimeState,
    source: FastPaperShadowExecutionInput,
) -> None:
    evidence = source.decision_evidence
    expected = fast_paper_shadow_decision_position(
        shadow_state,
        evidence.market_key,
    )
    if expected != evidence.position:
        raise ValueError(
            "learned decision posture does not match durable shadow posture"
        )


def _require_new_buy_mint_available(
    ledger: PaperLedger,
    shadow_state: FastPaperShadowRuntimeState,
    mint: str,
) -> None:
    if any(
        position.state is PaperPositionState.OPEN
        and position.mint == mint
        for position in ledger.positions
    ):
        raise ValueError(
            "new shadow BUY mint is already OPEN in the isolated PAPER ledger"
        )
    if any(
        mapping.mint == mint
        for mapping in shadow_state.market_positions
    ):
        raise ValueError(
            "new shadow BUY mint already has durable learned OPEN posture"
        )


def _paper_state(
    base: FastPaperRuntimeState,
    *,
    event_loop_state,
    ledger,
    as_of_unix_ms,
    pending_buy,
    position_action_states,
) -> FastPaperRuntimeState:
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=as_of_unix_ms,
        event_loop_state=event_loop_state,
        ledger=ledger,
        fill_policy=base.fill_policy,
        position_action_policy=base.position_action_policy,
        pending_buy=pending_buy,
        position_action_states=tuple(position_action_states),
    )


def _position_execution_quote_evidence(
    source: FastPaperShadowExecutionInput,
    selected_quote: FastCampaignPaperQuoteEvidence,
    action_state,
    position: PaperPosition,
    current_exposure: float,
) -> FastCampaignPaperQuoteEvidence:
    pending = action_state.pending_exit
    fresh_action = source.decision_evidence.decision.action
    if pending is None:
        return selected_quote
    if pending.assessment.action is FastPaperAction.SELL:
        return _campaign_quote_from_shadow(
            source.decision_evidence.exit_quote,
            source.quote_usd_evidence,
        )
    if fresh_action == "SELL":
        return selected_quote
    if pending.assessment.action is not FastPaperAction.REDUCE:
        raise ValueError(
            "shadow executor pending exit action is unsupported"
        )
    exit_quantity = pending.target_base_quantity
    if exit_quantity is None:
        raise ValueError(
            "pending REDUCE is missing base-quantity authority"
        )
    target_exposure = current_exposure * (
        1.0 - exit_quantity / position.quantity
    )
    if (
        not math.isfinite(target_exposure)
        or target_exposure <= 0.0
        or target_exposure >= current_exposure
    ):
        raise ValueError(
            "pending REDUCE cannot reconstruct learned target exposure"
        )
    matches = tuple(
        item.quote
        for item in source.decision_evidence.reduction_quotes
        if math.isclose(
            item.target_exposure_fraction,
            target_exposure,
            rel_tol=_REL_TOL,
            abs_tol=1e-15,
        )
    )
    if len(matches) != 1:
        raise ValueError(
            "pending REDUCE requires exactly one fresh target-sized reduction quote"
        )
    return _campaign_quote_from_shadow(
        matches[0],
        source.quote_usd_evidence,
    )


def _campaign_quote_from_shadow(
    value: FastPaperShadowQuoteEvidence,
    usd: FastPaperShadowQuoteUsdEvidence | None,
) -> FastCampaignPaperQuoteEvidence:
    if usd is None:
        raise ValueError(
            "OPEN-position execution requires explicit quote/USD evidence"
        )
    if usd.quote_mint != value.quote_mint:
        raise ValueError(
            "position quote/USD mint attribution mismatch"
        )
    return FastCampaignPaperQuoteEvidence(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=PaperQuoteState(value.state),
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=usd.quote_to_usd_rate,
    )


def _position_exit_quantity(
    source: FastPaperShadowExecutionInput,
    position: PaperPosition,
    current_exposure: float,
) -> float | None:
    decision = source.decision_evidence.decision
    if decision.action == "HOLD":
        return None
    if decision.action == "SELL":
        return position.quantity
    if decision.action != "REDUCE":
        raise ValueError(
            "position exit quantity requested for unsupported learned action"
        )
    target = decision.target_exposure_fraction
    if target <= 0.0 or target >= current_exposure:
        raise ValueError(
            "learned REDUCE target must be positive and below current exposure"
        )
    quantity = position.quantity * (
        1.0 - target / current_exposure
    )
    if (
        not math.isfinite(quantity)
        or quantity <= 0.0
        or quantity >= position.quantity
        or math.isclose(
            quantity,
            position.quantity,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        )
    ):
        raise ValueError(
            "derived learned REDUCE base quantity is invalid"
        )
    return quantity


def _filled_position_id(
    result: FastPaperBuyResult,
    ledger: PaperLedger,
) -> str:
    update = result.ledger_update
    if update is None or update.position_id is None:
        raise ValueError(
            "FILLED shadow BUY requires authoritative position ID"
        )
    position = _open_position(ledger, update.position_id)
    if position.mint != result.mint:
        raise ValueError(
            "FILLED shadow BUY position mint conflicts with result"
        )
    return position.position_id


def _mapping_for_market(
    state: FastPaperShadowRuntimeState,
    market_key: str,
) -> FastPaperShadowMarketPosition:
    matches = tuple(
        value
        for value in state.market_positions
        if value.market_key == market_key
    )
    if len(matches) != 1:
        raise ValueError(
            "OPEN learned action requires exactly one durable market mapping"
        )
    return matches[0]


def _open_position(
    ledger: PaperLedger,
    position_id: str,
) -> PaperPosition:
    matches = tuple(
        value
        for value in ledger.positions
        if value.position_id == position_id
        and value.state is PaperPositionState.OPEN
    )
    if len(matches) != 1:
        raise ValueError(
            "shadow executor requires one authoritative OPEN PAPER position"
        )
    return matches[0]


def _position_state(
    state: FastPaperRuntimeState,
    position_id: str,
):
    matches = tuple(
        value
        for value in state.position_action_states
        if value.position_id == position_id
    )
    if len(matches) != 1:
        raise ValueError(
            "shadow executor requires one Fast PAPER position-action state"
        )
    return matches[0]


def _buy_quote(
    value: FastCampaignPaperQuoteEvidence,
) -> FastPaperBuyQuote:
    return FastPaperBuyQuote(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=value.state,
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=value.quote_to_usd_rate,
    )


def _position_quote(
    value: FastCampaignPaperQuoteEvidence,
) -> FastPaperPositionQuote:
    return FastPaperPositionQuote(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=value.state,
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=value.quote_to_usd_rate,
    )


def _buy_quote_from_shadow(
    value: FastPaperShadowQuoteEvidence,
    quote_to_usd_rate: float,
) -> FastPaperBuyQuote:
    return FastPaperBuyQuote(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=PaperQuoteState(value.state),
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=quote_to_usd_rate,
    )


def _validate_pending_retry_quote(
    manifest: FastPaperRuntimeManifest,
    approval: FastPaperBuyApproval,
    retry: FastPaperShadowPendingBuyRetryInput,
) -> None:
    quote = retry.quote
    usd = retry.quote_usd_evidence
    if quote.provider != manifest.quote_provider:
        raise ValueError(
            "pending BUY retry quote provider does not match runtime manifest"
        )
    if quote.mint != approval.mint:
        raise ValueError(
            "pending BUY retry quote mint does not match approval"
        )
    if quote.quote_mint != approval.quote_mint:
        raise ValueError(
            "pending BUY retry quote currency does not match approval"
        )
    if usd.quote_mint != approval.quote_mint:
        raise ValueError(
            "pending BUY retry USD quote mint does not match approval"
        )
    if quote.observed_at_unix_ms < approval.decision_at_unix_ms:
        raise ValueError(
            "pending BUY retry quote predates original learned decision"
        )


def _canonical_mappings(
    values: tuple[FastPaperShadowMarketPosition, ...],
) -> tuple[FastPaperShadowMarketPosition, ...]:
    result = tuple(
        sorted(values, key=lambda value: value.market_key)
    )
    keys = tuple(value.market_key for value in result)
    ids = tuple(value.position_id for value in result)
    if len(keys) != len(set(keys)) or len(ids) != len(set(ids)):
        raise ValueError(
            "shadow executor market mappings must be unique"
        )
    return result


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


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(
            f"{name} must be positive"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )
