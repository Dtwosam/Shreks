from __future__ import annotations

import builtins
import os
from pathlib import Path
import subprocess

import pytest

from shreks_brain.research.counterfactual_parquet import (
    build_counterfactual_dataset,
    read_counterfactual_parquet,
    write_counterfactual_parquet,
)
from shreks_brain.research.counterfactual_source import (
    load_entry_counterfactual_from_sqlite,
)
from shreks_brain.research.counterfactuals import (
    CounterfactualAction,
    EntryCounterfactualContext,
    ExecutionStatus,
    label_entry_counterfactuals,
)
from shreks_brain.research.fast_training_bundle import (
    build_fast_training_bundle_from_components,
    build_fast_training_bundle_from_runtime_sources,
    read_fast_training_bundle,
    write_fast_training_bundle,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
)
from shreks_brain.research.fast_training_features import (
    read_fast_training_feature_jsonl,
)
from shreks_brain.research.fast_training_targets import (
    load_future_path_training_labels_from_sqlite,
)


WSOL = "So11111111111111111111111111111111111111112"


def _counterfactual(decision_id: str, observed_at_unix_ms: int, horizon_ms: int = 250):
    return label_entry_counterfactuals(
        EntryCounterfactualContext(
            decision_id=decision_id,
            mint="mint-fl8-training",
            quote_mint=WSOL,
            decision_observed_at_unix_ms=observed_at_unix_ms,
            base_quantity=2.0,
            horizon_ms=horizon_ms,
            horizon_complete=(horizon_ms == 250),
            buy_now=None,
            exit_at_horizon=None,
        )
    )


