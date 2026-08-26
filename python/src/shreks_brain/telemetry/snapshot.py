from __future__ import annotations

import os
from pathlib import Path

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.paper import PaperPositionState

from .codec import encode_telemetry_snapshot
from .financial import compose_financial_telemetry
from .models import (
    G4_TELEMETRY_SCHEMA_VERSION,
    LayerStatus,
    SystemTelemetry,
    TelemetrySnapshot,
    TradingTelemetry,
)
from .sources import TelemetrySources


class TelemetrySnapshotError(ValueError):
    """Raised when a G4 snapshot cannot be assembled or persisted safely."""


def assemble_telemetry_snapshot(
    sources: TelemetrySources,
    *,
    evaluation_policy: TradingEvaluationPolicy,
    generated_at_unix_ms: int,
) -> TelemetrySnapshot:
    if type(sources) is not TelemetrySources:
        raise TelemetrySnapshotError("sources must be an exact TelemetrySources")
    if (
        isinstance(generated_at_unix_ms, bool)
        or not isinstance(generated_at_unix_ms, int)
        or generated_at_unix_ms < 0
    ):
        raise TelemetrySnapshotError(
            "generated timestamp must be a non-negative integer"
        )
    if generated_at_unix_ms < sources.as_of_unix_ms:
        raise TelemetrySnapshotError(
            "generated timestamp cannot precede telemetry source timestamp"
        )

    system = _system_telemetry(sources)
    trading = _trading_telemetry(sources)
    try:
        money, proof_risk = compose_financial_telemetry(
            sources,
            evaluation_policy=evaluation_policy,
        )
    except (TypeError, ValueError) as error:
        raise TelemetrySnapshotError("financial telemetry composition failed") from error

    statuses = (system.status, trading.status, money.status, proof_risk.status)
    if LayerStatus.UNAVAILABLE in statuses:
        overall = LayerStatus.UNAVAILABLE
    elif LayerStatus.DEGRADED in statuses:
        overall = LayerStatus.DEGRADED
    else:
        overall = LayerStatus.HEALTHY

    return TelemetrySnapshot(
        schema_version=G4_TELEMETRY_SCHEMA_VERSION,
        generated_at_unix_ms=generated_at_unix_ms,
        mode="PAPER",
        overall_status=overall,
        system=system,
        trading=trading,
        money=money,
        proof_risk=proof_risk,
    )


def write_telemetry_snapshot(snapshot: TelemetrySnapshot, path: str | Path) -> None:
    if type(snapshot) is not TelemetrySnapshot:
        raise TelemetrySnapshotError("snapshot must be an exact TelemetrySnapshot")
    output = Path(path)
    if not output.name:
        raise TelemetrySnapshotError("telemetry output path must name a file")

    payload = encode_telemetry_snapshot(snapshot).encode("utf-8")
    parent = output.parent
    temporary = output.with_name(output.name + ".tmp")

    try:
        parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
        os.chmod(output, 0o600)
        _fsync_directory(parent)
    except (OSError, TypeError, ValueError) as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise TelemetrySnapshotError("telemetry snapshot write failed") from error


def _system_telemetry(sources: TelemetrySources) -> SystemTelemetry:
    operational = sources.operational
    errors: list[str] = []

    if operational.provider_count == 0:
        errors.append("PROVIDER_HEALTH_UNAVAILABLE")
    elif operational.unhealthy_provider_count > 0:
        errors.append("PROVIDER_HEALTH_DEGRADED")
    if operational.latest_market_observed_at_unix_ms is None:
        errors.append("MARKET_OBSERVATION_UNAVAILABLE")
    if operational.latest_ingestion_checkpoint_at_unix_ms is None:
        errors.append("INGESTION_CHECKPOINT_UNAVAILABLE")
    if sources.accounting_status == "INCOMPLETE":
        errors.append("PAPER_ACCOUNTING_INCOMPLETE")

    latest_market = operational.latest_market_observed_at_unix_ms
    market_age = (
        None if latest_market is None else sources.as_of_unix_ms - latest_market
    )
    status = LayerStatus.HEALTHY if not errors else LayerStatus.DEGRADED

    return SystemTelemetry(
        status=status,
        observed_at_unix_ms=sources.as_of_unix_ms,
        source_errors=tuple(errors),
        provider_count=operational.provider_count,
        unhealthy_provider_count=operational.unhealthy_provider_count,
        latest_market_observed_at_unix_ms=latest_market,
        market_age_ms=market_age,
        latest_ingestion_checkpoint_at_unix_ms=(
            operational.latest_ingestion_checkpoint_at_unix_ms
        ),
        paper_last_cycle_at_unix_ms=sources.state.last_cycle_at_unix_ms,
        accounting_status=sources.accounting_status,
        host_metrics_available=False,
    )


def _trading_telemetry(sources: TelemetrySources) -> TradingTelemetry:
    ledger = sources.state.ledger
    open_position_count = sum(
        position.state is PaperPositionState.OPEN for position in ledger.positions
    )
    closed_position_count = sum(
        position.state is PaperPositionState.CLOSED for position in ledger.positions
    )

    return TradingTelemetry(
        status=LayerStatus.HEALTHY,
        observed_at_unix_ms=sources.as_of_unix_ms,
        source_errors=(),
        candidate_count=sources.operational.candidate_count,
        holder_distribution_count=sources.operational.holder_distribution_count,
        paper_quote_count=sources.operational.paper_quote_count,
        terminal_paper_entry_count=len(ledger.entries),
        open_position_count=open_position_count,
        closed_position_count=closed_position_count,
        pending_entry=sources.state.pending_entry is not None,
        candidate_version=sources.manifest.candidate.candidate_version,
        candidate_mint=None,
        paper_run_id=sources.manifest.paper_run_id,
        historical_score_count=None,
        historical_decision_count=None,
    )


def _fsync_directory(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        # The file itself has already been fsynced before the atomic replace.
        # Some platforms/filesystems do not permit directory fsync.
        return
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
