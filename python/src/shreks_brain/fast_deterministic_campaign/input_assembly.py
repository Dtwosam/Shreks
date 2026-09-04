from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from shreks_brain.fast_deterministic_offline import (
    FastChampionEntryExecutionEvidence,
    FastOfflineExecutionCostModel,
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineMarketSnapshot,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
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

from .hydration import FastDeterministicComparisonHydrationInput
from .observer_probe import (
    FastObserverDirectionalProbeEvidence,
    build_fast_observer_champion_entry_execution,
    load_fast_observer_directional_probe,
)
from .risk_context import FastDeterministicCampaignRiskEnvironment


FAST_DETERMINISTIC_COMPARISON_INPUT_ASSEMBLY_VERSION = (
    "fl9-comparison-input-assembly-v1"
)


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonExecutionPolicy:
    version: str
    horizon_ms: int
    cost_model: FastOfflineExecutionCostModel
    required_edge_bps: int
    risk_margin_bps: int

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_positive_int("horizon_ms", self.horizon_ms)
        if type(self.cost_model) is not FastOfflineExecutionCostModel:
            raise ValueError(
                "cost_model must be exact FastOfflineExecutionCostModel"
            )
        _require_bps("required_edge_bps", self.required_edge_bps)
        _require_bps("risk_margin_bps", self.risk_margin_bps)


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonPointInTimeContext:
    observer_candidate_id: int
    state_version: str
    evaluated_at_unix_ms: int
    entry_quote_identity: ObserverPaperQuoteIdentity
    exit_quote_identity: ObserverPaperQuoteIdentity
    quote_asset: ObserverPaperQuoteAsset
    graduation_boost_context: bool | None
    wallet_cohort_evidence: FastOfflineWalletCohortEvidence
    longer_runner_evidence: FastOfflineLongerRunnerEvidence
    market_regime: MarketRegime
    risk_environment: FastDeterministicCampaignRiskEnvironment
    wallet_source_version: str | None
    graduation_context_source_version: str
    continuation_forecast_source_version: str | None
    regime_source_version: str
    risk_environment_source_version: str

    def __post_init__(self) -> None:
        _require_positive_int(
            "observer_candidate_id",
            self.observer_candidate_id,
        )
        _require_non_empty_string("state_version", self.state_version)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if type(self.entry_quote_identity) is not ObserverPaperQuoteIdentity:
            raise ValueError(
                "entry_quote_identity must be exact ObserverPaperQuoteIdentity"
            )
        if type(self.exit_quote_identity) is not ObserverPaperQuoteIdentity:
            raise ValueError(
                "exit_quote_identity must be exact ObserverPaperQuoteIdentity"
            )
        if type(self.quote_asset) is not ObserverPaperQuoteAsset:
            raise ValueError(
                "quote_asset must be exact ObserverPaperQuoteAsset"
            )
        if (
            self.graduation_boost_context is not None
            and type(self.graduation_boost_context) is not bool
        ):
            raise ValueError(
                "graduation_boost_context must be bool or None"
            )
        if type(self.wallet_cohort_evidence) is not FastOfflineWalletCohortEvidence:
            raise ValueError(
                "wallet_cohort_evidence must be exact FastOfflineWalletCohortEvidence"
            )
        if type(self.longer_runner_evidence) is not FastOfflineLongerRunnerEvidence:
            raise ValueError(
                "longer_runner_evidence must be exact FastOfflineLongerRunnerEvidence"
            )
        if type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be exact MarketRegime")
        if (
            type(self.risk_environment)
            is not FastDeterministicCampaignRiskEnvironment
        ):
            raise ValueError(
                "risk_environment must be exact FastDeterministicCampaignRiskEnvironment"
            )
        for name in (
            "graduation_context_source_version",
            "regime_source_version",
            "risk_environment_source_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "wallet_source_version",
            "continuation_forecast_source_version",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_empty_string(name, value)

        if (
            self.entry_quote_identity.candidate_id
            != self.observer_candidate_id
        ):
            raise ValueError(
                "ENTRY quote candidate must match observer_candidate_id"
            )
        if (
            self.exit_quote_identity.candidate_id
            != self.observer_candidate_id
        ):
            raise ValueError(
                "EXIT quote candidate must match observer_candidate_id"
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

        wallet_present = self.wallet_cohort_evidence.evidence is not None
        if wallet_present != (self.wallet_source_version is not None):
            raise ValueError(
                "wallet source version must match wallet evidence presence"
            )
        continuation = self.longer_runner_evidence.continuation
        if continuation is None:
            if self.continuation_forecast_source_version is not None:
                raise ValueError(
                    "continuation source exists without continuation evidence"
                )
        elif (
            self.continuation_forecast_source_version
            != continuation.forecast_source_version
        ):
            raise ValueError(
                "continuation source version must match continuation evidence"
            )


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonInputAssemblyResult:
    version: str
    probes: tuple[FastObserverDirectionalProbeEvidence, ...]
    champion_execution_evidence: tuple[
        FastChampionEntryExecutionEvidence | None, ...
    ]
    hydration_inputs: tuple[FastDeterministicComparisonHydrationInput, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_DETERMINISTIC_COMPARISON_INPUT_ASSEMBLY_VERSION:
            raise ValueError("unsupported comparison input assembly version")
        if (
            not isinstance(self.probes, tuple)
            or not self.probes
            or not all(
                type(value) is FastObserverDirectionalProbeEvidence
                for value in self.probes
            )
        ):
            raise ValueError(
                "probes must be a non-empty tuple of exact probe evidence"
            )
        if (
            not isinstance(self.champion_execution_evidence, tuple)
            or len(self.champion_execution_evidence) != len(self.probes)
            or not all(
                value is None
                or type(value) is FastChampionEntryExecutionEvidence
                for value in self.champion_execution_evidence
            )
        ):
            raise ValueError(
                "champion execution evidence must exactly match probe population"
            )
        if (
            not isinstance(self.hydration_inputs, tuple)
            or len(self.hydration_inputs) != len(self.probes)
            or not all(
                type(value) is FastDeterministicComparisonHydrationInput
                for value in self.hydration_inputs
            )
        ):
            raise ValueError(
                "hydration inputs must exactly match probe population"
            )


def assemble_fast_deterministic_comparison_hydration_inputs(
    *,
    database_path: str | os.PathLike[str],
    feature_dataset: FastTrainingFeatureDataset,
    champion_path: str | Path,
    execution_policy: FastDeterministicComparisonExecutionPolicy,
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...],
) -> FastDeterministicComparisonInputAssemblyResult:
    if type(feature_dataset) is not FastTrainingFeatureDataset:
        raise ValueError(
            "feature_dataset must be exact FastTrainingFeatureDataset"
        )
    if type(execution_policy) is not FastDeterministicComparisonExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastDeterministicComparisonExecutionPolicy"
        )
    if (
        not isinstance(contexts, tuple)
        or len(contexts) != len(feature_dataset.records)
        or not contexts
        or not all(
            type(value) is FastDeterministicComparisonPointInTimeContext
            for value in contexts
        )
    ):
        raise ValueError(
            "contexts must exactly match the FL8.1 feature population"
        )

    probes: list[FastObserverDirectionalProbeEvidence] = []
    champion_evidence: list[FastChampionEntryExecutionEvidence | None] = []
    hydration_inputs: list[FastDeterministicComparisonHydrationInput] = []

    for index, (record, context) in enumerate(
        zip(feature_dataset.records, contexts, strict=True)
    ):
        if context.evaluated_at_unix_ms < record.decision_observed_at_unix_ms:
            raise ValueError(
                f"context evaluation precedes FL8.1 decision at row {index}"
            )

        probe = load_fast_observer_directional_probe(
            database_path=database_path,
            record=record,
            observer_candidate_id=context.observer_candidate_id,
            evaluated_at_unix_ms=context.evaluated_at_unix_ms,
            entry_quote_identity=context.entry_quote_identity,
            exit_quote_identity=context.exit_quote_identity,
            quote_asset=context.quote_asset,
        )
        proof = build_fast_observer_champion_entry_execution(
            probe=probe,
            champion_path=champion_path,
            record=record,
            horizon_ms=execution_policy.horizon_ms,
            cost_model=execution_policy.cost_model,
            required_edge_bps=execution_policy.required_edge_bps,
            risk_margin_bps=execution_policy.risk_margin_bps,
            execution_policy_source_version=execution_policy.version,
        )
        execution = None if proof is None else proof.execution

        if proof is None:
            forecast_source_version = None
            forecast_horizon_ms = None
            execution_cost_source_version = None
            exit_capacity_source_version = None
        else:
            _validate_champion_execution_proof(
                proof,
                probe,
                execution_policy,
                index=index,
            )
            forecast_source_version = proof.forecast_source_version
            forecast_horizon_ms = proof.prediction.horizon_ms
            execution_cost_source_version = execution_policy.version
            exit_capacity_source_version = proof.exit_capacity_source_version

        pre_snapshot = _market_snapshot(record)
        hydration = FastDeterministicComparisonHydrationInput(
            source_event_id=(
                f"{record.decision_signature}:{record.decision_ordinal}"
            ),
            observer_candidate_id=context.observer_candidate_id,
            state_version=context.state_version,
            evaluated_at_unix_ms=context.evaluated_at_unix_ms,
            entry_quote_identity=context.entry_quote_identity,
            exit_quote_identity=context.exit_quote_identity,
            quote_asset=context.quote_asset,
            impulse_scalp_evidence=FastOfflineImpulseScalpEvidence(
                execution=execution
            ),
            micro_pullback_evidence=FastOfflineMicroPullbackEvidence(
                execution=execution
            ),
            pre_graduation_evidence=FastOfflinePreGraduationEvidence(
                execution=execution
            ),
            graduation_flow_evidence=FastOfflineGraduationFlowEvidence(
                pre_snapshot=pre_snapshot,
                boost_context=context.graduation_boost_context,
                execution=execution,
            ),
            wallet_cohort_evidence=context.wallet_cohort_evidence,
            longer_runner_evidence=context.longer_runner_evidence,
            market_regime=context.market_regime,
            risk_environment=context.risk_environment,
            entry_forecast_source_version=forecast_source_version,
            entry_forecast_horizon_ms=forecast_horizon_ms,
            execution_cost_source_version=execution_cost_source_version,
            exit_capacity_source_version=exit_capacity_source_version,
            wallet_source_version=context.wallet_source_version,
            graduation_context_source_version=(
                context.graduation_context_source_version
            ),
            continuation_forecast_source_version=(
                context.continuation_forecast_source_version
            ),
            regime_source_version=context.regime_source_version,
            risk_environment_source_version=(
                context.risk_environment_source_version
            ),
        )

        probes.append(probe)
        champion_evidence.append(proof)
        hydration_inputs.append(hydration)

    return FastDeterministicComparisonInputAssemblyResult(
        version=FAST_DETERMINISTIC_COMPARISON_INPUT_ASSEMBLY_VERSION,
        probes=tuple(probes),
        champion_execution_evidence=tuple(champion_evidence),
        hydration_inputs=tuple(hydration_inputs),
    )


def _validate_champion_execution_proof(
    proof: FastChampionEntryExecutionEvidence,
    probe: FastObserverDirectionalProbeEvidence,
    policy: FastDeterministicComparisonExecutionPolicy,
    *,
    index: int,
) -> None:
    if proof.execution_policy_source_version != policy.version:
        raise ValueError(
            f"champion execution policy provenance mismatch at row {index}"
        )
    if proof.prediction.horizon_ms != policy.horizon_ms:
        raise ValueError(
            f"champion execution forecast horizon mismatch at row {index}"
        )
    if proof.execution.cost_model != policy.cost_model:
        raise ValueError(
            f"champion execution cost model mismatch at row {index}"
        )
    if proof.execution.trade.required_edge_bps != policy.required_edge_bps:
        raise ValueError(
            f"champion execution required edge mismatch at row {index}"
        )
    if proof.execution.trade.risk_margin_bps != policy.risk_margin_bps:
        raise ValueError(
            f"champion execution risk margin mismatch at row {index}"
        )
    if proof.exit_capacity_source_version != probe.exit_quote_source_version:
        raise ValueError(
            f"champion execution capacity provenance mismatch at row {index}"
        )


def _market_snapshot(
    record: FastTrainingFeatureRecord,
) -> FastOfflineMarketSnapshot:
    return FastOfflineMarketSnapshot(
        mint=record.mint,
        quote_mint=record.quote_mint,
        venue=record.venue,
        as_of_unix_ms=record.snapshot_as_of_unix_ms,
        last_sequence=record.snapshot_last_sequence,
        last_price_quote=record.snapshot_last_price_quote,
        last_reserve_context=record.last_reserve_context,
        last_lifecycle_event=record.last_lifecycle_event,
        windows=record.windows,
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


def _require_bps(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 10_000
    ):
        raise ValueError(f"{name} must be an integer within [0, 10000]")
