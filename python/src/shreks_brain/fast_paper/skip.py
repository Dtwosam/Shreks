from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from .models import FastPaperAction, FastPaperActionAssessment


FAST_PAPER_SKIP_AUDIT_VERSION = "fl7.3-v1"


class FastPaperSkipAuditError(ValueError):
    """Fail-closed FL7.3 SKIP audit error."""


@dataclass(frozen=True, slots=True)
class FastPaperSkipLabelLink:
    decision_signature: str
    decision_ordinal: int
    mint: str
    quote_mint: str
    venue: str
    future_path_label_version: int

    def __post_init__(self) -> None:
        _require_non_empty_string("decision_signature", self.decision_signature)
        _require_non_negative_int("decision_ordinal", self.decision_ordinal)
        _require_non_empty_string("mint", self.mint)
        _require_non_empty_string("quote_mint", self.quote_mint)
        _require_non_empty_string("venue", self.venue)
        _require_positive_int(
            "future_path_label_version", self.future_path_label_version
        )


@dataclass(frozen=True, slots=True)
class FastPaperSkipAuditRecord:
    record_id: str
    version: str
    assessment: FastPaperActionAssessment
    link: FastPaperSkipLabelLink

    def __post_init__(self) -> None:
        _require_record_id(self.record_id)
        if self.version != FAST_PAPER_SKIP_AUDIT_VERSION:
            raise FastPaperSkipAuditError(
                f"unsupported Fast PAPER SKIP audit version: {self.version!r}"
            )
        if not isinstance(self.assessment, FastPaperActionAssessment):
            raise FastPaperSkipAuditError(
                "assessment must be FastPaperActionAssessment"
            )
        if self.assessment.action is not FastPaperAction.SKIP:
            raise FastPaperSkipAuditError("Fast PAPER SKIP audit requires SKIP action")
        if not isinstance(self.link, FastPaperSkipLabelLink):
            raise FastPaperSkipAuditError("link must be FastPaperSkipLabelLink")


@dataclass(frozen=True, slots=True)
class FastPaperSkipFutureLabel:
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    decision_mint: str
    decision_quote_mint: str
    decision_venue: str
    decision_observed_at_unix_ms: int
    decision_entry_price_quote: float
    decision_entry_total_quote: float | None
    coverage_complete_through_unix_ms: int
    coverage_contiguous: bool
    horizon_ms: int
    label_version: int
    completeness: str
    event_count: int
    no_trade_events: bool
    endpoint_signature: str | None
    endpoint_ordinal: int | None
    endpoint_observed_at_unix_ms: int | None
    endpoint_price_quote: float | None
    endpoint_return_bps: float | None
    mfe_bps: float | None
    mae_bps: float | None
    time_to_peak_ms: int | None
    time_to_trough_ms: int | None
    reversal_occurred: bool | None
    first_reversal_after_ms: int | None
    min_exit_capacity_base: float | None
    endpoint_exit_capacity_base: float | None
    route_unavailability_observed: bool | None
    best_cost_adjusted_return_bps: float | None
    endpoint_cost_adjusted_return_bps: float | None


@dataclass(frozen=True, slots=True)
class FastPaperSkipAuditView:
    record: FastPaperSkipAuditRecord
    future_labels: tuple[FastPaperSkipFutureLabel, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.record, FastPaperSkipAuditRecord):
            raise FastPaperSkipAuditError("record must be FastPaperSkipAuditRecord")
        if not isinstance(self.future_labels, tuple) or not all(
            isinstance(label, FastPaperSkipFutureLabel) for label in self.future_labels
        ):
            raise FastPaperSkipAuditError(
                "future_labels must be a tuple of FastPaperSkipFutureLabel"
            )


