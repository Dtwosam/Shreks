from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_POLICY = _ROOT / "crates" / "shreks-core" / "src" / "fast_lane" / "action_policy.rs"
_CARGO = _ROOT / "crates" / "shreks-core" / "Cargo.toml"


def test_fl9_action_policy_is_pure_point_in_time_decision_math() -> None:
    source = _POLICY.read_text(encoding="utf-8").lower()
    forbidden = {
        "reqwest",
        "tokio",
        "tungstenite",
        "providerid",
        "shreks_providers",
        "rusqlite",
        "sqlite3",
        "shreks_storage",
        "std::fs",
        "std::time",
        "systemtime",
        "instant::now",
        "std::env",
        "rand::",
        "futurepathlabel",
        "counterfactual",
        "fast_paper",
        "paperexecutor",
        "tradeintent",
        "sign_transaction",
        "submit_transaction",
        "championregistry",
        "promote",
        "runtimemode",
        "enable_live",
    }
    present = sorted(token for token in forbidden if token in source)
    assert present == []


def test_fl9_adds_no_new_shreks_core_dependency() -> None:
    cargo = _CARGO.read_text(encoding="utf-8")
    dependency_lines = []
    in_dependencies = False
    for raw_line in cargo.splitlines():
        line = raw_line.strip()
        if line == "[dependencies]":
            in_dependencies = True
            continue
        if in_dependencies and line.startswith("["):
            break
        if in_dependencies and line and not line.startswith("#"):
            dependency_lines.append(line.split("=", 1)[0].strip())

    assert dependency_lines == ["serde", "serde_json", "sha2"]
