from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from fast_forecast_fixtures import feature_record
from shreks_brain.fast_campaign import (
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_campaign.models import FastCampaignActionCandidate
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION,
    FastPaperShadowCycleInput,
    FastPaperShadowQuoteEvidence,
    build_fast_paper_runtime_manifest,
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_state,
    read_fast_paper_shadow_decision_evidence,
    run_fast_paper_shadow_batch,
)
from shreks_brain.research.fast_training_features import (
    feature_logical_fingerprint_sha256,
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
        champion_version="shadow-orchestration-v1",
        decision_reference="shadow-orchestration-fixture",
        decided_at_unix_ms=10_000,
        reason="shadow orchestration fixture",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    return path


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def _manifest(tmp_path: Path):
    return build_fast_paper_runtime_manifest(
        release_source_sha=_RELEASE_SHA,
        champion_path=_champion(tmp_path),
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
        paper_evidence_path=tmp_path / "paper-evidence.sqlite3",
        checkpoint_path=tmp_path / "fast-paper-runtime-state.json",
        quote_provider="jupiter",
        quote_mint=_QUOTE_MINT,
        quote_decimals=9,
        route_evidence_version="observer-paper-quote-v1",
    )


def _record(index: int, *, signature: str = "shadow-cycle"):
    base = feature_record(
        index,
        float(index),
        signature=signature,
        observed_at_unix_ms=20_000 + index * 100,
        with_context=True,
    )
    return replace(
        base,
        decision_ordinal=index,
        decision_executable_entry_price_quote=1.0,
    )


def _quote(record, *, observed_at: int, execution_price: float):
    return FastPaperShadowQuoteEvidence(
        provider="jupiter",
        mint=record.mint,
        quote_mint=record.quote_mint,
        observed_at_unix_ms=observed_at,
        state="EXECUTABLE",
        reference_price_quote=1.0,
        execution_price_quote=execution_price,
        quoted_base_quantity=2.0,
        available_base_quantity=2.0,
    )


def _cycle_input(record) -> FastPaperShadowCycleInput:
    return FastPaperShadowCycleInput(
        record=record,
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at_unix_ms=record.decision_observed_at_unix_ms + 20,
        max_exposure_fraction=0.5,
        entry_quote=_quote(
            record,
            observed_at=record.decision_observed_at_unix_ms + 10,
            execution_price=1.01,
        ),
        exit_quote=_quote(
            record,
            observed_at=record.decision_observed_at_unix_ms + 15,
            execution_price=0.98,
        ),
        reduction_quotes=(),
        force_sell=False,
    )


def _fake_champion(manifest):
    member = SimpleNamespace(
        forecast_artifact=SimpleNamespace(
            max_training_decision_observed_at_unix_ms=15_000
        )
    )
    return SimpleNamespace(
        champion_version=manifest.champion_version,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        feature_schema_version=manifest.feature_schema_version,
        selection=SimpleNamespace(decided_at_unix_ms=10_000),
        member_for=lambda target, horizon_ms: member,
    )


def _result_fingerprint(manifest, decision) -> str:
    material = {
        "schema_name": "shreks.fast_campaign_decision_results",
        "schema_version": 1,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "decisions": [asdict(decision)],
    }
    return hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _install_shadow_decision_stubs(monkeypatch, manifest, calls) -> None:
    import shreks_brain.fast_paper_runtime.shadow as shadow

    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda path: _fake_champion(manifest),
    )

    def fake_evaluate(
        *,
        binary_path,
        champion_path,
        batch,
        timeout_seconds=None,
    ):
        calls.append(batch.decisions[0].source_event_id)
        request = batch.decisions[0]
        decision = FastCampaignDecisionResult(
            source_event_id=request.source_event_id,
            market_key=request.market_key,
            source_sequence=request.source_sequence,
            as_of_unix_ms=request.as_of_unix_ms,
            policy_version=manifest.action_policy.version,
            action="SKIP",
            reason="SKIP_SELECTED",
            selected_horizon_ms=None,
            current_exposure_fraction=0.0,
            target_exposure_fraction=0.0,
            selected_reward_bps=0.0,
            selected_risk_bps=0.0,
            selected_execution_cost_bps=0.0,
            selected_value_bps=0.0,
            horizon_evidence=(),
            candidates=(
                FastCampaignActionCandidate(
                    action="SKIP",
                    horizon_ms=None,
                    target_exposure_fraction=0.0,
                    reward_bps=0.0,
                    risk_bps=0.0,
                    execution_cost_penalty_bps=0.0,
                    comparison_value_bps=0.0,
                    eligible=True,
                ),
            ),
        )
        return FastCampaignDecisionResults(
            schema_name="shreks.fast_campaign_decision_results",
            schema_version=1,
            champion_version=manifest.champion_version,
            champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
            decisions=(decision,),
            batch_fingerprint_sha256=_result_fingerprint(
                manifest,
                decision,
            ),
        )

    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        fake_evaluate,
    )


