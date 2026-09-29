from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_NAME = (
    "shreks.fast_paper_release_authorization"
)
FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_VERSION = 1
FAST_PAPER_RELEASE_AUTHORIZATION_STATE = (
    "AUTHORIZED_FAST_PAPER_RELEASE_UPGRADE"
)

_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "source_release_source_sha",
        "source_authorization_fingerprint_sha256",
        "release_handoff_fingerprint_sha256",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "fast_run_id",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "authorized_at_unix_ms",
        "production_paper_cutover",
        "service_control_authority",
        "signing_submission_authority",
        "live_authority",
        "authorization_fingerprint_sha256",
    }
)


class FastPaperReleaseAuthorizationError(RuntimeError):
    pass


def build_fast_paper_release_authorization(
    *,
    source_release_source_sha: str,
    source_authorization_fingerprint_sha256: str,
    release_handoff_fingerprint_sha256: str,
    release_source_sha: str,
    manifest_fingerprint_sha256: str,
    champion_version: str,
    champion_fingerprint_sha256: str,
    action_policy_version: int,
    fast_run_id: str,
    binding_fingerprint_sha256: str,
    execution_policy_fingerprint_sha256: str,
    authorized_at_unix_ms: int,
) -> dict[str, object]:
    if source_release_source_sha == release_source_sha:
        raise FastPaperReleaseAuthorizationError(
            "Fast PAPER release authorization requires a distinct target release"
        )
    material: dict[str, object] = {
        "schema_name": FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_NAME,
        "schema_version": FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_VERSION,
        "state": FAST_PAPER_RELEASE_AUTHORIZATION_STATE,
        "source_release_source_sha": _source_sha(
            source_release_source_sha,
            "source release source SHA",
        ),
        "source_authorization_fingerprint_sha256": _sha256(
            source_authorization_fingerprint_sha256,
            "source authorization fingerprint",
        ),
        "release_handoff_fingerprint_sha256": _sha256(
            release_handoff_fingerprint_sha256,
            "release handoff fingerprint",
        ),
        "release_source_sha": _source_sha(
            release_source_sha,
            "release source SHA",
        ),
        "manifest_fingerprint_sha256": _sha256(
            manifest_fingerprint_sha256,
            "manifest fingerprint",
        ),
        "champion_version": _text(champion_version, "champion version"),
        "champion_fingerprint_sha256": _sha256(
            champion_fingerprint_sha256,
            "champion fingerprint",
        ),
        "action_policy_version": _positive_int(
            action_policy_version,
            "action policy version",
        ),
        "fast_run_id": _text(fast_run_id, "Fast run id"),
        "binding_fingerprint_sha256": _sha256(
            binding_fingerprint_sha256,
            "binding fingerprint",
        ),
        "execution_policy_fingerprint_sha256": _sha256(
            execution_policy_fingerprint_sha256,
            "execution policy fingerprint",
        ),
        "authorized_at_unix_ms": _non_negative_int(
            authorized_at_unix_ms,
            "authorization timestamp",
        ),
        "production_paper_cutover": "GRANTED",
        "service_control_authority": "PROTECTED_FAST_RELEASE_ONLY",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return {
        **material,
        "authorization_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def encode_fast_paper_release_authorization(
    document: Mapping[str, object],
) -> str:
    normalized = _validate_document(document)
    return _canonical(normalized) + "\n"


def read_fast_paper_release_authorization(
    path: str | Path,
) -> dict[str, object]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperReleaseAuthorizationError(
            "release authorization must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        raw = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise FastPaperReleaseAuthorizationError(
            "release authorization is malformed JSON"
        ) from exc
    normalized = _validate_document(raw)
    if payload != _canonical(normalized) + "\n":
        raise FastPaperReleaseAuthorizationError(
            "release authorization must use canonical JSON"
        )
    return normalized


def verify_fast_paper_release_authorization(
    document: Mapping[str, object],
    *,
    manifest,
    binding,
    execution_policy,
) -> None:
    normalized = _validate_document(document)
    expected = {
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "fast_run_id": binding.fast_run_id,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            execution_policy.policy_fingerprint_sha256
        ),
    }
    for name, value in expected.items():
        if normalized[name] != value:
            raise FastPaperReleaseAuthorizationError(
                f"release authorization {name} identity mismatch"
            )


def _validate_document(
    document: Mapping[str, object] | object,
) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise FastPaperReleaseAuthorizationError(
            "release authorization must be a mapping"
        )
    normalized = dict(document)
    if frozenset(normalized) != _FIELDS:
        raise FastPaperReleaseAuthorizationError(
            "release authorization has unknown or missing fields"
        )
    expected_static = {
        "schema_name": FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_NAME,
        "schema_version": FAST_PAPER_RELEASE_AUTHORIZATION_SCHEMA_VERSION,
        "state": FAST_PAPER_RELEASE_AUTHORIZATION_STATE,
        "production_paper_cutover": "GRANTED",
        "service_control_authority": "PROTECTED_FAST_RELEASE_ONLY",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    for name, expected in expected_static.items():
        if normalized[name] != expected:
            raise FastPaperReleaseAuthorizationError(
                f"release authorization {name} is incompatible"
            )
    source_sha = _source_sha(
        normalized["source_release_source_sha"],
        "source release source SHA",
    )
    target_sha = _source_sha(
        normalized["release_source_sha"],
        "release source SHA",
    )
    if source_sha == target_sha:
        raise FastPaperReleaseAuthorizationError(
            "release authorization source and target releases must differ"
        )
    _text(normalized["champion_version"], "champion version")
    _text(normalized["fast_run_id"], "Fast run id")
    _positive_int(
        normalized["action_policy_version"],
        "action policy version",
    )
    _non_negative_int(
        normalized["authorized_at_unix_ms"],
        "authorization timestamp",
    )
    for name in (
        "source_authorization_fingerprint_sha256",
        "release_handoff_fingerprint_sha256",
        "manifest_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
    ):
        _sha256(normalized[name], name)
    claimed = _sha256(
        normalized["authorization_fingerprint_sha256"],
        "authorization fingerprint",
    )
    material = dict(normalized)
    material.pop("authorization_fingerprint_sha256")
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise FastPaperReleaseAuthorizationError(
            "release authorization fingerprint mismatch"
        )
    return normalized


def _source_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperReleaseAuthorizationError(
            f"{label} must be exactly 40 lowercase hex characters"
        )
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperReleaseAuthorizationError(
            f"{label} must be exactly 64 lowercase hex characters"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FastPaperReleaseAuthorizationError(
            f"{label} must be non-empty canonical text"
        )
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperReleaseAuthorizationError(
            f"{label} must be a positive integer"
        )
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperReleaseAuthorizationError(
            f"{label} must be a non-negative integer"
        )
    return value


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
    )
