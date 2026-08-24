from __future__ import annotations

from dataclasses import fields
from typing import Mapping

from shreks_brain.decision import DecisionAction

from .fingerprint import record_fingerprint, sha256_canonical
from .models import (
    SHADOW_CHALLENGER_SCHEMA_VERSION,
    ShadowDecisionRecord,
    ShadowEvidenceLedger,
    ShadowReasonCode,
)


_RECORD_FIELDS = frozenset(field.name for field in fields(ShadowDecisionRecord))
_LEDGER_FIELDS = frozenset(
    ("schema_version", "records", "ledger_fingerprint_sha256")
)


def build_ledger(records: tuple[ShadowDecisionRecord, ...]) -> ShadowEvidenceLedger:
    ordered = tuple(sorted(records, key=_record_sort_key))
    material = {
        "schema_version": SHADOW_CHALLENGER_SCHEMA_VERSION,
        "records": [record_to_dict(record) for record in ordered],
    }
    return ShadowEvidenceLedger(
        schema_version=SHADOW_CHALLENGER_SCHEMA_VERSION,
        records=ordered,
        ledger_fingerprint_sha256=sha256_canonical(material),
    )


def ledger_to_dict(ledger: ShadowEvidenceLedger) -> dict[str, object]:
    return {
        "schema_version": ledger.schema_version,
        "records": [record_to_dict(record) for record in ledger.records],
        "ledger_fingerprint_sha256": ledger.ledger_fingerprint_sha256,
    }


def record_to_dict(record: ShadowDecisionRecord) -> dict[str, object]:
    return {
        "schema_version": record.schema_version,
        "candidate_version": record.candidate_version,
        "strategy_version": record.strategy_version,
        "candidate_fingerprint_sha256": record.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": record.registry_fingerprint_sha256,
        "model_version": record.model_version,
        "model_training_fingerprint_sha256": record.model_training_fingerprint_sha256,
        "target_horizon_seconds": record.target_horizon_seconds,
        "target_minimum_return_pct": record.target_minimum_return_pct,
        "shadow_policy_version": record.shadow_policy_version,
        "enter_min_probability": record.enter_min_probability,
        "candidate_mint": record.candidate_mint,
        "as_of_unix_ms": record.as_of_unix_ms,
        "dataset_schema_version": record.dataset_schema_version,
        "decision_feature_fingerprint_sha256": record.decision_feature_fingerprint_sha256,
        "setup_name": record.setup_name,
        "safety_decision": record.safety_decision,
        "setup_state": record.setup_state,
        "market_regime": record.market_regime,
        "baseline_action": record.baseline_action.value,
        "positive_probability": record.positive_probability,
        "challenger_action": record.challenger_action.value,
        "reason": record.reason.value,
        "record_fingerprint_sha256": record.record_fingerprint_sha256,
    }


def decode_ledger_document(document: object) -> ShadowEvidenceLedger:
    mapping = _require_exact_mapping("ledger", document, _LEDGER_FIELDS)
    if mapping["schema_version"] != SHADOW_CHALLENGER_SCHEMA_VERSION:
        raise ValueError("ledger schema_version must equal e7-shadow-v1")
    raw_records = mapping["records"]
    if not isinstance(raw_records, list):
        raise ValueError("ledger records must be a list")
    records = tuple(_decode_record(value) for value in raw_records)
    ledger = ShadowEvidenceLedger(
        schema_version=mapping["schema_version"],  # type: ignore[arg-type]
        records=records,
        ledger_fingerprint_sha256=mapping["ledger_fingerprint_sha256"],  # type: ignore[arg-type]
    )
    expected = build_ledger(records).ledger_fingerprint_sha256
    if ledger.ledger_fingerprint_sha256 != expected:
        raise ValueError("ledger fingerprint does not match ledger content")
    return ledger


def _decode_record(value: object) -> ShadowDecisionRecord:
    mapping = _require_exact_mapping("record", value, _RECORD_FIELDS)
    try:
        baseline_action = DecisionAction(mapping["baseline_action"])
        challenger_action = DecisionAction(mapping["challenger_action"])
        reason = ShadowReasonCode(mapping["reason"])
    except (TypeError, ValueError) as error:
        raise ValueError("record contains an unsupported enum value") from error

    record = ShadowDecisionRecord(
        schema_version=mapping["schema_version"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        strategy_version=mapping["strategy_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        registry_fingerprint_sha256=mapping["registry_fingerprint_sha256"],  # type: ignore[arg-type]
        model_version=mapping["model_version"],  # type: ignore[arg-type]
        model_training_fingerprint_sha256=mapping["model_training_fingerprint_sha256"],  # type: ignore[arg-type]
        target_horizon_seconds=mapping["target_horizon_seconds"],  # type: ignore[arg-type]
        target_minimum_return_pct=mapping["target_minimum_return_pct"],  # type: ignore[arg-type]
        shadow_policy_version=mapping["shadow_policy_version"],  # type: ignore[arg-type]
        enter_min_probability=mapping["enter_min_probability"],  # type: ignore[arg-type]
        candidate_mint=mapping["candidate_mint"],  # type: ignore[arg-type]
        as_of_unix_ms=mapping["as_of_unix_ms"],  # type: ignore[arg-type]
        dataset_schema_version=mapping["dataset_schema_version"],  # type: ignore[arg-type]
        decision_feature_fingerprint_sha256=mapping["decision_feature_fingerprint_sha256"],  # type: ignore[arg-type]
        setup_name=mapping["setup_name"],  # type: ignore[arg-type]
        safety_decision=mapping["safety_decision"],  # type: ignore[arg-type]
        setup_state=mapping["setup_state"],  # type: ignore[arg-type]
        market_regime=mapping["market_regime"],  # type: ignore[arg-type]
        baseline_action=baseline_action,
        positive_probability=mapping["positive_probability"],  # type: ignore[arg-type]
        challenger_action=challenger_action,
        reason=reason,
        record_fingerprint_sha256=mapping["record_fingerprint_sha256"],  # type: ignore[arg-type]
    )
    if record.record_fingerprint_sha256 != record_fingerprint(record):
        raise ValueError("record fingerprint does not match record content")
    return record


def _require_exact_mapping(
    name: str,
    value: object,
    expected_fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != expected_fields or len(value) != len(expected_fields):
        raise ValueError(f"{name} fields must match the sealed schema exactly")
    return value


def _record_sort_key(record: ShadowDecisionRecord) -> tuple[int, str, str, str, str]:
    return (
        record.as_of_unix_ms,
        record.candidate_version,
        record.candidate_mint,
        record.shadow_policy_version,
        record.record_fingerprint_sha256,
    )
