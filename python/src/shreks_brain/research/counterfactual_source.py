from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3
from urllib.parse import quote

from .counterfactuals import (
    EntryCounterfactualContext,
    OpenPositionCounterfactualContext,
)


class CounterfactualSourceError(RuntimeError):
    """Raised when canonical FL3/FL4 source evidence is missing or contradictory."""


@dataclass(frozen=True, slots=True)
class CounterfactualSourceProvenance:
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    decision_observed_at_unix_ms: int
    mint: str
    quote_mint: str
    venue: str
    horizon_ms: int
    future_path_label_version: int
    completeness: str
    coverage_complete_through_unix_ms: int
    coverage_contiguous: bool
    endpoint_signature: str | None
    endpoint_ordinal: int | None
    endpoint_observed_at_unix_ms: int | None
    endpoint_price_quote: float | None
    decision_entry_total_quote: float | None
    endpoint_exit_capacity_base: float | None
    route_unavailability_observed: bool | None
    endpoint_cost_adjusted_return_bps: float | None
    decision_execution_economics_present: bool
    endpoint_execution_economics_present: bool


@dataclass(frozen=True, slots=True)
class LoadedEntryCounterfactual:
    provenance: CounterfactualSourceProvenance
    context: EntryCounterfactualContext


@dataclass(frozen=True, slots=True)
class LoadedOpenPositionCounterfactual:
    provenance: CounterfactualSourceProvenance
    context: OpenPositionCounterfactualContext


def load_entry_counterfactual_from_sqlite(
    db_path: str | Path,
    *,
    decision_signature: str,
    decision_ordinal: int,
    horizon_ms: int,
    label_version: int,
    base_quantity: float,
) -> LoadedEntryCounterfactual:
    """Load one canonical FL4 decision as an FL5 entry-research context.

    Existing FL4 rows intentionally do not persist enough requested-quantity
    execution evidence to manufacture ``ExecutableTradeEvidence``. The returned
    context therefore preserves the canonical horizon/market facts while keeping
    BUY/exit execution evidence unknown. SKIP remains available through the pure
    FL5 labeler.
    """

    _validate_lookup_identity(
        decision_signature=decision_signature,
        decision_ordinal=decision_ordinal,
        horizon_ms=horizon_ms,
        label_version=label_version,
    )
    _require_positive_finite("base_quantity", base_quantity)

    provenance = _load_provenance(
        db_path,
        decision_signature=decision_signature,
        decision_ordinal=decision_ordinal,
        horizon_ms=horizon_ms,
        label_version=label_version,
    )
    context = EntryCounterfactualContext(
        decision_id=_decision_id(provenance),
        mint=provenance.mint,
        quote_mint=provenance.quote_mint,
        decision_observed_at_unix_ms=provenance.decision_observed_at_unix_ms,
        base_quantity=base_quantity,
        horizon_ms=provenance.horizon_ms,
        horizon_complete=provenance.completeness == "complete",
        buy_now=None,
        exit_at_horizon=None,
        delayed_entries=(),
    )
    return LoadedEntryCounterfactual(provenance=provenance, context=context)


def load_open_position_counterfactual_from_sqlite(
    db_path: str | Path,
    *,
    decision_signature: str,
    decision_ordinal: int,
    horizon_ms: int,
    label_version: int,
    position_base_quantity: float,
    position_cost_basis_quote: float,
    reduce_quantity: float | None = None,
) -> LoadedOpenPositionCounterfactual:
    """Load one canonical FL4 horizon as an FL5 open-position context.

    Position state is caller supplied because FL4 is a market-path research
    artifact, not an authoritative position ledger. Stored market observations,
    capacity, or cost-adjusted returns are never promoted into SELL/HOLD/REDUCE
    fills without exact requested-quantity execution evidence.
    """

    _validate_lookup_identity(
        decision_signature=decision_signature,
        decision_ordinal=decision_ordinal,
        horizon_ms=horizon_ms,
        label_version=label_version,
    )
    _require_positive_finite("position_base_quantity", position_base_quantity)
    _require_positive_finite("position_cost_basis_quote", position_cost_basis_quote)
    if reduce_quantity is not None:
        _require_positive_finite("reduce_quantity", reduce_quantity)
        if reduce_quantity > position_base_quantity:
            raise CounterfactualSourceError(
                "reduce_quantity cannot exceed position_base_quantity"
            )

    provenance = _load_provenance(
        db_path,
        decision_signature=decision_signature,
        decision_ordinal=decision_ordinal,
        horizon_ms=horizon_ms,
        label_version=label_version,
    )
    context = OpenPositionCounterfactualContext(
        decision_id=_decision_id(provenance),
        mint=provenance.mint,
        quote_mint=provenance.quote_mint,
        action_observed_at_unix_ms=provenance.decision_observed_at_unix_ms,
        position_base_quantity=position_base_quantity,
        position_cost_basis_quote=position_cost_basis_quote,
        horizon_ms=provenance.horizon_ms,
        horizon_complete=provenance.completeness == "complete",
        sell_now=None,
        hold_exit=None,
        reduce_quantity=reduce_quantity,
        reduce_now=None,
    )
    return LoadedOpenPositionCounterfactual(provenance=provenance, context=context)


