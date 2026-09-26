from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from fast_forecast_fixtures import feature_record
from shreks_brain.fast_campaign import FastCampaignContinuousActionPolicy
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_NAME,
    FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION,
    FastPaperRuntimeCursor,
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    fetch_fast_paper_runtime_feature_batch,
    verify_fast_paper_runtime_bindings,
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


def _champion(tmp_path: Path) -> Path:
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="runtime-feed-champion-v1",
        decision_reference="runtime-feed-fixture",
        decided_at_unix_ms=10_000,
        reason="runtime feed fixture",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    return path


def _executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)
    return path


def _fingerprint(document: dict[str, object], field: str) -> str:
    material = dict(document)
    material.pop(field)
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _feature_batch_payload() -> str:
    record = feature_record(
        0,
        0.0,
        signature="runtime-event",
        observed_at_unix_ms=1_000,
        with_context=False,
    )
    record = type(record)(
        **{
            **asdict(record),
            "decision_entry_total_quote": None,
            "windows": record.windows,
        }
    )
    document: dict[str, object] = {
        "schema_name": FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_NAME,
        "schema_version": FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION,
        "after_cursor": None,
        "snapshot_max_sequence": 1,
        "records": [asdict(record)],
        "batch_fingerprint_sha256": "0" * 64,
    }
    document["batch_fingerprint_sha256"] = _fingerprint(
        document,
        "batch_fingerprint_sha256",
    )
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _manifest(tmp_path: Path):
    champion_path = _champion(tmp_path)
    decision_binary = _executable(
        tmp_path / "shreks-fast-campaign-decision",
        "#!/bin/sh\nexit 0\n",
    )
    payload = _feature_batch_payload()
    feed_binary = _executable(
        tmp_path / "export_fast_runtime_features",
        "#!/bin/sh\nprintf '%b' "
        + repr(payload)
        + "\n",
    )
    return build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=champion_path,
        decision_binary_path=decision_binary,
        feature_feed_binary_path=feed_binary,
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


def test_runtime_manifest_v2_binds_feature_feed_binary(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    assert manifest.schema_version == 2
    assert Path(manifest.feature_feed_binary_path).is_absolute()
    assert len(manifest.feature_feed_binary_sha256) == 64
    verify_fast_paper_runtime_bindings(manifest)

    feed = Path(manifest.feature_feed_binary_path)
    feed.write_text(feed.read_text(encoding="utf-8") + "# tamper\n", encoding="utf-8")
    with pytest.raises(ValueError, match="feature feed binary SHA-256"):
        verify_fast_paper_runtime_bindings(manifest)


def test_adapter_fetches_unseen_features_and_returns_next_state(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    Path(manifest.observer_database_path).write_bytes(b"fixture-db")
    state = build_fast_paper_runtime_state(manifest, cursor=None)

    batch = fetch_fast_paper_runtime_feature_batch(
        manifest,
        state,
        maximum_decisions=10,
    )

    assert batch.schema_name == FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_NAME
    assert batch.schema_version == FAST_PAPER_RUNTIME_FEATURE_BATCH_SCHEMA_VERSION
    assert batch.snapshot_max_sequence == 1
    assert len(batch.records) == 1
    assert batch.records[0].decision_signature == "runtime-event"
    assert batch.records[0].decision_sequence == 1
    assert batch.records[0].decision_entry_total_quote is None
    assert batch.next_state.cursor == FastPaperRuntimeCursor(
        decision_sequence=1,
        decision_signature="runtime-event",
        decision_ordinal=0,
        decision_observed_at_unix_ms=1_000,
    )
    assert batch.next_state.manifest_fingerprint_sha256 == (
        manifest.manifest_fingerprint_sha256
    )


def test_adapter_rejects_state_manifest_mismatch_and_zero_limit(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    Path(manifest.observer_database_path).write_bytes(b"fixture-db")
    state = build_fast_paper_runtime_state(manifest, cursor=None)

    with pytest.raises(ValueError):
        fetch_fast_paper_runtime_feature_batch(
            manifest,
            state,
            maximum_decisions=0,
        )

    alien = type(state)(
        schema_name=state.schema_name,
        schema_version=state.schema_version,
        manifest_fingerprint_sha256="f" * 64,
        release_source_sha=state.release_source_sha,
        champion_fingerprint_sha256=state.champion_fingerprint_sha256,
        action_policy_version=state.action_policy_version,
        cursor=state.cursor,
        state_fingerprint_sha256=state.state_fingerprint_sha256,
    )
    with pytest.raises(ValueError):
        fetch_fast_paper_runtime_feature_batch(
            manifest,
            alien,
            maximum_decisions=10,
        )


def test_runtime_feed_source_cannot_import_future_labels_or_counterfactuals() -> None:
    import shreks_brain.fast_paper_runtime as runtime

    source = "\n".join(
        child.read_text(encoding="utf-8")
        for child in sorted(Path(runtime.__file__).resolve().parent.glob("*.py"))
    )
    forbidden = (
        "fast_training_targets",
        "counterfactual",
        "future_path_labels",
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
    )
    for marker in forbidden:
        assert marker not in source
