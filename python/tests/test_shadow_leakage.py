from __future__ import annotations

import subprocess
import sys

from shreks_brain.research import RESEARCH_LABEL_COLUMNS
from shreks_brain.shadow import ShadowDecisionPolicy, evaluate_shadow_challenger

from test_shadow_engine import model, registered_candidate, registry_with, row


def test_future_label_mutation_cannot_change_shadow_decision_or_fingerprints() -> None:
    artifact = model()
    candidate = registered_candidate(artifact)
    registry = registry_with(candidate)
    policy = ShadowDecisionPolicy("shadow-policy-v1", 0.8)

    base = row()
    changed = dict(base)
    for column in RESEARCH_LABEL_COLUMNS:
        if column.endswith("_return_pct") or column.endswith("_mfe_pct") or column.endswith("_mae_pct"):
            changed[column] = 999.0
        elif column.endswith("_rug_or_dead_pool"):
            changed[column] = True
        elif column.endswith("_exitability"):
            changed[column] = "NOT_EXITABLE"
        elif column.endswith("_status"):
            changed[column] = "COMPLETED"
        elif column.endswith("_observed_at_unix_ms"):
            changed[column] = 999_999
        elif column.endswith("_checkpoint_target_unix_ms"):
            changed[column] = 888_888
        elif column.endswith("_checkpoint_tolerance_ms"):
            changed[column] = 777
        elif column.endswith("_sample_count"):
            changed[column] = 123
        else:
            changed[column] = "mutated-future-only"

    first = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        base,
        policy,
    )
    second = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        changed,
        policy,
    )

    assert second.positive_probability == first.positive_probability
    assert second.challenger_action is first.challenger_action
    assert second.reason is first.reason
    assert (
        second.decision_feature_fingerprint_sha256
        == first.decision_feature_fingerprint_sha256
    )
    assert second.record_fingerprint_sha256 == first.record_fingerprint_sha256


def test_material_decision_time_feature_changes_feature_and_record_fingerprint() -> None:
    artifact = model()
    candidate = registered_candidate(artifact)
    registry = registry_with(candidate)
    policy = ShadowDecisionPolicy("shadow-policy-v1", 0.8)

    first = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        row(liquidity=300.0),
        policy,
    )
    second = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        row(liquidity=250.0),
        policy,
    )

    assert (
        second.decision_feature_fingerprint_sha256
        != first.decision_feature_fingerprint_sha256
    )
    assert second.record_fingerprint_sha256 != first.record_fingerprint_sha256


def test_repeated_identical_shadow_evaluation_is_deterministic() -> None:
    artifact = model()
    candidate = registered_candidate(artifact)
    registry = registry_with(candidate)
    policy = ShadowDecisionPolicy("shadow-policy-v1", 0.8)
    input_row = row()

    first = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        input_row,
        policy,
    )
    second = evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        dict(input_row),
        policy,
    )
    assert second == first


def test_importing_shadow_does_not_eagerly_import_sklearn_or_pyarrow() -> None:
    script = (
        "import sys; import shreks_brain.shadow; "
        "assert not any(k == 'sklearn' or k.startswith('sklearn.') for k in sys.modules); "
        "assert not any(k == 'pyarrow' or k.startswith('pyarrow.') for k in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script], check=True)
