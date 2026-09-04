from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import os
from pathlib import Path

from shreks_brain.fast_campaign_paper import FastCampaignPaperQuoteEvidence
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
    ObserverCampaignStore,
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.paper import PaperQuoteState
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

    store = ObserverCampaignStore(database_path)
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
        _validate_market_attribution(record, source)

        token_decimals = store.latest_token_decimals(
            source.observer_candidate_id,
            record.mint,
            source.evaluated_at_unix_ms,
        )
        if token_decimals is None:
            raise ValueError(
                f"comparison hydration token decimals unavailable at row {index}"
            )
        entry_raw = store.latest_paper_quote(
            source.entry_quote_identity,
            source.evaluated_at_unix_ms,
        )
        exit_raw = store.latest_paper_quote(
            source.exit_quote_identity,
            source.evaluated_at_unix_ms,
        )
        if entry_raw is None or exit_raw is None:
            raise ValueError(
                f"comparison hydration requires persisted ENTRY and EXIT quotes at row {index}"
            )

        entry_quote = _campaign_quote(
            record,
            entry_raw,
            token_decimals=token_decimals,
            quote_asset=source.quote_asset,
        )
        exit_quote = _campaign_quote(
            record,
            exit_raw,
            token_decimals=token_decimals,
            quote_asset=source.quote_asset,
        )
        _validate_quote_chronology(
            record,
            source,
            entry_quote,
            exit_quote,
            index=index,
        )
        _validate_risk_quote_consistency(
            source.risk_environment,
            entry_raw,
            quote_asset=source.quote_asset,
        )

        execution = _shared_entry_execution(source, index=index)
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
            entry_quote_source_version=_quote_source_version(entry_raw),
            exit_quote_source_version=_quote_source_version(exit_raw),
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


