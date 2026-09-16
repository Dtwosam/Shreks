from __future__ import annotations

import inspect

import shreks_brain.fast_first_champion_v2.bundle as bundle_module
import shreks_brain.fast_first_champion_v2.host_request as request_module
import shreks_brain.fast_first_champion_v2.host_run as host_module
import shreks_brain.research.fast_training_economics as economics_module
import shreks_brain.research.fast_training_features as features_module
import shreks_brain.research.fast_training_targets as targets_module


def test_v2_economics_paths_do_not_materialize_full_overlay() -> None:
    scanner_source = inspect.getsource(
        economics_module._scan_fast_training_economics_overlay
    )
    assert ".read_bytes(" not in scanner_source

    bundle_source = inspect.getsource(
        bundle_module.build_fast_first_champion_v2_bundle
    )
    assert "read_fast_training_economics_overlay_for_identities" in bundle_source
    assert "read_fast_training_economics_overlay_for_horizon" not in bundle_source
    assert "read_fast_training_economics_overlay(" not in bundle_source

    request_source = inspect.getsource(
        request_module.write_fast_first_champion_v2_host_request_from_sources
    )
    assert "validate_fast_training_economics_overlay" in request_source
    assert "read_fast_training_economics_overlay(" not in request_source

    host_source = inspect.getsource(host_module.run_fast_first_champion_v2_host_request)
    assert "validate_fast_training_economics_overlay" in host_source
    assert "read_fast_training_economics_overlay(" not in host_source


def test_v2_features_retain_only_requested_cohort() -> None:
    reader = getattr(
        features_module,
        "read_fast_training_feature_jsonl_for_identities",
        None,
    )
    assert reader is not None

    bundle_source = inspect.getsource(
        bundle_module.build_fast_first_champion_v2_bundle
    )
    assert "read_fast_training_feature_jsonl_for_identities" in bundle_source
    assert "read_fast_training_feature_jsonl(" not in bundle_source
    assert "_select_exact_features(" not in bundle_source


def test_v2_future_path_does_not_materialize_full_label_population() -> None:
    bundle_source = inspect.getsource(
        bundle_module.build_fast_first_champion_v2_bundle
    )
    assert "load_future_path_training_labels_for_identities_from_sqlite" in bundle_source
    assert "load_future_path_training_labels_from_sqlite(" not in bundle_source

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
