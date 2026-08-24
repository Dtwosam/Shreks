from __future__ import annotations

from pathlib import Path

from .dataset import (
    RESEARCH_FEATURE_COLUMNS,
    RESEARCH_LABEL_COLUMNS,
    build_research_dataset,
    logical_dataset_fingerprint_sha256,
)
from .models import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchDatasetManifest,
    ResearchSnapshotInputs,
)


_STRING_COLUMNS = {
    "dataset_schema_version",
    "candidate_mint",
    "market_feature_schema_version",
    "wallet_feature_schema_version",
    "safety_policy_version",
    "wallet_feature_policy_version",
    "wallet_profile_policy_version",
    "wallet_profile_context_version",
    "wallet_relationship_policy_version",
    "regime_policy_version",
    "score_policy_version",
    "decision_policy_version",
    "setup_name",
    "setup_policy_version",
    "wallet_strength_assessments_json",
    "regime",
    "regime_base",
    "safety_decision",
    "setup_state",
    "market_regime",
    "decision_action",
}
for _horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
    _STRING_COLUMNS.add(f"label_{_horizon}s_status")
    _STRING_COLUMNS.add(f"label_{_horizon}s_exitability")

_BOOL_COLUMNS = {
    "market_safety_liquidity_weak",
    "market_safety_holder_concentration_elevated",
    "market_safety_creator_concentration_elevated",
    "market_safety_exit_price_impact_elevated",
    "wallet_strong_entry_all_pairs_independent_under_evidence",
    "regime_performance_applied",
}
for _horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
    _BOOL_COLUMNS.add(f"label_{_horizon}s_rug_or_dead_pool")

_INT_COLUMNS = {
    "as_of_unix_ms",
    "market_source_observed_at_unix_ms",
    "market_source_age_ms",
    "market_tx_count_m5",
    "market_tx_count_h1",
    "market_safety_soft_finding_count",
    "wallet_count",
    "wallet_recent_entry_wallet_count",
    "wallet_recent_exit_wallet_count",
    "wallet_strong_wallet_count",
    "wallet_unknown_strength_wallet_count",
    "wallet_strong_entry_wallet_count",
    "wallet_strong_exit_wallet_count",
    "wallet_entry_quality_profile_sample_count",
    "wallet_independently_strong_entry_wallet_count",
    "wallet_strong_entry_linked_pair_count",
    "wallet_strong_entry_conflicting_pair_count",
    "wallet_strong_entry_unknown_pair_count",
    "wallet_strong_entry_coordination_cluster_count",
    "wallet_strong_entry_max_independent_group_count_upper_bound",
    "wallet_creator_deployer_action_observation_count",
    "regime_source_observed_at_unix_ms",
    "regime_window_started_at_unix_ms",
    "regime_source_age_ms",
    "regime_candidate_count",
    "regime_performance_sample_count",
}
for _horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS:
    for _suffix in (
        "baseline_observed_at_unix_ms",
        "due_at_unix_ms",
        "checkpoint_observed_at_unix_ms",
        "completed_at_unix_ms",
        "buys_m5_change",
        "sells_m5_change",
    ):
        _INT_COLUMNS.add(f"label_{_horizon}s_{_suffix}")

_LIST_STRING_COLUMNS = {
    "market_missing_features",
    "wallet_missing_features",
    "regime_reason_codes",
    "score_reason_codes",
    "decision_reason_codes",
}

_ALL_COLUMNS = RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS


def _arrow_schema(pa, metadata: dict[bytes, bytes]):
    fields = []
    for column in _ALL_COLUMNS:
        if column in _STRING_COLUMNS:
            value_type = pa.string()
        elif column in _BOOL_COLUMNS:
            value_type = pa.bool_()
        elif column in _INT_COLUMNS:
            value_type = pa.int64()
        elif column in _LIST_STRING_COLUMNS:
            value_type = pa.list_(pa.string())
        else:
            value_type = pa.float64()
        fields.append(pa.field(column, value_type, nullable=True))
    return pa.schema(fields, metadata=metadata)


def write_research_parquet(
    snapshots: tuple[ResearchSnapshotInputs, ...],
    path: str | Path,
) -> ResearchDatasetManifest:
    rows = build_research_dataset(snapshots)

    destination = Path(path)
    if destination.suffix != ".parquet":
        raise ValueError("research dataset path must end with .parquet")

    digest = logical_dataset_fingerprint_sha256(rows)
    manifest = ResearchDatasetManifest(
        schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
        row_count=len(rows),
        min_as_of_unix_ms=int(rows[0]["as_of_unix_ms"]),
        max_as_of_unix_ms=int(rows[-1]["as_of_unix_ms"]),
        dataset_fingerprint_sha256=digest,
    )

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires the shreks-brain[research] extra"
        ) from exc

    metadata = {
        b"shreks_dataset_schema_version": RESEARCH_DATASET_SCHEMA_VERSION.encode(),
        b"shreks_market_feature_schema_version": str(
            rows[0]["market_feature_schema_version"]
        ).encode(),
        b"shreks_wallet_feature_schema_version": str(
            rows[0]["wallet_feature_schema_version"]
        ).encode(),
        b"shreks_label_horizons_seconds": ",".join(
            str(value) for value in RESEARCH_OUTCOME_HORIZONS_SECONDS
        ).encode(),
        b"shreks_row_count": str(manifest.row_count).encode(),
        b"shreks_logical_sha256": digest.encode(),
    }
    schema = _arrow_schema(pa, metadata)
    table = pa.Table.from_pylist([dict(row) for row in rows], schema=schema)

    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )
    return manifest
