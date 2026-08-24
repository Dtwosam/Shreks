import inspect

import shreks_brain.shadow as shadow


def test_shadow_task1_public_api_is_deliberately_small() -> None:
    assert set(shadow.__all__) == {
        "SHADOW_CHALLENGER_SCHEMA_VERSION",
        "ShadowDecisionPolicy",
        "ShadowReasonCode",
        "ShadowDecisionRecord",
        "ShadowEvidenceLedger",
    }


def test_shadow_policy_has_no_default_probability_threshold() -> None:
    signature = inspect.signature(shadow.ShadowDecisionPolicy)
    assert signature.parameters["version"].default is inspect.Parameter.empty
    assert (
        signature.parameters["enter_min_probability"].default
        is inspect.Parameter.empty
    )


def test_shadow_task1_api_has_no_execution_or_promotion_authority() -> None:
    forbidden = {
        "RegistryStore",
        "record_status",
        "TradeIntent",
        "RiskAssessment",
        "PaperExecutionResult",
        "execute_paper",
        "promote",
        "enable_live",
        "sign",
        "submit",
    }
    assert forbidden.isdisjoint(set(dir(shadow)))
