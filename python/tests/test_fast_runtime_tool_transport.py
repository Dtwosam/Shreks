from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain.fast_proof_tools import FAST_PROOF_TOOL_NAMES
from shreks_brain.fast_runtime_tools import (
    FAST_RUNTIME_FEATURE_TOOL_NAME,
    FAST_RUNTIME_TOOLS_SCHEMA_NAME,
    FAST_RUNTIME_TOOLS_SCHEMA_VERSION,
    build_fast_runtime_tools_manifest,
    decode_fast_runtime_tools_manifest,
    encode_fast_runtime_tools_manifest,
    materialize_fast_runtime_feature_tool_from_directory,
    stage_fast_runtime_tools_package,
    verify_fast_runtime_tools_package,
    verify_fast_runtime_tools_wheel,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_SCRIPT = _REPO_ROOT / "deploy" / "release" / "build_release.sh"
_RELEASE_BUNDLE = _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"


def _tool(tmp_path: Path) -> Path:
    path = tmp_path / FAST_RUNTIME_FEATURE_TOOL_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"runtime-feature-tool")
    path.chmod(0o700)
    return path


def test_runtime_tool_manifest_is_exact_canonical_and_separate_from_proof_v1(
    tmp_path: Path,
) -> None:
    assert FAST_PROOF_TOOL_NAMES == (
        "export_fast_training_features",
        "shreks-fast-campaign-decision",
        "shreks-fast-entry-authority",
    )

    tool = _tool(tmp_path)
    manifest = build_fast_runtime_tools_manifest(
        source_sha="a" * 40,
        platform="aarch64-unknown-linux-gnu",
        tool=tool,
    )
    payload = encode_fast_runtime_tools_manifest(manifest)

    assert decode_fast_runtime_tools_manifest(payload) == manifest
    assert manifest.schema_name == FAST_RUNTIME_TOOLS_SCHEMA_NAME
    assert manifest.schema_version == FAST_RUNTIME_TOOLS_SCHEMA_VERSION
    assert manifest.tool_name == FAST_RUNTIME_FEATURE_TOOL_NAME
    assert manifest.size == tool.stat().st_size
    assert manifest.sha256 == hashlib.sha256(tool.read_bytes()).hexdigest()


def test_runtime_tool_package_and_materialization_are_private_and_tamper_evident(
    tmp_path: Path,
) -> None:
    tool = _tool(tmp_path / "native")
    package = tmp_path / "package"
    manifest = stage_fast_runtime_tools_package(
        source_sha="b" * 40,
        platform="x86_64-unknown-linux-gnu",
        tool=tool,
        destination=package,
    )

    assert verify_fast_runtime_tools_package(
        package,
        expected_source_sha="b" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    ) == manifest

    root = tmp_path / "materialized"
    materialized = materialize_fast_runtime_feature_tool_from_directory(
        package,
        root,
        expected_source_sha="b" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    )
    assert materialized.name == FAST_RUNTIME_FEATURE_TOOL_NAME
    assert stat.S_IMODE(materialized.stat().st_mode) == 0o700
    assert materialized.read_bytes() == tool.read_bytes()

    again = materialize_fast_runtime_feature_tool_from_directory(
        package,
        root,
        expected_source_sha="b" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    )
    assert again == materialized

    materialized.write_bytes(b"drift")
    with pytest.raises(ValueError, match="fingerprint|manifest|materialized"):
        materialize_fast_runtime_feature_tool_from_directory(
            package,
            root,
            expected_source_sha="b" * 40,
            expected_platform="x86_64-unknown-linux-gnu",
        )


def test_runtime_tool_wheel_verifier_requires_exact_separate_package(
    tmp_path: Path,
) -> None:
    tool = _tool(tmp_path / "native")
    package = tmp_path / "package"
    stage_fast_runtime_tools_package(
        source_sha="c" * 40,
        platform="aarch64-unknown-linux-gnu",
        tool=tool,
        destination=package,
    )

    wheel = tmp_path / "shreks_brain-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(
                path,
                f"shreks_brain/_sealed_fast_runtime_tools/{path.name}",
            )

    verify_fast_runtime_tools_wheel(
        wheel,
        expected_source_sha="c" * 40,
        expected_platform="aarch64-unknown-linux-gnu",
        expected_tool=tool,
    )

    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(
            "shreks_brain/_sealed_fast_runtime_tools/"
            f"{FAST_RUNTIME_FEATURE_TOOL_NAME}.bin",
            b"tampered",
        )
    with pytest.raises(ValueError):
        verify_fast_runtime_tools_wheel(
            wheel,
            expected_source_sha="c" * 40,
            expected_platform="aarch64-unknown-linux-gnu",
        )


def test_release_build_transports_runtime_tool_inside_existing_hashed_wheel_only() -> None:
    script = _BUILD_SCRIPT.read_text(encoding="utf-8")
    bundle = _RELEASE_BUNDLE.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    assert f"--bin {FAST_RUNTIME_FEATURE_TOOL_NAME}" in script
    assert f"target/release/{FAST_RUNTIME_FEATURE_TOOL_NAME}" in script
    for required in (
        "stage_fast_runtime_tools_package",
        "verify_fast_runtime_tools_wheel",
        "_sealed_fast_runtime_tools",
        'shreks_brain._sealed_fast_runtime_tools',
    ):
        assert required in (script + "\n" + pyproject)

    assert f"target/release/{FAST_RUNTIME_FEATURE_TOOL_NAME}" not in bundle
