from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.risk import TradeSide


_ARITH_REL_TOL = 1e-12
_ARITH_ABS_TOL = 1e-9


class PaperQuoteState(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED_AFTER_SUBMISSION = "FAILED_AFTER_SUBMISSION"


class PaperExecutionState(StrEnum):
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"


class PaperExecutionReasonCode(StrEnum):
    INTENT_MODE_NOT_PAPER = "INTENT_MODE_NOT_PAPER"
    DUPLICATE_INTENT = "DUPLICATE_INTENT"
    EVALUATION_BEFORE_INTENT = "EVALUATION_BEFORE_INTENT"
    QUOTE_AFTER_EVALUATION = "QUOTE_AFTER_EVALUATION"
    QUOTE_MINT_MISMATCH = "QUOTE_MINT_MISMATCH"
    LATENCY_PENDING = "LATENCY_PENDING"
    QUOTE_PENDING = "QUOTE_PENDING"
    QUOTE_BEFORE_LATENCY = "QUOTE_BEFORE_LATENCY"
    QUOTE_WINDOW_EXPIRED = "QUOTE_WINDOW_EXPIRED"
    QUOTE_TOO_LATE = "QUOTE_TOO_LATE"
    ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"
    SIMULATED_SUBMISSION_FAILED = "SIMULATED_SUBMISSION_FAILED"
    REFERENCE_PRICE_UNKNOWN = "REFERENCE_PRICE_UNKNOWN"
    EXECUTION_PRICE_UNKNOWN = "EXECUTION_PRICE_UNKNOWN"
    QUOTED_NOTIONAL_UNKNOWN = "QUOTED_NOTIONAL_UNKNOWN"
    AVAILABLE_NOTIONAL_UNKNOWN = "AVAILABLE_NOTIONAL_UNKNOWN"
    NO_EXECUTABLE_NOTIONAL = "NO_EXECUTABLE_NOTIONAL"
    PARTIAL_FILL_DISABLED = "PARTIAL_FILL_DISABLED"
    PARTIAL_FILL_TOO_SMALL = "PARTIAL_FILL_TOO_SMALL"
    SLIPPAGE_EXCEEDS_INTENT = "SLIPPAGE_EXCEEDS_INTENT"
    FILL_PARTIAL = "FILL_PARTIAL"
    FILL_COMPLETE = "FILL_COMPLETE"


@dataclass(frozen=True, slots=True)
class PaperFillPolicy:
    version: str
    assumed_latency_ms: int
    max_quote_lag_ms: int
    swap_fee_bps: int
    network_fee_usd: float
    allow_partial_fills: bool
    min_partial_fill_fraction: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_non_negative_int("assumed_latency_ms", self.assumed_latency_ms)
        _require_non_negative_int("max_quote_lag_ms", self.max_quote_lag_ms)
        _require_bps("swap_fee_bps", self.swap_fee_bps)
        _require_non_negative_finite("network_fee_usd", self.network_fee_usd)
        _require_bool("allow_partial_fills", self.allow_partial_fills)
        _require_fraction_open_zero("min_partial_fill_fraction", self.min_partial_fill_fraction)


@dataclass(frozen=True, slots=True)
class PaperQuote:
    provider: str
    mint: str
    observed_at_unix_ms: int
    state: PaperQuoteState
    reference_price_usd: float | None
    execution_price_usd: float | None
    quoted_notional_usd: float | None
    available_notional_usd: float | None

    def __post_init__(self) -> None:
        _require_non_empty_string("provider", self.provider)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if not isinstance(self.state, PaperQuoteState):
            raise ValueError("state must be a PaperQuoteState")
        _require_optional_positive_finite("reference_price_usd", self.reference_price_usd)
        _require_optional_positive_finite("execution_price_usd", self.execution_price_usd)
        _require_optional_non_negative_finite("quoted_notional_usd", self.quoted_notional_usd)
        _require_optional_non_negative_finite("available_notional_usd", self.available_notional_usd)


@dataclass(frozen=True, slots=True)
class PaperExecutionContext:
    evaluated_at_unix_ms: int
    processed_intent_keys: frozenset[str]
    quote: PaperQuote | None

    def __post_init__(self) -> None:
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if not isinstance(self.processed_intent_keys, frozenset):
            raise ValueError("processed_intent_keys must be a frozenset")
        if not all(isinstance(key, str) and key.strip() for key in self.processed_intent_keys):
            raise ValueError("processed_intent_keys must contain non-empty strings")
        if self.quote is not None and not isinstance(self.quote, PaperQuote):
            raise ValueError("quote must be a PaperQuote or None")


@dataclass(frozen=True, slots=True)
class PaperExecutionFinding:
    code: PaperExecutionReasonCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, PaperExecutionReasonCode):
            raise ValueError("code must be a PaperExecutionReasonCode")
        _require_non_empty_string("message", self.message)


