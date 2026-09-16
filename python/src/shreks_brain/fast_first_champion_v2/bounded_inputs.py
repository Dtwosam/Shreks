from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from shreks_brain.fast_proof_workspace import (
    FastProofWorkspaceManifest,
    _MANIFEST_FILE as _PROOF_MANIFEST_FILE,
    _MANIFEST_KEYS as _PROOF_MANIFEST_KEYS,
    _ROOT_ENTRIES as _PROOF_ROOT_ENTRIES,
    _load_canonical as _load_proof_canonical,
    _sha256_canonical as _sha256_proof_canonical,
    _sha256_file_stable as _sha256_file_stable,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingEconomicsOverlaySelection,
    _load_json_object as _load_economics_json_object,
    _row_from_mapping as _economics_row_from_mapping,
    validate_fast_training_economics_overlay,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    _canonicalize as _canonicalize_feature,
    _iter_feature_mappings,
    _record_from_mapping,
    feature_logical_fingerprint_sha256,
)


def read_fast_proof_workspace_manifest_bounded(
    path: str | Path,
) -> FastProofWorkspaceManifest:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Fast proof workspace must be an existing real directory"
        )
    entries: set[str] = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "Fast proof workspace may contain regular files only"
            )
        entries.add(child.name)
    if entries != _PROOF_ROOT_ENTRIES:
        raise ValueError(
            "Fast proof workspace has unknown or missing entries"
        )

    document = _load_proof_canonical(
        (root / _PROOF_MANIFEST_FILE).read_text(encoding="utf-8"),
        label="Fast proof workspace manifest",
    )
    if frozenset(document) != _PROOF_MANIFEST_KEYS:
        raise ValueError(
            "Fast proof workspace manifest has unknown or missing fields"
        )
    try:
        manifest = FastProofWorkspaceManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            release_source_sha=document["release_source_sha"],
            platform=document["platform"],
            proof_tools_manifest_fingerprint_sha256=document[
                "proof_tools_manifest_fingerprint_sha256"
            ],
            exporter_sha256=document["exporter_sha256"],
            observer_database_sha256=document["observer_database_sha256"],
            observer_database_wal_sha256=document[
                "observer_database_wal_sha256"
            ],
            feature_jsonl_sha256=document["feature_jsonl_sha256"],
            feature_logical_fingerprint_sha256=document[
                "feature_logical_fingerprint_sha256"
            ],
            row_count=document["row_count"],
            min_decision_sequence=document["min_decision_sequence"],
            max_decision_sequence=document["max_decision_sequence"],
            min_decision_observed_at_unix_ms=document[
                "min_decision_observed_at_unix_ms"
            ],
            max_decision_observed_at_unix_ms=document[
                "max_decision_observed_at_unix_ms"
            ],
            artifact_fingerprint_sha256=document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Fast proof workspace manifest is invalid: {exc}"
        ) from exc

    material = dict(document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_proof_canonical(material) != claimed:
        raise ValueError(
            "Fast proof workspace artifact fingerprint mismatch"
        )
    feature_path = root / "features.jsonl"
    if _sha256_file_stable(feature_path) != manifest.feature_jsonl_sha256:
        raise ValueError(
            "Fast proof workspace feature file hash mismatch"
        )
    return manifest


def read_fast_training_feature_jsonl_for_identities(
    path: str | Path,
    *,
    decision_identities: tuple[tuple[object, ...], ...],
    proof_manifest: FastProofWorkspaceManifest,
) -> FastTrainingFeatureDataset:
    if type(proof_manifest) is not FastProofWorkspaceManifest:
        raise ValueError("proof_manifest must be an exact FastProofWorkspaceManifest")
    identities = _validated_identity_population(decision_identities)
    requested = set(identities)

    source = Path(path)
    source_digest = hashlib.sha256()
    logical_digest = hashlib.sha256()
    logical_digest.update(b"[")
    seen: set[tuple[str, int]] = set()
    selected: dict[tuple[object, ...], object] = {}
    previous_sort: tuple[object, ...] | None = None
    previous_sequence: int | None = None
    row_count = 0
    min_sequence: int | None = None
    max_sequence: int | None = None
    min_time: int | None = None
    max_time: int | None = None

    for mapping in _iter_feature_mappings(source, source_digest):
        record = _record_from_mapping(mapping)
        key = (record.decision_signature, record.decision_ordinal)
        if key in seen:
            raise ValueError(
                "training feature dataset contains a duplicate decision identity"
            )
        seen.add(key)
        sort_key = (
            record.decision_sequence,
            record.decision_signature,
            record.decision_ordinal,
        )
        if previous_sort is not None and sort_key < previous_sort:
            raise ValueError("training feature rows are not in canonical order")
        if previous_sequence is not None and record.decision_sequence <= previous_sequence:
            raise ValueError(
                "training feature decision sequences must strictly increase"
            )
        previous_sort = sort_key
        previous_sequence = record.decision_sequence

        if row_count:
            logical_digest.update(b",")
        logical_digest.update(
            json.dumps(
                _canonicalize_feature(asdict(record)),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        )
        row_count += 1
        observed_at = record.decision_observed_at_unix_ms
        min_sequence = (
            record.decision_sequence
            if min_sequence is None
            else min(min_sequence, record.decision_sequence)
        )
        max_sequence = (
            record.decision_sequence
            if max_sequence is None
            else max(max_sequence, record.decision_sequence)
        )
        min_time = observed_at if min_time is None else min(min_time, observed_at)
        max_time = observed_at if max_time is None else max(max_time, observed_at)

        identity = record.decision_identity
        if identity in requested:
            selected[identity] = record

    if row_count == 0:
        raise ValueError("training feature dataset cannot be empty")
    logical_digest.update(b"]")
    source_sha256 = source_digest.hexdigest()
    full_logical = logical_digest.hexdigest()
    if source_sha256 != proof_manifest.feature_jsonl_sha256:
        raise ValueError("Fast proof workspace feature source fingerprint mismatch")
    if full_logical != proof_manifest.feature_logical_fingerprint_sha256:
        raise ValueError("Fast proof workspace feature logical fingerprint mismatch")
    if row_count != proof_manifest.row_count:
        raise ValueError("Fast proof workspace feature row count mismatch")
    if (
        min_sequence != proof_manifest.min_decision_sequence
        or max_sequence != proof_manifest.max_decision_sequence
        or min_time != proof_manifest.min_decision_observed_at_unix_ms
        or max_time != proof_manifest.max_decision_observed_at_unix_ms
    ):
        raise ValueError("Fast proof workspace feature bounds do not match manifest")

    missing = [identity for identity in identities if identity not in selected]
    if missing:
        raise ValueError(
            "authenticated feature source is missing an accepted cohort identity"
        )
    records = tuple(selected[identity] for identity in identities)
    return FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(records),
        source_sha256=source_sha256,
    )


def read_fast_training_economics_overlay_for_identities(
    path: str | Path,
    *,
    horizon_ms: int,
    label_version: int,
    decision_identities: tuple[tuple[object, ...], ...],
) -> FastTrainingEconomicsOverlaySelection:
    if isinstance(horizon_ms, bool) or not isinstance(horizon_ms, int) or horizon_ms <= 0:
        raise ValueError("horizon_ms must be positive")
    if (
        isinstance(label_version, bool)
        or not isinstance(label_version, int)
        or label_version <= 0
    ):
        raise ValueError("label_version must be positive")
    identities = _validated_identity_population(decision_identities)
    requested = set(identities)
    manifest = validate_fast_training_economics_overlay(path)
    if manifest.future_path_label_version != label_version:
        raise ValueError("training economics selected label version contradicts manifest")

    source = Path(path)
    rows_path = source / "rows.jsonl"
    row_hasher = hashlib.sha256()
    selected: dict[tuple[object, ...], object] = {}
    with rows_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.endswith(b"\n"):
                raise ValueError(
                    "training economics rows JSONL must be newline terminated"
                )
            row_hasher.update(raw_line)
            payload = raw_line[:-1]
            if payload.endswith(b"\r"):
                payload = payload[:-1]
            if not payload.strip():
                raise ValueError(f"training economics row {line_number} is blank")
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"training economics row {line_number} is not UTF-8"
                ) from exc
            mapping = _load_economics_json_object(
                text,
                f"training economics overlay row {line_number}",
            )
            identity = (
                mapping.get("decision_signature"),
                mapping.get("decision_ordinal"),
                mapping.get("decision_sequence"),
                mapping.get("mint"),
                mapping.get("quote_mint"),
                mapping.get("venue"),
                mapping.get("decision_observed_at_unix_ms"),
            )
            if (
                identity in requested
                and mapping.get("horizon_ms") == horizon_ms
                and mapping.get("future_path_label_version") == label_version
            ):
                if identity in selected:
                    raise ValueError(
                        "training economics overlay contains duplicate accepted decision identity"
                    )
                selected[identity] = _economics_row_from_mapping(mapping)

    if row_hasher.hexdigest() != manifest.ordered_row_logical_fingerprint_sha256:
        raise ValueError("training economics overlay changed during bounded selection")
    missing = [identity for identity in identities if identity not in selected]
    if missing:
        raise ValueError(
            "training economics overlay is missing an accepted cohort identity"
        )
    rows = tuple(selected[identity] for identity in identities)
    return FastTrainingEconomicsOverlaySelection(manifest=manifest, rows=rows)


def snapshot_regular_files(
    path: str | Path,
    *,
    expected_names: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("snapshot source must be an existing real directory")
    entries = {entry.name for entry in root.iterdir()}
    if entries != expected_names:
        raise ValueError("snapshot source has unknown or missing entries")
    result: list[tuple[str, str]] = []
    for name in sorted(expected_names):
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("snapshot source may contain regular files only")
        result.append((name, _sha256_file_stable(source)))
    return tuple(result)


def _validated_identity_population(
    values: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("decision identities must be a non-empty tuple")
    for value in values:
        if not isinstance(value, tuple) or len(value) != 7:
            raise ValueError("decision identity must be an exact seven-field tuple")
    if len(set(values)) != len(values):
        raise ValueError("decision identities contain a duplicate identity")
    return values
