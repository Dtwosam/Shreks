from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path


FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME = "shreks.fl9_v2_cohort_acceptance"
FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION = 1
FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION = "fl9-v2-cohort-acceptance-v1"
FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION = "fl9-v2-cohort-evidence-floor-v1"

_TRADABLE_UNIVERSE_POLICY_VERSION = "fl9-tradable-universe-v1"
_TRADABLE_UNIVERSE_POLICY_FINGERPRINT = (
    "abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4"
)
_FEATURE_FIREWALL_VERSION = "fl8.3-feature-identity-firewall-v1"
_FEATURE_FIREWALL_FINGERPRINT = (
    "e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0"
)


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _positive_int(name: str, value: object) -> None:
    _non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class Fl9V2CoverageSessionCheckpoint:
    session_id: int
    provider: str
    process_session_sequence: int
    first_notification_observed_at_unix_ms: int
    last_notification_observed_at_unix_ms: int
    notification_count: int

    def __post_init__(self) -> None:
        _positive_int("session_id", self.session_id)
        _non_empty("provider", self.provider)
        _positive_int(
            "process_session_sequence",
            self.process_session_sequence,
        )
        _non_negative_int(
            "first_notification_observed_at_unix_ms",
            self.first_notification_observed_at_unix_ms,
        )
        _non_negative_int(
            "last_notification_observed_at_unix_ms",
            self.last_notification_observed_at_unix_ms,
        )
        if (
            self.last_notification_observed_at_unix_ms
            < self.first_notification_observed_at_unix_ms
        ):
            raise ValueError("coverage session timestamp bounds are reversed")
        _positive_int("notification_count", self.notification_count)


_SOURCE_SESSIONS = (
    Fl9V2CoverageSessionCheckpoint(
        115,
        "solana_public",
        1,
        1_788_878_323_281,
        1_788_878_840_118,
        20_710,
    ),
    Fl9V2CoverageSessionCheckpoint(
        116,
        "solana_public",
        1,
        1_788_883_195_692,
        1_788_883_318_307,
        269,
    ),
    Fl9V2CoverageSessionCheckpoint(
        117,
        "solana_public",
        2,
        1_788_883_321_082,
        1_788_886_814_126,
        190_896,
    ),
    Fl9V2CoverageSessionCheckpoint(
        118,
        "solana_public",
        3,
        1_788_887_193_636,
        1_788_890_813_557,
        196_433,
    ),
    Fl9V2CoverageSessionCheckpoint(
        119,
        "solana_public",
        4,
        1_788_890_820_688,
        1_788_891_310_394,
        30_697,
    ),
    Fl9V2CoverageSessionCheckpoint(
        120,
        "solana_public",
        5,
        1_788_891_317_263,
        1_788_892_489_553,
        62_883,
    ),
    Fl9V2CoverageSessionCheckpoint(
        121,
        "solana_public",
        6,
        1_788_895_790_049,
        1_788_900_928_410,
        279_491,
    ),
    Fl9V2CoverageSessionCheckpoint(
        122,
        "solana_public",
        1,
        1_788_900_968_708,
        1_788_902_289_834,
        64_497,
    ),
)

_EXPECTED_ELIGIBILITY_REASON_COUNTS = (
    ("below_minimum_liquidity_usd", 52_974),
    ("below_minimum_volume_h24_usd", 1_109),
    ("eligible", 274_334),
    ("missing_fresh_exact_market_snapshot", 176_299),
)


