from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .artifact import read_fast_deterministic_campaign_artifact
from .request import (
    decode_fast_deterministic_campaign_request,
    run_fast_deterministic_campaign_request_file,
)


FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_NAME = (
    "shreks.fast_deterministic_campaign_invocation"
)
FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_VERSION = 1
_FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_NAME = (
    "shreks.fast_deterministic_campaign_sources"
)
_FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_VERSION = 1

_REQUEST_FILE = "request.json"
_SOURCES_FILE = "sources.json"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset({_REQUEST_FILE, _SOURCES_FILE, _MANIFEST_FILE})
_SOURCE_LABELS = (
    "candidate_binary_path",
    "champion_path",
    "comparison_catalog_path",
    "entry_authority_binary_path",
    "feature_parquet_path",
    "observer_database_path",
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request_fingerprint_sha256",
        "request_file_sha256",
        "source_count",
        "source_snapshot_fingerprint_sha256",
        "campaign_artifact_fingerprint_sha256",
        "campaign_directory_name",
        "invocation_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignSourceComponent:
    role: str
    file_name: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_non_empty_string("role", self.role)
        _require_non_empty_string("file_name", self.file_name)
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        _require_sha256("sha256", self.sha256)


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignSourceSnapshot:
    label: str
    declared_path: str
    components: tuple[FastDeterministicCampaignSourceComponent, ...]

    def __post_init__(self) -> None:
        if self.label not in _SOURCE_LABELS:
            raise ValueError("source snapshot label is unsupported")
        _require_non_empty_string("declared_path", self.declared_path)
        if not isinstance(self.components, tuple) or not self.components:
            raise ValueError("source snapshot components must be non-empty")
        if not all(
            type(value) is FastDeterministicCampaignSourceComponent
            for value in self.components
        ):
            raise ValueError(
                "source snapshot components must contain exact source components"
            )
        roles = tuple(value.role for value in self.components)
        if len(roles) != len(set(roles)):
            raise ValueError("source snapshot component roles must be unique")


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignInvocationManifest:
    schema_name: str
    schema_version: int
    request_fingerprint_sha256: str
    request_file_sha256: str
    source_count: int
    source_snapshot_fingerprint_sha256: str
    campaign_artifact_fingerprint_sha256: str
    campaign_directory_name: str
    invocation_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_NAME:
            raise ValueError("unsupported deterministic campaign invocation schema_name")
        if self.schema_version != FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_VERSION:
            raise ValueError("unsupported deterministic campaign invocation schema_version")
        for name in (
            "request_fingerprint_sha256",
            "request_file_sha256",
            "source_snapshot_fingerprint_sha256",
            "campaign_artifact_fingerprint_sha256",
            "invocation_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.source_count != len(_SOURCE_LABELS):
            raise ValueError(
                "deterministic campaign invocation must contain exactly six sources"
            )
        _require_non_empty_string(
            "campaign_directory_name",
            self.campaign_directory_name,
        )


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignInvocationSeal:
    path: Path
    manifest: FastDeterministicCampaignInvocationManifest
    request_payload: str
    sources: tuple[FastDeterministicCampaignSourceSnapshot, ...]

    def __post_init__(self) -> None:
        if type(self.path) is not Path:
            raise ValueError("path must be exact Path")
        if type(self.manifest) is not FastDeterministicCampaignInvocationManifest:
            raise ValueError(
                "manifest must be exact FastDeterministicCampaignInvocationManifest"
            )
        if not isinstance(self.request_payload, str) or not self.request_payload:
            raise ValueError("request_payload must be non-empty text")
        if (
            not isinstance(self.sources, tuple)
            or len(self.sources) != len(_SOURCE_LABELS)
            or not all(
                type(value) is FastDeterministicCampaignSourceSnapshot
                for value in self.sources
            )
        ):
            raise ValueError(
                "sources must contain exactly six exact source snapshots"
            )


def run_fast_deterministic_campaign_invocation_file(
    request_path: str | Path,
) -> FastDeterministicCampaignInvocationSeal:
    source = Path(request_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(
            "deterministic campaign request path must identify an existing file"
        )
    request_payload = source.read_text(encoding="utf-8")
    request = decode_fast_deterministic_campaign_request(request_payload)
    base = source.parent
    campaign_path = _resolve_path(base, request.destination_path)
    seal_path = Path(f"{campaign_path}.invocation")
    if campaign_path.exists():
        raise FileExistsError(
            "deterministic campaign destination already exists"
        )
    if seal_path.exists():
        raise FileExistsError(
            "deterministic campaign invocation seal already exists"
        )

    before = _capture_sources(base, request)
    staging_path: Path | None = None
    campaign_created = False
    try:
        campaign_manifest = run_fast_deterministic_campaign_request_file(
            source
        )
        campaign_created = campaign_path.exists()
        after = _capture_sources(base, request)
        if after != before:
            raise ValueError(
                "deterministic campaign source fingerprint changed during execution"
            )

        campaign = read_fast_deterministic_campaign_artifact(campaign_path)
        if (
            campaign.manifest.artifact_fingerprint_sha256
            != campaign_manifest.artifact_fingerprint_sha256
        ):
            raise ValueError(
                "deterministic campaign artifact fingerprint changed after execution"
            )

        sources_document = _sources_document(before)
        sources_payload = _canonical(sources_document)
        source_snapshot_fingerprint = sources_document[
            "source_snapshot_fingerprint_sha256"
        ]
        request_file_sha256 = _sha256_bytes(
            request_payload.encode("utf-8")
        )
        manifest_material = {
            "schema_name": FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_NAME,
            "schema_version": FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_VERSION,
            "request_fingerprint_sha256": (
                request.request_fingerprint_sha256
            ),
            "request_file_sha256": request_file_sha256,
            "source_count": len(before),
            "source_snapshot_fingerprint_sha256": (
                source_snapshot_fingerprint
            ),
            "campaign_artifact_fingerprint_sha256": (
                campaign_manifest.artifact_fingerprint_sha256
            ),
            "campaign_directory_name": campaign_path.name,
        }
        manifest = FastDeterministicCampaignInvocationManifest(
            **manifest_material,
            invocation_fingerprint_sha256=_sha256_canonical(
                manifest_material
            ),
        )

        seal_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = Path(
            tempfile.mkdtemp(
                prefix=f".{seal_path.name}-",
                dir=seal_path.parent,
            )
        )
        (staging_path / _REQUEST_FILE).write_text(
            request_payload,
            encoding="utf-8",
        )
        (staging_path / _SOURCES_FILE).write_text(
            sources_payload,
            encoding="utf-8",
        )
        (staging_path / _MANIFEST_FILE).write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )

        verified = read_fast_deterministic_campaign_invocation_seal(
            staging_path
        )
        if verified.manifest != manifest:
            raise ValueError(
                "staged deterministic campaign invocation manifest did not round-trip"
            )
        staging_path.rename(seal_path)
        staging_path = None
        return read_fast_deterministic_campaign_invocation_seal(seal_path)
    except Exception:
        if staging_path is not None:
            shutil.rmtree(staging_path, ignore_errors=True)
        if campaign_created and campaign_path.exists():
            shutil.rmtree(campaign_path, ignore_errors=True)
        raise


def read_fast_deterministic_campaign_invocation_seal(
    source: str | Path,
) -> FastDeterministicCampaignInvocationSeal:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            "deterministic campaign invocation source must be an existing directory"
        )
    entries = frozenset(path.name for path in root.iterdir())
    if entries != _ROOT_ENTRIES:
        raise ValueError(
            "deterministic campaign invocation has unknown or missing entries"
        )

    request_payload = (root / _REQUEST_FILE).read_text(encoding="utf-8")
    request = decode_fast_deterministic_campaign_request(request_payload)

    sources_payload = (root / _SOURCES_FILE).read_text(encoding="utf-8")
    sources_document = _load_canonical_object(
        sources_payload,
        label="deterministic campaign source snapshot",
    )
    sources = _decode_sources_document(sources_document)

    manifest_payload = (root / _MANIFEST_FILE).read_text(encoding="utf-8")
    manifest_document = _load_canonical_object(
        manifest_payload,
        label="deterministic campaign invocation manifest",
    )
    if frozenset(manifest_document) != _MANIFEST_KEYS:
        raise ValueError(
            "deterministic campaign invocation manifest has unknown or missing fields"
        )
    try:
        manifest = FastDeterministicCampaignInvocationManifest(
            **manifest_document
        )
    except TypeError as exc:
        raise ValueError(
            "deterministic campaign invocation manifest is invalid"
        ) from exc

    fingerprint_material = dict(manifest_document)
    claimed = fingerprint_material.pop(
        "invocation_fingerprint_sha256"
    )
    if _sha256_canonical(fingerprint_material) != claimed:
        raise ValueError(
            "deterministic campaign invocation fingerprint mismatch"
        )
    if _sha256_bytes(request_payload.encode("utf-8")) != (
        manifest.request_file_sha256
    ):
        raise ValueError(
            "deterministic campaign invocation request file fingerprint mismatch"
        )
    if request.request_fingerprint_sha256 != (
        manifest.request_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign invocation request fingerprint mismatch"
        )
    if sources_document["source_snapshot_fingerprint_sha256"] != (
        manifest.source_snapshot_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign invocation source fingerprint mismatch"
        )
    if len(sources) != manifest.source_count:
        raise ValueError(
            "deterministic campaign invocation source count mismatch"
        )

    campaign_path = root.parent / manifest.campaign_directory_name
    campaign = read_fast_deterministic_campaign_artifact(campaign_path)
    if campaign.manifest.artifact_fingerprint_sha256 != (
        manifest.campaign_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign invocation campaign fingerprint mismatch"
        )

    return FastDeterministicCampaignInvocationSeal(
        path=root,
        manifest=manifest,
        request_payload=request_payload,
        sources=sources,
    )


def _capture_sources(
    base: Path,
    request: object,
) -> tuple[FastDeterministicCampaignSourceSnapshot, ...]:
    values = []
    for label in _SOURCE_LABELS:
        declared = getattr(request, label)
        _require_non_empty_string(label, declared)
        path = _resolve_path(base, declared)
        if not path.is_file():
            raise ValueError(f"{label} must resolve to an existing file")
        components = [_component("file", path)]
        if label == "observer_database_path":
            components[0] = _component("database", path)
            wal = Path(f"{path}-wal")
            if wal.exists():
                if not wal.is_file():
                    raise ValueError(
                        "observer database WAL sidecar must be a file when present"
                    )
                components.append(_component("wal", wal))
        values.append(
            FastDeterministicCampaignSourceSnapshot(
                label=label,
                declared_path=declared,
                components=tuple(components),
            )
        )
    return tuple(values)


def _component(
    role: str,
    path: Path,
) -> FastDeterministicCampaignSourceComponent:
    payload = path.read_bytes()
    return FastDeterministicCampaignSourceComponent(
        role=role,
        file_name=path.name,
        size_bytes=len(payload),
        sha256=_sha256_bytes(payload),
    )


def _sources_document(
    sources: tuple[FastDeterministicCampaignSourceSnapshot, ...],
) -> dict[str, object]:
    body = {
        "schema_name": _FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_NAME,
        "schema_version": _FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_VERSION,
        "sources": [_source_document(value) for value in sources],
    }
    return {
        **body,
        "source_snapshot_fingerprint_sha256": _sha256_canonical(body),
    }


def _decode_sources_document(
    document: dict[str, object],
) -> tuple[FastDeterministicCampaignSourceSnapshot, ...]:
    expected = frozenset(
        {
            "schema_name",
            "schema_version",
            "sources",
            "source_snapshot_fingerprint_sha256",
        }
    )
    if frozenset(document) != expected:
        raise ValueError(
            "deterministic campaign source snapshot has unknown or missing fields"
        )
    if document["schema_name"] != _FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_NAME:
        raise ValueError(
            "unsupported deterministic campaign source snapshot schema_name"
        )
    if document["schema_version"] != _FAST_DETERMINISTIC_CAMPAIGN_SOURCES_SCHEMA_VERSION:
        raise ValueError(
            "unsupported deterministic campaign source snapshot schema_version"
        )
    raw_sources = document["sources"]
    if not isinstance(raw_sources, list):
        raise ValueError(
            "deterministic campaign source snapshot sources must be an array"
        )
    values = tuple(_decode_source(value) for value in raw_sources)
    if tuple(value.label for value in values) != _SOURCE_LABELS:
        raise ValueError(
            "deterministic campaign source snapshot source order is invalid"
        )
    material = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "sources": raw_sources,
    }
    claimed = document["source_snapshot_fingerprint_sha256"]
    _require_sha256("source_snapshot_fingerprint_sha256", claimed)
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "deterministic campaign source snapshot fingerprint mismatch"
        )
    return values


