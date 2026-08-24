from __future__ import annotations

import shreks_brain.evaluation as evaluation


def test_e5_adapter_public_api_is_explicit() -> None:
    assert evaluation.__all__ == (
        "TRADING_EVALUATION_SCHEMA_VERSION",
        "TradingEvaluationPolicy",
        "EvaluatedTrade",
        "ProbabilityObservation",
        "TradingPerformanceMetrics",
        "CalibrationBucket",
        "CalibrationReport",
        "SegmentPerformance",
        "TradingEvaluationReport",
        "build_probability_observations_from_e4",
    )
