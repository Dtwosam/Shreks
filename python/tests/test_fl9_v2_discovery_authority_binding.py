from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fl9_v2_discovery_authority_binding import (
    DiscoveryAuthorityBindingError,
    bind_fl9_v2_discovery_authority,
    decode_fl9_v2_discovery_authority_binding,
)


SOURCE_SHA = "2" * 40
COHORT_FP = "a" * 64
AUTHORITY_GROUP_FP = "b" * 64
REQUEST_FP = "c" * 64
AUTHORITY_POLICY_FP = "d" * 64
RUNTIME_FP = "e" * 64
HYDRATION_FP = "f" * 64
WSOL = "So11111111111111111111111111111111111111112"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _candidate(
    *,
    runtime_fp: str = RUNTIME_FP,
    hydration_fp: str = HYDRATION_FP,
    source_path: str = "/etc/shreks/paper-campaign.json",
    source_kind: str = "active",
    backup_bundle_path: str | None = None,
    compatibility: str = "COMPATIBLE",
) -> dict[str, object]:
    return {
        "source_kind": source_kind,
        "source_path": source_path,
        "backup_bundle_path": backup_bundle_path,
        "backup_created_at_unix_ms": None,
        "authentication": "AUTHENTICATED",
        "compatibility": compatibility,
        "paper_run_id": "paper-123",
        "runtime_manifest_fingerprint_sha256": runtime_fp,
        "hydration_policy_fingerprint_sha256": hydration_fp,
        "regime_quote_asset_mint": WSOL,
        "safety_probe_output_mint": WSOL,
        "quote_asset_mint": WSOL,
        "quote_asset_decimals": 9,
        "quote_provider": "jupiter",
    }


