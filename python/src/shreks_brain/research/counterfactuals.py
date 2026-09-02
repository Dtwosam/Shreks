from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import hashlib
import json
import math
from typing import Iterator, overload


COUNTERFACTUAL_ACTION_LABEL_VERSION = 1


class CounterfactualLabelError(ValueError):
    """Raised when FL5 counterfactual evidence is internally inconsistent."""


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ExecutionStatus(StrEnum):
    EXECUTABLE = "executable"
    NOT_EXECUTABLE = "not_executable"
    UNKNOWN = "unknown"


class CounterfactualAction(StrEnum):
    BUY_NOW = "BUY_NOW"
    SKIP = "SKIP"
    DELAY_ENTRY = "DELAY_ENTRY"
    HOLD = "HOLD"
    REDUCE_NOW = "REDUCE_NOW"
    SELL_NOW = "SELL_NOW"


@dataclass(frozen=True, slots=True)
class ExecutableTradeEvidence:
    evidence_id: str
    source_event_signature: str
    source_event_ordinal: int
    observed_at_unix_ms: int
    side: TradeSide
    base_quantity: float
    status: ExecutionStatus
    quote_amount: float | None
    evidence_version: str

    def __post_init__(self) -> None:
        _require_text("evidence_id", self.evidence_id)
        _require_text("source_event_signature", self.source_event_signature)
        _require_non_negative_int("source_event_ordinal", self.source_event_ordinal)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if not isinstance(self.side, TradeSide):
            raise CounterfactualLabelError("side must be a TradeSide")
        _require_positive_finite("base_quantity", self.base_quantity)
        if not isinstance(self.status, ExecutionStatus):
            raise CounterfactualLabelError("status must be an ExecutionStatus")
        _require_text("evidence_version", self.evidence_version)

        if self.status is ExecutionStatus.EXECUTABLE:
            if self.quote_amount is None:
                raise CounterfactualLabelError(
                    "executable trade evidence requires quote_amount"
                )
            _require_positive_finite("quote_amount", self.quote_amount)
        elif self.quote_amount is not None:
            raise CounterfactualLabelError(
                "non-executable or unknown trade evidence cannot contain quote_amount"
            )


@dataclass(frozen=True, slots=True)
class DelayedEntryAlternative:
    alternative_id: str
    entry: ExecutableTradeEvidence
    exit: ExecutableTradeEvidence | None

    def __post_init__(self) -> None:
        _require_text("alternative_id", self.alternative_id)
        if type(self.entry) is not ExecutableTradeEvidence:
            raise CounterfactualLabelError(
                "delayed entry must be exact ExecutableTradeEvidence"
            )
        if self.entry.side is not TradeSide.BUY:
            raise CounterfactualLabelError("delayed entry evidence must be a buy")
        if self.exit is not None:
            if type(self.exit) is not ExecutableTradeEvidence:
                raise CounterfactualLabelError(
                    "delayed exit must be exact ExecutableTradeEvidence or None"
                )
            if self.exit.side is not TradeSide.SELL:
                raise CounterfactualLabelError("delayed exit evidence must be a sell")
            if self.exit.base_quantity != self.entry.base_quantity:
                raise CounterfactualLabelError(
                    "delayed entry and exit evidence must use the same base quantity"
                )
            if self.exit.observed_at_unix_ms <= self.entry.observed_at_unix_ms:
                raise CounterfactualLabelError(
                    "delayed exit evidence must be observed after delayed entry"
                )


