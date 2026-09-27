from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shreks_brain.evaluation import EvaluatedTrade
from shreks_brain.fast_paper_shadow_decision_telemetry import (
    collect_fast_paper_shadow_decision_telemetry,
)
from shreks_brain.fast_paper_shadow_execution_telemetry import (
    collect_fast_paper_shadow_execution_telemetry,
)
from shreks_brain.fast_paper_shadow_outcome_telemetry import (
    collect_fast_paper_shadow_outcome_telemetry,
)
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    bootstrap_observer_paper_campaign_runtime,
)
from shreks_brain.paper import PaperLedgerEntry
from shreks_brain.telemetry import TelemetrySnapshot, decode_telemetry_snapshot

from .config import DashboardFastLaneConfig
from .models import (
    DashboardEvidenceAvailability,
    DashboardLedgerEvent,
    DashboardSnapshotSource,
    DashboardSourceConfig,
    DashboardTradeDetail,
    DashboardTradeSummary,
)


class DashboardSourceError(RuntimeError):
    """Raised when required dashboard evidence cannot be read coherently."""


@dataclass(frozen=True, slots=True)
class _DashboardContext:
    telemetry: TelemetrySnapshot
    telemetry_file_mtime_ns: int
    trades: tuple[EvaluatedTrade, ...]
    ledger_entries: tuple[PaperLedgerEntry, ...]


def load_dashboard_snapshot(
    config: DashboardSourceConfig,
    *,
    max_trades: int,
) -> DashboardSnapshotSource:
    _require_config(config)
    if isinstance(max_trades, bool) or not isinstance(max_trades, int) or max_trades <= 0:
        raise DashboardSourceError("max_trades must be a positive integer")
    context = _load_context(config)
    summaries = tuple(_summary(trade) for trade in _ordered_trades(context.trades))
    return DashboardSnapshotSource(
        telemetry=context.telemetry,
        telemetry_file_mtime_ns=context.telemetry_file_mtime_ns,
        trades=summaries[:max_trades],
    )


def load_dashboard_fast_lane_snapshot(
    config: DashboardFastLaneConfig,
    *,
    until_unix_ms: int,
) -> dict[str, object]:
    if type(config) is not DashboardFastLaneConfig:
        raise DashboardSourceError(
            "Fast Lane dashboard config must be exact"
        )
    if (
        isinstance(until_unix_ms, bool)
        or not isinstance(until_unix_ms, int)
        or until_unix_ms < 0
    ):
        raise DashboardSourceError(
            "Fast Lane dashboard window end must be a non-negative integer"
        )
    since_unix_ms = max(
        0,
        until_unix_ms - config.window_seconds * 1000,
    )
    if since_unix_ms >= until_unix_ms:
        raise DashboardSourceError(
            "Fast Lane dashboard window is empty"
        )

    try:
        decision = collect_fast_paper_shadow_decision_telemetry(
            evidence_directory=config.decision_evidence_directory,
            expected_release_sha=config.expected_release_sha,
            since_unix_ms=since_unix_ms,
            until_unix_ms=until_unix_ms,
        )
        execution = collect_fast_paper_shadow_execution_telemetry(
            manifest_path=config.manifest_path,
            execution_policy_path=config.execution_policy_path,
            ledger_database_path=config.ledger_database_path,
            run_id=config.run_id,
            decision_evidence_directory=(
                config.decision_evidence_directory
            ),
            execution_source_directory=(
                config.execution_source_directory
            ),
            pending_buy_retry_source_directory=(
                config.pending_buy_retry_source_directory
            ),
            expected_release_sha=config.expected_release_sha,
            since_unix_ms=since_unix_ms,
            until_unix_ms=until_unix_ms,
        )
        outcome = collect_fast_paper_shadow_outcome_telemetry(
            manifest_path=config.manifest_path,
            ledger_database_path=config.ledger_database_path,
            run_id=config.run_id,
            expected_release_sha=config.expected_release_sha,
            since_unix_ms=since_unix_ms,
            until_unix_ms=until_unix_ms,
        )
    except Exception as error:
        raise DashboardSourceError(
            "Fast Lane telemetry source is unavailable"
        ) from error

    _require_fast_lane_document(
        "decision",
        decision,
        expected_release_sha=config.expected_release_sha,
        since_unix_ms=since_unix_ms,
        until_unix_ms=until_unix_ms,
    )
    _require_fast_lane_document(
        "execution",
        execution,
        expected_release_sha=config.expected_release_sha,
        since_unix_ms=since_unix_ms,
        until_unix_ms=until_unix_ms,
    )
    _require_fast_lane_document(
        "outcome",
        outcome,
        expected_release_sha=config.expected_release_sha,
        since_unix_ms=since_unix_ms,
        until_unix_ms=until_unix_ms,
    )
    _require_fast_lane_identity(decision, execution, outcome)
    return {
        "window_since_unix_ms": since_unix_ms,
        "window_until_unix_ms": until_unix_ms,
        "expected_release_sha": config.expected_release_sha,
        "decision": decision,
        "execution": execution,
        "outcome": outcome,
    }


