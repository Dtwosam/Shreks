from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import string

from shreks_brain.fast_champion import FastForecastChampionArtifact
from shreks_brain.fast_evaluation import FastForecastEvaluationReport
from shreks_brain.fast_learning import (
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTarget,
)
from shreks_brain.fast_validation_v2 import (
    FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
    FastChronologicalGeneralizationRun,
)


FAST_FIRST_CHAMPION_V2_SCHEMA_NAME = (
    "shreks.fast_first_champion_v2_evidence"
)
FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION = 1
FAST_FIRST_CHAMPION_V2_POLICY_VERSION = "fl9-v2-first-champion-v1"

_COHORT_POLICY_VERSION = "fl9-v2-cohort-acceptance-v1"
_COHORT_ARTIFACT_FINGERPRINT = (
    "bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a"
)
_ACCEPTED_IDENTITY_FINGERPRINT = (
    "75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b"
)
_FEATURE_FIREWALL_VERSION = "fl8.3-feature-identity-firewall-v1"
_FEATURE_FIREWALL_FINGERPRINT = (
    "e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0"
)
_HORIZON_MS = 30_000
_SELECTION_AT_UNIX_MS = 1_788_902_319_835
_TRAINING_STARTED_AT_UNIX_MS = 1_788_878_323_281
_TRAINING_ENDED_AT_UNIX_MS = 1_788_892_302_791
_VALIDATION_STARTED_AT_UNIX_MS = _TRAINING_ENDED_AT_UNIX_MS
_VALIDATION_ENDED_AT_UNIX_MS = 1_788_898_931_418
_TEST_STARTED_AT_UNIX_MS = _VALIDATION_ENDED_AT_UNIX_MS
_TEST_ENDED_AT_UNIX_MS = 1_788_902_289_835
_MIN_NATURAL_TEST_SCORED = 40_000
_MIN_UNSEEN_MINT_TEST_SCORED = 35_000
_MIN_UNSEEN_MINT_VALIDATION_ROWS = 40_000
_MIN_UNSEEN_MINT_VALIDATION_MINTS = 20
_MIN_UNSEEN_MINT_TEST_ROWS = 40_000
_MIN_UNSEEN_MINT_TEST_MINTS = 25
_REQUIRED_MEMBERS = (
    (
        FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.ENDPOINT_RETURN_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.MAE_BPS,
        FastForecastModelFamily.MEAN_REGRESSOR,
    ),
    (
        FastForecastTarget.REVERSAL_OCCURRED,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    ),
    (
        FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
        FastForecastModelFamily.PRIOR_CLASSIFIER,
    ),
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2Policy:
    version: str = FAST_FIRST_CHAMPION_V2_POLICY_VERSION
    cohort_policy_version: str = _COHORT_POLICY_VERSION
    expected_cohort_artifact_fingerprint_sha256: str = (
        _COHORT_ARTIFACT_FINGERPRINT
    )
    expected_accepted_identity_fingerprint_sha256: str = (
        _ACCEPTED_IDENTITY_FINGERPRINT
    )
    generalization_policy_version: str = (
        FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION
    )
    feature_identity_firewall_version: str = _FEATURE_FIREWALL_VERSION
    feature_identity_firewall_fingerprint_sha256: str = (
        _FEATURE_FIREWALL_FINGERPRINT
    )
    horizon_ms: int = _HORIZON_MS
    selection_at_unix_ms: int = _SELECTION_AT_UNIX_MS
    training_started_at_unix_ms: int = _TRAINING_STARTED_AT_UNIX_MS
    training_ended_at_unix_ms: int = _TRAINING_ENDED_AT_UNIX_MS
    validation_started_at_unix_ms: int = _VALIDATION_STARTED_AT_UNIX_MS
    validation_ended_at_unix_ms: int = _VALIDATION_ENDED_AT_UNIX_MS
    test_started_at_unix_ms: int = _TEST_STARTED_AT_UNIX_MS
    test_ended_at_unix_ms: int = _TEST_ENDED_AT_UNIX_MS
    minimum_natural_test_scored_observations: int = (
        _MIN_NATURAL_TEST_SCORED
    )
    minimum_unseen_mint_test_scored_observations: int = (
        _MIN_UNSEEN_MINT_TEST_SCORED
    )
    minimum_unseen_mint_validation_rows: int = (
        _MIN_UNSEEN_MINT_VALIDATION_ROWS
    )
    minimum_unseen_mint_validation_mints: int = (
        _MIN_UNSEEN_MINT_VALIDATION_MINTS
    )
    minimum_unseen_mint_test_rows: int = _MIN_UNSEEN_MINT_TEST_ROWS
    minimum_unseen_mint_test_mints: int = _MIN_UNSEEN_MINT_TEST_MINTS
    required_members: tuple[
        tuple[FastForecastTarget, FastForecastModelFamily], ...
    ] = _REQUIRED_MEMBERS

    def __post_init__(self) -> None:
        expected = (
            FAST_FIRST_CHAMPION_V2_POLICY_VERSION,
            _COHORT_POLICY_VERSION,
            _COHORT_ARTIFACT_FINGERPRINT,
            _ACCEPTED_IDENTITY_FINGERPRINT,
            FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION,
            _FEATURE_FIREWALL_VERSION,
            _FEATURE_FIREWALL_FINGERPRINT,
            _HORIZON_MS,
            _SELECTION_AT_UNIX_MS,
            _TRAINING_STARTED_AT_UNIX_MS,
            _TRAINING_ENDED_AT_UNIX_MS,
            _VALIDATION_STARTED_AT_UNIX_MS,
            _VALIDATION_ENDED_AT_UNIX_MS,
            _TEST_STARTED_AT_UNIX_MS,
            _TEST_ENDED_AT_UNIX_MS,
            _MIN_NATURAL_TEST_SCORED,
            _MIN_UNSEEN_MINT_TEST_SCORED,
            _MIN_UNSEEN_MINT_VALIDATION_ROWS,
            _MIN_UNSEEN_MINT_VALIDATION_MINTS,
            _MIN_UNSEEN_MINT_TEST_ROWS,
            _MIN_UNSEEN_MINT_TEST_MINTS,
            _REQUIRED_MEMBERS,
        )
        actual = (
            self.version,
            self.cohort_policy_version,
            self.expected_cohort_artifact_fingerprint_sha256,
            self.expected_accepted_identity_fingerprint_sha256,
            self.generalization_policy_version,
            self.feature_identity_firewall_version,
            self.feature_identity_firewall_fingerprint_sha256,
            self.horizon_ms,
            self.selection_at_unix_ms,
            self.training_started_at_unix_ms,
            self.training_ended_at_unix_ms,
            self.validation_started_at_unix_ms,
            self.validation_ended_at_unix_ms,
            self.test_started_at_unix_ms,
            self.test_ended_at_unix_ms,
            self.minimum_natural_test_scored_observations,
            self.minimum_unseen_mint_test_scored_observations,
            self.minimum_unseen_mint_validation_rows,
            self.minimum_unseen_mint_validation_mints,
            self.minimum_unseen_mint_test_rows,
            self.minimum_unseen_mint_test_mints,
            self.required_members,
        )
        if actual != expected:
            raise ValueError(
                "FL9 V2 first-champion policy is immutable; "
                "changes require a new policy version"
            )
        if self.selection_at_unix_ms - self.horizon_ms != (
            self.test_ended_at_unix_ms
        ):
            raise ValueError(
                "FL9 V2 selection/horizon/TEST-end relationship is invalid"
            )
        if self.training_ended_at_unix_ms != (
            self.validation_started_at_unix_ms
        ):
            raise ValueError("FL9 V2 training/validation boundary is invalid")
        if self.validation_ended_at_unix_ms != (
            self.test_started_at_unix_ms
        ):
            raise ValueError("FL9 V2 validation/TEST boundary is invalid")


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2MemberEvidence:
    target: FastForecastTarget
    model_family: FastForecastModelFamily
    horizon_ms: int
    runtime_artifact_fingerprint_sha256: str
    generalization_run_fingerprint_sha256: str
    natural_test_report_fingerprint_sha256: str
    natural_test_scored_observation_count: int
    natural_test_target_unavailable_count: int
    unseen_mint_test_report_fingerprint_sha256: str
    unseen_mint_test_scored_observation_count: int
    unseen_mint_test_target_unavailable_count: int
    unseen_mint_test_identity_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if type(self.target) is not FastForecastTarget:
            raise ValueError("target must be exact FastForecastTarget")
        if type(self.model_family) is not FastForecastModelFamily:
            raise ValueError(
                "model_family must be exact FastForecastModelFamily"
            )
        if (self.target, self.model_family) not in _REQUIRED_MEMBERS:
            raise ValueError(
                "member evidence target/family is not a required FL9 V2 member"
            )
        if self.horizon_ms != _HORIZON_MS:
            raise ValueError("member evidence horizon must be frozen at 30000 ms")
        for name in (
            "runtime_artifact_fingerprint_sha256",
            "generalization_run_fingerprint_sha256",
            "natural_test_report_fingerprint_sha256",
            "unseen_mint_test_report_fingerprint_sha256",
            "unseen_mint_test_identity_fingerprint_sha256",
        ):
            _sha256(name, getattr(self, name))
        _non_negative_int(
            "natural_test_scored_observation_count",
            self.natural_test_scored_observation_count,
        )
        _non_negative_int(
            "natural_test_target_unavailable_count",
            self.natural_test_target_unavailable_count,
        )
        _non_negative_int(
            "unseen_mint_test_scored_observation_count",
            self.unseen_mint_test_scored_observation_count,
        )
        _non_negative_int(
            "unseen_mint_test_target_unavailable_count",
            self.unseen_mint_test_target_unavailable_count,
        )
        if (
            self.natural_test_scored_observation_count
            < _MIN_NATURAL_TEST_SCORED
        ):
            raise ValueError(
                "natural TEST scored evidence is below the frozen minimum"
            )
        if (
            self.unseen_mint_test_scored_observation_count
            < _MIN_UNSEEN_MINT_TEST_SCORED
        ):
            raise ValueError(
                "unseen-mint TEST scored evidence is below the frozen minimum"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2BuildResult:
    policy_version: str
    cohort_artifact_fingerprint_sha256: str
    accepted_identity_fingerprint_sha256: str
    training_bundle_fingerprint_sha256: str
    champion: FastForecastChampionArtifact
    runtime_artifacts: tuple[FastForecastBaselineArtifact, ...]
    generalization_runs: tuple[FastChronologicalGeneralizationRun, ...]
    natural_test_reports: tuple[FastForecastEvaluationReport, ...]
    unseen_mint_test_reports: tuple[FastForecastEvaluationReport, ...]
    member_evidence: tuple[FastFirstChampionV2MemberEvidence, ...]

    def __post_init__(self) -> None:
        if self.policy_version != FAST_FIRST_CHAMPION_V2_POLICY_VERSION:
            raise ValueError("unsupported V2 first-champion build policy")
        _sha256(
            "cohort_artifact_fingerprint_sha256",
            self.cohort_artifact_fingerprint_sha256,
        )
        _sha256(
            "accepted_identity_fingerprint_sha256",
            self.accepted_identity_fingerprint_sha256,
        )
        _sha256(
            "training_bundle_fingerprint_sha256",
            self.training_bundle_fingerprint_sha256,
        )
        if type(self.champion) is not FastForecastChampionArtifact:
            raise ValueError(
                "champion must be exact FastForecastChampionArtifact"
            )
        count = len(_REQUIRED_MEMBERS)
        typed_populations = (
            (
                "runtime_artifacts",
                self.runtime_artifacts,
                FastForecastBaselineArtifact,
            ),
            (
                "generalization_runs",
                self.generalization_runs,
                FastChronologicalGeneralizationRun,
            ),
            (
                "natural_test_reports",
                self.natural_test_reports,
                FastForecastEvaluationReport,
            ),
            (
                "unseen_mint_test_reports",
                self.unseen_mint_test_reports,
                FastForecastEvaluationReport,
            ),
            (
                "member_evidence",
                self.member_evidence,
                FastFirstChampionV2MemberEvidence,
            ),
        )
        for name, values, expected_type in typed_populations:
            if (
                not isinstance(values, tuple)
                or len(values) != count
                or not all(type(value) is expected_type for value in values)
            ):
                raise ValueError(
                    f"{name} must contain the exact required member population"
                )

        expected_keys = tuple(
            (target, family, _HORIZON_MS)
            for target, family in _REQUIRED_MEMBERS
        )
        artifact_keys = tuple(
            (value.target, value.model_family, value.horizon_ms)
            for value in self.runtime_artifacts
        )
        run_keys = tuple(
            (
                value.training_request.target,
                value.training_request.model_family,
                value.training_request.horizon_ms,
            )
            for value in self.generalization_runs
        )
        natural_keys = tuple(
            (value.target, value.model_family, value.horizon_ms)
            for value in self.natural_test_reports
        )
        unseen_keys = tuple(
            (value.target, value.model_family, value.horizon_ms)
            for value in self.unseen_mint_test_reports
        )
        evidence_keys = tuple(
            (value.target, value.model_family, value.horizon_ms)
            for value in self.member_evidence
        )
        if (
            artifact_keys != expected_keys
            or run_keys != expected_keys
            or natural_keys != expected_keys
            or unseen_keys != expected_keys
            or evidence_keys != expected_keys
        ):
            raise ValueError(
                "V2 build evidence populations are not in canonical "
                "required member order"
            )

        if (
            self.champion.training_bundle_fingerprint_sha256
            != self.training_bundle_fingerprint_sha256
        ):
            raise ValueError(
                "V2 champion training bundle fingerprint does not match build"
            )
        if len(self.champion.members) != count:
            raise ValueError(
                "V2 champion member population does not match required members"
            )

        for artifact, run, natural, unseen, evidence in zip(
            self.runtime_artifacts,
            self.generalization_runs,
            self.natural_test_reports,
            self.unseen_mint_test_reports,
            self.member_evidence,
            strict=True,
        ):
            if (
                artifact.training_bundle_fingerprint_sha256
                != self.training_bundle_fingerprint_sha256
                or run.training_bundle_fingerprint_sha256
                != self.training_bundle_fingerprint_sha256
                or natural.training_bundle_fingerprint_sha256
                != self.training_bundle_fingerprint_sha256
                or unseen.training_bundle_fingerprint_sha256
                != self.training_bundle_fingerprint_sha256
            ):
                raise ValueError(
                    "V2 member training bundle fingerprints do not reconcile"
                )
            if (
                natural.validation_run_fingerprint_sha256
                != run.validation_run_fingerprint_sha256
                or unseen.validation_run_fingerprint_sha256
                != run.validation_run_fingerprint_sha256
            ):
                raise ValueError(
                    "V2 TEST reports do not bind the exact generalization run"
                )
            if (
                evidence.runtime_artifact_fingerprint_sha256
                != artifact.artifact_fingerprint_sha256
                or evidence.generalization_run_fingerprint_sha256
                != run.validation_run_fingerprint_sha256
                or evidence.natural_test_report_fingerprint_sha256
                != natural.evaluation_report_fingerprint_sha256
                or evidence.unseen_mint_test_report_fingerprint_sha256
                != unseen.evaluation_report_fingerprint_sha256
                or evidence.natural_test_scored_observation_count
                != natural.overall.scored_observation_count
                or evidence.natural_test_target_unavailable_count
                != natural.overall.target_unavailable_count
                or evidence.unseen_mint_test_scored_observation_count
                != unseen.overall.scored_observation_count
                or evidence.unseen_mint_test_target_unavailable_count
                != unseen.overall.target_unavailable_count
            ):
                raise ValueError(
                    "V2 member evidence does not reconcile to build artifacts"
                )
            member = self.champion.member_for(
                artifact.target,
                artifact.horizon_ms,
            )
            if (
                member.forecast_artifact != artifact
                or member.validation_run_fingerprint_sha256
                != run.validation_run_fingerprint_sha256
                or member.test_evaluation_report_fingerprint_sha256
                != natural.evaluation_report_fingerprint_sha256
                or member.test_scored_observation_count
                != natural.overall.scored_observation_count
                or member.test_target_unavailable_count
                != natural.overall.target_unavailable_count
            ):
                raise ValueError(
                    "V2 runtime champion member does not reconcile "
                    "to natural TEST evidence"
                )


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2EvidenceManifest:
    schema_name: str
    schema_version: int
    policy_version: str
    cohort_artifact_fingerprint_sha256: str
    accepted_identity_fingerprint_sha256: str
    training_bundle_fingerprint_sha256: str
    feature_identity_firewall_fingerprint_sha256: str
    selection_at_unix_ms: int
    champion_fingerprint_sha256: str
    member_evidence: tuple[FastFirstChampionV2MemberEvidence, ...]
    file_sha256: tuple[tuple[str, str], ...]
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_V2_SCHEMA_NAME:
            raise ValueError(
                "unsupported V2 first-champion evidence schema_name"
            )
        if self.schema_version != FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION:
            raise ValueError(
                "unsupported V2 first-champion evidence schema_version"
            )
        if self.policy_version != FAST_FIRST_CHAMPION_V2_POLICY_VERSION:
            raise ValueError("unsupported V2 first-champion evidence policy")
        if self.selection_at_unix_ms != _SELECTION_AT_UNIX_MS:
            raise ValueError(
                "V2 first-champion selection timestamp is not frozen"
            )
        for name in (
            "cohort_artifact_fingerprint_sha256",
            "accepted_identity_fingerprint_sha256",
            "training_bundle_fingerprint_sha256",
            "feature_identity_firewall_fingerprint_sha256",
            "champion_fingerprint_sha256",
            "artifact_fingerprint_sha256",
        ):
            _sha256(name, getattr(self, name))
        if (
            not isinstance(self.member_evidence, tuple)
            or len(self.member_evidence) != len(_REQUIRED_MEMBERS)
            or not all(
                type(value) is FastFirstChampionV2MemberEvidence
                for value in self.member_evidence
            )
        ):
            raise ValueError(
                "member_evidence must contain the exact required population"
            )
        if (
            tuple(
                (value.target, value.model_family)
                for value in self.member_evidence
            )
            != _REQUIRED_MEMBERS
        ):
            raise ValueError(
                "member_evidence is not in canonical required member order"
            )
        if (
            not isinstance(self.file_sha256, tuple)
            or not self.file_sha256
        ):
            raise ValueError("file_sha256 must be a non-empty tuple")
        names: list[str] = []
        for item in self.file_sha256:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
            ):
                raise ValueError("file_sha256 entries are incompatible")
            names.append(item[0])
            _sha256("file_sha256 digest", item[1])
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError(
                "file_sha256 entries must be unique and canonical"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionV2EvidenceArtifact:
    path: Path
    manifest: FastFirstChampionV2EvidenceManifest
    champion: FastForecastChampionArtifact
    natural_test_reports: tuple[FastForecastEvaluationReport, ...]
    unseen_mint_test_reports: tuple[FastForecastEvaluationReport, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("artifact path must be Path")
        if type(self.manifest) is not FastFirstChampionV2EvidenceManifest:
            raise ValueError(
                "manifest must be exact FastFirstChampionV2EvidenceManifest"
            )
        if type(self.champion) is not FastForecastChampionArtifact:
            raise ValueError(
                "champion must be exact FastForecastChampionArtifact"
            )
        count = len(_REQUIRED_MEMBERS)
        for name, reports in (
            ("natural_test_reports", self.natural_test_reports),
            ("unseen_mint_test_reports", self.unseen_mint_test_reports),
        ):
            if (
                not isinstance(reports, tuple)
                or len(reports) != count
                or not all(
                    type(value) is FastForecastEvaluationReport
                    for value in reports
                )
            ):
                raise ValueError(
                    f"{name} must contain the exact required member population"
                )


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
