from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path

from .codec import (
    build_registry,
    canonical_json,
    compute_candidate_fingerprint,
    compute_event_fingerprint,
    decode_registry_document,
    registry_to_dict,
)
from .models import (
    ChampionChallengerRegistry,
    RegistryCandidate,
    RegistryStatus,
    RegistryStatusEvent,
)


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

    def record_status(
        self,
        *,
        candidate_version: str,
        to_status: RegistryStatus,
        decision_reference: str,
        decided_at_unix_ms: int,
        reason: str,
    ) -> ChampionChallengerRegistry:
        current = self.load()
        candidate = next(
            (
                value
                for value in current.candidates
                if value.candidate_version == candidate_version
            ),
            None,
        )
        if candidate is None:
            raise ValueError(f"candidate '{candidate_version}' is not registered")

        from_status = current.current_status(candidate_version)
        draft = RegistryStatusEvent(
            candidate_version=candidate_version,
            from_status=from_status,
            to_status=to_status,
            decision_reference=decision_reference,
            decided_at_unix_ms=decided_at_unix_ms,
            reason=reason,
            event_fingerprint_sha256="0" * 64,
        )
        event = replace(
            draft,
            event_fingerprint_sha256=compute_event_fingerprint(draft),
        )
        return self.record_status_event(event)

    def record_status_event(
        self, event: RegistryStatusEvent
    ) -> ChampionChallengerRegistry:
        if type(event) is not RegistryStatusEvent:
            raise ValueError("event must be an exact RegistryStatusEvent")
        actual_event_fingerprint = compute_event_fingerprint(event)
        if actual_event_fingerprint != event.event_fingerprint_sha256:
            raise ValueError("status event fingerprint does not match event content")

        current = self.load()
        candidate = next(
            (
                value
                for value in current.candidates
                if value.candidate_version == event.candidate_version
            ),
            None,
        )
        if candidate is None:
            raise ValueError(
                f"candidate '{event.candidate_version}' is not registered"
            )

        identity = (
            event.candidate_version,
            event.decision_reference,
            event.decided_at_unix_ms,
        )
        for existing in current.status_events:
            existing_identity = (
                existing.candidate_version,
                existing.decision_reference,
                existing.decided_at_unix_ms,
            )
            if existing_identity == identity:
                if existing == event:
                    return current
                raise ValueError("status event identity is already recorded with different content")

        if event.decided_at_unix_ms < candidate.registered_at_unix_ms:
            raise ValueError("status event cannot precede candidate registration")
        current_status = current.current_status(event.candidate_version)
        if event.from_status is not current_status:
            raise ValueError("status event from_status must match reconstructed current status")
        if event.to_status is RegistryStatus.CHAMPION:
            champion = current.current_champion()
            if champion is not None and champion.candidate_version != event.candidate_version:
                raise ValueError("registry may contain at most one current champion")

        updated = build_registry(
            current.candidates,
            current.status_events + (event,),
        )
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
