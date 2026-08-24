from __future__ import annotations

import json
import os
from pathlib import Path

from .codec import build_ledger, decode_ledger_document, ledger_to_dict
from .fingerprint import record_fingerprint
from .models import ShadowDecisionRecord, ShadowEvidenceLedger


class ShadowEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("shadow evidence path must name a file")

    def load(self) -> ShadowEvidenceLedger:
        if not self.path.exists():
            return build_ledger(())
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_ledger_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"shadow evidence file is invalid: {error}") from error

    def append(self, record: ShadowDecisionRecord) -> ShadowEvidenceLedger:
        if type(record) is not ShadowDecisionRecord:
            raise ValueError("record must be an exact ShadowDecisionRecord")
        if record.record_fingerprint_sha256 != record_fingerprint(record):
            raise ValueError("record fingerprint does not match record content")

        current = self.load()
        identity = _decision_identity(record)
        for existing in current.records:
            if _decision_identity(existing) == identity:
                if existing == record:
                    return current
                raise ValueError(
                    "decision identity is already recorded with different content"
                )

        updated = build_ledger(current.records + (record,))
        self._write(updated)
        return updated

    def _write(self, ledger: ShadowEvidenceLedger) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = json.dumps(
            ledger_to_dict(ledger),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def _decision_identity(record: ShadowDecisionRecord) -> tuple[str, str, int, str]:
    return (
        record.candidate_version,
        record.candidate_mint,
        record.as_of_unix_ms,
        record.shadow_policy_version,
    )
