from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.fast_deterministic_lifecycle import (
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
    FastDeterministicLifecycleDecision,
    FastDeterministicLifecycleResults,
    decode_fast_deterministic_lifecycle_results,
    fast_deterministic_lifecycle_to_paper_assessment,
)
from shreks_brain.fast_paper import FastPaperAction, FastPaperActionAssessment


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_lifecycle_results_v1.json"
)


def _payload() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_shared_golden_lifecycle_wire_decodes_exactly() -> None:
    decoded = decode_fast_deterministic_lifecycle_results(_payload())

    assert type(decoded) is FastDeterministicLifecycleResults
    assert decoded.schema_name == FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME
    assert decoded.schema_version == FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION
    assert (
        decoded.batch_fingerprint_sha256
        == "bd7e267a2a7cf836f6db87ad75306676efaf500446e62097d58004559812a576"
    )
    assert decoded.policy.entry_baseline_kind == "IMPULSE_SCALP"
    assert decoded.policy.manager_baseline_kind == "LONGER_RUNNER"
    assert len(decoded.decisions) == 2
    assert decoded.decisions[0].posture == "FLAT"
    assert decoded.decisions[0].action == "BUY"
    assert decoded.decisions[0].current_exposure_fraction is None
    assert decoded.decisions[1].posture == "OPEN"
    assert decoded.decisions[1].action == "REDUCE"
    assert decoded.decisions[1].current_exposure_fraction == 0.8


def test_decoder_requires_canonical_json_and_exact_fingerprint() -> None:
    document = json.loads(_payload())

    non_canonical = json.dumps(document, indent=2)
    with pytest.raises(ValueError, match="canonical"):
        decode_fast_deterministic_lifecycle_results(non_canonical)

    document["decisions"][1]["target_exposure_fraction"] = 0.3
    tampered = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_deterministic_lifecycle_results(tampered)


def test_decoder_rejects_unknown_fields_and_invalid_lifecycle_semantics() -> None:
    document = json.loads(_payload())
    document["unexpected"] = True
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(ValueError, match="unknown|missing"):
        decode_fast_deterministic_lifecycle_results(payload)

    document = json.loads(_payload())
    document["decisions"][0]["action"] = "REDUCE"
    material = dict(document)
    material.pop("batch_fingerprint_sha256")
    import hashlib

    document["batch_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(ValueError, match="action|FLAT"):
        decode_fast_deterministic_lifecycle_results(payload)


def test_lifecycle_decision_translates_directly_to_truthful_fast_paper_assessment() -> None:
    decoded = decode_fast_deterministic_lifecycle_results(_payload())

    buy = fast_deterministic_lifecycle_to_paper_assessment(
        decoded.decisions[0],
        assessment_version="baseline-assessment-v1",
        strategy_family="fast_deterministic_lifecycle",
        strategy_version="impulse-scalp__longer-runner",
    )
    assert type(buy) is FastPaperActionAssessment
    assert buy.action is FastPaperAction.BUY
    assert buy.source_event_id == "sig-a:0"
    assert buy.reasons == (
        "component_kind=IMPULSE_SCALP",
        "component_version=1",
        "posture=FLAT",
        "current_exposure_fraction=none",
        "target_exposure_fraction=0.8",
    )

    reduce = fast_deterministic_lifecycle_to_paper_assessment(
        decoded.decisions[1],
        assessment_version="baseline-assessment-v1",
        strategy_family="fast_deterministic_lifecycle",
        strategy_version="impulse-scalp__longer-runner",
    )
    assert reduce.action is FastPaperAction.REDUCE
    assert reduce.reasons == (
        "component_kind=LONGER_RUNNER",
        "component_version=1",
        "posture=OPEN",
        "current_exposure_fraction=0.8",
        "target_exposure_fraction=0.4",
    )


def test_translation_requires_exact_decision_type() -> None:
    decoded = decode_fast_deterministic_lifecycle_results(_payload())
    decision = decoded.decisions[0]
    assert type(decision) is FastDeterministicLifecycleDecision

    with pytest.raises(ValueError, match="exact FastDeterministicLifecycleDecision"):
        fast_deterministic_lifecycle_to_paper_assessment(
            object(),
            assessment_version="baseline-assessment-v1",
            strategy_family="fast_deterministic_lifecycle",
            strategy_version="impulse-scalp__longer-runner",
        )


def test_lifecycle_python_package_has_no_learned_forecast_or_execution_authority() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "shreks_brain" / "fast_deterministic_lifecycle"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )

    for forbidden in (
        "FastCampaignDecisionResult",
        "selected_reward_bps",
        "selected_risk_bps",
        "horizon_evidence",
        "requests.",
        "sqlite3",
        "PaperLedger",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "RiskContext",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
