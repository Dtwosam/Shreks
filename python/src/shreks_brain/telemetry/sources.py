from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from shreks_brain.evaluation import EvaluatedTrade
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    bootstrap_observer_paper_campaign_runtime,
)
from shreks_brain.observer_campaign.runtime_config import (
    ObserverPaperCampaignRuntimeConfig,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifest,
)
from shreks_brain.paper_loop import PaperLoopState
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    validate_paper_accounting,
)
from shreks_brain.proof import CandidateProofAssessment
from shreks_brain.proof.store import CandidateProofAssessmentStore
from shreks_brain.promotion import PromotionAssessment
from shreks_brain.promotion.store import PromotionAssessmentStore


class TelemetrySourceError(RuntimeError):
    """Raised when required G4 telemetry source evidence cannot be trusted."""


@dataclass(frozen=True, slots=True)
class TelemetrySourceConfig:
    runtime_config: ObserverPaperCampaignRuntimeConfig
    proof_path: Path
    promotion_path: Path

    def __post_init__(self) -> None:
        if type(self.runtime_config) is not ObserverPaperCampaignRuntimeConfig:
            raise ValueError(
                "runtime_config must be an exact ObserverPaperCampaignRuntimeConfig"
            )
        for name in ("proof_path", "promotion_path"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be a Path")


@dataclass(frozen=True, slots=True)
class OperationalTelemetrySources:
    provider_count: int
    unhealthy_provider_count: int
    candidate_count: int
    latest_ingestion_checkpoint_at_unix_ms: int | None
    latest_market_observed_at_unix_ms: int | None
    holder_distribution_count: int
    paper_quote_count: int

    def __post_init__(self) -> None:
        for name in (
            "provider_count",
            "unhealthy_provider_count",
            "candidate_count",
            "holder_distribution_count",
            "paper_quote_count",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if self.unhealthy_provider_count > self.provider_count:
            raise ValueError("unhealthy_provider_count cannot exceed provider_count")
        for name in (
            "latest_ingestion_checkpoint_at_unix_ms",
            "latest_market_observed_at_unix_ms",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_int(name, value)


@dataclass(frozen=True, slots=True)
class TelemetrySources:
    as_of_unix_ms: int
    operational: OperationalTelemetrySources
    manifest: ObserverPaperCampaignRuntimeManifest
    state: PaperLoopState
    accounting_status: str
    evaluated_trades: tuple[EvaluatedTrade, ...]
    proof_assessments: tuple[CandidateProofAssessment, ...]
    promotion_assessments: tuple[PromotionAssessment, ...]
    optional_source_errors: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if type(self.operational) is not OperationalTelemetrySources:
            raise ValueError("operational must be an exact OperationalTelemetrySources")
        if type(self.manifest) is not ObserverPaperCampaignRuntimeManifest:
            raise ValueError(
                "manifest must be an exact ObserverPaperCampaignRuntimeManifest"
            )
        if type(self.state) is not PaperLoopState:
            raise ValueError("state must be an exact PaperLoopState")
        if self.accounting_status not in ("VALID", "INCOMPLETE"):
            raise ValueError("accounting_status must be VALID or INCOMPLETE")
        _require_exact_tuple("evaluated_trades", self.evaluated_trades, EvaluatedTrade)
        _require_exact_tuple(
            "proof_assessments", self.proof_assessments, CandidateProofAssessment
        )
        _require_exact_tuple(
            "promotion_assessments", self.promotion_assessments, PromotionAssessment
        )
        if not isinstance(self.optional_source_errors, tuple) or not all(
            isinstance(value, str) and value.strip()
            for value in self.optional_source_errors
        ):
            raise ValueError(
                "optional_source_errors must be a tuple of non-empty strings"
            )
        if len(self.optional_source_errors) != len(set(self.optional_source_errors)):
            raise ValueError("optional_source_errors must not contain duplicates")


def collect_telemetry_sources(
    config: TelemetrySourceConfig,
    *,
    as_of_unix_ms: int,
) -> TelemetrySources:
    if type(config) is not TelemetrySourceConfig:
        raise TelemetrySourceError("config must be an exact TelemetrySourceConfig")
    try:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    except ValueError as error:
        raise TelemetrySourceError(str(error)) from error

    operational = _collect_operational_sources(
        config.runtime_config.observer_database_path,
        as_of_unix_ms,
    )

    try:
        bootstrap = bootstrap_observer_paper_campaign_runtime(config.runtime_config)
        state = bootstrap.restored_state
        if state.last_cycle_at_unix_ms > as_of_unix_ms:
            raise TelemetrySourceError(
                "paper state is later than telemetry observation timestamp"
            )
        accounting = validate_paper_accounting(state)
        if accounting.status is AccountingValidationStatus.INVALID:
            raise TelemetrySourceError("paper accounting is invalid")
        accounting_status = (
            "VALID"
            if accounting.status is AccountingValidationStatus.RECONCILED
            else "INCOMPLETE"
        )
        evaluated_trades = tuple(bootstrap.runner.evaluated_trades())
    except TelemetrySourceError:
        raise
    except (ObserverPaperCampaignRuntimeError, OSError, TypeError, ValueError) as error:
        raise TelemetrySourceError("required PAPER telemetry source is invalid") from error

    proof_assessments, proof_error = _load_optional_proof(config.proof_path)
    promotion_assessments, promotion_error = _load_optional_promotion(
        config.promotion_path
    )
    optional_errors = tuple(
        value for value in (proof_error, promotion_error) if value is not None
    )

    return TelemetrySources(
        as_of_unix_ms=as_of_unix_ms,
        operational=operational,
        manifest=bootstrap.manifest,
        state=state,
        accounting_status=accounting_status,
        evaluated_trades=evaluated_trades,
        proof_assessments=proof_assessments,
        promotion_assessments=promotion_assessments,
        optional_source_errors=optional_errors,
    )


def _collect_operational_sources(
    database_path: Path,
    as_of_unix_ms: int,
) -> OperationalTelemetrySources:
    if not database_path.exists() or not database_path.is_file():
        raise TelemetrySourceError("operational database is unavailable")

    try:
        uri = database_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            _validate_operational_schema(connection)
            provider_count = _scalar_count(
                connection,
                "SELECT COUNT(*) FROM provider_health WHERE observed_at_unix_ms <= ?",
                as_of_unix_ms,
            )
            unhealthy_provider_count = _scalar_count(
                connection,
                "SELECT COUNT(*) FROM provider_health "
                "WHERE observed_at_unix_ms <= ? AND status != 'healthy'",
                as_of_unix_ms,
            )
            candidate_count = _scalar_count(
                connection,
                "SELECT COUNT(*) FROM token_candidates WHERE discovered_at_unix_ms <= ?",
                as_of_unix_ms,
            )
            holder_distribution_count = _scalar_count(
                connection,
                "SELECT COUNT(*) FROM token_holder_distributions "
                "WHERE observed_at_unix_ms <= ?",
                as_of_unix_ms,
            )
            paper_quote_count = _scalar_count(
                connection,
                "SELECT COUNT(*) FROM paper_quote_snapshots "
                "WHERE quoted_at_unix_ms <= ?",
                as_of_unix_ms,
            )
            latest_ingestion = _optional_scalar_int(
                connection,
                "SELECT MAX(updated_at_unix_ms) FROM ingestion_checkpoints "
                "WHERE updated_at_unix_ms <= ?",
                as_of_unix_ms,
            )
            latest_market = _optional_scalar_int(
                connection,
                "SELECT MAX(observed_at_unix_ms) FROM market_snapshots "
                "WHERE observed_at_unix_ms <= ?",
                as_of_unix_ms,
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        raise TelemetrySourceError("operational database is invalid") from error

    return OperationalTelemetrySources(
        provider_count=provider_count,
        unhealthy_provider_count=unhealthy_provider_count,
        candidate_count=candidate_count,
        latest_ingestion_checkpoint_at_unix_ms=latest_ingestion,
        latest_market_observed_at_unix_ms=latest_market,
        holder_distribution_count=holder_distribution_count,
        paper_quote_count=paper_quote_count,
    )


def _validate_operational_schema(connection: sqlite3.Connection) -> None:
    required = {
        "provider_health": {
            "status",
            "observed_at_unix_ms",
        },
        "token_candidates": {"discovered_at_unix_ms"},
        "market_snapshots": {"observed_at_unix_ms"},
        "ingestion_checkpoints": {"updated_at_unix_ms"},
        "token_holder_distributions": {"observed_at_unix_ms"},
        "paper_quote_snapshots": {"quoted_at_unix_ms"},
    }
    for table, required_columns in required.items():
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {str(row[1]) for row in rows}
        if not rows or not required_columns.issubset(columns):
            raise TelemetrySourceError(
                f"operational database schema is missing required table: {table}"
            )


def _scalar_count(
    connection: sqlite3.Connection,
    query: str,
    as_of_unix_ms: int,
) -> int:
    row = connection.execute(query, (as_of_unix_ms,)).fetchone()
    if row is None or len(row) != 1:
        raise TelemetrySourceError("operational database count query failed")
    value = row[0]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetrySourceError("operational database count is invalid")
    return value


def _optional_scalar_int(
    connection: sqlite3.Connection,
    query: str,
    as_of_unix_ms: int,
) -> int | None:
    row = connection.execute(query, (as_of_unix_ms,)).fetchone()
    if row is None or len(row) != 1:
        raise TelemetrySourceError("operational database timestamp query failed")
    value = row[0]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetrySourceError("operational database timestamp is invalid")
    return value


def _load_optional_proof(
    path: Path,
) -> tuple[tuple[CandidateProofAssessment, ...], str | None]:
    if not path.exists():
        return (), "PROOF_ASSESSMENT_UNAVAILABLE"
    try:
        return CandidateProofAssessmentStore(path).load(), None
    except (OSError, TypeError, ValueError):
        return (), "PROOF_ASSESSMENT_INVALID"


def _load_optional_promotion(
    path: Path,
) -> tuple[tuple[PromotionAssessment, ...], str | None]:
    if not path.exists():
        return (), "PROMOTION_ASSESSMENT_UNAVAILABLE"
    try:
        return PromotionAssessmentStore(path).load(), None
    except (OSError, TypeError, ValueError):
        return (), "PROMOTION_ASSESSMENT_INVALID"


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_exact_tuple(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple) or not all(type(item) is expected_type for item in value):
        raise ValueError(f"{name} must contain exact {expected_type.__name__} values")
