from __future__ import annotations

import ast
from pathlib import Path

import shreks_brain.dashboard as dashboard_package


_DASHBOARD_ROOT = Path(dashboard_package.__file__).resolve().parent


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(_DASHBOARD_ROOT.glob("*.py")))


def test_dashboard_exports_no_mutation_or_control_authority() -> None:
    exports = tuple(getattr(dashboard_package, "__all__", ()))
    assert exports
    forbidden_fragments = (
        "create_",
        "update_",
        "delete_",
        "write_",
        "mutate",
        "promote",
        "execute",
        "submit",
        "sign",
        "live",
        "halt",
        "kill",
        "control",
    )
    for exported in exports:
        lowered = exported.lower()
        assert not any(fragment in lowered for fragment in forbidden_fragments), exported


def test_dashboard_source_imports_only_risk_control_as_mutation_authority() -> None:
    forbidden_prefixes = (
        "shreks_brain.execution",
        "shreks_brain.live",
        "shreks_brain.registry",
        "shreks_brain.promotion",
        "shreks_brain.risk",
    )
    forbidden_fragments = (
        "wallet_secret",
        "wallet_secrets",
        "transaction_builder",
        "transaction_submission",
        "signer",
    )
    observed_risk_control = False
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for module in imported:
            lowered = module.lower()
            if lowered == "shreks_brain.risk_control" or lowered.startswith(
                "shreks_brain.risk_control."
            ):
                observed_risk_control = True
                continue
            assert not any(
                lowered == prefix or lowered.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            ), (path.name, module)
            assert not any(fragment in lowered for fragment in forbidden_fragments), (
                path.name,
                module,
            )
    assert observed_risk_control


def test_dashboard_has_no_direct_filesystem_write_calls() -> None:
    forbidden_markers = (
        ".write_text(",
        ".write_bytes(",
        ".mkdir(",
        ".touch(",
        ".unlink(",
        ".rename(",
        ".chmod(",
        ".chown(",
        "os.remove(",
        "os.rename(",
        "shutil.move(",
        "shutil.copy",
    )
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, (path.name, marker)


def test_http_router_allows_only_exact_g7_safety_post_routes() -> None:
    source = (_DASHBOARD_ROOT / "http.py").read_text(encoding="utf-8")
    assert '_HALT_PATH = "/api/v1/operator-controls/halt-new-entries"' in source
    assert '_KILL_PATH = "/api/v1/operator-controls/emergency-kill"' in source
    assert 'if method == "POST":' in source
    assert "if path not in (_HALT_PATH, _KILL_PATH):" in source
    assert 'if method != "GET":' in source
    first_get_route = 'if path == "/":'
    assert first_get_route in source
    assert source.index('if method != "GET":') < source.index(first_get_route)
    for method in ("PUT", "PATCH", "DELETE"):
        assert f'if method == "{method}"' not in source
        assert f'if method in ("{method}"' not in source
    for forbidden_route in (
        "reset-kill-switch",
        "clear-entry-halt",
        "/resume",
        "live-enable",
        "/buy",
        "/sell",
    ):
        assert forbidden_route not in source