def _validate_market_attribution(
    record: FastTrainingFeatureRecord,
    source: FastDeterministicComparisonHydrationInput,
) -> None:
    entry = source.entry_quote_identity
    exit_value = source.exit_quote_identity
    if source.quote_asset.mint != record.quote_mint:
        raise ValueError(
            "comparison hydration quote asset does not match FL8.1 quote mint"
        )
    if entry.input_mint != record.quote_mint or entry.output_mint != record.mint:
        raise ValueError(
            "comparison hydration ENTRY quote market attribution mismatch"
        )
    if exit_value.input_mint != record.mint or exit_value.output_mint != record.quote_mint:
        raise ValueError(
            "comparison hydration EXIT quote market attribution mismatch"
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


def _campaign_quote(
    record: FastTrainingFeatureRecord,
    evidence: ObserverPaperQuoteEvidence,
    *,
    token_decimals: int,
    quote_asset: ObserverPaperQuoteAsset,
) -> FastCampaignPaperQuoteEvidence:
    if type(evidence) is not ObserverPaperQuoteEvidence:
        raise ValueError(
            "comparison hydration quote must be exact ObserverPaperQuoteEvidence"
        )
    if evidence.identity.provider != "jupiter":
        raise ValueError(
            "comparison hydration PAPER quote provider must be jupiter"
        )
    if not evidence.route_available:
        return FastCampaignPaperQuoteEvidence(
            provider=evidence.identity.provider,
            mint=record.mint,
            quote_mint=record.quote_mint,
            observed_at_unix_ms=evidence.quoted_at_unix_ms,
            state=PaperQuoteState.UNAVAILABLE,
            reference_price_quote=None,
            execution_price_quote=None,
            quoted_base_quantity=None,
            available_base_quantity=None,
            quote_to_usd_rate=quote_asset.usd_per_token,
        )

    if evidence.identity.purpose is ObserverPaperQuotePurpose.ENTRY:
        quote_quantity = _raw_quantity(
            evidence.identity.input_amount,
            quote_asset.decimals,
            "ENTRY quote input",
        )
        base_quantity = _raw_quantity(
            evidence.output_amount,
            token_decimals,
            "ENTRY token output",
        )
    elif evidence.identity.purpose is ObserverPaperQuotePurpose.EXIT:
        base_quantity = _raw_quantity(
            evidence.identity.input_amount,
            token_decimals,
            "EXIT token input",
        )
        quote_quantity = _raw_quantity(
            evidence.output_amount,
            quote_asset.decimals,
            "EXIT quote output",
        )
    else:
        raise ValueError("unsupported comparison hydration quote purpose")

    if base_quantity <= 0.0 or quote_quantity <= 0.0:
        raise ValueError(
            "comparison hydration executable quote quantities must be positive"
        )
    execution_price = quote_quantity / base_quantity
    if not math.isfinite(execution_price) or execution_price <= 0.0:
        raise ValueError(
            "comparison hydration execution price must be positive and finite"
        )

    return FastCampaignPaperQuoteEvidence(
        provider=evidence.identity.provider,
        mint=record.mint,
        quote_mint=record.quote_mint,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=record.decision_executable_entry_price_quote,
        execution_price_quote=execution_price,
        quoted_base_quantity=base_quantity,
        available_base_quantity=base_quantity,
        quote_to_usd_rate=quote_asset.usd_per_token,
    )


def _validate_quote_chronology(
    record: FastTrainingFeatureRecord,
    source: FastDeterministicComparisonHydrationInput,
    entry_quote: FastCampaignPaperQuoteEvidence,
    exit_quote: FastCampaignPaperQuoteEvidence,
    *,
    index: int,
) -> None:
    for name, value in (
        ("ENTRY", entry_quote),
        ("EXIT", exit_quote),
    ):
        if not (
            record.decision_observed_at_unix_ms
            <= value.observed_at_unix_ms
            <= source.evaluated_at_unix_ms
        ):
            raise ValueError(
                f"comparison hydration {name} quote is outside decision-safe chronology at row {index}"
            )


def _validate_risk_quote_consistency(
    environment: FastDeterministicCampaignRiskEnvironment,
    entry_quote: ObserverPaperQuoteEvidence,
    *,
    quote_asset: ObserverPaperQuoteAsset,
) -> None:
    if not entry_quote.route_available:
        if (
            environment.expected_price_impact_pct is not None
            or environment.price_impact_notional_usd is not None
        ):
            raise ValueError(
                "comparison hydration risk impact cannot exist without executable ENTRY quote"
            )
        return

    if entry_quote.price_impact_pct is None:
        if (
            environment.expected_price_impact_pct is not None
            or environment.price_impact_notional_usd is not None
        ):
            raise ValueError(
                "comparison hydration risk impact provenance is absent from ENTRY quote"
            )
        return

    try:
        impact = float(Decimal(entry_quote.price_impact_pct))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(
            "comparison hydration ENTRY price impact is malformed"
        ) from exc
    notional = (
        _raw_quantity(
            entry_quote.identity.input_amount,
            quote_asset.decimals,
            "ENTRY quote notional",
        )
        * quote_asset.usd_per_token
    )
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
        impact,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "comparison hydration risk price impact does not match ENTRY quote"
        )
    if not math.isclose(
        environment.price_impact_notional_usd,
        notional,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "comparison hydration risk impact notional does not match ENTRY quote"
        )


def _quote_source_version(evidence: ObserverPaperQuoteEvidence) -> str:
    identity = evidence.identity
    return (
        f"observer:{identity.provider}:"
        f"{identity.probe_policy_version}:{identity.purpose.value}"
    )


def _raw_quantity(raw_amount: int, decimals: int, name: str) -> float:
    if (
        isinstance(raw_amount, bool)
        or not isinstance(raw_amount, int)
        or raw_amount < 0
    ):
        raise ValueError(f"{name} raw amount is invalid")
    if (
        isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or not 0 <= decimals <= 255
    ):
        raise ValueError(f"{name} decimals are invalid")
    try:
        value = Decimal(raw_amount) / (Decimal(10) ** decimals)
        converted = float(value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be converted safely") from exc
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return converted


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
