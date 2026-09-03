from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import warnings

from shreks_brain.research.fast_training_bundle import FastTrainingBundle

from .features import (
    FAST_FORECAST_FEATURE_SCHEMA_VERSION,
    FastForecastFeatureTransform,
    apply_feature_transforms,
    extract_fast_forecast_features,
    fit_feature_transforms,
)
from .models import (
    FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
    FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
    FastForecastBaselineArtifact,
    FastForecastModelFamily,
    FastForecastTargetKind,
    FastForecastTrainingRequest,
    fast_forecast_artifact_fingerprint_sha256,
)


@dataclass(frozen=True, slots=True)
class _PreparedFastForecastTrainingData:
    raw_feature_rows: tuple[tuple[float | None, ...], ...]
    targets: tuple[float, ...]
    decision_identities: tuple[tuple[object, ...], ...]
    target_unavailable_row_count: int
    min_training_decision_observed_at_unix_ms: int
    max_training_decision_observed_at_unix_ms: int
    training_data_fingerprint_sha256: str


def train_fast_forecast_baseline(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
) -> FastForecastBaselineArtifact:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be an exact FastTrainingBundle")
    if type(request) is not FastForecastTrainingRequest:
        raise ValueError("request must be an exact FastForecastTrainingRequest")

    prepared = _prepare_fast_forecast_training_data(bundle, request)
    targets = prepared.targets
    training_row_count = len(targets)
    positive_row_count: int | None = None
    negative_row_count: int | None = None
    if request.target.kind is FastForecastTargetKind.BINARY:
        binary_targets = tuple(int(value) for value in targets)
        if any(float(value) not in {0.0, 1.0} for value in targets):
            raise ValueError("binary forecast targets must be exactly false/true")
        positive_row_count = sum(binary_targets)
        negative_row_count = training_row_count - positive_row_count

    transforms: tuple[FastForecastFeatureTransform, ...] = ()
    coefficients: tuple[float, ...] = ()
    intercept: float | None = None
    constant_prediction: float | None = None

    if request.model_family is FastForecastModelFamily.MEAN_REGRESSOR:
        constant_prediction = float(math.fsum(targets) / training_row_count)
    elif request.model_family is FastForecastModelFamily.PRIOR_CLASSIFIER:
        assert positive_row_count is not None
        constant_prediction = float(positive_row_count / training_row_count)
    elif request.model_family is FastForecastModelFamily.RIDGE_REGRESSION:
        if training_row_count < 2:
            raise ValueError("ridge training requires at least two target-eligible rows")
        transforms = fit_feature_transforms(prepared.raw_feature_rows)
        matrix = tuple(
            apply_feature_transforms(row, transforms)
            for row in prepared.raw_feature_rows
        )
        coefficients, intercept = _fit_ridge(matrix, targets, request)
    elif request.model_family is FastForecastModelFamily.LOGISTIC_REGRESSION:
        if training_row_count < 2:
            raise ValueError("logistic training requires at least two target-eligible rows")
        if positive_row_count == 0 or negative_row_count == 0:
            raise ValueError("logistic training requires both binary target classes")
        transforms = fit_feature_transforms(prepared.raw_feature_rows)
        matrix = tuple(
            apply_feature_transforms(row, transforms)
            for row in prepared.raw_feature_rows
        )
        coefficients, intercept = _fit_logistic(
            matrix, tuple(int(value) for value in targets), request
        )
    else:  # pragma: no cover - exact enum validation keeps this unreachable.
        raise ValueError("unsupported Fast Lane forecast model family")

    provisional = FastForecastBaselineArtifact(
        schema_name=FAST_FORECAST_ARTIFACT_SCHEMA_NAME,
        schema_version=FAST_FORECAST_ARTIFACT_SCHEMA_VERSION,
        model_version=request.model_version,
        model_family=request.model_family,
        target=request.target,
        target_kind=request.target.kind,
        horizon_ms=request.horizon_ms,
        feature_schema_version=FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        training_policy_version=request.training_policy.version,
        training_bundle_fingerprint_sha256=bundle.manifest.bundle_fingerprint_sha256,
        future_path_label_version=bundle.manifest.future_path_label_version,
        training_row_count=training_row_count,
        target_unavailable_row_count=prepared.target_unavailable_row_count,
        positive_row_count=positive_row_count,
        negative_row_count=negative_row_count,
        min_training_decision_observed_at_unix_ms=prepared.min_training_decision_observed_at_unix_ms,
        max_training_decision_observed_at_unix_ms=prepared.max_training_decision_observed_at_unix_ms,
        training_data_fingerprint_sha256=prepared.training_data_fingerprint_sha256,
        feature_transforms=transforms,
        coefficients=coefficients,
        intercept=intercept,
        constant_prediction=constant_prediction,
        artifact_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        artifact_fingerprint_sha256=fast_forecast_artifact_fingerprint_sha256(
            provisional
        ),
    )


