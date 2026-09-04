from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

import shreks_brain.fast_proof_workspace as workspace_module
from fast_forecast_fixtures import feature_record
from shreks_brain.fast_proof_tools import (
    FAST_PROOF_TOOL_NAMES,
    FastProofToolSet,
    build_fast_proof_tools_manifest,
    encode_fast_proof_tools_manifest,
)
from shreks_brain.fast_proof_workspace import (
    FAST_PROOF_WORKSPACE_SCHEMA_NAME,
    FAST_PROOF_WORKSPACE_SCHEMA_VERSION,
    FastProofWorkspaceArtifact,
    prepare_fast_proof_workspace,
    read_fast_proof_workspace,
)


SOURCE_SHA = "8fb1576d6d1270e513bbecd01b56ea715e927198"
PLATFORM = "x86_64-unknown-linux-gnu"


def _feature_payload() -> str:
    rows = (
        feature_record(0, 0.0),
        feature_record(1, 1.0),
    )
    return "".join(
        json.dumps(
            asdict(row),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
        for row in rows
    )


def _toolset(tmp_path: Path, *, mutate_database: bool = False, exit_code: int = 0):
    root = tmp_path / "materialized-tools" / SOURCE_SHA
    root.mkdir(parents=True)
    payload = _feature_payload()
    exporter = root / FAST_PROOF_TOOL_NAMES[0]
    exporter.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "database = pathlib.Path(sys.argv[1])\n"
        "output = pathlib.Path(sys.argv[2])\n"
        + (
            f"output.write_text({payload!r}, encoding='utf-8')\n"
            if exit_code == 0
            else ""
        )
        + (
            "database.write_bytes(database.read_bytes() + b'mutated')\n"
            if mutate_database
            else ""
        )
        + f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    exporter.chmod(0o700)
    for name in FAST_PROOF_TOOL_NAMES[1:]:
        path = root / name
        path.write_bytes(b"unused-offline-tool")
        path.chmod(0o700)
    paths = tuple(root / name for name in FAST_PROOF_TOOL_NAMES)
    manifest = build_fast_proof_tools_manifest(
        source_sha=SOURCE_SHA,
        platform=PLATFORM,
        tools={path.name: path for path in paths},
    )
    (root / "manifest.json").write_text(
        encode_fast_proof_tools_manifest(manifest),
        encoding="utf-8",
    )
    return FastProofToolSet(
        source_sha=SOURCE_SHA,
        platform=PLATFORM,
        paths=paths,
    ), manifest


def test_prepare_workspace_materializes_exporter_and_seals_feature_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable-observer-db")
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"stable-wal")
    toolset, tool_manifest = _toolset(tmp_path)
    calls = []

    def _materialize(destination_root, *, expected_source_sha, expected_platform):
        calls.append(
            (Path(destination_root), expected_source_sha, expected_platform)
        )
        return toolset

    monkeypatch.setattr(
        workspace_module,
        "materialize_fast_proof_tools",
        _materialize,
    )
    destination = tmp_path / "workspace"

    artifact = prepare_fast_proof_workspace(
        database_path=database,
        destination=destination,
        tool_root=tmp_path / "proof-tools",
        expected_source_sha=SOURCE_SHA,
        expected_platform=PLATFORM,
        timeout_seconds=30,
    )
    reopened = read_fast_proof_workspace(destination)

    assert type(artifact) is FastProofWorkspaceArtifact
    assert reopened.manifest == artifact.manifest
    assert reopened.features == artifact.features
    assert artifact.manifest.schema_name == FAST_PROOF_WORKSPACE_SCHEMA_NAME
    assert artifact.manifest.schema_version == FAST_PROOF_WORKSPACE_SCHEMA_VERSION
    assert artifact.manifest.proof_tools_manifest_fingerprint_sha256 == (
        tool_manifest.manifest_fingerprint_sha256
    )
    assert artifact.manifest.exporter_sha256 == hashlib.sha256(
        toolset.paths[0].read_bytes()
    ).hexdigest()
    assert artifact.manifest.observer_database_wal_sha256 == hashlib.sha256(
        wal.read_bytes()
    ).hexdigest()
    assert artifact.manifest.feature_jsonl_sha256 == (
        artifact.features.source_sha256
    )
    assert artifact.manifest.feature_logical_fingerprint_sha256 == (
        artifact.features.logical_fingerprint_sha256
    )
    assert artifact.manifest.row_count == 2
    assert calls == [
        (
            tmp_path / "proof-tools",
            SOURCE_SHA,
            PLATFORM,
        )
    ]
    assert {path.name for path in destination.iterdir()} == {
        "features.jsonl",
        "manifest.json",
    }


def test_workspace_rejects_database_mutation_and_publishes_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"before")
    toolset, _ = _toolset(tmp_path, mutate_database=True)
    monkeypatch.setattr(
        workspace_module,
        "materialize_fast_proof_tools",
        lambda *_args, **_kwargs: toolset,
    )
    destination = tmp_path / "workspace"

    with pytest.raises(ValueError, match="database.*changed|source.*changed"):
        prepare_fast_proof_workspace(
            database_path=database,
            destination=destination,
            tool_root=tmp_path / "proof-tools",
            expected_source_sha=SOURCE_SHA,
            expected_platform=PLATFORM,
            timeout_seconds=30,
        )
    assert not destination.exists()


def test_workspace_rejects_exporter_failure_and_publishes_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable")
    toolset, _ = _toolset(tmp_path, exit_code=7)
    monkeypatch.setattr(
        workspace_module,
        "materialize_fast_proof_tools",
        lambda *_args, **_kwargs: toolset,
    )
    destination = tmp_path / "workspace"

    with pytest.raises(ValueError, match="exporter.*failed|exit"):
        prepare_fast_proof_workspace(
            database_path=database,
            destination=destination,
            tool_root=tmp_path / "proof-tools",
            expected_source_sha=SOURCE_SHA,
            expected_platform=PLATFORM,
            timeout_seconds=30,
        )
    assert not destination.exists()


def test_workspace_reader_rejects_feature_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable")
    toolset, _ = _toolset(tmp_path)
    monkeypatch.setattr(
        workspace_module,
        "materialize_fast_proof_tools",
        lambda *_args, **_kwargs: toolset,
    )
    destination = tmp_path / "workspace"
    prepare_fast_proof_workspace(
        database_path=database,
        destination=destination,
        tool_root=tmp_path / "proof-tools",
        expected_source_sha=SOURCE_SHA,
        expected_platform=PLATFORM,
        timeout_seconds=30,
    )

    feature_path = destination / "features.jsonl"
    feature_path.write_bytes(feature_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="fingerprint|hash|JSON"):
        read_fast_proof_workspace(destination)


def test_workspace_refuses_existing_destination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable")
    toolset, _ = _toolset(tmp_path)
    monkeypatch.setattr(
        workspace_module,
        "materialize_fast_proof_tools",
        lambda *_args, **_kwargs: toolset,
    )
    destination = tmp_path / "workspace"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="exists|overwrite"):
        prepare_fast_proof_workspace(
            database_path=database,
            destination=destination,
            tool_root=tmp_path / "proof-tools",
            expected_source_sha=SOURCE_SHA,
            expected_platform=PLATFORM,
            timeout_seconds=30,
        )


def test_workspace_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_proof_workspace.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
    ):
        assert forbidden not in source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fast-proof-workspace = "shreks_brain.fast_proof_workspace:main"'
        in pyproject
    )
