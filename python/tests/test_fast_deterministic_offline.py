from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from shreks_brain.fast_campaign_paper import FastDeterministicPaperPosture
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicLifecycleDecision,
    decode_fast_deterministic_candidate_manifest,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    build_fast_deterministic_row_request,
    decode_fast_deterministic_row_result,
    evaluate_fast_deterministic_row_offline,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    FastTrainingReserveContext,
    FastTrainingWindowSummary,
    DEFAULT_FAST_WINDOWS_MS,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_candidate_manifest_v1.json"
)
T0 = 15_000_000
MARKET = "pump_fun_bonding_curve:mint-life:quote-life"


def _manifest():
    return decode_fast_deterministic_candidate_manifest(
        FIXTURE.read_text(encoding="utf-8")
    )


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=8 if window_ms == 500 else 0,
        sell_count=2 if window_ms == 500 else 0,
        unique_buy_actors=6 if window_ms == 500 else 0,
        unique_sell_actors=2 if window_ms == 500 else 0,
        buy_arrival_rate_per_second=16.0 if window_ms == 500 else 0.0,
        sell_arrival_rate_per_second=4.0 if window_ms == 500 else 0.0,
        count_imbalance=0.6 if window_ms == 500 else 0.0,
        buy_base_quantity=1.0 if window_ms == 500 else 0.0,
        sell_base_quantity=0.2 if window_ms == 500 else 0.0,
        buy_quote_quantity=4.5 if window_ms == 500 else 0.0,
        sell_quote_quantity=0.8 if window_ms == 500 else 0.0,
        net_quote_quantity=3.7 if window_ms == 500 else 0.0,
        quote_flow_imbalance=(3.7 / 5.3) if window_ms == 500 else 0.0,
        quote_flow_velocity_per_second=7.4 if window_ms == 500 else (
            2.0 if window_ms == 2_000 else 0.0
        ),
        quote_flow_acceleration_per_second2=12.0 if window_ms == 500 else 0.0,
        local_high_price_quote=0.0102,
        local_high_sequence=40,
        local_high_observed_at_unix_ms=T0 - 120,
        local_low_price_quote=0.0095,
        local_low_sequence=30,
        local_low_observed_at_unix_ms=T0 - 140,
        post_high_low_price_quote=0.0099,
        post_high_low_sequence=41,
        post_high_low_observed_at_unix_ms=T0 - 110,
        last_price_quote=0.0101,
        drawdown_from_local_high=0.009_803_921_568_627_45,
        recovery_from_local_low=0.063_157_894_736_842_1,
    )


def _record(
    *,
    reserve: FastTrainingReserveContext | None = None,
    venue: str = "pump_fun_bonding_curve",
) -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature="sig-row",
        decision_ordinal=0,
        decision_sequence=42,
        mint="mint-life",
        quote_mint="quote-life",
        venue=venue,
        decision_observed_at_unix_ms=T0,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 - 1,
        decision_occurred_at_unix_ms=T0 - 2,
        decision_slot=142,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=0.01,
        decision_entry_total_quote=1.01,
        snapshot_as_of_unix_ms=T0,
        snapshot_last_sequence=42,
        snapshot_last_price_quote=0.0101,
        last_reserve_context=reserve,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=20,
        expected_latency_bps=10,
        network_fee_quote=0.0001,
        priority_fee_quote=0.0,
        expected_failure_cost_quote=0.0,
    )


def _execution() -> FastOfflineEntryExecution:
    return FastOfflineEntryExecution(
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=_leg(),
            exit=_leg(),
        ),
        trade=FastOfflineExecutionTrade(
            base_quantity=100.0,
            executable_entry_price_quote=0.01,
            forecast_exit_price_quote=0.012,
            exit_capacity_base=125.0,
            required_edge_bps=200,
            risk_margin_bps=100,
        ),
    )


def _flat() -> FastDeterministicPaperPosture:
    return FastDeterministicPaperPosture(
        market_key=MARKET,
        posture="FLAT",
        current_exposure_fraction=None,
        position_id=None,
        opened_at_unix_ms=None,
    )


