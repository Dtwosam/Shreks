from __future__ import annotations

import json
from pathlib import Path

from shreks_brain.research.fast_training_features import (
    read_fast_training_feature_jsonl,
    read_fast_training_feature_parquet,
    write_fast_training_feature_parquet,
)


WINDOWS = (100, 250, 500, 1_000, 2_000, 5_000, 10_000)


def _window(window_ms: int) -> dict[str, object]:
    return {
        "window_ms": window_ms,
        "buy_count": 1,
        "sell_count": 0,
        "unique_buy_actors": 1,
        "unique_sell_actors": 0,
        "buy_arrival_rate_per_second": 1.0,
        "sell_arrival_rate_per_second": 0.0,
        "count_imbalance": 1.0,
        "buy_base_quantity": 2.0,
        "sell_base_quantity": 0.0,
        "buy_quote_quantity": 0.1,
        "sell_quote_quantity": 0.0,
        "net_quote_quantity": 0.1,
        "quote_flow_imbalance": 1.0,
        "quote_flow_velocity_per_second": 0.4,
        "quote_flow_acceleration_per_second2": 0.0,
        "local_high_price_quote": 0.05,
        "local_high_sequence": 2,
        "local_high_observed_at_unix_ms": 1_100,
        "local_low_price_quote": 0.05,
        "local_low_sequence": 2,
        "local_low_observed_at_unix_ms": 1_100,
        "post_high_low_price_quote": None,
        "post_high_low_sequence": None,
        "post_high_low_observed_at_unix_ms": None,
        "last_price_quote": 0.05,
        "drawdown_from_local_high": 0.0,
        "recovery_from_local_low": 0.0,
    }


def test_pumpswap_virtual_quote_reserve_survives_feature_parquet_round_trip(
    tmp_path: Path,
) -> None:
    row = {
        "schema_name": "shreks.fast_lane_training_features",
        "schema_version": 1,
        "decision_signature": "decision-pumpswap",
        "decision_ordinal": 0,
        "decision_sequence": 2,
        "mint": "mint-fl8-pumpswap",
        "quote_mint": "So11111111111111111111111111111111111111112",
        "venue": "pump_swap",
        "decision_observed_at_unix_ms": 1_100,
        "decision_provider": "helius",
        "decision_source_observed_at_unix_ms": 1_090,
        "decision_occurred_at_unix_ms": 1_080,
        "decision_slot": 77,
        "decision_event_kind": "buy",
        "decision_actor": "wallet-decision",
        "decision_executable_entry_price_quote": 0.05,
        "decision_entry_total_quote": 0.1,
        "snapshot_as_of_unix_ms": 1_100,
        "snapshot_last_sequence": 2,
        "snapshot_last_price_quote": 0.05,
        "last_reserve_context": {
            "kind": "pump_swap_pool",
            "pool_base_reserve_raw": 20_000_000_000,
            "pool_quote_reserve_raw": 10_000_000_000,
            "virtual_quote_reserve_raw": 3_000_000_000,
            "base_decimals": 6,
            "quote_decimals": 9,
        },
        "last_lifecycle_event": None,
        "windows": [_window(value) for value in WINDOWS],
    }
    jsonl = tmp_path / "features.jsonl"
    jsonl.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")

    original = read_fast_training_feature_jsonl(jsonl)
    parquet = tmp_path / "features.parquet"
    write_fast_training_feature_parquet(original, parquet)
    loaded = read_fast_training_feature_parquet(parquet)

    reserve = loaded.records[0].last_reserve_context
    assert reserve is not None
    assert reserve.kind == "pump_swap_pool"
    assert reserve.virtual_quote_reserve_raw == 3_000_000_000
    assert loaded.logical_fingerprint_sha256 == original.logical_fingerprint_sha256
