from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_FORECAST = _ROOT / "crates" / "shreks-core" / "src" / "fast_lane" / "forecast.rs"
_CARGO = _ROOT / "crates" / "shreks-core" / "Cargo.toml"


def test_fl86_forecast_module_has_no_execution_or_external_io_authority() -> None:
    source = _FORECAST.read_text(encoding="utf-8")
    forbidden = (
        "reqwest",
        "tokio",
        "rusqlite",
        "rand::",
        "std::time",
        "std::net",
        "shreks_providers",
        "FastLaneAction",
        "TradeIntent",
        "RuntimeMode",
        "RegistryStatus",
        "submit_transaction",
        "sign_transaction",
        "promote_champion",
    )
    for token in forbidden:
        assert token not in source


def test_fl86_core_adds_only_sealed_format_and_hash_dependencies() -> None:
    cargo = _CARGO.read_text(encoding="utf-8")
    dependencies = cargo.split("[dependencies]", maxsplit=1)[1].strip().splitlines()
    names = {line.split("=", maxsplit=1)[0].strip() for line in dependencies if "=" in line}
    assert names == {"serde", "serde_json", "sha2"}
