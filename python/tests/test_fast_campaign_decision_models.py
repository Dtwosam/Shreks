from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fast_campaign import (
    FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionBatch,
    FastCampaignDecisionPosition,
    FastCampaignDecisionRequest,
    FastCampaignReduceExecutionCost,
    build_fast_campaign_decision_batch,
)
from shreks_brain.fast_learning import FAST_FORECAST_FEATURE_NAMES



def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000,),
        entry_exposure_candidates=(0.5, 1.0),
        reduce_target_exposure_candidates=(0.5,),
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
        expected_future_exit_cost_bps=12.0,
        reduce_execution_costs=(
            FastCampaignReduceExecutionCost(
                target_exposure_fraction=0.5,
                execution_cost_bps=20.0,
            ),
        ),
        sell_executable=True,
        sell_now_cost_bps=15.0,
        force_sell=False,
    )


def _request(
    *,
    event_id: str = "sig-a:0",
    market_key: str = "pump_fun_bonding_curve:mint-a:quote-a",
    sequence: int = 1,
    at: int = 1_000,
) -> FastCampaignDecisionRequest:
    return FastCampaignDecisionRequest(
        source_event_id=event_id,
        market_key=market_key,
        source_sequence=sequence,
        as_of_unix_ms=at,
        features=tuple([1.0] * len(FAST_FORECAST_FEATURE_NAMES)),
        position=FastCampaignDecisionPosition(kind="FLAT"),
        constraints=_constraints(),
    )


def test_public_schema_and_strict_models() -> None:
    assert (
        FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME
        == "shreks.fast_campaign_decision_batch"
    )
    assert (
        FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME
        == "shreks.fast_campaign_decision_results"
    )
    assert FAST_CAMPAIGN_DECISION_SCHEMA_VERSION == 1
    assert len(_request().features) == 169

    with pytest.raises(ValueError):
        FastCampaignDecisionPosition(kind="OPEN")
    with pytest.raises(ValueError):
        FastCampaignDecisionPosition(kind="FLAT", current_exposure_fraction=0.5)
    assert FastCampaignDecisionPosition(
        kind="OPEN", current_exposure_fraction=0.5
    ).current_exposure_fraction == pytest.approx(0.5)

    with pytest.raises(ValueError):
        replace(_request(), source_sequence=0)
    with pytest.raises(ValueError):
        replace(_request(), features=(1.0,))
    with pytest.raises(ValueError):
        replace(_request(), features=tuple([float("nan")] * 169))


def test_batch_rejects_duplicate_identity_and_per_market_order_regression() -> None:
    first = _request(sequence=2, at=2_000)
    duplicate = replace(first)
    with pytest.raises(ValueError, match="duplicate|event"):
        build_fast_campaign_decision_batch(
            _policy(),
            (first, duplicate),
        )

    regressing = _request(
        event_id="sig-b:0",
        sequence=1,
        at=2_001,
    )
    with pytest.raises(ValueError, match="order|sequence"):
        build_fast_campaign_decision_batch(
            _policy(),
            (first, regressing),
        )


def test_direct_batch_dataclass_requires_exact_schema() -> None:
    request = _request()
    with pytest.raises(ValueError):
        FastCampaignDecisionBatch(
            schema_name="wrong",
            schema_version=1,
            policy=_policy(),
            decisions=(request,),
        )