def _load_provenance(
    db_path: str | Path,
    *,
    decision_signature: str,
    decision_ordinal: int,
    horizon_ms: int,
    label_version: int,
) -> CounterfactualSourceProvenance:
    path = Path(db_path)
    connection = _open_read_only(path)
    try:
        row = connection.execute(
            """
            SELECT
                label.decision_signature,
                label.decision_ordinal,
                label.decision_sequence,
                label.decision_mint,
                label.decision_quote_mint,
                label.decision_venue,
                label.decision_observed_at_unix_ms,
                label.decision_entry_price_quote,
                label.decision_entry_total_quote,
                label.coverage_complete_through_unix_ms,
                label.coverage_contiguous,
                label.horizon_ms,
                label.label_version,
                label.completeness,
                label.event_count,
                label.no_trade_events,
                label.endpoint_signature,
                label.endpoint_ordinal,
                label.endpoint_observed_at_unix_ms,
                label.endpoint_price_quote,
                label.endpoint_exit_capacity_base,
                label.route_unavailability_observed,
                label.endpoint_cost_adjusted_return_bps,
                decision.sequence AS canonical_decision_sequence,
                decision.mint AS canonical_decision_mint,
                decision.quote_mint AS canonical_decision_quote_mint,
                decision.venue AS canonical_decision_venue,
                decision.observed_at_unix_ms AS canonical_decision_observed_at_unix_ms,
                decision.price_quote AS canonical_decision_price_quote,
                endpoint.sequence AS canonical_endpoint_sequence,
                endpoint.mint AS canonical_endpoint_mint,
                endpoint.quote_mint AS canonical_endpoint_quote_mint,
                endpoint.venue AS canonical_endpoint_venue,
                endpoint.observed_at_unix_ms AS canonical_endpoint_observed_at_unix_ms,
                endpoint.price_quote AS canonical_endpoint_price_quote
            FROM fast_future_path_labels AS label
            JOIN fast_events AS decision
              ON decision.signature = label.decision_signature
             AND decision.ordinal = label.decision_ordinal
            LEFT JOIN fast_events AS endpoint
              ON endpoint.signature = label.endpoint_signature
             AND endpoint.ordinal = label.endpoint_ordinal
            WHERE label.decision_signature = ?
              AND label.decision_ordinal = ?
              AND label.horizon_ms = ?
              AND label.label_version = ?
            """,
            (
                decision_signature,
                decision_ordinal,
                horizon_ms,
                label_version,
            ),
        ).fetchone()
        if row is None:
            raise CounterfactualSourceError(
                "canonical FL4 label was not found for the requested decision/horizon/version"
            )

        _validate_canonical_row(row)
        _reject_conflict_quarantined(
            connection,
            signature=row["decision_signature"],
            ordinal=row["decision_ordinal"],
            venue=row["decision_venue"],
            role="decision",
        )
        if row["endpoint_signature"] is not None:
            _reject_conflict_quarantined(
                connection,
                signature=row["endpoint_signature"],
                ordinal=row["endpoint_ordinal"],
                venue=row["decision_venue"],
                role="endpoint",
            )

        decision_execution_economics_present = _execution_economics_present(
            connection,
            signature=row["decision_signature"],
            ordinal=row["decision_ordinal"],
            venue=row["decision_venue"],
        )
        endpoint_execution_economics_present = False
        if row["endpoint_signature"] is not None:
            endpoint_execution_economics_present = _execution_economics_present(
                connection,
                signature=row["endpoint_signature"],
                ordinal=row["endpoint_ordinal"],
                venue=row["decision_venue"],
            )

        return CounterfactualSourceProvenance(
            decision_signature=row["decision_signature"],
            decision_ordinal=int(row["decision_ordinal"]),
            decision_sequence=int(row["decision_sequence"]),
            decision_observed_at_unix_ms=int(row["decision_observed_at_unix_ms"]),
            mint=row["decision_mint"],
            quote_mint=row["decision_quote_mint"],
            venue=row["decision_venue"],
            horizon_ms=int(row["horizon_ms"]),
            future_path_label_version=int(row["label_version"]),
            completeness=row["completeness"],
            coverage_complete_through_unix_ms=int(
                row["coverage_complete_through_unix_ms"]
            ),
            coverage_contiguous=bool(row["coverage_contiguous"]),
            endpoint_signature=row["endpoint_signature"],
            endpoint_ordinal=(
                int(row["endpoint_ordinal"])
                if row["endpoint_ordinal"] is not None
                else None
            ),
            endpoint_observed_at_unix_ms=(
                int(row["endpoint_observed_at_unix_ms"])
                if row["endpoint_observed_at_unix_ms"] is not None
                else None
            ),
            endpoint_price_quote=row["endpoint_price_quote"],
            decision_entry_total_quote=row["decision_entry_total_quote"],
            endpoint_exit_capacity_base=row["endpoint_exit_capacity_base"],
            route_unavailability_observed=(
                bool(row["route_unavailability_observed"])
                if row["route_unavailability_observed"] is not None
                else None
            ),
            endpoint_cost_adjusted_return_bps=row[
                "endpoint_cost_adjusted_return_bps"
            ],
            decision_execution_economics_present=decision_execution_economics_present,
            endpoint_execution_economics_present=endpoint_execution_economics_present,
        )
    except CounterfactualSourceError:
        raise
    except sqlite3.Error as error:
        raise CounterfactualSourceError(
            f"canonical source database schema/query failed closed: {error}"
        ) from error
    finally:
        connection.close()


