from __future__ import annotations

from dataclasses import dataclass
import math
import string

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide


PAPER_EVALUATION_SCHEMA_VERSION = "e11-paper-evaluation-v1"


@dataclass(frozen=True, slots=True)
class PaperEntryProvenance:
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    intent_idempotency_key: str
    mint: str
    decision_as_of_unix_ms: int
    setup_name: str
    market_regime: MarketRegime
    score_policy_version: str
    decision_policy_version: str
    paper_execution_policy_version: str

    def __post_init__(self) -> None:
        _validate_attribution(self)
        for name in (
            "intent_idempotency_key",
            "mint",
            "setup_name",
            "score_policy_version",
            "decision_policy_version",
            "paper_execution_policy_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_non_negative_int("decision_as_of_unix_ms", self.decision_as_of_unix_ms)
        if type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be an exact MarketRegime")


@dataclass(frozen=True, slots=True)
class PaperPositionExecutionEvidence:
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    position_id: str
    ledger_sequence: int
    intent_idempotency_key: str
    mint: str
    side: TradeSide
    execution_state: PaperExecutionState
    ledger_reason_code: PaperLedgerReasonCode
    booked_at_unix_ms: int
    evaluated_at_unix_ms: int
    requested_notional_usd: float
    explicit_cost_usd: float
    filled_notional_usd: float | None
    filled_quantity: float | None
    reference_price_usd: float | None
    execution_price_usd: float | None
    signed_slippage_usd: float | None
    quote_provider: str | None
    executed_at_unix_ms: int | None

    def __post_init__(self) -> None:
        _validate_attribution(self)
        for name in ("position_id", "intent_idempotency_key", "mint"):
            _require_non_empty_string(name, getattr(self, name))
        _require_positive_int("ledger_sequence", self.ledger_sequence)
        if type(self.side) is not TradeSide:
            raise ValueError("side must be an exact TradeSide")
        if self.execution_state not in (
            PaperExecutionState.FAILED,
            PaperExecutionState.PARTIAL,
            PaperExecutionState.FILLED,
        ):
            raise ValueError("execution_state must be terminal FAILED/PARTIAL/FILLED")
        if type(self.ledger_reason_code) is not PaperLedgerReasonCode:
            raise ValueError("ledger_reason_code must be an exact PaperLedgerReasonCode")
        _require_non_negative_int("booked_at_unix_ms", self.booked_at_unix_ms)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)

        fill_values = (
            self.filled_notional_usd,
            self.filled_quantity,
            self.reference_price_usd,
            self.execution_price_usd,
            self.signed_slippage_usd,
            self.quote_provider,
            self.executed_at_unix_ms,
        )
        fill_present = tuple(value is not None for value in fill_values)
        if any(fill_present) and not all(fill_present):
            raise ValueError("fill evidence fields must be all present or all absent")

        if self.execution_state is PaperExecutionState.FAILED:
            if any(fill_present):
                raise ValueError("FAILED execution evidence cannot contain fill fields")
            return

        if not all(fill_present):
            raise ValueError("PARTIAL/FILLED execution evidence requires complete fill fields")
        assert self.filled_notional_usd is not None
        assert self.filled_quantity is not None
        assert self.reference_price_usd is not None
        assert self.execution_price_usd is not None
        assert self.signed_slippage_usd is not None
        assert self.quote_provider is not None
        assert self.executed_at_unix_ms is not None
        _require_positive_finite("filled_notional_usd", self.filled_notional_usd)
        _require_positive_finite("filled_quantity", self.filled_quantity)
        _require_positive_finite("reference_price_usd", self.reference_price_usd)
        _require_positive_finite("execution_price_usd", self.execution_price_usd)
        _require_finite("signed_slippage_usd", self.signed_slippage_usd)
        _require_non_empty_string("quote_provider", self.quote_provider)
        _require_non_negative_int("executed_at_unix_ms", self.executed_at_unix_ms)


@dataclass(frozen=True, slots=True)
class PaperClosedPositionEvidence:
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    position_id: str
    mint: str
    opened_at_unix_ms: int
    closed_at_unix_ms: int
    realized_pnl_usd: float
    accumulated_costs_usd: float
    buy_fill_count: int
    sell_fill_count: int
    closing_ledger_sequence: int

    def __post_init__(self) -> None:
        _validate_attribution(self)
        _require_non_empty_string("position_id", self.position_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("opened_at_unix_ms", self.opened_at_unix_ms)
        _require_non_negative_int("closed_at_unix_ms", self.closed_at_unix_ms)
        if self.closed_at_unix_ms < self.opened_at_unix_ms:
            raise ValueError("closed_at_unix_ms cannot precede opened_at_unix_ms")
        _require_finite("realized_pnl_usd", self.realized_pnl_usd)
        _require_non_negative_finite("accumulated_costs_usd", self.accumulated_costs_usd)
        _require_positive_int("buy_fill_count", self.buy_fill_count)
        _require_positive_int("sell_fill_count", self.sell_fill_count)
        _require_positive_int("closing_ledger_sequence", self.closing_ledger_sequence)


@dataclass(frozen=True, slots=True)
class PaperOrphanCostEvidence:
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    intent_idempotency_key: str
    mint: str
    explicit_cost_usd: float
    evaluated_at_unix_ms: int

    def __post_init__(self) -> None:
        _validate_attribution(self)
        _require_non_empty_string("intent_idempotency_key", self.intent_idempotency_key)
        _require_non_empty_string("mint", self.mint)
        _require_positive_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)


