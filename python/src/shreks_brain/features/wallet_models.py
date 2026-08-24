from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.wallets import (
    WalletIndependenceAssessment,
    WalletObservation,
    WalletProfile,
    WalletTradeReconstruction,
)


WALLET_FEATURE_SCHEMA_VERSION = "d5-wallet-v1"

_STRENGTH_CHECK_ORDER = (
    "effective_closed_sample_size",
    "evidence_sample_confidence",
    "median_return_pct",
    "win_rate",
    "rug_exposure_rate",
    "median_drawdown_pct",
)
_STRENGTH_CHECK_INDEX = {
    name: index for index, name in enumerate(_STRENGTH_CHECK_ORDER)
}
_MISSING_FEATURE_ORDER = (
    "confidence_weighted_entry_median_return_pct",
    "confidence_weighted_entry_win_rate",
    "independently_strong_entry_wallet_count",
    "strong_entry_all_pairs_independent_under_evidence",
)


class WalletHistoricalStrengthState(StrEnum):
    STRONG = "STRONG"
    NOT_STRONG = "NOT_STRONG"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WalletFeaturePolicy:
    version: str
    entry_window_ms: int
    exit_window_ms: int
    creator_activity_window_ms: int
    minimum_effective_closed_sample_size: float
    minimum_evidence_sample_confidence: float
    minimum_median_return_pct: float
    minimum_win_rate: float
    maximum_rug_exposure_rate: float | None
    maximum_median_drawdown_pct: float | None

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_positive_int("entry_window_ms", self.entry_window_ms)
        _require_positive_int("exit_window_ms", self.exit_window_ms)
        _require_positive_int(
            "creator_activity_window_ms", self.creator_activity_window_ms
        )
        if _require_finite_number(
            "minimum_effective_closed_sample_size",
            self.minimum_effective_closed_sample_size,
        ) <= 0.0:
            raise ValueError(
                "minimum_effective_closed_sample_size must be strictly positive"
            )
        if _require_rate(
            "minimum_evidence_sample_confidence",
            self.minimum_evidence_sample_confidence,
        ) <= 0.0:
            raise ValueError(
                "minimum_evidence_sample_confidence must be strictly positive"
            )
        if _require_finite_number(
            "minimum_median_return_pct", self.minimum_median_return_pct
        ) <= 0.0:
            raise ValueError("minimum_median_return_pct must be strictly positive")
        _require_rate("minimum_win_rate", self.minimum_win_rate)
        _require_optional_rate(
            "maximum_rug_exposure_rate", self.maximum_rug_exposure_rate
        )
        _require_optional_percentage(
            "maximum_median_drawdown_pct", self.maximum_median_drawdown_pct
        )


