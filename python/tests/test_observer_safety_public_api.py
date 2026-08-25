from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys

import shreks_brain.observer_safety as observer_safety


_EXPECTED_PUBLIC_API = (
    "ObserverSafetyProbeIdentity",
    "ObserverMintSafetyEvidence",
    "ObserverHolderSafetyEvidence",
    "ObserverExitQuoteSafetyEvidence",
    "ObserverSafetyReadError",
    "ObserverSafetyEvidenceStore",
    "ObserverSafetyAssemblyError",
    "build_safety_inputs",
    "assess_observer_safety",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "shreks_brain.paper",
    "shreks_brain.paper_loop",
    "shreks_brain.paper_evaluation",
    "shreks_brain.registry",
    "shreks_brain.promotion",
    "shreks_brain.shadow",
    "shreks_brain.execution",
    "shreks_brain.live",
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
    assert observer_safety.__all__ == _EXPECTED_PUBLIC_API
    for name in _EXPECTED_PUBLIC_API:
        assert getattr(observer_safety, name) is not None


def test_store_public_methods_are_read_only_evidence_queries():
    public_methods = {
        name
        for name, value in inspect.getmembers(
            observer_safety.ObserverSafetyEvidenceStore, predicate=callable
        )
        if not name.startswith("_")
    }

    assert public_methods == {
        "latest_mint_state",
        "latest_holder_distribution",
        "latest_exit_quote",
    }
    assert not any(
        word in method_name.lower()
        for method_name in public_methods
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )


def test_public_functions_have_no_execution_or_promotion_authority_names():
    public_callables = {
        name
        for name in observer_safety.__all__
        if callable(getattr(observer_safety, name))
    }
    assert not any(
        word in name.lower()
        for name in public_callables
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )


def test_source_import_firewall_excludes_execution_promotion_and_live_packages():
    package_dir = Path(observer_safety.__file__).parent
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


def test_fresh_process_import_does_not_pull_execution_promotion_or_live_modules():
    code = """
import json
import sys
import shreks_brain.observer_safety
forbidden = (
    'shreks_brain.paper',
    'shreks_brain.paper_loop',
    'shreks_brain.paper_evaluation',
    'shreks_brain.registry',
    'shreks_brain.promotion',
    'shreks_brain.shadow',
    'shreks_brain.execution',
    'shreks_brain.live',
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
