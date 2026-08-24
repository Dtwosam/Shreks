from shreks_brain import backtest


def test_backtest_public_api_is_exact() -> None:
    assert backtest.__all__ == (
        "BACKTEST_REPLAY_SCHEMA_VERSION",
        "ReplaySetupKind",
        "ReplayDecisionInput",
        "ReplayOutcomeBundle",
        "ReplayPolicySet",
        "ReplayRun",
        "replay_entry_decisions",
    )