def load_dashboard_trade(
    config: DashboardSourceConfig,
    position_id: str,
) -> DashboardTradeDetail | None:
    _require_config(config)
    if not isinstance(position_id, str) or not position_id.strip():
        raise DashboardSourceError("position_id must be a non-empty string")
    context = _load_context(config)
    matches = tuple(trade for trade in context.trades if trade.position_id == position_id)
    if not matches:
        return None
    if len(matches) != 1:
        raise DashboardSourceError("dashboard trade position_id is ambiguous")
    trade = matches[0]
    linked = tuple(
        entry for entry in context.ledger_entries if entry.position_id == trade.position_id
    )
    linked = tuple(sorted(linked, key=lambda entry: entry.sequence))
    if any(entry.mint != trade.candidate_mint for entry in linked):
        raise DashboardSourceError("dashboard ledger candidate mint mismatch")
    events = tuple(_ledger_event(entry) for entry in linked)
    unavailable = DashboardEvidenceAvailability.NOT_PERSISTED
    return DashboardTradeDetail(
        summary=_summary(trade),
        ledger_events=events,
        safety_assessment=unavailable,
        feature_vector=unavailable,
        score_assessment=unavailable,
        entry_decision=unavailable,
        risk_assessment=unavailable,
        entry_quote=unavailable,
        strategic_exit_reason=unavailable,
    )



