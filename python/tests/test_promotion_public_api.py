from __future__ import annotations

import inspect
import sys

import shreks_brain.promotion as promotion
from shreks_brain.promotion import engine


def test_task2_public_api_is_deliberately_small() -> None:
    assert set(promotion.__all__) == {
        "PROMOTION_SCHEMA_VERSION",
        "PromotionDecision",
        "PromotionGateStatus",
        "PromotionGateCode",
        "PromotionPolicy",
        "PromotionGateResult",
        "PromotionAssessment",
        "evaluate_promotion",
    }


def test_promotion_policy_has_no_default_thresholds() -> None:
    signature = inspect.signature(promotion.PromotionPolicy)
    for parameter in signature.parameters.values():
        assert parameter.default is inspect.Parameter.empty


def test_task2_api_has_no_registry_execution_or_live_authority() -> None:
    forbidden = {
        "PromotionAssessmentStore",
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

    source = inspect.getsource(engine)
    for token in (
        "RegistryStore",
        "record_status(",
        "record_status_event(",
        "TradeIntent",
        "PaperExecutionResult",
        "enable_live",
        ".sign(",
        ".submit(",
    ):
        assert token not in source


def test_importing_promotion_does_not_eagerly_import_heavy_training_or_parquet_modules() -> None:
    assert "sklearn" not in sys.modules
    assert "pyarrow" not in sys.modules