@dataclass(frozen=True, slots=True)
class PaperFill:
    intent_idempotency_key: str
    mint: str
    side: TradeSide
    state: PaperExecutionState
    requested_notional_usd: float
    filled_notional_usd: float
    unfilled_notional_usd: float
    quantity: float
    reference_price_usd: float
    execution_price_usd: float
    signed_slippage_bps: float
    signed_slippage_usd: float
    swap_fee_usd: float
    network_fee_usd: float
    explicit_cost_usd: float
    net_cash_flow_usd: float
    quote_provider: str
    executed_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_non_empty_string("intent_idempotency_key", self.intent_idempotency_key)
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.side, TradeSide):
            raise ValueError("side must be a TradeSide")
        if self.state not in (PaperExecutionState.PARTIAL, PaperExecutionState.FILLED):
            raise ValueError("state must be PARTIAL or FILLED for PaperFill")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        _require_positive_finite("filled_notional_usd", self.filled_notional_usd)
        _require_non_negative_finite("unfilled_notional_usd", self.unfilled_notional_usd)
        if self.unfilled_notional_usd >= self.requested_notional_usd:
            raise ValueError("unfilled_notional_usd must be below requested_notional_usd")
        _require_positive_finite("quantity", self.quantity)
        _require_positive_finite("reference_price_usd", self.reference_price_usd)
        _require_positive_finite("execution_price_usd", self.execution_price_usd)
        _require_finite("signed_slippage_bps", self.signed_slippage_bps)
        _require_finite("signed_slippage_usd", self.signed_slippage_usd)
        _require_non_negative_finite("swap_fee_usd", self.swap_fee_usd)
        _require_non_negative_finite("network_fee_usd", self.network_fee_usd)
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_finite("net_cash_flow_usd", self.net_cash_flow_usd)
        _require_non_empty_string("quote_provider", self.quote_provider)
        _require_non_negative_int("executed_at_unix_ms", self.executed_at_unix_ms)

        _require_close(
            "filled_notional_usd + unfilled_notional_usd",
            self.filled_notional_usd + self.unfilled_notional_usd,
            self.requested_notional_usd,
        )
        _require_close(
            "quantity",
            self.quantity,
            self.filled_notional_usd / self.execution_price_usd,
        )
        _require_close(
            "explicit_cost_usd",
            self.explicit_cost_usd,
            self.swap_fee_usd + self.network_fee_usd,
        )

        if self.state is PaperExecutionState.FILLED:
            if not math.isclose(
                self.unfilled_notional_usd,
                0.0,
                rel_tol=_ARITH_REL_TOL,
                abs_tol=_ARITH_ABS_TOL,
            ):
                raise ValueError("FILLED requires zero unfilled_notional_usd")
        elif self.unfilled_notional_usd <= 0.0:
            raise ValueError("PARTIAL requires positive unfilled_notional_usd")

        if self.side is TradeSide.BUY:
            expected_cash = -(self.filled_notional_usd + self.explicit_cost_usd)
        else:
            expected_cash = self.filled_notional_usd - self.explicit_cost_usd
        _require_close("net_cash_flow_usd", self.net_cash_flow_usd, expected_cash)