def record_fast_paper_skip(
    database_path: str | Path,
    assessment: FastPaperActionAssessment,
    link: FastPaperSkipLabelLink,
) -> FastPaperSkipAuditRecord:
    """Durably record one truthful Fast Lane SKIP assessment.

    The function writes only ``fast_paper_skip_records``. It never creates or
    mutates future-path labels; those remain independently produced FL4 evidence.
    """

    if not isinstance(assessment, FastPaperActionAssessment):
        raise FastPaperSkipAuditError(
            "assessment must be FastPaperActionAssessment"
        )
    if assessment.action is not FastPaperAction.SKIP:
        raise FastPaperSkipAuditError("Fast PAPER SKIP audit accepts only SKIP actions")
    if not isinstance(link, FastPaperSkipLabelLink):
        raise FastPaperSkipAuditError("link must be FastPaperSkipLabelLink")

    connection = _open_existing_database(database_path)
    try:
        _require_table(connection, "fast_paper_skip_records")
        _require_canonical_fast_event(connection, assessment, link)
        incoming = _build_record(assessment, link)

        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT *
                   FROM fast_paper_skip_records
                   WHERE source_event_id = ?
                     AND strategy_family = ?
                     AND strategy_version = ?
                     AND assessment_version = ?""",
                (
                    assessment.source_event_id,
                    assessment.strategy_family,
                    assessment.strategy_version,
                    assessment.version,
                ),
            ).fetchone()

            if row is not None:
                stored = _decode_record(row)
                connection.rollback()
                if stored == incoming:
                    return stored
                raise FastPaperSkipAuditError(
                    "Fast PAPER SKIP audit conflict for existing logical assessment"
                )

            connection.execute(
                """INSERT INTO fast_paper_skip_records (
                       record_id, record_version, assessment_version,
                       source_event_id, market_key, source_sequence,
                       as_of_unix_ms, strategy_family, strategy_version,
                       reasons_json, decision_signature, decision_ordinal,
                       decision_mint, decision_quote_mint, decision_venue,
                       future_path_label_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incoming.record_id,
                    incoming.version,
                    assessment.version,
                    assessment.source_event_id,
                    assessment.market_key,
                    assessment.source_sequence,
                    assessment.as_of_unix_ms,
                    assessment.strategy_family,
                    assessment.strategy_version,
                    _encode_reasons(assessment.reasons),
                    link.decision_signature,
                    link.decision_ordinal,
                    link.mint,
                    link.quote_mint,
                    link.venue,
                    link.future_path_label_version,
                ),
            )
            connection.commit()
            return incoming
        except FastPaperSkipAuditError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            raise FastPaperSkipAuditError(
                f"Fast PAPER SKIP audit write failed: {error}"
            ) from error
    finally:
        connection.close()


def load_fast_paper_skip_with_future_labels(
    database_path: str | Path,
    record_id: str,
) -> FastPaperSkipAuditView:
    """Load one immutable SKIP record and any matching FL4 future labels."""

    _require_record_id(record_id)
    connection = _open_existing_database(database_path)
    try:
        _require_table(connection, "fast_paper_skip_records")
        _require_table(connection, "fast_future_path_labels")
        try:
            row = connection.execute(
                "SELECT * FROM fast_paper_skip_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise FastPaperSkipAuditError(
                    f"Fast PAPER SKIP record not found: {record_id}"
                )
            record = _decode_record(row)

            label_rows = connection.execute(
                """SELECT *
                   FROM fast_future_path_labels
                   WHERE decision_signature = ?
                     AND decision_ordinal = ?
                     AND label_version = ?
                   ORDER BY horizon_ms ASC""",
                (
                    record.link.decision_signature,
                    record.link.decision_ordinal,
                    record.link.future_path_label_version,
                ),
            ).fetchall()
            labels = tuple(_decode_future_label(row) for row in label_rows)
            return FastPaperSkipAuditView(record=record, future_labels=labels)
        except FastPaperSkipAuditError:
            raise
        except sqlite3.Error as error:
            raise FastPaperSkipAuditError(
                f"Fast PAPER SKIP audit read failed: {error}"
            ) from error
    finally:
        connection.close()


