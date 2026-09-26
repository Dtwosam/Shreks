from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignDecisionPosition,
    FastCampaignDecisionResults,
    build_fast_campaign_decision_batch,
    build_fast_campaign_decision_request,
)
from shreks_brain.fast_campaign_offline import (
    evaluate_fast_campaign_decision_batch_offline,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
)

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest


FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_decision_evidence"
)
FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION = 1
_QUOTE_STATES = frozenset({"EXECUTABLE", "UNAVAILABLE", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class FastPaperShadowDecisionInput:
    record: FastTrainingFeatureRecord
    position: FastCampaignDecisionPosition
    constraints: FastCampaignActionConstraints
    evaluated_at_unix_ms: int
    quote_state: str

    def __post_init__(self) -> None:
        if type(self.record) is not FastTrainingFeatureRecord:
            raise ValueError("record must be an exact FastTrainingFeatureRecord")
        if type(self.position) is not FastCampaignDecisionPosition:
            raise ValueError(
                "position must be an exact FastCampaignDecisionPosition"
            )
        if type(self.constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "constraints must be an exact FastCampaignActionConstraints"
            )
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if self.evaluated_at_unix_ms < self.record.decision_observed_at_unix_ms:
            raise ValueError(
                "shadow evaluation cannot precede the source decision"
            )
        if self.quote_state not in _QUOTE_STATES:
            raise ValueError("quote_state is unsupported")


@dataclass(frozen=True, slots=True)
class FastPaperShadowDecisionEvidence:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    release_source_sha: str
    champion_version: str
    champion_fingerprint_sha256: str
    action_policy_version: int
    source_event_id: str
    source_sequence: int
    market_key: str
    decision_observed_at_unix_ms: int
    evaluated_at_unix_ms: int
    event_to_decision_latency_ms: int
    quote_state: str
    action: str
    reason: str
    selected_horizon_ms: int | None
    current_exposure_fraction: float
    target_exposure_fraction: float
    selected_reward_bps: float
    selected_risk_bps: float
    selected_execution_cost_bps: float
    selected_value_bps: float
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME:
            raise ValueError("shadow evidence schema_name is incompatible")
        if self.schema_version != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("shadow evidence schema_version is incompatible")
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )
        _require_source_sha("release_source_sha", self.release_source_sha)
        _require_non_empty("champion_version", self.champion_version)
        _require_sha256(
            "champion_fingerprint_sha256",
            self.champion_fingerprint_sha256,
        )
        _require_positive_int(
            "action_policy_version",
            self.action_policy_version,
        )
        _require_non_empty("source_event_id", self.source_event_id)
        _require_positive_int("source_sequence", self.source_sequence)
        _require_non_empty("market_key", self.market_key)
        _require_non_negative_int(
            "decision_observed_at_unix_ms",
            self.decision_observed_at_unix_ms,
        )
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if self.evaluated_at_unix_ms < self.decision_observed_at_unix_ms:
            raise ValueError("shadow evidence evaluation time regressed")
        _require_non_negative_int(
            "event_to_decision_latency_ms",
            self.event_to_decision_latency_ms,
        )
        if (
            self.event_to_decision_latency_ms
            != self.evaluated_at_unix_ms
            - self.decision_observed_at_unix_ms
        ):
            raise ValueError("shadow evidence latency is inconsistent")
        if self.quote_state not in _QUOTE_STATES:
            raise ValueError("shadow evidence quote_state is unsupported")
        _require_non_empty("action", self.action)
        _require_non_empty("reason", self.reason)
        if self.selected_horizon_ms is not None:
            _require_positive_int(
                "selected_horizon_ms",
                self.selected_horizon_ms,
            )
        for name in (
            "current_exposure_fraction",
            "target_exposure_fraction",
            "selected_reward_bps",
            "selected_risk_bps",
            "selected_execution_cost_bps",
            "selected_value_bps",
        ):
            _require_finite(name, getattr(self, name))
        _require_sha256(
            "record_fingerprint_sha256",
            self.record_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowEvidenceLedger:
    schema_name: str
    schema_version: int
    records: tuple[FastPaperShadowDecisionEvidence, ...]
    ledger_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME:
            raise ValueError("shadow ledger schema_name is incompatible")
        if self.schema_version != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("shadow ledger schema_version is incompatible")
        if not isinstance(self.records, tuple) or not all(
            type(value) is FastPaperShadowDecisionEvidence
            for value in self.records
        ):
            raise ValueError(
                "shadow ledger records must contain exact evidence values"
            )
        expected = tuple(sorted(self.records, key=_record_sort_key))
        if self.records != expected:
            raise ValueError("shadow ledger records are not in canonical order")
        identities = tuple(value.source_event_id for value in self.records)
        if len(identities) != len(set(identities)):
            raise ValueError("shadow ledger source identities must be unique")
        for value in self.records:
            _require_record_fingerprint(value)
        _require_sha256(
            "ledger_fingerprint_sha256",
            self.ledger_fingerprint_sha256,
        )


def build_fast_paper_shadow_evidence_ledger(
    records: tuple[FastPaperShadowDecisionEvidence, ...],
) -> FastPaperShadowEvidenceLedger:
    if not isinstance(records, tuple) or not all(
        type(value) is FastPaperShadowDecisionEvidence for value in records
    ):
        raise ValueError(
            "records must be a tuple of exact FastPaperShadowDecisionEvidence"
        )
    ordered = tuple(sorted(records, key=_record_sort_key))
    identities = tuple(value.source_event_id for value in ordered)
    if len(identities) != len(set(identities)):
        raise ValueError("shadow evidence contains duplicate source identities")
    for value in ordered:
        _require_record_fingerprint(value)
    provisional = FastPaperShadowEvidenceLedger(
        schema_name=FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION,
        records=ordered,
        ledger_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        ledger_fingerprint_sha256=_ledger_fingerprint(provisional),
    )


def evaluate_fast_paper_shadow_batch(
    manifest: FastPaperRuntimeManifest,
    inputs: tuple[FastPaperShadowDecisionInput, ...],
) -> FastPaperShadowEvidenceLedger:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be an exact FastPaperRuntimeManifest")
    if not isinstance(inputs, tuple) or not inputs or not all(
        type(value) is FastPaperShadowDecisionInput for value in inputs
    ):
        raise ValueError(
            "inputs must be a non-empty tuple of exact FastPaperShadowDecisionInput"
        )
    verify_fast_paper_runtime_bindings(manifest)

    requests = tuple(
        build_fast_campaign_decision_request(
            value.record,
            value.position,
            value.constraints,
        )
        for value in inputs
    )
    batch = build_fast_campaign_decision_batch(
        manifest.action_policy,
        requests,
    )
    results = evaluate_fast_campaign_decision_batch_offline(
        binary_path=manifest.decision_binary_path,
        champion_path=manifest.champion_path,
        batch=batch,
    )
    _validate_results(manifest, requests, results)

    records = tuple(
        _evidence_from_result(manifest, source, decision)
        for source, decision in zip(
            inputs,
            results.decisions,
            strict=True,
        )
    )
    return build_fast_paper_shadow_evidence_ledger(records)


def fast_paper_shadow_record_fingerprint_sha256(
    record: FastPaperShadowDecisionEvidence,
) -> str:
    if type(record) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "record must be an exact FastPaperShadowDecisionEvidence"
        )
    document = _record_document(record)
    document.pop("record_fingerprint_sha256")
    return _sha256_canonical(document)


def fast_paper_shadow_ledger_fingerprint_sha256(
    ledger: FastPaperShadowEvidenceLedger,
) -> str:
    if type(ledger) is not FastPaperShadowEvidenceLedger:
        raise ValueError(
            "ledger must be an exact FastPaperShadowEvidenceLedger"
        )
    return _ledger_fingerprint(ledger)


def _validate_results(
    manifest: FastPaperRuntimeManifest,
    requests: tuple[Any, ...],
    results: FastCampaignDecisionResults,
) -> None:
    if type(results) is not FastCampaignDecisionResults:
        raise ValueError(
            "shadow learned result must be an exact FastCampaignDecisionResults"
        )
    if results.champion_version != manifest.champion_version:
        raise ValueError("shadow champion version mismatch")
    if (
        results.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError("shadow champion fingerprint mismatch")
    if len(results.decisions) != len(requests):
        raise ValueError("shadow result population length mismatch")

    for index, (request, decision) in enumerate(
        zip(requests, results.decisions, strict=True)
    ):
        if (
            decision.source_event_id != request.source_event_id
            or decision.market_key != request.market_key
            or decision.source_sequence != request.source_sequence
            or decision.as_of_unix_ms != request.as_of_unix_ms
        ):
            raise ValueError(
                f"shadow result identity/population mismatch at row {index}"
            )
        if decision.policy_version != manifest.action_policy.version:
            raise ValueError(
                f"shadow action policy version mismatch at row {index}"
            )


def _evidence_from_result(
    manifest: FastPaperRuntimeManifest,
    source: FastPaperShadowDecisionInput,
    decision: Any,
) -> FastPaperShadowDecisionEvidence:
    provisional = FastPaperShadowDecisionEvidence(
        schema_name=FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION,
        manifest_fingerprint_sha256=manifest.manifest_fingerprint_sha256,
        release_source_sha=manifest.release_source_sha,
        champion_version=manifest.champion_version,
        champion_fingerprint_sha256=(
            manifest.champion_fingerprint_sha256
        ),
        action_policy_version=manifest.action_policy.version,
        source_event_id=decision.source_event_id,
        source_sequence=decision.source_sequence,
        market_key=decision.market_key,
        decision_observed_at_unix_ms=decision.as_of_unix_ms,
        evaluated_at_unix_ms=source.evaluated_at_unix_ms,
        event_to_decision_latency_ms=(
            source.evaluated_at_unix_ms - decision.as_of_unix_ms
        ),
        quote_state=source.quote_state,
        action=decision.action,
        reason=decision.reason,
        selected_horizon_ms=decision.selected_horizon_ms,
        current_exposure_fraction=decision.current_exposure_fraction,
        target_exposure_fraction=decision.target_exposure_fraction,
        selected_reward_bps=decision.selected_reward_bps,
        selected_risk_bps=decision.selected_risk_bps,
        selected_execution_cost_bps=(
            decision.selected_execution_cost_bps
        ),
        selected_value_bps=decision.selected_value_bps,
        record_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        record_fingerprint_sha256=(
            fast_paper_shadow_record_fingerprint_sha256(provisional)
        ),
    )


def _require_record_fingerprint(
    record: FastPaperShadowDecisionEvidence,
) -> None:
    expected = fast_paper_shadow_record_fingerprint_sha256(record)
    if record.record_fingerprint_sha256 != expected:
        raise ValueError("shadow evidence record fingerprint mismatch")


def _ledger_fingerprint(
    ledger: FastPaperShadowEvidenceLedger,
) -> str:
    material = {
        "schema_name": ledger.schema_name,
        "schema_version": ledger.schema_version,
        "records": [_record_document(value) for value in ledger.records],
    }
    return _sha256_canonical(material)


def _record_sort_key(
    record: FastPaperShadowDecisionEvidence,
) -> tuple[int, str, int]:
    return (
        record.source_sequence,
        record.source_event_id,
        record.evaluated_at_unix_ms,
    )


def _record_document(
    record: FastPaperShadowDecisionEvidence,
) -> dict[str, object]:
    return {
        "schema_name": record.schema_name,
        "schema_version": record.schema_version,
        "manifest_fingerprint_sha256": (
            record.manifest_fingerprint_sha256
        ),
        "release_source_sha": record.release_source_sha,
        "champion_version": record.champion_version,
        "champion_fingerprint_sha256": (
            record.champion_fingerprint_sha256
        ),
        "action_policy_version": record.action_policy_version,
        "source_event_id": record.source_event_id,
        "source_sequence": record.source_sequence,
        "market_key": record.market_key,
        "decision_observed_at_unix_ms": (
            record.decision_observed_at_unix_ms
        ),
        "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
        "event_to_decision_latency_ms": (
            record.event_to_decision_latency_ms
        ),
        "quote_state": record.quote_state,
        "action": record.action,
        "reason": record.reason,
        "selected_horizon_ms": record.selected_horizon_ms,
        "current_exposure_fraction": record.current_exposure_fraction,
        "target_exposure_fraction": record.target_exposure_fraction,
        "selected_reward_bps": record.selected_reward_bps,
        "selected_risk_bps": record.selected_risk_bps,
        "selected_execution_cost_bps": (
            record.selected_execution_cost_bps
        ),
        "selected_value_bps": record.selected_value_bps,
        "record_fingerprint_sha256": (
            record.record_fingerprint_sha256
        ),
    }


def _sha256_canonical(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    import math

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 40-character source SHA")
