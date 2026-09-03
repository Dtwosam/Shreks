from __future__ import annotations

from shreks_brain.fast_learning import extract_fast_forecast_features
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .models import (
    FastCampaignActionConstraints,
    FastCampaignDecisionPosition,
    FastCampaignDecisionRequest,
)


def build_fast_campaign_decision_request(
    record: FastTrainingFeatureRecord,
    position: FastCampaignDecisionPosition,
    constraints: FastCampaignActionConstraints,
) -> FastCampaignDecisionRequest:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be an exact FastTrainingFeatureRecord")
    if type(position) is not FastCampaignDecisionPosition:
        raise ValueError("position must be an exact FastCampaignDecisionPosition")
    if type(constraints) is not FastCampaignActionConstraints:
        raise ValueError("constraints must be exact FastCampaignActionConstraints")

    features = extract_fast_forecast_features(record)
    return FastCampaignDecisionRequest(
        source_event_id=f"{record.decision_signature}:{record.decision_ordinal}",
        market_key=f"{record.venue}:{record.mint}:{record.quote_mint}",
        source_sequence=record.decision_sequence,
        as_of_unix_ms=record.decision_observed_at_unix_ms,
        features=features,
        position=position,
        constraints=constraints,
    )
