from __future__ import annotations

import shreks_brain.evaluation as evaluation


EXPECTED_E10_EXPORTS = (
    "EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION",
    "TradingEvaluationEvidence",
    "TradingEvaluationEvidenceStore",
)


def test_e10_public_exports_are_additive() -> None:
    for name in EXPECTED_E10_EXPORTS:
        assert hasattr(evaluation, name)
    assert evaluation.__all__[-3:] == EXPECTED_E10_EXPORTS


def test_e10_store_exposes_only_append_get_and_load() -> None:
    store_type = evaluation.TradingEvaluationEvidenceStore
    public_methods = {
        name
        for name, value in vars(store_type).items()
        if not name.startswith("_") and callable(value)
    }

    assert public_methods == {"append", "get", "load"}


def test_e10_store_exposes_no_execution_or_promotion_authority() -> None:
    forbidden_fragments = (
        "delete",
        "rewrite",
        "update",
        "registry",
        "promote",
        "promotion",
        "trade",
        "sign",
        "submit",
        "live",
    )
    public_names = {
        name.lower()
        for name in vars(evaluation.TradingEvaluationEvidenceStore)
        if not name.startswith("_")
    }

    assert not any(
        fragment in name
        for name in public_names
        for fragment in forbidden_fragments
    )
