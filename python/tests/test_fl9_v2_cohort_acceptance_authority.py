from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from shreks_brain import fl9_v2_cohort_acceptance as cohort


_EXPECTED_PUBLIC_API = {
    "FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION",
    "FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME",
    "FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION",
    "FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION",
    "Fl9V2CoverageSessionCheckpoint",
    "Fl9V2CohortEvidenceFloorPolicy",
    "Fl9V2CohortAcceptancePolicy",
    "Fl9V2ConcentrationSummary",
    "Fl9V2AcceptedDecision",
    "Fl9V2QuarantinedDecision",
    "Fl9V2CohortAcceptanceManifest",
    "Fl9V2CohortAcceptanceArtifact",
    "SqliteFl9V2CohortSource",
    "build_fl9_v2_cohort_acceptance",
    "write_fl9_v2_cohort_acceptance",
    "read_fl9_v2_cohort_acceptance",
}


def test_public_api_is_exact_and_intentionally_small() -> None:
    assert set(cohort.__all__) == _EXPECTED_PUBLIC_API
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(cohort, name)


def test_package_source_has_no_target_model_economics_execution_or_live_authority() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fl9_v2_cohort_acceptance"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.py"))
        if path.name != "cli.py"
    )
    for forbidden in (
        "fast_training_bundle",
        "future_path",
        "FastTrainingBundle",
        "train_fast_forecast",
        "predict_fast_forecast",
        "fast_validation_v2.engine",
        "fast_evaluation",
        "training_economics",
        "fast_first_champion",
        "promotion",
        "registry",
        "paper_executor",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "requests.",
        "httpx",
    ):
        assert forbidden not in source


def test_package_import_does_not_eagerly_load_training_or_evaluation_stack() -> None:
    code = r"""
import json
import sys
import shreks_brain.fl9_v2_cohort_acceptance

forbidden = (
    "sklearn",
    "pyarrow",
    "shreks_brain.fast_learning.trainer",
    "shreks_brain.fast_evaluation",
    "shreks_brain.fast_first_champion",
    "shreks_brain.research.fast_training_bundle",
    "shreks_brain.research.fast_training_targets",
)
print(json.dumps({
    name: any(
        loaded == name or loaded.startswith(name + ".")
        for loaded in sys.modules
    )
    for name in forbidden
}, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {
        "pyarrow": False,
        "shreks_brain.fast_evaluation": False,
        "shreks_brain.fast_first_champion": False,
        "shreks_brain.fast_learning.trainer": False,
        "shreks_brain.research.fast_training_bundle": False,
        "shreks_brain.research.fast_training_targets": False,
        "sklearn": False,
    }


def test_production_checkpoint_is_frozen_in_public_policy() -> None:
    policy = cohort.Fl9V2CohortAcceptancePolicy()
    floors = cohort.Fl9V2CohortEvidenceFloorPolicy()

    assert policy.source_session_ids == tuple(range(115, 123))
    assert policy.expected_raw_row_count == 504_716
    assert policy.expected_eligible_row_count == 274_334
    assert policy.expected_training_raw_row_count == 164_645
    assert policy.expected_validation_raw_row_count == 54_858
    assert policy.expected_test_raw_row_count == 54_831
    assert policy.expected_validation_unseen_mint_rows == 49_754
    assert policy.expected_validation_unseen_mint_unique_mints == 24
    assert policy.expected_test_unseen_mint_rows == 54_828
    assert policy.expected_test_unseen_mint_unique_mints == 31

    assert floors.minimum_total_eligible_rows == 250_000
    assert floors.minimum_training_rows == 150_000
    assert floors.minimum_validation_rows == 50_000
    assert floors.minimum_test_rows == 50_000
    assert floors.minimum_unseen_mint_validation_rows == 40_000
    assert floors.minimum_unseen_mint_validation_unique_mints == 20
    assert floors.minimum_unseen_mint_test_rows == 40_000
    assert floors.minimum_unseen_mint_test_unique_mints == 25
    assert floors.minimum_natural_test_scored_observations == 40_000
    assert floors.minimum_unseen_mint_test_scored_observations == 35_000
