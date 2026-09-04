from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from shreks_brain.fast_proof_tools import (
    FAST_PROOF_TOOL_NAMES,
    FAST_PROOF_TOOLS_SCHEMA_NAME,
    FAST_PROOF_TOOLS_SCHEMA_VERSION,
    build_fast_proof_tools_manifest,
    decode_fast_proof_tools_manifest,
    encode_fast_proof_tools_manifest,
    materialize_fast_proof_tools_from_directory,
    stage_fast_proof_tools_package,
    verify_fast_proof_tools_package,
    verify_fast_proof_tools_wheel,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_SCRIPT = _REPO_ROOT / "deploy" / "release" / "build_release.sh"
_RELEASE_BUNDLE = _REPO_ROOT / "deploy" / "release" / "release_bundle.py"
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"


def _tools(tmp_path: Path) -> dict[str, Path]:
    values: dict[str, Path] = {}
    for index, name in enumerate(FAST_PROOF_TOOL_NAMES):
        path = tmp_path / name
        path.write_bytes(f"tool-{index}-{name}".encode())
        values[name] = path
    return values


def test_manifest_is_canonical_exact_and_authenticated(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    manifest = build_fast_proof_tools_manifest(
        source_sha="a" * 40,
        platform="aarch64-unknown-linux-gnu",
        tools=tools,
    )
    payload = encode_fast_proof_tools_manifest(manifest)

    assert payload == (
        json.dumps(
            json.loads(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    assert decode_fast_proof_tools_manifest(payload) == manifest
    assert manifest.schema_name == FAST_PROOF_TOOLS_SCHEMA_NAME
    assert manifest.schema_version == FAST_PROOF_TOOLS_SCHEMA_VERSION
    assert tuple(value.name for value in manifest.tools) == FAST_PROOF_TOOL_NAMES

    for value in manifest.tools:
        assert value.sha256 == hashlib.sha256(tools[value.name].read_bytes()).hexdigest()
        assert value.size == tools[value.name].stat().st_size


def test_manifest_rejects_unknown_missing_duplicate_and_tampered_tool_entries(
    tmp_path: Path,
) -> None:
    tools = _tools(tmp_path)
    manifest = build_fast_proof_tools_manifest(
        source_sha="b" * 40,
        platform="x86_64-unknown-linux-gnu",
        tools=tools,
    )
    raw = json.loads(encode_fast_proof_tools_manifest(manifest))

    mutations = []

    unknown = json.loads(json.dumps(raw))
    unknown["tools"].append(
        {"name": "unexpected", "sha256": "0" * 64, "size": 1}
    )
    mutations.append(unknown)

    missing = json.loads(json.dumps(raw))
    missing["tools"].pop()
    mutations.append(missing)

    duplicate = json.loads(json.dumps(raw))
    duplicate["tools"][-1] = duplicate["tools"][0]
    mutations.append(duplicate)

    tampered = json.loads(json.dumps(raw))
    tampered["tools"][0]["sha256"] = "0" * 64
    mutations.append(tampered)

    for value in mutations:
        payload = (
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        with pytest.raises(ValueError):
            decode_fast_proof_tools_manifest(payload)


def test_stage_and_verify_package_bind_exact_native_tool_bytes(tmp_path: Path) -> None:
    tools = _tools(tmp_path / "native")
    package = tmp_path / "package"

    manifest = stage_fast_proof_tools_package(
        source_sha="c" * 40,
        platform="aarch64-unknown-linux-gnu",
        tools=tools,
        destination=package,
    )

    assert sorted(path.name for path in package.iterdir()) == sorted(
        ["__init__.py", "manifest.json"]
        + [f"{name}.bin" for name in FAST_PROOF_TOOL_NAMES]
    )
    assert verify_fast_proof_tools_package(
        package,
        expected_source_sha="c" * 40,
        expected_platform="aarch64-unknown-linux-gnu",
    ) == manifest

    (package / f"{FAST_PROOF_TOOL_NAMES[0]}.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="fingerprint|SHA|size"):
        verify_fast_proof_tools_package(
            package,
            expected_source_sha="c" * 40,
            expected_platform="aarch64-unknown-linux-gnu",
        )


def test_materialization_is_private_idempotent_and_refuses_drift(
    tmp_path: Path,
) -> None:
    tools = _tools(tmp_path / "native")
    package = tmp_path / "package"
    stage_fast_proof_tools_package(
        source_sha="d" * 40,
        platform="x86_64-unknown-linux-gnu",
        tools=tools,
        destination=package,
    )

    root = tmp_path / "materialized"
    toolset = materialize_fast_proof_tools_from_directory(
        package,
        root,
        expected_source_sha="d" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    )

    assert toolset.source_sha == "d" * 40
    assert toolset.platform == "x86_64-unknown-linux-gnu"
    assert tuple(path.name for path in toolset.paths) == FAST_PROOF_TOOL_NAMES
    for path in toolset.paths:
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o700

    again = materialize_fast_proof_tools_from_directory(
        package,
        root,
        expected_source_sha="d" * 40,
        expected_platform="x86_64-unknown-linux-gnu",
    )
    assert again == toolset

    toolset.paths[0].write_bytes(b"local-drift")
    with pytest.raises(ValueError, match="materialized|fingerprint|SHA|size"):
        materialize_fast_proof_tools_from_directory(
            package,
            root,
            expected_source_sha="d" * 40,
            expected_platform="x86_64-unknown-linux-gnu",
        )


def test_wheel_verifier_requires_exact_embedded_package(tmp_path: Path) -> None:
    tools = _tools(tmp_path / "native")
    package = tmp_path / "package"
    stage_fast_proof_tools_package(
        source_sha="e" * 40,
        platform="aarch64-unknown-linux-gnu",
        tools=tools,
        destination=package,
    )

    wheel = tmp_path / "shreks_brain-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in sorted(package.iterdir()):
            archive.write(
                path,
                f"shreks_brain/_sealed_fast_tools/{path.name}",
            )

    manifest = verify_fast_proof_tools_wheel(
        wheel,
        expected_source_sha="e" * 40,
        expected_platform="aarch64-unknown-linux-gnu",
    )
    assert tuple(value.name for value in manifest.tools) == FAST_PROOF_TOOL_NAMES

    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(
            f"shreks_brain/_sealed_fast_tools/{FAST_PROOF_TOOL_NAMES[0]}.bin",
            b"tampered",
        )
    with pytest.raises(ValueError):
        verify_fast_proof_tools_wheel(
            wheel,
            expected_source_sha="e" * 40,
            expected_platform="aarch64-unknown-linux-gnu",
        )


def test_release_build_transports_proof_tools_inside_existing_hashed_wheel_only() -> None:
    script = _BUILD_SCRIPT.read_text(encoding="utf-8")
    bundle = _RELEASE_BUNDLE.read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")

    for name in FAST_PROOF_TOOL_NAMES:
        assert f"--bin {name}" in script
        assert f"target/release/{name}" in script

    for required in (
        "stage_fast_proof_tools_package",
        "verify_fast_proof_tools_wheel",
        "_sealed_fast_tools",
        "[tool.setuptools.package-data]",
        'shreks_brain._sealed_fast_tools',
    ):
        assert required in (script + "\n" + pyproject)

    # Backward compatibility: old root G2 verifiers still see the historical
    # top-level allowlist. Proof tools must never become top-level release payloads.
    assert "target/release/export_fast_training_features" not in bundle
    assert "target/release/shreks-fast-entry-authority" not in bundle
    assert "target/release/shreks-fast-campaign-decision" not in bundle


def test_transport_module_has_no_runtime_trading_or_network_authority() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_proof_tools.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "httpx",
        "sqlite3",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