def _open() -> FastDeterministicPaperPosture:
    return FastDeterministicPaperPosture(
        market_key=MARKET,
        posture="OPEN",
        current_exposure_fraction=0.8,
        position_id="paper-position-1",
        opened_at_unix_ms=T0 - 1_000,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _result_document(
    *,
    action: str = "BUY",
    posture: str = "FLAT",
    current: float | None = None,
    target: float = 0.8,
) -> dict[str, object]:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document: dict[str, object] = {
        "schema_name": "shreks.fast_deterministic_row_result",
        "schema_version": 1,
        "candidate_version": manifest["candidate_version"],
        "candidate_fingerprint_sha256": manifest["candidate_fingerprint_sha256"],
        "lifecycle_policy": manifest["lifecycle_policy"],
        "decision": {
            "source_event_id": "sig-row:0",
            "market_key": MARKET,
            "source_sequence": 42,
            "as_of_unix_ms": T0,
            "posture": posture,
            "component_kind": (
                "IMPULSE_SCALP" if posture == "FLAT" else "LONGER_RUNNER"
            ),
            "component_version": 1,
            "action": action,
            "current_exposure_fraction": current,
            "target_exposure_fraction": target,
        },
        "result_fingerprint_sha256": "",
    }
    material = dict(document)
    material.pop("result_fingerprint_sha256")
    document["result_fingerprint_sha256"] = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    return document


def _rust_wire_json(document: dict[str, object]) -> str:
    policy = document["lifecycle_policy"]
    decision = document["decision"]
    ordered = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "candidate_version": document["candidate_version"],
        "candidate_fingerprint_sha256": document["candidate_fingerprint_sha256"],
        "lifecycle_policy": {
            "version": policy["version"],
            "entry_baseline_kind": policy["entry_baseline_kind"],
            "manager_baseline_kind": policy["manager_baseline_kind"],
            "entry_target_exposure_fraction": policy[
                "entry_target_exposure_fraction"
            ],
            "reduce_remaining_fraction": policy["reduce_remaining_fraction"],
        },
        "decision": {
            "source_event_id": decision["source_event_id"],
            "market_key": decision["market_key"],
            "source_sequence": decision["source_sequence"],
            "as_of_unix_ms": decision["as_of_unix_ms"],
            "posture": decision["posture"],
            "component_kind": decision["component_kind"],
            "component_version": decision["component_version"],
            "action": decision["action"],
            "current_exposure_fraction": decision["current_exposure_fraction"],
            "target_exposure_fraction": decision["target_exposure_fraction"],
        },
        "result_fingerprint_sha256": document["result_fingerprint_sha256"],
    }
    return json.dumps(
        ordered,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _write_fake_binary(path: Path, stdout: str, *, exit_code: int = 0) -> None:
    script = f"""#!/usr/bin/env python3
import sys
from pathlib import Path
request = Path(sys.argv[1])
if not request.exists():
    raise SystemExit(93)
print({stdout!r}, end="")
raise SystemExit({exit_code})
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_flat_impulse_request_is_exact_rust_v1_shape() -> None:
    request = build_fast_deterministic_row_request(
        record=_record(),
        manifest=_manifest(),
        posture=_flat(),
        evidence=FastOfflineImpulseScalpEvidence(execution=_execution()),
    )
    document = json.loads(request)

    assert document["schema_name"] == "shreks.fast_deterministic_row_request"
    assert document["schema_version"] == 1
    assert document["manifest"]["candidate_fingerprint_sha256"] == (
        "7377f016783f80c6d3935ff41efd7a66b8da280df13cd7be8d2e6c03146a8676"
    )
    assert document["posture"] == {"kind": "FLAT"}
    assert document["evidence"]["kind"] == "IMPULSE_SCALP"
    assert "market" not in document["evidence"]["execution"]
    assert "as_of_unix_ms" not in document["evidence"]["execution"]
    assert document["record"]["decision_signature"] == "sig-row"


def test_insufficient_exit_capacity_is_transported_to_rust_unchanged() -> None:
    insufficient = FastOfflineEntryExecution(
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=_leg(),
            exit=_leg(),
        ),
        trade=FastOfflineExecutionTrade(
            base_quantity=100.0,
            executable_entry_price_quote=0.01,
            forecast_exit_price_quote=0.012,
            exit_capacity_base=25.0,
            required_edge_bps=200,
            risk_margin_bps=100,
        ),
    )
    request = json.loads(
        build_fast_deterministic_row_request(
            record=_record(),
            manifest=_manifest(),
            posture=_flat(),
            evidence=FastOfflineImpulseScalpEvidence(execution=insufficient),
        )
    )
    trade = request["evidence"]["execution"]["trade"]
    assert trade["base_quantity"] == 100.0
    assert trade["exit_capacity_base"] == 25.0


def test_reserve_variants_emit_only_rust_exporter_fields() -> None:
    pump = FastTrainingReserveContext(
        kind="pump_curve",
        virtual_base_reserve_raw=100,
        virtual_quote_reserve_raw=200,
        real_base_reserve_raw=300,
        real_quote_reserve_raw=400,
        base_decimals=6,
        quote_decimals=9,
    )
    request = json.loads(
        build_fast_deterministic_row_request(
            record=_record(reserve=pump),
            manifest=_manifest(),
            posture=_flat(),
            evidence=FastOfflineImpulseScalpEvidence(execution=None),
        )
    )
    reserve = request["record"]["last_reserve_context"]
    assert set(reserve) == {
        "kind",
        "virtual_base_reserve_raw",
        "virtual_quote_reserve_raw",
        "real_base_reserve_raw",
        "real_quote_reserve_raw",
        "base_decimals",
        "quote_decimals",
    }

    swap = FastTrainingReserveContext(
        kind="pump_swap_pool",
        pool_base_reserve_raw=500,
        pool_quote_reserve_raw=600,
        virtual_quote_reserve_raw=700,
        base_decimals=6,
        quote_decimals=9,
    )
    swap_record = replace(_record(reserve=swap), venue="pump_swap")
    # The manifest is Impulse Scalp and this is only a serialization proof;
    # market posture still must match the row.
    swap_posture = replace(
        _flat(),
        market_key="pump_swap:mint-life:quote-life",
    )
    request = json.loads(
        build_fast_deterministic_row_request(
            record=swap_record,
            manifest=_manifest(),
            posture=swap_posture,
            evidence=FastOfflineImpulseScalpEvidence(execution=None),
        )
    )
    reserve = request["record"]["last_reserve_context"]
    assert set(reserve) == {
        "kind",
        "pool_base_reserve_raw",
        "pool_quote_reserve_raw",
        "virtual_quote_reserve_raw",
        "base_decimals",
        "quote_decimals",
    }


def test_open_posture_uses_authoritative_session_state_only() -> None:
    request = json.loads(
        build_fast_deterministic_row_request(
            record=_record(),
            manifest=_manifest(),
            posture=_open(),
            evidence=FastOfflineLongerRunnerEvidence(
                protective=FastOfflineLongerRunnerProtective(
                    hard_stop_triggered=False,
                    risk_limit_exit_required=False,
                    liquidity_exit_required=False,
                ),
                continuation=None,
            ),
        )
    )
    assert request["posture"] == {
        "kind": "OPEN",
        "current_exposure_fraction": 0.8,
        "opened_at_unix_ms": T0 - 1_000,
    }
    assert "position_id" not in request["posture"]
    assert set(request["evidence"]["protective"]) == {
        "hard_stop_triggered",
        "risk_limit_exit_required",
        "liquidity_exit_required",
    }


def test_wrong_market_or_evidence_family_fails_before_process_launch(tmp_path: Path) -> None:
    wrong_posture = replace(_flat(), market_key="other:mint:quote")
    with pytest.raises(ValueError, match="market"):
        build_fast_deterministic_row_request(
            record=_record(),
            manifest=_manifest(),
            posture=wrong_posture,
            evidence=FastOfflineImpulseScalpEvidence(execution=None),
        )

    binary = tmp_path / "must-not-run"
    binary.write_text("#!/bin/sh\nexit 77\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | 0o111)
    with pytest.raises(ValueError, match="evidence|family|manager"):
        evaluate_fast_deterministic_row_offline(
            binary_path=binary,
            record=_record(),
            manifest=_manifest(),
            posture=_flat(),
            evidence=FastOfflineLongerRunnerEvidence(
                protective=FastOfflineLongerRunnerProtective(
                    hard_stop_triggered=False,
                    risk_limit_exit_required=False,
                    liquidity_exit_required=False,
                ),
                continuation=None,
            ),
        )


def test_valid_offline_result_decodes_to_exact_lifecycle_decision(tmp_path: Path) -> None:
    document = _result_document()
    binary = tmp_path / "row-evaluator"
    _write_fake_binary(binary, _rust_wire_json(document))

    decision = evaluate_fast_deterministic_row_offline(
        binary_path=binary,
        record=_record(),
        manifest=_manifest(),
        posture=_flat(),
        evidence=FastOfflineImpulseScalpEvidence(execution=_execution()),
    )

    assert type(decision) is FastDeterministicLifecycleDecision
    assert decision.source_event_id == "sig-row:0"
    assert decision.market_key == MARKET
    assert decision.action == "BUY"
    assert decision.target_exposure_fraction == 0.8


def test_result_tamper_candidate_and_row_identity_fail_closed() -> None:
    manifest = _manifest()
    record = _record()
    posture = _flat()

    document = _result_document()
    payload = _rust_wire_json(document)
    tampered = payload.replace('"target_exposure_fraction":0.8', '"target_exposure_fraction":0.7')
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_deterministic_row_result(
            tampered,
            manifest=manifest,
            record=record,
            posture=posture,
        )

    document = _result_document()
    document["candidate_version"] = "other-candidate"
    material = dict(document)
    material.pop("result_fingerprint_sha256")
    document["result_fingerprint_sha256"] = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="candidate"):
        decode_fast_deterministic_row_result(
            _rust_wire_json(document),
            manifest=manifest,
            record=record,
            posture=posture,
        )

    document = _result_document()
    document["decision"]["source_event_id"] = "other:0"
    material = dict(document)
    material.pop("result_fingerprint_sha256")
    document["result_fingerprint_sha256"] = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="identity|source"):
        decode_fast_deterministic_row_result(
            _rust_wire_json(document),
            manifest=manifest,
            record=record,
            posture=posture,
        )


def test_nonzero_binary_exit_fails_closed_and_temp_request_is_removed(tmp_path: Path) -> None:
    binary = tmp_path / "row-evaluator"
    capture = tmp_path / "captured-request-path"
    script = f"""#!/usr/bin/env python3
import sys
from pathlib import Path
Path({str(capture)!r}).write_text(sys.argv[1], encoding="utf-8")
print("intentional failure", file=sys.stderr)
raise SystemExit(7)
"""
    binary.write_text(script, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | 0o111)

    with pytest.raises(RuntimeError, match="7|failure"):
        evaluate_fast_deterministic_row_offline(
            binary_path=binary,
            record=_record(),
            manifest=_manifest(),
            posture=_flat(),
            evidence=FastOfflineImpulseScalpEvidence(execution=None),
        )

    request_path = Path(capture.read_text(encoding="utf-8"))
    assert not request_path.exists()


def test_process_authority_is_isolated_from_pure_packages() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "shreks_brain"
    adapter = root / "fast_deterministic_offline"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(adapter.glob("*.py"))
    )
    assert "subprocess.run" in source

    for pure in (
        root / "fast_deterministic_lifecycle",
        root / "fast_campaign_paper",
    ):
        pure_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(pure.glob("*.py"))
        )
        assert "import subprocess" not in pure_source
        assert "subprocess.run" not in pure_source

    for forbidden in (
        "requests.",
        "sqlite3",
        "cargo ",
        "cargo\"",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
