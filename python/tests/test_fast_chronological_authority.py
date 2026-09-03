from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.fast_learning as fast_learning
import shreks_brain.fast_validation as fast_validation
import shreks_brain.fast_validation.engine as engine
import shreks_brain.fast_validation.models as models


EXPECTED_PUBLIC_API = (
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME",
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION",
    "FastChronologicalFold",
    "FastChronologicalValidationPolicy",
    "FastLeakageQuarantineSummary",
    "FastChronologicalFoldResult",
    "FastChronologicalValidationRun",
    "run_fast_chronological_validation",
)


def test_fast_validation_public_api_is_exact_and_subset_trainer_is_not_root_exported() -> None:
    assert fast_validation.__all__ == EXPECTED_PUBLIC_API
    assert "train_fast_forecast_baseline_for_decision_identities" not in fast_learning.__all__


def test_importing_fast_validation_does_not_eagerly_import_sklearn() -> None:
    script = (
        "import sys; import shreks_brain.fast_validation; "
        "assert not any(k == 'sklearn' or k.startswith('sklearn.') for k in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_fast_validation_sources_have_no_metric_promotion_execution_or_live_authority() -> None:
    source = "\n".join(inspect.getsource(module) for module in (models, engine))
    for forbidden in (
        "shreks_brain.promotion",
        "shreks_brain.registry",
        "shreks_providers",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "RuntimeMode::Live",
        "send_transaction",
        "private_key",
        "import sqlite3",
        "import pyarrow",
        "import random",
        "from random",
        "roc_auc",
        "accuracy_score",
        "calibration_curve",
        "profit_factor",
        "promote_champion",
    ):
        assert forbidden not in source
