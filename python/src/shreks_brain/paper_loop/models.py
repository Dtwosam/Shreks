from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shreks_brain.decision import DecisionAction, DecisionPolicy, TradeDecision
from shreks_brain.exits import (
    ExitAssessment,
    ExitExecutionContext,
    ExitPolicy,
    ExitState,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import (
    PaperExecutionResult,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdate,
    PaperPositionState,
    PaperQuote,
)
from shreks_brain.regime import RegimeAssessment
from shreks_brain.risk import RiskAssessment, RiskContext, RiskPolicy, TradeIntent, TradeSide
from shreks_brain.runtime import RuntimeMode
from shreks_brain.scoring import ScoreAssessment, ScorePolicy
from shreks_brain.setups import (
    FirstPullbackAssessment,
    FirstPullbackPolicy,
    FreshLaunchAssessment,
    FreshLaunchPolicy,
    GraduationBreakoutAssessment,
    GraduationBreakoutPolicy,
    GraduationContext,
    PullbackContext,
)


class PaperLoopReasonCode(StrEnum):
    CYCLE_APPLIED = "CYCLE_APPLIED"
    CYCLE_BEFORE_STATE = "CYCLE_BEFORE_STATE"
    PENDING_ENTRY_DEFERRED = "PENDING_ENTRY_DEFERRED"
    PENDING_ENTRY_TERMINAL = "PENDING_ENTRY_TERMINAL"
    ENTRY_NOT_SELECTED = "ENTRY_NOT_SELECTED"
    ENTRY_OPEN_POSITION_EXISTS = "ENTRY_OPEN_POSITION_EXISTS"
    ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH = (
        "ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH"
    )
    ENTRY_RISK_REJECTED = "ENTRY_RISK_REJECTED"
    ENTRY_EXECUTION_DEFERRED = "ENTRY_EXECUTION_DEFERRED"
    ENTRY_EXECUTION_TERMINAL = "ENTRY_EXECUTION_TERMINAL"
    EXIT_OBSERVATION_MISSING = "EXIT_OBSERVATION_MISSING"
    EXIT_HOLD = "EXIT_HOLD"
    EXIT_QUOTE_MISSING = "EXIT_QUOTE_MISSING"
    EXIT_QUOTE_AFTER_CYCLE = "EXIT_QUOTE_AFTER_CYCLE"
    EXIT_QUOTE_BEFORE_LATENCY = "EXIT_QUOTE_BEFORE_LATENCY"
    EXIT_EXECUTION_PRICE_UNAVAILABLE = "EXIT_EXECUTION_PRICE_UNAVAILABLE"
    EXIT_EXECUTION_TERMINAL = "EXIT_EXECUTION_TERMINAL"
    EXIT_POSITION_CLOSED = "EXIT_POSITION_CLOSED"


@dataclass(frozen=True, slots=True)
class PaperLoopFinding:
    code: PaperLoopReasonCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, PaperLoopReasonCode):
            raise ValueError("code must be a PaperLoopReasonCode")
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class PaperLoopPolicy:
    version: str
    exit_max_slippage_bps: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_bps("exit_max_slippage_bps", self.exit_max_slippage_bps)


@dataclass(frozen=True, slots=True)
class FreshLaunchSetupInput:
    policy: FreshLaunchPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.policy, FreshLaunchPolicy):
            raise ValueError("policy must be a FreshLaunchPolicy")


@dataclass(frozen=True, slots=True)
class GraduationBreakoutSetupInput:
    context: GraduationContext | None
    policy: GraduationBreakoutPolicy

    def __post_init__(self) -> None:
        if self.context is not None and not isinstance(self.context, GraduationContext):
            raise ValueError("context must be a GraduationContext or None")
        if not isinstance(self.policy, GraduationBreakoutPolicy):
            raise ValueError("policy must be a GraduationBreakoutPolicy")


@dataclass(frozen=True, slots=True)
class FirstPullbackSetupInput:
    context: PullbackContext | None
    policy: FirstPullbackPolicy

    def __post_init__(self) -> None:
        if self.context is not None and not isinstance(self.context, PullbackContext):
            raise ValueError("context must be a PullbackContext or None")
        if not isinstance(self.policy, FirstPullbackPolicy):
            raise ValueError("policy must be a FirstPullbackPolicy")


SetupInput = FreshLaunchSetupInput | GraduationBreakoutSetupInput | FirstPullbackSetupInput
SetupAssessment = FreshLaunchAssessment | GraduationBreakoutAssessment | FirstPullbackAssessment


