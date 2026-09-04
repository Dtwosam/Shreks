from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicComparisonCatalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
    derive_fast_deterministic_entry_authority_offline,
)
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
)

from .comparison import (
    FastDeterministicCandidatePaperAuthority,
    FastDeterministicComparisonEvidenceRow,
)
from .evidence_bundle import (
    FastDeterministicComparisonEvidenceProvenance,
)
from .observer_probe import (
    FastObserverDirectionalProbeEvidence,
    load_fast_observer_directional_probe,
)
from .risk_context import FastDeterministicCampaignRiskEnvironment


FAST_DETERMINISTIC_COMPARISON_HYDRATION_VERSION = (
    "fl9-comparison-evidence-hydration-v1"
)
_ENTRY_AUTHORITY_SOURCE_VERSION = "fl3-execution-economics-v1"


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonHydrationInput:
    source_event_id: str
    observer_candidate_id: int
    state_version: str
    evaluated_at_unix_ms: int
    entry_quote_identity: ObserverPaperQuoteIdentity
    exit_quote_identity: ObserverPaperQuoteIdentity
    quote_asset: ObserverPaperQuoteAsset
    impulse_scalp_evidence: FastOfflineImpulseScalpEvidence
    micro_pullback_evidence: FastOfflineMicroPullbackEvidence
    pre_graduation_evidence: FastOfflinePreGraduationEvidence
    graduation_flow_evidence: FastOfflineGraduationFlowEvidence
    wallet_cohort_evidence: FastOfflineWalletCohortEvidence
    longer_runner_evidence: FastOfflineLongerRunnerEvidence
    market_regime: MarketRegime
    risk_environment: FastDeterministicCampaignRiskEnvironment
    entry_forecast_source_version: str | None
    entry_forecast_horizon_ms: int | None
    execution_cost_source_version: str | None
    exit_capacity_source_version: str | None
    wallet_source_version: str | None
    graduation_context_source_version: str
    continuation_forecast_source_version: str | None
    regime_source_version: str
    risk_environment_source_version: str

    def __post_init__(self) -> None:
        for name in (
            "source_event_id",
            "state_version",
            "graduation_context_source_version",
            "regime_source_version",
            "risk_environment_source_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        _require_positive_int("observer_candidate_id", self.observer_candidate_id)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )

        exact = (
            ("entry_quote_identity", ObserverPaperQuoteIdentity),
            ("exit_quote_identity", ObserverPaperQuoteIdentity),
            ("quote_asset", ObserverPaperQuoteAsset),
            ("impulse_scalp_evidence", FastOfflineImpulseScalpEvidence),
            ("micro_pullback_evidence", FastOfflineMicroPullbackEvidence),
            ("pre_graduation_evidence", FastOfflinePreGraduationEvidence),
            ("graduation_flow_evidence", FastOfflineGraduationFlowEvidence),
            ("wallet_cohort_evidence", FastOfflineWalletCohortEvidence),
            ("longer_runner_evidence", FastOfflineLongerRunnerEvidence),
            ("market_regime", MarketRegime),
            (
                "risk_environment",
                FastDeterministicCampaignRiskEnvironment,
            ),
        )
        for name, expected in exact:
            if type(getattr(self, name)) is not expected:
                raise ValueError(f"{name} must be exact {expected.__name__}")

        if self.entry_quote_identity.candidate_id != self.observer_candidate_id:
            raise ValueError(
                "entry quote observer candidate identity mismatch"
            )
        if self.exit_quote_identity.candidate_id != self.observer_candidate_id:
            raise ValueError(
                "exit quote observer candidate identity mismatch"
            )
        if (
            self.entry_quote_identity.purpose
            is not ObserverPaperQuotePurpose.ENTRY
        ):
            raise ValueError("entry_quote_identity must have ENTRY purpose")
        if (
            self.exit_quote_identity.purpose
            is not ObserverPaperQuotePurpose.EXIT
        ):
            raise ValueError("exit_quote_identity must have EXIT purpose")

        for name in (
            "entry_forecast_source_version",
            "execution_cost_source_version",
            "exit_capacity_source_version",
            "wallet_source_version",
            "continuation_forecast_source_version",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_empty_string(name, value)
        if (self.entry_forecast_source_version is None) != (
            self.entry_forecast_horizon_ms is None
        ):
            raise ValueError(
                "entry forecast source version and horizon must be both present or absent"
            )
        if self.entry_forecast_horizon_ms is not None:
            _require_positive_int(
                "entry_forecast_horizon_ms",
                self.entry_forecast_horizon_ms,
            )


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonHydrationResult:
    version: str
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...]
    provenance: tuple[FastDeterministicComparisonEvidenceProvenance, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_DETERMINISTIC_COMPARISON_HYDRATION_VERSION:
            raise ValueError("unsupported comparison hydration version")
        if (
            not isinstance(self.rows, tuple)
            or not self.rows
            or not all(
                type(value) is FastDeterministicComparisonEvidenceRow
                for value in self.rows
            )
        ):
            raise ValueError(
                "hydration rows must be a non-empty tuple of exact comparison rows"
            )
        if (
            not isinstance(self.provenance, tuple)
            or len(self.provenance) != len(self.rows)
            or not all(
                type(value) is FastDeterministicComparisonEvidenceProvenance
                for value in self.provenance
            )
        ):
            raise ValueError(
                "hydration provenance must exactly match row population"
            )


def hydrate_fast_deterministic_comparison_evidence(
    *,
    database_path: str | os.PathLike[str],
    feature_dataset: FastTrainingFeatureDataset,
    catalog: FastDeterministicComparisonCatalog,
    hydration_inputs: tuple[FastDeterministicComparisonHydrationInput, ...],
    entry_authority_binary_path: str | Path,
) -> FastDeterministicComparisonHydrationResult:
    if type(feature_dataset) is not FastTrainingFeatureDataset:
        raise ValueError(
            "feature_dataset must be exact FastTrainingFeatureDataset"
        )
    if type(catalog) is not FastDeterministicComparisonCatalog:
        raise ValueError(
            "catalog must be exact FastDeterministicComparisonCatalog"
        )
    if (
        not isinstance(hydration_inputs, tuple)
        or len(hydration_inputs) != len(feature_dataset.records)
        or not hydration_inputs
        or not all(
            type(value) is FastDeterministicComparisonHydrationInput
            for value in hydration_inputs
        )
    ):
        raise ValueError(
            "hydration inputs must exactly match the FL8.1 feature population"
        )

    rows: list[FastDeterministicComparisonEvidenceRow] = []
    provenance: list[FastDeterministicComparisonEvidenceProvenance] = []

    for index, (record, source) in enumerate(
        zip(feature_dataset.records, hydration_inputs, strict=True)
    ):
        expected_source_event_id = (
            f"{record.decision_signature}:{record.decision_ordinal}"
        )
        if source.source_event_id != expected_source_event_id:
            raise ValueError(
                f"comparison hydration source identity mismatch at row {index}"
            )
        if source.evaluated_at_unix_ms < record.decision_observed_at_unix_ms:
            raise ValueError(
                f"comparison hydration evaluation precedes FL8.1 decision at row {index}"
            )
        probe = load_fast_observer_directional_probe(
            database_path=database_path,
            record=record,
            observer_candidate_id=source.observer_candidate_id,
            evaluated_at_unix_ms=source.evaluated_at_unix_ms,
            entry_quote_identity=source.entry_quote_identity,
            exit_quote_identity=source.exit_quote_identity,
            quote_asset=source.quote_asset,
        )
        entry_quote = probe.entry_quote
        exit_quote = probe.exit_quote
        _validate_risk_probe_consistency(
            source.risk_environment,
            probe_entry_route_available=probe.entry_evidence.route_available,
            probe_entry_price_impact_pct=probe.entry_price_impact_pct,
            probe_entry_input_notional_usd=probe.entry_input_notional_usd,
        )

        execution = _shared_entry_execution(source, index=index)
        _validate_execution_probe_alignment(
            source,
            execution,
            probe,
            index=index,
        )
        _validate_execution_provenance(source, execution, index=index)

        entry_authority = (
            None
            if execution is None
            else derive_fast_deterministic_entry_authority_offline(
                binary_path=entry_authority_binary_path,
                record=record,
                execution=execution,
            )
        )
        authorities = tuple(
            FastDeterministicCandidatePaperAuthority(
                candidate_version=manifest.candidate_version,
                entry_authority=entry_authority,
            )
            for manifest in catalog.candidates
        )

        row = FastDeterministicComparisonEvidenceRow(
            record=record,
            impulse_scalp_evidence=source.impulse_scalp_evidence,
            micro_pullback_evidence=source.micro_pullback_evidence,
            pre_graduation_evidence=source.pre_graduation_evidence,
            graduation_flow_evidence=source.graduation_flow_evidence,
            wallet_cohort_evidence=source.wallet_cohort_evidence,
            longer_runner_evidence=source.longer_runner_evidence,
            state_version=source.state_version,
            evaluated_at_unix_ms=source.evaluated_at_unix_ms,
            quote=None,
            market_regime=source.market_regime,
            risk_environment=source.risk_environment,
            candidate_authorities=authorities,
            entry_quote=entry_quote,
            exit_quote=exit_quote,
        )
        proof = FastDeterministicComparisonEvidenceProvenance(
            source_event_id=expected_source_event_id,
            entry_quote_source_version=probe.entry_quote_source_version,
            exit_quote_source_version=probe.exit_quote_source_version,
            entry_forecast_source_version=(
                source.entry_forecast_source_version
            ),
            entry_forecast_horizon_ms=source.entry_forecast_horizon_ms,
            execution_cost_source_version=(
                source.execution_cost_source_version
            ),
            exit_capacity_source_version=(
                source.exit_capacity_source_version
            ),
            wallet_source_version=source.wallet_source_version,
            graduation_context_source_version=(
                source.graduation_context_source_version
            ),
            continuation_forecast_source_version=(
                source.continuation_forecast_source_version
            ),
            regime_source_version=source.regime_source_version,
            risk_environment_source_version=(
                source.risk_environment_source_version
            ),
            entry_authority_source_version=(
                _ENTRY_AUTHORITY_SOURCE_VERSION
            ),
        )
        rows.append(row)
        provenance.append(proof)

    return FastDeterministicComparisonHydrationResult(
        version=FAST_DETERMINISTIC_COMPARISON_HYDRATION_VERSION,
        rows=tuple(rows),
        provenance=tuple(provenance),
    )


def _shared_entry_execution(
    source: FastDeterministicComparisonHydrationInput,
    *,
    index: int,
) -> FastOfflineEntryExecution | None:
    values = (
        source.impulse_scalp_evidence.execution,
        source.micro_pullback_evidence.execution,
        source.pre_graduation_evidence.execution,
        source.graduation_flow_evidence.execution,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError(
            f"comparison hydration shared entry execution is partially absent at row {index}"
        )
    first = values[0]
    assert first is not None
    if any(value != first for value in values[1:]):
        raise ValueError(
            f"comparison hydration entry families must share exact execution economics at row {index}"
        )
    return first


def _validate_execution_probe_alignment(
    source: FastDeterministicComparisonHydrationInput,
    execution: FastOfflineEntryExecution | None,
    probe: FastObserverDirectionalProbeEvidence,
    *,
    index: int,
) -> None:
    if execution is None:
        return
    if probe.intended_base_quantity is None:
        raise ValueError(
            f"comparison hydration execution exists without executable ENTRY probe at row {index}"
        )
    if probe.exit_capacity_base is None:
        raise ValueError(
            f"comparison hydration execution exists without executable EXIT capacity probe at row {index}"
        )
    if not math.isclose(
        execution.trade.base_quantity,
        probe.intended_base_quantity,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"comparison hydration execution base quantity does not match observer probe size at row {index}"
        )
    if not math.isclose(
        execution.trade.exit_capacity_base,
        probe.exit_capacity_base,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"comparison hydration execution exit capacity does not match observer probe at row {index}"
        )
    if source.exit_capacity_source_version != probe.exit_quote_source_version:
        raise ValueError(
            f"comparison hydration exit capacity provenance does not match observer EXIT probe at row {index}"
        )


def _validate_execution_provenance(
    source: FastDeterministicComparisonHydrationInput,
    execution: FastOfflineEntryExecution | None,
    *,
    index: int,
) -> None:
    values = (
        source.entry_forecast_source_version,
        source.entry_forecast_horizon_ms,
        source.execution_cost_source_version,
        source.exit_capacity_source_version,
    )
    if execution is None:
        if any(value is not None for value in values):
            raise ValueError(
                f"comparison hydration execution provenance exists without execution at row {index}"
            )
    elif any(value is None for value in values):
        raise ValueError(
            f"comparison hydration execution provenance is incomplete at row {index}"
        )

    wallet_present = source.wallet_cohort_evidence.evidence is not None
    if wallet_present != (source.wallet_source_version is not None):
        raise ValueError(
            f"comparison hydration wallet provenance mismatch at row {index}"
        )
    continuation = source.longer_runner_evidence.continuation
    if continuation is None:
        if source.continuation_forecast_source_version is not None:
            raise ValueError(
                f"comparison hydration continuation provenance exists without evidence at row {index}"
            )
    elif (
        source.continuation_forecast_source_version
        != continuation.forecast_source_version
    ):
        raise ValueError(
            f"comparison hydration continuation provenance mismatch at row {index}"
        )


def _validate_risk_probe_consistency(
    environment: FastDeterministicCampaignRiskEnvironment,
    *,
    probe_entry_route_available: bool,
    probe_entry_price_impact_pct: float | None,
    probe_entry_input_notional_usd: float,
) -> None:
    if not probe_entry_route_available:
        if (
            environment.expected_price_impact_pct is not None
            or environment.price_impact_notional_usd is not None
        ):
            raise ValueError(
                "comparison hydration risk impact cannot exist without executable ENTRY quote"
            )
        return

    if probe_entry_price_impact_pct is None:
        if (
            environment.expected_price_impact_pct is not None
            or environment.price_impact_notional_usd is not None
        ):
            raise ValueError(
                "comparison hydration risk impact provenance is absent from ENTRY quote"
            )
        return

    if environment.expected_price_impact_pct is None:
        raise ValueError(
            "comparison hydration risk impact is missing despite ENTRY quote evidence"
        )
    if environment.price_impact_notional_usd is None:
        raise ValueError(
            "comparison hydration risk impact notional is missing"
        )
    if not math.isclose(
        environment.expected_price_impact_pct,
        probe_entry_price_impact_pct,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "comparison hydration risk price impact does not match ENTRY quote"
        )
    if not math.isclose(
        environment.price_impact_notional_usd,
        probe_entry_input_notional_usd,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "comparison hydration risk impact notional does not match ENTRY quote"
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")