@dataclass(frozen=True, slots=True)
class Fl9V2CohortEvidenceFloorPolicy:
    version: str = FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION
    minimum_total_eligible_rows: int = 250_000
    minimum_training_rows: int = 150_000
    minimum_validation_rows: int = 50_000
    minimum_test_rows: int = 50_000
    minimum_unseen_mint_validation_rows: int = 40_000
    minimum_unseen_mint_validation_unique_mints: int = 20
    minimum_unseen_mint_test_rows: int = 40_000
    minimum_unseen_mint_test_unique_mints: int = 25
    minimum_natural_test_scored_observations: int = 40_000
    minimum_unseen_mint_test_scored_observations: int = 35_000

    def __post_init__(self) -> None:
        expected = (
            FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
            250_000,
            150_000,
            50_000,
            50_000,
            40_000,
            20,
            40_000,
            25,
            40_000,
            35_000,
        )
        actual = (
            self.version,
            self.minimum_total_eligible_rows,
            self.minimum_training_rows,
            self.minimum_validation_rows,
            self.minimum_test_rows,
            self.minimum_unseen_mint_validation_rows,
            self.minimum_unseen_mint_validation_unique_mints,
            self.minimum_unseen_mint_test_rows,
            self.minimum_unseen_mint_test_unique_mints,
            self.minimum_natural_test_scored_observations,
            self.minimum_unseen_mint_test_scored_observations,
        )
        if actual != expected:
            raise ValueError(
                "fl9-v2 cohort evidence floors are immutable; "
                "changes require a new policy version"
            )


