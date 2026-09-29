from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_release_authorization as authorization
from shreks_brain.fast_paper_production_authorization import (
    read_and_verify_fast_paper_production_authorization,
)


_SOURCE_SHA = "a" * 40
_TARGET_SHA = "b" * 40
_MANIFEST_FP = "c" * 64
_CHAMPION_FP = "d" * 64
_BINDING_FP = "e" * 64
_POLICY_FP = "f" * 64


def _document() -> dict[str, object]:
    return authorization.build_fast_paper_release_authorization(
        source_release_source_sha=_SOURCE_SHA,
        source_authorization_fingerprint_sha256="1" * 64,
        release_handoff_fingerprint_sha256="2" * 64,
        release_source_sha=_TARGET_SHA,
        manifest_fingerprint_sha256=_MANIFEST_FP,
        champion_version="champion-v1",
        champion_fingerprint_sha256=_CHAMPION_FP,
        action_policy_version=7,
        fast_run_id="fast-paper-release-b",
        binding_fingerprint_sha256=_BINDING_FP,
        execution_policy_fingerprint_sha256=_POLICY_FP,
        authorized_at_unix_ms=123_456,
    )


def _identity():
    return (
        SimpleNamespace(
            release_source_sha=_TARGET_SHA,
            manifest_fingerprint_sha256=_MANIFEST_FP,
            champion_version="champion-v1",
            champion_fingerprint_sha256=_CHAMPION_FP,
            action_policy=SimpleNamespace(version=7),
        ),
        SimpleNamespace(
            fast_run_id="fast-paper-release-b",
            binding_fingerprint_sha256=_BINDING_FP,
        ),
        SimpleNamespace(policy_fingerprint_sha256=_POLICY_FP),
    )


def test_release_authorization_round_trips_and_generic_verifier_accepts_it(
    tmp_path: Path,
) -> None:
    document = _document()
    path = tmp_path / "authorization.json"
    path.write_text(
        authorization.encode_fast_paper_release_authorization(document),
        encoding="utf-8",
    )
    manifest, binding, policy = _identity()

    restored = read_and_verify_fast_paper_production_authorization(
        path,
        manifest=manifest,
        binding=binding,
        execution_policy=policy,
    )

    assert restored == document
    assert restored["state"] == "AUTHORIZED_FAST_PAPER_RELEASE_UPGRADE"
    assert restored["production_paper_cutover"] == "GRANTED"
    assert restored["service_control_authority"] == "PROTECTED_FAST_RELEASE_ONLY"
    assert restored["signing_submission_authority"] == "NOT_GRANTED"
    assert restored["live_authority"] == "DISABLED"


def test_release_authorization_rejects_source_target_equality() -> None:
    with pytest.raises(
        authorization.FastPaperReleaseAuthorizationError,
        match="distinct target release",
    ):
        authorization.build_fast_paper_release_authorization(
            source_release_source_sha=_TARGET_SHA,
            source_authorization_fingerprint_sha256="1" * 64,
            release_handoff_fingerprint_sha256="2" * 64,
            release_source_sha=_TARGET_SHA,
            manifest_fingerprint_sha256=_MANIFEST_FP,
            champion_version="champion-v1",
            champion_fingerprint_sha256=_CHAMPION_FP,
            action_policy_version=7,
            fast_run_id="fast-paper-release-b",
            binding_fingerprint_sha256=_BINDING_FP,
            execution_policy_fingerprint_sha256=_POLICY_FP,
            authorized_at_unix_ms=123_456,
        )


def test_release_authorization_rejects_runtime_identity_drift() -> None:
    document = _document()
    manifest, binding, policy = _identity()

    with pytest.raises(
        authorization.FastPaperReleaseAuthorizationError,
        match="fast_run_id identity mismatch",
    ):
        authorization.verify_fast_paper_release_authorization(
            document,
            manifest=manifest,
            binding=SimpleNamespace(
                fast_run_id="different-run",
                binding_fingerprint_sha256=binding.binding_fingerprint_sha256,
            ),
            execution_policy=policy,
        )


def test_release_authorization_fingerprint_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    document = _document()
    payload = authorization.encode_fast_paper_release_authorization(
        document
    ).replace(
        document["authorization_fingerprint_sha256"],
        "0" * 64,
    )
    path = tmp_path / "authorization.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(
        authorization.FastPaperReleaseAuthorizationError,
        match="fingerprint",
    ):
        authorization.read_fast_paper_release_authorization(path)
