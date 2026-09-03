from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PY_CAMPAIGN = ROOT / "python" / "src" / "shreks_brain" / "fast_campaign"
RUST_CAMPAIGN = ROOT / "crates" / "shreks-core" / "src" / "fast_lane" / "campaign.rs"
RUST_CLI = ROOT / "crates" / "shreks-core" / "src" / "bin" / "shreks-fast-campaign-decision.rs"


def test_python_campaign_adapter_has_no_process_storage_execution_or_future_authority() -> None:
    assert PY_CAMPAIGN.is_dir()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PY_CAMPAIGN.glob("*.py"))
    )
    forbidden = (
        "subprocess",
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "shreks_brain.providers",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "submit_transaction",
        "sign_transaction",
        "evaluate_promotion",
        "promote_champion",
        "RegistryStatus",
        "RuntimeMode",
        "future_path",
        "counterfactual_action",
    )
    for token in forbidden:
        assert token not in source, f"forbidden campaign adapter token: {token}"


def test_rust_campaign_core_has_no_io_provider_storage_runtime_or_trade_authority() -> None:
    assert RUST_CAMPAIGN.is_file()
    source = RUST_CAMPAIGN.read_text(encoding="utf-8")
    forbidden = (
        "std::fs",
        "std::net",
        "rusqlite",
        "shreks_storage",
        "shreks_providers",
        "TradeIntent",
        "RuntimeMode",
        "submit_transaction",
        "sign_transaction",
        "promote_champion",
    )
    for token in forbidden:
        assert token not in source, f"forbidden Rust campaign core token: {token}"


def test_rust_campaign_cli_is_file_io_only_not_network_or_trading() -> None:
    assert RUST_CLI.is_file()
    source = RUST_CLI.read_text(encoding="utf-8")
    forbidden = (
        "std::net",
        "rusqlite",
        "shreks_storage",
        "shreks_providers",
        "TradeIntent",
        "RuntimeMode",
        "submit_transaction",
        "sign_transaction",
        "promote_champion",
    )
    for token in forbidden:
        assert token not in source, f"forbidden Rust campaign CLI token: {token}"