def _write_rust_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = tmp_path / "rust-fixture"
    env = os.environ.copy()
    env["SHREKS_FL8_INTEGRATION_DIR"] = str(fixture_root)
    subprocess.run(
        [
            "cargo",
            "test",
            "-p",
            "shreks-storage",
            "--test",
            "fl8_training_fixture",
            "write_fl8_python_integration_fixture",
            "--",
            "--ignored",
            "--exact",
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )
    database = fixture_root / "shreks.db"
    features = fixture_root / "features.jsonl"
    assert database.is_file()
    assert features.is_file()
    return database, features


def _write_mixed_training_economics_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = tmp_path / "mixed-training-economics-fixture"
    env = os.environ.copy()
    env["SHREKS_TRAINING_ECONOMICS_INTEGRATION_DIR"] = str(fixture_root)
    subprocess.run(
        [
            "cargo",
            "test",
            "-p",
            "shreks-storage",
            "--test",
            "fl3_training_economics_overlay",
            "write_mixed_training_economics_python_integration_fixture",
            "--",
            "--ignored",
            "--exact",
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )
    database = fixture_root / "shreks.db"
    features = fixture_root / "features.jsonl"
    overlay = fixture_root / "training-economics"
    assert database.is_file()
    assert features.is_file()
    assert (overlay / "rows.jsonl").is_file()
    assert (overlay / "manifest.json").is_file()
    return database, features, overlay


def _training_cost_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="runtime-training-cost-v1",
        additional_entry_slippage_bps=10,
        additional_exit_slippage_bps=20,
        entry_latency_bps=5,
        exit_latency_bps=5,
        entry_network_fee_quote=0.0,
        exit_network_fee_quote=0.0,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def _all_counterfactuals(database: Path):
    values = []
    labels = load_future_path_training_labels_from_sqlite(
        database,
        future_path_label_version=1,
    )
    for label in labels.labels:
        loaded = load_entry_counterfactual_from_sqlite(
            database,
            decision_signature=label.decision_signature,
            decision_ordinal=label.decision_ordinal,
            horizon_ms=label.horizon_ms,
            label_version=label.label_version,
            base_quantity=2.0,
        )
        values.append(label_entry_counterfactuals(loaded.context))
    return tuple(values)


def test_in_memory_counterfactual_dataset_matches_parquet_logical_evidence(
    tmp_path: Path,
) -> None:
    outcome_sets = (
        _counterfactual("decision-a:0:h250:v1", 1_100),
        _counterfactual("decision-b:0:h250:v1", 1_600),
    )

    rows, manifest = build_counterfactual_dataset(outcome_sets)

    parquet = tmp_path / "counterfactual.parquet"
    written = write_counterfactual_parquet(outcome_sets, parquet)
    loaded_rows, loaded = read_counterfactual_parquet(parquet)

    assert rows == loaded_rows
    assert manifest == written == loaded


def test_in_memory_training_bundle_matches_existing_parquet_bundle(
    tmp_path: Path,
) -> None:
    database, features_path = _write_rust_fixture(tmp_path)
    features = read_fast_training_feature_jsonl(features_path)
    future_path = load_future_path_training_labels_from_sqlite(
        database,
        future_path_label_version=1,
    )
    outcome_sets = _all_counterfactuals(database)

    in_memory = build_fast_training_bundle_from_components(
        features=features,
        future_path_labels=future_path,
        counterfactual_outcome_sets=outcome_sets,
    )

    counterfactual = tmp_path / "counterfactual.parquet"
    write_counterfactual_parquet(outcome_sets, counterfactual)
    destination = tmp_path / "bundle"
    written = write_fast_training_bundle(
        feature_jsonl_path=features_path,
        sqlite_path=database,
        counterfactual_parquet_path=counterfactual,
        destination=destination,
        future_path_label_version=1,
    )
    persisted = read_fast_training_bundle(destination)

    assert in_memory.manifest == written == persisted.manifest
    assert in_memory.features == persisted.features
    assert in_memory.future_path_labels == persisted.future_path_labels
    assert in_memory.counterfactual_rows == persisted.counterfactual_rows
    assert in_memory.counterfactual_manifest == persisted.counterfactual_manifest


def test_runtime_sources_build_exact_bundle_without_pyarrow(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database, features_path, overlay_path = _write_mixed_training_economics_fixture(
        tmp_path
    )
    imported_pyarrow = False
    original_import = builtins.__import__

    def _guard(name, *args, **kwargs):
        nonlocal imported_pyarrow
        if name == "pyarrow" or name.startswith("pyarrow."):
            imported_pyarrow = True
            raise AssertionError("runtime bundle assembly must not import PyArrow")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guard)

    bundle = build_fast_training_bundle_from_runtime_sources(
        feature_jsonl_path=features_path,
        sqlite_path=database,
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        training_economics_overlay_path=overlay_path,
        training_execution_cost_policy=_training_cost_policy(),
    )

    assert not imported_pyarrow
    assert bundle.manifest.decision_count == 2
    assert bundle.manifest.future_path_label_row_count == 2
    assert bundle.manifest.counterfactual_row_count == 4

    by_decision = {}
    for row in bundle.counterfactual_rows:
        by_decision.setdefault(row["decision_id"], []).append(row)

    assert set(by_decision) == {
        "mixed-pump-decision:0:h500:v1",
        "mixed-swap-decision:2147483650:h500:v1",
    }

    pump_actions = {
        row["action"]: row["execution_status"]
        for row in by_decision["mixed-pump-decision:0:h500:v1"]
    }
    assert (
        pump_actions[CounterfactualAction.BUY_NOW.value]
        == ExecutionStatus.UNKNOWN.value
    )
    assert (
        pump_actions[CounterfactualAction.SKIP.value]
        == ExecutionStatus.EXECUTABLE.value
    )

    swap_actions = {
        row["action"]: row["execution_status"]
        for row in by_decision["mixed-swap-decision:2147483650:h500:v1"]
    }
    assert (
        swap_actions[CounterfactualAction.BUY_NOW.value]
        == ExecutionStatus.EXECUTABLE.value
    )
    assert (
        swap_actions[CounterfactualAction.SKIP.value]
        == ExecutionStatus.EXECUTABLE.value
    )


def test_component_builder_rejects_tampered_feature_or_future_path_fingerprint(
    tmp_path: Path,
) -> None:
    database, features_path = _write_rust_fixture(tmp_path)
    features = read_fast_training_feature_jsonl(features_path)
    future_path = load_future_path_training_labels_from_sqlite(
        database,
        future_path_label_version=1,
    )
    outcome_sets = _all_counterfactuals(database)

    from dataclasses import replace

    with pytest.raises(ValueError, match="feature.*fingerprint"):
        build_fast_training_bundle_from_components(
            features=replace(features, logical_fingerprint_sha256="0" * 64),
            future_path_labels=future_path,
            counterfactual_outcome_sets=outcome_sets,
        )

    with pytest.raises(ValueError, match="future.*fingerprint"):
        build_fast_training_bundle_from_components(
            features=features,
            future_path_labels=replace(
                future_path,
                logical_fingerprint_sha256="0" * 64,
            ),
            counterfactual_outcome_sets=outcome_sets,
        )


def test_runtime_bundle_source_has_no_provider_execution_promotion_or_live_authority() -> None:
    research_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "research"
    )
    sources = (
        (research_root / "fast_training_bundle.py").read_text(encoding="utf-8"),
        (research_root / "fast_training_economics.py").read_text(encoding="utf-8"),
    )

    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert all(forbidden not in source for source in sources)
