from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from fast_forecast_fixtures import feature_record
from shreks_brain.fast_campaign import (
    FastCampaignActionCandidate,
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION,
    FastPaperShadowDecisionInput,
    FastPaperShadowEvidenceStore,
    build_fast_paper_runtime_manifest,
    evaluate_fast_paper_shadow_batch,
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


def _constraints() -> FastCampaignActionConstraints:
    return FastCampaignActionConstraints(
        max_exposure_fraction=0.5,
        buy_economically_allowed=True,
        expected_future_exit_cost_bps=8.0,
        reduce_execution_costs=(),
        sell_executable=True,
        sell_now_cost_bps=7.0,
        force_sell=False,
    )


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def _manifest(tmp_path: Path):
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="shadow-champion-v1",
        decision_reference="shadow-runtime-red",
        decided_at_unix_ms=10_000,
        reason="shadow runtime fixture",
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


def _input() -> FastPaperShadowDecisionInput:
    record = feature_record(
        0,
        0.0,
        signature="shadow-event",
        observed_at_unix_ms=20_000,
        with_context=False,
    )
    return FastPaperShadowDecisionInput(
        record=record,
        position=FastCampaignDecisionPosition(kind="FLAT"),
        constraints=_constraints(),
        evaluated_at_unix_ms=20_037,
        quote_state="EXECUTABLE",
    )


def _result(manifest, request) -> FastCampaignDecisionResults:
    candidate = FastCampaignActionCandidate(
        action="BUY",
        horizon_ms=250,
        target_exposure_fraction=0.5,
        reward_bps=31.0,
        risk_bps=9.0,
        execution_cost_penalty_bps=6.0,
        comparison_value_bps=16.0,
        eligible=True,
    )
    decision = FastCampaignDecisionResult(
        source_event_id=request.source_event_id,
        market_key=request.market_key,
        source_sequence=request.source_sequence,
        as_of_unix_ms=request.as_of_unix_ms,
        policy_version=manifest.action_policy.version,
        action="BUY",
        reason="BUY_SELECTED",
        selected_horizon_ms=250,
        current_exposure_fraction=0.0,
        target_exposure_fraction=0.5,
        selected_reward_bps=31.0,
        selected_risk_bps=9.0,
        selected_execution_cost_bps=6.0,
        selected_value_bps=16.0,
        horizon_evidence=(),
        candidates=(candidate,),
    )
    return FastCampaignDecisionResults(
        schema_name="shreks.fast_campaign_decision_results",
        schema_version=1,
        champion_version=manifest.champion_version,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        decisions=(decision,),
        batch_fingerprint_sha256="d" * 64,
    )


def test_shadow_batch_records_exact_learned_decision_and_latency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    item = _input()
    captured = {}

    def fake_eval(*, binary_path, champion_path, batch):
        captured["binary_path"] = Path(binary_path)
        captured["champion_path"] = Path(champion_path)
        captured["batch"] = batch
        return _result(manifest, batch.decisions[0])

    monkeypatch.setattr(
        "shreks_brain.fast_paper_runtime.shadow."
        "evaluate_fast_campaign_decision_batch_offline",
        fake_eval,
    )

    ledger = evaluate_fast_paper_shadow_batch(manifest, (item,))
    assert ledger.schema_name == FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_NAME
    assert ledger.schema_version == FAST_PAPER_SHADOW_EVIDENCE_SCHEMA_VERSION
    assert len(ledger.records) == 1

    evidence = ledger.records[0]
    assert evidence.source_event_id == "shadow-event:0"
    assert evidence.action == "BUY"
    assert evidence.selected_horizon_ms == 250
    assert evidence.selected_value_bps == 16.0
    assert evidence.quote_state == "EXECUTABLE"
    assert evidence.event_to_decision_latency_ms == 37
    assert evidence.champion_fingerprint_sha256 == (
        manifest.champion_fingerprint_sha256
    )
    assert captured["binary_path"] == Path(manifest.decision_binary_path)
    assert captured["champion_path"] == Path(manifest.champion_path)


def test_shadow_batch_fails_closed_on_champion_or_population_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    item = _input()

    def wrong_champion(*, batch, **_kwargs):
        result = _result(manifest, batch.decisions[0])
        return replace(result, champion_fingerprint_sha256="f" * 64)

    monkeypatch.setattr(
        "shreks_brain.fast_paper_runtime.shadow."
        "evaluate_fast_campaign_decision_batch_offline",
        wrong_champion,
    )
    with pytest.raises(ValueError, match="champion"):
        evaluate_fast_paper_shadow_batch(manifest, (item,))

    def wrong_population(*, batch, **_kwargs):
        result = _result(manifest, batch.decisions[0])
        bad = replace(result.decisions[0], source_event_id="other:0")
        return replace(result, decisions=(bad,))

    monkeypatch.setattr(
        "shreks_brain.fast_paper_runtime.shadow."
        "evaluate_fast_campaign_decision_batch_offline",
        wrong_population,
    )
    with pytest.raises(ValueError, match="identity|population"):
        evaluate_fast_paper_shadow_batch(manifest, (item,))


def test_shadow_store_is_idempotent_private_and_cannot_target_authoritative_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    item = _input()

    def fake_eval(*, batch, **_kwargs):
        return _result(manifest, batch.decisions[0])

    monkeypatch.setattr(
        "shreks_brain.fast_paper_runtime.shadow."
        "evaluate_fast_campaign_decision_batch_offline",
        fake_eval,
    )
    record = evaluate_fast_paper_shadow_batch(manifest, (item,)).records[0]

    store = FastPaperShadowEvidenceStore(
        tmp_path / "shadow" / "evidence.json",
        manifest=manifest,
    )
    first = store.append(record)
    second = store.append(record)
    assert first == second
    assert len(second.records) == 1
    assert (tmp_path / "shadow" / "evidence.json").stat().st_mode & 0o777 == 0o600

    conflict = replace(
        record,
        selected_value_bps=record.selected_value_bps + 1.0,
        record_fingerprint_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="conflict|fingerprint"):
        store.append(conflict)

    with pytest.raises(ValueError, match="authoritative"):
        FastPaperShadowEvidenceStore(
            manifest.paper_evidence_path,
            manifest=manifest,
        )
    with pytest.raises(ValueError, match="authoritative"):
        FastPaperShadowEvidenceStore(
            manifest.checkpoint_path,
            manifest=manifest,
        )


def test_shadow_source_has_no_score_future_label_execution_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime as runtime

    root = Path(runtime.__file__).resolve().parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "shadow.py", root / "shadow_store.py")
    )
    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "fast_training_targets",
        "future_path_labels",
        "counterfactual",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    )
    for marker in forbidden:
        assert marker not in source


def test_shadow_service_is_separate_and_has_no_legacy_paper_lifecycle_authority() -> None:
    unit = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "systemd"
        / "shreks-fast-paper-shadow.service"
    ).read_text(encoding="utf-8")

    assert "User=shreks" in unit
    assert "Group=shreks" in unit
    assert "/opt/shreks/current/.venv/bin/python" in unit
    assert "shreks_brain.fast_paper_runtime.shadow_runtime" in unit
    assert "RuntimeMode.LIVE" not in unit
    for forbidden in (
        "PartOf=shreks.target",
        "WantedBy=shreks.target",
        "Requires=shreks-paper-campaign.service",
        "Conflicts=shreks-paper-campaign.service",
        "ExecStop=systemctl",
        "PRIVATE_KEY",
        "WALLET",
        "SIGNER",
    ):
        assert forbidden not in unit
