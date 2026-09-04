from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import shreks_brain.fast_runtime_hydration_policy as bridge
from shreks_brain.fast_context_hydration import (
    decode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    build_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)
from test_observer_campaign_runtime_manifest import _manifest


def test_runtime_manifest_derives_only_manifest_backed_context_fields() -> None:
    manifest = _manifest()
    policy = bridge.build_fast_forecast_context_hydration_policy_from_runtime_manifest(
        manifest,
        version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=2_000,
        execution_cost_policy_version="paper-cost-policy-v1",
        expected_round_trip_cost_bps=None,
    )

    bundle = manifest.policy_bundle
    assert policy.version == "fl9-runtime-context-v1"
    assert policy.strategy_families == ("fresh_launch_continuation",)
    assert policy.regime_read_policy == bundle.regime_read_policy
    assert policy.regime_policy == bundle.regime_policy
    assert policy.safety_policy == bundle.safety_policy
    assert policy.safety_probe_identity == bundle.safety_probe_identity
    assert policy.global_risk_halt is manifest.global_risk_halt
    assert policy.exit_quote_provider == bundle.entry_quote_identity.provider
    assert policy.quote_asset_decimals == bundle.quote_asset.decimals
    assert policy.max_exit_quote_age_ms == 2_000
    assert policy.execution_cost_policy_version == "paper-cost-policy-v1"
    assert policy.expected_round_trip_cost_bps is None


def test_runtime_manifest_bridge_preserves_explicit_numeric_cost() -> None:
    policy = bridge.build_fast_forecast_context_hydration_policy_from_runtime_manifest(
        _manifest(),
        version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=1_500,
        execution_cost_policy_version="comparison-cost-v3",
        expected_round_trip_cost_bps=37.25,
    )
    assert policy.expected_round_trip_cost_bps == 37.25


def test_runtime_manifest_bridge_rejects_duplicate_strategy_families() -> None:
    with pytest.raises(ValueError, match="strategy.*duplicate|unique"):
        bridge.build_fast_forecast_context_hydration_policy_from_runtime_manifest(
            _manifest(),
            version="fl9-runtime-context-v1",
            strategy_families=("fresh_launch_continuation", "fresh_launch_continuation"),
            max_exit_quote_age_ms=1_000,
            execution_cost_policy_version="paper-cost-policy-v1",
            expected_round_trip_cost_bps=None,
        )


def test_runtime_manifest_file_bridge_is_canonical_no_overwrite_and_source_bound(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "campaign-manifest.json"
    manifest = _manifest()
    source = encode_observer_paper_campaign_runtime_manifest(manifest)
    manifest_path.write_bytes(source)
    destination = tmp_path / "hydration-policy.json"

    result = bridge.write_fast_forecast_context_hydration_policy_from_runtime_manifest(
        runtime_manifest_path=manifest_path,
        destination=destination,
        version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=2_000,
        execution_cost_policy_version="paper-cost-policy-v1",
        expected_round_trip_cost_bps=None,
    )

    decoded = decode_fast_forecast_context_hydration_policy(
        destination.read_text(encoding="utf-8")
    )
    assert result.path == destination.resolve()
    assert result.runtime_manifest_fingerprint_sha256 == (
        manifest.manifest_fingerprint_sha256
    )
    assert result.policy_fingerprint_sha256 == (
        fast_forecast_context_hydration_policy_fingerprint_sha256(decoded)
    )
    assert manifest_path.read_bytes() == source

    with pytest.raises(FileExistsError):
        bridge.write_fast_forecast_context_hydration_policy_from_runtime_manifest(
            runtime_manifest_path=manifest_path,
            destination=destination,
            version="fl9-runtime-context-v1",
            strategy_families=("fresh_launch_continuation",),
            max_exit_quote_age_ms=2_000,
            execution_cost_policy_version="paper-cost-policy-v1",
            expected_round_trip_cost_bps=None,
        )


def test_runtime_manifest_file_bridge_rejects_source_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "campaign-manifest.json"
    manifest_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(_manifest())
    )
    destination = tmp_path / "hydration-policy.json"

    original_encode = bridge.encode_fast_forecast_context_hydration_policy

    def _mutating_encode(policy):
        payload = original_encode(policy)
        manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
        return payload

    monkeypatch.setattr(
        bridge,
        "encode_fast_forecast_context_hydration_policy",
        _mutating_encode,
    )

    with pytest.raises(ValueError, match="manifest.*changed|source.*changed"):
        bridge.write_fast_forecast_context_hydration_policy_from_runtime_manifest(
            runtime_manifest_path=manifest_path,
            destination=destination,
            version="fl9-runtime-context-v1",
            strategy_families=("fresh_launch_continuation",),
            max_exit_quote_age_ms=2_000,
            execution_cost_policy_version="paper-cost-policy-v1",
            expected_round_trip_cost_bps=None,
        )
    assert not destination.exists()


@pytest.mark.parametrize(
    ("cost_arg", "expected"),
    (("unknown", None), ("42.5", 42.5), ("0", 0.0)),
)
def test_cli_writes_policy_and_reports_fingerprints(
    tmp_path: Path,
    capsys,
    cost_arg: str,
    expected: float | None,
) -> None:
    manifest_path = tmp_path / "campaign-manifest.json"
    manifest_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(_manifest())
    )
    destination = tmp_path / "hydration-policy.json"

    code = bridge.main(
        [
            "--runtime-manifest",
            str(manifest_path),
            "--destination",
            str(destination),
            "--version",
            "fl9-runtime-context-v1",
            "--strategy-family",
            "fresh_launch_continuation",
            "--max-exit-quote-age-ms",
            "2000",
            "--execution-cost-policy-version",
            "paper-cost-policy-v1",
            "--expected-round-trip-cost-bps",
            cost_arg,
        ]
    )
    document = json.loads(capsys.readouterr().out)
    decoded = decode_fast_forecast_context_hydration_policy(
        destination.read_text(encoding="utf-8")
    )

    assert code == 0
    assert decoded.expected_round_trip_cost_bps == expected
    assert document["status"] == "SUCCEEDED"
    assert document["runtime_manifest_fingerprint_sha256"] == (
        _manifest().manifest_fingerprint_sha256
    )
    assert document["policy_fingerprint_sha256"] == (
        fast_forecast_context_hydration_policy_fingerprint_sha256(decoded)
    )


def test_bridge_tracks_runtime_global_halt_exactly() -> None:
    source = _manifest()
    manifest = build_observer_paper_campaign_runtime_manifest(
        paper_run_id=source.paper_run_id,
        candidate=source.candidate,
        initial_state=source.initial_state,
        policy_bundle=source.policy_bundle,
        risk_environment=source.risk_environment,
        selection_policy=source.selection_policy,
        recent_performance=source.recent_performance,
        global_risk_halt=True,
    )
    policy = bridge.build_fast_forecast_context_hydration_policy_from_runtime_manifest(
        manifest,
        version="fl9-runtime-context-v1",
        strategy_families=("fresh_launch_continuation",),
        max_exit_quote_age_ms=2_000,
        execution_cost_policy_version="paper-cost-policy-v1",
        expected_round_trip_cost_bps=None,
    )
    assert policy.global_risk_halt is True


def test_bridge_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_runtime_hydration_policy.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
        "sqlite3",
    ):
        assert forbidden not in source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fast-context-policy-from-runtime = '
        '"shreks_brain.fast_runtime_hydration_policy:main"'
        in pyproject
    )
