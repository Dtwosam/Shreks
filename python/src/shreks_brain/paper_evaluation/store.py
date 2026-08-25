from __future__ import annotations

import json
import os
from pathlib import Path

from .codec import (
    build_paper_evaluation_ledger,
    decode_paper_evaluation_document,
    encode_paper_evaluation_ledger,
)
from .engine import build_evaluated_trades, extract_paper_evaluation_evidence
from .models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationCapture,
    PaperEvaluationLedger,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)


class PaperEvaluationEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("paper evaluation evidence path must name a file")

    def load(self) -> PaperEvaluationLedger:
        if not self.path.exists():
            return build_paper_evaluation_ledger((), (), (), ())
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_paper_evaluation_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"paper evaluation evidence file is invalid: {error}") from error

    def record_capture(self, capture: PaperEvaluationCapture) -> PaperEvaluationLedger:
        if type(capture) is not PaperEvaluationCapture:
            raise ValueError("capture must be an exact PaperEvaluationCapture")
        current = self.load()
        _require_run_attribution_coherent(current, capture)

        entries = _merge_collection(
            current.entry_provenance,
            capture.entry_provenance,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            "entry provenance",
        )
        executions = _merge_collection(
            current.executions,
            capture.executions,
            lambda value: (value.paper_run_id, value.ledger_sequence),
            "execution evidence",
        )
        closures = _merge_collection(
            current.closures,
            capture.closures,
            lambda value: (value.paper_run_id, value.position_id),
            "closure evidence",
        )
        orphan_costs = _merge_collection(
            current.orphan_costs,
            capture.orphan_costs,
            lambda value: (value.paper_run_id, value.intent_idempotency_key),
            "orphan cost evidence",
        )
        updated = build_paper_evaluation_ledger(
            entries,  # type: ignore[arg-type]
            executions,  # type: ignore[arg-type]
            closures,  # type: ignore[arg-type]
            orphan_costs,  # type: ignore[arg-type]
        )
        if updated == current:
            return current
        self._write(updated)
        return updated

    def record_cycle(self, paper_run_id, candidate, cycle) -> PaperEvaluationLedger:
        capture = extract_paper_evaluation_evidence(paper_run_id, candidate, cycle)
        return self.record_capture(capture)

    def evaluated_trades(self, paper_run_id: str, candidate_version: str):
        ledger = self.load()
        return build_evaluated_trades(
            paper_run_id,
            candidate_version,
            ledger.entry_provenance,
            ledger.executions,
            ledger.closures,
            ledger.orphan_costs,
        )

    def _write(self, ledger: PaperEvaluationLedger) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = encode_paper_evaluation_ledger(ledger)
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


def _merge_collection(current, incoming, identity_key, label: str):
    by_identity = {identity_key(value): value for value in current}
    merged = list(current)
    for value in incoming:
        identity = identity_key(value)
        existing = by_identity.get(identity)
        if existing is not None:
            if existing != value:
                raise ValueError(
                    f"{label} identity is already stored with different content"
                )
            continue
        by_identity[identity] = value
        merged.append(value)
    return tuple(merged)


def _require_run_attribution_coherent(
    ledger: PaperEvaluationLedger,
    capture: PaperEvaluationCapture,
) -> None:
    existing = (
        ledger.entry_provenance
        + ledger.executions
        + ledger.closures
        + ledger.orphan_costs
    )
    for value in existing:
        if value.paper_run_id != capture.paper_run_id:
            continue
        if (
            value.candidate_version != capture.candidate_version
            or value.candidate_fingerprint_sha256
            != capture.candidate_fingerprint_sha256
            or value.strategy_version != capture.strategy_version
        ):
            raise ValueError(
                "paper run is already stored with different candidate attribution"
            )
