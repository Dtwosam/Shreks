from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

from shreks_brain.research.counterfactual_source import (
    CounterfactualSourceProvenance,
    _load_provenance,
    _open_read_only,
)
from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    ExecutionStatus,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingEconomicsOverlayRow,
    FastTrainingEconomicsStatus,
    FastTrainingExecutionCostPolicy,
    build_entry_counterfactual_context_from_training_economics,
)
from shreks_brain.research.fast_training_targets import FuturePathTrainingLabel

from .bundle import (
    _validate_overlay_matches_label,
    _validate_provenance_matches_label,
)


def iter_entry_counterfactual_provenance_for_labels(
    db_path: str | Path,
    *,
    labels: tuple[FuturePathTrainingLabel, ...],
) -> Iterator[CounterfactualSourceProvenance]:
    """Yield canonical FL4 provenance in label order without a cohort-sized dict."""

    if not isinstance(labels, tuple) or not labels:
        raise ValueError("labels must be a non-empty tuple")
    if not all(type(label) is FuturePathTrainingLabel for label in labels):
        raise ValueError("labels must contain exact FuturePathTrainingLabel values")

    source = Path(db_path)
    connection = _open_read_only(source)
    try:
        for label in labels:
            yield _load_provenance(
                source,
                decision_signature=label.decision_signature,
                decision_ordinal=label.decision_ordinal,
                horizon_ms=label.horizon_ms,
                label_version=label.label_version,
                connection=connection,
            )
    finally:
        connection.close()


def project_selected_targets_with_streamed_provenance(
    *,
    labels: tuple[FuturePathTrainingLabel, ...],
    overlay_rows: tuple[FastTrainingEconomicsOverlayRow, ...],
    provenance_rows: Iterable[CounterfactualSourceProvenance],
    overlay_manifest_fingerprint_sha256: str,
    execution_cost_policy: FastTrainingExecutionCostPolicy,
    counterfactual_base_quantity: float,
):
    """Project V2 targets while retaining at most one provenance row at a time."""

    if len(labels) != len(overlay_rows):
        raise ValueError("selected FL4/economics row counts do not reconcile")

    projected: list[FuturePathTrainingLabel] = []
    outcome_sets = []
    try:
        rows = zip(labels, overlay_rows, provenance_rows, strict=True)
        for label, row, provenance in rows:
            _validate_overlay_matches_label(row, label)
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
    except ValueError as exc:
        if "zip() argument" in str(exc):
            raise ValueError(
                "canonical counterfactual provenance population does not "
                "match the accepted V2 cohort exactly"
            ) from exc
        raise

    return tuple(projected), tuple(outcome_sets)
