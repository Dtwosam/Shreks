from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.fast_validation as v1
import shreks_brain.fast_validation_v2 as v2
import shreks_brain.fast_validation_v2.engine as engine
import shreks_brain.fast_validation_v2.firewall as firewall
import shreks_brain.fast_validation_v2.models as models
import shreks_brain.fast_validation_v2.population as population


EXPECTED_V1_PUBLIC_API = (
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_NAME",
    "FAST_CHRONOLOGICAL_VALIDATION_SCHEMA_VERSION",
    "FastChronologicalFold",
    "FastChronologicalValidationPolicy",
    "FastLeakageQuarantineSummary",
    "FastChronologicalFoldResult",
    "FastChronologicalValidationRun",
    "run_fast_chronological_validation",
)

EXPECTED_V2_PUBLIC_API = (
    "FAST_CHRONOLOGICAL_GENERALIZATION_POLICY_VERSION",
    "FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_NAME",
    "FAST_CHRONOLOGICAL_GENERALIZATION_SCHEMA_VERSION",
    "FastChronologicalGeneralizationPolicy",
    "FastFutureNoveltySummary",
    "FastSignatureQuarantineSummary",
    "FastChronologicalGeneralizationFoldResult",
    "FastChronologicalGeneralizationRun",
    "run_fast_chronological_generalization",
)


def test_v1_public_api_remains_exact_and_v2_api_is_explicit() -> None:
    assert v1.__all__ == EXPECTED_V1_PUBLIC_API
    assert v2.__all__ == EXPECTED_V2_PUBLIC_API


def test_importing_fast_validation_v2_does_not_eagerly_import_sklearn() -> None:
    script = (
        "import sys; import shreks_brain.fast_validation_v2; "
        "assert not any(k == 'sklearn' or k.startswith('sklearn.') "
        "for k in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_v2_sources_have_no_metric_promotion_execution_or_live_authority() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in (models, firewall, population, engine)
    )
    for forbidden in (
        "requests.",
        "httpx",
        "import sqlite3",
        "import pyarrow",
        "import random",
        "from random",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "RuntimeMode::Live",
        "sign_transaction",
        "submit_transaction",
        "send_transaction",
        "promote_champion",
        "shreks_brain.promotion",
        "shreks_brain.registry",
        "profit_factor",
        "roc_auc",
        "accuracy_score",
    ):
        assert forbidden not in source
