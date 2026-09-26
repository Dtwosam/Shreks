from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import stat

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from shreks_brain.fast_campaign import FastCampaignContinuousActionPolicy
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper import FAST_PAPER_EVENT_LOOP_VERSION
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME,
    FAST_PAPER_RUNTIME_SCHEMA_VERSION,
    FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME,
    FastPaperRuntimeCursor,
    FastPaperRuntimeManifest,
    FastPaperRuntimeState,
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
    write_fast_paper_runtime_manifest,
    write_fast_paper_runtime_state,
)


_RELEASE_SHA = "a" * 40
_QUOTE_MINT = "So11111111111111111111111111111111111111112"


def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
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


def _champion_path(tmp_path: Path):
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="runtime-champion-v1",
        decision_reference="runtime-contract-fixture",
        decided_at_unix_ms=10_000,
        reason="runtime contract fixture",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    return champion, path


def _decision_binary(tmp_path: Path) -> Path:
    path = tmp_path / "shreks-fast-campaign-decision"
    path.write_bytes(b"fixture-fast-campaign-decision\n")
    path.chmod(0o700)
    return path


def _manifest(tmp_path: Path) -> FastPaperRuntimeManifest:
    champion, champion_path = _champion_path(tmp_path)
    binary_path = _decision_binary(tmp_path)
    manifest = build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=champion_path,
        decision_binary_path=binary_path,
        action_policy=_policy(),
        state_version="fast-state-v1",
        risk_policy_version="fast-risk-v1",
        fill_policy_version="paper-fill-v1",
        position_action_policy_version="fl7.4-v1",
        strategy_family="fast-lane-learned",
        strategy_version="fast-lane-learned-v1",
        assessment_version="fast-paper-assessment-v1",
        observer_database_path=tmp_path / "observer.sqlite3",
        paper_evidence_path=tmp_path / "paper-evidence.sqlite3",
        checkpoint_path=tmp_path / "fast-paper-runtime-state.json",
        quote_provider="jupiter",
        quote_mint=_QUOTE_MINT,
        quote_decimals=9,
        route_evidence_version="observer-paper-quote-v1",
    )
    assert manifest.champion_version == champion.champion_version
    assert (
        manifest.champion_fingerprint_sha256
        == champion.champion_fingerprint_sha256
    )
    return manifest


