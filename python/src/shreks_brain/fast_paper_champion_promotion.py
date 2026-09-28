from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Iterator, Mapping

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_shadow_promotion_readiness import (
    FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_NAME,
    FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_VERSION,
)


FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_NAME = "shreks.fast_paper_champion_registry"
FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_VERSION = 1
FAST_PAPER_CHAMPION_PROMOTION_RECEIPT_SCHEMA_NAME = (
    "shreks.fast_paper_champion_promotion_receipt"
)
FAST_PAPER_CHAMPION_PROMOTION_RECEIPT_SCHEMA_VERSION = 1

_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_READINESS_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy_version",
        "policy_fingerprint_sha256",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "binding_fingerprint_sha256",
        "window_since_unix_ms",
        "window_until_unix_ms",
        "window_duration_ms",
        "sample_proof_fingerprint_sha256",
        "trade_economics_report_fingerprint_sha256",
        "missed_opportunity_report_fingerprint_sha256",
        "latency_proof_report_fingerprint_sha256",
        "observed_metrics",
        "gate_results",
        "decision",
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "report_fingerprint_sha256",
    }
)

_REGISTRY_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "revision",
        "current_champion_version",
        "current_champion_fingerprint_sha256",
        "transitions",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "registry_fingerprint_sha256",
    }
)

_TRANSITION_FIELDS = frozenset(
    {
        "sequence",
        "decision_reference",
        "readiness_policy_version",
        "readiness_policy_fingerprint_sha256",
        "release_source_sha",
        "shadow_manifest_fingerprint_sha256",
        "shadow_binding_fingerprint_sha256",
        "action_policy_version",
        "window_since_unix_ms",
        "window_until_unix_ms",
        "candidate_champion_version",
        "candidate_champion_fingerprint_sha256",
        "previous_champion_version",
        "previous_champion_fingerprint_sha256",
        "decided_at_unix_ms",
        "reason",
        "transition_fingerprint_sha256",
    }
)


class FastPaperChampionPromotionError(RuntimeError):
    pass


def preflight_fast_paper_champion_promotion(
    *,
    manifest_path: str | Path,
    readiness_path: str | Path,
    registry_path: str | Path,
    expected_release_sha: str,
    expected_current_champion_fingerprint: str | None,
) -> dict[str, object]:
    candidate = _authenticate_candidate(
        manifest_path=manifest_path,
        readiness_path=readiness_path,
        expected_release_sha=expected_release_sha,
    )
    registry = _read_optional_registry(registry_path)
    state = _plan_state(
        candidate=candidate,
        registry=registry,
        expected_current_champion_fingerprint=(
            expected_current_champion_fingerprint
        ),
    )
    return _receipt(
        state=state,
        candidate=candidate,
        registry=registry,
        registry_after=None,
    )


def promote_fast_paper_champion(
    *,
    manifest_path: str | Path,
    readiness_path: str | Path,
    registry_path: str | Path,
    expected_release_sha: str,
    expected_current_champion_fingerprint: str | None,
    decided_at_unix_ms: int,
    reason: str,
) -> dict[str, object]:
    decided_at = _non_negative_int(
        decided_at_unix_ms,
        "decided_at_unix_ms",
    )
    if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
        raise FastPaperChampionPromotionError(
            "promotion reason must be non-empty trimmed text"
        )

    destination = Path(registry_path).expanduser()
    parent = _safe_parent(destination)
    with _exclusive_lock(destination, parent):
        candidate = _authenticate_candidate(
            manifest_path=manifest_path,
            readiness_path=readiness_path,
            expected_release_sha=expected_release_sha,
        )
        registry = _read_optional_registry(destination)
        state = _plan_state(
            candidate=candidate,
            registry=registry,
            expected_current_champion_fingerprint=(
                expected_current_champion_fingerprint
            ),
        )
        if state == "ALREADY_CURRENT":
            return _receipt(
                state=state,
                candidate=candidate,
                registry=registry,
                registry_after=registry,
            )

        next_registry = _next_registry(
            candidate=candidate,
            registry=registry,
            decided_at_unix_ms=decided_at,
            reason=reason,
        )
        _atomic_publish_registry(destination, next_registry, parent)
        published = read_fast_paper_champion_registry(destination)
        if (
            published["registry_fingerprint_sha256"]
            != next_registry["registry_fingerprint_sha256"]
        ):
            raise FastPaperChampionPromotionError(
                "published champion registry readback fingerprint mismatch"
            )
        return _receipt(
            state="PROMOTED",
            candidate=candidate,
            registry=registry,
            registry_after=published,
        )


