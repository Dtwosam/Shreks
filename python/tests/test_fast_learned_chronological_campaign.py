from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fast_forecast_fixtures import feature_record
from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign import (
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_campaign.models import FastCampaignActionCandidate
from shreks_brain.fast_campaign_paper import (
    FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
    FastCampaignPaperCandidateIdentity,
)
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignPaperEvidence,
    FastLearnedCampaignRow,
    run_fast_learned_chronological_campaign,
)
from shreks_brain.fast_paper import (
    FastPaperBuyOutcome,
    FastPaperPositionActionPolicy,
)
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperLedgerUpdateState,
    PaperPositionState,
    create_paper_ledger,
)
from shreks_brain.risk import RiskPolicy


def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000,),
        entry_exposure_candidates=(0.5,),
        reduce_target_exposure_candidates=(0.25,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=100.0,
        route_unavailability_penalty_bps=100.0,
        horizon_disagreement_weight=1.0,
        minimum_buy_value_bps=1.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )


def _constraints() -> FastCampaignActionConstraints:
    return FastCampaignActionConstraints(
        max_exposure_fraction=1.0,
        buy_economically_allowed=True,
        expected_future_exit_cost_bps=10.0,
        reduce_execution_costs=(),
        sell_executable=True,
        sell_now_cost_bps=10.0,
        force_sell=False,
    )


def _raw(record) -> FastDeterministicCampaignPaperEvidence:
    return FastDeterministicCampaignPaperEvidence(
        source_event_id=f"{record.decision_signature}:{record.decision_ordinal}",
        state_version="learned-state-v1",
        evaluated_at_unix_ms=record.decision_observed_at_unix_ms,
        quote=None,
        risk_context=None,
        entry_authority=None,
        market_regime=None,
    )


def _identity() -> FastCampaignPaperCandidateIdentity:
    return FastCampaignPaperCandidateIdentity(
        version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
        paper_run_id="learned-paper-run",
        candidate_version="learned-continuous-v1",
        candidate_fingerprint_sha256="a" * 64,
        strategy_family="fl9-continuous-action",
        strategy_version="fl9-continuous-v1",
        assessment_version="assessment-v1",
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-v1",
        required_decision_policy_version="not-applicable:fast-learned",
        required_feature_schema_version="1",
        target_position_notional_usd=100.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=0.1,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=5_000.0,
        max_daily_realized_loss_usd=1_000.0,
        max_rolling_drawdown_pct=20.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=60,
        min_liquidity_usd=0.0,
        max_expected_price_impact_pct=5.0,
        max_slippage_bps=500,
        max_market_data_age_ms=10_000,
    )


def _decision(request, action: str, current: float, target: float):
    return FastCampaignDecisionResult(
        source_event_id=request.source_event_id,
        market_key=request.market_key,
        source_sequence=request.source_sequence,
        as_of_unix_ms=request.as_of_unix_ms,
        policy_version=1,
        action=action,
        reason=f"{action}_SELECTED",
        selected_horizon_ms=None,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
        selected_reward_bps=0.0,
        selected_risk_bps=0.0,
        selected_execution_cost_bps=0.0,
        selected_value_bps=0.0,
        horizon_evidence=(),
        candidates=(
            FastCampaignActionCandidate(
                action=action,
                horizon_ms=None,
                target_exposure_fraction=target,
                reward_bps=0.0,
                risk_bps=0.0,
                execution_cost_penalty_bps=0.0,
                comparison_value_bps=0.0,
                eligible=True,
            ),
        ),
    )


def _results(requests, actions):
    decisions = tuple(
        _decision(
            request,
            action,
            0.0 if index == 0 else 0.5,
            0.5 if action == "BUY" else (0.5 if action == "HOLD" else 0.0),
        )
        for index, (request, action) in enumerate(zip(requests, actions))
    )
    return FastCampaignDecisionResults(
        schema_name=FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
        schema_version=FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        champion_version="champion-v1",
        champion_fingerprint_sha256="b" * 64,
        decisions=decisions,
        batch_fingerprint_sha256="c" * 64,
    )


