from __future__ import annotations

from pathlib import Path
import math
import sqlite3
import time
from typing import Callable

from .feed import fetch_fast_paper_runtime_feature_batch
from .persisted_quotes import (
    FastPaperShadowQuoteReadPolicy,
    FastPaperShadowReductionRead,
    resolve_fast_paper_shadow_cycle_input,
)
from .shadow_reduction_source import (
    _record_filename as _reduction_source_record_filename,
    build_fast_paper_shadow_reduction_source_record,
    read_fast_paper_shadow_reduction_source_record,
    write_fast_paper_shadow_reduction_source_record,
)
from .shadow_runtime_state import fast_paper_shadow_decision_position
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    _resolve_candidate_id,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
)


_MAX_U64 = (1 << 64) - 1
_REL_TOL = 1e-12
_FLOAT_ABS_TOL = 1e-12


def run_fast_paper_shadow_open_quote_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperShadowServiceExecutionBootstrap,
    *,
    reduction_source_directory: str | Path,
    clock_unix_ms: Callable[[], int] | None = None,
) -> int:
    if type(decision_bootstrap) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if (
        type(execution_bootstrap)
        is not FastPaperShadowServiceExecutionBootstrap
    ):
        raise ValueError(
            "execution_bootstrap must be exact "
            "FastPaperShadowServiceExecutionBootstrap"
        )

    manifest = decision_bootstrap.manifest
    _require_bootstrap_manifest_binding(manifest, execution_bootstrap)
    source_root = _require_directory(
        reduction_source_directory,
        label="OPEN quote writer source",
    )

    preview = fetch_fast_paper_runtime_feature_batch(
        manifest,
        decision_bootstrap.state,
        maximum_decisions=1,
    )
    if not preview.records:
        return 0
    if len(preview.records) != 1:
        raise ValueError(
            "OPEN quote writer feature preview must contain at most one row"
        )
    record = preview.records[0]

    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    evaluated_at = _clock_value(
        clock,
        minimum=record.decision_observed_at_unix_ms,
    )
    market_key = f"{record.venue}:{record.mint}:{record.quote_mint}"
    position = fast_paper_shadow_decision_position(
        execution_bootstrap.runtime_state,
        market_key,
    )
    if position.kind == "FLAT":
        return 0
    mapping = _market_mapping(
        execution_bootstrap,
        market_key,
    )
    if record.mint != mapping.mint:
        raise ValueError(
            "OPEN quote writer preview mint does not match durable mapping"
        )
    if record.quote_mint != manifest.quote_mint:
        raise ValueError(
            "OPEN quote writer preview quote mint does not match runtime manifest"
        )

    source_path = source_root / _reduction_source_record_filename(
        execution_bootstrap.runtime_state.state_fingerprint_sha256,
        market_key,
    )
    if source_path.is_symlink():
        raise ValueError(
            "OPEN quote source record path must not be a symlink"
        )
    if source_path.exists():
        if not source_path.is_file():
            raise ValueError(
                "OPEN quote source record path must identify a regular file"
            )
        read_fast_paper_shadow_reduction_source_record(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.checkpoint,
            execution_bootstrap.runtime_state,
            market_key,
            source_root,
        )
        return 0

    policy = decision_bootstrap.policy
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=record.mint,
        quote_mint=record.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            record.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evaluated_at,
        max_quote_age_ms=policy.max_quote_age_ms,
    )
    minimum_observed_at = max(
        record.decision_observed_at_unix_ms,
        evaluated_at - policy.max_quote_age_ms,
    )
    persisted_inputs = _persisted_exit_input_amounts(
        manifest.observer_database_path,
        candidate_id=candidate_id,
        mint=record.mint,
        quote_mint=manifest.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        minimum_observed_at_unix_ms=minimum_observed_at,
        evaluated_at_unix_ms=evaluated_at,
    )
    if mapping.current_base_quantity_raw not in persisted_inputs:
        return 0

    reduction_reads = _select_reduction_reads(
        manifest.action_policy.reduce_target_exposure_candidates,
        persisted_inputs,
        current_base_quantity_raw=mapping.current_base_quantity_raw,
        current_exposure_fraction=mapping.current_exposure_fraction,
    )
    if reduction_reads is None:
        return 0

    quote_read_policy = FastPaperShadowQuoteReadPolicy(
        version=policy.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        exit_input_amount_raw=mapping.current_base_quantity_raw,
        max_quote_age_ms=policy.max_quote_age_ms,
        reduction_reads=reduction_reads,
    )
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        position,
        quote_read_policy,
        evaluated_at_unix_ms=evaluated_at,
        max_exposure_fraction=policy.max_exposure_fraction,
        force_sell=False,
    )
    _require_replayed_raw_authority(
        cycle,
        full_exit_input_amount_raw=mapping.current_base_quantity_raw,
        reduction_reads=reduction_reads,
    )

    source = build_fast_paper_shadow_reduction_source_record(
        manifest,
        execution_bootstrap.binding,
        execution_bootstrap.checkpoint,
        execution_bootstrap.runtime_state,
        market_key,
        reduction_reads,
    )
    try:
        write_fast_paper_shadow_reduction_source_record(
            source,
            source_root,
        )
    except FileExistsError:
        restored = read_fast_paper_shadow_reduction_source_record(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.checkpoint,
            execution_bootstrap.runtime_state,
            market_key,
            source_root,
        )
        if restored != source:
            raise ValueError(
                "OPEN quote writer collision read-back mismatch"
            )
        return 0
    return 1