def read_fast_paper_champion_registry(
    path: str | Path,
) -> dict[str, object]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperChampionPromotionError(
            "champion registry must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FastPaperChampionPromotionError(
            "champion registry read failed"
        ) from exc
    return _decode_registry(payload)


def canonical_fast_paper_champion_registry(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperChampionPromotionError(
            "champion registry document must be a mapping"
        )
    try:
        return _canonical(dict(document))
    except (TypeError, ValueError) as exc:
        raise FastPaperChampionPromotionError(
            "champion registry document is not canonicalizable"
        ) from exc


def _authenticate_candidate(
    *,
    manifest_path: str | Path,
    readiness_path: str | Path,
    expected_release_sha: str,
) -> dict[str, object]:
    expected_sha = _release_sha(expected_release_sha)
    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperChampionPromotionError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperChampionPromotionError(
            "Fast PAPER runtime manifest release identity mismatch"
        )

    readiness = _read_readiness(readiness_path)
    if readiness["decision"] != "PROMOTION_READY":
        raise FastPaperChampionPromotionError(
            "champion promotion requires FL11.4 PROMOTION_READY"
        )
    gates = readiness["gate_results"]
    if not isinstance(gates, list) or not gates:
        raise FastPaperChampionPromotionError(
            "promotion readiness gate results must be a non-empty list"
        )
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("status") != "PASS":
            raise FastPaperChampionPromotionError(
                "PROMOTION_READY readiness must contain only PASS gates"
            )
    _require_readiness_authority(readiness)

    expected_identity = {
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
    }
    for name, expected in expected_identity.items():
        if readiness.get(name) != expected:
            raise FastPaperChampionPromotionError(
                f"promotion readiness {name} mismatch"
            )

    return {
        "readiness_report_fingerprint_sha256": readiness[
            "report_fingerprint_sha256"
        ],
        "readiness_policy_version": readiness["policy_version"],
        "readiness_policy_fingerprint_sha256": readiness[
            "policy_fingerprint_sha256"
        ],
        "release_source_sha": readiness["release_source_sha"],
        "shadow_manifest_fingerprint_sha256": readiness[
            "manifest_fingerprint_sha256"
        ],
        "shadow_binding_fingerprint_sha256": readiness[
            "binding_fingerprint_sha256"
        ],
        "action_policy_version": readiness["action_policy_version"],
        "window_since_unix_ms": readiness["window_since_unix_ms"],
        "window_until_unix_ms": readiness["window_until_unix_ms"],
        "candidate_champion_version": readiness["champion_version"],
        "candidate_champion_fingerprint_sha256": readiness[
            "champion_fingerprint_sha256"
        ],
    }


def _read_readiness(path: str | Path) -> dict[str, object]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperChampionPromotionError(
            "promotion readiness source must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        document = _decode_canonical_json(payload, "promotion readiness")
    except (OSError, UnicodeError, ValueError) as exc:
        raise FastPaperChampionPromotionError(
            "promotion readiness is malformed or non-canonical"
        ) from exc
    if frozenset(document) != _READINESS_FIELDS:
        raise FastPaperChampionPromotionError(
            "promotion readiness has unknown or missing fields"
        )
    if (
        document.get("schema_name")
        != FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_NAME
        or document.get("schema_version")
        != FAST_PAPER_SHADOW_PROMOTION_READINESS_SCHEMA_VERSION
    ):
        raise FastPaperChampionPromotionError(
            "promotion readiness schema is incompatible"
        )
    fingerprint = document.get("report_fingerprint_sha256")
    _sha256(fingerprint, "promotion readiness report fingerprint")
    material = dict(document)
    material.pop("report_fingerprint_sha256", None)
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if fingerprint != expected:
        raise FastPaperChampionPromotionError(
            "promotion readiness report fingerprint mismatch"
        )

    for name in (
        "policy_fingerprint_sha256",
        "manifest_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "sample_proof_fingerprint_sha256",
        "trade_economics_report_fingerprint_sha256",
        "missed_opportunity_report_fingerprint_sha256",
        "latency_proof_report_fingerprint_sha256",
    ):
        _sha256(document.get(name), f"promotion readiness {name}")
    _release_sha(document.get("release_source_sha"))
    for name in (
        "policy_version",
        "champion_version",
        "action_policy_version",
        "decision",
    ):
        _non_empty(document.get(name), f"promotion readiness {name}")
    since = _non_negative_int(
        document.get("window_since_unix_ms"),
        "promotion readiness window_since_unix_ms",
    )
    until = _non_negative_int(
        document.get("window_until_unix_ms"),
        "promotion readiness window_until_unix_ms",
    )
    duration = _non_negative_int(
        document.get("window_duration_ms"),
        "promotion readiness window_duration_ms",
    )
    if until <= since or duration != until - since:
        raise FastPaperChampionPromotionError(
            "promotion readiness window is inconsistent"
        )
    if not isinstance(document.get("observed_metrics"), dict):
        raise FastPaperChampionPromotionError(
            "promotion readiness observed_metrics must be an object"
        )
    return document


def _require_readiness_authority(
    readiness: Mapping[str, object],
) -> None:
    for name in (
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
    ):
        if readiness.get(name) != "NOT_GRANTED":
            raise FastPaperChampionPromotionError(
                f"promotion readiness {name} boundary is incompatible"
            )
    if readiness.get("live_authority") != "DISABLED":
        raise FastPaperChampionPromotionError(
            "promotion readiness live authority boundary is incompatible"
        )


def _read_optional_registry(
    path: str | Path,
) -> dict[str, object] | None:
    source = Path(path).expanduser()
    if source.is_symlink():
        raise FastPaperChampionPromotionError(
            "champion registry destination must not be a symlink"
        )
    if not source.exists():
        return None
    if not source.is_file():
        raise FastPaperChampionPromotionError(
            "champion registry destination must be a regular file"
        )
    return read_fast_paper_champion_registry(source)


def _plan_state(
    *,
    candidate: Mapping[str, object],
    registry: Mapping[str, object] | None,
    expected_current_champion_fingerprint: str | None,
) -> str:
    expected = _optional_sha256(
        expected_current_champion_fingerprint,
        "expected incumbent champion fingerprint",
    )
    candidate_fingerprint = candidate[
        "candidate_champion_fingerprint_sha256"
    ]
    decision_reference = candidate[
        "readiness_report_fingerprint_sha256"
    ]

    if registry is None:
        if expected is not None:
            raise FastPaperChampionPromotionError(
                "expected incumbent champion fingerprint supplied for empty registry"
            )
        return "READY_TO_PROMOTE"

    current = registry["current_champion_fingerprint_sha256"]
    if current == candidate_fingerprint:
        if expected is not None and expected != current:
            raise FastPaperChampionPromotionError(
                "incumbent champion fingerprint mismatch"
            )
        return "ALREADY_CURRENT"

    transitions = registry["transitions"]
    assert isinstance(transitions, list)
    if any(
        transition["decision_reference"] == decision_reference
        for transition in transitions
    ):
        raise FastPaperChampionPromotionError(
            "promotion readiness decision reference was already consumed"
        )

    if expected is None:
        raise FastPaperChampionPromotionError(
            "expected incumbent champion fingerprint is required for replacement"
        )
    if expected != current:
        raise FastPaperChampionPromotionError(
            "incumbent champion fingerprint mismatch"
        )
    return "READY_TO_PROMOTE"


def _next_registry(
    *,
    candidate: Mapping[str, object],
    registry: Mapping[str, object] | None,
    decided_at_unix_ms: int,
    reason: str,
) -> dict[str, object]:
    if registry is None:
        revision = 1
        transitions: list[dict[str, object]] = []
        previous_version = None
        previous_fingerprint = None
    else:
        revision = int(registry["revision"]) + 1
        transitions = [
            dict(value)
            for value in registry["transitions"]  # type: ignore[arg-type]
        ]
        previous_version = registry["current_champion_version"]
        previous_fingerprint = registry[
            "current_champion_fingerprint_sha256"
        ]
        previous_decided_at = transitions[-1]["decided_at_unix_ms"]
        if decided_at_unix_ms < previous_decided_at:
            raise FastPaperChampionPromotionError(
                "promotion decision time cannot precede prior transition"
            )

    transition_material: dict[str, object] = {
        "sequence": revision,
        "decision_reference": candidate[
            "readiness_report_fingerprint_sha256"
        ],
        "readiness_policy_version": candidate[
            "readiness_policy_version"
        ],
        "readiness_policy_fingerprint_sha256": candidate[
            "readiness_policy_fingerprint_sha256"
        ],
        "release_source_sha": candidate["release_source_sha"],
        "shadow_manifest_fingerprint_sha256": candidate[
            "shadow_manifest_fingerprint_sha256"
        ],
        "shadow_binding_fingerprint_sha256": candidate[
            "shadow_binding_fingerprint_sha256"
        ],
        "action_policy_version": candidate["action_policy_version"],
        "window_since_unix_ms": candidate["window_since_unix_ms"],
        "window_until_unix_ms": candidate["window_until_unix_ms"],
        "candidate_champion_version": candidate[
            "candidate_champion_version"
        ],
        "candidate_champion_fingerprint_sha256": candidate[
            "candidate_champion_fingerprint_sha256"
        ],
        "previous_champion_version": previous_version,
        "previous_champion_fingerprint_sha256": previous_fingerprint,
        "decided_at_unix_ms": decided_at_unix_ms,
        "reason": reason,
    }
    transition = {
        **transition_material,
        "transition_fingerprint_sha256": hashlib.sha256(
            _canonical(transition_material).encode("utf-8")
        ).hexdigest(),
    }
    transitions.append(transition)

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_NAME,
        "schema_version": FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_VERSION,
        "revision": revision,
        "current_champion_version": candidate[
            "candidate_champion_version"
        ],
        "current_champion_fingerprint_sha256": candidate[
            "candidate_champion_fingerprint_sha256"
        ],
        "transitions": transitions,
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return {
        **material,
        "registry_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _decode_registry(payload: str) -> dict[str, object]:
    try:
        document = _decode_canonical_json(payload, "champion registry")
    except ValueError as exc:
        raise FastPaperChampionPromotionError(
            "champion registry is malformed or non-canonical"
        ) from exc
    if frozenset(document) != _REGISTRY_FIELDS:
        raise FastPaperChampionPromotionError(
            "champion registry has unknown or missing fields"
        )
    if (
        document.get("schema_name")
        != FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_NAME
        or document.get("schema_version")
        != FAST_PAPER_CHAMPION_REGISTRY_SCHEMA_VERSION
    ):
        raise FastPaperChampionPromotionError(
            "champion registry schema is incompatible"
        )

    revision = _positive_int(
        document.get("revision"),
        "champion registry revision",
    )
    current_version = _non_empty(
        document.get("current_champion_version"),
        "champion registry current champion version",
    )
    current_fingerprint = _sha256(
        document.get("current_champion_fingerprint_sha256"),
        "champion registry current champion fingerprint",
    )
    transitions = document.get("transitions")
    if not isinstance(transitions, list) or len(transitions) != revision:
        raise FastPaperChampionPromotionError(
            "champion registry transitions must reconcile to revision"
        )
    if not transitions:
        raise FastPaperChampionPromotionError(
            "champion registry must contain promotion history"
        )

    seen_decisions: set[str] = set()
    previous_candidate_version: str | None = None
    previous_candidate_fingerprint: str | None = None
    previous_decided_at: int | None = None
    validated: list[dict[str, object]] = []
    for index, raw in enumerate(transitions, start=1):
        if not isinstance(raw, dict) or frozenset(raw) != _TRANSITION_FIELDS:
            raise FastPaperChampionPromotionError(
                "champion transition has unknown or missing fields"
            )
        transition = dict(raw)
        if transition.get("sequence") != index:
            raise FastPaperChampionPromotionError(
                "champion transition sequence is not contiguous"
            )
        claimed = _sha256(
            transition.get("transition_fingerprint_sha256"),
            "champion transition fingerprint",
        )
        transition_material = dict(transition)
        transition_material.pop("transition_fingerprint_sha256", None)
        expected = hashlib.sha256(
            _canonical(transition_material).encode("utf-8")
        ).hexdigest()
        if claimed != expected:
            raise FastPaperChampionPromotionError(
                "champion transition fingerprint mismatch"
            )

        decision_reference = _sha256(
            transition.get("decision_reference"),
            "champion transition decision reference",
        )
        if decision_reference in seen_decisions:
            raise FastPaperChampionPromotionError(
                "champion registry reuses a promotion decision reference"
            )
        seen_decisions.add(decision_reference)

        _non_empty(
            transition.get("readiness_policy_version"),
            "champion transition readiness policy version",
        )
        _sha256(
            transition.get("readiness_policy_fingerprint_sha256"),
            "champion transition readiness policy fingerprint",
        )
        _release_sha(transition.get("release_source_sha"))
        for name in (
            "shadow_manifest_fingerprint_sha256",
            "shadow_binding_fingerprint_sha256",
        ):
            _sha256(
                transition.get(name),
                f"champion transition {name}",
            )
        _non_empty(
            transition.get("action_policy_version"),
            "champion transition action policy version",
        )
        since = _non_negative_int(
            transition.get("window_since_unix_ms"),
            "champion transition window start",
        )
        until = _non_negative_int(
            transition.get("window_until_unix_ms"),
            "champion transition window end",
        )
        if until <= since:
            raise FastPaperChampionPromotionError(
                "champion transition evidence window is invalid"
            )
        candidate_version = _non_empty(
            transition.get("candidate_champion_version"),
            "champion transition candidate version",
        )
        candidate_fingerprint = _sha256(
            transition.get("candidate_champion_fingerprint_sha256"),
            "champion transition candidate fingerprint",
        )
        decided_at = _non_negative_int(
            transition.get("decided_at_unix_ms"),
            "champion transition decision time",
        )
        _non_empty(
            transition.get("reason"),
            "champion transition reason",
        )

        prior_version = transition.get("previous_champion_version")
        prior_fingerprint = transition.get(
            "previous_champion_fingerprint_sha256"
        )
        if index == 1:
            if prior_version is not None or prior_fingerprint is not None:
                raise FastPaperChampionPromotionError(
                    "first champion transition must not claim an incumbent"
                )
        else:
            if (
                prior_version != previous_candidate_version
                or prior_fingerprint != previous_candidate_fingerprint
            ):
                raise FastPaperChampionPromotionError(
                    "champion transition incumbent chain is inconsistent"
                )
            if candidate_fingerprint == previous_candidate_fingerprint:
                raise FastPaperChampionPromotionError(
                    "champion transition history contains duplicate promotion"
                )
        if previous_decided_at is not None and decided_at < previous_decided_at:
            raise FastPaperChampionPromotionError(
                "champion transition times are not monotonic"
            )
        previous_candidate_version = candidate_version
        previous_candidate_fingerprint = candidate_fingerprint
        previous_decided_at = decided_at
        validated.append(transition)

    if (
        current_version != previous_candidate_version
        or current_fingerprint != previous_candidate_fingerprint
    ):
        raise FastPaperChampionPromotionError(
            "champion registry current identity does not match final transition"
        )

    if document.get("production_paper_cutover") != "NOT_GRANTED":
        raise FastPaperChampionPromotionError(
            "champion registry PAPER cutover boundary is incompatible"
        )
    if document.get("signing_submission_authority") != "NOT_GRANTED":
        raise FastPaperChampionPromotionError(
            "champion registry signing boundary is incompatible"
        )
    if document.get("live_authority") != "DISABLED":
        raise FastPaperChampionPromotionError(
            "champion registry live boundary is incompatible"
        )

    claimed_registry = _sha256(
        document.get("registry_fingerprint_sha256"),
        "champion registry fingerprint",
    )
    material = dict(document)
    material.pop("registry_fingerprint_sha256", None)
    expected_registry = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed_registry != expected_registry:
        raise FastPaperChampionPromotionError(
            "champion registry fingerprint mismatch"
        )
    return document


def _receipt(
    *,
    state: str,
    candidate: Mapping[str, object],
    registry: Mapping[str, object] | None,
    registry_after: Mapping[str, object] | None,
) -> dict[str, object]:
    effective = registry_after if registry_after is not None else registry
    material: dict[str, object] = {
        "schema_name": FAST_PAPER_CHAMPION_PROMOTION_RECEIPT_SCHEMA_NAME,
        "schema_version": FAST_PAPER_CHAMPION_PROMOTION_RECEIPT_SCHEMA_VERSION,
        "state": state,
        "candidate_champion_version": candidate[
            "candidate_champion_version"
        ],
        "candidate_champion_fingerprint_sha256": candidate[
            "candidate_champion_fingerprint_sha256"
        ],
        "decision_reference": candidate[
            "readiness_report_fingerprint_sha256"
        ],
        "registry_revision": (
            0 if effective is None else effective["revision"]
        ),
        "registry_fingerprint_sha256": (
            None
            if effective is None
            else effective["registry_fingerprint_sha256"]
        ),
        "paper_champion_authority": (
            "RECORDED"
            if state in {"PROMOTED", "ALREADY_CURRENT"}
            else "NOT_RECORDED"
        ),
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _atomic_publish_registry(
    destination: Path,
    registry: Mapping[str, object],
    parent: Path,
) -> None:
    payload = _canonical(dict(registry)).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.is_symlink():
            raise FastPaperChampionPromotionError(
                "champion registry destination became a symlink"
            )
        os.replace(temporary, destination)
        destination.chmod(0o600)
        _fsync_directory(parent)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _exclusive_lock(destination: Path, parent: Path) -> Iterator[None]:
    lock_path = parent / f".{destination.name}.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise FastPaperChampionPromotionError(
                "champion registry lock must be a regular file"
            )
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _safe_parent(destination: Path) -> Path:
    if destination.is_symlink():
        raise FastPaperChampionPromotionError(
            "champion registry destination must not be a symlink"
        )
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise FastPaperChampionPromotionError(
            "champion registry parent must be an existing regular directory"
        )
    return parent


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _decode_canonical_json(
    payload: str,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} payload must be non-empty")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} JSON is malformed") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} JSON must be an object")
    if payload != _canonical(document):
        raise ValueError(f"{label} JSON must be canonical")
    return document


def _release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperChampionPromotionError(
            "release source SHA must be lowercase 40-character hex"
        )
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperChampionPromotionError(
            f"{label} must be lowercase SHA-256"
        )
    return value


def _optional_sha256(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, label)


def _non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FastPaperChampionPromotionError(
            f"{label} must be non-empty trimmed text"
        )
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperChampionPromotionError(
            f"{label} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, label: str) -> int:
    result = _non_negative_int(value, label)
    if result == 0:
        raise FastPaperChampionPromotionError(
            f"{label} must be positive"
        )
    return result


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--readiness-path", required=True)
    parser.add_argument("--registry-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument(
        "--expected-current-champion-fingerprint",
        default=None,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-champion-promotion"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    _add_common_arguments(preflight)
    promote = commands.add_parser("promote")
    _add_common_arguments(promote)
    promote.add_argument("--decided-at-unix-ms", type=int, required=True)
    promote.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight_fast_paper_champion_promotion(
                manifest_path=args.manifest_path,
                readiness_path=args.readiness_path,
                registry_path=args.registry_path,
                expected_release_sha=args.expected_release_sha,
                expected_current_champion_fingerprint=(
                    args.expected_current_champion_fingerprint
                ),
            )
        else:
            result = promote_fast_paper_champion(
                manifest_path=args.manifest_path,
                readiness_path=args.readiness_path,
                registry_path=args.registry_path,
                expected_release_sha=args.expected_release_sha,
                expected_current_champion_fingerprint=(
                    args.expected_current_champion_fingerprint
                ),
                decided_at_unix_ms=args.decided_at_unix_ms,
                reason=args.reason,
            )
    except (FastPaperChampionPromotionError, ValueError, OSError) as exc:
        print(
            _canonical(
                {
                    "schema_name": (
                        "shreks.fast_paper_champion_promotion_failure"
                    ),
                    "schema_version": 1,
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "paper_champion_authority": "NOT_RECORDED",
                    "production_paper_cutover": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(_canonical(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