def _open_existing_database(database_path: str | Path) -> sqlite3.Connection:
    try:
        path = Path(database_path)
    except TypeError as error:
        raise FastPaperSkipAuditError("database_path must be path-like") from error
    if not path.is_file():
        raise FastPaperSkipAuditError(
            f"Fast PAPER SKIP database does not exist: {path}"
        )

    try:
        connection = sqlite3.connect(
            f"file:{path.resolve()}?mode=rw",
            uri=True,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except sqlite3.Error as error:
        raise FastPaperSkipAuditError(
            f"cannot open Fast PAPER SKIP database read/write: {error}"
        ) from error


def _require_table(connection: sqlite3.Connection, table: str) -> None:
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    except sqlite3.Error as error:
        raise FastPaperSkipAuditError(
            f"cannot inspect required table {table}: {error}"
        ) from error
    if row is None:
        raise FastPaperSkipAuditError(
            f"required operational table {table} is absent; Rust migration is required"
        )


def _require_canonical_fast_event(
    connection: sqlite3.Connection,
    assessment: FastPaperActionAssessment,
    link: FastPaperSkipLabelLink,
) -> None:
    try:
        row = connection.execute(
            """SELECT sequence, mint, quote_mint, venue, observed_at_unix_ms
               FROM fast_events
               WHERE signature = ? AND ordinal = ?""",
            (link.decision_signature, link.decision_ordinal),
        ).fetchone()
    except sqlite3.Error as error:
        raise FastPaperSkipAuditError(
            f"cannot validate canonical FastEvent: {error}"
        ) from error

    expected = (
        assessment.source_sequence,
        link.mint,
        link.quote_mint,
        link.venue,
        assessment.as_of_unix_ms,
    )
    if row is None or tuple(row) != expected:
        raise FastPaperSkipAuditError(
            "Fast PAPER SKIP canonical FastEvent identity/sequence/time mismatch"
        )


def _build_record(
    assessment: FastPaperActionAssessment,
    link: FastPaperSkipLabelLink,
) -> FastPaperSkipAuditRecord:
    payload = {
        "record_version": FAST_PAPER_SKIP_AUDIT_VERSION,
        "assessment_version": assessment.version,
        "source_event_id": assessment.source_event_id,
        "market_key": assessment.market_key,
        "source_sequence": assessment.source_sequence,
        "as_of_unix_ms": assessment.as_of_unix_ms,
        "strategy_family": assessment.strategy_family,
        "strategy_version": assessment.strategy_version,
        "reasons": list(assessment.reasons),
        "decision_signature": link.decision_signature,
        "decision_ordinal": link.decision_ordinal,
        "decision_mint": link.mint,
        "decision_quote_mint": link.quote_mint,
        "decision_venue": link.venue,
        "future_path_label_version": link.future_path_label_version,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    record_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return FastPaperSkipAuditRecord(
        record_id=record_id,
        version=FAST_PAPER_SKIP_AUDIT_VERSION,
        assessment=assessment,
        link=link,
    )


def _encode_reasons(reasons: tuple[str, ...]) -> str:
    if not isinstance(reasons, tuple) or not reasons:
        raise FastPaperSkipAuditError("SKIP reasons must be a non-empty tuple")
    if not all(isinstance(reason, str) and reason.strip() for reason in reasons):
        raise FastPaperSkipAuditError("SKIP reasons must be non-empty strings")
    return json.dumps(list(reasons), ensure_ascii=False, separators=(",", ":"))


def _decode_reasons(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise FastPaperSkipAuditError("stored SKIP reasons_json must be text")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FastPaperSkipAuditError("stored SKIP reasons_json is malformed") from error
    if (
        not isinstance(decoded, list)
        or not decoded
        or not all(isinstance(reason, str) and reason.strip() for reason in decoded)
    ):
        raise FastPaperSkipAuditError(
            "stored SKIP reasons_json must contain non-empty strings"
        )
    return tuple(decoded)


def _decode_record(row: sqlite3.Row) -> FastPaperSkipAuditRecord:
    try:
        assessment = FastPaperActionAssessment(
            version=_require_row_string(row, "assessment_version"),
            source_event_id=_require_row_string(row, "source_event_id"),
            market_key=_require_row_string(row, "market_key"),
            source_sequence=_require_row_positive_int(row, "source_sequence"),
            as_of_unix_ms=_require_row_non_negative_int(row, "as_of_unix_ms"),
            strategy_family=_require_row_string(row, "strategy_family"),
            strategy_version=_require_row_string(row, "strategy_version"),
            action=FastPaperAction.SKIP,
            reasons=_decode_reasons(row["reasons_json"]),
        )
        link = FastPaperSkipLabelLink(
            decision_signature=_require_row_string(row, "decision_signature"),
            decision_ordinal=_require_row_non_negative_int(row, "decision_ordinal"),
            mint=_require_row_string(row, "decision_mint"),
            quote_mint=_require_row_string(row, "decision_quote_mint"),
            venue=_require_row_string(row, "decision_venue"),
            future_path_label_version=_require_row_positive_int(
                row, "future_path_label_version"
            ),
        )
        return FastPaperSkipAuditRecord(
            record_id=_require_row_string(row, "record_id"),
            version=_require_row_string(row, "record_version"),
            assessment=assessment,
            link=link,
        )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        if isinstance(error, FastPaperSkipAuditError):
            raise
        raise FastPaperSkipAuditError(
            f"stored Fast PAPER SKIP record is malformed: {error}"
        ) from error


def _decode_future_label(row: sqlite3.Row) -> FastPaperSkipFutureLabel:
    try:
        completeness = _require_row_string(row, "completeness")
        if completeness not in {"complete", "incomplete"}:
            raise FastPaperSkipAuditError(
                f"stored FL4 completeness is invalid: {completeness!r}"
            )
        return FastPaperSkipFutureLabel(
            decision_signature=_require_row_string(row, "decision_signature"),
            decision_ordinal=_require_row_non_negative_int(row, "decision_ordinal"),
            decision_sequence=_require_row_positive_int(row, "decision_sequence"),
            decision_mint=_require_row_string(row, "decision_mint"),
            decision_quote_mint=_require_row_string(row, "decision_quote_mint"),
            decision_venue=_require_row_string(row, "decision_venue"),
            decision_observed_at_unix_ms=_require_row_non_negative_int(
                row, "decision_observed_at_unix_ms"
            ),
            decision_entry_price_quote=_require_row_positive_finite(
                row, "decision_entry_price_quote"
            ),
            decision_entry_total_quote=_optional_row_positive_finite(
                row, "decision_entry_total_quote"
            ),
            coverage_complete_through_unix_ms=_require_row_non_negative_int(
                row, "coverage_complete_through_unix_ms"
            ),
            coverage_contiguous=_row_bool(row, "coverage_contiguous"),
            horizon_ms=_require_row_positive_int(row, "horizon_ms"),
            label_version=_require_row_positive_int(row, "label_version"),
            completeness=completeness,
            event_count=_require_row_non_negative_int(row, "event_count"),
            no_trade_events=_row_bool(row, "no_trade_events"),
            endpoint_signature=_optional_row_string(row, "endpoint_signature"),
            endpoint_ordinal=_optional_row_non_negative_int(row, "endpoint_ordinal"),
            endpoint_observed_at_unix_ms=_optional_row_non_negative_int(
                row, "endpoint_observed_at_unix_ms"
            ),
            endpoint_price_quote=_optional_row_positive_finite(
                row, "endpoint_price_quote"
            ),
            endpoint_return_bps=_optional_row_finite(row, "endpoint_return_bps"),
            mfe_bps=_optional_row_finite(row, "mfe_bps"),
            mae_bps=_optional_row_finite(row, "mae_bps"),
            time_to_peak_ms=_optional_row_non_negative_int(row, "time_to_peak_ms"),
            time_to_trough_ms=_optional_row_non_negative_int(
                row, "time_to_trough_ms"
            ),
            reversal_occurred=_optional_row_bool(row, "reversal_occurred"),
            first_reversal_after_ms=_optional_row_non_negative_int(
                row, "first_reversal_after_ms"
            ),
            min_exit_capacity_base=_optional_row_non_negative_finite(
                row, "min_exit_capacity_base"
            ),
            endpoint_exit_capacity_base=_optional_row_non_negative_finite(
                row, "endpoint_exit_capacity_base"
            ),
            route_unavailability_observed=_optional_row_bool(
                row, "route_unavailability_observed"
            ),
            best_cost_adjusted_return_bps=_optional_row_finite(
                row, "best_cost_adjusted_return_bps"
            ),
            endpoint_cost_adjusted_return_bps=_optional_row_finite(
                row, "endpoint_cost_adjusted_return_bps"
            ),
        )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        if isinstance(error, FastPaperSkipAuditError):
            raise
        raise FastPaperSkipAuditError(
            f"stored FL4 future-path label is malformed: {error}"
        ) from error


def _require_record_id(value: Any) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise FastPaperSkipAuditError("record_id must be a 64-character SHA-256 hex string")
    try:
        parsed = bytes.fromhex(value)
    except ValueError as error:
        raise FastPaperSkipAuditError("record_id must be hexadecimal") from error
    if len(parsed) != 32 or value.lower() != value:
        raise FastPaperSkipAuditError(
            "record_id must be a lowercase 64-character SHA-256 hex string"
        )


def _require_non_empty_string(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FastPaperSkipAuditError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperSkipAuditError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperSkipAuditError(f"{name} must be a positive integer")


def _require_row_string(row: sqlite3.Row, name: str) -> str:
    value = row[name]
    _require_non_empty_string(name, value)
    return value


def _optional_row_string(row: sqlite3.Row, name: str) -> str | None:
    value = row[name]
    if value is None:
        return None
    _require_non_empty_string(name, value)
    return value


def _require_row_non_negative_int(row: sqlite3.Row, name: str) -> int:
    value = row[name]
    _require_non_negative_int(name, value)
    return value


def _require_row_positive_int(row: sqlite3.Row, name: str) -> int:
    value = row[name]
    _require_positive_int(name, value)
    return value


def _optional_row_non_negative_int(row: sqlite3.Row, name: str) -> int | None:
    value = row[name]
    if value is None:
        return None
    _require_non_negative_int(name, value)
    return value


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FastPaperSkipAuditError(f"{name} must be finite")
    converted = float(value)
    if not math.isfinite(converted):
        raise FastPaperSkipAuditError(f"{name} must be finite")
    return converted


def _require_row_positive_finite(row: sqlite3.Row, name: str) -> float:
    value = _finite(name, row[name])
    if value <= 0.0:
        raise FastPaperSkipAuditError(f"{name} must be strictly positive")
    return value


def _optional_row_positive_finite(row: sqlite3.Row, name: str) -> float | None:
    if row[name] is None:
        return None
    return _require_row_positive_finite(row, name)


def _optional_row_non_negative_finite(row: sqlite3.Row, name: str) -> float | None:
    if row[name] is None:
        return None
    value = _finite(name, row[name])
    if value < 0.0:
        raise FastPaperSkipAuditError(f"{name} must be non-negative")
    return value


def _optional_row_finite(row: sqlite3.Row, name: str) -> float | None:
    if row[name] is None:
        return None
    return _finite(name, row[name])


def _row_bool(row: sqlite3.Row, name: str) -> bool:
    value = row[name]
    if isinstance(value, bool):
        return value
    if not isinstance(value, int) or value not in (0, 1):
        raise FastPaperSkipAuditError(f"{name} must be encoded as SQLite boolean 0/1")
    return bool(value)


def _optional_row_bool(row: sqlite3.Row, name: str) -> bool | None:
    if row[name] is None:
        return None
    return _row_bool(row, name)
