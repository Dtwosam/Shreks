from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "python" / "src" / "shreks_brain" / "fast_policy_proof"
ADAPTER = ROOT / "python" / "src" / "shreks_brain" / "paper_evaluation" / "fast.py"


def test_fast_policy_proof_has_no_runtime_execution_or_promotion_authority() -> None:
    assert PROOF.is_dir(), "FL9 proof package must exist"
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PROOF.glob("*.py"))
    )
    forbidden = (
        "requests",
        "httpx",
        "urllib",
        "socket",
        "sqlite3",
        "subprocess",
        "datetime.now",
        "time.time",
        "ChampionChallengerRegistry",
        "RegistryStatus",
        "evaluate_promotion",
        "promote_champion",
        "TradeIntent",
        "submit_transaction",
        "sign_transaction",
        "RuntimeMode",
    )
    for token in forbidden:
        assert token not in sources, f"forbidden FL9 proof authority token: {token}"


def test_fast_paper_evaluation_adapter_is_measurement_only() -> None:
    assert ADAPTER.is_file(), "Fast PAPER evaluation adapter must exist"
    source = ADAPTER.read_text(encoding="utf-8")
    forbidden = (
        "requests",
        "httpx",
        "sqlite3",
        "subprocess",
        "execute_paper_trade",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "submit_transaction",
        "sign_transaction",
        "evaluate_promotion",
        "promote_champion",
    )
    for token in forbidden:
        assert token not in source, f"forbidden Fast PAPER adapter token: {token}"


def test_proof_package_does_not_import_future_labels() -> None:
    assert PROOF.is_dir()
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PROOF.glob("*.py"))
    )
    for token in (
        "future_path",
        "counterfactual_action",
        "FastPaperSkipFutureLabel",
    ):
        assert token not in sources
