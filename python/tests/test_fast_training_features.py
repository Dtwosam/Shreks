from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.research.fast_training_features import (
    FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
    read_fast_training_feature_jsonl,
)


WINDOWS = (100, 250, 500, 1_000, 2_000, 5_000, 10_000)


def _window(window_ms: int, *, decision_sequence: int = 2, decision_time: int = 1_100) -> dict[str, object]:
    return {
        "window_ms": window_ms,
        "buy_count": 2,
        "sell_count": 0,
        "unique_buy_actors": 2,
        "unique_sell_actors": 0,
        "buy_arrival_rate_per_second": 2.0,
        "sell_arrival_rate_per_second": 0.0,
        "count_imbalance": 1.0,
        "buy_base_quantity": 4.0,
        "sell_base_quantity": 0.0,
        "buy_quote_quantity": 0.21,
        "sell_quote_quantity": 0.0,
        "net_quote_quantity": 0.21,
        "quote_flow_imbalance": 1.0,
        "quote_flow_velocity_per_second": 0.84,
        "quote_flow_acceleration_per_second2": 1.5,
        "local_high_price_quote": 0.055,
        "local_high_sequence": decision_sequence,
        "local_high_observed_at_unix_ms": decision_time,
        "local_low_price_quote": 0.05,
        "local_low_sequence": 1,
        "local_low_observed_at_unix_ms": 1_000,
        "post_high_low_price_quote": None,
        "post_high_low_sequence": None,
        "post_high_low_observed_at_unix_ms": None,
        "last_price_quote": 0.055,
        "drawdown_from_local_high": 0.0,
        "recovery_from_local_low": 0.1,
    }


def feature_row(
    *,
    signature: str = "decision",
    sequence: int = 2,
    observed_at: int = 1_100,
) -> dict[str, object]:
    return {
        "schema_name": "shreks.fast_lane_training_features",
        "schema_version": 1,
        "decision_signature": signature,
        "decision_ordinal": 0,
        "decision_sequence": sequence,
        "mint": "mint-fl8",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "venue": "pump_fun_bonding_curve",
        "decision_observed_at_unix_ms": observed_at,
        "decision_provider": "helius",
        "decision_source_observed_at_unix_ms": observed_at - 20,
        "decision_occurred_at_unix_ms": 1_000,
        "decision_slot": 77,
        "decision_event_kind": "buy",
        "decision_actor": "wallet-decision",
        "decision_executable_entry_price_quote": 0.055,
        "decision_entry_total_quote": 0.11275,
        "snapshot_as_of_unix_ms": observed_at,
        "snapshot_last_sequence": sequence,
        "snapshot_last_price_quote": 0.055,
        "last_reserve_context": {
            "kind": "pump_curve",
            "virtual_base_reserve_raw": 20_002_000_000,
            "virtual_quote_reserve_raw": 10_110_000_000,
            "real_base_reserve_raw": 11_000_000_000,
            "real_quote_reserve_raw": 5_110_000_000,
            "base_decimals": 6,
            "quote_decimals": 9,
        },
        "last_lifecycle_event": None,
        "windows": [
            _window(value, decision_sequence=sequence, decision_time=observed_at)
            for value in WINDOWS
        ],
    }


def _write(path: Path, rows: list[dict[str, object]], *, pretty: bool = False) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if pretty:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            else:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def test_feature_interchange_constants_and_round_trip_are_stable(tmp_path: Path) -> None:
    assert FAST_TRAINING_FEATURE_SCHEMA_NAME == "shreks.fast_lane_training_features"
    assert FAST_TRAINING_FEATURE_SCHEMA_VERSION == 1

    path = tmp_path / "features.jsonl"
    _write(path, [feature_row()])
    dataset = read_fast_training_feature_jsonl(path)

    assert len(dataset.records) == 1
    record = dataset.records[0]
    assert record.decision_signature == "decision"
    assert record.decision_sequence == 2
    assert tuple(window.window_ms for window in record.windows) == WINDOWS
    assert record.last_reserve_context is not None
    assert record.last_reserve_context.kind == "pump_curve"
    assert record.last_reserve_context.real_base_reserve_raw == 11_000_000_000
    assert len(dataset.logical_fingerprint_sha256) == 64
    assert len(dataset.source_sha256) == 64


def test_logical_fingerprint_ignores_json_object_formatting(tmp_path: Path) -> None:
    compact = tmp_path / "compact.jsonl"
    pretty = tmp_path / "pretty.jsonl"
    row = feature_row()
    _write(compact, [row])
    _write(pretty, [row], pretty=True)

    first = read_fast_training_feature_jsonl(compact)
    second = read_fast_training_feature_jsonl(pretty)
    assert first.logical_fingerprint_sha256 == second.logical_fingerprint_sha256
    assert first.source_sha256 != second.source_sha256


def test_duplicate_decision_identity_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.jsonl"
    row = feature_row()
    _write(path, [row, dict(row)])
    with pytest.raises(ValueError, match="duplicate"):
        read_fast_training_feature_jsonl(path)


def test_future_sequence_timestamp_and_lifecycle_evidence_fail_closed(tmp_path: Path) -> None:
    future_sequence = feature_row()
    windows = list(future_sequence["windows"])
    windows[0] = dict(windows[0], local_high_sequence=3)
    future_sequence["windows"] = windows
    path = tmp_path / "future-sequence.jsonl"
    _write(path, [future_sequence])
    with pytest.raises(ValueError, match="future|sequence"):
        read_fast_training_feature_jsonl(path)

    future_time = feature_row()
    windows = list(future_time["windows"])
    windows[0] = dict(windows[0], local_high_observed_at_unix_ms=1_101)
    future_time["windows"] = windows
    path = tmp_path / "future-time.jsonl"
    _write(path, [future_time])
    with pytest.raises(ValueError, match="future|timestamp"):
        read_fast_training_feature_jsonl(path)

    future_lifecycle = feature_row()
    future_lifecycle["last_lifecycle_event"] = {
        "kind": "pump_graduation",
        "provider": "helius",
        "mint": "mint-fl8",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "from_venue": "pump_fun_bonding_curve",
        "to_venue": "pump_swap",
        "pool_address": "pool",
        "signature": "grad",
        "slot": 88,
        "detected_at_unix_ms": 1_101,
        "occurred_at_unix_ms": 1_050,
    }
    path = tmp_path / "future-lifecycle.jsonl"
    _write(path, [future_lifecycle])
    with pytest.raises(ValueError, match="future|lifecycle"):
        read_fast_training_feature_jsonl(path)


def test_mixed_or_unknown_schema_versions_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "mixed.jsonl"
    first = feature_row(signature="a", sequence=2)
    second = feature_row(signature="b", sequence=3, observed_at=1_200)
    second["schema_version"] = 2
    _write(path, [first, second])
    with pytest.raises(ValueError, match="schema"):
        read_fast_training_feature_jsonl(path)
