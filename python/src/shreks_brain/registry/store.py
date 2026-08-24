from __future__ import annotations

import json
import os
from pathlib import Path

from .codec import (
    build_registry,
    canonical_json,
    compute_candidate_fingerprint,
    decode_registry_document,
    registry_to_dict,
)
from .models import ChampionChallengerRegistry, RegistryCandidate


class RegistryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.name:
            raise ValueError("registry path must name a file")

    def load(self) -> ChampionChallengerRegistry:
        if not self.path.exists():
            return build_registry((), ())
        try:
            raw = self.path.read_text(encoding="utf-8")
            document = json.loads(raw)
            return decode_registry_document(document)
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            raise ValueError(f"registry file is invalid: {error}") from error

    def register(self, candidate: RegistryCandidate) -> ChampionChallengerRegistry:
        if type(candidate) is not RegistryCandidate:
            raise ValueError("candidate must be an exact RegistryCandidate")
        actual_candidate_fingerprint = compute_candidate_fingerprint(candidate)
        if actual_candidate_fingerprint != candidate.candidate_fingerprint_sha256:
            raise ValueError("candidate fingerprint does not match candidate content")

        current = self.load()
        existing = next(
            (
                value
                for value in current.candidates
                if value.candidate_version == candidate.candidate_version
            ),
            None,
        )
        if existing is not None:
            if existing == candidate:
                return current
            raise ValueError(
                f"candidate version '{candidate.candidate_version}' is already registered with different content"
            )

        updated = build_registry(current.candidates + (candidate,), current.status_events)
        self._write(updated)
        return updated

    def _write(self, registry: ChampionChallengerRegistry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = canonical_json(registry_to_dict(registry)) + "\n"
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
