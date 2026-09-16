from __future__ import annotations

import importlib.util
import inspect

import shreks_brain.fast_first_champion_v2.host_request as request_module
import shreks_brain.fast_first_champion_v2.host_run as host_module
import shreks_brain.research.fast_training_economics as economics_module
import shreks_brain.research.fast_training_targets as targets_module


def test_v2_uses_cohort_bounded_input_module() -> None:
    inputs_spec = importlib.util.find_spec(
        "shreks_brain.fast_first_champion_v2.bounded_inputs"
    )
    bundle_spec = importlib.util.find_spec(
        "shreks_brain.fast_first_champion_v2.bounded_bundle"
    )
    assert inputs_spec is not None
    assert bundle_spec is not None

    host_source = inspect.getsource(host_module)
    assert "from .bounded_bundle import" in host_source
    assert "from .bundle import" not in host_source


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

    host_source = inspect.getsource(host_module.run_fast_first_champion_v2_host_request)
    assert "validate_fast_training_economics_overlay" in host_source
    assert "read_fast_training_economics_overlay(" not in host_source


def test_v2_future_path_does_not_materialize_full_label_population() -> None:
    host_source = inspect.getsource(host_module)
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


def test_v2_host_binds_proof_to_full_feature_source_bytes() -> None:
    source = inspect.getsource(host_module.run_fast_first_champion_v2_host_request)
    assert "bundle.features.source_sha256" in source
    assert "proof.manifest.feature_jsonl_sha256" in source
    assert not (
        "bundle.features.logical_fingerprint_sha256"
        "\n            != proof.manifest.feature_logical_fingerprint_sha256"
        in source
    )
