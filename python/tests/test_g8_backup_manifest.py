from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.backup import (
    BACKUP_MANIFEST_SCHEMA_VERSION,
    BackupArtifactRecord,
    BackupArtifactRole,
    BackupManifest,
    BackupManifestError,
    decode_backup_manifest,
    encode_backup_manifest,
    verify_backup_bundle,
)


_FINGERPRINT = "ab" * 32


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record(
    role: BackupArtifactRole,
    relative_path: str,
    payload: bytes,
    *,
    required: bool = True,
) -> BackupArtifactRecord:
    return BackupArtifactRecord(
        role=role,
        relative_path=relative_path,
        sha256=_sha(payload),
        byte_size=len(payload),
        required=required,
    )


def _manifest(records: tuple[BackupArtifactRecord, ...]) -> BackupManifest:
    return BackupManifest(
        schema_version=BACKUP_MANIFEST_SCHEMA_VERSION,
        created_at_unix_ms=1_787_752_800_000,
        paper_run_id="paper-run-g8-test",
        campaign_manifest_fingerprint_sha256=_FINGERPRINT,
        sqlite_quick_check="ok",
        completed=True,
        artifacts=records,
    )


def _write_valid_bundle(tmp_path: Path) -> tuple[Path, BackupManifest]:
    bundle = tmp_path / "bundle"
    artifacts = bundle / "artifacts"
    artifacts.mkdir(parents=True)

    db_path = artifacts / "operational.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE proof (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO proof(value) VALUES ('durable')")
        connection.commit()
    finally:
        connection.close()

    payloads = {
        BackupArtifactRole.OPERATIONAL_SQLITE: db_path.read_bytes(),
        BackupArtifactRole.E11_EVIDENCE: b'{"e11":"evidence"}\n',
        BackupArtifactRole.CAMPAIGN_MANIFEST: b'{"manifest":"sealed"}\n',
        BackupArtifactRole.OPERATOR_RISK_CONTROL: b'{"halt":true}\n',
        BackupArtifactRole.ALERT_STATE: b'{"pending":["critical"]}\n',
    }
    paths = {
        BackupArtifactRole.OPERATIONAL_SQLITE: "artifacts/operational.sqlite3",
        BackupArtifactRole.E11_EVIDENCE: "artifacts/e11.json",
        BackupArtifactRole.CAMPAIGN_MANIFEST: "artifacts/paper-campaign.json",
        BackupArtifactRole.OPERATOR_RISK_CONTROL: "artifacts/operator-control.json",
        BackupArtifactRole.ALERT_STATE: "artifacts/alerts-state.json",
    }
    for role, payload in payloads.items():
        if role is BackupArtifactRole.OPERATIONAL_SQLITE:
            continue
        (bundle / paths[role]).write_bytes(payload)

    records = tuple(
        _record(
            role,
            paths[role],
            payload,
            required=role is not BackupArtifactRole.ALERT_STATE,
        )
        for role, payload in payloads.items()
    )
    manifest = _manifest(records)
    (bundle / "manifest.json").write_bytes(encode_backup_manifest(manifest))
    return bundle, manifest


def test_manifest_round_trip_is_exact_canonical_and_versioned() -> None:
    records = (
        _record(
            BackupArtifactRole.OPERATIONAL_SQLITE,
            "artifacts/operational.sqlite3",
            b"db",
        ),
        _record(BackupArtifactRole.E11_EVIDENCE, "artifacts/e11.json", b"e11"),
        _record(
            BackupArtifactRole.CAMPAIGN_MANIFEST,
            "artifacts/paper-campaign.json",
            b"manifest",
        ),
        _record(
            BackupArtifactRole.OPERATOR_RISK_CONTROL,
            "artifacts/operator-control.json",
            b"risk",
        ),
    )
    manifest = _manifest(records)

    encoded = encode_backup_manifest(manifest)
    decoded = decode_backup_manifest(encoded)

    assert decoded == manifest
    assert encode_backup_manifest(decoded) == encoded
    document = json.loads(encoded)
    assert document["schema_version"] == "g8-backup-bundle-v1"
    assert encoded == json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def test_artifact_role_vocabulary_excludes_secrets_telemetry_and_live_authority() -> None:
    assert {role.value for role in BackupArtifactRole} == {
        "operational_sqlite",
        "e11_evidence",
        "campaign_manifest",
        "operator_risk_control",
        "alert_state",
    }
    vocabulary = " ".join(role.value for role in BackupArtifactRole).lower()
    for forbidden in (
        "password",
        "token",
        "api_key",
        "private_key",
        "seed",
        "wallet",
        "telemetry",
        "live",
        "sign",
        "submit",
    ):
        assert forbidden not in vocabulary