def _prepare_fast_forecast_training_data(
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
) -> _PreparedFastForecastTrainingData:
    feature_by_identity = {
        record.decision_identity: record for record in bundle.features.records
    }
    if len(feature_by_identity) != len(bundle.features.records):
        raise ValueError("FL8.1 feature bundle contains duplicate decision identities")

    selected = tuple(
        label
        for label in bundle.future_path_labels.labels
        if label.horizon_ms == request.horizon_ms
    )
    if not selected:
        raise ValueError("requested forecast horizon has no FL4 training label rows")

    raw_rows: list[tuple[float | None, ...]] = []
    targets: list[float] = []
    identities: list[tuple[object, ...]] = []
    timestamps: list[int] = []
    unavailable = 0
    seen_identities: set[tuple[object, ...]] = set()

    for label in selected:
        identity = label.decision_identity
        if identity in seen_identities:
            raise ValueError("requested FL4 horizon contains duplicate decision identities")
        seen_identities.add(identity)
        record = feature_by_identity.get(identity)
        if record is None:
            raise ValueError("FL4 training label does not map to an exact FL8.1 feature decision")

        target_value = getattr(label, request.target.value)
        if label.completeness != "complete" or target_value is None:
            unavailable += 1
            continue

        target = _target_scalar(target_value, request.target.kind)
        raw = extract_fast_forecast_features(record)
        raw_rows.append(raw)
        targets.append(target)
        identities.append(identity)
        timestamps.append(record.decision_observed_at_unix_ms)

    if not targets:
        raise ValueError("requested forecast target has no complete target-eligible rows")

    fingerprint = _training_data_fingerprint(
        bundle=bundle,
        request=request,
        decision_identities=tuple(identities),
        raw_feature_rows=tuple(raw_rows),
        targets=tuple(targets),
    )
    return _PreparedFastForecastTrainingData(
        raw_feature_rows=tuple(raw_rows),
        targets=tuple(targets),
        decision_identities=tuple(identities),
        target_unavailable_row_count=unavailable,
        min_training_decision_observed_at_unix_ms=min(timestamps),
        max_training_decision_observed_at_unix_ms=max(timestamps),
        training_data_fingerprint_sha256=fingerprint,
    )


def _fit_ridge(
    matrix: tuple[tuple[float, ...], ...],
    targets: tuple[float, ...],
    request: FastForecastTrainingRequest,
) -> tuple[tuple[float, ...], float]:
    try:
        from sklearn.linear_model import Ridge
    except ImportError as exc:  # pragma: no cover - exercised by isolated import tests.
        raise RuntimeError(
            "scikit-learn is required for FL8.2 ridge training; install the learning extra"
        ) from exc

    alpha = request.training_policy.ridge_alpha
    if alpha is None:
        raise ValueError("ridge training policy is missing ridge_alpha")
    estimator = Ridge(alpha=alpha, fit_intercept=True)
    estimator.fit(matrix, targets)
    raw_coefficients = estimator.coef_.tolist()
    if not isinstance(raw_coefficients, list) or len(raw_coefficients) != len(matrix[0]):
        raise ValueError("fitted ridge regression has unexpected coefficient dimensions")
    coefficients = tuple(_finite_fit_value("ridge coefficient", value) for value in raw_coefficients)
    intercept = _finite_fit_value("ridge intercept", estimator.intercept_)
    return coefficients, intercept


