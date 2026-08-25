from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path

import pytest

from shreks_brain.promotion import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionAssessmentStore,
    PromotionGateResult,
    evaluate_promotion,
)
from shreks_brain.promotion.fingerprint import sha256_canonical

from test_promotion_engine import _fixture, _policy, _trades


def _assessment(*, evaluated_at_unix_ms: int = 10_000) -> PromotionAssessment:
    report, baseline, candidate, registry, shadow = _fixture()
    return evaluate_promotion(
        registry,
        candidate.candidate_version,
        report,
        _trades(candidate.candidate_version),
        shadow,
        (baseline,),
        _policy(),
        evaluated_at_unix_ms,
    )


def _assessment_material(value: PromotionAssessment) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": value.registry_fingerprint_sha256,
        "evaluation_fingerprint_sha256": value.evaluation_fingerprint_sha256,
        "trade_evidence_fingerprint_sha256": value.trade_evidence_fingerprint_sha256,
        "shadow_ledger_fingerprint_sha256": value.shadow_ledger_fingerprint_sha256,
        "baseline_evaluation_identities": value.baseline_evaluation_identities,
        "evaluated_at_unix_ms": value.evaluated_at_unix_ms,
        "gates": tuple(
            {
                "code": gate.code,
                "status": gate.status,
                "observed_value": gate.observed_value,
                "threshold_value": gate.threshold_value,
                "message": gate.message,
            }
            for gate in value.gates
        ),
        "decision": value.decision,
    }


def _refingerprint(value: PromotionAssessment, **changes: object) -> PromotionAssessment:
    draft = replace(value, assessment_fingerprint_sha256="0" * 64, **changes)
    return replace(
        draft,
        assessment_fingerprint_sha256=sha256_canonical(_assessment_material(draft)),
    )


def test_missing_store_loads_empty_tuple_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "promotion" / "assessments.json"

    assert PromotionAssessmentStore(path).load() == ()
    assert not path.exists()


def test_append_round_trip_is_canonical_ordered_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "promotion.json"
    store = PromotionAssessmentStore(path)
    base = _assessment()
    later = _refingerprint(base, evaluated_at_unix_ms=12_000)
    earlier = _refingerprint(base, evaluated_at_unix_ms=11_000)

    first = store.append(later)
    second = store.append(earlier)
    loaded = PromotionAssessmentStore(path).load()

    assert first == (later,)
    assert second == (earlier, later)
    assert loaded == second
    assert not path.with_name(path.name + ".tmp").exists()

    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert set(parsed) == {"schema_version", "assessments"}
    assert parsed["schema_version"] == PROMOTION_SCHEMA_VERSION
    assert raw == json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def test_canonical_order_uses_time_candidate_then_policy(tmp_path: Path) -> None:
    store = PromotionAssessmentStore(tmp_path / "promotion.json")
    base = _assessment(evaluated_at_unix_ms=20_000)
    values = (
        _refingerprint(base, candidate_version="candidate-b", policy_version="policy-b"),
        _refingerprint(base, candidate_version="candidate-a", policy_version="policy-z"),
        _refingerprint(base, candidate_version="candidate-a", policy_version="policy-a"),
        _refingerprint(base, evaluated_at_unix_ms=19_000),
    )
    for value in values:
        store.append(value)

    loaded = store.load()
    assert tuple(
        (value.evaluated_at_unix_ms, value.candidate_version, value.policy_version)
        for value in loaded
    ) == (
        (19_000, "challenger-v1", "promotion-policy-v1"),
        (20_000, "candidate-a", "policy-a"),
        (20_000, "candidate-a", "policy-z"),
        (20_000, "candidate-b", "policy-b"),
    )


def test_identical_append_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "promotion.json"
    store = PromotionAssessmentStore(path)
    assessment = _assessment()

    first = store.append(assessment)
    before = path.read_bytes()
    second = store.append(assessment)

    assert second == first
    assert path.read_bytes() == before


