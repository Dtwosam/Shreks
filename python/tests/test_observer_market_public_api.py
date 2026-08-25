from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys

import shreks_brain.observer_market as observer_market


_EXPECTED_PUBLIC_API = (
    "OBSERVER_MARKET_SCHEMA_VERSION",
    "ObserverMarketReadPolicy",
    "ObserverCandidateIdentity",
    "ObserverMarketSnapshot",
    "ObservedMarketWindow",
    "ObserverMarketReadError",
    "ObserverMarketStore",
    "build_market_feature_points",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "shreks_brain.paper",
    "shreks_brain.paper_loop",
    "shreks_brain.paper_evaluation",
    "shreks_brain.registry",
    "shreks_brain.promotion",
    "shreks_brain.shadow",
)

_FORBIDDEN_PUBLIC_AUTHORITY_WORDS = (
    "write",
    "save",
    "insert",
    "update",
    "delete",
    "execute",
    "trade",
    "promote",
    "live",
    "sign",
    "submit",
)


def test_public_api_is_exact_and_small():
    assert observer_market.__all__ == _EXPECTED_PUBLIC_API
    for name in _EXPECTED_PUBLIC_API:
        assert getattr(observer_market, name) is not None


def test_store_public_methods_are_read_only_evidence_operations():
    public_methods = {
        name
        for name, value in inspect.getmembers(
            observer_market.ObserverMarketStore, predicate=callable
        )
        if not name.startswith("_")
    }

    assert public_methods == {"load_window", "resolve_candidate"}
    assert not any(
        word in method_name.lower()
        for method_name in public_methods
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )


def test_source_import_firewall_excludes_execution_promotion_and_live_packages():
    package_dir = Path(observer_market.__file__).parent
    imported_modules: set[str] = set()

    for path in package_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imported_modules
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def test_fresh_process_import_does_not_pull_execution_or_promotion_modules():
    code = """
import json
import sys
import shreks_brain.observer_market
forbidden = (
    'shreks_brain.paper',
    'shreks_brain.paper_loop',
    'shreks_brain.paper_evaluation',
    'shreks_brain.registry',
    'shreks_brain.promotion',
    'shreks_brain.shadow',
)
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden)
)
print(json.dumps(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
