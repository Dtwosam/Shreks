from __future__ import annotations

from dataclasses import replace

import pytest

from fast_forecast_fixtures import feature_record
from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignDecisionPosition,
    FastCampaignReduceExecutionCost,
    build_fast_campaign_decision_request,
)
from shreks_brain.fast_learning import (
    FAST_FORECAST_FEATURE_NAMES,
    extract_fast_forecast_features,
)


def _constraints() -> FastCampaignActionConstraints:
    return FastCampaignActionConstraints(
        max_exposure_fraction=1.0,
        buy_economically_allowed=True,
        expected_future_exit_cost_bps=10.0,
        reduce_execution_costs=(
            FastCampaignReduceExecutionCost(0.5, 20.0),
        ),
        sell_executable=True,
        sell_now_cost_bps=15.0,
        force_sell=False,
    )


def test_feature_row_adapter_uses_sealed_forecast_extractor_and_preserves_identity() -> None:
    record = feature_record(2, 2.5, with_context=True)
    request = build_fast_campaign_decision_request(
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        _constraints(),
    )

    assert request.features == extract_fast_forecast_features(record)
    assert len(request.features) == len(FAST_FORECAST_FEATURE_NAMES) == 169
    assert request.source_event_id == (
        f"{record.decision_signature}:{record.decision_ordinal}"
    )
    assert request.source_sequence == record.decision_sequence
    assert request.as_of_unix_ms == record.decision_observed_at_unix_ms
    assert request.market_key == (
        f"{record.venue}:{record.mint}:{record.quote_mint}"
    )


def test_feature_row_future_context_still_fails_through_sealed_extractor() -> None:
    record = feature_record(2, 2.5, with_context=True)
    assert record.last_lifecycle_event is not None
    future = replace(
        record,
        last_lifecycle_event=replace(
            record.last_lifecycle_event,
            detected_at_unix_ms=record.decision_observed_at_unix_ms + 1,
        ),
    )
    with pytest.raises(ValueError, match="future|lifecycle"):
        build_fast_campaign_decision_request(
            future,
            FastCampaignDecisionPosition(kind="FLAT"),
            _constraints(),
        )
