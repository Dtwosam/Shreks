from __future__ import annotations

import pytest

import shreks_brain.research.fast_training_bundle as training_bundle


@pytest.mark.parametrize(
    "decision_id",
    (
        "position:open-123",
        "position-123:h250:v1",
        "decision:0:v1",
        "decision:0:h250",
        "decision:0:h250:v1:extra",
    ),
)
def test_noncanonical_or_open_position_counterfactual_ids_fail_closed(
    decision_id: str,
) -> None:
    with pytest.raises(ValueError, match="canonical FL4 entry decision identity"):
        training_bundle._parse_entry_decision_id(decision_id)


def test_fl81_training_bundle_module_has_no_model_execution_or_live_authority() -> None:
    forbidden_public_names = {
        "train",
        "fit",
        "estimator",
        "champion",
        "promote",
        "provider",
        "sign",
        "submit",
        "transaction",
        "trade",
        "create_trade_intent",
        "enable_live",
    }
    assert forbidden_public_names.isdisjoint(set(dir(training_bundle)))