def _require_fast_lane_document(
    label: str,
    document: object,
    *,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> None:
    if not isinstance(document, dict):
        raise DashboardSourceError(
            f"Fast Lane {label} telemetry must be a document"
        )
    if (
        document.get("release_source_sha") != expected_release_sha
        or document.get("window_since_unix_ms") != since_unix_ms
        or document.get("window_until_unix_ms") != until_unix_ms
    ):
        raise DashboardSourceError(
            f"Fast Lane {label} telemetry release/window identity mismatch"
        )


def _require_fast_lane_identity(
    decision: dict[str, object],
    execution: dict[str, object],
    outcome: dict[str, object],
) -> None:
    identity_keys = (
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
    )
    execution_identity = tuple(execution.get(key) for key in identity_keys)
    outcome_identity = tuple(outcome.get(key) for key in identity_keys)
    if execution_identity != outcome_identity:
        raise DashboardSourceError(
            "Fast Lane execution/outcome identity mismatch"
        )
    decision_identity = tuple(decision.get(key) for key in identity_keys)
    if any(value is not None for value in decision_identity):
        if decision_identity != execution_identity:
            raise DashboardSourceError(
                "Fast Lane decision identity mismatch"
            )
    for key in ("run_id", "binding_fingerprint_sha256"):
        if execution.get(key) != outcome.get(key):
            raise DashboardSourceError(
                "Fast Lane ledger identity mismatch"
            )


def _load_context(config: DashboardSourceConfig) -> _DashboardContext:
    path = config.telemetry_path
    try:
        if path.is_symlink() or not path.is_file():
            raise DashboardSourceError("dashboard telemetry source is unavailable")
        payload = path.read_bytes()
        mtime_ns = path.stat().st_mtime_ns
        telemetry = decode_telemetry_snapshot(payload)
    except DashboardSourceError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise DashboardSourceError("dashboard telemetry source is invalid") from error

    try:
        bootstrap = bootstrap_observer_paper_campaign_runtime(config.paper_runtime_config)
        raw_trades = bootstrap.runner.evaluated_trades()
        if not isinstance(raw_trades, tuple) or not all(
            type(value) is EvaluatedTrade for value in raw_trades
        ):
            raise DashboardSourceError("dashboard evaluated trade evidence is invalid")
        ledger_entries = bootstrap.restored_state.ledger.entries
        if not isinstance(ledger_entries, tuple) or not all(
            type(value) is PaperLedgerEntry for value in ledger_entries
        ):
            raise DashboardSourceError("dashboard ledger evidence is invalid")
    except DashboardSourceError:
        raise
    except (ObserverPaperCampaignRuntimeError, OSError, TypeError, ValueError) as error:
        raise DashboardSourceError("required PAPER dashboard source is invalid") from error

    expected_candidate = telemetry.trading.candidate_version
    if raw_trades:
        if expected_candidate is None:
            raise DashboardSourceError("dashboard candidate version is unavailable")
        if any(trade.candidate_version != expected_candidate for trade in raw_trades):
            raise DashboardSourceError("dashboard candidate version evidence mismatch")
    position_ids = tuple(trade.position_id for trade in raw_trades)
    if len(position_ids) != len(set(position_ids)):
        raise DashboardSourceError("dashboard evaluated trade position IDs are ambiguous")

    return _DashboardContext(
        telemetry=telemetry,
        telemetry_file_mtime_ns=mtime_ns,
        trades=raw_trades,
        ledger_entries=ledger_entries,
    )


def _ordered_trades(trades: tuple[EvaluatedTrade, ...]) -> tuple[EvaluatedTrade, ...]:
    return tuple(
        sorted(
            trades,
            key=lambda trade: (
                -trade.closed_at_unix_ms,
                -trade.opened_at_unix_ms,
                trade.position_id,
                trade.candidate_mint,
            ),
        )
    )


def _summary(trade: EvaluatedTrade) -> DashboardTradeSummary:
    return DashboardTradeSummary(
        candidate_version=trade.candidate_version,
        position_id=trade.position_id,
        mint=trade.candidate_mint,
        setup_name=trade.setup_name,
        market_regime=trade.market_regime,
        opened_at_unix_ms=trade.opened_at_unix_ms,
        closed_at_unix_ms=trade.closed_at_unix_ms,
        entry_notional_usd=trade.entry_notional_usd,
        turnover_usd=trade.turnover_usd,
        gross_pnl_usd=trade.gross_pnl_usd,
        execution_friction_usd=trade.execution_friction_usd,
        explicit_cost_usd=trade.explicit_cost_usd,
        net_pnl_usd=trade.net_pnl_usd,
    )


def _ledger_event(entry: PaperLedgerEntry) -> DashboardLedgerEvent:
    return DashboardLedgerEvent(
        sequence=entry.sequence,
        side=entry.side.value,
        execution_state=entry.execution_state.value,
        paper_execution_reason_code=entry.paper_execution_reason_code.value,
        ledger_reason_code=entry.ledger_reason_code.value,
        strategy_name=entry.strategy_name,
        strategy_version=entry.strategy_version,
        score_policy_version=entry.score_policy_version,
        decision_policy_version=entry.decision_policy_version,
        risk_policy_version=entry.risk_policy_version,
        paper_policy_version=entry.paper_policy_version,
        booked_at_unix_ms=entry.booked_at_unix_ms,
        filled_quantity=entry.filled_quantity,
        filled_notional_usd=entry.filled_notional_usd,
        explicit_cost_usd=entry.explicit_cost_usd,
        realized_pnl_delta_usd=entry.realized_pnl_delta_usd,
    )


def _require_config(config: object) -> None:
    if type(config) is not DashboardSourceConfig:
        raise DashboardSourceError("config must be an exact DashboardSourceConfig")
