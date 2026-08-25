from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
_SPEC = importlib.util.spec_from_file_location("shreks_g2_release_bundle", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
release_bundle = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_bundle)


SOURCE_SHA = "a" * 40
PLATFORM = "x86_64-unknown-linux-gnu"
PAYLOADS = {
    "target/release/shreks-observe": b"observer-binary",
    "target/release/shreks-paper-evidence": b"evidence-binary",
    "deploy/systemd/shreks-observe.service": b"observe-unit\n",
    "deploy/systemd/shreks-paper-evidence.service": b"evidence-unit\n",
    "deploy/systemd/shreks-paper-campaign.service": b"campaign-unit\n",
    "deploy/systemd/shreks.target": b"target-unit\n",
    "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl": b"wheel-bytes",
}


def _write_payload_tree(root: Path) -> None:
    for relative, payload in PAYLOADS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _build_archive(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir(parents=True)
    _write_payload_tree(staging)
    manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)
    manifest_payload = release_bundle.encode_release_manifest(manifest)
    (staging / "RELEASE_MANIFEST.json").write_bytes(manifest_payload)

    manifest_path = tmp_path / "RELEASE_MANIFEST.json"
    manifest_path.write_bytes(manifest_payload)
    archive_path = tmp_path / f"shreks-release-{SOURCE_SHA}.tar.gz"
    archive_sha = release_bundle.write_release_archive(staging, manifest, archive_path)
    checksum_path = tmp_path / f"{archive_path.name}.sha256"
    checksum_path.write_text(f"{archive_sha}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, checksum_path, manifest_path, manifest


def test_source_sha_and_release_tag_are_exact():
    assert release_bundle.validate_source_sha(SOURCE_SHA) == SOURCE_SHA
    assert release_bundle.release_tag_for_sha(SOURCE_SHA) == f"shreks-{SOURCE_SHA}"

    for invalid in ("", "abc", "A" * 40, "a" * 39, "a" * 41, "g" * 40):
        with pytest.raises(release_bundle.ReleaseBundleError):
            release_bundle.validate_source_sha(invalid)


def test_manifest_is_canonical_exact_and_hashes_payloads(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_payload_tree(staging)

    manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)
    payload = release_bundle.encode_release_manifest(manifest)
    decoded = release_bundle.decode_release_manifest(payload)

    assert decoded == manifest
    assert manifest.schema_version == "g2-release-manifest-v1"
    assert manifest.source_sha == SOURCE_SHA
    assert manifest.platform == PLATFORM
    assert [entry.path for entry in manifest.files] == sorted(PAYLOADS)
    assert "RELEASE_MANIFEST.json" not in {entry.path for entry in manifest.files}

    expected = json.dumps(
        {
            "files": [
                {
                    "path": path,
                    "sha256": hashlib.sha256(PAYLOADS[path]).hexdigest(),
                    "size": len(PAYLOADS[path]),
                }
                for path in sorted(PAYLOADS)
            ],
            "platform": PLATFORM,
            "schema_version": "g2-release-manifest-v1",
            "source_sha": SOURCE_SHA,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    assert payload == expected
    release_bundle.verify_release_tree(staging, manifest)


def test_manifest_requires_exact_schema_keys_and_supported_platform(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_payload_tree(staging)
    manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)
    raw = json.loads(release_bundle.encode_release_manifest(manifest))

    for mutated in (
        {**raw, "extra": True},
        {key: value for key, value in raw.items() if key != "platform"},
        {**raw, "schema_version": "g2-release-manifest-v999"},
        {**raw, "platform": "aarch64-unknown-linux-gnu"},
    ):
        payload = json.dumps(mutated, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        with pytest.raises(release_bundle.ReleaseBundleError):
            release_bundle.decode_release_manifest(payload)


def test_manifest_requires_exact_payload_allowlist_and_one_wheel(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_payload_tree(staging)

    (staging / "unexpected.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)

    (staging / "unexpected.txt").unlink()
    (staging / "wheelhouse" / "second.whl").write_bytes(b"second")
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)


def test_release_tree_fails_closed_on_missing_or_tampered_payload(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_payload_tree(staging)
    manifest = release_bundle.build_release_manifest(staging, SOURCE_SHA, PLATFORM)

    (staging / "target/release/shreks-observe").write_bytes(b"tampered")
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.verify_release_tree(staging, manifest)

    _write_payload_tree(staging)
    (staging / "deploy/systemd/shreks.target").unlink()
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.verify_release_tree(staging, manifest)


def test_archive_round_trip_verifies_checksum_manifest_and_payloads(tmp_path: Path):
    archive_path, checksum_path, manifest_path, manifest = _build_archive(tmp_path)

    decoded = release_bundle.verify_release_archive(
        archive_path, checksum_path, manifest_path
    )

    assert decoded == manifest


def test_archive_rejects_checksum_or_external_manifest_mismatch(tmp_path: Path):
    archive_path, checksum_path, manifest_path, _ = _build_archive(tmp_path)

    checksum_path.write_text(f"{'0' * 64}  {archive_path.name}\n", encoding="utf-8")
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.verify_release_archive(archive_path, checksum_path, manifest_path)

    archive_path, checksum_path, manifest_path, _ = _build_archive(tmp_path / "second")
    manifest_path.write_bytes(manifest_path.read_bytes().replace(SOURCE_SHA.encode(), ("b" * 40).encode()))
    with pytest.raises(release_bundle.ReleaseBundleError):
        release_bundle.verify_release_archive(archive_path, checksum_path, manifest_path)


def _write_malicious_archive(path: Path, member: tarfile.TarInfo, payload: bytes = b"x") -> None:
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload) if member.isreg() else None)


def test_archive_rejects_path_traversal_absolute_paths_and_symlinks(tmp_path: Path):
    manifest_path = tmp_path / "RELEASE_MANIFEST.json"
    manifest_path.write_text("{}\n", encoding="utf-8")

    members = []
    traversal = tarfile.TarInfo("../escape")
    traversal.size = 1
    members.append(traversal)
    absolute = tarfile.TarInfo("/absolute")
    absolute.size = 1
    members.append(absolute)
    symlink = tarfile.TarInfo("target/release/shreks-observe")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "/tmp/escape"
    members.append(symlink)

    for index, member in enumerate(members):
        archive_path = tmp_path / f"malicious-{index}.tar.gz"
        _write_malicious_archive(archive_path, member)
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        checksum_path = tmp_path / f"malicious-{index}.sha256"
        checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
        with pytest.raises(release_bundle.ReleaseBundleError):
            release_bundle.verify_release_archive(archive_path, checksum_path, manifest_path)
