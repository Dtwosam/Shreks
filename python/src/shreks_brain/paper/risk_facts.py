from __future__ import annotations

from dataclasses import dataclass
import math

from .ledger_models import PaperLedger, PaperPositionState


@dataclass(frozen=True, slots=True)
class PaperRiskAccountingFacts:
    open_position_count: int
    aggregate_open_risk_usd: float
    daily_realized_pnl_usd: float
    rolling_drawdown_pct: float | None
    consecutive_losses: int
    last_loss_at_unix_ms: int | None

    def __post_init__(self) -> None:
        _require_non_negative_int(
            "open_position_count",
            self.open_position_count,
        )
        _require_non_negative_finite(
            "aggregate_open_risk_usd",
            self.aggregate_open_risk_usd,
        )
        _require_finite(
            "daily_realized_pnl_usd",
            self.daily_realized_pnl_usd,
        )
        if self.rolling_drawdown_pct is not None:
            _require_finite(
                "rolling_drawdown_pct",
                self.rolling_drawdown_pct,
            )
            if not 0.0 <= self.rolling_drawdown_pct <= 100.0:
                raise ValueError(
                    "rolling_drawdown_pct must be within [0, 100]"
                )
        _require_non_negative_int(
            "consecutive_losses",
            self.consecutive_losses,
        )
        if self.last_loss_at_unix_ms is not None:
            _require_non_negative_int(
                "last_loss_at_unix_ms",
                self.last_loss_at_unix_ms,
            )
        if self.consecutive_losses == 0:
            if self.last_loss_at_unix_ms is not None:
                raise ValueError(
                    "zero consecutive losses cannot carry last_loss_at_unix_ms"
                )
        elif self.last_loss_at_unix_ms is None:
            raise ValueError(
                "positive consecutive losses require last_loss_at_unix_ms"
            )


def derive_paper_risk_accounting_facts(
    ledger: PaperLedger,
    *,
    day_started_at_unix_ms: int,
) -> PaperRiskAccountingFacts:
    if type(ledger) is not PaperLedger:
        raise ValueError("ledger must be exact PaperLedger")
    _require_non_negative_int(
        "day_started_at_unix_ms",
        day_started_at_unix_ms,
    )

    open_positions = tuple(
        position
        for position in ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    aggregate_open_risk = sum(
        position.open_cost_basis_usd for position in open_positions
    )
    daily_realized = sum(
        entry.realized_pnl_delta_usd
        for entry in ledger.entries
        if entry.booked_at_unix_ms >= day_started_at_unix_ms
    )
    rolling_drawdown = _rolling_drawdown_pct(ledger, open_positions)
    consecutive_losses, last_loss_at = _loss_streak(ledger)

    return PaperRiskAccountingFacts(
        open_position_count=len(open_positions),
        aggregate_open_risk_usd=aggregate_open_risk,
        daily_realized_pnl_usd=daily_realized,
        rolling_drawdown_pct=rolling_drawdown,
        consecutive_losses=consecutive_losses,
        last_loss_at_unix_ms=last_loss_at,
    )


def _rolling_drawdown_pct(
    ledger: PaperLedger,
    open_positions: tuple,
) -> float | None:
    if any(
        position.unrealized_pnl_usd is None
        for position in open_positions
    ):
        return None

    equity = ledger.starting_cash_usd
    points = [equity]
    for entry in ledger.entries:
        equity += entry.realized_pnl_delta_usd
        points.append(equity)

    current_unrealized = sum(
        position.unrealized_pnl_usd or 0.0
        for position in open_positions
    )
    points.append(equity + current_unrealized)

    peak = points[0]
    maximum = 0.0
    for value in points:
        if value > peak:
            peak = value
        if peak <= 0.0:
            return None
        drawdown = (peak - value) / peak * 100.0
        maximum = max(maximum, drawdown)

    if not math.isfinite(maximum):
        return None
    return maximum


def _loss_streak(ledger: PaperLedger) -> tuple[int, int | None]:
    closed = sorted(
        (
            position
            for position in ledger.positions
            if position.state is PaperPositionState.CLOSED
        ),
        key=lambda position: (
            (
                position.closed_at_unix_ms
                if position.closed_at_unix_ms is not None
                else -1
            ),
            position.position_id,
        ),
    )

    streak = 0
    last_loss_at: int | None = None
    for position in reversed(closed):
        if position.realized_pnl_usd >= 0.0:
            break
        if last_loss_at is None:
            last_loss_at = position.closed_at_unix_ms
        streak += 1
    return streak, last_loss_at


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")
