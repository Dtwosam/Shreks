from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from fast_chronological_fixtures import chronological_bundle
from shreks_brain.fast_first_champion_v2.bounded_inputs import (
    read_fast_training_feature_jsonl_for_identities,
)
from shreks_brain.fast_proof_workspace import FastProofWorkspaceManifest
from shreks_brain.research.fast_training_features import (
    feature_logical_fingerprint_sha256,
)
from shreks_brain.research.fast_training_targets import (
    _canonicalize,
    future_path_logical_fingerprint_sha256,
)


def _proof_manifest_for(path: Path, records) -> FastProofWorkspaceManifest:
    return FastProofWorkspaceManifest(
        schema_name="shreks.fast_proof_workspace",
        schema_version=1,
        release_source_sha="1" * 40,
        platform="test-platform",
        proof_tools_manifest_fingerprint_sha256="2" * 64,
        exporter_sha256="3" * 64,
        observer_database_sha256="4" * 64,
        observer_database_wal_sha256=None,
        feature_jsonl_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        feature_logical_fingerprint_sha256=(
            feature_logical_fingerprint_sha256(records)
        ),
        row_count=len(records),
        min_decision_sequence=min(value.decision_sequence for value in records),
        max_decision_sequence=max(value.decision_sequence for value in records),
        min_decision_observed_at_unix_ms=min(
            value.decision_observed_at_unix_ms for value in records
        ),
        max_decision_observed_at_unix_ms=max(
            value.decision_observed_at_unix_ms for value in records
        ),
        artifact_fingerprint_sha256="5" * 64,
    )


def test_bounded_feature_reader_authenticates_full_source_and_retains_requested_order(
    tmp_path: Path,
) -> None:
    source = chronological_bundle().features.records
    feature_path = tmp_path / "features.jsonl"
    feature_path.write_text(
        "".join(
            json.dumps(
                asdict(record),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
            for record in source
        ),
        encoding="utf-8",
    )
    manifest = _proof_manifest_for(feature_path, source)
    requested = (
        source[-1].decision_identity,
        source[1].decision_identity,
    )

    selected = read_fast_training_feature_jsonl_for_identities(
        feature_path,
        decision_identities=requested,
        proof_manifest=manifest,
    )

    assert tuple(value.decision_identity for value in selected.records) == requested
    assert selected.source_sha256 == manifest.feature_jsonl_sha256
    assert selected.logical_fingerprint_sha256 == feature_logical_fingerprint_sha256(
        selected.records
    )
    assert len(selected.records) == len(requested)


def test_incremental_future_path_fingerprint_matches_legacy_array_bytes() -> None:
    labels = chronological_bundle().future_path_labels.labels
    legacy = hashlib.sha256(
        json.dumps(
            [_canonicalize(asdict(label)) for label in labels],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    assert future_path_logical_fingerprint_sha256(labels) == legacy