def test_shadow_batch_writes_evidence_before_cursor_and_binds_feature_record(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    record = _record(0)
    item = _cycle_input(record)
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    final = run_fast_paper_shadow_batch(
        manifest,
        initial,
        (item,),
        evidence_directory=tmp_path / "shadow-evidence",
    )

    assert calls == ["shadow-cycle:0"]
    assert final.cursor is not None
    assert final.cursor.decision_sequence == record.decision_sequence
    assert read_fast_paper_runtime_state(
        manifest.checkpoint_path
    ) == final

    files = tuple((tmp_path / "shadow-evidence").glob("*.json"))
    assert len(files) == 1
    assert not tuple(
        (tmp_path / "shadow-evidence").glob(".*.tmp-*")
    )
    assert "shadow-cycle" not in files[0].name
    evidence = read_fast_paper_shadow_decision_evidence(files[0])
    assert FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION == 2
    assert evidence.feature_record_fingerprint_sha256 == (
        feature_logical_fingerprint_sha256((record,))
    )


def test_shadow_batch_evidence_fsync_failure_leaves_no_partial_artifact_or_cursor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow as shadow

    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    item = _cycle_input(_record(0))
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    monkeypatch.setattr(
        shadow,
        "_fsync_directory",
        lambda path: (_ for _ in ()).throw(
            OSError("simulated evidence directory fsync failure")
        ),
    )

    with pytest.raises(OSError, match="evidence directory fsync failure"):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (item,),
            evidence_directory=tmp_path / "shadow-evidence",
        )

    assert calls == ["shadow-cycle:0"]
    assert not tuple((tmp_path / "shadow-evidence").glob("*.json"))
    assert not tuple(
        (tmp_path / "shadow-evidence").glob(".*.tmp-*")
    )
    assert not Path(manifest.checkpoint_path).exists()


def test_shadow_batch_reuses_durable_evidence_after_checkpoint_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow_cycle as cycle

    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    item = _cycle_input(_record(0))
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    original_write = cycle.write_fast_paper_runtime_state
    attempts = {"count": 0}

    def fail_first_checkpoint(state, path):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("simulated checkpoint failure")
        return original_write(state, path)

    monkeypatch.setattr(
        cycle,
        "write_fast_paper_runtime_state",
        fail_first_checkpoint,
    )

    with pytest.raises(OSError, match="checkpoint failure"):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (item,),
            evidence_directory=tmp_path / "shadow-evidence",
        )

    assert calls == ["shadow-cycle:0"]
    assert not Path(manifest.checkpoint_path).exists()
    assert len(tuple((tmp_path / "shadow-evidence").glob("*.json"))) == 1

    final = run_fast_paper_shadow_batch(
        manifest,
        initial,
        (item,),
        evidence_directory=tmp_path / "shadow-evidence",
    )
    assert calls == ["shadow-cycle:0"]
    assert final.cursor is not None


def test_shadow_batch_rejects_conflicting_replay_without_rerunning_decision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow_cycle as cycle

    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    original_record = _record(0)
    item = _cycle_input(original_record)
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    monkeypatch.setattr(
        cycle,
        "write_fast_paper_runtime_state",
        lambda state, path: (_ for _ in ()).throw(
            OSError("leave evidence without checkpoint")
        ),
    )
    with pytest.raises(OSError):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (item,),
            evidence_directory=tmp_path / "shadow-evidence",
        )
    assert calls == ["shadow-cycle:0"]

    changed_record = replace(
        original_record,
        snapshot_last_price_quote=99.0,
    )
    changed_item = replace(item, record=changed_record)

    with pytest.raises(ValueError, match="feature.*fingerprint|replay"):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (changed_item,),
            evidence_directory=tmp_path / "shadow-evidence",
        )
    assert calls == ["shadow-cycle:0"]


def test_shadow_batch_failure_on_second_record_leaves_checkpoint_at_first(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow_cycle as cycle

    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    first = _cycle_input(_record(0))
    second = _cycle_input(_record(1))
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    real_evaluate = cycle.evaluate_fast_paper_shadow_decision

    def fail_second(manifest_value, record, position, **kwargs):
        if record.decision_ordinal == second.record.decision_ordinal:
            raise RuntimeError("simulated second decision failure")
        return real_evaluate(manifest_value, record, position, **kwargs)

    monkeypatch.setattr(
        cycle,
        "evaluate_fast_paper_shadow_decision",
        fail_second,
    )

    with pytest.raises(RuntimeError, match="second decision failure"):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (first, second),
            evidence_directory=tmp_path / "shadow-evidence",
        )

    durable = read_fast_paper_runtime_state(manifest.checkpoint_path)
    assert durable.cursor is not None
    assert durable.cursor.decision_sequence == first.record.decision_sequence
    assert calls == ["shadow-cycle:0"]


def test_shadow_batch_rejects_stale_supplied_state_and_authoritative_evidence_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    initial = build_fast_paper_runtime_state(manifest, cursor=None)
    item = _cycle_input(_record(0))
    calls = []
    _install_shadow_decision_stubs(monkeypatch, manifest, calls)

    final = run_fast_paper_shadow_batch(
        manifest,
        initial,
        (item,),
        evidence_directory=tmp_path / "shadow-evidence",
    )
    assert final.cursor is not None

    with pytest.raises(ValueError, match="checkpoint|state"):
        run_fast_paper_shadow_batch(
            manifest,
            initial,
            (item,),
            evidence_directory=tmp_path / "shadow-evidence",
        )

    with pytest.raises(ValueError, match="authoritative|paper evidence"):
        run_fast_paper_shadow_batch(
            manifest,
            final,
            (_cycle_input(_record(1)),),
            evidence_directory=manifest.paper_evidence_path,
        )


def test_shadow_cycle_source_has_no_score_ledger_provider_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime.shadow_cycle as cycle

    source = Path(cycle.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "PaperLedger",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