@dataclass(frozen=True, slots=True)
class Fl9V2CohortAcceptancePolicy:
    version: str = FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION
    source_sessions: tuple[Fl9V2CoverageSessionCheckpoint, ...] = _SOURCE_SESSIONS
    required_latest_session_id: int = 123
    minimum_decision_observed_at_unix_ms: int = 1_788_878_323_281
    horizon_ms: int = 30_000
    test_end_unix_ms: int = 1_788_902_289_835
    selection_at_unix_ms: int = 1_788_902_319_835
    training_cut_unix_ms: int = 1_788_892_302_791
    validation_cut_unix_ms: int = 1_788_898_931_418
    tradable_universe_policy_version: str = _TRADABLE_UNIVERSE_POLICY_VERSION
    tradable_universe_policy_fingerprint_sha256: str = (
        _TRADABLE_UNIVERSE_POLICY_FINGERPRINT
    )
    feature_identity_firewall_version: str = _FEATURE_FIREWALL_VERSION
    feature_identity_firewall_fingerprint_sha256: str = (
        _FEATURE_FIREWALL_FINGERPRINT
    )
    expected_raw_row_count: int = 504_716
    expected_cross_session_duplicate_count: int = 0
    expected_raw_unique_mint_count: int = 394
    expected_eligibility_reason_counts: tuple[tuple[str, int], ...] = (
        _EXPECTED_ELIGIBILITY_REASON_COUNTS
    )
    expected_eligible_row_count: int = 274_334
    expected_eligible_unique_mint_count: int = 146
    expected_training_raw_row_count: int = 164_645
    expected_validation_raw_row_count: int = 54_858
    expected_test_raw_row_count: int = 54_831
    expected_shared_signature_count: int = 0
    expected_training_quarantined_row_count: int = 0
    expected_validation_quarantined_row_count: int = 0
    expected_test_quarantined_row_count: int = 0
    expected_validation_unseen_mint_rows: int = 49_754
    expected_validation_unseen_mint_unique_mints: int = 24
    expected_validation_seen_mint_rows: int = 5_104
    expected_validation_seen_mint_unique_mints: int = 10
    expected_validation_seen_actor_rows: int = 23_416
    expected_validation_unseen_actor_rows: int = 31_442
    expected_validation_null_actor_rows: int = 0
    expected_test_unseen_mint_rows: int = 54_828
    expected_test_unseen_mint_unique_mints: int = 31
    expected_test_seen_mint_rows: int = 3
    expected_test_seen_mint_unique_mints: int = 3
    expected_test_seen_actor_rows: int = 11_841
    expected_test_unseen_actor_rows: int = 42_990
    expected_test_null_actor_rows: int = 0

    @property
    def source_session_ids(self) -> tuple[int, ...]:
        return tuple(value.session_id for value in self.source_sessions)

    def __post_init__(self) -> None:
        expected = Fl9V2CohortAcceptancePolicy.__new__(
            Fl9V2CohortAcceptancePolicy
        )
        # Compare directly to module constants rather than recursively
        # constructing another instance.
        expected_values = (
            FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
            _SOURCE_SESSIONS,
            123,
            1_788_878_323_281,
            30_000,
            1_788_902_289_835,
            1_788_902_319_835,
            1_788_892_302_791,
            1_788_898_931_418,
            _TRADABLE_UNIVERSE_POLICY_VERSION,
            _TRADABLE_UNIVERSE_POLICY_FINGERPRINT,
            _FEATURE_FIREWALL_VERSION,
            _FEATURE_FIREWALL_FINGERPRINT,
            504_716,
            0,
            394,
            _EXPECTED_ELIGIBILITY_REASON_COUNTS,
            274_334,
            146,
            164_645,
            54_858,
            54_831,
            0,
            0,
            0,
            0,
            49_754,
            24,
            5_104,
            10,
            23_416,
            31_442,
            0,
            54_828,
            31,
            3,
            3,
            11_841,
            42_990,
            0,
        )
        actual_values = (
            self.version,
            self.source_sessions,
            self.required_latest_session_id,
            self.minimum_decision_observed_at_unix_ms,
            self.horizon_ms,
            self.test_end_unix_ms,
            self.selection_at_unix_ms,
            self.training_cut_unix_ms,
            self.validation_cut_unix_ms,
            self.tradable_universe_policy_version,
            self.tradable_universe_policy_fingerprint_sha256,
            self.feature_identity_firewall_version,
            self.feature_identity_firewall_fingerprint_sha256,
            self.expected_raw_row_count,
            self.expected_cross_session_duplicate_count,
            self.expected_raw_unique_mint_count,
            self.expected_eligibility_reason_counts,
            self.expected_eligible_row_count,
            self.expected_eligible_unique_mint_count,
            self.expected_training_raw_row_count,
            self.expected_validation_raw_row_count,
            self.expected_test_raw_row_count,
            self.expected_shared_signature_count,
            self.expected_training_quarantined_row_count,
            self.expected_validation_quarantined_row_count,
            self.expected_test_quarantined_row_count,
            self.expected_validation_unseen_mint_rows,
            self.expected_validation_unseen_mint_unique_mints,
            self.expected_validation_seen_mint_rows,
            self.expected_validation_seen_mint_unique_mints,
            self.expected_validation_seen_actor_rows,
            self.expected_validation_unseen_actor_rows,
            self.expected_validation_null_actor_rows,
            self.expected_test_unseen_mint_rows,
            self.expected_test_unseen_mint_unique_mints,
            self.expected_test_seen_mint_rows,
            self.expected_test_seen_mint_unique_mints,
            self.expected_test_seen_actor_rows,
            self.expected_test_unseen_actor_rows,
            self.expected_test_null_actor_rows,
        )
        del expected
        if actual_values != expected_values:
            raise ValueError(
                "fl9-v2-cohort-acceptance-v1 is immutable; "
                "changes require a new policy version"
            )
        if self.selection_at_unix_ms - self.horizon_ms != self.test_end_unix_ms:
            raise ValueError("frozen selection/horizon/test-end relationship is invalid")
        _sha256(
            "tradable_universe_policy_fingerprint_sha256",
            self.tradable_universe_policy_fingerprint_sha256,
        )
        _sha256(
            "feature_identity_firewall_fingerprint_sha256",
            self.feature_identity_firewall_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class Fl9V2ConcentrationSummary:
    row_count: int
    unique_mint_count: int
    top1_share: float
    top3_share: float
    top5_share: float
    top10_share: float
    hhi: float
    effective_mint_count: float

    def __post_init__(self) -> None:
        _non_negative_int("row_count", self.row_count)
        _non_negative_int("unique_mint_count", self.unique_mint_count)
        for name in (
            "top1_share",
            "top3_share",
            "top5_share",
            "top10_share",
            "hhi",
        ):
            value = getattr(self, name)
            _finite_non_negative(name, value)
            if value > 1.0:
                raise ValueError(f"{name} cannot exceed 1")
        _finite_non_negative("effective_mint_count", self.effective_mint_count)
        if not (
            self.top1_share
            <= self.top3_share
            <= self.top5_share
            <= self.top10_share
        ):
            raise ValueError("concentration top-k shares must be monotonic")


@dataclass(frozen=True, slots=True)
class Fl9V2AcceptedDecision:
    decision_identity: tuple[object, ...]
    partition: str
    assessment_fingerprint_sha256: str
    mint_novelty: str
    actor_novelty: str

    def __post_init__(self) -> None:
        _decision_identity(self.decision_identity)
        if self.partition not in {"training", "validation", "test"}:
            raise ValueError("partition must be training, validation, or test")
        _sha256(
            "assessment_fingerprint_sha256",
            self.assessment_fingerprint_sha256,
        )
        if self.mint_novelty not in {"seen", "unseen", "not_applicable"}:
            raise ValueError("mint novelty is invalid")
        if self.actor_novelty not in {
            "seen",
            "unseen",
            "null",
            "not_applicable",
        }:
            raise ValueError("actor novelty is invalid")
        if self.partition == "training":
            if (
                self.mint_novelty != "not_applicable"
                or self.actor_novelty != "not_applicable"
            ):
                raise ValueError(
                    "training decision novelty must be not_applicable"
                )


@dataclass(frozen=True, slots=True)
class Fl9V2QuarantinedDecision:
    decision_identity: tuple[object, ...]
    partition: str
    shared_signature: str

    def __post_init__(self) -> None:
        _decision_identity(self.decision_identity)
        if self.partition not in {"training", "validation", "test"}:
            raise ValueError("partition must be training, validation, or test")
        _non_empty("shared_signature", self.shared_signature)
        if self.decision_identity[0] != self.shared_signature:
            raise ValueError(
                "quarantined decision shared signature must match identity"
            )


@dataclass(frozen=True, slots=True)
class Fl9V2CohortAcceptanceManifest:
    schema_name: str
    schema_version: int
    policy_version: str
    floor_policy_version: str
    source_session_ids: tuple[int, ...]
    source_sessions: tuple[Fl9V2CoverageSessionCheckpoint, ...]
    latest_session_id: int
    horizon_ms: int
    minimum_decision_observed_at_unix_ms: int
    test_end_unix_ms: int
    selection_at_unix_ms: int
    training_cut_unix_ms: int
    validation_cut_unix_ms: int
    raw_row_count: int
    cross_session_duplicate_count: int
    raw_unique_mint_count: int
    eligibility_reason_counts: tuple[tuple[str, int], ...]
    eligible_row_count: int
    eligible_unique_mint_count: int
    training_raw_row_count: int
    validation_raw_row_count: int
    test_raw_row_count: int
    shared_signature_count: int
    training_quarantined_row_count: int
    validation_quarantined_row_count: int
    test_quarantined_row_count: int
    training_row_count: int
    validation_row_count: int
    test_row_count: int
    validation_unseen_mint_row_count: int
    validation_unseen_mint_unique_mint_count: int
    validation_seen_mint_row_count: int
    validation_seen_mint_unique_mint_count: int
    validation_seen_actor_row_count: int
    validation_unseen_actor_row_count: int
    validation_null_actor_row_count: int
    test_unseen_mint_row_count: int
    test_unseen_mint_unique_mint_count: int
    test_seen_mint_row_count: int
    test_seen_mint_unique_mint_count: int
    test_seen_actor_row_count: int
    test_unseen_actor_row_count: int
    test_null_actor_row_count: int
    structural_floor_passed: bool
    evidence_floor_policy: Fl9V2CohortEvidenceFloorPolicy
    concentration_summaries: tuple[
        tuple[str, Fl9V2ConcentrationSummary], ...
    ]
    tradable_universe_policy_fingerprint_sha256: str
    feature_identity_firewall_fingerprint_sha256: str
    accepted_decisions_file_sha256: str
    signature_quarantine_file_sha256: str
    accepted_identity_fingerprint_sha256: str
    training_identity_fingerprint_sha256: str
    validation_identity_fingerprint_sha256: str
    test_identity_fingerprint_sha256: str
    validation_unseen_mint_identity_fingerprint_sha256: str
    validation_seen_mint_identity_fingerprint_sha256: str
    test_unseen_mint_identity_fingerprint_sha256: str
    test_seen_mint_identity_fingerprint_sha256: str
    signature_quarantine_identity_fingerprint_sha256: str
    assessment_evidence_fingerprint_sha256: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME:
            raise ValueError("unsupported FL9 V2 cohort acceptance schema")
        if self.schema_version != FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported FL9 V2 cohort acceptance schema version"
            )
        if self.policy_version != FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION:
            raise ValueError(
                "unsupported FL9 V2 cohort acceptance policy"
            )
        if self.floor_policy_version != FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION:
            raise ValueError(
                "unsupported FL9 V2 cohort evidence floor policy"
            )
        if self.source_session_ids != tuple(range(115, 123)):
            raise ValueError(
                "manifest source session IDs contradict frozen policy"
            )
        if self.source_sessions != _SOURCE_SESSIONS:
            raise ValueError(
                "manifest source session metadata contradicts frozen policy"
            )
        if (
            tuple(value.session_id for value in self.source_sessions)
            != self.source_session_ids
        ):
            raise ValueError(
                "manifest source session IDs do not reconcile to metadata"
            )
        for name in (
            "latest_session_id",
            "horizon_ms",
            "minimum_decision_observed_at_unix_ms",
            "test_end_unix_ms",
            "selection_at_unix_ms",
            "training_cut_unix_ms",
            "validation_cut_unix_ms",
            "raw_row_count",
            "cross_session_duplicate_count",
            "raw_unique_mint_count",
            "eligible_row_count",
            "eligible_unique_mint_count",
            "training_raw_row_count",
            "validation_raw_row_count",
            "test_raw_row_count",
            "shared_signature_count",
            "training_quarantined_row_count",
            "validation_quarantined_row_count",
            "test_quarantined_row_count",
            "training_row_count",
            "validation_row_count",
            "test_row_count",
            "validation_unseen_mint_row_count",
            "validation_unseen_mint_unique_mint_count",
            "validation_seen_mint_row_count",
            "validation_seen_mint_unique_mint_count",
            "validation_seen_actor_row_count",
            "validation_unseen_actor_row_count",
            "validation_null_actor_row_count",
            "test_unseen_mint_row_count",
            "test_unseen_mint_unique_mint_count",
            "test_seen_mint_row_count",
            "test_seen_mint_unique_mint_count",
            "test_seen_actor_row_count",
            "test_unseen_actor_row_count",
            "test_null_actor_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if self.latest_session_id < 123:
            raise ValueError(
                "manifest latest session does not prove source immutability"
            )
        if (
            self.selection_at_unix_ms - self.horizon_ms
            != self.test_end_unix_ms
        ):
            raise ValueError(
                "manifest selection/horizon/test-end relationship is invalid"
            )
        if not isinstance(self.structural_floor_passed, bool):
            raise ValueError("structural_floor_passed must be bool")
        if (
            type(self.evidence_floor_policy)
            is not Fl9V2CohortEvidenceFloorPolicy
        ):
            raise ValueError(
                "evidence_floor_policy must be exact frozen floor policy"
            )
        if self.evidence_floor_policy.version != self.floor_policy_version:
            raise ValueError(
                "manifest floor policy version does not reconcile"
            )
        expected_concentration_keys = (
            "full_eligible",
            "raw_training",
            "raw_validation",
            "raw_test",
            "post_signature_training",
            "post_signature_validation",
            "post_signature_test",
            "unseen_mint_validation",
            "unseen_mint_test",
        )
        if (
            not isinstance(self.concentration_summaries, tuple)
            or tuple(name for name, _ in self.concentration_summaries)
            != expected_concentration_keys
            or not all(
                type(value) is Fl9V2ConcentrationSummary
                for _, value in self.concentration_summaries
            )
        ):
            raise ValueError(
                "manifest concentration summaries do not match required set"
            )
        for name in (
            "tradable_universe_policy_fingerprint_sha256",
            "feature_identity_firewall_fingerprint_sha256",
            "accepted_decisions_file_sha256",
            "signature_quarantine_file_sha256",
            "accepted_identity_fingerprint_sha256",
            "training_identity_fingerprint_sha256",
            "validation_identity_fingerprint_sha256",
            "test_identity_fingerprint_sha256",
            "validation_unseen_mint_identity_fingerprint_sha256",
            "validation_seen_mint_identity_fingerprint_sha256",
            "test_unseen_mint_identity_fingerprint_sha256",
            "test_seen_mint_identity_fingerprint_sha256",
            "signature_quarantine_identity_fingerprint_sha256",
            "assessment_evidence_fingerprint_sha256",
            "artifact_fingerprint_sha256",
        ):
            _sha256(name, getattr(self, name))
        _reason_counts(self.eligibility_reason_counts)
        if (
            self.training_raw_row_count
            + self.validation_raw_row_count
            + self.test_raw_row_count
            != self.eligible_row_count
        ):
            raise ValueError("raw partition counts do not reconcile")
        if (
            self.training_raw_row_count
            - self.training_quarantined_row_count
            != self.training_row_count
            or (
                self.validation_raw_row_count
                - self.validation_quarantined_row_count
                != self.validation_row_count
            )
            or (
                self.test_raw_row_count
                - self.test_quarantined_row_count
                != self.test_row_count
            )
        ):
            raise ValueError("signature quarantine counts do not reconcile")
        if (
            self.validation_unseen_mint_row_count
            + self.validation_seen_mint_row_count
            != self.validation_row_count
        ):
            raise ValueError(
                "validation mint novelty counts do not reconcile"
            )
        if (
            self.test_unseen_mint_row_count
            + self.test_seen_mint_row_count
            != self.test_row_count
        ):
            raise ValueError("TEST mint novelty counts do not reconcile")
        if (
            self.validation_seen_actor_row_count
            + self.validation_unseen_actor_row_count
            + self.validation_null_actor_row_count
            != self.validation_row_count
        ):
            raise ValueError(
                "validation actor novelty counts do not reconcile"
            )
        if (
            self.test_seen_actor_row_count
            + self.test_unseen_actor_row_count
            + self.test_null_actor_row_count
            != self.test_row_count
        ):
            raise ValueError("TEST actor novelty counts do not reconcile")


@dataclass(frozen=True, slots=True)
class Fl9V2CohortAcceptanceArtifact:
    path: Path
    manifest: Fl9V2CohortAcceptanceManifest
    accepted_decisions: tuple[Fl9V2AcceptedDecision, ...]
    quarantined_decisions: tuple[Fl9V2QuarantinedDecision, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("artifact path must be Path")
        if type(self.manifest) is not Fl9V2CohortAcceptanceManifest:
            raise ValueError(
                "manifest must be exact Fl9V2CohortAcceptanceManifest"
            )
        if not isinstance(self.accepted_decisions, tuple) or not all(
            type(value) is Fl9V2AcceptedDecision
            for value in self.accepted_decisions
        ):
            raise ValueError(
                "accepted_decisions must contain exact Fl9V2AcceptedDecision values"
            )
        if not isinstance(self.quarantined_decisions, tuple) or not all(
            type(value) is Fl9V2QuarantinedDecision
            for value in self.quarantined_decisions
        ):
            raise ValueError(
                "quarantined_decisions must contain exact Fl9V2QuarantinedDecision values"
            )


def _decision_identity(value: object) -> None:
    if not isinstance(value, tuple) or len(value) != 7:
        raise ValueError("decision identity must use the seven-field FL8.1 shape")
    signature, ordinal, sequence, mint, quote_mint, venue, observed = value
    for name, field in (
        ("signature", signature),
        ("mint", mint),
        ("quote_mint", quote_mint),
        ("venue", venue),
    ):
        _non_empty(name, field)
    for name, field in (
        ("ordinal", ordinal),
        ("sequence", sequence),
        ("observed_at_unix_ms", observed),
    ):
        _non_negative_int(name, field)


def _reason_counts(value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError("eligibility_reason_counts must be tuple")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("eligibility reason count entry is malformed")
        reason, count = item
        _non_empty("eligibility reason", reason)
        _non_negative_int("eligibility reason count", count)
        if reason in seen:
            raise ValueError("eligibility reason counts contain duplicate reason")
        seen.add(reason)
    if tuple(sorted(value)) != value:
        raise ValueError("eligibility reason counts must be canonical")

def _finite_non_negative(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ValueError(f"{name} must be finite and non-negative")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 fingerprint")
