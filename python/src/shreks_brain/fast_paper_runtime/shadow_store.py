from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .models import FastPaperRuntimeManifest
from .shadow import (
    FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION,
    FastPaperShadowDecisionEvidence,
    FastPaperShadowEvidenceLedger,
    build_fast_paper_shadow_evidence_ledger,
    fast_paper_shadow_record_fingerprint_sha256,
)


class FastPaperShadowEvidenceStore:
    def __init__(
        self,
        path: str | Path,
        *,
        manifest: FastPaperRuntimeManifest,
    ) -> None:
        if type(manifest) is not FastPaperRuntimeManifest:
            raise ValueError(
                "manifest must be an exact FastPaperRuntimeManifest"
            )
        self.path = _normalized_path(path)
        if not self.path.name:
            raise ValueError("shadow evidence path must name a file")

        authoritative = {
            _normalized_path(manifest.paper_evidence_path),
            _normalized_path(manifest.checkpoint_path),
        }
        if self.path in authoritative:
            raise ValueError(
                "shadow evidence path must not target authoritative PAPER state"
            )

    def load(self) -> FastPaperShadowEvidenceLedger:
        if self.path.is_symlink():
            raise ValueError("shadow evidence path must not be a symlink")
        if not self.path.exists():
            return build_fast_paper_shadow_evidence_ledger(())
        if not self.path.is_file():
            raise ValueError(
                "shadow evidence source must be a regular file"
            )
        try:
            payload = self.path.read_text(encoding="utf-8")
            document = json.loads(
                payload,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("shadow evidence file is invalid") from exc
        if not isinstance(document, dict):
            raise ValueError("shadow evidence file must contain an object")
        if payload != _canonical(document):
            raise ValueError("shadow evidence file must use canonical JSON")
        return _decode_ledger(document)

    def append(
        self,
        record: FastPaperShadowDecisionEvidence,
    ) -> FastPaperShadowEvidenceLedger:
        if type(record) is not FastPaperShadowDecisionEvidence:
            raise ValueError(
                "record must be an exact FastPaperShadowDecisionEvidence"
            )
        if (
            record.record_fingerprint_sha256
            != fast_paper_shadow_record_fingerprint_sha256(record)
        ):
            raise ValueError("shadow evidence record fingerprint mismatch")

        current = self.load()
        existing = next(
            (
                value
                for value in current.records
                if value.source_event_id == record.source_event_id
            ),
            None,
        )
        if existing is not None:
            if existing == record:
                return current
            raise ValueError(
                "shadow evidence source identity conflicts with existing record"
            )

        updated = build_fast_paper_shadow_evidence_ledger(
            (*current.records, record)
        )
        self._write(updated)
        return updated

    def append_ledger(
        self,
        incoming: FastPaperShadowEvidenceLedger,
    ) -> FastPaperShadowEvidenceLedger:
        if type(incoming) is not FastPaperShadowEvidenceLedger:
            raise ValueError(
                "incoming must be an exact FastPaperShadowEvidenceLedger"
            )
        result = self.load()
        for record in incoming.records:
            result = self.append(record)
        return result

    def _write(self, ledger: FastPaperShadowEvidenceLedger) -> None:
        if self.path.is_symlink():
            raise ValueError("shadow evidence destination must not be a symlink")
        if self.path.exists() and not self.path.is_file():
            raise ValueError(
                "shadow evidence destination must be a regular file"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_name": ledger.schema_name,
            "schema_version": ledger.schema_version,
            "records": [_record_document(value) for value in ledger.records],
            "ledger_fingerprint_sha256": (
                ledger.ledger_fingerprint_sha256
            ),
        }
        encoded = _canonical(document).encode("utf-8")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.tmp-",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.is_symlink():
                raise ValueError(
                    "shadow evidence destination became a symlink"
                )
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        except Exception:
            if fd >= 0:
                os.close(fd)
            temporary.unlink(missing_ok=True)
            raise


def _decode_ledger(document: dict[str, Any]) -> FastPaperShadowEvidenceLedger:
    expected = {
        "schema_name",
        "schema_version",
        "records",
        "ledger_fingerprint_sha256",
    }
    if set(document) != expected:
        raise ValueError("shadow evidence ledger has unknown or missing fields")
    if document["schema_name"] != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME:
        raise ValueError("shadow evidence ledger schema_name is incompatible")
    if document["schema_version"] != FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("shadow evidence ledger schema_version is incompatible")
    raw_records = document["records"]
    if not isinstance(raw_records, list):
        raise ValueError("shadow evidence records must be a list")
    records = tuple(_decode_record(value) for value in raw_records)
    ledger = build_fast_paper_shadow_evidence_ledger(records)
    if ledger.ledger_fingerprint_sha256 != document[
        "ledger_fingerprint_sha256"
    ]:
        raise ValueError("shadow evidence ledger fingerprint mismatch")
    return ledger


def _decode_record(value: object) -> FastPaperShadowDecisionEvidence:
    if not isinstance(value, dict):
        raise ValueError("shadow evidence record must be an object")
    expected = {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "release_source_sha",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "source_event_id",
        "source_sequence",
        "market_key",
        "decision_observed_at_unix_ms",
        "evaluated_at_unix_ms",
        "event_to_decision_latency_ms",
        "quote_state",
        "action",
        "reason",
        "selected_horizon_ms",
        "current_exposure_fraction",
        "target_exposure_fraction",
        "selected_reward_bps",
        "selected_risk_bps",
        "selected_execution_cost_bps",
        "selected_value_bps",
        "record_fingerprint_sha256",
    }
    if set(value) != expected:
        raise ValueError("shadow evidence record has unknown or missing fields")
    try:
        record = FastPaperShadowDecisionEvidence(**value)
    except (TypeError, ValueError) as exc:
        raise ValueError("shadow evidence record is incompatible") from exc
    if (
        record.record_fingerprint_sha256
        != fast_paper_shadow_record_fingerprint_sha256(record)
    ):
        raise ValueError("shadow evidence record fingerprint mismatch")
    return record


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


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _normalized_path(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)):
        raise ValueError("shadow evidence path must be string or Path")
    if isinstance(path, str) and not path.strip():
        raise ValueError("shadow evidence path must be non-empty")
    return Path(path).expanduser().resolve(strict=False)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
