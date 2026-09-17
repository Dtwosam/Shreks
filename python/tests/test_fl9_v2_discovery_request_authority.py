from __future__ import annotations

from types import SimpleNamespace

import pytest

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery

from test_fl9_v2_cohort_acceptance_artifact import _write as _write_cohort
from test_fl9_v2_runtime_manifest_discovery import (
    _bind_synthetic_cohort_to_request_authority,
    _prior_request_authority,
)


def test_authenticated_request_authority_exposes_only_sealed_non_manifest_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    cohort = _write_cohort(tmp_path, "cohort")
    request_path, policy_path, request, _policy = _prior_request_authority(
        tmp_path,
        cohort.path,
    )
    _bind_synthetic_cohort_to_request_authority(monkeypatch, cohort, request)

    authority = discovery.authenticate_fl9_v2_discovery_request_authority(
        cohort_path=cohort.path,
        v2_host_request_authority_path=request_path,
    )

    assert isinstance(authority, discovery.AuthenticatedV2DiscoveryRequestAuthority)
    assert authority.request_path == request_path.resolve()
    assert authority.request_fingerprint_sha256 == request.request_fingerprint_sha256
    assert authority.request_release_source_sha == request.expected_release_source_sha
    assert authority.cohort_artifact_fingerprint_sha256 == (
        request.expected_cohort_artifact_fingerprint_sha256
    )
    assert authority.hydration_policy_path == policy_path.resolve()
    assert authority.hydration_policy_fingerprint_sha256 == (
        request.expected_hydration_policy_fingerprint_sha256
    )
    assert authority.hydration_policy_version == "approved-v2-hydration-v7"
    assert authority.strategy_families == ("approved_alpha", "approved_beta")
    assert authority.max_exit_quote_age_ms == 4_321
    assert authority.execution_cost_policy_version == "approved-cost-v5"
    assert authority.expected_round_trip_cost_bps == 17.5


def test_authenticated_request_authority_fails_closed_on_cohort_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    cohort = _write_cohort(tmp_path, "cohort")
    request_path, _policy_path, request, _policy = _prior_request_authority(
        tmp_path,
        cohort.path,
    )
    mismatched = SimpleNamespace(
        path=cohort.path,
        manifest=SimpleNamespace(artifact_fingerprint_sha256="b" * 64),
        accepted_decisions=cohort.accepted_decisions,
        quarantined_decisions=cohort.quarantined_decisions,
    )
    monkeypatch.setattr(
        discovery,
        "read_fl9_v2_cohort_acceptance",
        lambda _path: mismatched,
    )

    with pytest.raises(
        discovery.RuntimeManifestDiscoveryError,
        match="current frozen cohort|cohort",
    ):
        discovery.authenticate_fl9_v2_discovery_request_authority(
            cohort_path=cohort.path,
            v2_host_request_authority_path=request_path,
        )


def test_authenticated_request_authority_fails_closed_on_bound_policy_mismatch(
    tmp_path,
    monkeypatch,
) -> None:
    cohort = _write_cohort(tmp_path, "cohort")
    request_path, policy_path, request, _policy = _prior_request_authority(
        tmp_path,
        cohort.path,
    )
    _bind_synthetic_cohort_to_request_authority(monkeypatch, cohort, request)
    policy_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        discovery.RuntimeManifestDiscoveryError,
        match="hydration|policy|fingerprint|authentication",
    ):
        discovery.authenticate_fl9_v2_discovery_request_authority(
            cohort_path=cohort.path,
            v2_host_request_authority_path=request_path,
        )
