from __future__ import annotations

import shreks_brain.evaluation as evaluation


def test_e5_public_api_is_explicit() -> None:
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
        "evaluate_trading_performance",
        "EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION",
        "TradingEvaluationEvidence",
        "TradingEvaluationEvidenceStore",
    )
