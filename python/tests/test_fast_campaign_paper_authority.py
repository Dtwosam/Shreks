from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "python" / "src" / "shreks_brain" / "fast_campaign_paper"


def test_campaign_paper_executor_has_no_external_or_live_authority() -> None:
    assert PACKAGE.is_dir(), "campaign PAPER package must exist"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.glob("*.py"))
    )
    forbidden = (
        "requests",
        "httpx",
        "urllib",
        "socket",
        "sqlite3",
        "subprocess",
        "shreks_brain.providers",
        "submit_transaction",
        "sign_transaction",
        "promote_champion",
        "evaluate_promotion",
        "RegistryStatus",
        "RuntimeMode.LIVE",
        "future_path",
        "counterfactual_action",
    )
    for token in forbidden:
        assert token not in source, f"forbidden campaign PAPER authority token: {token}"


def test_campaign_paper_executor_reuses_sealed_economics_instead_of_reimplementing_metrics() -> None:
    assert PACKAGE.is_dir()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.glob("*.py"))
    )
    required = (
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "extract_fast_paper_evaluation_evidence",
        "build_evaluated_trades",
        "evaluate_trading_performance",
        "build_fast_policy_run_evidence",
    )
    for token in required:
        assert token in source, f"missing sealed campaign PAPER dependency: {token}"

    forbidden_metric_implementation = (
        "profit_factor =",
        "net_expectancy_pct =",
        "maximum_drawdown_pct =",
        "realized_pnl_usd =",
        "explicit_cost_usd =",
    )
    for token in forbidden_metric_implementation:
        assert token not in source, f"custom economics calculation forbidden: {token}"