@dataclass(frozen=True, slots=True)
class WalletFeatureInputs:
    as_of_unix_ms: int
    candidate_mint: str
    reconstructions: tuple[WalletTradeReconstruction, ...]
    profiles: tuple[WalletProfile, ...]
    independence: WalletIndependenceAssessment
    observations: tuple[WalletObservation, ...]
    policy: WalletFeaturePolicy

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        if not isinstance(self.reconstructions, tuple) or not all(
            type(value) is WalletTradeReconstruction
            for value in self.reconstructions
        ):
            raise ValueError(
                "reconstructions must be a tuple of WalletTradeReconstruction values"
            )
        if not isinstance(self.profiles, tuple) or not all(
            type(value) is WalletProfile for value in self.profiles
        ):
            raise ValueError("profiles must be a tuple of WalletProfile values")
        if type(self.independence) is not WalletIndependenceAssessment:
            raise ValueError("independence must be a WalletIndependenceAssessment")
        if not isinstance(self.observations, tuple) or not all(
            type(value) is WalletObservation for value in self.observations
        ):
            raise ValueError(
                "observations must be a tuple of WalletObservation values"
            )
        if type(self.policy) is not WalletFeaturePolicy:
            raise ValueError("policy must be a WalletFeaturePolicy")

        reconstruction_wallets: list[str] = []
        for reconstruction in self.reconstructions:
            if reconstruction.candidate_mint != self.candidate_mint:
                raise ValueError(
                    "reconstruction candidate mint must match WalletFeatureInputs"
                )
            if reconstruction.as_of_unix_ms != self.as_of_unix_ms:
                raise ValueError(
                    "reconstruction as_of_unix_ms must equal wallet feature as_of"
                )
            reconstruction_wallets.append(reconstruction.wallet)
            for episode in reconstruction.episodes:
                timestamps = (
                    episode.opened_at_unix_ms,
                    episode.last_observed_at_unix_ms,
                    episode.closed_at_unix_ms,
                )
                if any(
                    timestamp is not None and timestamp > self.as_of_unix_ms
                    for timestamp in timestamps
                ):
                    raise ValueError(
                        "future episode evidence is not allowed in wallet features"
                    )
        if len(set(reconstruction_wallets)) != len(reconstruction_wallets):
            raise ValueError("duplicate reconstruction wallet")
        reconstruction_wallet_set = set(reconstruction_wallets)

        profile_wallets: list[str] = []
        profile_policy_versions: set[str] = set()
        context_versions: set[str] = set()
        for profile in self.profiles:
            if profile.as_of_unix_ms != self.as_of_unix_ms:
                raise ValueError(
                    "profile as_of_unix_ms must equal wallet feature as_of"
                )
            profile_wallets.append(profile.wallet)
            profile_policy_versions.add(profile.policy_version)
            if profile.context_version is not None:
                context_versions.add(profile.context_version)
        if len(set(profile_wallets)) != len(profile_wallets):
            raise ValueError("duplicate profile wallet")
        if set(profile_wallets) != reconstruction_wallet_set:
            raise ValueError(
                "profile wallet set must exactly match reconstruction wallet set"
            )
        if len(profile_policy_versions) > 1:
            raise ValueError("profiles cannot mix D3 profile policy versions")
        if len(context_versions) > 1:
            raise ValueError("profiles cannot mix non-null context versions")

        if self.independence.as_of_unix_ms != self.as_of_unix_ms:
            raise ValueError(
                "independence as_of_unix_ms must equal wallet feature as_of"
            )
        if set(self.independence.wallets) != reconstruction_wallet_set:
            raise ValueError(
                "independence wallet set must exactly match reconstruction wallet set"
            )

        for observation in self.observations:
            if observation.candidate_mint != self.candidate_mint:
                raise ValueError(
                    "observation candidate mint must match WalletFeatureInputs candidate"
                )
            if observation.observed_at_unix_ms > self.as_of_unix_ms:
                raise ValueError("future wallet observation is not allowed")


@dataclass(frozen=True, slots=True)
class WalletStrengthAssessment:
    wallet: str
    state: WalletHistoricalStrengthState
    effective_closed_sample_size: float
    evidence_sample_confidence: float
    median_return_pct: float | None
    win_rate: float | None
    rug_exposure_rate: float | None
    median_drawdown_pct: float | None
    failed_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet", self.wallet)
        if not isinstance(self.state, WalletHistoricalStrengthState):
            raise ValueError("state must be a WalletHistoricalStrengthState")
        _require_non_negative_finite_number(
            "effective_closed_sample_size", self.effective_closed_sample_size
        )
        _require_rate("evidence_sample_confidence", self.evidence_sample_confidence)
        _require_optional_finite_number("median_return_pct", self.median_return_pct)
        _require_optional_rate("win_rate", self.win_rate)
        _require_optional_rate("rug_exposure_rate", self.rug_exposure_rate)
        _require_optional_percentage("median_drawdown_pct", self.median_drawdown_pct)
        _validate_check_tuple("failed_checks", self.failed_checks)
        _validate_check_tuple("missing_checks", self.missing_checks)
        if set(self.failed_checks) & set(self.missing_checks):
            raise ValueError("failed_checks and missing_checks must be disjoint")
        if self.state is WalletHistoricalStrengthState.STRONG:
            if self.failed_checks or self.missing_checks:
                raise ValueError("STRONG assessment cannot have failed or missing checks")
        elif self.state is WalletHistoricalStrengthState.NOT_STRONG:
            if not self.failed_checks:
                raise ValueError("NOT_STRONG assessment requires failed checks")
        elif self.state is WalletHistoricalStrengthState.UNKNOWN:
            if self.failed_checks or not self.missing_checks:
                raise ValueError(
                    "UNKNOWN assessment requires missing checks and no failed checks"
                )


