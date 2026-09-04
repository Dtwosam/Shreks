from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.fast_policy_proof import FastPolicyRunEvidence
from shreks_brain.paper import PaperFillPolicy, PaperLedger
from shreks_brain.risk import RiskPolicy

from .engine import run_fast_deterministic_chronological_campaign
from .models import FastDeterministicCampaignRow


FAST_DETERMINISTIC_CANDIDATE_MATRIX_VERSION = (
    "fl9-deterministic-candidate-matrix-v1"
)


@dataclass(frozen=True, slots=True)
class FastDeterministicCandidateCampaignSpec:
    manifest: FastDeterministicCandidateManifest
    rows: tuple[FastDeterministicCampaignRow, ...]
    paper_run_id: str

    def __post_init__(self) -> None:
        if type(self.manifest) is not FastDeterministicCandidateManifest:
            raise ValueError(
                "manifest must be exact FastDeterministicCandidateManifest"
            )
        if (
            not isinstance(self.rows, tuple)
            or not self.rows
            or not all(
                type(row) is FastDeterministicCampaignRow for row in self.rows
            )
        ):
            raise ValueError(
                "rows must be a non-empty tuple of exact FastDeterministicCampaignRow values"
            )
        _require_non_empty_string("paper_run_id", self.paper_run_id)


@dataclass(frozen=True, slots=True)
class FastDeterministicCandidateMatrixResult:
    version: str
    runs: tuple[FastPolicyRunEvidence, ...]
    event_population_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.version != FAST_DETERMINISTIC_CANDIDATE_MATRIX_VERSION:
            raise ValueError(
                "unsupported deterministic candidate matrix version"
            )
        if (
            not isinstance(self.runs, tuple)
            or not self.runs
            or not all(type(run) is FastPolicyRunEvidence for run in self.runs)
        ):
            raise ValueError(
                "runs must be a non-empty tuple of exact FastPolicyRunEvidence values"
            )
        _require_sha256(
            "event_population_fingerprint_sha256",
            self.event_population_fingerprint_sha256,
        )
        if any(
            run.event_population_fingerprint_sha256
            != self.event_population_fingerprint_sha256
            for run in self.runs
        ):
            raise ValueError(
                "all matrix runs must share the matrix event population fingerprint"
            )
        versions = tuple(run.candidate_version for run in self.runs)
        if versions != tuple(sorted(versions)):
            raise ValueError(
                "matrix run candidate versions must remain in lexical order"
            )
        if len(versions) != len(set(versions)):
            raise ValueError(
                "matrix run candidate versions must be unique"
            )


def run_fast_deterministic_candidate_matrix(
    *,
    binary_path: str | Path,
    specs: tuple[FastDeterministicCandidateCampaignSpec, ...],
    assessment_version: str,
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicCandidateMatrixResult:
    _preflight_matrix(specs)

    runs: list[FastPolicyRunEvidence] = []
    for spec in specs:
        session = run_fast_deterministic_chronological_campaign(
            binary_path=binary_path,
            manifest=spec.manifest,
            rows=spec.rows,
            paper_run_id=spec.paper_run_id,
            assessment_version=assessment_version,
            starting_ledger=starting_ledger,
            fill_policy=fill_policy,
            risk_policy=risk_policy,
            position_policy=position_policy,
            evaluation_policy=evaluation_policy,
        )
        if session.latest_result is None:
            raise ValueError(
                "deterministic matrix candidate did not produce final PAPER evidence"
            )
        run = session.latest_result.run_evidence
        if type(run) is not FastPolicyRunEvidence:
            raise ValueError(
                "deterministic matrix candidate must return exact FastPolicyRunEvidence"
            )
        if run.candidate_version != spec.manifest.candidate_version:
            raise ValueError(
                "matrix run candidate version does not match authenticated manifest"
            )
        if (
            run.candidate_fingerprint_sha256
            != spec.manifest.candidate_fingerprint_sha256
        ):
            raise ValueError(
                "matrix run candidate fingerprint does not match authenticated manifest"
            )
        if run.trading_evaluation.policy != evaluation_policy:
            raise ValueError(
                "matrix run trading evaluation policy does not match common E5 policy"
            )
        runs.append(run)

    population_fingerprints = {
        run.event_population_fingerprint_sha256 for run in runs
    }
    if len(population_fingerprints) != 1:
        raise ValueError(
            "deterministic candidate matrix runs do not share one event population"
        )
    population_fingerprint = next(iter(population_fingerprints))

    return FastDeterministicCandidateMatrixResult(
        version=FAST_DETERMINISTIC_CANDIDATE_MATRIX_VERSION,
        runs=tuple(runs),
        event_population_fingerprint_sha256=population_fingerprint,
    )


def _preflight_matrix(
    specs: tuple[FastDeterministicCandidateCampaignSpec, ...],
) -> None:
    if (
        not isinstance(specs, tuple)
        or not specs
        or not all(
            type(spec) is FastDeterministicCandidateCampaignSpec
            for spec in specs
        )
    ):
        raise ValueError(
            "specs must be a non-empty tuple of exact FastDeterministicCandidateCampaignSpec values"
        )

    versions = tuple(spec.manifest.candidate_version for spec in specs)
    if len(versions) != len(set(versions)):
        raise ValueError(
            "deterministic matrix candidate versions must be unique"
        )
    if versions != tuple(sorted(versions)):
        raise ValueError(
            "deterministic matrix candidate versions must be in lexical order"
        )

    fingerprints = tuple(
        spec.manifest.candidate_fingerprint_sha256 for spec in specs
    )
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError(
            "deterministic matrix candidate fingerprints must be unique"
        )

    paper_run_ids = tuple(spec.paper_run_id for spec in specs)
    if len(paper_run_ids) != len(set(paper_run_ids)):
        raise ValueError(
            "deterministic matrix paper_run_id values must be unique"
        )

    reference_rows = specs[0].rows
    for spec in specs[1:]:
        if len(spec.rows) != len(reference_rows):
            raise ValueError(
                "deterministic matrix candidate row population lengths must match"
            )
        for index, (reference, candidate) in enumerate(
            zip(reference_rows, spec.rows)
        ):
            if candidate.record != reference.record:
                raise ValueError(
                    f"deterministic matrix FL8.1 record population mismatch at row {index}"
                )
            _require_shared_paper_population(
                reference,
                candidate,
                index=index,
            )


def _require_shared_paper_population(
    reference: FastDeterministicCampaignRow,
    candidate: FastDeterministicCampaignRow,
    *,
    index: int,
) -> None:
    left = reference.paper_evidence
    right = candidate.paper_evidence
    if left.source_event_id != right.source_event_id:
        raise ValueError(
            f"deterministic matrix PAPER source population mismatch at row {index}"
        )
    if left.state_version != right.state_version:
        raise ValueError(
            f"deterministic matrix state-version population mismatch at row {index}"
        )
    if left.evaluated_at_unix_ms != right.evaluated_at_unix_ms:
        raise ValueError(
            f"deterministic matrix evaluated-clock population mismatch at row {index}"
        )
    if left.quote != right.quote:
        raise ValueError(
            f"deterministic matrix quote population mismatch at row {index}"
        )
    if left.market_regime != right.market_regime:
        raise ValueError(
            f"deterministic matrix market-regime population mismatch at row {index}"
        )
    if left.risk_environment != right.risk_environment:
        raise ValueError(
            f"deterministic matrix risk-environment population mismatch at row {index}"
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
