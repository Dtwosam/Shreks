from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys

import shreks_brain.observer_campaign as observer_campaign


_EXPECTED_PUBLIC_API = (
    "OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION",
    "ObserverPaperQuotePurpose",
    "ObserverPaperQuoteAsset",
    "ObserverPaperQuoteIdentity",
    "ObserverPaperQuoteEvidence",
    "ObserverRegimeReadPolicy",
    "ObserverPaperRiskEnvironment",
    "ObserverCampaignReadError",
    "ObserverCampaignStore",
    "ObserverPaperQuoteError",
    "build_entry_paper_quote",
    "build_exit_paper_quote",
    "ObserverPaperRiskContextError",
    "build_observer_risk_context",
    "OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION",
    "ObserverPaperAssemblyError",
    "ObserverFreshLaunchPolicyBundle",
    "ObserverPaperCycleAudit",
    "assemble_observer_paper_cycle",
    "ObserverPaperCampaignError",
    "ObserverPaperCampaignRunner",
    "OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION",
    "ObserverCampaignCoordinatorError",
    "ObserverPaperCampaignSelectionPolicy",
    "ObserverCampaignCandidate",
    "ObserverPaperCampaignCycleAudit",
    "assemble_observer_paper_campaign_cycle",
    "ObserverPaperCampaignCoordinatorRunner",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "shreks_brain.promotion",
    "shreks_brain.live",
    "shreks_brain.execution",
)

_FORBIDDEN_PUBLIC_AUTHORITY_WORDS = (
    "promote",
    "promotion",
    "live",
    "sign",
    "submit",
    "transaction",
    "registry",
    "execute",
    "credential",
)


def test_public_api_is_exact_and_authority_limited():
    assert observer_campaign.__all__ == _EXPECTED_PUBLIC_API
    for name in _EXPECTED_PUBLIC_API:
        assert getattr(observer_campaign, name) is not None

    assert not any(
        word in name.lower()
        for name in observer_campaign.__all__
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )
    assert "ObserverCampaignCandidateStore" not in observer_campaign.__all__


def test_campaign_store_public_methods_are_read_only_evidence_queries():
    public_methods = {
        name
        for name, value in inspect.getmembers(
            observer_campaign.ObserverCampaignStore, predicate=callable
        )
        if not name.startswith("_")
    }

    assert public_methods == {
        "latest_paper_quote",
        "latest_token_decimals",
        "build_regime_market_window",
    }


def test_campaign_runner_public_methods_are_paper_evidence_only():
    public_methods = {
        name
        for name, value in inspect.getmembers(
            observer_campaign.ObserverPaperCampaignRunner, predicate=callable
        )
        if not name.startswith("_")
    }

    assert public_methods == {"load_state", "run_cycle", "evaluated_trades"}
    assert not any(
        word in method_name.lower()
        for method_name in public_methods
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )


def test_coordinator_runner_public_methods_are_paper_evidence_only():
    public_methods = {
        name
        for name, value in inspect.getmembers(
            observer_campaign.ObserverPaperCampaignCoordinatorRunner,
            predicate=callable,
        )
        if not name.startswith("_")
    }

    assert public_methods == {"load_state", "run_cycle", "evaluated_trades"}
    assert not any(
        word in method_name.lower()
        for method_name in public_methods
        for word in _FORBIDDEN_PUBLIC_AUTHORITY_WORDS
    )


def test_source_import_firewall_excludes_promotion_and_live_execution_authority():
    package_dir = Path(observer_campaign.__file__).parent
    imported_modules: set[str] = set()
    registry_imports: set[str] = set()

    for path in package_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
                if node.module == "shreks_brain.registry":
                    registry_imports.update(alias.name for alias in node.names)

    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imported_modules
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )
    assert registry_imports <= {"RegistryCandidate"}


def test_fresh_process_import_does_not_pull_promotion_or_live_execution_modules():
    code = """
import json
import sys
import shreks_brain.observer_campaign
forbidden = (
    'shreks_brain.promotion',
    'shreks_brain.live',
    'shreks_brain.execution',
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
