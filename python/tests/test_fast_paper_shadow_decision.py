from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import stat
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
    FAST_PAPER_SHADOW_DECISION_SCHEMA_NAME,
    FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION,
    FastPaperShadowQuoteEvidence,
    FastPaperShadowReductionQuote,
    build_fast_paper_runtime_manifest,
    evaluate_fast_paper_shadow_decision,
    read_fast_paper_shadow_decision_evidence,
    write_fast_paper_shadow_decision_evidence,
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
        champion_version="shadow-champion-v1",
        decision_reference="shadow-fixture",
        decided_at_unix_ms=10_000,
        reason="shadow fixture",
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


def _record():
    base = feature_record(
        0,
        0.0,
        signature="shadow-event",
        observed_at_unix_ms=20_000,
        with_context=True,
    )
    return replace(
        base,
        decision_executable_entry_price_quote=1.0,
    )


def _quote(
    record,
    *,
    observed_at: int,
    state: str = "EXECUTABLE",
    execution_price: float | None = 1.0,
) -> FastPaperShadowQuoteEvidence:
    executable = state == "EXECUTABLE"
    return FastPaperShadowQuoteEvidence(
        provider="jupiter",
        mint=record.mint,
        quote_mint=record.quote_mint,
        observed_at_unix_ms=observed_at,
        state=state,
        reference_price_quote=(
            record.decision_executable_entry_price_quote
            if executable
            else None
        ),
        execution_price_quote=execution_price if executable else None,
        quoted_base_quantity=2.0 if executable else None,
        available_base_quantity=2.0 if executable else None,
    )


