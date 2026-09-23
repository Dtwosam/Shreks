from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import (
    g1c_v2_paper_manifest_manager_installation_proof as installation_proof,
)
from shreks_brain import g1c_v2_paper_manifest_manager_update as updater

from test_g1c_v2_paper_manifest_manager_installation_proof import _layout


PRIOR_RELEASE_SHA = "b" * 40


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _prior_proof(
    *,
    setup,
    old_payload: bytes,
    path: Path,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_name": installation_proof._PROOF_SCHEMA,
        "schema_version": installation_proof._SCHEMA_VERSION,
        "status": "VERIFIED",
        "release_source_sha": PRIOR_RELEASE_SHA,
        "release_directory": f"/opt/shreks/releases/{PRIOR_RELEASE_SHA}",
        "wheel_relative_path": "wheelhouse/shreks_brain-0.1.0-py3-none-any.whl",
        "wheel_sha256": "1" * 64,
        "manager_sha256": hashlib.sha256(old_payload).hexdigest(),
        "manager_destination": str(setup["destination"]),
        "destination_uid": installer._DESTINATION_UID,
        "destination_gid": installer._DESTINATION_GID,
        "destination_mode": "0755",
        "preinstall_snapshot_fingerprint_sha256": "2" * 64,
        "installer_receipt_sha256": "3" * 64,
        "campaign_manifest_sha256": "4" * 64,
        "campaign_manifest_unchanged": True,
        "deploy_sudoers_sha256": "5" * 64,
        "deploy_sudoers_unchanged": True,
        "service_lifecycle_unchanged": True,
        "proof_fingerprint_sha256": "0" * 64,
        "installation_authority": "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    document["proof_fingerprint_sha256"] = installation_proof._fingerprint(
        document,
        "proof_fingerprint_sha256",
    )
    path.write_bytes(_canonical(document))
    path.chmod(0o600)
    return document


def test_update_replaces_only_prior_verified_helper_with_current_release_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    old_payload = (
        b"#!/opt/shreks/current/.venv/bin/python\n"
        b"# prior verified helper\n"
    )
    setup["destination"].write_bytes(old_payload)
    setup["destination"].chmod(0o755)

    prior_path = tmp_path / "prior-installation-proof.json"
    prior = _prior_proof(
        setup=setup,
        old_payload=old_payload,
        path=prior_path,
    )

    receipt = updater.update_release_bound_paper_manifest_manager(
        expected_release_source_sha=installer_test_release_sha(),
        prior_installation_proof_path=prior_path,
        paths=setup["install_paths"],
        runtime_executable=setup["runtime_python"],
    )

    assert receipt["status"] == "UPDATED"
    assert receipt["prior_release_source_sha"] == PRIOR_RELEASE_SHA
    assert receipt["prior_manager_sha256"] == prior["manager_sha256"]
    assert receipt["manager_sha256"] == hashlib.sha256(
        setup["manager_payload"]
    ).hexdigest()
    assert receipt["helper_update_authority"] == (
        "EXERCISED_EXACT_RELEASE_BOUND_HELPER_REPLACEMENT_ONLY"
    )
    assert receipt["manifest_rotation_authority"] == "NOT_GRANTED"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"

    assert setup["destination"].read_bytes() == setup["manager_payload"]
    metadata = setup["destination"].stat()
    assert metadata.st_uid == os.getuid()
    assert metadata.st_gid == os.getgid()
    assert stat.S_IMODE(metadata.st_mode) == 0o755


def test_update_rejects_helper_drift_from_prior_proof_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    old_payload = (
        b"#!/opt/shreks/current/.venv/bin/python\n"
        b"# prior verified helper\n"
    )
    setup["destination"].write_bytes(old_payload)
    setup["destination"].chmod(0o755)
    prior_path = tmp_path / "prior-installation-proof.json"
    _prior_proof(
        setup=setup,
        old_payload=old_payload,
        path=prior_path,
    )

    drift = old_payload + b"# drift\n"
    setup["destination"].write_bytes(drift)
    setup["destination"].chmod(0o755)

    with pytest.raises(
        updater.PaperManifestManagerUpdateError,
        match="does not match prior verified",
    ):
        updater.update_release_bound_paper_manifest_manager(
            expected_release_source_sha=installer_test_release_sha(),
            prior_installation_proof_path=prior_path,
            paths=setup["install_paths"],
            runtime_executable=setup["runtime_python"],
        )

    assert setup["destination"].read_bytes() == drift


def test_update_rejects_nonverified_prior_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    old_payload = (
        b"#!/opt/shreks/current/.venv/bin/python\n"
        b"# prior verified helper\n"
    )
    setup["destination"].write_bytes(old_payload)
    setup["destination"].chmod(0o755)
    prior_path = tmp_path / "prior-installation-proof.json"
    document = _prior_proof(
        setup=setup,
        old_payload=old_payload,
        path=prior_path,
    )
    document["status"] = "FAILED"
    document["proof_fingerprint_sha256"] = "0" * 64
    document["proof_fingerprint_sha256"] = installation_proof._fingerprint(
        document,
        "proof_fingerprint_sha256",
    )
    prior_path.write_bytes(_canonical(document))
    prior_path.chmod(0o600)

    with pytest.raises(
        updater.PaperManifestManagerUpdateError,
        match="status is not acceptable",
    ):
        updater.update_release_bound_paper_manifest_manager(
            expected_release_source_sha=installer_test_release_sha(),
            prior_installation_proof_path=prior_path,
            paths=setup["install_paths"],
            runtime_executable=setup["runtime_python"],
        )

    assert setup["destination"].read_bytes() == old_payload


def test_update_authority_firewall() -> None:
    source = Path(updater.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "/etc/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert "EXERCISED_EXACT_RELEASE_BOUND_HELPER_REPLACEMENT_ONLY" in source
    assert '"manifest_rotation_authority": _NOT_GRANTED' in source
    assert '"paper_promotion_authority": _BLOCKED' in source
    assert '"live_authority": _DISABLED' in source


def installer_test_release_sha() -> str:
    from test_g1c_v2_paper_manifest_manager_installation_proof import RELEASE_SHA

    return RELEASE_SHA
