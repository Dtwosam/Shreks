from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicComparisonCatalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import PaperFillPolicy, PaperLedger
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord
from shreks_brain.risk import RiskPolicy

from .matrix import (
    FastDeterministicCandidateCampaignSpec,
    FastDeterministicCandidateMatrixResult,
    run_fast_deterministic_candidate_matrix,
)
from .models import FastDeterministicCampaignRow
from .paper_evidence import FastDeterministicCampaignPaperEvidence
from .risk_context import FastDeterministicCampaignRiskEnvironment


FAST_DETERMINISTIC_COMPARISON_EVIDENCE_BINDER_VERSION = (
    "fl9-deterministic-comparison-evidence-v1"
)


@dataclass(frozen=True, slots=True)
class FastDeterministicCandidatePaperAuthority:
    candidate_version: str
    entry_authority: FastCampaignPaperEntryAuthority

    def __post_init__(self) -> None:
        _require_non_empty_string("candidate_version", self.candidate_version)
        if type(self.entry_authority) is not FastCampaignPaperEntryAuthority:
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority"
            )


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonEvidenceRow:
    record: FastTrainingFeatureRecord
    impulse_scalp_evidence: FastOfflineImpulseScalpEvidence
    micro_pullback_evidence: FastOfflineMicroPullbackEvidence
    pre_graduation_evidence: FastOfflinePreGraduationEvidence
    graduation_flow_evidence: FastOfflineGraduationFlowEvidence
    wallet_cohort_evidence: FastOfflineWalletCohortEvidence
    longer_runner_evidence: FastOfflineLongerRunnerEvidence
    state_version: str
    evaluated_at_unix_ms: int
    quote: FastCampaignPaperQuoteEvidence
    market_regime: MarketRegime
    risk_environment: FastDeterministicCampaignRiskEnvironment
    candidate_authorities: tuple[FastDeterministicCandidatePaperAuthority, ...]

    def __post_init__(self) -> None:
        exact = (
            ("record", FastTrainingFeatureRecord),
            ("impulse_scalp_evidence", FastOfflineImpulseScalpEvidence),
            ("micro_pullback_evidence", FastOfflineMicroPullbackEvidence),
            ("pre_graduation_evidence", FastOfflinePreGraduationEvidence),
            ("graduation_flow_evidence", FastOfflineGraduationFlowEvidence),
            ("wallet_cohort_evidence", FastOfflineWalletCohortEvidence),
            ("longer_runner_evidence", FastOfflineLongerRunnerEvidence),
            ("quote", FastCampaignPaperQuoteEvidence),
            ("market_regime", MarketRegime),
            (
                "risk_environment",
                FastDeterministicCampaignRiskEnvironment,
            ),
        )
        for name, expected in exact:
            if type(getattr(self, name)) is not expected:
                raise ValueError(f"{name} must be exact {expected.__name__}")
        _require_non_empty_string("state_version", self.state_version)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if self.evaluated_at_unix_ms < self.record.decision_observed_at_unix_ms:
            raise ValueError(
                "comparison evidence evaluation cannot precede FL8.1 decision"
            )
        if (
            self.quote.mint != self.record.mint
            or self.quote.quote_mint != self.record.quote_mint
        ):
            raise ValueError("comparison quote attribution does not match FL8.1 row")
        if not (
            self.record.decision_observed_at_unix_ms
            <= self.quote.observed_at_unix_ms
            <= self.evaluated_at_unix_ms
        ):
            raise ValueError(
                "comparison quote must be contemporaneous with decision/evaluation"
            )
        if not (
            self.record.decision_observed_at_unix_ms
            <= self.risk_environment.market_observed_at_unix_ms
            <= self.evaluated_at_unix_ms
        ):
            raise ValueError(
                "comparison risk market evidence must be contemporaneous"
            )
        if (
            self.risk_environment.day_started_at_unix_ms
            > self.evaluated_at_unix_ms
        ):
            raise ValueError("comparison risk day start cannot be in the future")
        if (
            not isinstance(self.candidate_authorities, tuple)
            or not self.candidate_authorities
            or not all(
                type(value) is FastDeterministicCandidatePaperAuthority
                for value in self.candidate_authorities
            )
        ):
            raise ValueError(
                "candidate_authorities must be a non-empty tuple of exact authorities"
            )
        versions = tuple(
            value.candidate_version for value in self.candidate_authorities
        )
        if versions != tuple(sorted(versions)):
            raise ValueError("candidate authority versions must be lexical")
        if len(versions) != len(set(versions)):
            raise ValueError("candidate authority versions must be unique")
        for authority in self.candidate_authorities:
            entry = authority.entry_authority
            if entry.mint != self.record.mint or entry.quote_mint != self.record.quote_mint:
                raise ValueError(
                    "candidate entry authority market attribution does not match FL8.1 row"
                )
            if (
                entry.decision_executable_entry_price_quote
                != self.record.decision_executable_entry_price_quote
            ):
                raise ValueError(
                    "candidate entry authority decision price provenance mismatch"
                )


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonEvidenceSpec:
    version: str
    catalog_fingerprint_sha256: str
    specs: tuple[FastDeterministicCandidateCampaignSpec, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_DETERMINISTIC_COMPARISON_EVIDENCE_BINDER_VERSION:
            raise ValueError("unsupported deterministic comparison evidence version")
        _require_sha256(
            "catalog_fingerprint_sha256",
            self.catalog_fingerprint_sha256,
        )
        if (
            not isinstance(self.specs, tuple)
            or len(self.specs) != 8
            or not all(
                type(value) is FastDeterministicCandidateCampaignSpec
                for value in self.specs
            )
        ):
            raise ValueError(
                "comparison evidence spec must contain exactly eight campaign specs"
            )
        versions = tuple(
            value.manifest.candidate_version for value in self.specs
        )
        if versions != tuple(sorted(versions)) or len(versions) != len(set(versions)):
            raise ValueError("comparison campaign specs must be unique and lexical")


def bind_fast_deterministic_comparison_evidence(
    *,
    catalog: FastDeterministicComparisonCatalog,
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...],
    paper_run_id_prefix: str,
) -> FastDeterministicComparisonEvidenceSpec:
    if type(catalog) is not FastDeterministicComparisonCatalog:
        raise ValueError(
            "catalog must be exact FastDeterministicComparisonCatalog"
        )
    if (
        not isinstance(rows, tuple)
        or not rows
        or not all(
            type(value) is FastDeterministicComparisonEvidenceRow
            for value in rows
        )
    ):
        raise ValueError(
            "rows must be a non-empty tuple of exact comparison evidence rows"
        )
    _require_non_empty_string("paper_run_id_prefix", paper_run_id_prefix)

    expected_versions = tuple(
        manifest.candidate_version for manifest in catalog.candidates
    )
    authority_maps: list[dict[str, FastCampaignPaperEntryAuthority]] = []
    for index, row in enumerate(rows):
        versions = tuple(
            value.candidate_version for value in row.candidate_authorities
        )
        if versions != expected_versions:
            raise ValueError(
                f"candidate authority coverage mismatch at row {index}"
            )
        authority_maps.append(
            {
                value.candidate_version: value.entry_authority
                for value in row.candidate_authorities
            }
        )

    specs = tuple(
        FastDeterministicCandidateCampaignSpec(
            manifest=manifest,
            rows=tuple(
                _campaign_row(
                    row,
                    manifest.lifecycle_policy.entry_baseline_kind,
                    manifest.lifecycle_policy.manager_baseline_kind,
                    authority_maps[index][manifest.candidate_version],
                )
                for index, row in enumerate(rows)
            ),
            paper_run_id=(
                f"{paper_run_id_prefix}:{manifest.candidate_version}"
            ),
        )
        for manifest in catalog.candidates
    )
    return FastDeterministicComparisonEvidenceSpec(
        version=FAST_DETERMINISTIC_COMPARISON_EVIDENCE_BINDER_VERSION,
        catalog_fingerprint_sha256=catalog.catalog_fingerprint_sha256,
        specs=specs,
    )


