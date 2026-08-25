from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.paper_evaluation as paper_evaluation
from shreks_brain.paper_evaluation import store


_EXPECTED_PUBLIC_API = {
    "PAPER_EVALUATION_SCHEMA_VERSION",
    "PaperEntryProvenance",
    "PaperPositionExecutionEvidence",
    "PaperClosedPositionEvidence",
    "PaperOrphanCostEvidence",
    "PaperEvaluationCapture",
    "PaperEvaluationLedger",
    "PaperEvaluationEvidenceStore",
    "extract_paper_evaluation_evidence",
    "build_evaluated_trades",
}


def test_public_api_is_exact_and_deliberately_small() -> None:
    assert set(paper_evaluation.__all__) == _EXPECTED_PUBLIC_API
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(paper_evaluation, name)


def test_public_api_exposes_no_registry_promotion_or_execution_authority() -> None:
    forbidden = {
        "RegistryStore",
        "ChampionChallengerRegistryStore",
        "record_status",
        "record_status_event",
        "PromotionAssessmentStore",
        "evaluate_promotion",
        "TradeIntent",
        "RuntimeMode",
        "enable_live",
        "sign",
        "submit",
    }
    assert forbidden.isdisjoint(set(dir(paper_evaluation)))


def test_store_surface_remains_append_only_and_has_no_authority_methods() -> None:
    public = {
        name
        for name in dir(paper_evaluation.PaperEvaluationEvidenceStore)
        if not name.startswith("_")
    }
    assert public == {"load", "record_capture", "record_cycle", "evaluated_trades"}

    source = inspect.getsource(store.PaperEvaluationEvidenceStore)
    for token in (
        "record_status(",
        "record_status_event(",
        "evaluate_promotion(",
        "enable_live",
        ".sign(",
        ".submit(",
    ):
        assert token not in source


def test_importing_public_package_does_not_eagerly_import_training_or_parquet_modules() -> None:
    probe = (
        "import sys; import shreks_brain.paper_evaluation as p; "
        "assert set(p.__all__) == " + repr(_EXPECTED_PUBLIC_API) + "; "
        "assert 'sklearn' not in sys.modules; "
        "assert 'pyarrow' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
