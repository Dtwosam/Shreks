from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .candidate_manifest import decode_fast_deterministic_candidate_manifest
from .models import FastDeterministicCandidateManifest


FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME = (
    "shreks.fast_deterministic_comparison_catalog"
)
FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION = (
    "fl9-deterministic-comparison-v1"
)

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "catalog_version",
        "candidates",
        "catalog_fingerprint_sha256",
    }
)
_EXPECTED_VERSIONS = (
    "fl9-baseline-graduation-flow-longer-runner-v1",
    "fl9-baseline-graduation-flow-wallet-cohort-v1",
    "fl9-baseline-impulse-scalp-longer-runner-v1",
    "fl9-baseline-impulse-scalp-wallet-cohort-v1",
    "fl9-baseline-micro-pullback-longer-runner-v1",
    "fl9-baseline-micro-pullback-wallet-cohort-v1",
    "fl9-baseline-pre-graduation-longer-runner-v1",
    "fl9-baseline-pre-graduation-wallet-cohort-v1",
)
_EXPECTED_PAIRS = frozenset(
    {
        ("GRADUATION_FLOW", "LONGER_RUNNER"),
        ("GRADUATION_FLOW", "WALLET_COHORT"),
        ("IMPULSE_SCALP", "LONGER_RUNNER"),
        ("IMPULSE_SCALP", "WALLET_COHORT"),
        ("MICRO_PULLBACK", "LONGER_RUNNER"),
        ("MICRO_PULLBACK", "WALLET_COHORT"),
        ("PRE_GRADUATION", "LONGER_RUNNER"),
        ("PRE_GRADUATION", "WALLET_COHORT"),
    }
)


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonCatalog:
    schema_name: str
    schema_version: int
    catalog_version: str
    candidates: tuple[FastDeterministicCandidateManifest, ...]
    catalog_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME:
            raise ValueError(
                "unsupported deterministic comparison catalog schema_name"
            )
        if self.schema_version != FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION:
            raise ValueError(
                "unsupported deterministic comparison catalog schema_version"
            )
        if self.catalog_version != FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION:
            raise ValueError(
                "unsupported deterministic comparison catalog version"
            )
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) != 8
            or not all(
                type(value) is FastDeterministicCandidateManifest
                for value in self.candidates
            )
        ):
            raise ValueError(
                "comparison catalog candidates must be eight exact manifests"
            )
        _require_sha256(
            "catalog_fingerprint_sha256",
            self.catalog_fingerprint_sha256,
        )
        versions = tuple(value.candidate_version for value in self.candidates)
        if versions != _EXPECTED_VERSIONS:
            raise ValueError(
                "comparison catalog candidate version set is incompatible"
            )
        fingerprints = tuple(
            value.candidate_fingerprint_sha256 for value in self.candidates
        )
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError(
                "comparison catalog candidate fingerprints must be unique"
            )
        pairs = frozenset(
            (
                value.lifecycle_policy.entry_baseline_kind,
                value.lifecycle_policy.manager_baseline_kind,
            )
            for value in self.candidates
        )
        if pairs != _EXPECTED_PAIRS:
            raise ValueError(
                "comparison catalog must contain the exact four-by-two family product"
            )


def decode_fast_deterministic_comparison_catalog(
    payload: str,
) -> FastDeterministicComparisonCatalog:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "deterministic comparison catalog payload must be a non-empty string"
        )
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "deterministic comparison catalog is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "deterministic comparison catalog must be a JSON object"
        )
    if payload != _canonical(document):
        raise ValueError(
            "deterministic comparison catalog must use canonical JSON"
        )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "deterministic comparison catalog has unknown or missing fields"
        )

    material = dict(document)
    claimed = material.pop("catalog_fingerprint_sha256")
    if not isinstance(claimed, str):
        raise ValueError(
            "deterministic comparison catalog fingerprint must be a string"
        )
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise ValueError(
            "deterministic comparison catalog fingerprint mismatch"
        )

    raw_candidates = document["candidates"]
    if not isinstance(raw_candidates, list) or len(raw_candidates) != 8:
        raise ValueError(
            "deterministic comparison catalog must contain exactly eight candidates"
        )
    candidates = tuple(
        decode_fast_deterministic_candidate_manifest(_canonical(value))
        for value in raw_candidates
    )

    return FastDeterministicComparisonCatalog(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        catalog_version=document["catalog_version"],
        candidates=candidates,
        catalog_fingerprint_sha256=claimed,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
