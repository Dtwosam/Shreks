from __future__ import annotations

import inspect

import shreks_brain.fast_first_champion_v2.bundle as bundle_module
import shreks_brain.fast_first_champion_v2.host_request as request_module
import shreks_brain.fast_first_champion_v2.host_run as host_module
import shreks_brain.research.fast_training_economics as economics_module
import shreks_brain.research.fast_training_targets as targets_module


def test_v2_economics_paths_do_not_materialize_full_overlay() -> None:
    scanner_source = inspect.getsource(
        economics_module._scan_fast_training_economics_overlay
    )
    assert ".read_bytes(" not in scanner_source

    bundle_source = inspect.getsource(
        bundle_module.build_fast_first_champion_v2_bundle
    )
    assert "read_fast_training_economics_overlay_for_horizon" in bundle_source
    assert "read_fast_training_economics_overlay(" not in bundle_source

    request_source = inspect.getsource(
        request_module.write_fast_first_champion_v2_host_request_from_sources
    )
    assert "validate_fast_training_economics_overlay" in request_source
    assert "read_fast_training_economics_overlay(" not in request_source

    host_source = inspect.getsource(host_module.run_fast_first_champion_v2_host_request)
    assert "validate_fast_training_economics_overlay" in host_source
    assert "read_fast_training_economics_overlay(" not in host_source


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
