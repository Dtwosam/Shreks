from __future__ import annotations

from pathlib import Path

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from shreks_brain.fast_campaign import FastCampaignContinuousActionPolicy
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper_runtime import (
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
)
from shreks_brain.fast_paper_runtime.shadow_runtime import (
    FastPaperShadowRuntimeError,
    bootstrap_fast_paper_shadow_runtime,
    load_fast_paper_shadow_runtime_config,
)


_RELEASE_SHA = "a" * 40
_QUOTE_MINT = "So11111111111111111111111111111111111111112"


def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=7,
        horizons_ms=(250,),
        entry_exposure_candidates=(0.25, 0.5),
        reduce_target_exposure_candidates=(0.25,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=2.0,
        route_unavailability_penalty_bps=3.0,
        horizon_disagreement_weight=0.5,
        minimum_buy_value_bps=4.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def _manifest(tmp_path: Path):
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="shadow-runtime-loop-v1",
        decision_reference="shadow-runtime-loop-fixture",
        decided_at_unix_ms=10_000,
        reason="shadow runtime loop fixture",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    champion_path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, champion_path)
    return build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=champion_path,
        decision_binary_path=_executable(
            tmp_path / "shreks-fast-campaign-decision"
        ),
        feature_feed_binary_path=_executable(
            tmp_path / "export_fast_runtime_features"
        ),
        action_policy=_policy(),
        state_version="fast-state-v1",
        risk_policy_version="fast-risk-v1",
        fill_policy_version="paper-fill-v1",
        position_action_policy_version="fl7.4-v1",
        strategy_family="fast-lane-learned",
        strategy_version="fast-lane-learned-v1",
        assessment_version="fast-paper-assessment-v1",
        observer_database_path=tmp_path / "observer.sqlite3",
        paper_evidence_path=tmp_path / "authoritative-paper.sqlite3",
        checkpoint_path=tmp_path / "authoritative-runtime-state.json",
        quote_provider="jupiter",
        quote_mint=_QUOTE_MINT,
        quote_decimals=9,
        route_evidence_version="observer-paper-quote-v1",
    )


def _canonical_inputs(path: Path) -> None:
    path.write_text(
        '{"inputs":[],"schema_name":"shreks.fast_paper_shadow_runtime_inputs",'
        '"schema_version":1}\n',
        encoding="utf-8",
    )
    path.chmod(0o600)


def _environment(tmp_path: Path, manifest_path: Path) -> dict[str, str]:
    return {
        "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH": str(manifest_path),
        "SHREKS_FAST_PAPER_SHADOW_STATE_PATH": str(
            tmp_path / "shadow" / "state.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_PATH": str(
            tmp_path / "shadow" / "evidence.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_INPUT_PATH": str(
            tmp_path / "shadow-inputs.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS": "1.5",
        "SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS": "32",
    }


def test_shadow_runtime_bootstrap_uses_only_separate_shadow_state(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "runtime-manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    Path(manifest.observer_database_path).write_bytes(b"observer-fixture")
    input_path = tmp_path / "shadow-inputs.json"
    _canonical_inputs(input_path)

    config = load_fast_paper_shadow_runtime_config(
        _environment(tmp_path, manifest_path)
    )
    bootstrap = bootstrap_fast_paper_shadow_runtime(config)

    assert bootstrap.state == build_fast_paper_runtime_state(
        manifest,
        cursor=None,
    )
    assert not Path(manifest.checkpoint_path).exists()
    assert not Path(manifest.paper_evidence_path).exists()
    assert config.shadow_state_path != Path(manifest.checkpoint_path)
    assert config.shadow_evidence_path != Path(manifest.paper_evidence_path)


def test_shadow_runtime_rejects_authoritative_checkpoint_as_shadow_state(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "runtime-manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    Path(manifest.observer_database_path).write_bytes(b"observer-fixture")
    input_path = tmp_path / "shadow-inputs.json"
    _canonical_inputs(input_path)

    env = _environment(tmp_path, manifest_path)
    env["SHREKS_FAST_PAPER_SHADOW_STATE_PATH"] = manifest.checkpoint_path
    config = load_fast_paper_shadow_runtime_config(env)

    with pytest.raises(FastPaperShadowRuntimeError):
        bootstrap_fast_paper_shadow_runtime(config)


def test_shadow_runtime_rejects_state_bound_to_another_manifest(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "runtime-manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    Path(manifest.observer_database_path).write_bytes(b"observer-fixture")
    input_path = tmp_path / "shadow-inputs.json"
    _canonical_inputs(input_path)
    env = _environment(tmp_path, manifest_path)
    config = load_fast_paper_shadow_runtime_config(env)

    other_root = tmp_path / "other"
    other_root.mkdir()
    foreign_manifest = _manifest(other_root)
    foreign = build_fast_paper_runtime_state(
        foreign_manifest,
        cursor=None,
    )
    config.shadow_state_path.parent.mkdir(parents=True, exist_ok=True)
    write_fast_paper_runtime_state(foreign, config.shadow_state_path)

    with pytest.raises(FastPaperShadowRuntimeError):
        bootstrap_fast_paper_shadow_runtime(config)