@dataclass(frozen=True, slots=True)
class EntryCounterfactualContext:
    decision_id: str
    mint: str
    quote_mint: str
    decision_observed_at_unix_ms: int
    base_quantity: float
    horizon_ms: int
    horizon_complete: bool
    buy_now: ExecutableTradeEvidence | None
    exit_at_horizon: ExecutableTradeEvidence | None
    delayed_entries: tuple[DelayedEntryAlternative, ...] = ()

    def __post_init__(self) -> None:
        _require_text("decision_id", self.decision_id)
        _require_text("mint", self.mint)
        _require_text("quote_mint", self.quote_mint)
        _require_non_negative_int(
            "decision_observed_at_unix_ms", self.decision_observed_at_unix_ms
        )
        _require_positive_finite("base_quantity", self.base_quantity)
        _require_positive_int("horizon_ms", self.horizon_ms)
        if not isinstance(self.horizon_complete, bool):
            raise CounterfactualLabelError("horizon_complete must be bool")

        horizon_end = self.decision_observed_at_unix_ms + self.horizon_ms
        if self.buy_now is not None:
            _validate_trade_for_context(
                "buy_now", self.buy_now, TradeSide.BUY, self.base_quantity
            )
            if self.buy_now.observed_at_unix_ms != self.decision_observed_at_unix_ms:
                raise CounterfactualLabelError(
                    "buy_now evidence must be observed at the decision timestamp"
                )

        if self.exit_at_horizon is not None:
            _validate_trade_for_context(
                "exit_at_horizon",
                self.exit_at_horizon,
                TradeSide.SELL,
                self.base_quantity,
            )
            if not (
                self.decision_observed_at_unix_ms
                < self.exit_at_horizon.observed_at_unix_ms
                <= horizon_end
            ):
                raise CounterfactualLabelError(
                    "exit_at_horizon evidence must be after the decision and within the horizon"
                )

        if not isinstance(self.delayed_entries, tuple) or not all(
            type(value) is DelayedEntryAlternative for value in self.delayed_entries
        ):
            raise CounterfactualLabelError(
                "delayed_entries must be a tuple of DelayedEntryAlternative values"
            )
        seen_ids: set[str] = set()
        previous_time = self.decision_observed_at_unix_ms
        for alternative in self.delayed_entries:
            if alternative.alternative_id in seen_ids:
                raise CounterfactualLabelError("delayed alternative ids must be unique")
            seen_ids.add(alternative.alternative_id)
            if alternative.entry.base_quantity != self.base_quantity:
                raise CounterfactualLabelError(
                    "delayed entry evidence must use the requested base quantity"
                )
            if not (
                self.decision_observed_at_unix_ms
                < alternative.entry.observed_at_unix_ms
                <= horizon_end
            ):
                raise CounterfactualLabelError(
                    "delayed entry evidence must be later than the decision and within the horizon"
                )
            if alternative.entry.observed_at_unix_ms <= previous_time:
                raise CounterfactualLabelError(
                    "delayed entry alternatives must be strictly ordered by observation time"
                )
            previous_time = alternative.entry.observed_at_unix_ms
            if alternative.exit is not None:
                if alternative.exit.base_quantity != self.base_quantity:
                    raise CounterfactualLabelError(
                        "delayed exit evidence must use the requested base quantity"
                    )
                if alternative.exit.observed_at_unix_ms > horizon_end:
                    raise CounterfactualLabelError(
                        "delayed exit evidence must be within the comparison horizon"
                    )


