from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.fast_champion as fast_champion


def test_public_api_is_exact_and_has_no_auto_promotion_surface() -> None:
    assert set(fast_champion.__all__) == {
        "FAST_FORECAST_CHAMPION_SCHEMA_NAME",
        "FAST_FORECAST_CHAMPION_SCHEMA_VERSION",
        "FastForecastChampionSelection",
        "FastForecastChampionMember",
        "FastForecastChampionArtifact",
        "build_fast_forecast_champion",
        "write_fast_forecast_champion",
        "read_fast_forecast_champion",
    }
    forbidden = {"rank", "compare", "promote", "approve", "live", "trade"}
    assert not any(any(token in name.lower() for token in forbidden) for name in fast_champion.__all__)


def test_import_does_not_eagerly_load_heavy_training_or_storage_dependencies() -> None:
    script = """
import sys
import shreks_brain.fast_champion
for name in ('sklearn', 'numpy', 'pyarrow'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_production_package_has_no_execution_or_registry_mutation_authority() -> None:
    modules = (
        fast_champion,
        __import__("shreks_brain.fast_champion.models", fromlist=["*"]),
        __import__("shreks_brain.fast_champion.builder", fromlist=["*"]),
        __import__("shreks_brain.fast_champion.codec", fromlist=["*"]),
    )
    source = "\n".join(inspect.getsource(module).lower() for module in modules)
    forbidden = (
        "provider_client",
        "sqlite3",
        "tradeintent",
        "paper_executor",
        "sign_transaction",
        "submit_transaction",
        "registrystore",
        "registrystatusevent",
        "registry_status",
        "live_mode",
    )
    for token in forbidden:
        assert token not in source