@pytest.mark.parametrize(
    "relative_path",
    (
        "",
        "/absolute",
        "../escape",
        "artifacts/../escape",
        "artifacts//double",
        "./artifacts/file",
        "artifacts/./file",
        "artifacts/file/",
        "artifacts\\windows",
    ),
)
def test_artifact_record_rejects_unsafe_relative_paths(relative_path: str) -> None:
    with pytest.raises(BackupManifestError):
        BackupArtifactRecord(
            role=BackupArtifactRole.E11_EVIDENCE,
            relative_path=relative_path,
            sha256="00" * 32,
            byte_size=1,
            required=True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sha256", "not-a-sha"),
        ("byte_size", -1),
        ("byte_size", True),
        ("required", 1),
    ),
)
def test_artifact_record_rejects_invalid_hash_size_and_required_types(
    field: str,
    value: object,
) -> None:
    kwargs: dict[str, object] = {
        "role": BackupArtifactRole.E11_EVIDENCE,
        "relative_path": "artifacts/e11.json",
        "sha256": "00" * 32,
        "byte_size": 1,
        "required": True,
    }
    kwargs[field] = value
    with pytest.raises(BackupManifestError):
        BackupArtifactRecord(**kwargs)


def test_manifest_rejects_duplicate_roles_and_duplicate_paths() -> None:
    one = _record(BackupArtifactRole.E11_EVIDENCE, "artifacts/e11.json", b"a")
    duplicate_role = _record(
        BackupArtifactRole.E11_EVIDENCE,
        "artifacts/other-e11.json",
        b"b",
    )
    duplicate_path = _record(
        BackupArtifactRole.CAMPAIGN_MANIFEST,
        "artifacts/e11.json",
        b"c",
    )

    with pytest.raises(BackupManifestError):
        _manifest((one, duplicate_role))
    with pytest.raises(BackupManifestError):
        _manifest((one, duplicate_path))


def test_manifest_requires_core_paper_truth_roles_and_operator_state() -> None:
    records = (
        _record(
            BackupArtifactRole.OPERATIONAL_SQLITE,
            "artifacts/operational.sqlite3",
            b"db",
        ),
        _record(BackupArtifactRole.E11_EVIDENCE, "artifacts/e11.json", b"e11"),
        _record(
            BackupArtifactRole.CAMPAIGN_MANIFEST,
            "artifacts/paper-campaign.json",
            b"manifest",
        ),
    )

    with pytest.raises(BackupManifestError):
        _manifest(records)


def test_alert_state_is_the_only_optional_role_in_v1() -> None:
    records = (
        _record(
            BackupArtifactRole.OPERATIONAL_SQLITE,
            "artifacts/operational.sqlite3",
            b"db",
        ),
        _record(BackupArtifactRole.E11_EVIDENCE, "artifacts/e11.json", b"e11"),
        _record(
            BackupArtifactRole.CAMPAIGN_MANIFEST,
            "artifacts/paper-campaign.json",
            b"manifest",
        ),
        _record(
            BackupArtifactRole.OPERATOR_RISK_CONTROL,
            "artifacts/operator-control.json",
            b"risk",
        ),
        _record(
            BackupArtifactRole.ALERT_STATE,
            "artifacts/alerts-state.json",
            b"alerts",
            required=False,
        ),
    )
    assert _manifest(records).artifacts[-1].required is False

    for index in range(4):
        mutated = list(records)
        record = mutated[index]
        mutated[index] = BackupArtifactRecord(
            role=record.role,
            relative_path=record.relative_path,
            sha256=record.sha256,
            byte_size=record.byte_size,
            required=False,
        )
        with pytest.raises(BackupManifestError):
            _manifest(tuple(mutated))