@dataclass(frozen=True, slots=True)
class PaperEntryCandidate:
    mint: str
    features: FeatureVector
    regime: RegimeAssessment
    setup: SetupInput
    score_policy: ScorePolicy
    decision_policy: DecisionPolicy
    risk_context: RiskContext
    risk_policy: RiskPolicy
    exit_policy: ExitPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.features, FeatureVector):
            raise ValueError("features must be a FeatureVector")
        if not isinstance(self.regime, RegimeAssessment):
            raise ValueError("regime must be a RegimeAssessment")
        if not isinstance(
            self.setup,
            (FreshLaunchSetupInput, GraduationBreakoutSetupInput, FirstPullbackSetupInput),
        ):
            raise ValueError("setup must be a supported C5 setup input")
        if not isinstance(self.score_policy, ScorePolicy):
            raise ValueError("score_policy must be a ScorePolicy")
        if not isinstance(self.decision_policy, DecisionPolicy):
            raise ValueError("decision_policy must be a DecisionPolicy")
        if not isinstance(self.risk_context, RiskContext):
            raise ValueError("risk_context must be a RiskContext")
        if not isinstance(self.risk_policy, RiskPolicy):
            raise ValueError("risk_policy must be a RiskPolicy")
        if not isinstance(self.exit_policy, ExitPolicy):
            raise ValueError("exit_policy must be an ExitPolicy")


@dataclass(frozen=True, slots=True)
class PaperExitObservation:
    position_id: str
    features: FeatureVector
    execution_context: ExitExecutionContext

    def __post_init__(self) -> None:
        _require_non_empty_string("position_id", self.position_id)
        if not isinstance(self.features, FeatureVector):
            raise ValueError("features must be a FeatureVector")
        if not isinstance(self.execution_context, ExitExecutionContext):
            raise ValueError("execution_context must be an ExitExecutionContext")


@dataclass(frozen=True, slots=True)
class ManagedPaperPosition:
    position_id: str
    exit_policy: ExitPolicy
    exit_state: ExitState
    pending_exit: ExitAssessment | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string("position_id", self.position_id)
        if not isinstance(self.exit_policy, ExitPolicy):
            raise ValueError("managed exit_policy must be an ExitPolicy")
        if not isinstance(self.exit_state, ExitState):
            raise ValueError("managed exit_state must be an ExitState")
        if self.exit_state.position_id != self.position_id:
            raise ValueError("managed exit_state position_id must match position_id")
        if self.exit_state.policy_version != self.exit_policy.version:
            raise ValueError("managed exit_state policy version must match exit_policy")
        if self.pending_exit is None:
            return
        if not isinstance(self.pending_exit, ExitAssessment):
            raise ValueError("pending_exit must be an ExitAssessment or None")
        if self.pending_exit.position_id != self.position_id:
            raise ValueError("pending_exit position_id must match managed position")
        if self.pending_exit.mint != self.exit_state.mint:
            raise ValueError("pending_exit mint must match managed exit_state")
        if self.pending_exit.policy_version != self.exit_policy.version:
            raise ValueError("pending_exit policy version must match exit_policy")
        if self.pending_exit.action not in (DecisionAction.REDUCE, DecisionAction.EXIT):
            raise ValueError("pending_exit action must be REDUCE or EXIT")
        if self.pending_exit.target_quantity <= 0.0:
            raise ValueError("pending_exit target quantity must be positive")
        if self.pending_exit.as_of_unix_ms > self.exit_state.last_evaluated_at_unix_ms:
            raise ValueError("pending_exit cannot be later than managed exit_state")


@dataclass(frozen=True, slots=True)
class PendingPaperEntry:
    intent: TradeIntent
    exit_policy: ExitPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.intent, TradeIntent):
            raise ValueError("intent must be a TradeIntent")
        if (
            self.intent.execution_mode is not RuntimeMode.PAPER
            or self.intent.side is not TradeSide.BUY
        ):
            raise ValueError("pending entry intent must be a PAPER BUY")
        if not isinstance(self.exit_policy, ExitPolicy):
            raise ValueError("exit_policy must be an ExitPolicy")