def _fake_champion(manifest, *, max_training_at: int = 15_000):
    member = SimpleNamespace(
        forecast_artifact=SimpleNamespace(
            max_training_decision_observed_at_unix_ms=max_training_at
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


def _result(manifest, request):
    decision = FastCampaignDecisionResult(
        source_event_id=request.source_event_id,
        market_key=request.market_key,
        source_sequence=request.source_sequence,
        as_of_unix_ms=request.as_of_unix_ms,
        policy_version=manifest.action_policy.version,
        action="REDUCE",
        reason="REDUCE_SELECTED",
        selected_horizon_ms=250,
        current_exposure_fraction=0.5,
        target_exposure_fraction=0.25,
        selected_reward_bps=100.0,
        selected_risk_bps=25.0,
        selected_execution_cost_bps=150.0,
        selected_value_bps=20.0,
        horizon_evidence=(),
        candidates=(
            FastCampaignActionCandidate(
                action="REDUCE",
                horizon_ms=250,
                target_exposure_fraction=0.25,
                reward_bps=100.0,
                risk_bps=25.0,
                execution_cost_penalty_bps=37.5,
                comparison_value_bps=20.0,
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


def test_shadow_decision_derives_constraints_invokes_bound_binary_and_seals_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow as shadow

    manifest = _manifest(tmp_path)
    record = _record()
    entry = _quote(record, observed_at=20_010, execution_price=1.01)
    exit_quote = _quote(record, observed_at=20_015, execution_price=0.98)
    reduction = FastPaperShadowReductionQuote(
        target_exposure_fraction=0.25,
        quote=_quote(record, observed_at=20_012, execution_price=0.985),
    )
    captured = {}

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
        captured["binary_path"] = Path(binary_path)
        captured["champion_path"] = Path(champion_path)
        captured["batch"] = batch
        captured["timeout_seconds"] = timeout_seconds
        return _result(manifest, batch.decisions[0])

    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        fake_evaluate,
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(shadow.time, "monotonic_ns", lambda: next(ticks))

    evidence = evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at_unix_ms=20_020,
        max_exposure_fraction=0.75,
        entry_quote=entry,
        exit_quote=exit_quote,
        reduction_quotes=(reduction,),
        force_sell=False,
    )

    request = captured["batch"].decisions[0]
    constraints = request.constraints
    assert captured["binary_path"] == Path(manifest.decision_binary_path)
    assert captured["champion_path"] == Path(manifest.champion_path)
    assert captured["timeout_seconds"] == 30.0
    assert constraints.buy_economically_allowed is True
    assert constraints.expected_future_exit_cost_bps == pytest.approx(200.0)
    assert constraints.sell_executable is True
    assert constraints.sell_now_cost_bps == pytest.approx(200.0)
    assert constraints.reduce_execution_costs[0].target_exposure_fraction == 0.25
    assert constraints.reduce_execution_costs[0].execution_cost_bps == pytest.approx(150.0)

    assert evidence.schema_name == FAST_PAPER_SHADOW_DECISION_SCHEMA_NAME
    assert evidence.schema_version == FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION
    assert evidence.source_event_id == "shadow-event:0"
    assert evidence.entry_execution_cost_bps == pytest.approx(100.0)
    assert evidence.decision_latency_ns == 250
    assert evidence.decision.action == "REDUCE"
    assert evidence.release_source_sha == manifest.release_source_sha

    destination = tmp_path / "shadow-decision.json"
    write_fast_paper_shadow_decision_evidence(evidence, destination)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert destination.read_bytes().endswith(b"\n")
    assert read_fast_paper_shadow_decision_evidence(destination) == evidence
    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_decision_evidence(evidence, destination)

    tampered_document = json.loads(
        destination.read_text(encoding="utf-8")
    )
    tampered_document["constraints"]["sell_now_cost_bps"] = 999.0
    material = dict(tampered_document)
    material.pop("evidence_fingerprint_sha256")
    tampered_document["evidence_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    tampered = tmp_path / "shadow-decision-tampered.json"
    tampered.write_text(
        json.dumps(
            tampered_document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sell cost constraint|mismatch"):
        read_fast_paper_shadow_decision_evidence(tampered)


def test_shadow_decision_rejects_future_quote_and_future_trained_champion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow as shadow

    manifest = _manifest(tmp_path)
    record = _record()
    entry = _quote(record, observed_at=20_100, execution_price=1.01)
    exit_quote = _quote(record, observed_at=20_015, execution_price=0.98)

    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda path: _fake_champion(manifest),
    )
    with pytest.raises(ValueError, match="chronology|timestamp|future"):
        evaluate_fast_paper_shadow_decision(
            manifest,
            record,
            FastCampaignDecisionPosition(kind="FLAT"),
            evaluated_at_unix_ms=20_020,
            max_exposure_fraction=0.5,
            entry_quote=entry,
            exit_quote=exit_quote,
        )

    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda path: _fake_champion(manifest, max_training_at=20_000),
    )
    with pytest.raises(ValueError, match="training|champion|future"):
        evaluate_fast_paper_shadow_decision(
            manifest,
            record,
            FastCampaignDecisionPosition(kind="FLAT"),
            evaluated_at_unix_ms=20_020,
            max_exposure_fraction=0.5,
            entry_quote=_quote(record, observed_at=20_010, execution_price=1.01),
            exit_quote=exit_quote,
        )


def test_shadow_decision_disables_buy_when_exit_route_is_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import shreks_brain.fast_paper_runtime.shadow as shadow

    manifest = _manifest(tmp_path)
    record = _record()
    captured = {}
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
        captured["constraints"] = batch.decisions[0].constraints
        captured["timeout_seconds"] = timeout_seconds
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

    evidence = evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at_unix_ms=20_020,
        max_exposure_fraction=0.5,
        entry_quote=_quote(record, observed_at=20_010, execution_price=1.01),
        exit_quote=_quote(
            record,
            observed_at=20_015,
            state="UNAVAILABLE",
            execution_price=None,
        ),
    )

    assert captured["constraints"].buy_economically_allowed is False
    assert captured["constraints"].sell_executable is False
    assert evidence.exit_execution_cost_bps is None
    assert evidence.decision.action == "SKIP"


def test_shadow_runtime_source_has_no_score_ledger_provider_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime as runtime

    source = "\n".join(
        child.read_text(encoding="utf-8")
        for child in sorted(Path(runtime.__file__).resolve().parent.glob("*.py"))
    )
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