@dataclass(frozen=True, slots=True)
class PaperEvaluationCapture:
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    entry_provenance: tuple[PaperEntryProvenance, ...]
    executions: tuple[PaperPositionExecutionEvidence, ...]
    closures: tuple[PaperClosedPositionEvidence, ...]
    orphan_costs: tuple[PaperOrphanCostEvidence, ...]

    def __post_init__(self) -> None:
        _validate_attribution(self)
        _require_exact_tuple("entry_provenance", self.entry_provenance, PaperEntryProvenance)
        _require_exact_tuple("executions", self.executions, PaperPositionExecutionEvidence)
        _require_exact_tuple("closures", self.closures, PaperClosedPositionEvidence)
        _require_exact_tuple("orphan_costs", self.orphan_costs, PaperOrphanCostEvidence)
        _validate_nested_attribution(self)
        _validate_collection_identities_and_order(
            self.entry_provenance,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            lambda value: (
                value.paper_run_id,
                value.decision_as_of_unix_ms,
                value.intent_idempotency_key,
            ),
            "entry provenance",
        )
        _validate_collection_identities_and_order(
            self.executions,
            lambda value: (value.paper_run_id, value.ledger_sequence),
            lambda value: (value.paper_run_id, value.ledger_sequence),
            "execution evidence",
        )
        _validate_collection_identities_and_order(
            self.closures,
            lambda value: (value.paper_run_id, value.position_id),
            lambda value: (value.paper_run_id, value.closed_at_unix_ms, value.position_id),
            "closure evidence",
        )
        _validate_collection_identities_and_order(
            self.orphan_costs,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            lambda value: (
                value.paper_run_id,
                value.evaluated_at_unix_ms,
                value.intent_idempotency_key,
            ),
            "orphan cost evidence",
        )


@dataclass(frozen=True, slots=True)
class PaperEvaluationLedger:
    schema_version: str
    entry_provenance: tuple[PaperEntryProvenance, ...]
    executions: tuple[PaperPositionExecutionEvidence, ...]
    closures: tuple[PaperClosedPositionEvidence, ...]
    orphan_costs: tuple[PaperOrphanCostEvidence, ...]
    document_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != PAPER_EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {PAPER_EVALUATION_SCHEMA_VERSION}"
            )
        _require_sha256("document_fingerprint_sha256", self.document_fingerprint_sha256)
        _require_exact_tuple("entry_provenance", self.entry_provenance, PaperEntryProvenance)
        _require_exact_tuple("executions", self.executions, PaperPositionExecutionEvidence)
        _require_exact_tuple("closures", self.closures, PaperClosedPositionEvidence)
        _require_exact_tuple("orphan_costs", self.orphan_costs, PaperOrphanCostEvidence)
        _validate_collection_identities_and_order(
            self.entry_provenance,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            lambda value: (
                value.paper_run_id,
                value.decision_as_of_unix_ms,
                value.intent_idempotency_key,
            ),
            "entry provenance",
        )
        _validate_collection_identities_and_order(
            self.executions,
            lambda value: (value.paper_run_id, value.ledger_sequence),
            lambda value: (value.paper_run_id, value.ledger_sequence),
            "execution evidence",
        )
        _validate_collection_identities_and_order(
            self.closures,
            lambda value: (value.paper_run_id, value.position_id),
            lambda value: (value.paper_run_id, value.closed_at_unix_ms, value.position_id),
            "closure evidence",
        )
        _validate_collection_identities_and_order(
            self.orphan_costs,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            lambda value: (
                value.paper_run_id,
                value.evaluated_at_unix_ms,
                value.intent_idempotency_key,
            ),
            "orphan cost evidence",
        )


def _validate_attribution(value: object) -> None:
    _require_non_empty_string("paper_run_id", getattr(value, "paper_run_id"))
    _require_non_empty_string("candidate_version", getattr(value, "candidate_version"))
    _require_sha256(
        "candidate_fingerprint_sha256",
        getattr(value, "candidate_fingerprint_sha256"),
    )
    _require_non_empty_string("strategy_version", getattr(value, "strategy_version"))


def _validate_nested_attribution(capture: PaperEvaluationCapture) -> None:
    expected = (
        capture.paper_run_id,
        capture.candidate_version,
        capture.candidate_fingerprint_sha256,
        capture.strategy_version,
    )
    for collection in (
        capture.entry_provenance,
        capture.executions,
        capture.closures,
        capture.orphan_costs,
    ):
        for value in collection:
            actual = (
                value.paper_run_id,
                value.candidate_version,
                value.candidate_fingerprint_sha256,
                value.strategy_version,
            )
            if actual != expected:
                raise ValueError("capture evidence attribution must match capture identity")


def _validate_collection_identities_and_order(
    values: tuple[object, ...],
    identity_key,
    order_key,
    label: str,
) -> None:
    identities = tuple(identity_key(value) for value in values)
    if len(identities) != len(set(identities)):
        raise ValueError(f"{label} identities must be unique")
    ordered = tuple(sorted(values, key=order_key))
    if values != ordered:
        raise ValueError(f"{label} must be in canonical order")


def _require_exact_tuple(name: str, values: object, expected_type: type) -> None:
    if not isinstance(values, tuple) or any(type(value) is not expected_type for value in values):
        raise ValueError(f"{name} must be a tuple of exact {expected_type.__name__} values")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
