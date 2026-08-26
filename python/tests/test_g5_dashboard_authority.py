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


def test_dashboard_source_imports_no_execution_or_mutation_authority() -> None:
    forbidden_modules = (
        "shreks_brain.execution",
        "shreks_brain.live",
        "shreks_brain.registry",
        "shreks_brain.promotion",
        "shreks_brain.risk",
        "wallet_secret",
        "wallet_secrets",
        "transaction_builder",
        "transaction_submission",
        "signer",
    )
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
            assert not any(forbidden in lowered for forbidden in forbidden_modules), (
                path.name,
                module,
            )


def test_dashboard_has_no_filesystem_write_calls() -> None:
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


def test_http_router_is_get_only_before_any_application_route() -> None:
    source = (_DASHBOARD_ROOT / "http.py").read_text(encoding="utf-8")
    guard = 'if method != "GET":'
    first_route = 'if path == "/":'
    assert guard in source
    assert first_route in source
    assert source.index(guard) < source.index(first_route)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert f'if method == "{method}"' not in source
        assert f'if method in ("{method}"' not in source