def _decode_source(
    value: object,
) -> FastDeterministicCampaignSourceSnapshot:
    if not isinstance(value, dict):
        raise ValueError("deterministic campaign source must be an object")
    if frozenset(value) != {"label", "declared_path", "components"}:
        raise ValueError(
            "deterministic campaign source has unknown or missing fields"
        )
    raw_components = value["components"]
    if not isinstance(raw_components, list):
        raise ValueError(
            "deterministic campaign source components must be an array"
        )
    components = tuple(
        _decode_component(item) for item in raw_components
    )
    return FastDeterministicCampaignSourceSnapshot(
        label=value["label"],
        declared_path=value["declared_path"],
        components=components,
    )


def _decode_component(
    value: object,
) -> FastDeterministicCampaignSourceComponent:
    if not isinstance(value, dict):
        raise ValueError(
            "deterministic campaign source component must be an object"
        )
    if frozenset(value) != {"role", "file_name", "size_bytes", "sha256"}:
        raise ValueError(
            "deterministic campaign source component has unknown or missing fields"
        )
    try:
        return FastDeterministicCampaignSourceComponent(**value)
    except TypeError as exc:
        raise ValueError(
            "deterministic campaign source component is invalid"
        ) from exc


def _source_document(
    value: FastDeterministicCampaignSourceSnapshot,
) -> dict[str, object]:
    return {
        "label": value.label,
        "declared_path": value.declared_path,
        "components": [
            {
                "role": component.role,
                "file_name": component.file_name,
                "size_bytes": component.size_bytes,
                "sha256": component.sha256,
            }
            for component in value.components
        ],
    }


def _manifest_document(
    value: FastDeterministicCampaignInvocationManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "request_fingerprint_sha256": value.request_fingerprint_sha256,
        "request_file_sha256": value.request_file_sha256,
        "source_count": value.source_count,
        "source_snapshot_fingerprint_sha256": (
            value.source_snapshot_fingerprint_sha256
        ),
        "campaign_artifact_fingerprint_sha256": (
            value.campaign_artifact_fingerprint_sha256
        ),
        "campaign_directory_name": value.campaign_directory_name,
        "invocation_fingerprint_sha256": value.invocation_fingerprint_sha256,
    }


def _load_canonical_object(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty canonical JSON")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    if payload != _canonical(document):
        raise ValueError(f"{label} must be canonical JSON")
    return document


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return _sha256_bytes(_canonical(value).encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
