from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.proof as proof
from shreks_brain.proof import engine


_EXPECTED_PUBLIC_API = {
    "PAPER_PROOF_SCHEMA_VERSION",
    "PaperProofDecision",
    "PaperProofGateStatus",
    "PaperProofGateCode",
    "PaperProofPolicy",
    "PaperProofGateResult",
    "CandidateProofAssessment",
    "CandidateProofAssessmentStore",
    "evaluate_candidate_proof",
}


def test_public_api_is_exact_and_deliberately_small() -> None:
    assert set(proof.__all__) == _EXPECTED_PUBLIC_API


def test_store_surface_is_exactly_append_only() -> None:
    public = {
        name
        for name in dir(proof.CandidateProofAssessmentStore)
        if not name.startswith("_")
    }
    assert public == {"append", "load"}


def test_public_api_has_no_registry_execution_or_live_authority() -> None:
    forbidden_fragments = (
        "registry_store",
        "record_status",
        "promote",
        "promotion_apply",
        "trade_intent",
        "execute",
        "sign",
        "submit",
        "live",
        "delete",
        "overwrite",
        "rewrite",
    )
    for name in proof.__all__:
        lowered = name.lower()
        assert all(fragment not in lowered for fragment in forbidden_fragments)

    source = inspect.getsource(engine).lower()
    for token in (
        "registrystore",
        "record_status(",
        "record_status_event(",
        "tradeintent",
        "enable_live",
        ".sign(",
        ".submit(",
    ):
        assert token not in source


def test_importing_proof_does_not_eagerly_import_training_or_parquet_modules() -> None:
    probe = (
        "import sys; import shreks_brain.proof as p; "
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