def _result(
    *,
    status: str = "FOUND_COMPATIBLE",
    candidates: list[dict[str, object]] | None = None,
    expected_sha: str = SOURCE_SHA,
    observed_sha: str = SOURCE_SHA,
    authority_group_count: int = 1,
    authority_groups: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if candidates is None:
        candidates = [_candidate()]
    if authority_groups is None:
        authority_groups = [
            {
                "authority_group_fingerprint_sha256": AUTHORITY_GROUP_FP,
                "request_count": 1,
                "request_paths": ["/var/lib/shreks/fl9-v2-proof/v2-first-champion-request.json"],
            }
        ]
    compatible = sum(item["compatibility"] == "COMPATIBLE" for item in candidates)
    return {
        "schema_name": "shreks.fl9_v2_discovery_control_result",
        "schema_version": 1,
        "request_id": "gha-777-1",
        "expected_release_sha": expected_sha,
        "observed_release_sha": observed_sha,
        "request_candidate_count": 1,
        "authenticated_authority_count": 1,
        "rejected_authority_count": 0,
        "authority_group_count": authority_group_count,
        "authority_groups": authority_groups,
        "status": status,
        "selected_request_path": "/var/lib/shreks/fl9-v2-proof/v2-first-champion-request.json",
        "selected_request_fingerprint_sha256": REQUEST_FP,
        "discovery_report": {
            "schema_name": "shreks.fl9_v2_runtime_manifest_discovery",
            "schema_version": 2,
            "status": status,
            "cohort_quote_mint": WSOL,
            "candidate_count": len(candidates),
            "compatible_candidate_count": compatible,
            "candidates": candidates,
            "non_manifest_input_authority": {
                "authority_kind": "v2_host_request",
                "request_path": "/var/lib/shreks/fl9-v2-proof/v2-first-champion-request.json",
                "request_fingerprint_sha256": REQUEST_FP,
                "request_release_source_sha": "1" * 40,
                "cohort_artifact_fingerprint_sha256": COHORT_FP,
                "hydration_policy_path": "/var/lib/shreks/fl9-v2-proof/hydration-policy.json",
                "hydration_policy_fingerprint_sha256": AUTHORITY_POLICY_FP,
                "hydration_policy_version": "fl9-runtime-context-v1",
                "strategy_families": ["fresh_launch_continuation"],
                "max_exit_quote_age_ms": 2000,
                "execution_cost_policy_version": "paper-cost-policy-v1",
                "expected_round_trip_cost_bps": None,
            },
        },
    }


def _write_result(path: Path, document: dict[str, object], *, canonical: bool = True) -> None:
    if canonical:
        payload = _canonical(document)
    else:
        payload = json.dumps(document, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")


def test_single_compatible_candidate_binds_canonical_immutable_artifact(tmp_path: Path) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    document = _result()
    _write_result(source, document)

    artifact = bind_fl9_v2_discovery_authority(
        discovery_result_path=source,
        destination=destination,
    )

    assert artifact["schema_name"] == "shreks.fl9_v2_discovery_authority_binding"
    assert artifact["schema_version"] == 1
    assert artifact["request_id"] == "gha-777-1"
    assert artifact["release_source_sha"] == SOURCE_SHA
    assert artifact["cohort_artifact_fingerprint_sha256"] == COHORT_FP
    assert artifact["authority_group_fingerprint_sha256"] == AUTHORITY_GROUP_FP
    assert artifact["selected_request_fingerprint_sha256"] == REQUEST_FP
    assert artifact["runtime_manifest_fingerprint_sha256"] == RUNTIME_FP
    assert artifact["hydration_policy_fingerprint_sha256"] == HYDRATION_FP
    assert artifact["runtime_manifest_source_path"] == "/etc/shreks/paper-campaign.json"
    assert artifact["backup_bundle_path"] is None
    assert artifact["quote_asset_mint"] == WSOL
    assert artifact["quote_asset_decimals"] == 9
    assert artifact["quote_provider"] == "jupiter"
    assert artifact["discovery_result_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(artifact["binding_fingerprint_sha256"]) == 64

    assert destination.read_text(encoding="utf-8") == _canonical(artifact)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert decode_fl9_v2_discovery_authority_binding(destination.read_text(encoding="utf-8")) == artifact


@pytest.mark.parametrize(
    "status",
    [
        "HOLD_NO_REQUEST_AUTHORITY",
        "HOLD_AMBIGUOUS_REQUEST_AUTHORITY",
        "HOLD_NO_COMPATIBLE",
        "FAILED",
    ],
)
def test_non_found_result_is_never_bindable(tmp_path: Path, status: str) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    document = _result(status=status, candidates=[])
    if status in {"HOLD_NO_REQUEST_AUTHORITY", "HOLD_AMBIGUOUS_REQUEST_AUTHORITY"}:
        document.pop("selected_request_path")
        document.pop("selected_request_fingerprint_sha256")
        document.pop("discovery_report")
    _write_result(source, document)

    with pytest.raises(DiscoveryAuthorityBindingError):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )
    assert not destination.exists()


def test_release_binding_must_match_exactly(tmp_path: Path) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(source, _result(observed_sha="3" * 40))

    with pytest.raises(DiscoveryAuthorityBindingError, match="release"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )


def test_exactly_one_authenticated_authority_group_is_required(tmp_path: Path) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(
        source,
        _result(
            authority_group_count=2,
            authority_groups=[
                {
                    "authority_group_fingerprint_sha256": AUTHORITY_GROUP_FP,
                    "request_count": 1,
                    "request_paths": ["/a"],
                },
                {
                    "authority_group_fingerprint_sha256": "9" * 64,
                    "request_count": 1,
                    "request_paths": ["/b"],
                },
            ],
        ),
    )

    with pytest.raises(DiscoveryAuthorityBindingError, match="authority group"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )


def test_multiple_compatible_candidates_require_explicit_unique_runtime_fingerprint(
    tmp_path: Path,
) -> None:
    first = _candidate()
    second = _candidate(
        runtime_fp="9" * 64,
        hydration_fp="8" * 64,
        source_path="/var/lib/shreks/backups/g8/artifacts/paper-campaign.json",
        source_kind="g8_backup",
        backup_bundle_path="/var/lib/shreks/backups/g8",
    )
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(source, _result(candidates=[first, second]))

    with pytest.raises(DiscoveryAuthorityBindingError, match="explicit"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )

    artifact = bind_fl9_v2_discovery_authority(
        discovery_result_path=source,
        destination=destination,
        runtime_manifest_fingerprint_sha256="9" * 64,
    )
    assert artifact["runtime_manifest_fingerprint_sha256"] == "9" * 64
    assert artifact["runtime_manifest_source_kind"] == "g8_backup"
    assert artifact["backup_bundle_path"] == "/var/lib/shreks/backups/g8"


def test_explicit_runtime_fingerprint_must_identify_exactly_one_candidate(tmp_path: Path) -> None:
    duplicate = _candidate(
        source_path="/var/lib/shreks/backups/g8/artifacts/paper-campaign.json",
        source_kind="g8_backup",
        backup_bundle_path="/var/lib/shreks/backups/g8",
    )
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(source, _result(candidates=[_candidate(), duplicate]))

    with pytest.raises(DiscoveryAuthorityBindingError, match="exactly one"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
            runtime_manifest_fingerprint_sha256=RUNTIME_FP,
        )


def test_input_must_be_canonical_and_include_authenticated_cohort_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(source, _result(), canonical=False)

    with pytest.raises(DiscoveryAuthorityBindingError, match="canonical"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )

    document = _result()
    del document["discovery_report"]["non_manifest_input_authority"][
        "cohort_artifact_fingerprint_sha256"
    ]
    _write_result(source, document)
    with pytest.raises(DiscoveryAuthorityBindingError, match="cohort"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )


def test_quote_identity_must_match_frozen_cohort_quote(tmp_path: Path) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    document = _result()
    document["discovery_report"]["candidates"][0]["quote_asset_mint"] = "USDC"
    _write_result(source, document)

    with pytest.raises(DiscoveryAuthorityBindingError, match="quote"):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )


def test_binding_decode_rejects_tamper_and_writer_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "discovery.json"
    destination = tmp_path / "binding.json"
    _write_result(source, _result())
    artifact = bind_fl9_v2_discovery_authority(
        discovery_result_path=source,
        destination=destination,
    )

    tampered = dict(artifact)
    tampered["quote_provider"] = "tampered"
    with pytest.raises(DiscoveryAuthorityBindingError, match="fingerprint"):
        decode_fl9_v2_discovery_authority_binding(_canonical(tampered))

    with pytest.raises(FileExistsError):
        bind_fl9_v2_discovery_authority(
            discovery_result_path=source,
            destination=destination,
        )


def test_discovery_authority_binding_runbook_pins_exact_verified_release() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    runbook = (repo_root / "deploy" / "release" / "README.md").read_text(
        encoding="utf-8"
    )

    heading = "### Bind one compatible FL9 V2 discovery authority"
    assert heading in runbook
    section = runbook.split(heading, 1)[1].split("\n### ", 1)[0]

    assert 'EXPECTED_RELEASE_SHA="<exact-production-verified-release-sha>"' in section
    assert 'CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"' in section
    assert 'CURRENT_SHA="$(basename "$CURRENT_RELEASE")"' in section
    assert 'test "$CURRENT_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'MANIFEST_SHA="$(' in section
    assert 'test "$MANIFEST_SHA" = "$EXPECTED_RELEASE_SHA"' in section
    assert 'BINDING="' in section
    assert 'sudo test ! -e "$BINDING"' in section
    assert 'test "$(readlink -f /opt/shreks/current)" = "$CURRENT_RELEASE"' in section
    assert 'sudo "$CURRENT_RELEASE/.venv/bin/shreks-fl9-v2-discovery-authority-bind"' in section
