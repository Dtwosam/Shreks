from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    derive_fast_deterministic_entry_authority_offline,
)
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
)


T0 = 80_000_000


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=0,
        sell_count=0,
        unique_buy_actors=0,
        unique_sell_actors=0,
        buy_arrival_rate_per_second=0.0,
        sell_arrival_rate_per_second=0.0,
        count_imbalance=0.0,
        buy_base_quantity=0.0,
        sell_base_quantity=0.0,
        buy_quote_quantity=0.0,
        sell_quote_quantity=0.0,
        net_quote_quantity=0.0,
        quote_flow_imbalance=0.0,
        quote_flow_velocity_per_second=0.0,
        quote_flow_acceleration_per_second2=0.0,
        local_high_price_quote=None,
        local_high_sequence=None,
        local_high_observed_at_unix_ms=None,
        local_low_price_quote=None,
        local_low_sequence=None,
        local_low_observed_at_unix_ms=None,
        post_high_low_price_quote=None,
        post_high_low_sequence=None,
        post_high_low_observed_at_unix_ms=None,
        last_price_quote=10.0,
        drawdown_from_local_high=0.0,
        recovery_from_local_low=0.0,
    )


def _record() -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature="authority-sig",
        decision_ordinal=0,
        decision_sequence=1,
        mint="mint-authority",
        quote_mint="quote-authority",
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=T0,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 - 1,
        decision_occurred_at_unix_ms=T0 - 2,
        decision_slot=501,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=T0,
        snapshot_last_sequence=1,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=30,
        expected_latency_bps=10,
        network_fee_quote=0.01,
        priority_fee_quote=0.02,
        expected_failure_cost_quote=0.03,
    )


def _execution() -> FastOfflineEntryExecution:
    return FastOfflineEntryExecution(
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=_leg(),
            exit=FastOfflineExecutionLegCost(
                effective_fee_bps=50,
                expected_impact_bps=20,
                expected_slippage_bps=20,
                expected_latency_bps=10,
                network_fee_quote=0.01,
                priority_fee_quote=0.0,
                expected_failure_cost_quote=0.0,
            ),
        ),
        trade=FastOfflineExecutionTrade(
            base_quantity=10.0,
            executable_entry_price_quote=10.0,
            forecast_exit_price_quote=12.0,
            exit_capacity_base=10.0,
            required_edge_bps=200,
            risk_margin_bps=100,
        ),
    )


def _fake_binary(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        "from pathlib import Path\n"
        "request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "material = {\n"
        " 'schema_name': 'shreks.fast_deterministic_entry_authority_result',\n"
        " 'schema_version': 1,\n"
        " 'mint': request['mint'],\n"
        " 'quote_mint': request['quote_mint'],\n"
        " 'intended_base_quantity': 10.0,\n"
        " 'decision_executable_entry_price_quote': 10.0,\n"
        " 'maximum_acceptable_entry_price_quote': 11.401592194597294,\n"
        " 'expected_entry_variable_cost_bps': 110,\n"
        " 'expected_entry_fixed_cost_quote': 0.06,\n"
        "}\n"
        "canonical = json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)\n"
        "material['result_fingerprint_sha256'] = hashlib.sha256(canonical.encode()).hexdigest()\n"
        "print(json.dumps(material, separators=(',', ':'), ensure_ascii=False, allow_nan=False), end='')\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)


def test_offline_entry_authority_is_authenticated_and_exact(tmp_path: Path) -> None:
    binary = tmp_path / "authority"
    _fake_binary(binary)

    authority = derive_fast_deterministic_entry_authority_offline(
        binary_path=binary,
        record=_record(),
        execution=_execution(),
    )

    assert type(authority) is FastCampaignPaperEntryAuthority
    assert authority.mint == "mint-authority"
    assert authority.quote_mint == "quote-authority"
    assert authority.intended_base_quantity == 10.0
    assert authority.decision_executable_entry_price_quote == 10.0
    assert authority.maximum_acceptable_entry_price_quote == pytest.approx(
        11.401592194597294
    )
    assert authority.expected_entry_variable_cost_bps == 110
    assert authority.expected_entry_fixed_cost_quote == pytest.approx(0.06)



def test_offline_entry_authority_returns_none_when_fl3_boundary_is_below_decision(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "authority-below"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, sys\n"
        "from pathlib import Path\n"
        "request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "material = {\n"
        " 'schema_name': 'shreks.fast_deterministic_entry_authority_result',\n"
        " 'schema_version': 1,\n"
        " 'mint': request['mint'],\n"
        " 'quote_mint': request['quote_mint'],\n"
        " 'intended_base_quantity': 10.0,\n"
        " 'decision_executable_entry_price_quote': 10.0,\n"
        " 'maximum_acceptable_entry_price_quote': 9.5,\n"
        " 'expected_entry_variable_cost_bps': 110,\n"
        " 'expected_entry_fixed_cost_quote': 0.06,\n"
        "}\n"
        "canonical = json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)\n"
        "material['result_fingerprint_sha256'] = hashlib.sha256(canonical.encode()).hexdigest()\n"
        "print(json.dumps(material, separators=(',', ':'), ensure_ascii=False, allow_nan=False), end='')\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)

    assert derive_fast_deterministic_entry_authority_offline(
        binary_path=binary,
        record=_record(),
        execution=_execution(),
    ) is None


def test_offline_entry_authority_rejects_decision_price_drift_before_launch(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "marker"
    marker = tmp_path / "launched"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        f"from pathlib import Path; Path({str(marker)!r}).write_text('yes')\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)
    record = _record()
    execution = _execution()
    bad = FastOfflineEntryExecution(
        cost_model=execution.cost_model,
        trade=FastOfflineExecutionTrade(
            base_quantity=execution.trade.base_quantity,
            executable_entry_price_quote=9.9,
            forecast_exit_price_quote=execution.trade.forecast_exit_price_quote,
            exit_capacity_base=execution.trade.exit_capacity_base,
            required_edge_bps=execution.trade.required_edge_bps,
            risk_margin_bps=execution.trade.risk_margin_bps,
        ),
    )

    with pytest.raises(ValueError, match="decision|price|provenance"):
        derive_fast_deterministic_entry_authority_offline(
            binary_path=binary,
            record=record,
            execution=bad,
        )
    assert not marker.exists()


def test_authority_adapter_source_has_no_network_db_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_offline"
        / "entry_authority.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "sqlite3",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
