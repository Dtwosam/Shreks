from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from shreks_brain.fast_first_champion.builder import _REQUIRED_MEMBERS
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
    run_fast_chronological_validation,
)
from shreks_brain.research.fast_training_bundle import (
    FastTrainingBundle,
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    future_path_logical_fingerprint_sha256,
)


FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME = (
    "shreks.fast_first_champion_evidence_plan"
)
FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION = 1
FAST_FIRST_CHAMPION_EVIDENCE_PLAN_VERSION = (
    "fl9-first-champion-evidence-plan-v1"
)
FAST_FIRST_CHAMPION_PLAN_VALIDATION_POLICY_VERSION = (
    "fl9-first-champion-60-20-20-v1"
)
FAST_FIRST_CHAMPION_PLAN_FOLD_NAME = "first-champion-60-20-20-v1"
FAST_FIRST_CHAMPION_PLAN_TRAINING_POLICY_VERSION = (
    "fl9-first-champion-plan-naive-v1"
)

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "plan",
        "plan_fingerprint_sha256",
    }
)
_PLAN_KEYS = frozenset(
    {
        "version",
        "training_bundle_fingerprint_sha256",
        "feature_logical_fingerprint_sha256",
        "feature_source_jsonl_sha256",
        "future_path_logical_fingerprint_sha256",
        "horizon_ms",
        "selection_at_unix_ms",
        "minimum_raw_rows_per_partition",
        "minimum_test_scored_observations",
        "eligible_preselection_row_count",
        "validation_policy",
        "training_raw_row_count",
        "training_row_count",
        "validation_raw_row_count",
        "validation_row_count",
        "test_raw_row_count",
        "test_row_count",
        "quarantine_fingerprint_sha256",
        "target_evidence",
    }
)
_TARGET_KEYS = frozenset(
    {
        "target",
        "model_family",
        "validation_run_fingerprint_sha256",
        "test_prediction_count",
        "test_target_available_count",
    }
)
_FOLD_KEYS = frozenset(
    {
        "name",
        "training_started_at_unix_ms",
        "training_ended_at_unix_ms",
        "validation_started_at_unix_ms",
        "validation_ended_at_unix_ms",
        "test_started_at_unix_ms",
        "test_ended_at_unix_ms",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionTargetEvidence:
    target: FastForecastTarget
    model_family: FastForecastModelFamily
    validation_run_fingerprint_sha256: str
    test_prediction_count: int
    test_target_available_count: int

    def __post_init__(self) -> None:
        if type(self.target) is not FastForecastTarget:
            raise ValueError("target must be exact FastForecastTarget")
        if type(self.model_family) is not FastForecastModelFamily:
            raise ValueError(
                "model_family must be exact FastForecastModelFamily"
            )
        _require_sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )
        _require_positive_int(
            "test_prediction_count",
            self.test_prediction_count,
        )
        _require_non_negative_int(
            "test_target_available_count",
            self.test_target_available_count,
        )
        if self.test_target_available_count > self.test_prediction_count:
            raise ValueError(
                "test target availability cannot exceed prediction count"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionEvidencePlan:
    schema_name: str
    schema_version: int
    version: str
    training_bundle_fingerprint_sha256: str
    feature_logical_fingerprint_sha256: str
    feature_source_jsonl_sha256: str
    future_path_logical_fingerprint_sha256: str
    horizon_ms: int
    selection_at_unix_ms: int
    minimum_raw_rows_per_partition: int
    minimum_test_scored_observations: int
    eligible_preselection_row_count: int
    validation_policy: FastChronologicalValidationPolicy
    training_raw_row_count: int
    training_row_count: int
    validation_raw_row_count: int
    validation_row_count: int
    test_raw_row_count: int
    test_row_count: int
    quarantine_fingerprint_sha256: str
    target_evidence: tuple[FastFirstChampionTargetEvidence, ...]
    plan_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME:
            raise ValueError(
                "unsupported first champion evidence plan schema_name"
            )
        if self.schema_version != FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION:
            raise ValueError(
                "unsupported first champion evidence plan schema_version"
            )
        if self.version != FAST_FIRST_CHAMPION_EVIDENCE_PLAN_VERSION:
            raise ValueError(
                "unsupported first champion evidence plan version"
            )
        for name in (
            "training_bundle_fingerprint_sha256",
            "feature_logical_fingerprint_sha256",
            "feature_source_jsonl_sha256",
            "future_path_logical_fingerprint_sha256",
            "quarantine_fingerprint_sha256",
            "plan_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        for name in (
            "horizon_ms",
            "minimum_raw_rows_per_partition",
            "minimum_test_scored_observations",
            "eligible_preselection_row_count",
            "training_raw_row_count",
            "training_row_count",
            "validation_raw_row_count",
            "validation_row_count",
            "test_raw_row_count",
            "test_row_count",
        ):
            _require_positive_int(name, getattr(self, name))
        _require_non_negative_int(
            "selection_at_unix_ms",
            self.selection_at_unix_ms,
        )
        if type(self.validation_policy) is not FastChronologicalValidationPolicy:
            raise ValueError(
                "validation_policy must be exact FastChronologicalValidationPolicy"
            )
        if (
            self.validation_policy.version
            != FAST_FIRST_CHAMPION_PLAN_VALIDATION_POLICY_VERSION
            or len(self.validation_policy.folds) != 1
            or self.validation_policy.folds[0].name
            != FAST_FIRST_CHAMPION_PLAN_FOLD_NAME
        ):
            raise ValueError(
                "first champion evidence plan validation policy is incompatible"
            )
        if (
            self.training_raw_row_count
            + self.validation_raw_row_count
            + self.test_raw_row_count
            != self.eligible_preselection_row_count
        ):
            raise ValueError(
                "first champion evidence plan raw counts do not reconcile"
            )
        for raw_name, post_name in (
            ("training_raw_row_count", "training_row_count"),
            ("validation_raw_row_count", "validation_row_count"),
            ("test_raw_row_count", "test_row_count"),
        ):
            if getattr(self, post_name) > getattr(self, raw_name):
                raise ValueError(
                    "first champion evidence plan post-quarantine count exceeds raw count"
                )
        expected_members = tuple(
            (target, family) for target, family in _REQUIRED_MEMBERS
        )
        actual_members = tuple(
            (value.target, value.model_family)
            for value in self.target_evidence
        )
        if actual_members != expected_members:
            raise ValueError(
                "first champion target evidence does not match required member order"
            )
        if any(
            value.test_prediction_count != self.test_row_count
            for value in self.target_evidence
        ):
            raise ValueError(
                "first champion target TEST prediction counts do not reconcile"
            )
        if any(
            value.test_target_available_count
            < self.minimum_test_scored_observations
            for value in self.target_evidence
        ):
            raise ValueError(
                "first champion target evidence is below TEST minimum"
            )
        expected = _sha256_canonical(_plan_material(self))
        if self.plan_fingerprint_sha256 != expected:
            raise ValueError(
                "first champion evidence plan fingerprint mismatch"
            )


def build_fast_first_champion_evidence_plan(
    *,
    bundle: FastTrainingBundle,
    horizon_ms: int,
    selection_at_unix_ms: int,
    minimum_raw_rows_per_partition: int,
    minimum_test_scored_observations: int,
) -> FastFirstChampionEvidencePlan:
    _validate_bundle(bundle)
    _require_positive_int("horizon_ms", horizon_ms)
    _require_non_negative_int(
        "selection_at_unix_ms",
        selection_at_unix_ms,
    )
    _require_positive_int(
        "minimum_raw_rows_per_partition",
        minimum_raw_rows_per_partition,
    )
    _require_positive_int(
        "minimum_test_scored_observations",
        minimum_test_scored_observations,
    )
    if selection_at_unix_ms <= horizon_ms:
        raise ValueError(
            "selection timestamp must be later than the forecast horizon"
        )

    test_end = selection_at_unix_ms - horizon_ms
    records = tuple(
        sorted(
            (
                record
                for record in bundle.features.records
                if record.decision_observed_at_unix_ms < test_end
            ),
            key=_record_sort_key,
        )
    )
    minimum_total = 3 * minimum_raw_rows_per_partition
    if len(records) < minimum_total:
        raise ValueError(
            "eligible preselection evidence cannot fill all three partitions"
        )

    buckets = _timestamp_buckets(records)
    cut_one_index = _choose_training_boundary(
        buckets,
        minimum_raw_rows_per_partition,
    )
    training_count = sum(
        count for _, count in buckets[:cut_one_index]
    )
    cut_two_index = _choose_validation_boundary(
        buckets,
        cut_one_index=cut_one_index,
        training_count=training_count,
        total_count=len(records),
        minimum_rows=minimum_raw_rows_per_partition,
    )

    training_start = buckets[0][0]
    training_end = buckets[cut_one_index][0]
    validation_end = buckets[cut_two_index][0]
    policy = FastChronologicalValidationPolicy(
        version=FAST_FIRST_CHAMPION_PLAN_VALIDATION_POLICY_VERSION,
        folds=(
            FastChronologicalFold(
                name=FAST_FIRST_CHAMPION_PLAN_FOLD_NAME,
                training_started_at_unix_ms=training_start,
                training_ended_at_unix_ms=training_end,
                validation_started_at_unix_ms=training_end,
                validation_ended_at_unix_ms=validation_end,
                test_started_at_unix_ms=validation_end,
                test_ended_at_unix_ms=test_end,
            ),
        ),
    )

    labels_by_identity = _labels_for_horizon(bundle, horizon_ms)
    target_evidence: list[FastFirstChampionTargetEvidence] = []
    canonical_counts: tuple[int, int, int, int, int, int] | None = None
    canonical_quarantine: str | None = None
    canonical_test_identities: tuple[tuple[object, ...], ...] | None = None

    for target, family in _REQUIRED_MEMBERS:
        request = FastForecastTrainingRequest(
            model_version=(
                f"fl9-first-champion-plan:{target.value}@{horizon_ms}ms"
            ),
            model_family=family,
            target=target,
            horizon_ms=horizon_ms,
            training_policy=FastForecastTrainingPolicy(
                version=FAST_FIRST_CHAMPION_PLAN_TRAINING_POLICY_VERSION,
            ),
        )
        try:
            run = run_fast_chronological_validation(
                bundle,
                request,
                policy,
            )
        except (ValueError, RuntimeError) as exc:
            raise type(exc)(
                f"first champion evidence plan target {target.value}: {exc}"
            ) from exc
        if len(run.fold_results) != 1:
            raise ValueError(
                "first champion evidence plan requires exactly one validation fold result"
            )
        fold_result = run.fold_results[0]
        counts = (
            fold_result.training_raw_row_count,
            fold_result.training_row_count,
            fold_result.validation_raw_row_count,
            fold_result.validation_row_count,
            fold_result.test_raw_row_count,
            fold_result.test_row_count,
        )
        test_identities = tuple(
            prediction.decision_identity
            for prediction in fold_result.test_predictions
        )
        if canonical_counts is None:
            canonical_counts = counts
            canonical_quarantine = (
                fold_result.quarantine.quarantine_fingerprint_sha256
            )
            canonical_test_identities = test_identities
        elif (
            counts != canonical_counts
            or fold_result.quarantine.quarantine_fingerprint_sha256
            != canonical_quarantine
            or test_identities != canonical_test_identities
        ):
            raise ValueError(
                "first champion required targets produced different validation populations"
            )

        available_count = 0
        for identity in test_identities:
            label = labels_by_identity.get(identity)
            if label is None:
                raise ValueError(
                    f"first champion TEST identity lacks horizon label for {target.value}"
                )
            if getattr(label, target.value) is not None:
                available_count += 1
        if available_count < minimum_test_scored_observations:
            raise ValueError(
                f"{target.value} TEST target evidence does not meet the explicit minimum"
            )
        target_evidence.append(
            FastFirstChampionTargetEvidence(
                target=target,
                model_family=family,
                validation_run_fingerprint_sha256=(
                    run.validation_run_fingerprint_sha256
                ),
                test_prediction_count=len(test_identities),
                test_target_available_count=available_count,
            )
        )

    if canonical_counts is None or canonical_quarantine is None:
        raise ValueError("first champion evidence plan produced no target evidence")
    (
        training_raw,
        training_post,
        validation_raw,
        validation_post,
        test_raw,
        test_post,
    ) = canonical_counts
    if min(training_raw, validation_raw, test_raw) < (
        minimum_raw_rows_per_partition
    ):
        raise ValueError(
            "first champion evidence plan raw partition floor was not preserved"
        )

    material = {
        "version": FAST_FIRST_CHAMPION_EVIDENCE_PLAN_VERSION,
        "training_bundle_fingerprint_sha256": (
            bundle.manifest.bundle_fingerprint_sha256
        ),
        "feature_logical_fingerprint_sha256": (
            bundle.features.logical_fingerprint_sha256
        ),
        "feature_source_jsonl_sha256": bundle.features.source_sha256,
        "future_path_logical_fingerprint_sha256": (
            bundle.future_path_labels.logical_fingerprint_sha256
        ),
        "horizon_ms": horizon_ms,
        "selection_at_unix_ms": selection_at_unix_ms,
        "minimum_raw_rows_per_partition": (
            minimum_raw_rows_per_partition
        ),
        "minimum_test_scored_observations": (
            minimum_test_scored_observations
        ),
        "eligible_preselection_row_count": len(records),
        "validation_policy": _validation_policy_document(policy),
        "training_raw_row_count": training_raw,
        "training_row_count": training_post,
        "validation_raw_row_count": validation_raw,
        "validation_row_count": validation_post,
        "test_raw_row_count": test_raw,
        "test_row_count": test_post,
        "quarantine_fingerprint_sha256": canonical_quarantine,
        "target_evidence": [
            _target_evidence_document(value)
            for value in target_evidence
        ],
    }
    return FastFirstChampionEvidencePlan(
        schema_name=FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME,
        schema_version=FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION,
        version=material["version"],
        training_bundle_fingerprint_sha256=material[
            "training_bundle_fingerprint_sha256"
        ],
        feature_logical_fingerprint_sha256=material[
            "feature_logical_fingerprint_sha256"
        ],
        feature_source_jsonl_sha256=material[
            "feature_source_jsonl_sha256"
        ],
        future_path_logical_fingerprint_sha256=material[
            "future_path_logical_fingerprint_sha256"
        ],
        horizon_ms=horizon_ms,
        selection_at_unix_ms=selection_at_unix_ms,
        minimum_raw_rows_per_partition=(
            minimum_raw_rows_per_partition
        ),
        minimum_test_scored_observations=(
            minimum_test_scored_observations
        ),
        eligible_preselection_row_count=len(records),
        validation_policy=policy,
        training_raw_row_count=training_raw,
        training_row_count=training_post,
        validation_raw_row_count=validation_raw,
        validation_row_count=validation_post,
        test_raw_row_count=test_raw,
        test_row_count=test_post,
        quarantine_fingerprint_sha256=canonical_quarantine,
        target_evidence=tuple(target_evidence),
        plan_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_first_champion_evidence_plan(
    plan: FastFirstChampionEvidencePlan,
) -> str:
    if type(plan) is not FastFirstChampionEvidencePlan:
        raise ValueError(
            "plan must be exact FastFirstChampionEvidencePlan"
        )
    if plan.plan_fingerprint_sha256 != _sha256_canonical(
        _plan_material(plan)
    ):
        raise ValueError(
            "first champion evidence plan fingerprint mismatch before encode"
        )
    return _canonical(
        {
            "schema_name": plan.schema_name,
            "schema_version": plan.schema_version,
            "plan": _plan_material(plan),
            "plan_fingerprint_sha256": plan.plan_fingerprint_sha256,
        }
    )


def decode_fast_first_champion_evidence_plan(
    payload: str,
) -> FastFirstChampionEvidencePlan:
    document = _load_canonical(
        payload,
        label="first champion evidence plan",
    )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "first champion evidence plan has unknown or missing top-level fields"
        )
    if (
        document["schema_name"]
        != FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_NAME
        or document["schema_version"]
        != FAST_FIRST_CHAMPION_EVIDENCE_PLAN_SCHEMA_VERSION
    ):
        raise ValueError("unsupported first champion evidence plan schema")
    raw = document["plan"]
    if not isinstance(raw, dict) or frozenset(raw) != _PLAN_KEYS:
        raise ValueError(
            "first champion evidence plan fields are incompatible"
        )
    policy = _decode_validation_policy(raw["validation_policy"])
    raw_targets = raw["target_evidence"]
    if not isinstance(raw_targets, list):
        raise ValueError(
            "first champion target_evidence must be an array"
        )
    target_evidence = tuple(
        _decode_target_evidence(value) for value in raw_targets
    )
    plan = FastFirstChampionEvidencePlan(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        version=_text(raw["version"], "version"),
        training_bundle_fingerprint_sha256=_text(
            raw["training_bundle_fingerprint_sha256"],
            "training_bundle_fingerprint_sha256",
        ),
        feature_logical_fingerprint_sha256=_text(
            raw["feature_logical_fingerprint_sha256"],
            "feature_logical_fingerprint_sha256",
        ),
        feature_source_jsonl_sha256=_text(
            raw["feature_source_jsonl_sha256"],
            "feature_source_jsonl_sha256",
        ),
        future_path_logical_fingerprint_sha256=_text(
            raw["future_path_logical_fingerprint_sha256"],
            "future_path_logical_fingerprint_sha256",
        ),
        horizon_ms=_integer(raw["horizon_ms"], "horizon_ms"),
        selection_at_unix_ms=_integer(
            raw["selection_at_unix_ms"],
            "selection_at_unix_ms",
        ),
        minimum_raw_rows_per_partition=_integer(
            raw["minimum_raw_rows_per_partition"],
            "minimum_raw_rows_per_partition",
        ),
        minimum_test_scored_observations=_integer(
            raw["minimum_test_scored_observations"],
            "minimum_test_scored_observations",
        ),
        eligible_preselection_row_count=_integer(
            raw["eligible_preselection_row_count"],
            "eligible_preselection_row_count",
        ),
        validation_policy=policy,
        training_raw_row_count=_integer(
            raw["training_raw_row_count"],
            "training_raw_row_count",
        ),
        training_row_count=_integer(
            raw["training_row_count"],
            "training_row_count",
        ),
        validation_raw_row_count=_integer(
            raw["validation_raw_row_count"],
            "validation_raw_row_count",
        ),
        validation_row_count=_integer(
            raw["validation_row_count"],
            "validation_row_count",
        ),
        test_raw_row_count=_integer(
            raw["test_raw_row_count"],
            "test_raw_row_count",
        ),
        test_row_count=_integer(
            raw["test_row_count"],
            "test_row_count",
        ),
        quarantine_fingerprint_sha256=_text(
            raw["quarantine_fingerprint_sha256"],
            "quarantine_fingerprint_sha256",
        ),
        target_evidence=target_evidence,
        plan_fingerprint_sha256=_text(
            document["plan_fingerprint_sha256"],
            "plan_fingerprint_sha256",
        ),
    )
    if encode_fast_first_champion_evidence_plan(plan) != payload:
        raise ValueError(
            "first champion evidence plan must use canonical JSON"
        )
    return plan


def write_fast_first_champion_evidence_plan(
    plan: FastFirstChampionEvidencePlan,
    path: str | Path,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        encode_fast_first_champion_evidence_plan(plan),
        encoding="utf-8",
    )


def read_fast_first_champion_evidence_plan(
    path: str | Path,
) -> FastFirstChampionEvidencePlan:
    return decode_fast_first_champion_evidence_plan(
        Path(path).read_text(encoding="utf-8")
    )


def _validate_bundle(bundle: FastTrainingBundle) -> None:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be exact FastTrainingBundle")
    if (
        bundle.manifest.bundle_fingerprint_sha256
        != bundle_logical_fingerprint_sha256(bundle.manifest)
    ):
        raise ValueError("training bundle manifest fingerprint is invalid")
    actual_feature = feature_logical_fingerprint_sha256(
        bundle.features.records
    )
    if (
        bundle.features.logical_fingerprint_sha256 != actual_feature
        or bundle.manifest.feature_logical_fingerprint_sha256
        != actual_feature
    ):
        raise ValueError("training bundle feature fingerprint is invalid")
    actual_future = future_path_logical_fingerprint_sha256(
        bundle.future_path_labels.labels
    )
    if (
        bundle.future_path_labels.logical_fingerprint_sha256
        != actual_future
        or bundle.manifest.future_path_logical_fingerprint_sha256
        != actual_future
    ):
        raise ValueError(
            "training bundle future-path fingerprint is invalid"
        )


def _timestamp_buckets(records) -> tuple[tuple[int, int], ...]:
    counts: dict[int, int] = {}
    for record in records:
        observed = record.decision_observed_at_unix_ms
        counts[observed] = counts.get(observed, 0) + 1
    buckets = tuple(sorted(counts.items()))
    if len(buckets) < 3:
        raise ValueError(
            "eligible preselection evidence needs at least three distinct timestamps"
        )
    return buckets


def _choose_training_boundary(
    buckets: tuple[tuple[int, int], ...],
    minimum_rows: int,
) -> int:
    total = sum(count for _, count in buckets)
    cumulative = 0
    candidates: list[tuple[int, int, int]] = []
    for index in range(1, len(buckets) - 1):
        cumulative += buckets[index - 1][1]
        remaining = total - cumulative
        if cumulative < minimum_rows or remaining < 2 * minimum_rows:
            continue
        candidates.append(
            (
                abs(5 * cumulative - 3 * total),
                cumulative,
                index,
            )
        )
    if not candidates:
        raise ValueError(
            "eligible preselection evidence cannot form a 60/20/20 training boundary"
        )
    return min(candidates)[2]


def _choose_validation_boundary(
    buckets: tuple[tuple[int, int], ...],
    *,
    cut_one_index: int,
    training_count: int,
    total_count: int,
    minimum_rows: int,
) -> int:
    cumulative = training_count
    candidates: list[tuple[int, int, int]] = []
    for index in range(cut_one_index + 1, len(buckets)):
        cumulative += buckets[index - 1][1]
        validation_count = cumulative - training_count
        test_count = total_count - cumulative
        if (
            validation_count < minimum_rows
            or test_count < minimum_rows
        ):
            continue
        candidates.append(
            (
                abs(5 * cumulative - 4 * total_count),
                cumulative,
                index,
            )
        )
    if not candidates:
        raise ValueError(
            "eligible preselection evidence cannot form a 60/20/20 validation boundary"
        )
    return min(candidates)[2]


def _labels_for_horizon(
    bundle: FastTrainingBundle,
    horizon_ms: int,
):
    result = {}
    for label in bundle.future_path_labels.labels:
        if label.horizon_ms != horizon_ms:
            continue
        identity = label.decision_identity
        if identity in result:
            raise ValueError(
                "requested horizon contains duplicate future-path decision identities"
            )
        result[identity] = label
    if not result:
        raise ValueError(
            "requested horizon contains no future-path evidence"
        )
    return result


def _plan_material(
    plan: FastFirstChampionEvidencePlan,
) -> dict[str, object]:
    return {
        "version": plan.version,
        "training_bundle_fingerprint_sha256": (
            plan.training_bundle_fingerprint_sha256
        ),
        "feature_logical_fingerprint_sha256": (
            plan.feature_logical_fingerprint_sha256
        ),
        "feature_source_jsonl_sha256": (
            plan.feature_source_jsonl_sha256
        ),
        "future_path_logical_fingerprint_sha256": (
            plan.future_path_logical_fingerprint_sha256
        ),
        "horizon_ms": plan.horizon_ms,
        "selection_at_unix_ms": plan.selection_at_unix_ms,
        "minimum_raw_rows_per_partition": (
            plan.minimum_raw_rows_per_partition
        ),
        "minimum_test_scored_observations": (
            plan.minimum_test_scored_observations
        ),
        "eligible_preselection_row_count": (
            plan.eligible_preselection_row_count
        ),
        "validation_policy": _validation_policy_document(
            plan.validation_policy
        ),
        "training_raw_row_count": plan.training_raw_row_count,
        "training_row_count": plan.training_row_count,
        "validation_raw_row_count": plan.validation_raw_row_count,
        "validation_row_count": plan.validation_row_count,
        "test_raw_row_count": plan.test_raw_row_count,
        "test_row_count": plan.test_row_count,
        "quarantine_fingerprint_sha256": (
            plan.quarantine_fingerprint_sha256
        ),
        "target_evidence": [
            _target_evidence_document(value)
            for value in plan.target_evidence
        ],
    }


def _target_evidence_document(
    value: FastFirstChampionTargetEvidence,
) -> dict[str, object]:
    return {
        "target": value.target.value,
        "model_family": value.model_family.value,
        "validation_run_fingerprint_sha256": (
            value.validation_run_fingerprint_sha256
        ),
        "test_prediction_count": value.test_prediction_count,
        "test_target_available_count": (
            value.test_target_available_count
        ),
    }


def _decode_target_evidence(
    value: object,
) -> FastFirstChampionTargetEvidence:
    if not isinstance(value, dict) or frozenset(value) != _TARGET_KEYS:
        raise ValueError(
            "first champion target evidence fields are incompatible"
        )
    try:
        target = FastForecastTarget(
            _text(value["target"], "target")
        )
        family = FastForecastModelFamily(
            _text(value["model_family"], "model_family")
        )
    except ValueError as exc:
        raise ValueError(
            "first champion target evidence enum is incompatible"
        ) from exc
    return FastFirstChampionTargetEvidence(
        target=target,
        model_family=family,
        validation_run_fingerprint_sha256=_text(
            value["validation_run_fingerprint_sha256"],
            "validation_run_fingerprint_sha256",
        ),
        test_prediction_count=_integer(
            value["test_prediction_count"],
            "test_prediction_count",
        ),
        test_target_available_count=_integer(
            value["test_target_available_count"],
            "test_target_available_count",
        ),
    )


def _validation_policy_document(
    policy: FastChronologicalValidationPolicy,
) -> dict[str, object]:
    return {
        "version": policy.version,
        "folds": [
            {
                "name": fold.name,
                "training_started_at_unix_ms": (
                    fold.training_started_at_unix_ms
                ),
                "training_ended_at_unix_ms": (
                    fold.training_ended_at_unix_ms
                ),
                "validation_started_at_unix_ms": (
                    fold.validation_started_at_unix_ms
                ),
                "validation_ended_at_unix_ms": (
                    fold.validation_ended_at_unix_ms
                ),
                "test_started_at_unix_ms": (
                    fold.test_started_at_unix_ms
                ),
                "test_ended_at_unix_ms": (
                    fold.test_ended_at_unix_ms
                ),
            }
            for fold in policy.folds
        ],
    }


def _decode_validation_policy(
    value: object,
) -> FastChronologicalValidationPolicy:
    if not isinstance(value, dict) or frozenset(value) != {
        "version",
        "folds",
    }:
        raise ValueError(
            "first champion validation policy fields are incompatible"
        )
    raw_folds = value["folds"]
    if not isinstance(raw_folds, list) or len(raw_folds) != 1:
        raise ValueError(
            "first champion evidence plan requires exactly one fold"
        )
    raw = raw_folds[0]
    if not isinstance(raw, dict) or frozenset(raw) != _FOLD_KEYS:
        raise ValueError(
            "first champion validation fold fields are incompatible"
        )
    return FastChronologicalValidationPolicy(
        version=_text(value["version"], "validation policy version"),
        folds=(
            FastChronologicalFold(
                name=_text(raw["name"], "fold name"),
                training_started_at_unix_ms=_integer(
                    raw["training_started_at_unix_ms"],
                    "training_started_at_unix_ms",
                ),
                training_ended_at_unix_ms=_integer(
                    raw["training_ended_at_unix_ms"],
                    "training_ended_at_unix_ms",
                ),
                validation_started_at_unix_ms=_integer(
                    raw["validation_started_at_unix_ms"],
                    "validation_started_at_unix_ms",
                ),
                validation_ended_at_unix_ms=_integer(
                    raw["validation_ended_at_unix_ms"],
                    "validation_ended_at_unix_ms",
                ),
                test_started_at_unix_ms=_integer(
                    raw["test_started_at_unix_ms"],
                    "test_started_at_unix_ms",
                ),
                test_ended_at_unix_ms=_integer(
                    raw["test_ended_at_unix_ms"],
                    "test_ended_at_unix_ms",
                ),
            ),
        ),
    )


def _record_sort_key(record) -> tuple[object, ...]:
    return (
        record.decision_observed_at_unix_ms,
        record.decision_sequence,
        record.decision_signature,
        record.decision_ordinal,
    )


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(f"{label} must have exactly one trailing newline")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical(value) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