@dataclass(frozen=True, slots=True)
class OpenPositionCounterfactualContext:
    decision_id: str
    mint: str
    quote_mint: str
    action_observed_at_unix_ms: int
    position_base_quantity: float
    position_cost_basis_quote: float
    horizon_ms: int
    horizon_complete: bool
    sell_now: ExecutableTradeEvidence | None
    hold_exit: ExecutableTradeEvidence | None
    reduce_quantity: float | None = None
    reduce_now: ExecutableTradeEvidence | None = None

    def __post_init__(self) -> None:
        _require_text("decision_id", self.decision_id)
        _require_text("mint", self.mint)
        _require_text("quote_mint", self.quote_mint)
        _require_non_negative_int(
            "action_observed_at_unix_ms", self.action_observed_at_unix_ms
        )
        _require_positive_finite(
            "position_base_quantity", self.position_base_quantity
        )
        _require_positive_finite(
            "position_cost_basis_quote", self.position_cost_basis_quote
        )
        _require_positive_int("horizon_ms", self.horizon_ms)
        if not isinstance(self.horizon_complete, bool):
            raise CounterfactualLabelError("horizon_complete must be bool")

        horizon_end = self.action_observed_at_unix_ms + self.horizon_ms
        if self.sell_now is not None:
            _validate_trade_for_context(
                "sell_now",
                self.sell_now,
                TradeSide.SELL,
                self.position_base_quantity,
            )
            if self.sell_now.observed_at_unix_ms != self.action_observed_at_unix_ms:
                raise CounterfactualLabelError(
                    "sell_now evidence must be observed at the action timestamp"
                )

        if self.hold_exit is not None:
            _validate_trade_for_context(
                "hold_exit",
                self.hold_exit,
                TradeSide.SELL,
                self.position_base_quantity,
            )
            if not (
                self.action_observed_at_unix_ms
                < self.hold_exit.observed_at_unix_ms
                <= horizon_end
            ):
                raise CounterfactualLabelError(
                    "hold_exit evidence must be after the action and within the horizon"
                )

        if self.reduce_quantity is None:
            if self.reduce_now is not None:
                raise CounterfactualLabelError(
                    "reduce_now evidence requires an explicit reduce_quantity"
                )
            return

        _require_positive_finite("reduce_quantity", self.reduce_quantity)
        if self.reduce_quantity > self.position_base_quantity:
            raise CounterfactualLabelError(
                "reduce_quantity cannot exceed the open position quantity"
            )
        if self.reduce_now is not None:
            _validate_trade_for_context(
                "reduce_now",
                self.reduce_now,
                TradeSide.SELL,
                self.reduce_quantity,
            )
            if self.reduce_now.observed_at_unix_ms != self.action_observed_at_unix_ms:
                raise CounterfactualLabelError(
                    "reduce_now evidence must be observed at the action timestamp"
                )


@dataclass(frozen=True, slots=True)
class CounterfactualActionOutcome:
    label_version: int
    decision_id: str
    mint: str
    quote_mint: str
    action: CounterfactualAction
    alternative_id: str | None
    action_observed_at_unix_ms: int
    horizon_ms: int
    delay_ms: int
    base_quantity: float
    execution_status: ExecutionStatus
    entry_total_quote: float | None
    exit_net_quote: float | None
    net_pnl_quote: float | None
    return_bps: float | None
    entry_evidence_id: str | None
    exit_evidence_id: str | None
    position_cost_basis_quote: float | None = None
    realized_cost_basis_quote: float | None = None
    remaining_base_quantity: float | None = None
    remaining_cost_basis_quote: float | None = None
    entry_quote_savings_vs_buy_now: float | None = None
    return_bps_delta_vs_buy_now: float | None = None


@dataclass(frozen=True, slots=True)
class CounterfactualOutcomeSet:
    outcomes: tuple[CounterfactualActionOutcome, ...]
    fingerprint_sha256: str

    def __iter__(self) -> Iterator[CounterfactualActionOutcome]:
        return iter(self.outcomes)

    def __len__(self) -> int:
        return len(self.outcomes)

    @overload
    def __getitem__(self, index: int) -> CounterfactualActionOutcome: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[CounterfactualActionOutcome, ...]: ...

    def __getitem__(
        self, index: int | slice
    ) -> CounterfactualActionOutcome | tuple[CounterfactualActionOutcome, ...]:
        return self.outcomes[index]


