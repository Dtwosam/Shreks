from __future__ import annotations

import inspect

import shreks_brain.promotion as promotion


def test_task1_public_api_is_deliberately_small() -> None:
    assert set(promotion.__all__) == {
        "PROMOTION_SCHEMA_VERSION",
        "PromotionDecision",
        "PromotionGateStatus",
        "PromotionGateCode",
        "PromotionPolicy",
        "PromotionGateResult",
        "PromotionAssessment",
    }


def test_promotion_policy_has_no_default_thresholds() -> None:
    signature = inspect.signature(promotion.PromotionPolicy)
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty


def test_task1_api_has_no_registry_execution_or_live_authority() -> None:
    forbidden = {
        "PromotionAssessmentStore",
        "evaluate_promotion",
        "RegistryStore",
        "record_status",
        "record_status_event",
        "TradeIntent",
        "PaperExecutionResult",
        "enable_live",
        "promote",
        "sign",
        "submit",
    }
    assert forbidden.isdisjoint(set(dir(promotion)))
