from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
import sqlite3

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowQuoteEvidence,
    FastPaperShadowReductionQuote,
)
from .shadow_cycle import FastPaperShadowCycleInput


_MAX_U64 = 2**64 - 1
_REQUIRED_COLUMNS = {
    "token_candidates": frozenset({"id", "mint"}),
    "token_mint_states": frozenset(
        {"candidate_id", "decimals", "observed_at_unix_ms"}
    ),
    "paper_quote_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "purpose",
            "provider",
            "probe_policy_version",
            "input_mint",
            "output_mint",
            "taker",
            "input_amount",
            "output_amount",
            "minimum_output_amount",
            "slippage_bps",
            "route_available",
            "quoted_at_unix_ms",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class FastPaperShadowReductionRead:
    target_exposure_fraction: float
    input_amount_raw: int

    def __post_init__(self) -> None:
        _require_fraction(
            "target_exposure_fraction",
            self.target_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
            maximum_open=True,
        )
        _require_u64(
            "input_amount_raw",
            self.input_amount_raw,
            positive=True,
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowQuoteReadPolicy:
    version: str
    candidate_id: int
    probe_policy_version: str
    taker: str
    slippage_bps: int
    entry_input_amount_raw: int
    exit_input_amount_raw: int
    max_quote_age_ms: int
    reduction_reads: tuple[FastPaperShadowReductionRead, ...] = ()

    def __post_init__(self) -> None:
        for name in ("version", "probe_policy_version", "taker"):
            _require_non_empty(name, getattr(self, name))
        _require_positive_int("candidate_id", self.candidate_id)
        if (
            isinstance(self.slippage_bps, bool)
            or not isinstance(self.slippage_bps, int)
            or not 0 <= self.slippage_bps <= 10_000
        ):
            raise ValueError("slippage_bps must be an integer within [0,10000]")
        _require_u64(
            "entry_input_amount_raw",
            self.entry_input_amount_raw,
            positive=True,
        )
        _require_u64(
            "exit_input_amount_raw",
            self.exit_input_amount_raw,
            positive=True,
        )
        if (
            isinstance(self.max_quote_age_ms, bool)
            or not isinstance(self.max_quote_age_ms, int)
            or self.max_quote_age_ms < 0
        ):
            raise ValueError("max_quote_age_ms must be a non-negative integer")
        if (
            not isinstance(self.reduction_reads, tuple)
            or not all(
                type(value) is FastPaperShadowReductionRead
                for value in self.reduction_reads
            )
        ):
            raise ValueError(
                "reduction_reads must contain exact FastPaperShadowReductionRead values"
            )
        previous: float | None = None
        for value in self.reduction_reads:
            target = float(value.target_exposure_fraction)
            if previous is not None and target <= previous:
                raise ValueError(
                    "reduction_reads targets must be strictly increasing"
                )
            previous = target


def resolve_fast_paper_shadow_cycle_input(
    manifest: FastPaperRuntimeManifest,
    record: FastTrainingFeatureRecord,
    position: FastCampaignDecisionPosition,
    read_policy: FastPaperShadowQuoteReadPolicy,
    *,
    evaluated_at_unix_ms: int,
    max_exposure_fraction: float,
    force_sell: bool = False,
) -> FastPaperShadowCycleInput:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    if type(position) is not FastCampaignDecisionPosition:
        raise ValueError("position must be exact FastCampaignDecisionPosition")
    if type(read_policy) is not FastPaperShadowQuoteReadPolicy:
        raise ValueError(
            "read_policy must be exact FastPaperShadowQuoteReadPolicy"
        )
    if (
        isinstance(evaluated_at_unix_ms, bool)
        or not isinstance(evaluated_at_unix_ms, int)
        or evaluated_at_unix_ms < record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "evaluated_at_unix_ms must be an integer at or after the decision"
        )
    _require_fraction(
        "max_exposure_fraction",
        max_exposure_fraction,
        minimum=0.0,
        maximum=1.0,
    )
    if type(force_sell) is not bool:
        raise ValueError("force_sell must be bool")
    if read_policy.version != manifest.route_evidence_version:
        raise ValueError(
            "quote read policy version does not match runtime route evidence version"
        )
    if record.quote_mint != manifest.quote_mint:
        raise ValueError(
            "feature quote mint does not match runtime manifest quote mint"
        )
    if position.kind == "FLAT" and read_policy.reduction_reads:
        raise ValueError("FLAT shadow position cannot request reduction evidence")
    if position.kind == "OPEN":
        current = position.current_exposure_fraction
        assert current is not None
        if any(
            value.target_exposure_fraction >= current
            for value in read_policy.reduction_reads
        ):
            raise ValueError(
                "reduction read target must be below current exposure"
            )

    verify_fast_paper_runtime_bindings(manifest)
    connection = _open_query_only_database(manifest.observer_database_path)
    try:
        _validate_schema(connection)
        _require_candidate_mint(
            connection,
            candidate_id=read_policy.candidate_id,
            expected_mint=record.mint,
        )
        base_decimals = _resolve_base_decimals(
            connection,
            candidate_id=read_policy.candidate_id,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

        entry = _resolve_quote(
            connection,
            manifest=manifest,
            record=record,
            read_policy=read_policy,
            purpose="entry",
            input_mint=manifest.quote_mint,
            output_mint=record.mint,
            input_amount_raw=read_policy.entry_input_amount_raw,
            base_decimals=base_decimals,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )
        exit_quote = _resolve_quote(
            connection,
            manifest=manifest,
            record=record,
            read_policy=read_policy,
            purpose="exit",
            input_mint=record.mint,
            output_mint=manifest.quote_mint,
            input_amount_raw=read_policy.exit_input_amount_raw,
            base_decimals=base_decimals,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
        )

        reductions = tuple(
            FastPaperShadowReductionQuote(
                target_exposure_fraction=value.target_exposure_fraction,
                quote=_resolve_quote(
                    connection,
                    manifest=manifest,
                    record=record,
                    read_policy=read_policy,
                    purpose="exit",
                    input_mint=record.mint,
                    output_mint=manifest.quote_mint,
                    input_amount_raw=value.input_amount_raw,
                    base_decimals=base_decimals,
                    evaluated_at_unix_ms=evaluated_at_unix_ms,
                ),
            )
            for value in read_policy.reduction_reads
        )
    finally:
        connection.close()

    verify_fast_paper_runtime_bindings(manifest)
    return FastPaperShadowCycleInput(
        record=record,
        position=position,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        max_exposure_fraction=max_exposure_fraction,
        entry_quote=entry,
        exit_quote=exit_quote,
        reduction_quotes=reductions,
        force_sell=force_sell,
    )


def _open_query_only_database(path_value: str) -> sqlite3.Connection:
    path = Path(path_value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow persisted quote database must be an existing regular non-symlink file"
        )
    try:
        source = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            "shadow persisted quote database could not be resolved"
        ) from exc

    try:
        connection = sqlite3.connect(
            f"file:{source}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        row = connection.execute("PRAGMA query_only").fetchone()
        if row is None or row[0] != 1:
            connection.close()
            raise ValueError(
                "shadow persisted quote database connection is not query-only"
            )
        return connection
    except ValueError:
        raise
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow persisted quote database could not be opened read-only"
        ) from exc


def _validate_schema(connection: sqlite3.Connection) -> None:
    try:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table, required in _REQUIRED_COLUMNS.items():
            if table not in tables:
                raise ValueError(
                    f"shadow persisted quote database is missing {table}"
                )
            columns = {
                str(row["name"])
                for row in connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            missing = required - columns
            if missing:
                raise ValueError(
                    f"shadow persisted quote database table {table} is missing required columns"
                )
    except ValueError:
        raise
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow persisted quote database schema read failed"
        ) from exc


def _require_candidate_mint(
    connection: sqlite3.Connection,
    *,
    candidate_id: int,
    expected_mint: str,
) -> None:
    try:
        rows = connection.execute(
            "SELECT mint FROM token_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError("shadow candidate attribution read failed") from exc
    if len(rows) != 1:
        raise ValueError(
            "shadow quote read policy candidate is missing or ambiguous"
        )
    mint = rows[0]["mint"]
    if not isinstance(mint, str) or mint != expected_mint:
        raise ValueError(
            "shadow quote read policy candidate mint does not match feature row"
        )


def _resolve_base_decimals(
    connection: sqlite3.Connection,
    *,
    candidate_id: int,
    evaluated_at_unix_ms: int,
) -> int:
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT decimals
            FROM token_mint_states
            WHERE candidate_id = ?
              AND observed_at_unix_ms <= ?
            ORDER BY decimals ASC
            """,
            (candidate_id, evaluated_at_unix_ms),
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError("shadow token decimals read failed") from exc
    if not rows:
        raise ValueError("shadow token decimals evidence is missing")
    values: list[int] = []
    for row in rows:
        value = row["decimals"]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 255
        ):
            raise ValueError("shadow token decimals evidence is invalid")
        values.append(value)
    if len(values) != 1:
        raise ValueError("shadow token decimals evidence is conflicting")
    return values[0]


def _resolve_quote(
    connection: sqlite3.Connection,
    *,
    manifest: FastPaperRuntimeManifest,
    record: FastTrainingFeatureRecord,
    read_policy: FastPaperShadowQuoteReadPolicy,
    purpose: str,
    input_mint: str,
    output_mint: str,
    input_amount_raw: int,
    base_decimals: int,
    evaluated_at_unix_ms: int,
) -> FastPaperShadowQuoteEvidence:
    lower_bound = max(
        record.decision_observed_at_unix_ms,
        evaluated_at_unix_ms - read_policy.max_quote_age_ms,
    )
    try:
        rows = connection.execute(
            """
            SELECT
                id, input_amount, output_amount, minimum_output_amount,
                route_available, quoted_at_unix_ms
            FROM paper_quote_snapshots
            WHERE candidate_id = ?
              AND purpose = ?
              AND provider = ?
              AND probe_policy_version = ?
              AND input_mint = ?
              AND output_mint = ?
              AND taker = ?
              AND input_amount = ?
              AND slippage_bps = ?
              AND quoted_at_unix_ms BETWEEN ? AND ?
            ORDER BY quoted_at_unix_ms DESC, id DESC
            LIMIT 2
            """,
            (
                read_policy.candidate_id,
                purpose,
                manifest.quote_provider,
                read_policy.probe_policy_version,
                input_mint,
                output_mint,
                read_policy.taker,
                str(input_amount_raw),
                read_policy.slippage_bps,
                lower_bound,
                evaluated_at_unix_ms,
            ),
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(
            f"shadow persisted {purpose.upper()} quote evidence read failed"
        ) from exc

    if not rows:
        raise ValueError(
            f"shadow persisted {purpose.upper()} quote evidence is missing or stale"
        )
    latest = rows[0]
    if (
        len(rows) > 1
        and rows[1]["quoted_at_unix_ms"] == latest["quoted_at_unix_ms"]
    ):
        raise ValueError(
            f"shadow persisted {purpose.upper()} quote evidence is ambiguous"
        )

    quoted_at = latest["quoted_at_unix_ms"]
    if (
        isinstance(quoted_at, bool)
        or not isinstance(quoted_at, int)
        or not lower_bound <= quoted_at <= evaluated_at_unix_ms
    ):
        raise ValueError(
            f"shadow persisted {purpose.upper()} quote timestamp is invalid"
        )

    stored_input = _canonical_u64(
        latest["input_amount"],
        f"{purpose} input amount",
        positive=True,
    )
    if stored_input != input_amount_raw:
        raise ValueError(
            f"shadow persisted {purpose.upper()} quote input amount changed"
        )
    output = _canonical_u64(
        latest["output_amount"],
        f"{purpose} output amount",
    )
    minimum_output = _canonical_u64(
        latest["minimum_output_amount"],
        f"{purpose} minimum output amount",
    )
    if minimum_output > output:
        raise ValueError(
            f"shadow persisted {purpose.upper()} minimum output exceeds output"
        )
    route_available = latest["route_available"]
    if type(route_available) is not int or route_available not in (0, 1):
        raise ValueError(
            f"shadow persisted {purpose.upper()} route availability is invalid"
        )

    if route_available == 0:
        if output != 0 or minimum_output != 0:
            raise ValueError(
                f"shadow persisted unavailable {purpose.upper()} quote carries output"
            )
        return FastPaperShadowQuoteEvidence(
            provider=manifest.quote_provider,
            mint=record.mint,
            quote_mint=manifest.quote_mint,
            observed_at_unix_ms=quoted_at,
            state="UNAVAILABLE",
            reference_price_quote=None,
            execution_price_quote=None,
            quoted_base_quantity=None,
            available_base_quantity=None,
        )

    if output == 0 or minimum_output == 0:
        raise ValueError(
            f"shadow persisted executable {purpose.upper()} quote has zero output"
        )
    if purpose == "entry":
        quote_input = _raw_quantity(
            input_amount_raw,
            manifest.quote_decimals,
            "entry quote input",
        )
        base_output = _raw_quantity(
            output,
            base_decimals,
            "entry base output",
        )
        base_minimum = _raw_quantity(
            minimum_output,
            base_decimals,
            "entry minimum base output",
        )
        execution_price = quote_input / base_output
        quoted_base = base_output
        available_base = base_minimum
    elif purpose == "exit":
        base_input = _raw_quantity(
            input_amount_raw,
            base_decimals,
            "exit base input",
        )
        quote_output = _raw_quantity(
            output,
            manifest.quote_decimals,
            "exit quote output",
        )
        execution_price = quote_output / base_input
        quoted_base = base_input
        available_base = base_input
    else:
        raise ValueError("unsupported shadow persisted quote purpose")

    for name, value in (
        ("execution price", execution_price),
        ("quoted base quantity", quoted_base),
        ("available base quantity", available_base),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"shadow persisted {purpose.upper()} {name} is invalid"
            )
    return FastPaperShadowQuoteEvidence(
        provider=manifest.quote_provider,
        mint=record.mint,
        quote_mint=manifest.quote_mint,
        observed_at_unix_ms=quoted_at,
        state="EXECUTABLE",
        reference_price_quote=record.decision_executable_entry_price_quote,
        execution_price_quote=execution_price,
        quoted_base_quantity=quoted_base,
        available_base_quantity=available_base,
    )


def _raw_quantity(raw: int, decimals: int, label: str) -> float:
    _require_u64(label, raw, positive=True)
    if (
        isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or not 0 <= decimals <= 255
    ):
        raise ValueError(f"{label} decimals are invalid")
    try:
        value = Decimal(raw) / (Decimal(10) ** decimals)
        result = float(value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(f"{label} cannot be converted safely") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must convert to a positive finite quantity")
    return result


def _canonical_u64(
    value: object,
    label: str,
    *,
    positive: bool = False,
) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be canonical u64 text")
    if value != "0" and value.startswith("0"):
        raise ValueError(f"{label} must be canonical u64 text")
    if not value.isascii() or not value.isdigit():
        raise ValueError(f"{label} must be canonical u64 text")
    parsed = int(value)
    _require_u64(label, parsed, positive=positive)
    if str(parsed) != value:
        raise ValueError(f"{label} must be canonical u64 text")
    return parsed


def _require_u64(
    name: str,
    value: object,
    *,
    positive: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a u64 integer")
    minimum = 1 if positive else 0
    if not minimum <= value <= _MAX_U64:
        qualifier = "positive " if positive else ""
        raise ValueError(f"{name} must be a {qualifier}u64 integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_fraction(
    name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
    maximum_open: bool = False,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")
    scalar = float(value)
    if scalar < minimum:
        raise ValueError(f"{name} is below the permitted interval")
    if maximum_open:
        if scalar >= maximum:
            raise ValueError(f"{name} is above the permitted interval")
    elif scalar > maximum:
        raise ValueError(f"{name} is above the permitted interval")