def label_entry_counterfactuals(
    context: EntryCounterfactualContext,
) -> CounterfactualOutcomeSet:
    if type(context) is not EntryCounterfactualContext:
        raise CounterfactualLabelError(
            "context must be an exact EntryCounterfactualContext"
        )

    buy_now = _entry_outcome(
        context=context,
        action=CounterfactualAction.BUY_NOW,
        alternative_id=None,
        entry=context.buy_now,
        exit=context.exit_at_horizon,
        action_observed_at_unix_ms=context.decision_observed_at_unix_ms,
    )
    if buy_now.execution_status is ExecutionStatus.EXECUTABLE:
        buy_now = replace(
            buy_now,
            entry_quote_savings_vs_buy_now=0.0,
            return_bps_delta_vs_buy_now=0.0,
        )

    outcomes = [
        buy_now,
        CounterfactualActionOutcome(
            label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
            decision_id=context.decision_id,
            mint=context.mint,
            quote_mint=context.quote_mint,
            action=CounterfactualAction.SKIP,
            alternative_id=None,
            action_observed_at_unix_ms=context.decision_observed_at_unix_ms,
            horizon_ms=context.horizon_ms,
            delay_ms=0,
            base_quantity=context.base_quantity,
            execution_status=ExecutionStatus.EXECUTABLE,
            entry_total_quote=None,
            exit_net_quote=None,
            net_pnl_quote=0.0,
            return_bps=0.0,
            entry_evidence_id=None,
            exit_evidence_id=None,
        ),
    ]

    for alternative in context.delayed_entries:
        delayed = _entry_outcome(
            context=context,
            action=CounterfactualAction.DELAY_ENTRY,
            alternative_id=alternative.alternative_id,
            entry=alternative.entry,
            exit=alternative.exit,
            action_observed_at_unix_ms=alternative.entry.observed_at_unix_ms,
        )
        if (
            buy_now.execution_status is ExecutionStatus.EXECUTABLE
            and delayed.execution_status is ExecutionStatus.EXECUTABLE
        ):
            assert buy_now.entry_total_quote is not None
            assert buy_now.return_bps is not None
            assert delayed.entry_total_quote is not None
            assert delayed.return_bps is not None
            delayed = replace(
                delayed,
                entry_quote_savings_vs_buy_now=(
                    buy_now.entry_total_quote - delayed.entry_total_quote
                ),
                return_bps_delta_vs_buy_now=(
                    delayed.return_bps - buy_now.return_bps
                ),
            )
        outcomes.append(delayed)

    return _outcome_set(tuple(outcomes))


def label_open_position_counterfactuals(
    context: OpenPositionCounterfactualContext,
) -> CounterfactualOutcomeSet:
    if type(context) is not OpenPositionCounterfactualContext:
        raise CounterfactualLabelError(
            "context must be an exact OpenPositionCounterfactualContext"
        )

    outcomes = [_hold_outcome(context)]
    if context.reduce_quantity is not None:
        outcomes.append(_reduce_outcome(context))
    outcomes.append(_sell_now_outcome(context))
    return _outcome_set(tuple(outcomes))


def _entry_outcome(
    *,
    context: EntryCounterfactualContext,
    action: CounterfactualAction,
    alternative_id: str | None,
    entry: ExecutableTradeEvidence | None,
    exit: ExecutableTradeEvidence | None,
    action_observed_at_unix_ms: int,
) -> CounterfactualActionOutcome:
    status = _path_execution_status(
        entry=entry,
        exit=exit,
        horizon_complete=context.horizon_complete,
    )
    entry_total_quote: float | None = None
    exit_net_quote: float | None = None
    net_pnl_quote: float | None = None
    return_bps: float | None = None

    if status is ExecutionStatus.EXECUTABLE:
        assert entry is not None and entry.quote_amount is not None
        assert exit is not None and exit.quote_amount is not None
        entry_total_quote = entry.quote_amount
        exit_net_quote = exit.quote_amount
        net_pnl_quote = exit_net_quote - entry_total_quote
        return_bps = (exit_net_quote / entry_total_quote - 1.0) * 10_000.0

    return CounterfactualActionOutcome(
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_id=context.decision_id,
        mint=context.mint,
        quote_mint=context.quote_mint,
        action=action,
        alternative_id=alternative_id,
        action_observed_at_unix_ms=action_observed_at_unix_ms,
        horizon_ms=context.horizon_ms,
        delay_ms=action_observed_at_unix_ms - context.decision_observed_at_unix_ms,
        base_quantity=context.base_quantity,
        execution_status=status,
        entry_total_quote=entry_total_quote,
        exit_net_quote=exit_net_quote,
        net_pnl_quote=net_pnl_quote,
        return_bps=return_bps,
        entry_evidence_id=None if entry is None else entry.evidence_id,
        exit_evidence_id=None if exit is None else exit.evidence_id,
    )