@dataclass(frozen=True, slots=True)
class PaperPendingEntryResult:
    intent_idempotency_key: str
    mint: str
    execution: PaperExecutionResult
    ledger_update: PaperLedgerUpdate | None
    reason: PaperLoopReasonCode

    def __post_init__(self) -> None:
        _require_non_empty_string("intent_idempotency_key", self.intent_idempotency_key)
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.execution, PaperExecutionResult):
            raise ValueError("execution must be a PaperExecutionResult")
        if self.ledger_update is not None and not isinstance(
            self.ledger_update, PaperLedgerUpdate
        ):
            raise ValueError("ledger_update must be a PaperLedgerUpdate or None")
        if self.reason not in (
            PaperLoopReasonCode.PENDING_ENTRY_DEFERRED,
            PaperLoopReasonCode.PENDING_ENTRY_TERMINAL,
        ):
            raise ValueError("pending entry result reason is invalid")


@dataclass(frozen=True, slots=True)
class PaperEntryResult:
    mint: str
    setup_assessment: SetupAssessment
    score_assessment: ScoreAssessment
    decision: TradeDecision
    risk_assessment: RiskAssessment | None
    selected_for_entry: bool
    execution: PaperExecutionResult | None
    ledger_update: PaperLedgerUpdate | None
    reason: PaperLoopReasonCode

    def __post_init__(self) -> None:
        _require_non_empty_string("mint", self.mint)
        if not isinstance(
            self.setup_assessment,
            (FreshLaunchAssessment, GraduationBreakoutAssessment, FirstPullbackAssessment),
        ):
            raise ValueError("setup_assessment must be a supported setup assessment")
        if not isinstance(self.score_assessment, ScoreAssessment):
            raise ValueError("score_assessment must be a ScoreAssessment")
        if not isinstance(self.decision, TradeDecision):
            raise ValueError("decision must be a TradeDecision")
        if self.risk_assessment is not None and not isinstance(
            self.risk_assessment, RiskAssessment
        ):
            raise ValueError("risk_assessment must be a RiskAssessment or None")
        _require_bool("selected_for_entry", self.selected_for_entry)
        if self.execution is not None and not isinstance(
            self.execution, PaperExecutionResult
        ):
            raise ValueError("execution must be a PaperExecutionResult or None")
        if self.ledger_update is not None and not isinstance(
            self.ledger_update, PaperLedgerUpdate
        ):
            raise ValueError("ledger_update must be a PaperLedgerUpdate or None")
        if not isinstance(self.reason, PaperLoopReasonCode):
            raise ValueError("reason must be a PaperLoopReasonCode")
        if self.selected_for_entry and self.execution is None:
            raise ValueError("selected entry result requires execution evidence")
        if not self.selected_for_entry and self.execution is not None:
            raise ValueError("unselected entry result cannot carry execution evidence")


@dataclass(frozen=True, slots=True)
class PaperExitResult:
    position_id: str
    mint: str
    exit_assessment: ExitAssessment | None
    intent: TradeIntent | None
    execution: PaperExecutionResult | None
    execution_ledger_update: PaperLedgerUpdate | None
    mark_ledger_update: PaperLedgerUpdate | None
    reason: PaperLoopReasonCode

    def __post_init__(self) -> None:
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        if self.exit_assessment is not None and not isinstance(
            self.exit_assessment, ExitAssessment
        ):
            raise ValueError("exit_assessment must be an ExitAssessment or None")
        if self.intent is not None:
            if not isinstance(self.intent, TradeIntent):
                raise ValueError("intent must be a TradeIntent or None")
            if (
                self.intent.execution_mode is not RuntimeMode.PAPER
                or self.intent.side is not TradeSide.SELL
            ):
                raise ValueError("exit intent must be a PAPER SELL")
        if self.execution is not None and not isinstance(
            self.execution, PaperExecutionResult
        ):
            raise ValueError("execution must be a PaperExecutionResult or None")
        for name in ("execution_ledger_update", "mark_ledger_update"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, PaperLedgerUpdate):
                raise ValueError(f"{name} must be a PaperLedgerUpdate or None")
        if not isinstance(self.reason, PaperLoopReasonCode):
            raise ValueError("reason must be a PaperLoopReasonCode")


