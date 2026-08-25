from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from shreks_brain.proof.codec import (
    assessments_document,
    decode_assessments_document,
    encode_assessments,
)
from shreks_brain.proof.fingerprint import sha256_canonical
from shreks_brain.proof.models import (
    PAPER_PROOF_SCHEMA_VERSION,
    CandidateProofAssessment,
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateResult,
    PaperProofGateStatus,
)
from shreks_brain.proof.store import CandidateProofAssessmentStore


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _gates() -> tuple[PaperProofGateResult, ...]:
    return tuple(
        PaperProofGateResult(
            code=code,
            status=PaperProofGateStatus.PASS,
            observed_value=1,
            threshold_value=1,
            message=f"{code.value} checked",
        )
        for code in sorted(PaperProofGateCode, key=lambda value: value.value)
    )


def _assessment(**overrides: object) -> CandidateProofAssessment:
    values: dict[str, object] = dict(
        schema_version=PAPER_PROOF_SCHEMA_VERSION,
        policy_version="proof-v1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA_A,
        registry_fingerprint_sha256=SHA_B,
        e8_assessment_fingerprint_sha256=SHA_C,
        paper_run_id="run-1",
        paper_ledger_fingerprint_sha256=SHA_A,
        paper_evaluation_fingerprint_sha256=SHA_B,
        paper_trade_evidence_fingerprint_sha256=SHA_C,
        evaluated_at_unix_ms=1_000,
        gates=_gates(),
        decision=PaperProofDecision.SUFFICIENT,
        assessment_fingerprint_sha256="0" * 64,
    )
    values.update(overrides)
    draft = CandidateProofAssessment(**values)  # type: ignore[arg-type]
    material = asdict(draft)
    material["assessment_fingerprint_sha256"] = "0" * 64
    return replace(
        draft,
        assessment_fingerprint_sha256=sha256_canonical(material),
    )


def test_missing_store_loads_empty_without_creating_file(tmp_path) -> None:
    path = tmp_path / "proof.json"
    store = CandidateProofAssessmentStore(path)
    assert store.load() == ()
    assert not path.exists()


def test_append_round_trip_is_canonical_and_exact_schema(tmp_path) -> None:
    path = tmp_path / "proof.json"
    assessment = _assessment()
    store = CandidateProofAssessmentStore(path)
    assert store.append(assessment) == (assessment,)
    assert store.load() == (assessment,)

    payload = path.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert not payload.endswith("\n\n")
    assert payload == encode_assessments((assessment,))
    document = json.loads(payload)
    assert tuple(sorted(document)) == ("assessments", "schema_version")
    assert document["schema_version"] == PAPER_PROOF_SCHEMA_VERSION
    assert document == assessments_document((assessment,))
    encoded = document["assessments"][0]
    assert encoded["decision"] == "SUFFICIENT"
    assert encoded["gates"][0]["code"] == sorted(
        code.value for code in PaperProofGateCode
    )[0]
    assert encoded["gates"][0]["status"] == "PASS"


def test_identical_duplicate_is_byte_for_byte_idempotent(tmp_path) -> None:
    path = tmp_path / "proof.json"
    store = CandidateProofAssessmentStore(path)
    assessment = _assessment()
    store.append(assessment)
    before = path.read_bytes()
    assert store.append(assessment) == (assessment,)
    assert path.read_bytes() == before


def test_same_identity_with_different_content_fails_closed(tmp_path) -> None:
    store = CandidateProofAssessmentStore(tmp_path / "proof.json")
    first = _assessment()
    second = _assessment(e8_assessment_fingerprint_sha256=SHA_A)
    store.append(first)
    with pytest.raises(ValueError, match="different content"):
        store.append(second)


def test_store_orders_assessments_canonically(tmp_path) -> None:
    path = tmp_path / "proof.json"
    store = CandidateProofAssessmentStore(path)
    later = _assessment(evaluated_at_unix_ms=2_000, paper_run_id="run-z")
    earlier = _assessment(evaluated_at_unix_ms=1_000, paper_run_id="run-a")
    store.append(later)
    result = store.append(earlier)
    assert result == (earlier, later)
    assert store.load() == result


def test_successful_write_leaves_no_sibling_tmp(tmp_path) -> None:
    path = tmp_path / "proof.json"
    CandidateProofAssessmentStore(path).append(_assessment())
    assert not path.with_name(path.name + ".tmp").exists()


def test_load_rejects_malformed_json_and_unknown_fields(tmp_path) -> None:
    path = tmp_path / "proof.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        CandidateProofAssessmentStore(path).load()

    document = assessments_document((_assessment(),))
    document["unknown"] = 1
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        CandidateProofAssessmentStore(path).load()


def test_decoder_rejects_unknown_nested_fields_and_invalid_enum() -> None:
    document = assessments_document((_assessment(),))
    document["assessments"][0]["unknown"] = 1
    with pytest.raises(ValueError, match="fields"):
        decode_assessments_document(document)

    document = assessments_document((_assessment(),))
    document["assessments"][0]["gates"][0]["status"] = "MAYBE"
    with pytest.raises(ValueError, match="enum"):
        decode_assessments_document(document)


def test_decoder_rejects_non_finite_gate_value() -> None:
    document = assessments_document((_assessment(),))
    document["assessments"][0]["gates"][0]["observed_value"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        decode_assessments_document(document)


def test_decoder_rejects_tampered_assessment_fingerprint() -> None:
    document = assessments_document((_assessment(),))
    document["assessments"][0]["paper_run_id"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        decode_assessments_document(document)


def test_decoder_rejects_wrong_schema_and_noncanonical_order() -> None:
    first = _assessment(evaluated_at_unix_ms=1_000, paper_run_id="run-a")
    second = _assessment(evaluated_at_unix_ms=2_000, paper_run_id="run-b")
    document = assessments_document((first, second))
    document["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="schema_version"):
        decode_assessments_document(document)

    document = assessments_document((first, second))
    document["assessments"] = list(reversed(document["assessments"]))
    with pytest.raises(ValueError, match="canonical"):
        decode_assessments_document(document)


def test_append_rejects_wrong_type_and_stale_fingerprint(tmp_path) -> None:
    store = CandidateProofAssessmentStore(tmp_path / "proof.json")
    with pytest.raises(ValueError, match="CandidateProofAssessment"):
        store.append(object())  # type: ignore[arg-type]

    stale = replace(_assessment(), paper_run_id="changed")
    with pytest.raises(ValueError, match="fingerprint"):
        store.append(stale)


def test_store_surface_has_no_history_rewrite_or_authority_methods() -> None:
    public = {
        name
        for name in dir(CandidateProofAssessmentStore)
        if not name.startswith("_")
    }
    assert public == {"append", "load"}