def test_learned_campaign_feeds_actual_filled_paper_posture_into_next_rust_prefix(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "learned-decision"
    champion = tmp_path / "champion.json"
    binary.write_text("binary", encoding="utf-8")
    champion.write_text("champion", encoding="utf-8")
    r1 = feature_record(0, 1.0, signature="learned-1")
    r2 = feature_record(
        1,
        2.0,
        signature="learned-2",
        observed_at_unix_ms=r1.decision_observed_at_unix_ms + 100,
    )
    rows = (
        FastLearnedCampaignRow(r1, _constraints(), _constraints(), _raw(r1)),
        FastLearnedCampaignRow(r2, _constraints(), _constraints(), _raw(r2)),
    )
    prefixes = []

    def fake_prefix(**kwargs):
        batch = kwargs["batch"]
        prefixes.append(batch)
        actions = ("BUY",) if len(batch.decisions) == 1 else ("BUY", "HOLD")
        return _results(batch.decisions, actions)

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "evaluate_fast_campaign_decision_batch_offline",
        fake_prefix,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "materialize_fast_campaign_paper_evidence",
        lambda **kwargs: SimpleNamespace(
            source_event_id=kwargs["source_event_id"]
        ),
    )

    calls = []

    def fake_paper(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            update = SimpleNamespace(
                state=PaperLedgerUpdateState.APPLIED,
                position_id="position-1",
            )
            buy = SimpleNamespace(
                source_event_id=f"{r1.decision_signature}:0",
                outcome=FastPaperBuyOutcome.FILLED,
                ledger_update=update,
            )
            return SimpleNamespace(
                buy_results=(buy,),
                position_results=(),
                final_ledger=SimpleNamespace(
                    positions=(
                        SimpleNamespace(
                            position_id="position-1",
                            state=PaperPositionState.OPEN,
                            opened_at_unix_ms=r1.decision_observed_at_unix_ms,
                        ),
                    )
                ),
            )
        return SimpleNamespace(
            buy_results=calls[0]["decisions"].decisions[:0],
            position_results=(),
            final_ledger=calls[0].get(
                "_unused",
                SimpleNamespace(
                    positions=(
                        SimpleNamespace(
                            position_id="position-1",
                            state=PaperPositionState.OPEN,
                            opened_at_unix_ms=r1.decision_observed_at_unix_ms,
                        ),
                    )
                ),
            ),
        )

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "run_fast_campaign_paper_candidate",
        fake_paper,
    )

    result = run_fast_learned_chronological_campaign(
        decision_binary_path=binary,
        champion_path=champion,
        identity=_identity(),
        policy=_policy(),
        rows=rows,
        starting_ledger=create_paper_ledger(10_000.0, 0),
        fill_policy=PaperFillPolicy(
            version="fill-v1",
            assumed_latency_ms=0,
            max_quote_lag_ms=5_000,
            swap_fee_bps=0,
            network_fee_usd=0.0,
            allow_partial_fills=False,
            min_partial_fill_fraction=1.0,
        ),
        risk_policy=_risk_policy(),
        position_policy=FastPaperPositionActionPolicy(
            version="position-v1",
            max_slippage_bps=500,
        ),
        evaluation_policy=TradingEvaluationPolicy(
            version="evaluation-v1",
            starting_equity_usd=10_000.0,
            calibration_bucket_count=10,
        ),
    )

    assert result is calls[-1] or result is not None
    assert len(prefixes) == 2
    assert prefixes[0].decisions[0].position.kind == "FLAT"
    assert prefixes[1].decisions[1].position.kind == "OPEN"
    assert prefixes[1].decisions[1].position.current_exposure_fraction == pytest.approx(0.5)
    assert prefixes[1].decisions[0] == prefixes[0].decisions[0]


def test_learned_campaign_rejects_rust_history_drift_before_second_paper_apply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "learned-decision"
    champion = tmp_path / "champion.json"
    binary.write_text("binary", encoding="utf-8")
    champion.write_text("champion", encoding="utf-8")
    r1 = feature_record(0, 1.0, signature="drift-1")
    r2 = feature_record(1, 2.0, signature="drift-2")
    rows = (
        FastLearnedCampaignRow(r1, _constraints(), _constraints(), _raw(r1)),
        FastLearnedCampaignRow(r2, _constraints(), _constraints(), _raw(r2)),
    )
    count = {"value": 0}

    def fake_prefix(**kwargs):
        count["value"] += 1
        batch = kwargs["batch"]
        results = _results(
            batch.decisions,
            ("SKIP",) if len(batch.decisions) == 1 else ("SKIP", "SKIP"),
        )
        if len(batch.decisions) == 2:
            changed = _decision(batch.decisions[0], "BUY", 0.0, 0.5)
            return FastCampaignDecisionResults(
                schema_name=results.schema_name,
                schema_version=results.schema_version,
                champion_version=results.champion_version,
                champion_fingerprint_sha256=results.champion_fingerprint_sha256,
                decisions=(changed, results.decisions[1]),
                batch_fingerprint_sha256=results.batch_fingerprint_sha256,
            )
        return results

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "evaluate_fast_campaign_decision_batch_offline",
        fake_prefix,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "materialize_fast_campaign_paper_evidence",
        lambda **kwargs: SimpleNamespace(
            source_event_id=kwargs["source_event_id"]
        ),
    )
    paper_calls = []
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.learned."
        "run_fast_campaign_paper_candidate",
        lambda **kwargs: (
            paper_calls.append(kwargs)
            or SimpleNamespace(
                buy_results=(),
                position_results=(),
                final_ledger=SimpleNamespace(positions=()),
            )
        ),
    )

    with pytest.raises(ValueError, match="drift|history|prefix"):
        run_fast_learned_chronological_campaign(
            decision_binary_path=binary,
            champion_path=champion,
            identity=_identity(),
            policy=_policy(),
            rows=rows,
            starting_ledger=create_paper_ledger(10_000.0, 0),
            fill_policy=PaperFillPolicy(
                version="fill-v1",
                assumed_latency_ms=0,
                max_quote_lag_ms=5_000,
                swap_fee_bps=0,
                network_fee_usd=0.0,
                allow_partial_fills=False,
                min_partial_fill_fraction=1.0,
            ),
            risk_policy=_risk_policy(),
            position_policy=FastPaperPositionActionPolicy(
                version="position-v1",
                max_slippage_bps=500,
            ),
            evaluation_policy=TradingEvaluationPolicy(
                version="evaluation-v1",
                starting_equity_usd=10_000.0,
                calibration_bucket_count=10,
            ),
        )

    assert len(paper_calls) == 1


def test_learned_campaign_source_has_no_provider_superiority_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "learned.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sqlite3",
        "requests.",
        "httpx",
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source
