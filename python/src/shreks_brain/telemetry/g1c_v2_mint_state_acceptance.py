from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from shreks_brain.observer_campaign.coordinator import (
    ObserverCampaignCoordinatorError,
    assemble_observer_paper_campaign_cycle,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.paper_validation import PaperCheckpointError, decode_paper_checkpoint


ACCEPTANCE_SCHEMA_NAME = "shreks.g1c_v2_mint_state_acceptance"
ACCEPTANCE_SCHEMA_VERSION = 1
_MAX_CHECKPOINT_ROWS = 2_048


_ERROR_CODES = frozenset(
    {
        "INPUT_INVALID",
        "MANIFEST_VALIDATION_FAILED",
        "DATABASE_OPEN_FAILED",
        "CHECKPOINT_WINDOW_READ_FAILED",
        "CHECKPOINT_WINDOW_TOO_LARGE",
        "CHECKPOINT_DECODE_FAILED",
        "CHECKPOINT_SEQUENCE_INVALID",
        "CHECKPOINT_TIME_INVALID",
        "CYCLE_RECONSTRUCTION_FAILED",
        "CYCLE_RECONSTRUCTION_REQUIRED_MINT_FAILED",
        "CYCLE_RECONSTRUCTION_CANDIDATE_SELECTION_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_MARKET_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_QUOTE_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_SAFETY_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_WINDOW_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_MARKET_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_SAFETY_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED",
        "CYCLE_RECONSTRUCTION_COMPONENT_OTHER_FAILED",
        "CYCLE_RECONSTRUCTION_AGGREGATION_FAILED",
        "CANDIDATE_ATTRIBUTION_INVALID",
        "MINT_STATE_READ_FAILED",
        "MINT_STATE_VALUE_INVALID",
    }
)


class MintStateAcceptanceError(ValueError):
    """Raised when read-only mint-state acceptance evidence cannot be trusted."""

    def __init__(self, message: str, *, code: str = "INPUT_INVALID") -> None:
        if code not in _ERROR_CODES:
            raise ValueError("unsupported mint-state acceptance error code")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MintStateAcceptanceSample:
    candidate_id: int
    decision_as_of_unix_ms: int
    mint_observed_at_unix_ms: int | None
    previous_mint_observed_at_unix_ms: int | None

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_negative_int(
            "decision_as_of_unix_ms", self.decision_as_of_unix_ms
        )
        _require_optional_non_negative_int(
            "mint_observed_at_unix_ms", self.mint_observed_at_unix_ms
        )
        _require_optional_non_negative_int(
            "previous_mint_observed_at_unix_ms",
            self.previous_mint_observed_at_unix_ms,
        )


def derive_mint_state_refresh_age_ms(
    *,
    max_critical_data_age_ms: int,
    evidence_cycle_interval_ms: int,
) -> int:
    _require_non_negative_int(
        "max_critical_data_age_ms", max_critical_data_age_ms
    )
    _require_positive_int(
        "evidence_cycle_interval_ms", evidence_cycle_interval_ms
    )
    scheduler_headroom_ms = 6 * evidence_cycle_interval_ms
    bounded_headroom_ms = min(
        scheduler_headroom_ms,
        max_critical_data_age_ms // 2,
    )
    return max_critical_data_age_ms - bounded_headroom_ms


def evaluate_mint_state_acceptance_samples(
    samples: tuple[MintStateAcceptanceSample, ...],
    *,
    max_critical_data_age_ms: int,
    evidence_cycle_interval_ms: int,
) -> dict[str, object]:
    if not isinstance(samples, tuple) or any(
        type(sample) is not MintStateAcceptanceSample for sample in samples
    ):
        raise MintStateAcceptanceError(
            "samples must be a tuple of exact MintStateAcceptanceSample values"
        )
    refresh_age_ms = derive_mint_state_refresh_age_ms(
        max_critical_data_age_ms=max_critical_data_age_ms,
        evidence_cycle_interval_ms=evidence_cycle_interval_ms,
    )

    missing = 0
    stale = 0
    invalid = 0
    max_selected_age: int | None = None
    proactive_transitions: set[tuple[int, int, int]] = set()

    for sample in samples:
        current = sample.mint_observed_at_unix_ms
        previous = sample.previous_mint_observed_at_unix_ms

        if current is None:
            missing += 1
            if previous is not None:
                invalid += 1
            continue
        if current > sample.decision_as_of_unix_ms:
            invalid += 1
            continue

        age_ms = sample.decision_as_of_unix_ms - current
        max_selected_age = (
            age_ms
            if max_selected_age is None
            else max(max_selected_age, age_ms)
        )
        if age_ms > max_critical_data_age_ms:
            stale += 1

        if previous is None:
            continue
        if previous >= current:
            invalid += 1
            continue
        gap_ms = current - previous
        if refresh_age_ms < gap_ms <= max_critical_data_age_ms:
            proactive_transitions.add(
                (sample.candidate_id, current, previous)
            )

    if missing or stale or invalid:
        status = "FAILED"
    elif samples and proactive_transitions:
        status = "PASS"
    else:
        status = "HOLD_INSUFFICIENT_EVIDENCE"

    return {
        "schema_name": ACCEPTANCE_SCHEMA_NAME,
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "status": status,
        "max_critical_data_age_ms": max_critical_data_age_ms,
        "evidence_cycle_interval_ms": evidence_cycle_interval_ms,
        "mint_state_refresh_age_ms": refresh_age_ms,
        "selected_observation_count": len(samples),
        "proactive_refresh_count": len(proactive_transitions),
        "selected_missing_mint_count": missing,
        "selected_stale_mint_count": stale,
        "invalid_observation_count": invalid,
        "max_selected_mint_age_ms": max_selected_age,
    }


def analyze_mint_state_acceptance(
    database_path: str | Path,
    manifest_path: str | Path,
    *,
    window_start_unix_ms: int,
    window_end_unix_ms: int,
    evidence_cycle_interval_ms: int,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, object]:
    _require_non_negative_int("window_start_unix_ms", window_start_unix_ms)
    _require_non_negative_int("window_end_unix_ms", window_end_unix_ms)
    if window_end_unix_ms < window_start_unix_ms:
        raise MintStateAcceptanceError(
            "window_end_unix_ms cannot precede window_start_unix_ms"
        )
    _require_positive_int(
        "evidence_cycle_interval_ms", evidence_cycle_interval_ms
    )

    _emit_progress(progress_callback, "MANIFEST_VALIDATION")
    try:
        database = _require_existing_file(database_path, "observer database")
    except MintStateAcceptanceError as error:
        raise MintStateAcceptanceError(
            "observer database validation failed",
            code="DATABASE_OPEN_FAILED",
        ) from error
    try:
        manifest_file = _require_existing_file(manifest_path, "campaign manifest")
    except MintStateAcceptanceError as error:
        raise MintStateAcceptanceError(
            "campaign manifest validation failed",
            code="MANIFEST_VALIDATION_FAILED",
        ) from error
    try:
        manifest = decode_observer_paper_campaign_runtime_manifest(
            manifest_file.read_bytes()
        )
    except (OSError, ObserverPaperCampaignRuntimeManifestError) as error:
        raise MintStateAcceptanceError(
            "campaign manifest validation failed",
            code="MANIFEST_VALIDATION_FAILED",
        ) from error

    _emit_progress(progress_callback, "DATABASE_OPEN")
    try:
        connection = _connect_read_only(database)
    except MintStateAcceptanceError as error:
        raise MintStateAcceptanceError(
            "observer database could not be opened read-only",
            code="DATABASE_OPEN_FAILED",
        ) from error
    try:
        _emit_progress(progress_callback, "CHECKPOINT_WINDOW_READ")
        try:
            previous_row = connection.execute(
            """SELECT sequence, state_as_of_unix_ms, payload_sha256, payload_json
               FROM paper_loop_checkpoints
               WHERE run_id = ?
                 AND state_as_of_unix_ms < ?
               ORDER BY sequence DESC
               LIMIT 1""",
            (manifest.paper_run_id, window_start_unix_ms),
            ).fetchone()
            rows = connection.execute(
            """SELECT sequence, state_as_of_unix_ms, payload_sha256, payload_json
               FROM paper_loop_checkpoints
               WHERE run_id = ?
                 AND state_as_of_unix_ms BETWEEN ? AND ?
               ORDER BY sequence ASC
               LIMIT ?""",
            (
                manifest.paper_run_id,
                window_start_unix_ms,
                window_end_unix_ms,
                _MAX_CHECKPOINT_ROWS + 1,
            ),
            ).fetchall()
        except sqlite3.Error as error:
            raise MintStateAcceptanceError(
                "acceptance checkpoint window read failed",
                code="CHECKPOINT_WINDOW_READ_FAILED",
            ) from error
        if len(rows) > _MAX_CHECKPOINT_ROWS:
            raise MintStateAcceptanceError(
                "acceptance checkpoint window exceeds bounded row limit",
                code="CHECKPOINT_WINDOW_TOO_LARGE",
            )

        if previous_row is None:
            previous_state = manifest.initial_state
            previous_sequence = 0
        else:
            _emit_progress(progress_callback, "CHECKPOINT_DECODE")
            previous = _decode_checkpoint_row(previous_row)
            previous_state = previous.state
            previous_sequence = previous.sequence

        samples: list[MintStateAcceptanceSample] = []
        reconstructed_checkpoints = 0
        for row in rows:
            _emit_progress(progress_callback, "CHECKPOINT_DECODE")
            checkpoint = _decode_checkpoint_row(row)
            if checkpoint.sequence != previous_sequence + 1:
                raise MintStateAcceptanceError(
                    "paper checkpoint sequence is not contiguous",
                    code="CHECKPOINT_SEQUENCE_INVALID",
                )
            if checkpoint.state_as_of_unix_ms < previous_state.last_cycle_at_unix_ms:
                raise MintStateAcceptanceError(
                    "paper checkpoint time moved backwards",
                    code="CHECKPOINT_TIME_INVALID",
                )

            quote_policy = manifest.quote_usd_valuation_policy
            quote_mode = None if quote_policy is None else quote_policy.mode.value
            _emit_progress(progress_callback, "CYCLE_RECONSTRUCTION")
            try:
                _cycle, audit = assemble_observer_paper_campaign_cycle(
                    database,
                    previous_state,
                    checkpoint.state_as_of_unix_ms,
                    manifest.policy_bundle,
                    manifest.risk_environment,
                    manifest.selection_policy,
                    quote_usd_valuation_mode=quote_mode,
                    recent_performance=manifest.recent_performance,
                    global_risk_halt=manifest.global_risk_halt,
                    progress_callback=(
                        None
                        if progress_callback is None
                        else lambda stage: _emit_progress(
                            progress_callback,
                            f"CYCLE_RECONSTRUCTION_{stage}",
                        )
                    ),
                )
            except ObserverCampaignCoordinatorError as error:
                raise MintStateAcceptanceError(
                    "historical PAPER candidate reconstruction failed",
                    code=_classify_cycle_reconstruction_error(error),
                ) from error
            except (OSError, TypeError, ValueError) as error:
                raise MintStateAcceptanceError(
                    "historical PAPER candidate reconstruction failed",
                    code="CYCLE_RECONSTRUCTION_FAILED",
                ) from error

            if len(audit.selected_candidate_ids) != len(audit.selected_mints):
                raise MintStateAcceptanceError(
                    "historical PAPER candidate attribution is inconsistent",
                    code="CANDIDATE_ATTRIBUTION_INVALID",
                )
            for candidate_id, mint in zip(
                audit.selected_candidate_ids,
                audit.selected_mints,
                strict=True,
            ):
                _emit_progress(progress_callback, "MINT_STATE_READ")
                try:
                    current, previous_mint = _mint_state_times(
                        connection,
                        candidate_id=candidate_id,
                        mint=mint,
                        as_of_unix_ms=checkpoint.state_as_of_unix_ms,
                    )
                except sqlite3.Error as error:
                    raise MintStateAcceptanceError(
                        "historical mint-state read failed",
                        code="MINT_STATE_READ_FAILED",
                    ) from error
                except MintStateAcceptanceError as error:
                    raise MintStateAcceptanceError(
                        "historical mint-state value is invalid",
                        code="MINT_STATE_VALUE_INVALID",
                    ) from error
                samples.append(
                    MintStateAcceptanceSample(
                        candidate_id=candidate_id,
                        decision_as_of_unix_ms=checkpoint.state_as_of_unix_ms,
                        mint_observed_at_unix_ms=current,
                        previous_mint_observed_at_unix_ms=previous_mint,
                    )
                )

            previous_state = checkpoint.state
            previous_sequence = checkpoint.sequence
            reconstructed_checkpoints += 1

        result = evaluate_mint_state_acceptance_samples(
            tuple(samples),
            max_critical_data_age_ms=(
                manifest.policy_bundle.safety_policy.max_critical_data_age_ms
            ),
            evidence_cycle_interval_ms=evidence_cycle_interval_ms,
        )
        _emit_progress(progress_callback, "ANALYSIS_COMPLETE")
        return {
            **result,
            "paper_run_id": manifest.paper_run_id,
            "reconstructed_checkpoint_count": reconstructed_checkpoints,
            "window_start_unix_ms": window_start_unix_ms,
            "window_end_unix_ms": window_end_unix_ms,
        }
    except MintStateAcceptanceError:
        raise
    except sqlite3.Error as error:
        raise MintStateAcceptanceError(
            "acceptance SQLite read failed",
            code="CHECKPOINT_WINDOW_READ_FAILED",
        ) from error
    finally:
        connection.close()


def _decode_checkpoint_row(row: sqlite3.Row):
    payload = row["payload_json"]
    checksum = row["payload_sha256"]
    if not isinstance(payload, str) or not isinstance(checksum, str):
        raise MintStateAcceptanceError(
            "paper checkpoint row contains invalid payload metadata",
            code="CHECKPOINT_DECODE_FAILED",
        )
    try:
        record = decode_paper_checkpoint(
            payload.encode("utf-8"),
            expected_sha256=checksum,
        )
    except (PaperCheckpointError, TypeError, ValueError) as error:
        raise MintStateAcceptanceError(
            "paper checkpoint validation failed",
            code="CHECKPOINT_DECODE_FAILED",
        ) from error
    if (
        record.sequence != row["sequence"]
        or record.state_as_of_unix_ms != row["state_as_of_unix_ms"]
    ):
        raise MintStateAcceptanceError(
            "paper checkpoint row metadata does not match payload",
            code="CHECKPOINT_DECODE_FAILED",
        )
    return record


def _mint_state_times(
    connection: sqlite3.Connection,
    *,
    candidate_id: int,
    mint: str,
    as_of_unix_ms: int,
) -> tuple[int | None, int | None]:
    rows = connection.execute(
        """SELECT state.observed_at_unix_ms
           FROM token_mint_states AS state
           JOIN token_candidates AS candidate
             ON candidate.id = state.candidate_id
           WHERE state.candidate_id = ?
             AND candidate.mint = ?
             AND state.provider = 'helius'
             AND state.observed_at_unix_ms <= ?
           ORDER BY state.observed_at_unix_ms DESC, state.id ASC
           LIMIT 2""",
        (candidate_id, mint, as_of_unix_ms),
    ).fetchall()
    if not rows:
        return None, None
    current = _sqlite_non_negative_int(
        rows[0]["observed_at_unix_ms"],
        "mint observed_at_unix_ms",
    )
    previous = (
        None
        if len(rows) == 1
        else _sqlite_non_negative_int(
            rows[1]["observed_at_unix_ms"],
            "previous mint observed_at_unix_ms",
        )
    )
    return current, previous


def _connect_read_only(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection
    except sqlite3.Error as error:
        raise MintStateAcceptanceError(
            "observer database could not be opened read-only",
            code="DATABASE_OPEN_FAILED",
        ) from error


def _require_existing_file(value: str | Path, label: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, TypeError, ValueError) as error:
        raise MintStateAcceptanceError(f"{label} path is invalid") from error
    if not path.is_file():
        raise MintStateAcceptanceError(f"{label} is not a regular file")
    return path


def _sqlite_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MintStateAcceptanceError(
            f"{label} is not a non-negative integer",
            code="MINT_STATE_VALUE_INVALID",
        )
    return value


def _require_optional_non_negative_int(name: str, value: int | None) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MintStateAcceptanceError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: int) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise MintStateAcceptanceError(f"{name} must be positive")


def _classify_cycle_reconstruction_error(
    error: ObserverCampaignCoordinatorError,
) -> str:
    message = str(error).strip().lower()

    if (
        message.startswith("required observer candidate")
        or message.startswith("required observer candidate read failed")
        or message.startswith("required observer candidate evidence is invalid")
    ):
        return "CYCLE_RECONSTRUCTION_REQUIRED_MINT_FAILED"

    if (
        message.startswith("recent observer candidate")
        or message.startswith("observer campaign recent-candidate")
        or message.startswith("observer campaign quote-identity")
        or message.startswith("observer campaign database missing")
        or message.startswith("observer campaign schema")
    ):
        return "CYCLE_RECONSTRUCTION_CANDIDATE_SELECTION_FAILED"

    if message.startswith("observer candidate ") and " assembly failed:" in message:
        detail = message.split(" assembly failed:", 1)[1]
        regime_code = _classify_regime_reconstruction_detail(detail)
        if regime_code is not None:
            return regime_code
        if any(
            token in detail
            for token in (
                "quote",
                "valuation",
                "route",
                "token decimal",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_QUOTE_FAILED"
        if any(
            token in detail
            for token in (
                "safety",
                "critical data",
                "mint state",
                "holder",
                "authority",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_SAFETY_FAILED"
        if "regime" in detail:
            return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED"
        if any(
            token in detail
            for token in (
                "market",
                "snapshot",
                "price",
                "liquidity",
                "pair",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_MARKET_FAILED"
        return "CYCLE_RECONSTRUCTION_COMPONENT_OTHER_FAILED"

    if (
        message.startswith("aggregate paper cycle")
        or message.startswith("component paper cycle")
        or message.startswith("entry score reconstruction")
        or message.startswith("conflicting duplicate")
        or "resolved to conflicting identities" in message
        or "entry ordering supports" in message
    ):
        return "CYCLE_RECONSTRUCTION_AGGREGATION_FAILED"

    return "CYCLE_RECONSTRUCTION_FAILED"


def _classify_regime_reconstruction_detail(detail: str) -> str | None:
    canonical = detail.strip().lower()

    if "aggregate regime consumed evidence is not inside the requested window" in canonical:
        return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_WINDOW_FAILED"

    replay_prefix = "observer aggregate regime replay failed:"
    if replay_prefix in canonical:
        nested = canonical.split(replay_prefix, 1)[1]
        if any(
            token in nested
            for token in (
                "safety",
                "critical data",
                "mint state",
                "holder",
                "authority",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_SAFETY_FAILED"
        if any(
            token in nested
            for token in (
                "quote",
                "route",
                "slippage",
                "input amount",
                "output amount",
                "probe policy",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED"
        if any(
            token in nested
            for token in (
                "market",
                "snapshot",
                "price",
                "liquidity",
                "volume",
                "pair",
                "candidate",
            )
        ):
            return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_MARKET_FAILED"
        return "CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED"

    return None


def _emit_progress(
    callback: Callable[[str], None] | None,
    stage: str,
) -> None:
    if callback is None:
        return
    try:
        callback(stage)
    except Exception:
        return