def _open_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CounterfactualSourceError(
            f"cannot open canonical source database read-only: {path}"
        )
    resolved = path.resolve()
    uri = f"file:{quote(str(resolved), safe='/')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.Error as error:
        raise CounterfactualSourceError(
            f"cannot open canonical source database read-only: {error}"
        ) from error


def _validate_lookup_identity(
    *,
    decision_signature: str,
    decision_ordinal: int,
    horizon_ms: int,
    label_version: int,
) -> None:
    if not isinstance(decision_signature, str) or not decision_signature.strip():
        raise CounterfactualSourceError("decision_signature must not be blank")
    if (
        isinstance(decision_ordinal, bool)
        or not isinstance(decision_ordinal, int)
        or decision_ordinal < 0
    ):
        raise CounterfactualSourceError("decision_ordinal must be a non-negative integer")
    if isinstance(horizon_ms, bool) or not isinstance(horizon_ms, int) or horizon_ms <= 0:
        raise CounterfactualSourceError("horizon_ms must be a positive integer")
    if (
        isinstance(label_version, bool)
        or not isinstance(label_version, int)
        or label_version <= 0
    ):
        raise CounterfactualSourceError("label_version must be a positive integer")


def _validate_canonical_row(row: sqlite3.Row) -> None:
    decision_matches = (
        row["decision_sequence"] == row["canonical_decision_sequence"]
        and row["decision_mint"] == row["canonical_decision_mint"]
        and row["decision_quote_mint"] == row["canonical_decision_quote_mint"]
        and row["decision_venue"] == row["canonical_decision_venue"]
        and row["decision_observed_at_unix_ms"]
        == row["canonical_decision_observed_at_unix_ms"]
        and row["decision_entry_price_quote"] == row["canonical_decision_price_quote"]
    )
    if not decision_matches:
        raise CounterfactualSourceError(
            "FL4 row does not match its canonical decision FastEvent"
        )

    contiguous = row["coverage_contiguous"]
    if contiguous not in (0, 1):
        raise CounterfactualSourceError("FL4 coverage_contiguous is invalid")
    horizon_end = row["decision_observed_at_unix_ms"] + row["horizon_ms"]
    should_be_complete = bool(contiguous) and (
        row["coverage_complete_through_unix_ms"] >= horizon_end
    )
    if row["completeness"] not in ("complete", "incomplete"):
        raise CounterfactualSourceError("FL4 completeness value is invalid")
    if should_be_complete != (row["completeness"] == "complete"):
        raise CounterfactualSourceError(
            "FL4 completeness contradicts its canonical coverage watermark"
        )

    endpoint_signature = row["endpoint_signature"]
    endpoint_ordinal = row["endpoint_ordinal"]
    if (endpoint_signature is None) != (endpoint_ordinal is None):
        raise CounterfactualSourceError("FL4 endpoint identity is internally inconsistent")

    if endpoint_signature is None:
        if row["canonical_endpoint_sequence"] is not None:
            raise CounterfactualSourceError("FL4 null endpoint unexpectedly resolved")
        if row["event_count"] > 0:
            raise CounterfactualSourceError(
                "FL4 positive event_count is missing its canonical endpoint"
            )
        return

    if row["canonical_endpoint_sequence"] is None:
        raise CounterfactualSourceError("FL4 canonical endpoint FastEvent is missing")
    endpoint_matches = (
        row["canonical_endpoint_sequence"] > row["decision_sequence"]
        and row["canonical_endpoint_mint"] == row["decision_mint"]
        and row["canonical_endpoint_quote_mint"] == row["decision_quote_mint"]
        and row["canonical_endpoint_venue"] == row["decision_venue"]
        and row["canonical_endpoint_observed_at_unix_ms"]
        == row["endpoint_observed_at_unix_ms"]
        and row["canonical_endpoint_price_quote"] == row["endpoint_price_quote"]
    )
    if not endpoint_matches:
        raise CounterfactualSourceError(
            "FL4 row does not match its canonical endpoint FastEvent"
        )
    if row["endpoint_observed_at_unix_ms"] <= row["decision_observed_at_unix_ms"]:
        raise CounterfactualSourceError("FL4 endpoint time is not after the decision")
    if row["endpoint_observed_at_unix_ms"] > horizon_end:
        raise CounterfactualSourceError("FL4 endpoint lies beyond the requested horizon")