def run_fast_deterministic_comparison_catalog_matrix(
    *,
    binary_path: str | Path,
    catalog: FastDeterministicComparisonCatalog,
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...],
    paper_run_id_prefix: str,
    assessment_version: str,
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicCandidateMatrixResult:
    bound = bind_fast_deterministic_comparison_evidence(
        catalog=catalog,
        rows=rows,
        paper_run_id_prefix=paper_run_id_prefix,
    )
    return run_fast_deterministic_candidate_matrix(
        binary_path=binary_path,
        specs=bound.specs,
        assessment_version=assessment_version,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
    )


def _campaign_row(
    source: FastDeterministicComparisonEvidenceRow,
    entry_kind: str,
    manager_kind: str,
    entry_authority: FastCampaignPaperEntryAuthority,
) -> FastDeterministicCampaignRow:
    entry_evidence = {
        "IMPULSE_SCALP": source.impulse_scalp_evidence,
        "MICRO_PULLBACK": source.micro_pullback_evidence,
        "PRE_GRADUATION": source.pre_graduation_evidence,
        "GRADUATION_FLOW": source.graduation_flow_evidence,
    }.get(entry_kind)
    manager_evidence = {
        "WALLET_COHORT": source.wallet_cohort_evidence,
        "LONGER_RUNNER": source.longer_runner_evidence,
    }.get(manager_kind)
    if entry_evidence is None or manager_evidence is None:
        raise ValueError("catalog selected an unsupported evidence family")

    return FastDeterministicCampaignRow(
        record=source.record,
        flat_evidence=entry_evidence,
        open_evidence=manager_evidence,
        paper_evidence=FastDeterministicCampaignPaperEvidence(
            source_event_id=(
                f"{source.record.decision_signature}:"
                f"{source.record.decision_ordinal}"
            ),
            state_version=source.state_version,
            evaluated_at_unix_ms=source.evaluated_at_unix_ms,
            quote=source.quote,
            risk_context=None,
            entry_authority=entry_authority,
            market_regime=source.market_regime,
            risk_environment=source.risk_environment,
        ),
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