@dataclass(frozen=True, slots=True)
class PaperExecutionResult:
    policy_version: str
    intent_idempotency_key: str
    mint: str
    side: TradeSide
    state: PaperExecutionState
    requested_notional_usd: float
    evaluated_at_unix_ms: int
    quote_observed_at_unix_ms: int | None
    swap_fee_usd: float
    network_fee_usd: float
    explicit_cost_usd: float
    net_cash_flow_usd: float
    findings: tuple[PaperExecutionFinding, ...]
    fill: PaperFill | None

    def __post_init__(self) -> None:
        _require_non_empty_string("policy_version", self.policy_version)
        _require_non_empty_string("intent_idempotency_key", self.intent_idempotency_key)
        _require_non_empty_string("mint", self.mint)
        if not isinstance(self.side, TradeSide):
            raise ValueError("side must be a TradeSide")
        if not isinstance(self.state, PaperExecutionState):
            raise ValueError("state must be a PaperExecutionState")
        _require_positive_finite("requested_notional_usd", self.requested_notional_usd)
        _require_non_negative_int("evaluated_at_unix_ms", self.evaluated_at_unix_ms)
        if self.quote_observed_at_unix_ms is not None:
            _require_non_negative_int(
                "quote_observed_at_unix_ms", self.quote_observed_at_unix_ms
            )
        _require_non_negative_finite("swap_fee_usd", self.swap_fee_usd)
        _require_non_negative_finite("network_fee_usd", self.network_fee_usd)
        _require_non_negative_finite("explicit_cost_usd", self.explicit_cost_usd)
        _require_finite("net_cash_flow_usd", self.net_cash_flow_usd)
        if not isinstance(self.findings, tuple) or len(self.findings) != 1:
            raise ValueError("findings must contain exactly one PaperExecutionFinding")
        if not isinstance(self.findings[0], PaperExecutionFinding):
            raise ValueError("findings must contain only PaperExecutionFinding values")
        if self.fill is not None and not isinstance(self.fill, PaperFill):
            raise ValueError("fill must be a PaperFill or None")
        _require_close(
            "explicit_cost_usd",
            self.explicit_cost_usd,
            self.swap_fee_usd + self.network_fee_usd,
        )

        if self.state is PaperExecutionState.DEFERRED:
            if self.fill is not None:
                raise ValueError("DEFERRED results cannot carry a fill")
            _require_zero("swap_fee_usd", self.swap_fee_usd)
            _require_zero("network_fee_usd", self.network_fee_usd)
            _require_zero("explicit_cost_usd", self.explicit_cost_usd)
            _require_zero("net_cash_flow_usd", self.net_cash_flow_usd)
            return

        if self.state is PaperExecutionState.FAILED:
            if self.fill is not None:
                raise ValueError("FAILED results cannot carry a fill")
            _require_zero("swap_fee_usd", self.swap_fee_usd)
            if self.findings[0].code is PaperExecutionReasonCode.SIMULATED_SUBMISSION_FAILED:
                _require_close(
                    "explicit_cost_usd", self.explicit_cost_usd, self.network_fee_usd
                )
                _require_close(
                    "net_cash_flow_usd", self.net_cash_flow_usd, -self.network_fee_usd
                )
            else:
                _require_zero("network_fee_usd", self.network_fee_usd)
                _require_zero("explicit_cost_usd", self.explicit_cost_usd)
                _require_zero("net_cash_flow_usd", self.net_cash_flow_usd)
            return

        if self.fill is None:
            raise ValueError("PARTIAL/FILLED results require a fill")
        if self.fill.state is not self.state:
            raise ValueError("result state must match fill state")
        if self.fill.intent_idempotency_key != self.intent_idempotency_key:
            raise ValueError("fill intent_idempotency_key must match result")
        if self.fill.mint != self.mint:
            raise ValueError("fill mint must match result")
        if self.fill.side is not self.side:
            raise ValueError("fill side must match result")
        if not math.isclose(
            self.fill.requested_notional_usd,
            self.requested_notional_usd,
            rel_tol=_ARITH_REL_TOL,
            abs_tol=_ARITH_ABS_TOL,
        ):
            raise ValueError("fill requested_notional_usd must match result")
        if self.quote_observed_at_unix_ms != self.fill.executed_at_unix_ms:
            raise ValueError("quote_observed_at_unix_ms must match fill executed_at_unix_ms")
        for name in (
            "swap_fee_usd",
            "network_fee_usd",
            "explicit_cost_usd",
            "net_cash_flow_usd",
        ):
            _require_close(name, getattr(self, name), getattr(self.fill, name))


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
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000:
        raise ValueError(f"{name} must be an integer within [0, 10000]")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be strictly positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_optional_positive_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_positive_finite(name, value)


def _require_optional_non_negative_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_finite(name, value)


def _require_fraction_open_zero(name: str, value: object) -> None:
    _require_finite(name, value)
    if value <= 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within (0, 1]")


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=_ARITH_REL_TOL,
        abs_tol=_ARITH_ABS_TOL,
    ):
        raise ValueError(f"{name} is inconsistent")


def _require_zero(name: str, value: float) -> None:
    if not math.isclose(value, 0.0, rel_tol=_ARITH_REL_TOL, abs_tol=_ARITH_ABS_TOL):
        raise ValueError(f"{name} must be zero")