def test_decoder_rejects_unknown_extra_noncanonical_and_nonfinite_documents() -> None:
    manifest = _manifest(
        (
            _record(
                BackupArtifactRole.OPERATIONAL_SQLITE,
                "artifacts/operational.sqlite3",
                b"db",
            ),
            _record(BackupArtifactRole.E11_EVIDENCE, "artifacts/e11.json", b"e11"),
            _record(
                BackupArtifactRole.CAMPAIGN_MANIFEST,
                "artifacts/paper-campaign.json",
                b"manifest",
            ),
            _record(
                BackupArtifactRole.OPERATOR_RISK_CONTROL,
                "artifacts/operator-control.json",
                b"risk",
            ),
        )
    )
    document = json.loads(encode_backup_manifest(manifest))

    extra = {**document, "unexpected": True}
    with pytest.raises(BackupManifestError):
        decode_backup_manifest(json.dumps(extra, sort_keys=True, separators=(",", ":")))

    unknown_role = json.loads(encode_backup_manifest(manifest))
    unknown_role["artifacts"][0]["role"] = "wallet_secret"
    with pytest.raises(BackupManifestError):
        decode_backup_manifest(
            json.dumps(unknown_role, sort_keys=True, separators=(",", ":"))
        )

    pretty = json.dumps(document, indent=2)
    with pytest.raises(BackupManifestError):
        decode_backup_manifest(pretty)

    nonfinite = encode_backup_manifest(manifest).decode("utf-8").replace(
        '"created_at_unix_ms":1787752800000',
        '"created_at_unix_ms":NaN',
    )
    with pytest.raises(BackupManifestError):
        decode_backup_manifest(nonfinite)


def test_bundle_verifier_accepts_exact_complete_bundle(tmp_path: Path) -> None:
    bundle, expected = _write_valid_bundle(tmp_path)

    verified = verify_backup_bundle(bundle)

    assert verified == expected


@pytest.mark.parametrize(
    "mutation",
    ("missing", "hash", "size", "extra"),
)
def test_bundle_verifier_rejects_partial_tampered_or_extra_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle, manifest = _write_valid_bundle(tmp_path)
    e11 = bundle / "artifacts/e11.json"

    if mutation == "missing":
        e11.unlink()
    elif mutation == "hash":
        e11.write_bytes(b"tampered")
    elif mutation == "size":
        document = json.loads(encode_backup_manifest(manifest))
        document["artifacts"][1]["byte_size"] += 1
        (bundle / "manifest.json").write_bytes(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    else:
        (bundle / "artifacts/untracked.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(BackupManifestError):
        verify_backup_bundle(bundle)


def test_bundle_verifier_rejects_symlinked_artifact(tmp_path: Path) -> None:
    bundle, _manifest_value = _write_valid_bundle(tmp_path)
    e11 = bundle / "artifacts/e11.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(e11.read_bytes())
    e11.unlink()
    try:
        os.symlink(outside, e11)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(BackupManifestError):
        verify_backup_bundle(bundle)


def test_bundle_verifier_rejects_corrupt_sqlite_even_when_hash_matches(tmp_path: Path) -> None:
    bundle, manifest = _write_valid_bundle(tmp_path)
    db_path = bundle / "artifacts/operational.sqlite3"
    corrupt = b"not a sqlite database"
    db_path.write_bytes(corrupt)

    records = []
    for record in manifest.artifacts:
        if record.role is BackupArtifactRole.OPERATIONAL_SQLITE:
            records.append(
                BackupArtifactRecord(
                    role=record.role,
                    relative_path=record.relative_path,
                    sha256=_sha(corrupt),
                    byte_size=len(corrupt),
                    required=record.required,
                )
            )
        else:
            records.append(record)
    rewritten = _manifest(tuple(records))
    (bundle / "manifest.json").write_bytes(encode_backup_manifest(rewritten))

    with pytest.raises(BackupManifestError):
        verify_backup_bundle(bundle)
