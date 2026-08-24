from __future__ import annotations

import shreks_brain.validation as validation


def test_time_validation_contract_public_api_is_explicit() -> None:
    assert validation.__all__ == (
        "TIME_AWARE_VALIDATION_SCHEMA_VERSION",
        "ChronologicalValidationFold",
        "TimeAwareValidationPolicy",
        "ValidationFoldResult",
        "TimeAwareValidationRun",
    )
