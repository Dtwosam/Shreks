from __future__ import annotations

from dataclasses import dataclass
import string

from shreks_brain.fast_learning.models import (
    FastForecastBaselineArtifact,
    FastForecastPrediction,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_validation.models import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
)


FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME = (
    "shreks.fast_lane_chronological_generalization"
)
FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION = 1
FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION = (
    "fl8.3-chronological-generalization-v2"
)


@dataclass(frozen=True, slots=True)
class FastChronologicalGeneralizationPolicy:
    version: str
    folds: tuple[FastChronologicalFold, ...]
    feature_identity_firewall_version: str
    feature_identity_firewall_fingerprint_sha256: str
    minimum_unseen_mint_validation_rows: int
    minimum_unseen_mint_validation_mints: int
    minimum_unseen_mint_test_rows: int
    minimum_unseen_mint_test_mints: int

    def __post_init__(self) -> None:
        if self.version != FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION:
            raise ValueError("unsupported chronological generalization policy version")
        _non_empty(
            "feature_identity_firewall_version",
            self.feature_identity_firewall_version,
        )
        _sha256(
            "feature_identity_firewall_fingerprint_sha256",
            self.feature_identity_firewall_fingerprint_sha256,
        )
        for name in (
            "minimum_unseen_mint_validation_rows",
            "minimum_unseen_mint_validation_mints",
            "minimum_unseen_mint_test_rows",
            "minimum_unseen_mint_test_mints",
        ):
            _positive_int(name, getattr(self, name))

        # Reuse the sealed V1 fold validation only as a value-object validator.
        # V2 does not call the V1 engine or inherit its entity quarantine semantics.
        FastChronologicalValidationPolicy(
            version=f"{self.version}:fold-shape",
            folds=self.folds,
        )