def test_manifest_schema_is_exact_frozen_and_paper_only(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    assert FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME == (
        "shreks.fast_paper_runtime_manifest"
    )
    assert FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME == (
        "shreks.fast_paper_runtime_state"
    )
    assert FAST_PAPER_RUNTIME_SCHEMA_VERSION == 1
    assert manifest.schema_name == FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME
    assert manifest.schema_version == FAST_PAPER_RUNTIME_SCHEMA_VERSION
    assert manifest.runtime_mode == "PAPER"
    assert manifest.release_source_sha == _RELEASE_SHA
    assert manifest.action_policy == _policy()
    assert manifest.fast_paper_event_loop_version == FAST_PAPER_EVENT_LOOP_VERSION
    assert manifest.feature_schema_version > 0
    assert manifest.champion_file_sha256 != manifest.champion_fingerprint_sha256
    assert Path(manifest.champion_path).is_absolute()
    assert Path(manifest.decision_binary_path).is_absolute()
    assert Path(manifest.observer_database_path).is_absolute()
    assert Path(manifest.paper_evidence_path).is_absolute()
    assert Path(manifest.checkpoint_path).is_absolute()

    with pytest.raises(FrozenInstanceError):
        manifest.runtime_mode = "LIVE"  # type: ignore[misc]
    with pytest.raises(ValueError):
        replace(manifest, runtime_mode="LIVE")


def test_manifest_builder_and_verifier_bind_exact_champion_and_binary(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    verify_fast_paper_runtime_bindings(manifest)

    binary_path = Path(manifest.decision_binary_path)
    binary_path.write_bytes(binary_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="decision binary SHA-256"):
        verify_fast_paper_runtime_bindings(manifest)


def test_binding_verifier_detects_champion_byte_mutation(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    champion_path = Path(manifest.champion_path)
    champion_path.write_bytes(champion_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="champion file SHA-256"):
        verify_fast_paper_runtime_bindings(manifest)


def test_manifest_codec_is_canonical_private_and_write_once(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    destination = tmp_path / "runtime-manifest.json"

    write_fast_paper_runtime_manifest(manifest, destination)
    first = destination.read_bytes()
    assert first.endswith(b"\n")
    assert read_fast_paper_runtime_manifest(destination) == manifest
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    with pytest.raises(FileExistsError):
        write_fast_paper_runtime_manifest(manifest, destination)

    second = tmp_path / "runtime-manifest-copy.json"
    write_fast_paper_runtime_manifest(manifest, second)
    assert second.read_bytes() == first


def test_manifest_codec_rejects_score_fields_unknown_fields_and_nonfinite_json(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    destination = tmp_path / "runtime-manifest.json"
    write_fast_paper_runtime_manifest(manifest, destination)
    document = json.loads(destination.read_text(encoding="utf-8"))

    document["required_score_threshold"] = 99
    polluted = tmp_path / "polluted.json"
    polluted.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown or missing"):
        read_fast_paper_runtime_manifest(polluted)

    raw = destination.read_text(encoding="utf-8")
    raw = raw.replace('"minimum_buy_value_bps":4.0', '"minimum_buy_value_bps":NaN')
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError):
        read_fast_paper_runtime_manifest(nonfinite)


def test_runtime_state_is_identity_cursor_only_and_atomically_replaceable(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)

    assert initial.schema_name == FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME
    assert initial.manifest_fingerprint_sha256 == (
        manifest.manifest_fingerprint_sha256
    )
    assert initial.release_source_sha == manifest.release_source_sha
    assert initial.champion_fingerprint_sha256 == (
        manifest.champion_fingerprint_sha256
    )
    assert initial.action_policy_version == manifest.action_policy.version
    assert initial.cursor is None

    destination = Path(manifest.checkpoint_path)
    write_fast_paper_runtime_state(initial, destination)
    assert read_fast_paper_runtime_state(destination) == initial
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    cursor = FastPaperRuntimeCursor(
        decision_sequence=41,
        source_event_id="signature:0",
        decision_observed_at_unix_ms=50_000,
    )
    advanced = build_fast_paper_runtime_state(manifest, cursor=cursor)
    write_fast_paper_runtime_state(advanced, destination)

    assert read_fast_paper_runtime_state(destination) == advanced
    assert not tuple(destination.parent.glob(f".{destination.name}.tmp-*"))


def test_state_codec_rejects_tamper_unknown_fields_and_symlink_destination(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    state = build_fast_paper_runtime_state(
        manifest,
        cursor=FastPaperRuntimeCursor(
            decision_sequence=1,
            source_event_id="event-1",
            decision_observed_at_unix_ms=1_000,
        ),
    )
    destination = tmp_path / "state.json"
    write_fast_paper_runtime_state(state, destination)

    document = json.loads(destination.read_text(encoding="utf-8"))
    document["state_fingerprint_sha256"] = "f" * 64
    tampered = tmp_path / "tampered-state.json"
    tampered.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fingerprint"):
        read_fast_paper_runtime_state(tampered)

    document = json.loads(destination.read_text(encoding="utf-8"))
    document["score_policy_version"] = "forbidden"
    polluted = tmp_path / "polluted-state.json"
    polluted.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown or missing"):
        read_fast_paper_runtime_state(polluted)

    target = tmp_path / "real-state.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "state-link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        write_fast_paper_runtime_state(state, link)


def test_fast_paper_runtime_public_api_and_source_are_score_free() -> None:
    import shreks_brain.fast_paper_runtime as runtime

    assert runtime.__all__ == (
        "FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME",
        "FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME",
        "FAST_PAPER_RUNTIME_SCHEMA_VERSION",
        "FastPaperRuntimeCursor",
        "FastPaperRuntimeManifest",
        "FastPaperRuntimeState",
        "build_fast_paper_runtime_manifest",
        "build_fast_paper_runtime_state",
        "read_fast_paper_runtime_manifest",
        "read_fast_paper_runtime_state",
        "verify_fast_paper_runtime_bindings",
        "write_fast_paper_runtime_manifest",
        "write_fast_paper_runtime_state",
    )

    package_root = Path(runtime.__file__).resolve().parent
    source = "\n".join(
        child.read_text(encoding="utf-8")
        for child in sorted(package_root.glob("*.py"))
    )
    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
        "ScorePolicy",
        "DecisionPolicy",
        "TOTAL_SCORE_BELOW_THRESHOLD",
        "required_score_threshold",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