def test_same_identity_with_different_valid_content_fails_closed(tmp_path: Path) -> None:
    store = PromotionAssessmentStore(tmp_path / "promotion.json")
    assessment = _assessment()
    store.append(assessment)

    first_gate = assessment.gates[0]
    changed_gate = PromotionGateResult(
        first_gate.code,
        first_gate.status,
        first_gate.observed_value,
        first_gate.threshold_value,
        first_gate.message + " changed",
    )
    conflict = _refingerprint(
        assessment,
        gates=(changed_gate,) + assessment.gates[1:],
    )

    with pytest.raises(ValueError, match="assessment identity"):
        store.append(conflict)


def test_append_rejects_wrong_type_and_bad_assessment_fingerprint(tmp_path: Path) -> None:
    store = PromotionAssessmentStore(tmp_path / "promotion.json")
    with pytest.raises(ValueError, match="PromotionAssessment"):
        store.append(object())  # type: ignore[arg-type]

    assessment = _assessment()
    tampered = replace(assessment, assessment_fingerprint_sha256="f" * 64)
    with pytest.raises(ValueError, match="assessment fingerprint"):
        store.append(tampered)


def _write_document(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, allow_nan=True), encoding="utf-8")


def _persisted_document(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    path = tmp_path / "promotion.json"
    PromotionAssessmentStore(path).append(_assessment())
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_load_rejects_malformed_json_and_unknown_top_level_fields(tmp_path: Path) -> None:
    path = tmp_path / "promotion.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="promotion assessment file"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["unknown"] = True
    _write_document(path, document)
    with pytest.raises(ValueError, match="fields"):
        PromotionAssessmentStore(path).load()


def test_load_rejects_unknown_assessment_or_gate_fields_and_invalid_enums(tmp_path: Path) -> None:
    path, document = _persisted_document(tmp_path)
    assessment = document["assessments"][0]  # type: ignore[index]
    assessment["unknown"] = True  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="fields"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    gate = document["assessments"][0]["gates"][0]  # type: ignore[index]
    gate["unknown"] = True
    _write_document(path, document)
    with pytest.raises(ValueError, match="fields"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["decision"] = "PROMOTE"  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="enum"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["gates"][0]["status"] = "MAYBE"  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="enum"):
        PromotionAssessmentStore(path).load()


def test_load_rejects_wrong_schema_types_and_non_finite_gate_values(tmp_path: Path) -> None:
    path, document = _persisted_document(tmp_path)
    document["schema_version"] = "wrong"
    _write_document(path, document)
    with pytest.raises(ValueError, match="schema"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["evaluated_at_unix_ms"] = True  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="evaluated_at_unix_ms"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["gates"][0]["observed_value"] = math.nan  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="finite"):
        PromotionAssessmentStore(path).load()


def test_load_independently_rejects_tampered_evidence_and_assessment_fingerprints(
    tmp_path: Path,
) -> None:
    for field in (
        "candidate_fingerprint_sha256",
        "registry_fingerprint_sha256",
        "evaluation_fingerprint_sha256",
        "trade_evidence_fingerprint_sha256",
        "shadow_ledger_fingerprint_sha256",
    ):
        path, document = _persisted_document(tmp_path)
        document["assessments"][0][field] = "f" * 64  # type: ignore[index]
        _write_document(path, document)
        with pytest.raises(ValueError, match="assessment fingerprint"):
            PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["baseline_evaluation_identities"][0][1] = "f" * 64  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="assessment fingerprint"):
        PromotionAssessmentStore(path).load()

    path, document = _persisted_document(tmp_path)
    document["assessments"][0]["assessment_fingerprint_sha256"] = "f" * 64  # type: ignore[index]
    _write_document(path, document)
    with pytest.raises(ValueError, match="assessment fingerprint"):
        PromotionAssessmentStore(path).load()


def test_store_exposes_no_history_rewrite_registry_or_live_authority(tmp_path: Path) -> None:
    store = PromotionAssessmentStore(tmp_path / "promotion.json")
    for name in (
        "delete",
        "rewrite",
        "rewrite_history",
        "promote",
        "record_status",
        "record_status_event",
        "enable_live",
        "sign",
        "submit",
    ):
        assert not hasattr(store, name)
