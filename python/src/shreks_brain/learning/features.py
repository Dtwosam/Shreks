from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import statistics

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
)

from .models import (
    MODEL_TRAINING_SCHEMA_VERSION,
    FeatureTransform,
    ModelTrainingRequest,
)


TRAINABLE_RESEARCH_FEATURE_COLUMNS = (
    "market_source_age_ms",
    "market_token_age_seconds",
    "market_price_usd",
    "market_liquidity_usd",
    "market_liquidity_change_5m_pct",
    "market_exit_price_impact_pct",
    "market_volume_m5_usd",
    "market_volume_h1_usd",
    "market_volume_velocity_ratio",
    "market_tx_count_m5",
    "market_tx_count_h1",
    "market_buy_fraction_m5",
    "market_buy_fraction_h1",
    "market_buy_sell_ratio_m5",
    "market_buy_sell_ratio_h1",
    "market_buy_pressure_acceleration",
    "market_return_1m_pct",
    "market_return_5m_pct",
    "market_return_15m_pct",
    "market_momentum_acceleration_1m_vs_5m",
    "market_distance_from_local_high_pct",
    "market_range_position_pct",
    "market_safety_soft_finding_count",
    "market_safety_liquidity_weak",
    "market_safety_holder_concentration_elevated",
    "market_safety_creator_concentration_elevated",
    "market_safety_exit_price_impact_elevated",
    "wallet_count",
    "wallet_recent_entry_wallet_count",
    "wallet_recent_exit_wallet_count",
    "wallet_strong_wallet_count",
    "wallet_unknown_strength_wallet_count",
    "wallet_strong_entry_wallet_count",
    "wallet_strong_exit_wallet_count",
    "wallet_confidence_weighted_strong_entry_count",
    "wallet_confidence_weighted_strong_exit_count",
    "wallet_entry_quality_profile_sample_count",
    "wallet_confidence_weighted_entry_median_return_pct",
    "wallet_confidence_weighted_entry_win_rate",
    "wallet_independently_strong_entry_wallet_count",
    "wallet_strong_entry_all_pairs_independent_under_evidence",
    "wallet_strong_entry_linked_pair_count",
    "wallet_strong_entry_conflicting_pair_count",
    "wallet_strong_entry_unknown_pair_count",
    "wallet_strong_entry_coordination_cluster_count",
    "wallet_strong_entry_max_independent_group_count_upper_bound",
    "wallet_creator_deployer_action_observation_count",
    "regime_source_age_ms",
    "regime_window_seconds",
    "regime_candidate_count",
    "regime_candidate_rate_per_hour",
    "regime_executable_fraction",
    "regime_median_liquidity_usd",
    "regime_median_volume_m5_usd",
    "regime_performance_sample_count",
    "regime_performance_net_expectancy_after_costs_pct",
    "regime_performance_applied",
    "score_safety_quality",
    "score_money_flow",
    "score_setup_quality",
    "score_liquidity_executability",
    "total_score",
)

_D6_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
_D6_COLUMN_SET = frozenset(_D6_COLUMNS)
_TRAINABLE_SET = frozenset(TRAINABLE_RESEARCH_FEATURE_COLUMNS)


@dataclass(frozen=True, slots=True)
class _PreparedTrainingData:
    feature_matrix: tuple[tuple[float, ...], ...]
    targets: tuple[int, ...]
    feature_transforms: tuple[FeatureTransform, ...]
    ordered_identities: tuple[tuple[str, int], ...]
    target_unavailable_row_count: int
    min_training_as_of_unix_ms: int
    max_training_as_of_unix_ms: int
    training_fingerprint_sha256: str


