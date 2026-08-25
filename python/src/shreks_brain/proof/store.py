from __future__ import annotations

import json
import os
from pathlib import Path

from .codec import (
    assessment_identity,
    assessment_sort_key,
    compute_assessment_fingerprint,
    decode_assessments_document,
    encode_assessments,
)
from .models import CandidateProofAssessment


class CandidateProofAssessmentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("proof assessment path must name a file")

    def load(self) -> tuple[CandidateProofAssessment, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_assessments_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"proof assessment file is invalid: {error}") from error

    def append(
        self,
        assessment: CandidateProofAssessment,
    ) -> tuple[CandidateProofAssessment, ...]:
        if type(assessment) is not CandidateProofAssessment:
            raise ValueError("assessment must be an exact CandidateProofAssessment")
        if assessment.assessment_fingerprint_sha256 != compute_assessment_fingerprint(
            assessment
        ):
            raise ValueError("assessment fingerprint does not match assessment content")

        current = self.load()
        identity = assessment_identity(assessment)
        for existing in current:
            if assessment_identity(existing) == identity:
                if existing == assessment:
                    return current
                raise ValueError(
                    "assessment identity is already recorded with different content"
                )

        updated = tuple(sorted(current + (assessment,), key=assessment_sort_key))
        self._write(updated)
        return updated

    def _write(self, assessments: tuple[CandidateProofAssessment, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = encode_assessments(assessments)
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
