from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shreks_brain.backup import create_backup_snapshot
from shreks_brain.observer_campaign.runtime_manifest import (
    build_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)
import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery

from test_fl9_v2_cohort_acceptance_artifact import _write as _write_cohort
from test_g8_backup_snapshot import _sources as _backup_sources
from test_observer_campaign_runtime_manifest import _manifest


QUOTE = "quote-sol"


def _compatible_manifest():
    source = _manifest()
    bundle = source.policy_bundle
    compatible_bundle = replace(
        bundle,
        quote_asset=replace(bundle.quote_asset, mint=QUOTE, decimals=9),
        entry_quote_identity=replace(bundle.entry_quote_identity, input_mint=QUOTE),
        regime_read_policy=replace(bundle.regime_read_policy, quote_asset_mint=QUOTE),
        safety_probe_identity=replace(bundle.safety_probe_identity, output_mint=QUOTE),
    )
    return build_observer_paper_campaign_runtime_manifest(
        paper_run_id=source.paper_run_id,
        candidate=source.candidate,
        initial_state=source.initial_state,
        policy_bundle=compatible_bundle,
        risk_environment=source.risk_environment,
        selection_policy=source.selection_policy,
        recent_performance=source.recent_performance,
        global_risk_halt=source.global_risk_halt,
    )


def _discover(tmp_path: Path, *, active_manifest=None, backup_root=None):
    cohort = _write_cohort(tmp_path, "cohort")
    active = tmp_path / "active-paper-campaign.json"
    manifest = _compatible_manifest() if active_manifest is None else active_manifest
    active.write_bytes(encode_observer_paper_campaign_runtime_manifest(manifest))
    root = tmp_path / "backups" if backup_root is None else backup_root
    root.mkdir(exist_ok=True)
    return discovery.discover_fl9_v2_runtime_manifests(
        cohort_path=cohort.path,
        active_runtime_manifest_path=active,
        backup_root=root,
        hydration_policy_version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=2_000,
        execution_cost_policy_version="paper-cost-policy-v1",
        expected_round_trip_cost_bps=None,
    )


def test_discovery_authenticates_active_manifest_and_accepts_exact_quote_policy(tmp_path: Path) -> None:
    report = _discover(tmp_path)

    assert report["status"] == "FOUND_COMPATIBLE"
    assert report["cohort_quote_mint"] == QUOTE
    assert report["compatible_candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["source_kind"] == "active"
    assert candidate["authentication"] == "AUTHENTICATED"
    assert candidate["compatibility"] == "COMPATIBLE"
    assert candidate["regime_quote_asset_mint"] == QUOTE
    assert candidate["safety_probe_output_mint"] == QUOTE
    assert candidate["quote_asset_decimals"] == 9


def test_discovery_rejects_authenticated_quote_mismatch_without_rewriting(tmp_path: Path) -> None:
    source = _manifest()
    encoded_before = encode_observer_paper_campaign_runtime_manifest(source)
    report = _discover(tmp_path, active_manifest=source)

    assert report["status"] == "HOLD_NO_COMPATIBLE"
    candidate = report["candidates"][0]
    assert candidate["authentication"] == "AUTHENTICATED"
    assert candidate["compatibility"] == "REJECTED_QUOTE_POLICY"
    active = tmp_path / "active-paper-campaign.json"
    assert active.read_bytes() == encoded_before


def test_discovery_requires_verified_g8_backup_before_consuming_historical_manifest(tmp_path: Path) -> None:
    cohort = _write_cohort(tmp_path, "cohort")
    active = tmp_path / "active-paper-campaign.json"
    active.write_bytes(encode_observer_paper_campaign_runtime_manifest(_manifest()))

    backup_source = tmp_path / "backup-source"
    backup_source.mkdir()
    sources, _config, *_payloads = _backup_sources(backup_source)
    sources.campaign_manifest_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(_compatible_manifest())
    )
    backup_root = tmp_path / "backups"
    bundle = create_backup_snapshot(
        backup_root,
        sources,
        created_at_unix_ms=1_789_000_000_000,
        max_capture_attempts=1,
    )

    report = discovery.discover_fl9_v2_runtime_manifests(
        cohort_path=cohort.path,
        active_runtime_manifest_path=active,
        backup_root=backup_root,
        hydration_policy_version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=2_000,
        execution_cost_policy_version="paper-cost-policy-v1",
        expected_round_trip_cost_bps=None,
    )
    assert report["status"] == "FOUND_COMPATIBLE"
    assert any(
        candidate["source_kind"] == "g8_backup"
        and candidate["compatibility"] == "COMPATIBLE"
        for candidate in report["candidates"]
    )

    campaign = next(bundle.glob("artifacts/paper-campaign.json"))
    campaign.write_bytes(campaign.read_bytes() + b"\n")
    with pytest.raises(discovery.RuntimeManifestDiscoveryError, match="backup|verify|checksum"):
        discovery.discover_fl9_v2_runtime_manifests(
            cohort_path=cohort.path,
            active_runtime_manifest_path=active,
            backup_root=backup_root,
            hydration_policy_version="fl9-runtime-context-v1",
            strategy_families=("fresh_launch_continuation",),
            max_exit_quote_age_ms=2_000,
            execution_cost_policy_version="paper-cost-policy-v1",
            expected_round_trip_cost_bps=None,
        )


def test_discovery_fails_closed_on_tampered_runtime_manifest(tmp_path: Path) -> None:
    cohort = _write_cohort(tmp_path, "cohort")
    active = tmp_path / "active-paper-campaign.json"
    document = json.loads(encode_observer_paper_campaign_runtime_manifest(_compatible_manifest()))
    document["paper_run_id"] = "tampered-run"
    active.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    with pytest.raises(discovery.RuntimeManifestDiscoveryError, match="manifest|authenticate|fingerprint"):
        discovery.discover_fl9_v2_runtime_manifests(
            cohort_path=cohort.path,
            active_runtime_manifest_path=active,
            backup_root=backup_root,
            hydration_policy_version="fl9-runtime-context-v1",
            strategy_families=("fresh_launch_continuation",),
            max_exit_quote_age_ms=2_000,
            execution_cost_policy_version="paper-cost-policy-v1",
            expected_round_trip_cost_bps=None,
        )


def test_discovery_cli_is_registered_and_source_has_no_write_or_trading_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fl9_v2_runtime_manifest_discovery.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "write_bytes(",
        "write_text(",
        "open(\"w",
        "open('w",
        "sqlite3",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "registry promotion",
    ):
        assert forbidden not in source

    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        'shreks-fl9-v2-runtime-manifest-discovery = '
        '"shreks_brain.fl9_v2_runtime_manifest_discovery:main"'
        in pyproject
    )