@dataclass(frozen=True, slots=True)
class FastSignatureQuarantineSummary:
    shared_signature_count: int
    training_quarantined_row_count: int
    validation_quarantined_row_count: int
    test_quarantined_row_count: int
    quarantine_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "shared_signature_count",
            "training_quarantined_row_count",
            "validation_quarantined_row_count",
            "test_quarantined_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        _sha256(
            "quarantine_fingerprint_sha256",
            self.quarantine_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastFutureNoveltySummary:
    partition: str
    prediction_count: int
    unique_mint_count: int
    unseen_mint_identities: tuple[tuple[object, ...], ...]
    seen_mint_identities: tuple[tuple[object, ...], ...]
    unseen_mint_unique_mint_count: int
    seen_actor_row_count: int
    unseen_actor_row_count: int
    null_actor_row_count: int
    novelty_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.partition not in {"validation", "test"}:
            raise ValueError("novelty partition must be validation or test")
        for name in (
            "prediction_count",
            "unique_mint_count",
            "unseen_mint_unique_mint_count",
            "seen_actor_row_count",
            "unseen_actor_row_count",
            "null_actor_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if self.unseen_mint_unique_mint_count > self.unique_mint_count:
            raise ValueError("unseen mint count exceeds partition unique mint count")

        unseen = _canonical_identities(
            "unseen_mint_identities",
            self.unseen_mint_identities,
        )
        seen = _canonical_identities(
            "seen_mint_identities",
            self.seen_mint_identities,
        )
        if set(unseen).intersection(seen):
            raise ValueError("seen and unseen mint identities must be disjoint")
        if len(unseen) + len(seen) != self.prediction_count:
            raise ValueError("novelty identity counts do not reconcile")
        if len({identity[3] for identity in unseen}) != (
            self.unseen_mint_unique_mint_count
        ):
            raise ValueError("unseen mint count does not reconcile")
        if len({identity[3] for identity in (*unseen, *seen)}) != (
            self.unique_mint_count
        ):
            raise ValueError("unique mint count does not reconcile")
        if (
            self.seen_actor_row_count
            + self.unseen_actor_row_count
            + self.null_actor_row_count
            != self.prediction_count
        ):
            raise ValueError("actor novelty counts do not reconcile")
        _sha256(
            "novelty_fingerprint_sha256",
            self.novelty_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastChronologicalGeneralizationFoldResult:
    fold: FastChronologicalFold
    training_raw_row_count: int
    training_row_count: int
    training_target_unavailable_at_split_count: int
    validation_raw_row_count: int
    validation_row_count: int
    test_raw_row_count: int
    test_row_count: int
    signature_quarantine: FastSignatureQuarantineSummary
    validation_novelty: FastFutureNoveltySummary
    test_novelty: FastFutureNoveltySummary
    model: FastForecastBaselineArtifact
    validation_predictions: tuple[FastForecastPrediction, ...]
    test_predictions: tuple[FastForecastPrediction, ...]

    def __post_init__(self) -> None:
        if type(self.fold) is not FastChronologicalFold:
            raise ValueError("fold must be an exact FastChronologicalFold")
        for name in (
            "training_raw_row_count",
            "training_row_count",
            "training_target_unavailable_at_split_count",
            "validation_raw_row_count",
            "validation_row_count",
            "test_raw_row_count",
            "test_row_count",
        ):
            _non_negative_int(name, getattr(self, name))
        if type(self.signature_quarantine) is not FastSignatureQuarantineSummary:
            raise ValueError(
                "signature_quarantine must be exact FastSignatureQuarantineSummary"
            )
        if type(self.validation_novelty) is not FastFutureNoveltySummary:
            raise ValueError(
                "validation_novelty must be exact FastFutureNoveltySummary"
            )
        if type(self.test_novelty) is not FastFutureNoveltySummary:
            raise ValueError("test_novelty must be exact FastFutureNoveltySummary")
        if self.validation_novelty.partition != "validation":
            raise ValueError("validation novelty partition is incompatible")
        if self.test_novelty.partition != "test":
            raise ValueError("test novelty partition is incompatible")
        if type(self.model) is not FastForecastBaselineArtifact:
            raise ValueError("model must be exact FastForecastBaselineArtifact")
        _predictions("validation_predictions", self.validation_predictions)
        _predictions("test_predictions", self.test_predictions)

        if self.training_row_count > self.training_raw_row_count:
            raise ValueError("training post-quarantine count exceeds raw count")
        if self.validation_row_count > self.validation_raw_row_count:
            raise ValueError("validation post-quarantine count exceeds raw count")
        if self.test_row_count > self.test_raw_row_count:
            raise ValueError("test post-quarantine count exceeds raw count")
        if (
            self.training_raw_row_count - self.training_row_count
            != self.signature_quarantine.training_quarantined_row_count
        ):
            raise ValueError("training signature quarantine counts do not reconcile")
        if (
            self.validation_raw_row_count - self.validation_row_count
            != self.signature_quarantine.validation_quarantined_row_count
        ):
            raise ValueError(
                "validation signature quarantine counts do not reconcile"
            )
        if (
            self.test_raw_row_count - self.test_row_count
            != self.signature_quarantine.test_quarantined_row_count
        ):
            raise ValueError("test signature quarantine counts do not reconcile")
        if (
            self.model.training_row_count
            + self.training_target_unavailable_at_split_count
            != self.training_row_count
        ):
            raise ValueError("training target availability counts do not reconcile")
        if len(self.validation_predictions) != self.validation_row_count:
            raise ValueError("validation prediction count does not reconcile")
        if len(self.test_predictions) != self.test_row_count:
            raise ValueError("test prediction count does not reconcile")
        if self.validation_novelty.prediction_count != self.validation_row_count:
            raise ValueError("validation novelty count does not reconcile")
        if self.test_novelty.prediction_count != self.test_row_count:
            raise ValueError("test novelty count does not reconcile")
        if (
            self.model.max_training_decision_observed_at_unix_ms
            + self.model.horizon_ms
            > self.fold.validation_started_at_unix_ms
        ):
            raise ValueError(
                "training artifact maturity crosses validation boundary"
            )

        _validate_prediction_population(
            role="validation",
            predictions=self.validation_predictions,
            novelty=self.validation_novelty,
            model=self.model,
            started_at_unix_ms=self.fold.validation_started_at_unix_ms,
            ended_at_unix_ms=self.fold.validation_ended_at_unix_ms,
        )
        _validate_prediction_population(
            role="test",
            predictions=self.test_predictions,
            novelty=self.test_novelty,
            model=self.model,
            started_at_unix_ms=self.fold.test_started_at_unix_ms,
            ended_at_unix_ms=self.fold.test_ended_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class FastChronologicalGeneralizationRun:
    schema_name: str
    schema_version: int
    validation_policy_version: str
    training_request: FastForecastTrainingRequest
    training_bundle_fingerprint_sha256: str
    feature_identity_firewall_version: str
    feature_identity_firewall_fingerprint_sha256: str
    fold_results: tuple[FastChronologicalGeneralizationFoldResult, ...]
    validation_run_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME:
            raise ValueError("chronological generalization schema name is incompatible")
        if self.schema_version != FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION:
            raise ValueError(
                "chronological generalization schema version is incompatible"
            )
        if (
            self.validation_policy_version
            != FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION
        ):
            raise ValueError(
                "chronological generalization policy version is incompatible"
            )
        if type(self.training_request) is not FastForecastTrainingRequest:
            raise ValueError(
                "training_request must be exact FastForecastTrainingRequest"
            )
        _sha256(
            "training_bundle_fingerprint_sha256",
            self.training_bundle_fingerprint_sha256,
        )
        _non_empty(
            "feature_identity_firewall_version",
            self.feature_identity_firewall_version,
        )
        _sha256(
            "feature_identity_firewall_fingerprint_sha256",
            self.feature_identity_firewall_fingerprint_sha256,
        )
        if not isinstance(self.fold_results, tuple) or not self.fold_results:
            raise ValueError("fold_results must be a non-empty tuple")
        if not all(
            type(value) is FastChronologicalGeneralizationFoldResult
            for value in self.fold_results
        ):
            raise ValueError(
                "fold_results must contain exact FastChronologicalGeneralizationFoldResult values"
            )
        expected = tuple(
            sorted(
                self.fold_results,
                key=lambda value: _fold_sort_key(value.fold),
            )
        )
        if self.fold_results != expected:
            raise ValueError("fold_results must be in canonical order")
        names = tuple(value.fold.name for value in self.fold_results)
        if len(set(names)) != len(names):
            raise ValueError("fold result names must be unique")
        _sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )


def _canonical_identities(
    name: str,
    identities: object,
) -> tuple[tuple[object, ...], ...]:
    if not isinstance(identities, tuple):
        raise ValueError(f"{name} must be a tuple")
    for identity in identities:
        _decision_identity(identity)
    if len(set(identities)) != len(identities):
        raise ValueError(f"{name} must be unique")
    expected = tuple(sorted(identities, key=_identity_sort_key))
    if identities != expected:
        raise ValueError(f"{name} must be in canonical order")
    return identities


def _decision_identity(identity: object) -> None:
    if not isinstance(identity, tuple) or len(identity) != 7:
        raise ValueError("decision identity must use the FL8.1 seven-field shape")
    signature, ordinal, sequence, mint, quote_mint, venue, observed = identity
    for name, value in (
        ("signature", signature),
        ("mint", mint),
        ("quote_mint", quote_mint),
        ("venue", venue),
    ):
        _non_empty(name, value)
    for name, value in (
        ("ordinal", ordinal),
        ("sequence", sequence),
        ("observed_at_unix_ms", observed),
    ):
        _non_negative_int(name, value)


def _predictions(name: str, values: object) -> None:
    if not isinstance(values, tuple) or not all(
        type(value) is FastForecastPrediction for value in values
    ):
        raise ValueError(f"{name} must contain exact FastForecastPrediction values")
    identities = tuple(value.decision_identity for value in values)
    _canonical_identities(name, identities)


def _identity_sort_key(identity: tuple[object, ...]) -> tuple[object, ...]:
    return (identity[6], identity[2], identity[0], identity[1])


def _validate_prediction_population(
    *,
    role: str,
    predictions: tuple[FastForecastPrediction, ...],
    novelty: FastFutureNoveltySummary,
    model: FastForecastBaselineArtifact,
    started_at_unix_ms: int,
    ended_at_unix_ms: int,
) -> None:
    prediction_identities = tuple(
        value.decision_identity for value in predictions
    )
    novelty_identities = tuple(
        sorted(
            (
                *novelty.unseen_mint_identities,
                *novelty.seen_mint_identities,
            ),
            key=_identity_sort_key,
        )
    )
    if novelty_identities != prediction_identities:
        raise ValueError(
            f"{role} novelty identities do not reconcile to predictions"
        )

    for prediction in predictions:
        if (
            prediction.model_version != model.model_version
            or prediction.target is not model.target
            or prediction.horizon_ms != model.horizon_ms
        ):
            raise ValueError(
                f"{role} prediction metadata contradicts fitted model"
            )
        observed_at_unix_ms = prediction.decision_identity[6]
        if not (
            started_at_unix_ms
            <= observed_at_unix_ms
            < ended_at_unix_ms
        ):
            raise ValueError(
                f"{role} prediction timestamp is outside declared interval"
            )


def _fold_sort_key(fold: FastChronologicalFold) -> tuple[int, int, int, int, str]:
    return (
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
        fold.name,
    )


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _positive_int(name: str, value: object) -> None:
    _non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 digest")