def _fit_logistic(
    matrix: tuple[tuple[float, ...], ...],
    targets: tuple[int, ...],
    request: FastForecastTrainingRequest,
) -> tuple[tuple[float, ...], float]:
    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:  # pragma: no cover - exercised by isolated import tests.
        raise RuntimeError(
            "scikit-learn is required for FL8.2 logistic training; install the learning extra"
        ) from exc

    policy = request.training_policy
    if (
        policy.logistic_regularization_c is None
        or policy.logistic_max_iterations is None
        or policy.logistic_tolerance is None
        or policy.logistic_balanced_class_weight is None
    ):
        raise ValueError("logistic training policy is incomplete")
    estimator = LogisticRegression(
        solver="lbfgs",
        C=policy.logistic_regularization_c,
        max_iter=policy.logistic_max_iterations,
        tol=policy.logistic_tolerance,
        class_weight="balanced" if policy.logistic_balanced_class_weight else None,
        fit_intercept=True,
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            estimator.fit(matrix, targets)
    except ConvergenceWarning as exc:
        raise ValueError("logistic regression did not converge") from exc

    classes = tuple(int(value) for value in estimator.classes_.tolist())
    if classes != (0, 1):
        raise ValueError("fitted logistic regression must expose classes (0, 1)")
    raw_rows = estimator.coef_.tolist()
    raw_intercepts = estimator.intercept_.tolist()
    if (
        not isinstance(raw_rows, list)
        or len(raw_rows) != 1
        or not isinstance(raw_rows[0], list)
        or len(raw_rows[0]) != len(matrix[0])
        or not isinstance(raw_intercepts, list)
        or len(raw_intercepts) != 1
    ):
        raise ValueError("fitted logistic regression has unexpected coefficient dimensions")
    coefficients = tuple(
        _finite_fit_value("logistic coefficient", value) for value in raw_rows[0]
    )
    intercept = _finite_fit_value("logistic intercept", raw_intercepts[0])
    return coefficients, intercept


def _target_scalar(value: object, kind: FastForecastTargetKind) -> float:
    if kind is FastForecastTargetKind.BINARY:
        if type(value) is not bool:
            raise ValueError("binary FL4 forecast target must be a boolean")
        return 1.0 if value else 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("continuous FL4 forecast target must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("continuous FL4 forecast target must be finite")
    return result


def _training_data_fingerprint(
    *,
    bundle: FastTrainingBundle,
    request: FastForecastTrainingRequest,
    decision_identities: tuple[tuple[object, ...], ...],
    raw_feature_rows: tuple[tuple[float | None, ...], ...],
    targets: tuple[float, ...],
) -> str:
    policy = request.training_policy
    rows = [
        {
            "decision_identity": list(identity),
            "features": [_canonical_scalar(value) for value in feature_row],
            "target": _canonical_scalar(target),
        }
        for identity, feature_row, target in zip(
            decision_identities, raw_feature_rows, targets, strict=True
        )
    ]
    payload = {
        "feature_schema_version": FAST_FORECAST_FEATURE_SCHEMA_VERSION,
        "training_bundle_fingerprint_sha256": bundle.manifest.bundle_fingerprint_sha256,
        "future_path_label_version": bundle.manifest.future_path_label_version,
        "model_family": request.model_family.value,
        "target": request.target.value,
        "target_kind": request.target.kind.value,
        "horizon_ms": request.horizon_ms,
        "training_policy": {
            "version": policy.version,
            "ridge_alpha": _canonical_scalar(policy.ridge_alpha),
            "logistic_regularization_c": _canonical_scalar(
                policy.logistic_regularization_c
            ),
            "logistic_max_iterations": policy.logistic_max_iterations,
            "logistic_tolerance": _canonical_scalar(policy.logistic_tolerance),
            "logistic_balanced_class_weight": policy.logistic_balanced_class_weight,
        },
        "rows": rows,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_scalar(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("training fingerprint cannot contain non-finite floats")
        return {"float_hex": value.hex()}
    raise TypeError(f"unsupported training fingerprint scalar: {type(value).__name__}")


def _finite_fit_value(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # NumPy scalar values support float conversion without becoming part of the artifact.
        try:
            result = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be finite") from exc
    else:
        result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result