def _select_reduction_reads(
    targets: tuple[float, ...],
    persisted_inputs: tuple[int, ...],
    *,
    current_base_quantity_raw: int,
    current_exposure_fraction: float,
) -> tuple[FastPaperShadowReductionRead, ...] | None:
    eligible_targets = tuple(
        target
        for target in targets
        if target < current_exposure_fraction
    )
    selected: list[FastPaperShadowReductionRead] = []
    for target in eligible_targets:
        matches = tuple(
            value
            for value in persisted_inputs
            if _matches_reduction_target(
                input_amount_raw=value,
                current_base_quantity_raw=current_base_quantity_raw,
                current_exposure_fraction=current_exposure_fraction,
                target_exposure_fraction=target,
            )
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError(
                "OPEN quote writer persisted reduction target raw authority "
                "is ambiguous"
            )
        selected.append(
            FastPaperShadowReductionRead(
                target_exposure_fraction=target,
                input_amount_raw=matches[0],
            )
        )
    return tuple(selected)


def _matches_reduction_target(
    *,
    input_amount_raw: int,
    current_base_quantity_raw: int,
    current_exposure_fraction: float,
    target_exposure_fraction: float,
) -> bool:
    _require_u64(
        "input_amount_raw",
        input_amount_raw,
        positive=True,
    )
    _require_u64(
        "current_base_quantity_raw",
        current_base_quantity_raw,
        positive=True,
    )
    if input_amount_raw >= current_base_quantity_raw:
        return False
    _require_exposure(
        "current_exposure_fraction",
        current_exposure_fraction,
    )
    if (
        isinstance(target_exposure_fraction, bool)
        or not isinstance(target_exposure_fraction, (int, float))
        or not math.isfinite(float(target_exposure_fraction))
        or not 0.0 <= float(target_exposure_fraction)
        < float(current_exposure_fraction)
    ):
        raise ValueError(
            "target_exposure_fraction must be finite within current exposure"
        )

    remaining_raw = current_base_quantity_raw - input_amount_raw
    remaining_exposure = (
        float(current_exposure_fraction)
        * remaining_raw
        / current_base_quantity_raw
    )
    half_raw_unit_exposure = (
        float(current_exposure_fraction)
        / (2.0 * current_base_quantity_raw)
    )
    tolerance = max(_FLOAT_ABS_TOL, half_raw_unit_exposure)
    return math.isclose(
        remaining_exposure,
        float(target_exposure_fraction),
        rel_tol=_REL_TOL,
        abs_tol=tolerance,
    )


def _persisted_exit_input_amounts(
    database_path: str | Path,
    *,
    candidate_id: int,
    mint: str,
    quote_mint: str,
    provider: str,
    probe_policy_version: str,
    taker: str,
    slippage_bps: int,
    minimum_observed_at_unix_ms: int,
    evaluated_at_unix_ms: int,
) -> tuple[int, ...]:
    path = Path(database_path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "OPEN quote writer observer database must be an existing "
            "regular non-symlink file"
        )
    source = path.resolve(strict=True)
    try:
        connection = sqlite3.connect(
            f"file:{source}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        query_only = connection.execute(
            "PRAGMA query_only"
        ).fetchone()
        if query_only is None or query_only[0] != 1:
            connection.close()
            raise ValueError(
                "OPEN quote writer observer database is not query-only"
            )
    except ValueError:
        raise
    except sqlite3.Error as exc:
        raise ValueError(
            "OPEN quote writer observer database could not be opened read-only"
        ) from exc

    try:
        rows = connection.execute(
            """
            SELECT input_amount
            FROM paper_quote_snapshots
            WHERE candidate_id = ?
              AND purpose = 'exit'
              AND provider = ?
              AND probe_policy_version = ?
              AND input_mint = ?
              AND output_mint = ?
              AND taker = ?
              AND slippage_bps = ?
              AND quoted_at_unix_ms BETWEEN ? AND ?
            ORDER BY input_amount ASC, quoted_at_unix_ms ASC, id ASC
            """,
            (
                candidate_id,
                provider,
                probe_policy_version,
                mint,
                quote_mint,
                taker,
                slippage_bps,
                minimum_observed_at_unix_ms,
                evaluated_at_unix_ms,
            ),
        ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(
            "OPEN quote writer persisted EXIT input read failed"
        ) from exc
    finally:
        connection.close()

    values = {
        _canonical_u64_text(
            row["input_amount"],
            "OPEN quote writer EXIT input amount",
            positive=True,
        )
        for row in rows
    }
    return tuple(sorted(values))


def _require_replayed_raw_authority(
    cycle,
    *,
    full_exit_input_amount_raw: int,
    reduction_reads: tuple[FastPaperShadowReductionRead, ...],
) -> None:
    if cycle.exit_quote.input_amount_raw != full_exit_input_amount_raw:
        raise ValueError(
            "OPEN quote writer replayed full EXIT raw authority mismatch"
        )
    if len(cycle.reduction_quotes) != len(reduction_reads):
        raise ValueError(
            "OPEN quote writer replayed reduction quote count mismatch"
        )
    for expected, replayed in zip(
        reduction_reads,
        cycle.reduction_quotes,
        strict=True,
    ):
        if (
            replayed.target_exposure_fraction
            != expected.target_exposure_fraction
            or replayed.quote.input_amount_raw
            != expected.input_amount_raw
        ):
            raise ValueError(
                "OPEN quote writer replayed reduction raw authority mismatch"
            )


def _market_mapping(
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    market_key: str,
):
    matches = tuple(
        value
        for value in bootstrap.runtime_state.market_positions
        if value.market_key == market_key
    )
    if len(matches) != 1:
        raise ValueError(
            "OPEN quote writer requires exactly one durable market mapping"
        )
    return matches[0]


def _require_bootstrap_manifest_binding(
    manifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
) -> None:
    if (
        bootstrap.binding.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN quote writer ledger binding does not match runtime manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN quote writer execution policy does not match runtime manifest"
        )
    if (
        bootstrap.runtime_state.binding_fingerprint_sha256
        != bootstrap.binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN quote writer runtime state does not match ledger binding"
        )


def _require_directory(
    value: str | Path,
    *,
    label: str,
) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return root.resolve(strict=True)


def _clock_value(
    clock: Callable[[], int],
    *,
    minimum: int,
) -> int:
    try:
        value = clock()
    except Exception as exc:
        raise ValueError("OPEN quote writer clock failed") from exc
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise ValueError(
            "OPEN quote writer clock must not precede feature decision"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _canonical_u64_text(
    value: object,
    label: str,
    *,
    positive: bool,
) -> int:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
        or (value != "0" and value.startswith("0"))
    ):
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
    positive: bool,
) -> None:
    minimum = 1 if positive else 0
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= _MAX_U64
    ):
        qualifier = "positive " if positive else ""
        raise ValueError(f"{name} must be a {qualifier}u64 integer")


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ValueError(
            f"{name} must be finite within (0,1]"
        )
