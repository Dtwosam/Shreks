from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from shreks_brain.fast_proof_tools import (
    FAST_PROOF_TOOL_NAMES,
    FastProofToolSet,
    decode_fast_proof_tools_manifest,
    materialize_fast_proof_tools,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    read_fast_training_feature_jsonl,
)


FAST_PROOF_WORKSPACE_SCHEMA_NAME = "shreks.fast_proof_workspace"
FAST_PROOF_WORKSPACE_SCHEMA_VERSION = 1

_FEATURE_FILE = "features.jsonl"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset({_FEATURE_FILE, _MANIFEST_FILE})
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "release_source_sha",
        "platform",
        "proof_tools_manifest_fingerprint_sha256",
        "exporter_sha256",
        "observer_database_sha256",
        "observer_database_wal_sha256",
        "feature_jsonl_sha256",
        "feature_logical_fingerprint_sha256",
        "row_count",
        "min_decision_sequence",
        "max_decision_sequence",
        "min_decision_observed_at_unix_ms",
        "max_decision_observed_at_unix_ms",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastProofWorkspaceManifest:
    schema_name: str
    schema_version: int
    release_source_sha: str
    platform: str
    proof_tools_manifest_fingerprint_sha256: str
    exporter_sha256: str
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    feature_jsonl_sha256: str
    feature_logical_fingerprint_sha256: str
    row_count: int
    min_decision_sequence: int
    max_decision_sequence: int
    min_decision_observed_at_unix_ms: int
    max_decision_observed_at_unix_ms: int
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PROOF_WORKSPACE_SCHEMA_NAME:
            raise ValueError("unsupported fast proof workspace schema_name")
        if self.schema_version != FAST_PROOF_WORKSPACE_SCHEMA_VERSION:
            raise ValueError("unsupported fast proof workspace schema_version")
        _require_source_sha(self.release_source_sha)
        _require_non_empty("platform", self.platform)
        for name in (
            "proof_tools_manifest_fingerprint_sha256",
            "exporter_sha256",
            "observer_database_sha256",
            "feature_jsonl_sha256",
            "feature_logical_fingerprint_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.observer_database_wal_sha256 is not None:
            _require_sha256(
                "observer_database_wal_sha256",
                self.observer_database_wal_sha256,
            )
        _require_positive_int("row_count", self.row_count)
        _require_positive_int(
            "min_decision_sequence",
            self.min_decision_sequence,
        )
        _require_positive_int(
            "max_decision_sequence",
            self.max_decision_sequence,
        )
        if self.min_decision_sequence > self.max_decision_sequence:
            raise ValueError(
                "proof workspace decision sequence bounds are reversed"
            )
        _require_non_negative_int(
            "min_decision_observed_at_unix_ms",
            self.min_decision_observed_at_unix_ms,
        )
        _require_non_negative_int(
            "max_decision_observed_at_unix_ms",
            self.max_decision_observed_at_unix_ms,
        )
        if (
            self.min_decision_observed_at_unix_ms
            > self.max_decision_observed_at_unix_ms
        ):
            raise ValueError(
                "proof workspace decision timestamp bounds are reversed"
            )


@dataclass(frozen=True, slots=True)
class FastProofWorkspaceArtifact:
    path: Path
    manifest: FastProofWorkspaceManifest
    features: FastTrainingFeatureDataset

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        if type(self.manifest) is not FastProofWorkspaceManifest:
            raise ValueError(
                "manifest must be exact FastProofWorkspaceManifest"
            )
        if type(self.features) is not FastTrainingFeatureDataset:
            raise ValueError(
                "features must be exact FastTrainingFeatureDataset"
            )


@dataclass(frozen=True, slots=True)
class _DatabaseSnapshot:
    database_sha256: str
    wal_sha256: str | None


def prepare_fast_proof_workspace(
    *,
    database_path: str | Path,
    destination: str | Path,
    tool_root: str | Path,
    expected_source_sha: str,
    expected_platform: str,
    timeout_seconds: int,
) -> FastProofWorkspaceArtifact:
    _require_source_sha(expected_source_sha)
    _require_non_empty("expected_platform", expected_platform)
    _require_positive_int("timeout_seconds", timeout_seconds)

    database = Path(database_path).expanduser().resolve()
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "proof workspace database must be an existing regular file"
        )
    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "proof workspace destination already exists; overwrite is forbidden"
        )

    toolset = materialize_fast_proof_tools(
        tool_root,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    _validate_toolset(
        toolset,
        expected_source_sha=expected_source_sha,
        expected_platform=expected_platform,
    )
    tool_dir = toolset.paths[0].parent
    tool_manifest_path = tool_dir / "manifest.json"
    if tool_manifest_path.is_symlink() or not tool_manifest_path.is_file():
        raise ValueError(
            "materialized proof tools manifest is missing"
        )
    tool_manifest = decode_fast_proof_tools_manifest(
        tool_manifest_path.read_text(encoding="utf-8")
    )
    if (
        tool_manifest.source_sha != expected_source_sha
        or tool_manifest.platform != expected_platform
    ):
        raise ValueError(
            "materialized proof tools identity mismatch"
        )
    exporter = next(
        path
        for path in toolset.paths
        if path.name == "export_fast_training_features"
    )
    exporter_sha256 = _sha256_file_stable(exporter)

    before = _capture_database(database)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.tmp-",
            dir=destination_path.parent,
        )
    )
    staging.chmod(0o700)
    try:
        feature_path = staging / _FEATURE_FILE
        try:
            completed = subprocess.run(
                [str(exporter), str(database), str(feature_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "Fast proof workspace exporter timed out"
            ) from exc
        except OSError as exc:
            raise ValueError(
                "Fast proof workspace exporter could not be executed"
            ) from exc
        if completed.returncode != 0:
            raise ValueError(
                f"Fast proof workspace exporter failed with exit code {completed.returncode}"
            )
        if feature_path.is_symlink() or not feature_path.is_file():
            raise ValueError(
                "Fast proof workspace exporter did not create feature JSONL"
            )

        features = read_fast_training_feature_jsonl(feature_path)
        feature_sha256 = _sha256_file_stable(feature_path)
        if features.source_sha256 != feature_sha256:
            raise ValueError(
                "Fast proof workspace feature source fingerprint mismatch"
            )
        feature_path.chmod(0o600)

        after = _capture_database(database)
        if after != before:
            raise ValueError(
                "Fast proof workspace database source changed during export"
            )

        sequences = tuple(
            value.decision_sequence for value in features.records
        )
        observed = tuple(
            value.decision_observed_at_unix_ms
            for value in features.records
        )
        material = {
            "schema_name": FAST_PROOF_WORKSPACE_SCHEMA_NAME,
            "schema_version": FAST_PROOF_WORKSPACE_SCHEMA_VERSION,
            "release_source_sha": expected_source_sha,
            "platform": expected_platform,
            "proof_tools_manifest_fingerprint_sha256": (
                tool_manifest.manifest_fingerprint_sha256
            ),
            "exporter_sha256": exporter_sha256,
            "observer_database_sha256": before.database_sha256,
            "observer_database_wal_sha256": before.wal_sha256,
            "feature_jsonl_sha256": feature_sha256,
            "feature_logical_fingerprint_sha256": (
                features.logical_fingerprint_sha256
            ),
            "row_count": len(features.records),
            "min_decision_sequence": min(sequences),
            "max_decision_sequence": max(sequences),
            "min_decision_observed_at_unix_ms": min(observed),
            "max_decision_observed_at_unix_ms": max(observed),
        }
        manifest = FastProofWorkspaceManifest(
            schema_name=material["schema_name"],
            schema_version=material["schema_version"],
            release_source_sha=material["release_source_sha"],
            platform=material["platform"],
            proof_tools_manifest_fingerprint_sha256=material[
                "proof_tools_manifest_fingerprint_sha256"
            ],
            exporter_sha256=material["exporter_sha256"],
            observer_database_sha256=material[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=material[
                "observer_database_wal_sha256"
            ],
            feature_jsonl_sha256=material["feature_jsonl_sha256"],
            feature_logical_fingerprint_sha256=material[
                "feature_logical_fingerprint_sha256"
            ],
            row_count=material["row_count"],
            min_decision_sequence=material["min_decision_sequence"],
            max_decision_sequence=material["max_decision_sequence"],
            min_decision_observed_at_unix_ms=material[
                "min_decision_observed_at_unix_ms"
            ],
            max_decision_observed_at_unix_ms=material[
                "max_decision_observed_at_unix_ms"
            ],
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fast_proof_workspace(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged Fast proof workspace did not round-trip"
            )
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "proof workspace destination appeared during write"
            )
        staging.rename(destination_path)
        return read_fast_proof_workspace(destination_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_proof_workspace(
    path: str | Path,
) -> FastProofWorkspaceArtifact:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "Fast proof workspace must be an existing real directory"
        )
    entries = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "Fast proof workspace may contain regular files only"
            )
        entries.add(child.name)
    if entries != _ROOT_ENTRIES:
        raise ValueError(
            "Fast proof workspace has unknown or missing entries"
        )

    document = _load_canonical(
        (root / _MANIFEST_FILE).read_text(encoding="utf-8"),
        label="Fast proof workspace manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
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
            observer_database_sha256=document[
                "observer_database_sha256"
            ],
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
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "Fast proof workspace artifact fingerprint mismatch"
        )

    feature_path = root / _FEATURE_FILE
    if _sha256_file_stable(feature_path) != manifest.feature_jsonl_sha256:
        raise ValueError(
            "Fast proof workspace feature file hash mismatch"
        )
    features = read_fast_training_feature_jsonl(feature_path)
    if (
        features.source_sha256 != manifest.feature_jsonl_sha256
        or features.logical_fingerprint_sha256
        != manifest.feature_logical_fingerprint_sha256
        or len(features.records) != manifest.row_count
    ):
        raise ValueError(
            "Fast proof workspace feature evidence does not match manifest"
        )
    sequences = tuple(value.decision_sequence for value in features.records)
    observed = tuple(
        value.decision_observed_at_unix_ms for value in features.records
    )
    if (
        min(sequences) != manifest.min_decision_sequence
        or max(sequences) != manifest.max_decision_sequence
        or min(observed) != manifest.min_decision_observed_at_unix_ms
        or max(observed) != manifest.max_decision_observed_at_unix_ms
    ):
        raise ValueError(
            "Fast proof workspace feature bounds do not match manifest"
        )
    return FastProofWorkspaceArtifact(
        path=root,
        manifest=manifest,
        features=features,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-proof-workspace",
        description=(
            "Materialize sealed Fast proof tools and export an immutable "
            "FL8.1 feature workspace from a read-only Shreks database."
        ),
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--tool-root", required=True)
    parser.add_argument("--release-source-sha", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--timeout-seconds", required=True, type=int)
    args = parser.parse_args(argv)

    artifact = prepare_fast_proof_workspace(
        database_path=args.database,
        destination=args.destination,
        tool_root=args.tool_root,
        expected_source_sha=args.release_source_sha,
        expected_platform=args.platform,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            _manifest_document(artifact.manifest),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


def _validate_toolset(
    value: FastProofToolSet,
    *,
    expected_source_sha: str,
    expected_platform: str,
) -> None:
    if type(value) is not FastProofToolSet:
        raise ValueError(
            "materialized proof tools must be exact FastProofToolSet"
        )
    if (
        value.source_sha != expected_source_sha
        or value.platform != expected_platform
    ):
        raise ValueError("materialized proof toolset identity mismatch")
    if tuple(path.name for path in value.paths) != FAST_PROOF_TOOL_NAMES:
        raise ValueError(
            "materialized proof toolset member order mismatch"
        )


def _capture_database(database: Path) -> _DatabaseSnapshot:
    wal = Path(str(database) + "-wal")
    return _DatabaseSnapshot(
        database_sha256=_sha256_file_stable(database),
        wal_sha256=_sha256_file_stable(wal) if wal.is_file() else None,
    )


def _manifest_document(
    value: FastProofWorkspaceManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "release_source_sha": value.release_source_sha,
        "platform": value.platform,
        "proof_tools_manifest_fingerprint_sha256": (
            value.proof_tools_manifest_fingerprint_sha256
        ),
        "exporter_sha256": value.exporter_sha256,
        "observer_database_sha256": value.observer_database_sha256,
        "observer_database_wal_sha256": (
            value.observer_database_wal_sha256
        ),
        "feature_jsonl_sha256": value.feature_jsonl_sha256,
        "feature_logical_fingerprint_sha256": (
            value.feature_logical_fingerprint_sha256
        ),
        "row_count": value.row_count,
        "min_decision_sequence": value.min_decision_sequence,
        "max_decision_sequence": value.max_decision_sequence,
        "min_decision_observed_at_unix_ms": (
            value.min_decision_observed_at_unix_ms
        ),
        "max_decision_observed_at_unix_ms": (
            value.max_decision_observed_at_unix_ms
        ),
        "artifact_fingerprint_sha256": value.artifact_fingerprint_sha256,
    }


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(f"{label} must have exactly one trailing newline")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical(value) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be an existing regular file: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("source changed while fingerprinting")
    return digest.hexdigest()


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "release source SHA must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