@dataclass(frozen=True, slots=True)
class WalletFeatureVector:
    schema_version: str
    as_of_unix_ms: int
    candidate_mint: str
    wallet_feature_policy_version: str
    profile_policy_version: str | None
    profile_context_version: str | None
    relationship_policy_version: str
    wallet_count: int
    recent_entry_wallet_count: int
    recent_exit_wallet_count: int
    strong_wallet_count: int
    unknown_strength_wallet_count: int
    strong_entry_wallet_count: int
    strong_exit_wallet_count: int
    confidence_weighted_strong_entry_count: float
    confidence_weighted_strong_exit_count: float
    entry_quality_profile_sample_count: int
    confidence_weighted_entry_median_return_pct: float | None
    confidence_weighted_entry_win_rate: float | None
    independently_strong_entry_wallet_count: int | None
    strong_entry_all_pairs_independent_under_evidence: bool | None
    strong_entry_linked_pair_count: int
    strong_entry_conflicting_pair_count: int
    strong_entry_unknown_pair_count: int
    strong_entry_coordination_cluster_count: int
    strong_entry_max_independent_group_count_upper_bound: int
    creator_deployer_action_observation_count: int
    strength_assessments: tuple[WalletStrengthAssessment, ...]
    missing_features: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != WALLET_FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {WALLET_FEATURE_SCHEMA_VERSION}"
            )
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_empty_string(
            "wallet_feature_policy_version", self.wallet_feature_policy_version
        )
        if self.profile_policy_version is not None:
            _require_non_empty_string(
                "profile_policy_version", self.profile_policy_version
            )
        if self.profile_context_version is not None:
            _require_non_empty_string(
                "profile_context_version", self.profile_context_version
            )
        _require_non_empty_string(
            "relationship_policy_version", self.relationship_policy_version
        )

        count_names = (
            "wallet_count",
            "recent_entry_wallet_count",
            "recent_exit_wallet_count",
            "strong_wallet_count",
            "unknown_strength_wallet_count",
            "strong_entry_wallet_count",
            "strong_exit_wallet_count",
            "entry_quality_profile_sample_count",
            "strong_entry_linked_pair_count",
            "strong_entry_conflicting_pair_count",
            "strong_entry_unknown_pair_count",
            "strong_entry_coordination_cluster_count",
            "strong_entry_max_independent_group_count_upper_bound",
            "creator_deployer_action_observation_count",
        )
        for name in count_names:
            _require_non_negative_int(name, getattr(self, name))

        if self.wallet_count == 0 and self.profile_policy_version is not None:
            raise ValueError("empty wallet vector cannot claim a profile policy version")
        if self.wallet_count > 0 and self.profile_policy_version is None:
            raise ValueError("non-empty wallet vector requires profile policy version")
        if self.recent_entry_wallet_count > self.wallet_count:
            raise ValueError("recent_entry_wallet_count cannot exceed wallet_count")
        if self.recent_exit_wallet_count > self.wallet_count:
            raise ValueError("recent_exit_wallet_count cannot exceed wallet_count")
        if self.strong_wallet_count > self.wallet_count:
            raise ValueError("strong_wallet_count cannot exceed wallet_count")
        if self.unknown_strength_wallet_count > self.wallet_count:
            raise ValueError("unknown_strength_wallet_count cannot exceed wallet_count")
        if self.strong_wallet_count + self.unknown_strength_wallet_count > self.wallet_count:
            raise ValueError("strength state counts cannot exceed wallet_count")
        if self.strong_entry_wallet_count > min(
            self.strong_wallet_count, self.recent_entry_wallet_count
        ):
            raise ValueError("strong_entry_wallet_count is inconsistent")
        if self.strong_exit_wallet_count > min(
            self.strong_wallet_count, self.recent_exit_wallet_count
        ):
            raise ValueError("strong_exit_wallet_count is inconsistent")

        weighted_entry = _require_non_negative_finite_number(
            "confidence_weighted_strong_entry_count",
            self.confidence_weighted_strong_entry_count,
        )
        weighted_exit = _require_non_negative_finite_number(
            "confidence_weighted_strong_exit_count",
            self.confidence_weighted_strong_exit_count,
        )
        if weighted_entry > float(self.strong_entry_wallet_count) + 1e-12:
            raise ValueError(
                "weighted strong entry count cannot exceed raw strong entry count"
            )
        if weighted_exit > float(self.strong_exit_wallet_count) + 1e-12:
            raise ValueError(
                "weighted strong exit count cannot exceed raw strong exit count"
            )

        if self.entry_quality_profile_sample_count > self.recent_entry_wallet_count:
            raise ValueError(
                "entry_quality_profile_sample_count cannot exceed recent entrants"
            )
        _require_optional_finite_number(
            "confidence_weighted_entry_median_return_pct",
            self.confidence_weighted_entry_median_return_pct,
        )
        _require_optional_rate(
            "confidence_weighted_entry_win_rate",
            self.confidence_weighted_entry_win_rate,
        )
        if self.entry_quality_profile_sample_count == 0:
            if (
                self.confidence_weighted_entry_median_return_pct is not None
                or self.confidence_weighted_entry_win_rate is not None
            ):
                raise ValueError("entry quality metrics require a positive sample count")
        elif (
            self.confidence_weighted_entry_median_return_pct is None
            or self.confidence_weighted_entry_win_rate is None
        ):
            raise ValueError("positive entry quality sample requires both quality metrics")

        if self.independently_strong_entry_wallet_count is not None:
            _require_non_negative_int(
                "independently_strong_entry_wallet_count",
                self.independently_strong_entry_wallet_count,
            )
            if self.independently_strong_entry_wallet_count > self.strong_entry_wallet_count:
                raise ValueError(
                    "independently_strong_entry_wallet_count cannot exceed strong entrants"
                )
        if (
            self.strong_entry_all_pairs_independent_under_evidence is not None
            and not isinstance(
                self.strong_entry_all_pairs_independent_under_evidence, bool
            )
        ):
            raise ValueError(
                "strong_entry_all_pairs_independent_under_evidence must be bool or None"
            )
        self._validate_independence_summary()

        if not isinstance(self.strength_assessments, tuple) or not all(
            type(value) is WalletStrengthAssessment
            for value in self.strength_assessments
        ):
            raise ValueError(
                "strength_assessments must be a tuple of WalletStrengthAssessment values"
            )
        wallets = tuple(value.wallet for value in self.strength_assessments)
        if tuple(sorted(set(wallets))) != wallets:
            raise ValueError(
                "strength_assessments must be unique and in lexical wallet order"
            )
        if len(self.strength_assessments) != self.wallet_count:
            raise ValueError("strength_assessments must reconcile to wallet_count")
        if sum(
            value.state is WalletHistoricalStrengthState.STRONG
            for value in self.strength_assessments
        ) != self.strong_wallet_count:
            raise ValueError("strong assessment count must reconcile")
        if sum(
            value.state is WalletHistoricalStrengthState.UNKNOWN
            for value in self.strength_assessments
        ) != self.unknown_strength_wallet_count:
            raise ValueError("unknown assessment count must reconcile")

        expected_missing = tuple(
            name
            for name in _MISSING_FEATURE_ORDER
            if getattr(self, name) is None
        )
        if self.missing_features != expected_missing:
            raise ValueError(
                "missing_features must exactly list unknown nullable D5 features"
            )

    def _validate_independence_summary(self) -> None:
        strong = self.strong_entry_wallet_count
        pair_total = strong * (strong - 1) // 2
        observed_special = (
            self.strong_entry_linked_pair_count
            + self.strong_entry_conflicting_pair_count
            + self.strong_entry_unknown_pair_count
        )
        if observed_special > pair_total:
            raise ValueError("strong-entry pair counts exceed possible pair count")
        if self.strong_entry_coordination_cluster_count > strong:
            raise ValueError("coordination cluster count cannot exceed strong entrants")
        if self.strong_entry_max_independent_group_count_upper_bound > strong:
            raise ValueError("independent-group upper bound cannot exceed strong entrants")
        if self.strong_entry_coordination_cluster_count > self.strong_entry_max_independent_group_count_upper_bound:
            raise ValueError("coordination cluster count cannot exceed group upper bound")

        if strong == 0:
            if self.independently_strong_entry_wallet_count != 0:
                raise ValueError("zero strong entrants require exact independent count zero")
            if self.strong_entry_all_pairs_independent_under_evidence is not None:
                raise ValueError("zero strong entrants require unknown all-pairs flag")
            if observed_special != 0 or self.strong_entry_coordination_cluster_count != 0 or self.strong_entry_max_independent_group_count_upper_bound != 0:
                raise ValueError("zero strong entrants require zero relationship summaries")
            return
        if strong == 1:
            if self.independently_strong_entry_wallet_count != 1:
                raise ValueError("one strong entrant requires independent count one")
            if self.strong_entry_all_pairs_independent_under_evidence is not True:
                raise ValueError("one strong entrant is trivially pair-independent")
            if observed_special != 0 or self.strong_entry_coordination_cluster_count != 0 or self.strong_entry_max_independent_group_count_upper_bound != 1:
                raise ValueError("one strong entrant has fixed relationship summaries")
            return

        has_coordination = (
            self.strong_entry_linked_pair_count > 0
            or self.strong_entry_conflicting_pair_count > 0
        )
        has_unknown = self.strong_entry_unknown_pair_count > 0
        if has_coordination:
            if self.strong_entry_all_pairs_independent_under_evidence is not False:
                raise ValueError("linked/conflicting strong entrants require false independence")
            if self.independently_strong_entry_wallet_count is not None:
                raise ValueError("coordinated strong entrants cannot claim exact independent count")
        elif has_unknown:
            if self.strong_entry_all_pairs_independent_under_evidence is not None:
                raise ValueError("unknown strong-entry pair requires unknown independence")
            if self.independently_strong_entry_wallet_count is not None:
                raise ValueError("unknown strong-entry pair prevents exact independent count")
        else:
            if self.strong_entry_all_pairs_independent_under_evidence is not True:
                raise ValueError("all known independent pairs require true independence")
            if self.independently_strong_entry_wallet_count != strong:
                raise ValueError("all independent strong entrants require exact raw count")


def _validate_check_tuple(name: str, values: object) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"{name} must contain strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
    if any(value not in _STRENGTH_CHECK_INDEX for value in values):
        raise ValueError(f"{name} contains an unknown strength check")
    if tuple(sorted(values, key=_STRENGTH_CHECK_INDEX.__getitem__)) != values:
        raise ValueError(f"{name} must use stable strength-check order")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be strictly positive")


def _require_finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _require_non_negative_finite_number(name: str, value: object) -> float:
    result = _require_finite_number(name, value)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _require_rate(name: str, value: object) -> float:
    result = _require_finite_number(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def _require_optional_rate(name: str, value: object | None) -> None:
    if value is not None:
        _require_rate(name, value)


def _require_optional_percentage(name: str, value: object | None) -> None:
    if value is None:
        return
    result = _require_finite_number(name, value)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{name} must be between 0 and 100")


def _require_optional_finite_number(name: str, value: object | None) -> None:
    if value is not None:
        _require_finite_number(name, value)
