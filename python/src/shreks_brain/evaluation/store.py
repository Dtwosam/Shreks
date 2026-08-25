from __future__ import annotations

import json
import os
from pathlib import Path
import string

from .codec import (
    build_evidence,
    build_evidence_document,
    canonical_json,
    decode_evidence_document,
)
from .models import EvaluatedTrade, ProbabilityObservation, TradingEvaluationPolicy
from .evidence import TradingEvaluationEvidence


class TradingEvaluationEvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("evaluation evidence path must name a file")

    def load(self) -> tuple[TradingEvaluationEvidence, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_evidence_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"evaluation evidence file is invalid: {error}") from error

    def get(
        self,
        candidate_version: str,
        evaluation_fingerprint_sha256: str,
    ) -> TradingEvaluationEvidence | None:
        _require_candidate_version(candidate_version)
        _require_sha256(
            "evaluation_fingerprint_sha256", evaluation_fingerprint_sha256
        )
        for evidence in self.load():
            if (
                evidence.candidate_version == candidate_version
                and evidence.report.evaluation_fingerprint_sha256
                == evaluation_fingerprint_sha256
            ):
                return evidence
        return None

    def append(
        self,
        candidate_version: str,
        trades: tuple[EvaluatedTrade, ...],
        probability_observations: tuple[ProbabilityObservation, ...],
        policy: TradingEvaluationPolicy,
    ) -> tuple[TradingEvaluationEvidence, ...]:
        _require_candidate_version(candidate_version)
        if not isinstance(trades, tuple) or any(
            type(trade) is not EvaluatedTrade for trade in trades
        ):
            raise ValueError("trades must be a tuple of exact EvaluatedTrade values")
        if not isinstance(probability_observations, tuple) or any(
            type(observation) is not ProbabilityObservation
            for observation in probability_observations
        ):
            raise ValueError(
                "probability_observations must be a tuple of exact ProbabilityObservation values"
            )
        if type(policy) is not TradingEvaluationPolicy:
            raise ValueError("policy must be an exact TradingEvaluationPolicy")

        evidence = build_evidence(
            candidate_version,
            trades,
            probability_observations,
            policy,
        )
        identity = (
            evidence.candidate_version,
            evidence.report.evaluation_fingerprint_sha256,
        )

        current = self.load()
        for existing in current:
            existing_identity = (
                existing.candidate_version,
                existing.report.evaluation_fingerprint_sha256,
            )
            if existing_identity == identity:
                if existing == evidence:
                    return current
                raise ValueError(
                    "evaluation identity is already stored with different source content"
                )

        updated = current + (evidence,)
        self._write(updated)
        return updated

    def _write(self, evidence_values: tuple[TradingEvaluationEvidence, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = canonical_json(build_evidence_document(evidence_values)) + "\n"
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


def _require_candidate_version(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("candidate_version must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(
            f"{name} must be a 64-character lowercase SHA-256 hex digest"
        )
