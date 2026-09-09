from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptanceArtifact,
    read_fl9_v2_cohort_acceptance,
)
from shreks_brain.research.counterfactual_source import (
    CounterfactualSourceProvenance,
    load_entry_counterfactual_provenance_batch_from_sqlite,
)
from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    ExecutionStatus,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    FastTrainingBundle,
    build_fast_training_bundle_from_components,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingEconomicsOverlayRow,
    FastTrainingEconomicsStatus,
    FastTrainingExecutionCostPolicy,
    build_entry_counterfactual_context_from_training_economics,
    read_fast_training_economics_overlay,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
    feature_logical_fingerprint_sha256,
    read_fast_training_feature_jsonl,
)
from shreks_brain.research.fast_training_targets import (
    FuturePathTrainingLabel,
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
    load_future_path_training_labels_from_sqlite,
)

from .models import FastFirstChampionV2Policy


def build_fast_first_champion_v2_bundle(
    *,
    cohort_path: str | Path,
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

    # This is deliberately first. No target/economics source is opened before
    # the physically sealed cohort authority is authenticated.
    cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    _validate_cohort(cohort, active_policy)

    features = read_fast_training_feature_jsonl(feature_jsonl_path)
    selected_features = _select_exact_features(
        cohort.accepted_decisions,
        features,
    )

    # Target/economics access begins only after the exact input population has
    # been authenticated and bound to feature identities.
    future_path = load_future_path_training_labels_from_sqlite(
        sqlite_path,
        future_path_label_version=future_path_label_version,
    )
    selected_labels = _select_exact_labels(
        cohort.accepted_decisions,
        future_path,
        horizon_ms=active_policy.horizon_ms,
        label_version=future_path_label_version,
    )

    overlay = read_fast_training_economics_overlay(
        training_economics_overlay_path
    )
    if overlay.manifest.feature_source_jsonl_sha256 != features.source_sha256:
        raise ValueError(
            "training economics overlay feature source does not match "
            "the authenticated feature JSONL"
        )
    if (
        overlay.manifest.future_path_label_version
        != future_path_label_version
    ):
        raise ValueError(
            "training economics overlay label version mismatch"
        )
    if Decimal(overlay.manifest.counterfactual_base_quantity) != Decimal(
        str(counterfactual_base_quantity)
    ):
        raise ValueError(
            "training economics overlay counterfactual quantity mismatch"
        )

    selected_overlay = _select_exact_overlay(
        cohort.accepted_decisions,
        overlay.rows,
        horizon_ms=active_policy.horizon_ms,
        label_version=future_path_label_version,
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
    provenance_by_key = (
        load_entry_counterfactual_provenance_batch_from_sqlite(
            sqlite_path,
            lookup_identities=lookup_identities,
        )
    )
    if set(provenance_by_key) != set(lookup_identities):
        raise ValueError(
            "canonical counterfactual provenance population does not "
            "match the accepted V2 cohort exactly"
        )

    projected_labels, outcome_sets = _project_selected_targets(
        labels=selected_labels.labels,
        overlay_rows=selected_overlay,
        provenance_by_key=provenance_by_key,
        overlay_manifest_fingerprint_sha256=(
            overlay.manifest.manifest_fingerprint_sha256
        ),
        execution_cost_policy=training_execution_cost_policy,
        counterfactual_base_quantity=float(counterfactual_base_quantity),
    )
    projected_future_path = FuturePathTrainingLabelDataset(
        labels=projected_labels,
        logical_fingerprint_sha256=(
            future_path_logical_fingerprint_sha256(projected_labels)
        ),
        label_version=future_path_label_version,
    )

    bundle = build_fast_training_bundle_from_components(
        features=selected_features,
        future_path_labels=projected_future_path,
        counterfactual_outcome_sets=outcome_sets,
    )
    _require_bundle_matches_cohort(
        cohort,
        bundle,
        active_policy,
    )
    return cohort, bundle


def _validate_cohort(
    cohort: Fl9V2CohortAcceptanceArtifact,
    policy: FastFirstChampionV2Policy,
) -> None:
    if type(cohort) is not Fl9V2CohortAcceptanceArtifact:
        raise ValueError(
            "cohort must be exact Fl9V2CohortAcceptanceArtifact"
        )
    manifest = cohort.manifest
    if manifest.policy_version != policy.cohort_policy_version:
        raise ValueError("V2 cohort policy version mismatch")
    if (
        manifest.artifact_fingerprint_sha256
        != policy.expected_cohort_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "physical V2 cohort artifact fingerprint mismatch"
        )
    if (
        manifest.accepted_identity_fingerprint_sha256
        != policy.expected_accepted_identity_fingerprint_sha256
    ):
        raise ValueError(
            "physical V2 accepted identity fingerprint mismatch"
        )
    if not manifest.structural_floor_passed:
        raise ValueError("physical V2 cohort structural floor did not pass")
    if manifest.horizon_ms != policy.horizon_ms:
        raise ValueError("physical V2 cohort horizon mismatch")
    if (
        manifest.selection_at_unix_ms != policy.selection_at_unix_ms
        or manifest.training_cut_unix_ms
        != policy.training_ended_at_unix_ms
        or manifest.validation_cut_unix_ms
        != policy.validation_ended_at_unix_ms
        or manifest.test_end_unix_ms != policy.test_ended_at_unix_ms
    ):
        raise ValueError("physical V2 cohort chronology mismatch")
    if (
        manifest.feature_identity_firewall_fingerprint_sha256
        != policy.feature_identity_firewall_fingerprint_sha256
    ):
        raise ValueError("physical V2 cohort feature firewall mismatch")
    if len(cohort.accepted_decisions) != manifest.eligible_row_count:
        raise ValueError("physical V2 accepted row count does not reconcile")


def _select_exact_features(
    accepted: tuple[Fl9V2AcceptedDecision, ...],
    features: FastTrainingFeatureDataset,
) -> FastTrainingFeatureDataset:
    if not isinstance(accepted, tuple) or not accepted:
        raise ValueError("accepted cohort decisions must be non-empty")
    if not all(type(value) is Fl9V2AcceptedDecision for value in accepted):
        raise ValueError(
            "accepted cohort decisions must contain exact values"
        )
    if type(features) is not FastTrainingFeatureDataset:
        raise ValueError(
            "features must be exact FastTrainingFeatureDataset"
        )

    source_by_identity: dict[
        tuple[object, ...], FastTrainingFeatureRecord
    ] = {}
    for record in features.records:
        identity = record.decision_identity
        if identity in source_by_identity:
            raise ValueError(
                "feature source contains duplicate decision identity"
            )
        source_by_identity[identity] = record

    accepted_identities = tuple(
        value.decision_identity for value in accepted
    )
    if len(set(accepted_identities)) != len(accepted_identities):
        raise ValueError("accepted cohort contains duplicate identity")

    missing = [
        identity
        for identity in accepted_identities
        if identity not in source_by_identity
    ]
    if missing:
        raise ValueError(
            "authenticated feature source is missing an accepted cohort identity"
        )

    records = tuple(
        source_by_identity[identity] for identity in accepted_identities
    )
    if tuple(record.decision_identity for record in records) != (
        accepted_identities
    ):
        raise ValueError(
            "selected feature identities do not equal accepted cohort identities"
        )
    return FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=(
            feature_logical_fingerprint_sha256(records)
        ),
        source_sha256=features.source_sha256,
    )


def _select_exact_labels(
    accepted: tuple[Fl9V2AcceptedDecision, ...],
    dataset: FuturePathTrainingLabelDataset,
    *,
    horizon_ms: int,
    label_version: int,
) -> FuturePathTrainingLabelDataset:
    if type(dataset) is not FuturePathTrainingLabelDataset:
        raise ValueError(
            "future path dataset must be exact "
            "FuturePathTrainingLabelDataset"
        )
    by_identity: dict[
        tuple[object, ...], FuturePathTrainingLabel
    ] = {}
    for label in dataset.labels:
        if (
            label.horizon_ms != horizon_ms
            or label.label_version != label_version
        ):
            continue
        identity = label.decision_identity
        if identity in by_identity:
            raise ValueError(
                "FL4 source contains duplicate accepted horizon identity"
            )
        by_identity[identity] = label

    identities = tuple(value.decision_identity for value in accepted)
    missing = [
        identity for identity in identities if identity not in by_identity
    ]
    if missing:
        raise ValueError(
            "FL4 source is missing an accepted cohort 30000 ms identity"
        )
    labels = tuple(by_identity[identity] for identity in identities)
    return FuturePathTrainingLabelDataset(
        labels=labels,
        logical_fingerprint_sha256=(
            future_path_logical_fingerprint_sha256(labels)
        ),
        label_version=label_version,
    )


def _select_exact_overlay(
    accepted: tuple[Fl9V2AcceptedDecision, ...],
    rows: tuple[FastTrainingEconomicsOverlayRow, ...],
    *,
    horizon_ms: int,
    label_version: int,
) -> tuple[FastTrainingEconomicsOverlayRow, ...]:
    by_identity: dict[
        tuple[object, ...], FastTrainingEconomicsOverlayRow
    ] = {}
    for row in rows:
        if (
            row.horizon_ms != horizon_ms
            or row.future_path_label_version != label_version
        ):
            continue
        identity = (
            row.decision_signature,
            row.decision_ordinal,
            row.decision_sequence,
            row.mint,
            row.quote_mint,
            row.venue,
            row.decision_observed_at_unix_ms,
        )
        if identity in by_identity:
            raise ValueError(
                "training economics overlay contains duplicate "
                "accepted decision identity"
            )
        by_identity[identity] = row

    identities = tuple(value.decision_identity for value in accepted)
    if any(identity not in by_identity for identity in identities):
        raise ValueError(
            "training economics overlay is missing an accepted cohort identity"
        )
    return tuple(by_identity[identity] for identity in identities)


def _project_selected_targets(
    *,
    labels: tuple[FuturePathTrainingLabel, ...],
    overlay_rows: tuple[FastTrainingEconomicsOverlayRow, ...],
    provenance_by_key: dict[
        tuple[str, int, int, int],
        CounterfactualSourceProvenance,
    ],
    overlay_manifest_fingerprint_sha256: str,
    execution_cost_policy: FastTrainingExecutionCostPolicy,
    counterfactual_base_quantity: float,
):
    if len(labels) != len(overlay_rows):
        raise ValueError(
            "selected FL4/economics row counts do not reconcile"
        )
    projected: list[FuturePathTrainingLabel] = []
    outcome_sets = []

    for label, row in zip(labels, overlay_rows, strict=True):
        _validate_overlay_matches_label(row, label)
        key = (
            label.decision_signature,
            label.decision_ordinal,
            label.horizon_ms,
            label.label_version,
        )
        provenance = provenance_by_key.get(key)
        if provenance is None:
            raise ValueError(
                "canonical counterfactual provenance is missing an "
                "accepted V2 identity"
            )
        _validate_provenance_matches_label(provenance, label)
        context = build_entry_counterfactual_context_from_training_economics(
            row,
            policy=execution_cost_policy,
            overlay_manifest_fingerprint_sha256=(
                overlay_manifest_fingerprint_sha256
            ),
            base_quantity=counterfactual_base_quantity,
            horizon_complete=label.completeness == "complete",
        )
        outcomes = label_entry_counterfactuals(context)
        outcome_sets.append(outcomes)

        buy_now = outcomes[0]
        if buy_now.action is not CounterfactualAction.BUY_NOW:
            raise ValueError(
                "counterfactual outcome order does not begin with BUY_NOW"
            )

        endpoint_cost = label.endpoint_cost_adjusted_return_bps
        if (
            endpoint_cost is None
            and buy_now.execution_status is ExecutionStatus.EXECUTABLE
        ):
            if buy_now.return_bps is None:
                raise ValueError(
                    "executable BUY_NOW outcome is missing return_bps"
                )
            endpoint_cost = buy_now.return_bps

        route_unavailable = label.route_unavailability_observed
        if route_unavailable is None:
            if (
                row.status
                is FastTrainingEconomicsStatus.EXIT_PROJECTION_UNAVAILABLE
            ):
                route_unavailable = True
            elif row.exit_projection is not None:
                route_unavailable = False

        projected.append(
            replace(
                label,
                endpoint_cost_adjusted_return_bps=endpoint_cost,
                route_unavailability_observed=route_unavailable,
            )
        )

    return tuple(projected), tuple(outcome_sets)


def _validate_provenance_matches_label(
    provenance: CounterfactualSourceProvenance,
    label: FuturePathTrainingLabel,
) -> None:
    if type(provenance) is not CounterfactualSourceProvenance:
        raise ValueError(
            "counterfactual provenance must be exact "
            "CounterfactualSourceProvenance"
        )
    if (
        provenance.decision_signature != label.decision_signature
        or provenance.decision_ordinal != label.decision_ordinal
        or provenance.decision_sequence != label.decision_sequence
        or provenance.decision_observed_at_unix_ms
        != label.decision_observed_at_unix_ms
        or provenance.mint != label.decision_mint
        or provenance.quote_mint != label.decision_quote_mint
        or provenance.venue != label.decision_venue
        or provenance.horizon_ms != label.horizon_ms
        or provenance.future_path_label_version != label.label_version
        or provenance.completeness != label.completeness
        or provenance.endpoint_signature != label.endpoint_signature
        or provenance.endpoint_ordinal != label.endpoint_ordinal
        or provenance.endpoint_observed_at_unix_ms
        != label.endpoint_observed_at_unix_ms
    ):
        raise ValueError(
            "canonical counterfactual provenance does not match "
            "accepted FL4 label"
        )


def _validate_overlay_matches_label(
    row: FastTrainingEconomicsOverlayRow,
    label: FuturePathTrainingLabel,
) -> None:
    if (
        row.decision_signature != label.decision_signature
        or row.decision_ordinal != label.decision_ordinal
        or row.decision_sequence != label.decision_sequence
        or row.decision_observed_at_unix_ms
        != label.decision_observed_at_unix_ms
        or row.mint != label.decision_mint
        or row.quote_mint != label.decision_quote_mint
        or row.venue != label.decision_venue
        or row.horizon_ms != label.horizon_ms
        or row.future_path_label_version != label.label_version
        or row.endpoint_signature != label.endpoint_signature
        or row.endpoint_ordinal != label.endpoint_ordinal
        or row.endpoint_observed_at_unix_ms
        != label.endpoint_observed_at_unix_ms
    ):
        raise ValueError(
            "training economics overlay provenance does not match "
            "accepted FL4 label"
        )


def _require_bundle_matches_cohort(
    cohort: Fl9V2CohortAcceptanceArtifact,
    bundle: FastTrainingBundle,
    policy: FastFirstChampionV2Policy,
) -> None:
    identities = tuple(
        record.decision_identity for record in bundle.features.records
    )
    accepted = tuple(
        value.decision_identity for value in cohort.accepted_decisions
    )
    if identities != accepted:
        raise ValueError(
            "V2 training bundle feature identities do not equal "
            "the accepted cohort identities"
        )
    if len(identities) != cohort.manifest.eligible_row_count:
        raise ValueError(
            "V2 training bundle accepted identity count does not reconcile"
        )
    if (
        cohort.manifest.accepted_identity_fingerprint_sha256
        != policy.expected_accepted_identity_fingerprint_sha256
    ):
        raise ValueError(
            "V2 training bundle is not bound to the frozen identity fingerprint"
        )
