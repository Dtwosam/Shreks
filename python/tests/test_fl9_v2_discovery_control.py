from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest

from shreks_brain.fl9_v2_runtime_manifest_discovery import (
    AuthenticatedV2DiscoveryRequestAuthority,
    RuntimeManifestDiscoveryError,
)
from shreks_brain.telemetry import fl9_v2_discovery_control as control


SOURCE_SHA = "1" * 40
NOW_MS = 1_789_000_000_000


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _release_tree(tmp_path: Path, *, source_sha: str = SOURCE_SHA) -> Path:
    releases = tmp_path / "releases"
    release = releases / source_sha
    release.mkdir(parents=True, exist_ok=True)
    (release / "RELEASE_MANIFEST.json").write_text(
        _canonical(
            {
                "schema_version": "g2-release-manifest-v1",
                "source_sha": source_sha,
                "platform": "aarch64-unknown-linux-gnu",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    current = tmp_path / "current"
    if not current.exists() and not current.is_symlink():
        current.symlink_to(release, target_is_directory=True)
    return current


def _marker(
    directory: Path,
    *,
    request_id: str = "gha-123-1",
    source_sha: str = SOURCE_SHA,
    created_at_unix_ms: int = NOW_MS,
    mode: int = 0o644,
    canonical: bool = True,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"shreks-fl9-v2-discovery.{request_id}.request"
    document = {
        "schema_name": "shreks.fl9_v2_discovery_control_request",
        "schema_version": 1,
        "request_id": request_id,
        "expected_release_sha": source_sha,
        "created_at_unix_ms": created_at_unix_ms,
    }
    if canonical:
        payload = _canonical(document)
    else:
        payload = json.dumps(document, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    path.chmod(mode)
    return path


def _authority(path: Path, *, version: str = "approved-v7") -> AuthenticatedV2DiscoveryRequestAuthority:
    return AuthenticatedV2DiscoveryRequestAuthority(
        request_path=path.resolve(),
        request_fingerprint_sha256="a" * 64,
        request_release_source_sha="2" * 40,
        cohort_artifact_fingerprint_sha256="b" * 64,
        hydration_policy_path=(path.parent / "hydration.json").resolve(),
        hydration_policy_fingerprint_sha256="c" * 64,
        hydration_policy_version=version,
        strategy_families=("alpha", "beta"),
        max_exit_quote_age_ms=4_321,
        execution_cost_policy_version="cost-v5",
        expected_round_trip_cost_bps=17.5,
    )


def _process(tmp_path: Path, marker_directory: Path, **kwargs):
    receipt_root = tmp_path / "receipts"
    request_root = tmp_path / "requests"
    request_root.mkdir(exist_ok=True)
    backup_root = tmp_path / "backups"
    backup_root.mkdir(exist_ok=True)
    cohort = tmp_path / "cohort"
    cohort.write_text("cohort\n", encoding="utf-8")
    active = tmp_path / "paper-campaign.json"
    active.write_text("{}\n", encoding="utf-8")
    current = _release_tree(tmp_path)
    return control.process_pending_fl9_v2_discovery_requests(
        marker_directory=marker_directory,
        receipt_root=receipt_root,
        request_search_root=request_root,
        cohort_path=cohort,
        active_runtime_manifest_path=active,
        backup_root=backup_root,
        current_release_link=current,
        expected_owner_uid=os.getuid(),
        now_unix_ms=NOW_MS,
        **kwargs,
    )


def test_valid_canonical_marker_without_request_authority_returns_trusted_hold_and_receipt(
    tmp_path: Path,
) -> None:
    markers = tmp_path / "markers"
    marker = _marker(markers)

    results = _process(tmp_path, markers)

    assert len(results) == 1
    result = results[0]
    assert result["schema_name"] == "shreks.fl9_v2_discovery_control_result"
    assert result["schema_version"] == 1
    assert result["request_id"] == "gha-123-1"
    assert result["expected_release_sha"] == SOURCE_SHA
    assert result["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    receipt = tmp_path / "receipts" / "gha-123-1.json"
    assert receipt.is_file()
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert marker.is_file()


def test_privileged_predeploy_processing_can_defer_receipt_persistence(
    tmp_path: Path,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)

    results = _process(tmp_path, markers, persist_receipts=False)

    assert len(results) == 1
    assert results[0]["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    assert not (tmp_path / "receipts" / "gha-123-1.json").exists()


@pytest.mark.parametrize(
    ("mutation", "error_fragment"),
    [
        ("wrong_mode", "mode"),
        ("noncanonical", "canonical"),
        ("stale", "stale"),
        ("future", "future"),
    ],
)
def test_marker_failures_close_and_receipt_only_after_authentication(
    tmp_path: Path,
    mutation: str,
    error_fragment: str,
) -> None:
    markers = tmp_path / "markers"
    if mutation == "wrong_mode":
        marker = _marker(markers, mode=0o600)
    elif mutation == "noncanonical":
        marker = _marker(markers, canonical=False)
    elif mutation == "stale":
        marker = _marker(markers, created_at_unix_ms=NOW_MS - 301_000)
    else:
        marker = _marker(markers, created_at_unix_ms=NOW_MS + 31_000)

    results = _process(tmp_path, markers)

    assert len(results) == 1
    assert results[0]["status"] == "FAILED"
    assert error_fragment in str(results[0]["error"]).lower()
    receipt = tmp_path / "receipts" / "gha-123-1.json"
    if mutation in {"stale", "future"}:
        assert receipt.is_file()
        assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    else:
        assert not receipt.exists()
    assert marker.exists()


def test_symlink_marker_is_rejected_without_following_target(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()
    target = tmp_path / "target"
    target.write_text("do-not-follow\n", encoding="utf-8")
    marker = markers / "shreks-fl9-v2-discovery.gha-123-1.request"
    marker.symlink_to(target)

    results = _process(tmp_path, markers)

    assert len(results) == 1
    assert results[0]["status"] == "FAILED"
    assert "symlink" in str(results[0]["error"]).lower() or "regular" in str(results[0]["error"]).lower()
    assert target.read_text(encoding="utf-8") == "do-not-follow\n"


def test_trusted_symlink_marker_directory_is_processed(tmp_path: Path) -> None:
    shared = tmp_path / "shared-shm"
    shared.mkdir()
    shared.chmod(0o1777)
    alias = tmp_path / "dev-shm"
    alias.symlink_to(shared, target_is_directory=True)
    _marker(shared)

    results = _process(
        tmp_path,
        alias,
        expected_marker_directory_owner_uid=os.getuid(),
    )

    assert len(results) == 1
    assert results[0]["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    assert results[0]["request_id"] == "gha-123-1"


@pytest.mark.parametrize("mode", [0o777, 0o755, 0o1770])
def test_symlink_marker_directory_requires_trusted_sticky_world_writable_target(
    tmp_path: Path,
    mode: int,
) -> None:
    shared = tmp_path / "shared-shm"
    shared.mkdir()
    shared.chmod(mode)
    alias = tmp_path / "dev-shm"
    alias.symlink_to(shared, target_is_directory=True)
    _marker(shared)

    results = _process(
        tmp_path,
        alias,
        expected_marker_directory_owner_uid=os.getuid(),
    )

    assert results == ()


def test_symlink_marker_directory_requires_trusted_symlink_owner(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared-shm"
    shared.mkdir()
    shared.chmod(0o1777)
    alias = tmp_path / "dev-shm"
    alias.symlink_to(shared, target_is_directory=True)
    _marker(shared)

    results = _process(
        tmp_path,
        alias,
        expected_marker_directory_owner_uid=os.getuid() + 1,
    )

    assert results == ()


def test_release_binding_requires_current_link_and_manifest_source_sha(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    _marker(markers, source_sha="3" * 40)

    results = _process(tmp_path, markers)

    assert results[0]["status"] == "FAILED"
    assert "release" in str(results[0]["error"]).lower()


def test_bounded_authority_enumeration_uses_only_root_and_fl9_v2_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()
    root_request = requests / "v2-first-champion-request.json"
    root_request.write_text("root\n", encoding="utf-8")
    child = requests / "fl9-v2-a"
    child.mkdir()
    child_request = child / "v2-first-champion-request.json"
    child_request.write_text("child\n", encoding="utf-8")
    ignored = requests / "unrelated" / "deep"
    ignored.mkdir(parents=True)
    (ignored / "v2-first-champion-request.json").write_text("ignored\n", encoding="utf-8")

    seen: list[Path] = []

    def authenticate(*, cohort_path, v2_host_request_authority_path):
        path = Path(v2_host_request_authority_path)
        seen.append(path.resolve())
        return _authority(path)

    delegated: list[Path] = []

    def discover(**kwargs):
        delegated.append(Path(kwargs["v2_host_request_authority_path"]).resolve())
        return {
            "status": "FOUND_COMPATIBLE",
            "compatible_candidate_count": 1,
            "candidates": [],
        }

    monkeypatch.setattr(control, "authenticate_fl9_v2_discovery_request_authority", authenticate)
    monkeypatch.setattr(control, "discover_fl9_v2_runtime_manifests_from_v2_request_authority", discover)

    results = _process(tmp_path, markers)

    assert results[0]["status"] == "FOUND_COMPATIBLE"
    assert sorted(seen) == sorted((root_request.resolve(), child_request.resolve()))
    assert delegated == [min(root_request.resolve(), child_request.resolve())]
    source = Path(control.__file__).read_text(encoding="utf-8")
    assert ".rglob(" not in source
    assert "os.walk(" not in source


def test_unreadable_historical_subtree_is_skipped_while_readable_authority_is_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()

    protected = requests / "fl9-v2-protected"
    protected.mkdir()
    protected_request = protected / "v2-first-champion-request.json"
    protected_request.write_text("protected\n", encoding="utf-8")

    readable = requests / "fl9-v2-readable"
    readable.mkdir()
    readable_request = readable / "v2-first-champion-request.json"
    readable_request.write_text("readable\n", encoding="utf-8")

    seen: list[Path] = []

    def authenticate(*, cohort_path, v2_host_request_authority_path):
        path = Path(v2_host_request_authority_path)
        seen.append(path.resolve())
        return _authority(path)

    monkeypatch.setattr(
        control,
        "authenticate_fl9_v2_discovery_request_authority",
        authenticate,
    )
    monkeypatch.setattr(
        control,
        "discover_fl9_v2_runtime_manifests_from_v2_request_authority",
        lambda **_kwargs: {
            "status": "FOUND_COMPATIBLE",
            "compatible_candidate_count": 1,
            "candidates": [],
        },
    )

    protected.chmod(0)
    try:
        results = _process(tmp_path, markers)
    finally:
        protected.chmod(0o700)

    assert results[0]["status"] == "FOUND_COMPATIBLE"
    assert seen == [readable_request.resolve()]


def test_only_unreadable_historical_subtree_returns_trusted_no_authority_hold(
    tmp_path: Path,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()

    protected = requests / "fl9-v2-protected"
    protected.mkdir()
    (protected / "v2-first-champion-request.json").write_text(
        "protected\n",
        encoding="utf-8",
    )

    protected.chmod(0)
    try:
        results = _process(tmp_path, markers)
    finally:
        protected.chmod(0o700)

    assert results[0]["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    assert results[0]["request_candidate_count"] == 0
    assert results[0]["authenticated_authority_count"] == 0
    assert results[0]["rejected_authority_count"] == 0


def test_distinct_authenticated_authority_groups_hold_ambiguous_without_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()
    first_dir = requests / "fl9-v2-a"
    second_dir = requests / "fl9-v2-b"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "v2-first-champion-request.json"
    second = second_dir / "v2-first-champion-request.json"
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")

    def authenticate(*, cohort_path, v2_host_request_authority_path):
        path = Path(v2_host_request_authority_path)
        return _authority(path, version=("v1" if path.parent.name.endswith("a") else "v2"))

    monkeypatch.setattr(control, "authenticate_fl9_v2_discovery_request_authority", authenticate)
    monkeypatch.setattr(
        control,
        "discover_fl9_v2_runtime_manifests_from_v2_request_authority",
        lambda **_kwargs: pytest.fail("ambiguous authority must not invoke discovery"),
    )

    results = _process(tmp_path, markers)

    assert results[0]["status"] == "HOLD_AMBIGUOUS_REQUEST_AUTHORITY"
    assert results[0]["authority_group_count"] == 2


def test_invalid_historical_authorities_are_rejected_not_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()
    candidate = requests / "v2-first-champion-request.json"
    candidate.write_text("invalid\n", encoding="utf-8")

    def reject(**_kwargs):
        raise RuntimeManifestDiscoveryError("invalid authority")

    monkeypatch.setattr(control, "authenticate_fl9_v2_discovery_request_authority", reject)
    monkeypatch.setattr(
        control,
        "discover_fl9_v2_runtime_manifests_from_v2_request_authority",
        lambda **_kwargs: pytest.fail("invalid authority must not invoke discovery"),
    )

    results = _process(tmp_path, markers)

    assert results[0]["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    assert results[0]["rejected_authority_count"] == 1


def test_receipt_replay_is_idempotent_and_does_not_rescan_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = tmp_path / "markers"
    _marker(markers)
    requests = tmp_path / "requests"
    requests.mkdir()
    candidate = requests / "v2-first-champion-request.json"
    candidate.write_text("valid\n", encoding="utf-8")
    calls = {"authenticate": 0, "discover": 0}

    def authenticate(*, cohort_path, v2_host_request_authority_path):
        calls["authenticate"] += 1
        return _authority(Path(v2_host_request_authority_path))

    def discover(**_kwargs):
        calls["discover"] += 1
        return {
            "status": "FOUND_COMPATIBLE",
            "compatible_candidate_count": 1,
            "candidates": [],
        }

    monkeypatch.setattr(control, "authenticate_fl9_v2_discovery_request_authority", authenticate)
    monkeypatch.setattr(control, "discover_fl9_v2_runtime_manifests_from_v2_request_authority", discover)

    first = _process(tmp_path, markers)
    second = _process(tmp_path, markers)

    assert first == second
    assert calls == {"authenticate": 1, "discover": 1}


def _result_exchange_directory(marker_directory: Path, request_id: str = "gha-123-1") -> Path:
    path = marker_directory / f"shreks-fl9-v2-discovery.{request_id}.result.d"
    path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o733)
    return path


def _hold_result(request_id: str = "gha-123-1") -> dict[str, object]:
    return {
        "schema_name": "shreks.fl9_v2_discovery_control_result",
        "schema_version": 1,
        "request_id": request_id,
        "expected_release_sha": SOURCE_SHA,
        "observed_release_sha": SOURCE_SHA,
        "status": "HOLD_NO_REQUEST_AUTHORITY",
    }


def test_result_exchange_publishes_canonical_atomic_read_only_file(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()
    exchange = _result_exchange_directory(markers)
    result = _hold_result()

    published = control.publish_fl9_v2_discovery_control_result(
        result,
        marker_directory=markers,
        expected_exchange_owner_uid=os.getuid(),
    )

    assert published is True
    output = exchange / "result.json"
    assert output.is_file()
    assert not output.is_symlink()
    assert stat.S_IMODE(output.stat().st_mode) == 0o644
    assert output.stat().st_uid == os.getuid()
    assert output.read_text(encoding="utf-8") == _canonical(result)
    assert not tuple(exchange.glob("result.json.tmp.*"))


def test_result_exchange_is_optional_when_directory_is_absent(tmp_path: Path) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()

    assert (
        control.publish_fl9_v2_discovery_control_result(
            _hold_result(),
            marker_directory=markers,
            expected_exchange_owner_uid=os.getuid(),
        )
        is False
    )


@pytest.mark.parametrize("mode", [0o700, 0o755, 0o777])
def test_result_exchange_requires_exact_deploy_owned_0733_directory(
    tmp_path: Path,
    mode: int,
) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()
    exchange = _result_exchange_directory(markers)
    exchange.chmod(mode)

    with pytest.raises(control.DiscoveryControlError, match="exchange"):
        control.publish_fl9_v2_discovery_control_result(
            _hold_result(),
            marker_directory=markers,
            expected_exchange_owner_uid=os.getuid(),
        )


def test_result_exchange_rejects_symlink_directory_and_never_overwrites(
    tmp_path: Path,
) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()
    real = tmp_path / "real-exchange"
    real.mkdir()
    real.chmod(0o733)
    alias = markers / "shreks-fl9-v2-discovery.gha-123-1.result.d"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(control.DiscoveryControlError, match="exchange"):
        control.publish_fl9_v2_discovery_control_result(
            _hold_result(),
            marker_directory=markers,
            expected_exchange_owner_uid=os.getuid(),
        )

    alias.unlink()
    exchange = _result_exchange_directory(markers)
    output = exchange / "result.json"
    output.write_text("forged\n", encoding="utf-8")
    output.chmod(0o644)

    with pytest.raises(control.DiscoveryControlError, match="result"):
        control.publish_fl9_v2_discovery_control_result(
            _hold_result(),
            marker_directory=markers,
            expected_exchange_owner_uid=os.getuid(),
        )
    assert output.read_text(encoding="utf-8") == "forged\n"


def test_single_discovery_request_can_run_without_persistent_receipt(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    marker = _marker(exchange)
    request_root = tmp_path / "requests"
    request_root.mkdir()
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    cohort = tmp_path / "cohort"
    cohort.write_text("cohort\n", encoding="utf-8")
    active = tmp_path / "paper-campaign.json"
    active.write_text("{}\n", encoding="utf-8")
    current = _release_tree(tmp_path)

    result = control.process_fl9_v2_discovery_request(
        marker,
        receipt_root=None,
        request_search_root=request_root,
        cohort_path=cohort,
        active_runtime_manifest_path=active,
        backup_root=backup_root,
        current_release_link=current,
        expected_owner_uid=os.getuid(),
        now_unix_ms=NOW_MS,
    )

    assert result["status"] == "HOLD_NO_REQUEST_AUTHORITY"
    assert not (tmp_path / "receipts").exists()
