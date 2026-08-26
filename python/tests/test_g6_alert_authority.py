from __future__ import annotations

import ast
from pathlib import Path

import shreks_brain.alerts as alerts


_ALERTS_DIRECTORY = Path(alerts.__file__).resolve().parent


def _sources() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_ALERTS_DIRECTORY.glob("*.py"))
    }


def _trees() -> dict[str, ast.AST]:
    return {name: ast.parse(text, filename=name) for name, text in _sources().items()}


def test_alert_package_public_surface_has_no_trading_or_control_authority() -> None:
    lowered = " ".join(sorted(alerts.__all__)).lower()
    for fragment in (
        "trade_intent",
        "execute_trade",
        "submit_transaction",
        "sign_transaction",
        "wallet",
        "promote",
        "registry_mut",
        "risk_mut",
        "live_enable",
        "kill_switch_set",
        "start_service",
        "stop_service",
        "restart_service",
    ):
        assert fragment not in lowered


def test_alert_modules_do_not_import_trading_mutation_subsystems() -> None:
    forbidden_module_fragments = (
        "live_executor",
        "transaction_builder",
        "signer",
        "submission",
        "wallet",
        "registry.mutation",
        "promotion.mutation",
        "risk.mutation",
    )
    for filename, tree in _trees().items():
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                lowered = module.lower()
                for fragment in forbidden_module_fragments:
                    assert fragment not in lowered, f"{filename} imports forbidden {module}"


def test_alert_modules_never_call_a_trading_run_cycle_or_host_listener() -> None:
    for filename, tree in _trees().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ""
            assert name != "run_cycle", f"{filename} gained trading/PAPER cycle authority"
            assert name not in {"HTTPServer", "ThreadingHTTPServer", "TCPServer"}
            assert name != "listen"

    combined = "\n".join(_sources().values()).lower()
    for forbidden in (
        "getupdates",
        "setwebhook",
        "callback_query",
        "callbackquery",
        "commandhandler",
        "reply_markup",
        "socketserver",
    ):
        assert forbidden not in combined


def test_direct_filesystem_write_primitives_exist_only_in_state_module() -> None:
    write_attributes = {
        "write_bytes",
        "write_text",
        "unlink",
        "replace",
        "chmod",
        "mkdir",
        "touch",
        "fsync",
    }
    for filename, tree in _trees().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in write_attributes:
                assert filename == "state.py", (
                    f"direct filesystem write primitive {node.func.attr} escaped state.py into {filename}"
                )
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr in {"open", "replace", "chmod", "fsync"}
            ):
                assert filename == "state.py"


def test_subprocess_is_confined_to_read_only_systemd_source() -> None:
    imported_in: list[str] = []
    for filename, tree in _trees().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names):
                imported_in.append(filename)
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                imported_in.append(filename)
    assert imported_in == ["source.py"]

    source = _sources()["source.py"]
    assert '("/usr/bin/systemctl", "is-active", unit)' in source
    for forbidden in (
        '"start"',
        '"stop"',
        '"restart"',
        '"enable"',
        '"disable"',
        '"reset-failed"',
        '"daemon-reload"',
    ):
        assert forbidden not in source