@dataclass(frozen=True, slots=True)
class PaperCycleInput:
    as_of_unix_ms: int
    entry_candidates: tuple[PaperEntryCandidate, ...]
    exit_observations: tuple[PaperExitObservation, ...]
    quotes: tuple[PaperQuote, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_tuple_of("entry_candidates", self.entry_candidates, PaperEntryCandidate)
        _require_tuple_of(
            "exit_observations", self.exit_observations, PaperExitObservation
        )
        _require_tuple_of("quotes", self.quotes, PaperQuote)

        candidate_mints = tuple(candidate.mint for candidate in self.entry_candidates)
        if len(candidate_mints) != len(set(candidate_mints)):
            raise ValueError("candidate mints must be unique within a cycle")
        quote_mints = tuple(quote.mint for quote in self.quotes)
        if len(quote_mints) != len(set(quote_mints)):
            raise ValueError("quote mints must be unique within a cycle")
        exit_ids = tuple(item.position_id for item in self.exit_observations)
        if len(exit_ids) != len(set(exit_ids)):
            raise ValueError("exit observation position IDs must be unique within a cycle")

        for candidate in self.entry_candidates:
            if candidate.features.as_of_unix_ms != self.as_of_unix_ms:
                raise ValueError("candidate feature timestamp must match cycle as_of")
            if candidate.regime.as_of_unix_ms != self.as_of_unix_ms:
                raise ValueError("candidate regime timestamp must match cycle as_of")
            if candidate.risk_context.as_of_unix_ms != self.as_of_unix_ms:
                raise ValueError("candidate risk timestamp must match cycle as_of")


@dataclass(frozen=True, slots=True)
class PaperLoopState:
    ledger: PaperLedger
    loop_policy: PaperLoopPolicy
    paper_fill_policy: PaperFillPolicy
    managed_positions: tuple[ManagedPaperPosition, ...]
    pending_entry: PendingPaperEntry | None
    last_cycle_at_unix_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.ledger, PaperLedger):
            raise ValueError("ledger must be a PaperLedger")
        if not isinstance(self.loop_policy, PaperLoopPolicy):
            raise ValueError("loop_policy must be a PaperLoopPolicy")
        if not isinstance(self.paper_fill_policy, PaperFillPolicy):
            raise ValueError("paper_fill_policy must be a PaperFillPolicy")
        _require_tuple_of(
            "managed_positions", self.managed_positions, ManagedPaperPosition
        )
        if self.pending_entry is not None and not isinstance(
            self.pending_entry, PendingPaperEntry
        ):
            raise ValueError("pending_entry must be a PendingPaperEntry or None")
        _require_non_negative_int("last_cycle_at_unix_ms", self.last_cycle_at_unix_ms)
        if self.last_cycle_at_unix_ms < self.ledger.as_of_unix_ms:
            raise ValueError("last_cycle_at_unix_ms must not precede ledger time")

        managed_ids = tuple(item.position_id for item in self.managed_positions)
        if len(managed_ids) != len(set(managed_ids)):
            raise ValueError("managed position IDs must be unique")
        open_positions = tuple(
            position
            for position in self.ledger.positions
            if position.state is PaperPositionState.OPEN
        )
        open_ids = tuple(position.position_id for position in open_positions)
        if set(managed_ids) != set(open_ids):
            raise ValueError("managed positions must exactly cover OPEN ledger positions")
        positions_by_id = {position.position_id: position for position in open_positions}
        for managed in self.managed_positions:
            position = positions_by_id[managed.position_id]
            if managed.exit_state.mint != position.mint:
                raise ValueError("managed exit_state mint must match ledger position")
            if managed.exit_state.last_evaluated_at_unix_ms > self.last_cycle_at_unix_ms:
                raise ValueError("managed exit state cannot be later than loop state")


@dataclass(frozen=True, slots=True)
class PaperCycleResult:
    policy_version: str
    as_of_unix_ms: int
    next_state: PaperLoopState
    pending_entry_result: PaperPendingEntryResult | None
    entry_results: tuple[PaperEntryResult, ...]
    exit_results: tuple[PaperExitResult, ...]
    findings: tuple[PaperLoopFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.next_state, PaperLoopState):
            raise ValueError("next_state must be a PaperLoopState")
        if self.next_state.loop_policy.version != self.policy_version:
            raise ValueError("next_state loop policy must match result policy_version")
        if self.pending_entry_result is not None and not isinstance(
            self.pending_entry_result, PaperPendingEntryResult
        ):
            raise ValueError(
                "pending_entry_result must be a PaperPendingEntryResult or None"
            )
        _require_tuple_of("entry_results", self.entry_results, PaperEntryResult)
        _require_tuple_of("exit_results", self.exit_results, PaperExitResult)
        _require_tuple_of("findings", self.findings, PaperLoopFinding)
        if len(self.findings) != 1:
            raise ValueError("findings must contain exactly one PaperLoopFinding")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_bps(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value > 10_000:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 10000]")


def _require_tuple_of(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if not all(isinstance(item, expected_type) for item in value):
        raise ValueError(f"{name} contains invalid values")
