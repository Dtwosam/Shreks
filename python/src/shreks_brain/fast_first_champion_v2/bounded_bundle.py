from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from shreks_brain.fast_proof_workspace import FastProofWorkspaceManifest
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptanceArtifact,
)
from shreks_brain.research.counterfactual_source import (
    load_entry_counterfactual_provenance_batch_from_sqlite,
)
from shreks_brain.research.fast_training_bundle import (
    FastTrainingBundle,
    build_fast_training_bundle_from_components,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
)
from shreks_brain.research.fast_training_targets import (
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
    load_future_path_training_labels_for_identities_from_sqlite,
)

from .bounded_inputs import (
    read_fast_training_economics_overlay_for_identities,
    read_fast_training_feature_jsonl_for_identities,
)
from .bundle import (
    _project_selected_targets,
    _require_bundle_matches_cohort,
    _select_exact_labels,
    _validate_cohort,
)
from .models import FastFirstChampionV2Policy


def build_fast_first_champion_v2_bundle(
    *,
    cohort: Fl9V2CohortAcceptanceArtifact,
    proof_manifest: FastProofWorkspaceManifest,
    feature_jsonl_path: str | Path,
    sqlite_path: str | Path,
    future_path_label_version: int,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    counterfactual_base_quantity: float,
    policy: FastFirstChampionV2Policy | None = None,
) -> tuple[Fl9V2CohortAcceptanceArtifact, FastTrainingBundle]:
    active_policy = policy or FastFirstChampionV2Policy()
    if type(active_policy) is not FastFirstChampionV2Policy:
        raise ValueError("policy must be exact FastFirstChampionV2Policy")
    if type(cohort) is not Fl9V2CohortAcceptanceArtifact:
        raise ValueError("cohort must be exact Fl9V2CohortAcceptanceArtifact")
    if type(proof_manifest) is not FastProofWorkspaceManifest:
        raise ValueError("proof_manifest must be exact FastProofWorkspaceManifest")
    if (
        isinstance(future_path_label_version, bool)
        or not isinstance(future_path_label_version, int)
        or future_path_label_version <= 0
    ):
        raise ValueError("future_path_label_version must be positive")
    if type(training_execution_cost_policy) is not FastTrainingExecutionCostPolicy:
        raise ValueError(
            "training_execution_cost_policy must be exact "
            "FastTrainingExecutionCostPolicy"
        )
    if (
        isinstance(counterfactual_base_quantity, bool)
        or not isinstance(counterfactual_base_quantity, (int, float))
        or counterfactual_base_quantity <= 0
    ):
        raise ValueError("counterfactual_base_quantity must be positive")

    _validate_cohort(cohort, active_policy)
    identities = tuple(
        value.decision_identity for value in cohort.accepted_decisions
    )

    features = read_fast_training_feature_jsonl_for_identities(
        feature_jsonl_path,
        decision_identities=identities,
        proof_manifest=proof_manifest,
    )

    future_path = load_future_path_training_labels_for_identities_from_sqlite(
        sqlite_path,
        future_path_label_version=future_path_label_version,
        horizon_ms=active_policy.horizon_ms,
        decision_identities=identities,
    )
    selected_labels = _select_exact_labels(
        cohort.accepted_decisions,
        future_path,
        horizon_ms=active_policy.horizon_ms,
        label_version=future_path_label_version,
    )
    del future_path

    overlay = read_fast_training_economics_overlay_for_identities(
        training_economics_overlay_path,
        horizon_ms=active_policy.horizon_ms,
        label_version=future_path_label_version,
        decision_identities=identities,
    )
    if overlay.manifest.feature_source_jsonl_sha256 != features.source_sha256:
        raise ValueError(
            "training economics overlay feature source does not match "
            "the authenticated feature JSONL"
        )
    if overlay.manifest.future_path_label_version != future_path_label_version:
        raise ValueError("training economics overlay label version mismatch")
    if Decimal(overlay.manifest.counterfactual_base_quantity) != Decimal(
        str(counterfactual_base_quantity)
    ):
        raise ValueError(
            "training economics overlay counterfactual quantity mismatch"
        )

    lookup_identities = tuple(
        (
            label.decision_signature,
            label.decision_ordinal,
            label.horizon_ms,
            label.label_version,
        )
        for label in selected_labels.labels
    )
    provenance_by_key = load_entry_counterfactual_provenance_batch_from_sqlite(
        sqlite_path,
        lookup_identities=lookup_identities,
    )
    if set(provenance_by_key) != set(lookup_identities):
        raise ValueError(
            "canonical counterfactual provenance population does not "
            "match the accepted V2 cohort exactly"
        )

    projected_labels, outcome_sets = _project_selected_targets(
        labels=selected_labels.labels,
        overlay_rows=overlay.rows,
        provenance_by_key=provenance_by_key,
        overlay_manifest_fingerprint_sha256=(
            overlay.manifest.manifest_fingerprint_sha256
        ),
        execution_cost_policy=training_execution_cost_policy,
        counterfactual_base_quantity=float(counterfactual_base_quantity),
    )
    del provenance_by_key
    del overlay

    projected_future_path = FuturePathTrainingLabelDataset(
        labels=projected_labels,
        logical_fingerprint_sha256=(
            future_path_logical_fingerprint_sha256(projected_labels)
        ),
        label_version=future_path_label_version,
    )
    bundle = build_fast_training_bundle_from_components(
        features=features,
        future_path_labels=projected_future_path,
        counterfactual_outcome_sets=outcome_sets,
    )
    _require_bundle_matches_cohort(cohort, bundle, active_policy)
    return cohort, bundle