def _hold_outcome(
    context: OpenPositionCounterfactualContext,
) -> CounterfactualActionOutcome:
    status = _future_sell_status(
        context.hold_exit,
        horizon_complete=context.horizon_complete,
    )
    exit_net_quote: float | None = None
    net_pnl_quote: float | None = None
    return_bps: float | None = None
    if status is ExecutionStatus.EXECUTABLE:
        assert context.hold_exit is not None
        assert context.hold_exit.quote_amount is not None
        exit_net_quote = context.hold_exit.quote_amount
        net_pnl_quote = exit_net_quote - context.position_cost_basis_quote
        return_bps = (
            exit_net_quote / context.position_cost_basis_quote - 1.0
        ) * 10_000.0

    return CounterfactualActionOutcome(
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_id=context.decision_id,
        mint=context.mint,
        quote_mint=context.quote_mint,
        action=CounterfactualAction.HOLD,
        alternative_id=None,
        action_observed_at_unix_ms=context.action_observed_at_unix_ms,
        horizon_ms=context.horizon_ms,
        delay_ms=0,
        base_quantity=context.position_base_quantity,
        execution_status=status,
        entry_total_quote=None,
        exit_net_quote=exit_net_quote,
        net_pnl_quote=net_pnl_quote,
        return_bps=return_bps,
        entry_evidence_id=None,
        exit_evidence_id=(
            None if context.hold_exit is None else context.hold_exit.evidence_id
        ),
        position_cost_basis_quote=context.position_cost_basis_quote,
    )


def _sell_now_outcome(
    context: OpenPositionCounterfactualContext,
) -> CounterfactualActionOutcome:
    status = _immediate_sell_status(context.sell_now)
    exit_net_quote: float | None = None
    net_pnl_quote: float | None = None
    return_bps: float | None = None
    if status is ExecutionStatus.EXECUTABLE:
        assert context.sell_now is not None
        assert context.sell_now.quote_amount is not None
        exit_net_quote = context.sell_now.quote_amount
        net_pnl_quote = exit_net_quote - context.position_cost_basis_quote
        return_bps = (
            exit_net_quote / context.position_cost_basis_quote - 1.0
        ) * 10_000.0

    return CounterfactualActionOutcome(
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_id=context.decision_id,
        mint=context.mint,
        quote_mint=context.quote_mint,
        action=CounterfactualAction.SELL_NOW,
        alternative_id=None,
        action_observed_at_unix_ms=context.action_observed_at_unix_ms,
        horizon_ms=context.horizon_ms,
        delay_ms=0,
        base_quantity=context.position_base_quantity,
        execution_status=status,
        entry_total_quote=None,
        exit_net_quote=exit_net_quote,
        net_pnl_quote=net_pnl_quote,
        return_bps=return_bps,
        entry_evidence_id=None,
        exit_evidence_id=(
            None if context.sell_now is None else context.sell_now.evidence_id
        ),
        position_cost_basis_quote=context.position_cost_basis_quote,
    )


