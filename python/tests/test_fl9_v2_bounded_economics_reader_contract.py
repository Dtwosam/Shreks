from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import shreks_brain.fast_first_champion_v2.host_request as request_module
import shreks_brain.research.counterfactual_parquet as counterfactual_module
import shreks_brain.research.fast_training_economics as economics_module
import shreks_brain.research.fast_training_targets as targets_module


def _bounded_host_module():
    import shreks_brain.fast_first_champion_v2.bounded_host_run as host_module

    return host_module


def _bounded_bundle_module():
    import shreks_brain.fast_first_champion_v2.bounded_bundle as bundle_module

    return bundle_module


def test_v2_uses_cohort_bounded_input_module() -> None:
    inputs_spec = importlib.util.find_spec(
        "shreks_brain.fast_first_champion_v2.bounded_inputs"
    )
    bundle_spec = importlib.util.find_spec(
        "shreks_brain.fast_first_champion_v2.bounded_bundle"
    )
    host_spec = importlib.util.find_spec(
        "shreks_brain.fast_first_champion_v2.bounded_host_run"
    )
    assert inputs_spec is not None
    assert bundle_spec is not None
    assert host_spec is not None

    host_source = inspect.getsource(_bounded_host_module())
    assert "from .bounded_bundle import" in host_source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fl9-v2-first-champion = '
        '"shreks_brain.fast_first_champion_v2.bounded_host_run:main"'
        in pyproject
    )


def test_v2_generic_economics_paths_remain_stream_authenticated() -> None:
    scanner_source = inspect.getsource(
        economics_module._scan_fast_training_economics_overlay
    )
    assert ".read_bytes(" not in scanner_source

    request_source = inspect.getsource(
        request_module.write_fast_first_champion_v2_host_request_from_sources
    )
    assert "validate_fast_training_economics_overlay" in request_source
    assert "read_fast_training_economics_overlay(" not in request_source

    host_source = inspect.getsource(
        _bounded_host_module().run_fast_first_champion_v2_host_request
    )
    assert "validate_fast_training_economics_overlay" in host_source
    assert "read_fast_training_economics_overlay(" not in host_source


def test_v2_future_path_does_not_materialize_full_label_population() -> None:
    host_source = inspect.getsource(_bounded_host_module())
    assert "bounded_bundle" in host_source

    bounded_source = inspect.getsource(
        targets_module.load_future_path_training_labels_for_identities_from_sqlite
    )
    assert ".fetchall(" not in bounded_source


def test_future_path_fingerprint_is_incremental() -> None:
    source = inspect.getsource(
        targets_module.future_path_logical_fingerprint_sha256
    )
    assert "payload = [" not in source
    assert "json.dumps(payload" not in source
    assert 'digest.update(b"[")' in source
    assert 'digest.update(b"]")' in source


def test_counterfactual_dataset_fingerprint_is_incremental() -> None:
    source = inspect.getsource(
        counterfactual_module._logical_dataset_fingerprint_sha256
    )
    assert "json.dumps(rows" not in source
    assert 'digest.update(b"[")' in source
    assert 'digest.update(b"]")' in source


def test_v2_host_never_materializes_full_proof_feature_dataset() -> None:
    host_module = _bounded_host_module()
    module_source = inspect.getsource(host_module)
    run_source = inspect.getsource(host_module.run_fast_first_champion_v2_host_request)
    assert "read_fast_proof_workspace(" not in module_source
    assert "read_fast_proof_workspace_manifest_bounded" in module_source
    assert "proof_manifest = read_fast_proof_workspace_manifest_bounded(" in run_source


def test_v2_host_binds_proof_to_full_feature_source_bytes() -> None:
    source = inspect.getsource(
        _bounded_host_module().run_fast_first_champion_v2_host_request
    )
    assert "bundle.features.source_sha256" in source
    assert "proof_manifest.feature_jsonl_sha256" in source
    assert not (
        "bundle.features.logical_fingerprint_sha256"
        "\n            != proof_manifest.feature_logical_fingerprint_sha256"
        in source
    )


def test_v2_provenance_does_not_materialize_full_cohort_batch() -> None:
    source = inspect.getsource(
        _bounded_bundle_module().build_fast_first_champion_v2_bundle
    )
    assert "load_entry_counterfactual_provenance_batch_from_sqlite" not in source
    assert "iter_entry_counterfactual_provenance_for_labels" in source
    assert "provenance_by_key" not in source
    assert "del selected_labels" in source
    assert "del overlay" in source
