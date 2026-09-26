from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    fast_training_feature_record_from_mapping,
)

from .codec import (
    build_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
)
from .models import (
    FastPaperRuntimeCursor,
    FastPaperRuntimeManifest,
    FastPaperRuntimeState,
)


FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_NAME = (
    "shreks.fast_paper_runtime_feature_batch"
)
FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION = 1

_BATCH_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "after_cursor",
        "snapshot_max_sequence",
        "records",
        "batch_fingerprint_sha256",
    }
)
_CURSOR_KEYS = frozenset(
    {
        "decision_sequence",
        "decision_signature",
        "decision_ordinal",
        "decision_observed_at_unix_ms",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperRuntimeFeatureBatch:
    schema_name: str
    schema_version: int
    after_cursor: FastPaperRuntimeCursor | None
    snapshot_max_sequence: int
    records: tuple[FastTrainingFeatureRecord, ...]
    batch_fingerprint_sha256: str
    next_state: FastPaperRuntimeState


def fetch_fast_paper_runtime_feature_batch(
    manifest: FastPaperRuntimeManifest,
    state: FastPaperRuntimeState,
    *,
    maximum_decisions: int,
) -> FastPaperRuntimeFeatureBatch:
    if (
        isinstance(maximum_decisions, bool)
        or not isinstance(maximum_decisions, int)
        or maximum_decisions <= 0
    ):
        raise ValueError("maximum_decisions must be a positive integer")

    verify_fast_paper_runtime_bindings(manifest)
    expected_state = build_fast_paper_runtime_state(
        manifest,
        cursor=state.cursor,
    )
    if state != expected_state:
        raise ValueError("runtime state does not authenticate against manifest")

    database = Path(manifest.observer_database_path)
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "runtime observer database must be an existing regular non-symlink file"
        )

    args = [
        manifest.feature_feed_binary_path,
        manifest.observer_database_path,
        str(maximum_decisions),
    ]
    if state.cursor is not None:
        args.extend(
            (
                str(state.cursor.decision_sequence),
                state.cursor.decision_signature,
                str(state.cursor.decision_ordinal),
                str(state.cursor.decision_observed_at_unix_ms),
            )
        )

    try:
        completed = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ValueError("Fast Lane feature feed invocation failed") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise ValueError(
            "Fast Lane feature feed binary failed"
            + (f": {detail}" if detail else "")
        )
    if completed.stderr:
        raise ValueError("Fast Lane feature feed emitted unexpected stderr")

    document = _decode_canonical_batch(completed.stdout)
    after_cursor = _decode_cursor(document["after_cursor"])
    if after_cursor != state.cursor:
        raise ValueError("runtime feature batch cursor does not match runtime state")

    snapshot_max_sequence = _non_negative_int(
        "snapshot_max_sequence",
        document["snapshot_max_sequence"],
    )
    after_sequence = 0 if after_cursor is None else after_cursor.decision_sequence
    if snapshot_max_sequence < after_sequence:
        raise ValueError("runtime feature snapshot watermark regressed behind cursor")

    raw_records = document["records"]
    if not isinstance(raw_records, list):
        raise ValueError("runtime feature batch records must be a list")
    records = tuple(
        fast_training_feature_record_from_mapping(value)
        for value in raw_records
    )

    previous_sequence = after_sequence
    seen: set[tuple[str, int]] = set()
    for record in records:
        if record.decision_sequence <= previous_sequence:
            raise ValueError(
                "runtime feature batch decision sequences must strictly advance"
            )
        if record.decision_sequence > snapshot_max_sequence:
            raise ValueError(
                "runtime feature batch contains a decision beyond snapshot watermark"
            )
        identity = (record.decision_signature, record.decision_ordinal)
        if identity in seen:
            raise ValueError("runtime feature batch contains duplicate decision identity")
        seen.add(identity)
        previous_sequence = record.decision_sequence

    _require_sha256(
        "batch_fingerprint_sha256",
        document["batch_fingerprint_sha256"],
    )
    claimed_fingerprint = document["batch_fingerprint_sha256"]
    fingerprint_material = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "after_cursor": document["after_cursor"],
        "snapshot_max_sequence": snapshot_max_sequence,
        "record_identities": [
            {
                "decision_sequence": record.decision_sequence,
                "decision_signature": record.decision_signature,
                "decision_ordinal": record.decision_ordinal,
                "decision_observed_at_unix_ms": (
                    record.decision_observed_at_unix_ms
                ),
                "mint": record.mint,
                "quote_mint": record.quote_mint,
                "venue": record.venue,
            }
            for record in records
        ],
    }
    if _sha256_canonical(fingerprint_material) != claimed_fingerprint:
        raise ValueError("runtime feature batch fingerprint mismatch")

    next_cursor = state.cursor
    if records:
        last = records[-1]
        next_cursor = FastPaperRuntimeCursor(
            decision_sequence=last.decision_sequence,
            decision_signature=last.decision_signature,
            decision_ordinal=last.decision_ordinal,
            decision_observed_at_unix_ms=last.decision_observed_at_unix_ms,
        )
    next_state = build_fast_paper_runtime_state(
        manifest,
        cursor=next_cursor,
    )

    return FastPaperRuntimeFeatureBatch(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        after_cursor=after_cursor,
        snapshot_max_sequence=snapshot_max_sequence,
        records=records,
        batch_fingerprint_sha256=claimed_fingerprint,
        next_state=next_state,
    )


def _decode_canonical_batch(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str) or not payload:
        raise ValueError("runtime feature batch payload must be non-empty text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("runtime feature batch is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("runtime feature batch must be a JSON object")
    if frozenset(value) != _BATCH_KEYS:
        raise ValueError("runtime feature batch has unknown or missing fields")
    if payload != _canonical(value) + "\n":
        raise ValueError("runtime feature batch must use canonical JSON")

    if value["schema_name"] != FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_NAME:
        raise ValueError("runtime feature batch schema_name is incompatible")
    if value["schema_version"] != FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION:
        raise ValueError("runtime feature batch schema_version is incompatible")
    return value


def _decode_cursor(value: object) -> FastPaperRuntimeCursor | None:
    if value is None:
        return None
    if not isinstance(value, dict) or frozenset(value) != _CURSOR_KEYS:
        raise ValueError("runtime feature cursor has unknown or missing fields")
    try:
        return FastPaperRuntimeCursor(
            decision_sequence=value["decision_sequence"],
            decision_signature=value["decision_signature"],
            decision_ordinal=value["decision_ordinal"],
            decision_observed_at_unix_ms=value["decision_observed_at_unix_ms"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime feature cursor is incompatible") from exc


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


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