def _reduce_outcome(
    context: OpenPositionCounterfactualContext,
) -> CounterfactualActionOutcome:
    assert context.reduce_quantity is not None
    status = _immediate_sell_status(context.reduce_now)
    realized_cost_basis_quote: float | None = None
    remaining_base_quantity: float | None = None
    remaining_cost_basis_quote: float | None = None
    exit_net_quote: float | None = None
    net_pnl_quote: float | None = None
    return_bps: float | None = None

    if status is ExecutionStatus.EXECUTABLE:
        assert context.reduce_now is not None
        assert context.reduce_now.quote_amount is not None
        realized_cost_basis_quote = (
            context.position_cost_basis_quote
            * context.reduce_quantity
            / context.position_base_quantity
        )
        remaining_base_quantity = (
            context.position_base_quantity - context.reduce_quantity
        )
        remaining_cost_basis_quote = (
            context.position_cost_basis_quote - realized_cost_basis_quote
        )
        exit_net_quote = context.reduce_now.quote_amount
        net_pnl_quote = exit_net_quote - realized_cost_basis_quote
        return_bps = (
            exit_net_quote / realized_cost_basis_quote - 1.0
        ) * 10_000.0

    return CounterfactualActionOutcome(
        label_version=COUNTERFACTUAL_ACTION_LABEL_VERSION,
        decision_id=context.decision_id,
        mint=context.mint,
        quote_mint=context.quote_mint,
        action=CounterfactualAction.REDUCE_NOW,
        alternative_id=None,
        action_observed_at_unix_ms=context.action_observed_at_unix_ms,
        horizon_ms=context.horizon_ms,
        delay_ms=0,
        base_quantity=context.reduce_quantity,
        execution_status=status,
        entry_total_quote=None,
        exit_net_quote=exit_net_quote,
        net_pnl_quote=net_pnl_quote,
        return_bps=return_bps,
        entry_evidence_id=None,
        exit_evidence_id=(
            None if context.reduce_now is None else context.reduce_now.evidence_id
        ),
        position_cost_basis_quote=context.position_cost_basis_quote,
        realized_cost_basis_quote=realized_cost_basis_quote,
        remaining_base_quantity=remaining_base_quantity,
        remaining_cost_basis_quote=remaining_cost_basis_quote,
    )


def _path_execution_status(
    *,
    entry: ExecutableTradeEvidence | None,
    exit: ExecutableTradeEvidence | None,
    horizon_complete: bool,
) -> ExecutionStatus:
    present = tuple(value for value in (entry, exit) if value is not None)
    if any(value.status is ExecutionStatus.NOT_EXECUTABLE for value in present):
        return ExecutionStatus.NOT_EXECUTABLE
    if not horizon_complete or entry is None or exit is None:
        return ExecutionStatus.UNKNOWN
    if entry.status is ExecutionStatus.UNKNOWN or exit.status is ExecutionStatus.UNKNOWN:
        return ExecutionStatus.UNKNOWN
    return ExecutionStatus.EXECUTABLE


def _immediate_sell_status(
    evidence: ExecutableTradeEvidence | None,
) -> ExecutionStatus:
    if evidence is None or evidence.status is ExecutionStatus.UNKNOWN:
        return ExecutionStatus.UNKNOWN
    return evidence.status


def _future_sell_status(
    evidence: ExecutableTradeEvidence | None,
    *,
    horizon_complete: bool,
) -> ExecutionStatus:
    if evidence is not None and evidence.status is ExecutionStatus.NOT_EXECUTABLE:
        return ExecutionStatus.NOT_EXECUTABLE
    if not horizon_complete or evidence is None:
        return ExecutionStatus.UNKNOWN
    return evidence.status


def _outcome_set(
    outcomes: tuple[CounterfactualActionOutcome, ...],
) -> CounterfactualOutcomeSet:
    return CounterfactualOutcomeSet(
        outcomes=outcomes,
        fingerprint_sha256=_fingerprint_outcomes(outcomes),
    )


def _fingerprint_outcomes(
    outcomes: tuple[CounterfactualActionOutcome, ...],
) -> str:
    payload = [asdict(outcome) for outcome in outcomes]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_trade_for_context(
    name: str,
    value: ExecutableTradeEvidence,
    side: TradeSide,
    base_quantity: float,
) -> None:
    if type(value) is not ExecutableTradeEvidence:
        raise CounterfactualLabelError(
            f"{name} must be exact ExecutableTradeEvidence"
        )
    if value.side is not side:
        raise CounterfactualLabelError(f"{name} has the wrong trade side")
    if value.base_quantity != base_quantity:
        raise CounterfactualLabelError(
            f"{name} must use the requested base quantity"
        )


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CounterfactualLabelError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CounterfactualLabelError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise CounterfactualLabelError(f"{name} must be positive")


def _require_positive_finite(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CounterfactualLabelError(f"{name} must be a finite positive number")
    if not math.isfinite(value) or value <= 0:
        raise CounterfactualLabelError(f"{name} must be a finite positive number")