def _prepare_training_data(
    rows: tuple[dict[str, object], ...],
    request: ModelTrainingRequest,
) -> _PreparedTrainingData:
    if not isinstance(rows, tuple) or not rows:
        raise ValueError("rows must be a non-empty tuple")
    if type(request) is not ModelTrainingRequest:
        raise ValueError("request must be an exact ModelTrainingRequest")

    for feature_name in request.feature_columns:
        if feature_name not in _TRAINABLE_SET:
            raise ValueError(
                f"feature {feature_name!r} is not an E3 trainable decision-time feature"
            )

    identities: set[tuple[str, int]] = set()
    eligible: list[tuple[int, str, dict[str, object], int]] = []
    target_unavailable = 0
    target_prefix = f"label_{request.target.horizon_seconds}s_"
    target_status_column = target_prefix + "status"
    target_return_column = target_prefix + "return_pct"
    target_baseline_column = target_prefix + "baseline_observed_at_unix_ms"
    target_due_column = target_prefix + "due_at_unix_ms"

    for row in rows:
        if type(row) is not dict:
            raise ValueError("rows must contain exact D6 logical row mappings")
        if len(row) != len(_D6_COLUMNS) or frozenset(row) != _D6_COLUMN_SET:
            raise ValueError("each D6 row must expose exactly the sealed physical column set")
        if row["dataset_schema_version"] != RESEARCH_DATASET_SCHEMA_VERSION:
            raise ValueError("row dataset schema must equal the sealed D6 schema")

        mint = row["candidate_mint"]
        as_of = row["as_of_unix_ms"]
        if not isinstance(mint, str) or not mint.strip():
            raise ValueError("candidate_mint must be a non-empty string")
        if isinstance(as_of, bool) or not isinstance(as_of, int) or as_of < 0:
            raise ValueError("as_of_unix_ms must be a non-negative integer")

        identity = (mint, as_of)
        if identity in identities:
            raise ValueError("duplicate D6 training row identity")
        identities.add(identity)

        baseline = row[target_baseline_column]
        due = row[target_due_column]
        if baseline != as_of:
            raise ValueError("target baseline must equal row as_of_unix_ms")
        if due != as_of + request.target.horizon_seconds * 1_000:
            raise ValueError("target due timestamp must match the selected horizon")

        status = row[target_status_column]
        if status not in ("PENDING", "COMPLETED"):
            raise ValueError("target label status must be PENDING or COMPLETED")
        target_return = row[target_return_column]
        if status != "COMPLETED" or target_return is None:
            target_unavailable += 1
            continue
        target_value = _finite_number(target_return, target_return_column)
        target = int(target_value >= float(request.target.minimum_return_pct))
        eligible.append((as_of, mint, row, target))

    eligible.sort(key=lambda item: (item[0], item[1]))
    if not eligible:
        raise ValueError("no target-eligible training rows are available")

    raw_columns: list[list[float | None]] = [
        [] for _ in request.feature_columns
    ]
    for _, _, row, _ in eligible:
        for index, feature_name in enumerate(request.feature_columns):
            value = row[feature_name]
            if value is None:
                raw_columns[index].append(None)
            else:
                raw_columns[index].append(_finite_scalar(value, feature_name))

    transforms: list[FeatureTransform] = []
    transformed_columns: list[list[float]] = []
    for feature_name, raw_values in zip(
        request.feature_columns, raw_columns, strict=True
    ):
        observed = [value for value in raw_values if value is not None]
        if not observed:
            raise ValueError(
                f"{feature_name} must have at least one observed training value"
            )
        median = float(statistics.median(observed))
        imputed = [
            median if value is None else float(value)
            for value in raw_values
        ]
        mean = float(statistics.fmean(imputed))
        variance = float(
            statistics.fmean((value - mean) ** 2 for value in imputed)
        )
        scale = math.sqrt(variance)
        if scale == 0.0:
            scale = 1.0
        transform = FeatureTransform(
            feature_name=feature_name,
            imputation_median=median,
            mean=mean,
            scale=scale,
        )
        transforms.append(transform)
        transformed_columns.append(
            [(value - mean) / scale for value in imputed]
        )

    feature_matrix = tuple(
        tuple(
            transformed_columns[column_index][row_index]
            for column_index in range(len(request.feature_columns))
        )
        for row_index in range(len(eligible))
    )
    targets = tuple(item[3] for item in eligible)
    ordered_identities = tuple((item[1], item[0]) for item in eligible)
    fingerprint = _training_fingerprint(eligible, request)

    return _PreparedTrainingData(
        feature_matrix=feature_matrix,
        targets=targets,
        feature_transforms=tuple(transforms),
        ordered_identities=ordered_identities,
        target_unavailable_row_count=target_unavailable,
        min_training_as_of_unix_ms=eligible[0][0],
        max_training_as_of_unix_ms=eligible[-1][0],
        training_fingerprint_sha256=fingerprint,
    )


def _finite_scalar(value: object, name: str) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric, boolean, or None")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _training_fingerprint(
    eligible: list[tuple[int, str, dict[str, object], int]],
    request: ModelTrainingRequest,
) -> str:
    rows_payload = []
    for as_of, mint, row, target in eligible:
        rows_payload.append(
            {
                "candidate_mint": mint,
                "as_of_unix_ms": as_of,
                "features": [
                    _canonical_scalar(row[feature_name])
                    for feature_name in request.feature_columns
                ],
                "target": target,
            }
        )
    policy = request.training_policy
    payload = {
        "schema_version": MODEL_TRAINING_SCHEMA_VERSION,
        "research_dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION,
        "model_version": request.model_version,
        "model_family": request.model_family.value,
        "feature_columns": list(request.feature_columns),
        "target": {
            "horizon_seconds": request.target.horizon_seconds,
            "minimum_return_pct": _canonical_scalar(
                request.target.minimum_return_pct
            ),
        },
        "training_policy": {
            "version": policy.version,
            "regularization_c": _canonical_scalar(policy.regularization_c),
            "max_iterations": policy.max_iterations,
            "tolerance": _canonical_scalar(policy.tolerance),
            "class_weight_mode": policy.class_weight_mode.value,
        },
        "rows": rows_payload,
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
    raise TypeError(
        f"unsupported E3 training fingerprint scalar: {type(value).__name__}"
    )