def _reject_conflict_quarantined(
    connection: sqlite3.Connection,
    *,
    signature: str,
    ordinal: int,
    venue: str,
    role: str,
) -> None:
    table = _conflict_table_for_venue(venue)
    conflict = connection.execute(
        f"SELECT 1 FROM {table} WHERE signature = ? AND ordinal = ? LIMIT 1",
        (signature, ordinal),
    ).fetchone()
    if conflict is not None:
        raise CounterfactualSourceError(
            f"canonical {role} source is conflict-quarantined"
        )


def _execution_economics_present(
    connection: sqlite3.Connection,
    *,
    signature: str,
    ordinal: int,
    venue: str,
) -> bool:
    table = _execution_economics_table_for_venue(venue)
    return (
        connection.execute(
            f"SELECT 1 FROM {table} WHERE signature = ? AND ordinal = ? LIMIT 1",
            (signature, ordinal),
        ).fetchone()
        is not None
    )


def _conflict_table_for_venue(venue: str) -> str:
    if venue == "pump_fun_bonding_curve":
        return "pump_trade_evidence_conflicts"
    if venue == "pump_swap":
        return "pump_swap_trade_evidence_conflicts"
    raise CounterfactualSourceError(
        f"unsupported canonical venue for conflict quarantine: {venue}"
    )


def _execution_economics_table_for_venue(venue: str) -> str:
    if venue == "pump_fun_bonding_curve":
        return "pump_trade_execution_economics"
    if venue == "pump_swap":
        return "pump_swap_execution_economics"
    raise CounterfactualSourceError(
        f"unsupported canonical venue for FL3 economics lookup: {venue}"
    )


def _decision_id(provenance: CounterfactualSourceProvenance) -> str:
    return (
        f"{provenance.decision_signature}:{provenance.decision_ordinal}:"
        f"h{provenance.horizon_ms}:v{provenance.future_path_label_version}"
    )


def _require_positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CounterfactualSourceError(f"{name} must be numeric")
    if not math.isfinite(float(value)) or value <= 0:
        raise CounterfactualSourceError(f"{name} must be positive and finite")
