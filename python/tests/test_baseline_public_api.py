def test_baseline_public_api_is_exact():
    from shreks_brain import baselines

    assert set(baselines.__all__) == {
        "BASELINE_SUITE_SCHEMA_VERSION",
        "BaselineKind",
        "ThresholdDeltaBaselineSpec",
        "BaselineSuitePolicy",
        "BaselineReplayResult",
        "BaselineSuite",
        "build_baseline_suite",
    }
