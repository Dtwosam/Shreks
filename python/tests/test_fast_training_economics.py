from __future__ import annotations

from dataclasses import fields, replace
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from shreks_brain.research.counterfactuals import ExecutionStatus
from shreks_brain.research.fast_training_economics import (
    FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME,
    FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION,
    FastTrainingEconomicsEntryProjection,
    FastTrainingEconomicsExitProjection,
    FastTrainingEconomicsFeeProvenance,
    FastTrainingEconomicsOverlayRow,
    FastTrainingEconomicsReserveProvenance,
    FastTrainingEconomicsStatus,
    FastTrainingExecutionCostPolicy,
    build_entry_counterfactual_context_from_training_economics,
    decode_fast_training_execution_cost_policy,
    encode_fast_training_execution_cost_policy,
    fast_training_execution_cost_policy_fingerprint_sha256,
    read_fast_training_economics_overlay,
)
from shreks_brain.research.fast_training_targets import (
    load_future_path_training_labels_from_sqlite,
)


WSOL = "So11111111111111111111111111111111111111112"


def _policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="training-cost-v1",
        additional_entry_slippage_bps=10,
        additional_exit_slippage_bps=20,
        entry_latency_bps=5,
        exit_latency_bps=5,
        entry_network_fee_quote=0.1,
        exit_network_fee_quote=0.2,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def _reserve(signature: str, sequence: int, observed_at: int):
    return FastTrainingEconomicsReserveProvenance(
        source_signature=signature,
        source_ordinal=2,
        source_sequence=sequence,
        source_observed_at_unix_ms=observed_at,
        pool_base_reserve_raw=10_000_000_000,
        pool_quote_reserve_raw=5_000_000_000,
        virtual_quote_reserve_raw=1_000_000_000,
        base_decimals=6,
        quote_decimals=9,
    )


def _fee(signature: str, sequence: int, observed_at: int, bps: int):
    market_quote_amount_raw = 100_000_000
    signed_user_cost_quote_raw = market_quote_amount_raw * bps // 10_000
    assert signed_user_cost_quote_raw * 10_000 == market_quote_amount_raw * bps
    return FastTrainingEconomicsFeeProvenance(
        source_signature=signature,
        source_ordinal=2,
        source_sequence=sequence,
        source_observed_at_unix_ms=observed_at,
        age_ms=0,
        market_quote_amount_raw=market_quote_amount_raw,
        user_quote_amount_raw=market_quote_amount_raw + signed_user_cost_quote_raw,
        signed_user_cost_quote_raw=signed_user_cost_quote_raw,
        effective_fee_bps=bps,
    )


def _available_row() -> FastTrainingEconomicsOverlayRow:
    return FastTrainingEconomicsOverlayRow(
        decision_signature="decision",
        decision_ordinal=2,
        decision_sequence=10,
        decision_observed_at_unix_ms=1_000,
        mint="mint-training-economics-python",
        quote_mint=WSOL,
        venue="pump_swap",
        horizon_ms=500,
        future_path_label_version=1,
        counterfactual_base_quantity="2",
        endpoint_signature="endpoint",
        endpoint_ordinal=2,
        endpoint_sequence=11,
        endpoint_observed_at_unix_ms=1_200,
        status=FastTrainingEconomicsStatus.AVAILABLE,
        requested_base_quantity_raw=2_000_000,
        entry_reserve=_reserve("decision", 10, 980),
        exit_reserve=_reserve("endpoint", 11, 1_180),
        entry_projection=FastTrainingEconomicsEntryProjection(
            base_quantity_raw=2_000_000,
            quote_input_raw=100_000_000_000,
            base_quantity=2.0,
            quote_input=100.0,
            average_price_quote=50.0,
        ),
        exit_projection=FastTrainingEconomicsExitProjection(
            base_quantity_raw=2_000_000,
            quote_output_raw=120_000_000_000,
            base_quantity=2.0,
            quote_output=120.0,
            average_price_quote=60.0,
        ),
        entry_fee=_fee("decision-fee", 9, 1_000, 50),
        exit_fee=_fee("endpoint-fee", 11, 1_200, 40),
    )


def _write_rust_overlay_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = tmp_path / "rust-overlay-fixture"
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
    overlay = fixture_root / "training-economics"
    subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "shreks-observer",
            "--bin",
            "shreks-observe",
            "--",
            "export-training-economics",
            "--database",
            str(database),
            "--feature-jsonl",
            str(features),
            "--future-path-label-version",
            "1",
            "--counterfactual-base-quantity",
            "2",
            "--pump-swap-fee-maximum-age-ms",
            "60000",
            "--output",
            str(overlay),
        ],
        cwd=repo_root,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SHREKS_")
        },
        check=True,
        capture_output=True,
        text=True,
    )
    return database, features, overlay


def test_training_cost_policy_validates_and_has_no_hidden_protocol_or_impact_fields() -> None:
    policy = _policy()
    assert policy.version == "training-cost-v1"

    names = {field.name for field in fields(FastTrainingExecutionCostPolicy)}
    assert "protocol_fee_bps" not in names
    assert "effective_fee_bps" not in names
    assert "price_impact_bps" not in names
    assert "reserve_impact_bps" not in names

    with pytest.raises(ValueError):
        replace(policy, additional_entry_slippage_bps=-1)
    with pytest.raises(ValueError):
        replace(policy, exit_latency_bps=10_001)
    with pytest.raises(ValueError):
        replace(policy, entry_network_fee_quote=math.inf)
    with pytest.raises(ValueError):
        replace(policy, version=" ")


def test_training_cost_policy_codec_is_exact_and_fingerprinted() -> None:
    policy = _policy()
    payload = encode_fast_training_execution_cost_policy(policy)

    assert decode_fast_training_execution_cost_policy(payload) == policy
    fingerprint = fast_training_execution_cost_policy_fingerprint_sha256(policy)
    assert len(fingerprint) == 64
    assert fingerprint == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    decoded = json.loads(payload)
    decoded["unexpected"] = 1
    with pytest.raises(ValueError, match="keys|field|policy"):
        decode_fast_training_execution_cost_policy(
            json.dumps(decoded, sort_keys=True, separators=(",", ":"))
        )


def test_rust_overlay_reader_authenticates_source_fl4_rows_and_manifest(
    tmp_path: Path,
) -> None:
    database, features, overlay_path = _write_rust_overlay_fixture(tmp_path)

    overlay = read_fast_training_economics_overlay(overlay_path)
    assert overlay.manifest.schema_name == FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME
    assert overlay.manifest.schema_version == FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION
    assert overlay.manifest.feature_source_jsonl_sha256 == hashlib.sha256(
        features.read_bytes()
    ).hexdigest()
    assert (
        overlay.manifest.future_path_logical_fingerprint_sha256
        == load_future_path_training_labels_from_sqlite(
            database,
            future_path_label_version=1,
        ).logical_fingerprint_sha256
    )
    assert len(overlay.rows) == overlay.manifest.row_count

    tampered_rows = tmp_path / "tampered-rows"
    shutil.copytree(overlay_path, tampered_rows)
    raw = (tampered_rows / "rows.jsonl").read_bytes()
    assert b"mint-fl8-training" in raw
    (tampered_rows / "rows.jsonl").write_bytes(
        raw.replace(b"mint-fl8-training", b"mint-fl8-traininX", 1)
    )
    with pytest.raises(ValueError, match="fingerprint"):
        read_fast_training_economics_overlay(tampered_rows)

    tampered_manifest = tmp_path / "tampered-manifest"
    shutil.copytree(overlay_path, tampered_manifest)
    manifest_path = tampered_manifest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] += 1
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest.*fingerprint|fingerprint.*manifest"):
        read_fast_training_economics_overlay(tampered_manifest)


def test_fee_provenance_accepts_exact_non_integral_ratio_and_rejects_contradictions() -> None:
    exact_rational = FastTrainingEconomicsFeeProvenance(
        source_signature="rational-fee",
        source_ordinal=2,
        source_sequence=9,
        source_observed_at_unix_ms=1_000,
        age_ms=0,
        market_quote_amount_raw=3,
        user_quote_amount_raw=4,
        signed_user_cost_quote_raw=1,
        effective_fee_bps=None,
    )
    assert exact_rational.effective_fee_bps is None

    with pytest.raises(ValueError, match="fee|bps|ratio|represent"):
        FastTrainingEconomicsFeeProvenance(
            source_signature="contradictory-fee",
            source_ordinal=2,
            source_sequence=9,
            source_observed_at_unix_ms=1_000,
            age_ms=0,
            market_quote_amount_raw=3,
            user_quote_amount_raw=4,
            signed_user_cost_quote_raw=1,
            effective_fee_bps=100,
        )

    with pytest.raises(ValueError, match="negative|user-cost|delta|fee"):
        FastTrainingEconomicsFeeProvenance(
            source_signature="negative-fee",
            source_ordinal=2,
            source_sequence=9,
            source_observed_at_unix_ms=1_000,
            age_ms=0,
            market_quote_amount_raw=100,
            user_quote_amount_raw=99,
            signed_user_cost_quote_raw=-1,
            effective_fee_bps=0,
        )


def test_available_overlay_applies_exact_rational_source_fee_without_rounding() -> None:
    row = replace(
        _available_row(),
        entry_fee=FastTrainingEconomicsFeeProvenance(
            source_signature="decision-fee-rational",
            source_ordinal=2,
            source_sequence=9,
            source_observed_at_unix_ms=1_000,
            age_ms=0,
            market_quote_amount_raw=3,
            user_quote_amount_raw=4,
            signed_user_cost_quote_raw=1,
            effective_fee_bps=None,
        ),
        exit_fee=FastTrainingEconomicsFeeProvenance(
            source_signature="endpoint-fee-rational",
            source_ordinal=2,
            source_sequence=11,
            source_observed_at_unix_ms=1_200,
            age_ms=0,
            market_quote_amount_raw=7,
            user_quote_amount_raw=6,
            signed_user_cost_quote_raw=1,
            effective_fee_bps=None,
        ),
    )
    policy = _policy()
    context = build_entry_counterfactual_context_from_training_economics(
        row,
        policy=policy,
        overlay_manifest_fingerprint_sha256="d" * 64,
        base_quantity=2.0,
        horizon_complete=True,
    )

    entry_rate = Fraction(1, 3) + Fraction(
        policy.additional_entry_slippage_bps + policy.entry_latency_bps,
        10_000,
    )
    exit_rate = Fraction(1, 7) + Fraction(
        policy.additional_exit_slippage_bps + policy.exit_latency_bps,
        10_000,
    )
    expected_entry = (
        Fraction(row.entry_projection.quote_input_raw, 10**row.entry_reserve.quote_decimals)
        * (1 + entry_rate)
        + Fraction(str(policy.entry_network_fee_quote))
    )
    expected_exit = (
        Fraction(row.exit_projection.quote_output_raw, 10**row.exit_reserve.quote_decimals)
        * (1 - exit_rate)
        - Fraction(str(policy.exit_network_fee_quote))
    )

    assert context.buy_now is not None
    assert context.exit_at_horizon is not None
    assert context.buy_now.quote_amount == pytest.approx(float(expected_entry))
    assert context.exit_at_horizon.quote_amount == pytest.approx(float(expected_exit))


def test_available_overlay_applies_only_source_fee_and_explicit_non_source_costs() -> None:
    row = _available_row()
    context = build_entry_counterfactual_context_from_training_economics(
        row,
        policy=_policy(),
        overlay_manifest_fingerprint_sha256="a" * 64,
        base_quantity=2.0,
        horizon_complete=True,
    )

    assert context.buy_now is not None
    assert context.exit_at_horizon is not None
    assert context.buy_now.status is ExecutionStatus.EXECUTABLE
    assert context.exit_at_horizon.status is ExecutionStatus.EXECUTABLE

    assert context.buy_now.quote_amount == pytest.approx(
        100.0 * (1.0 + (50 + 10 + 5) / 10_000.0) + 0.1
    )
    assert context.exit_at_horizon.quote_amount == pytest.approx(
        120.0 * (1.0 - (40 + 20 + 5) / 10_000.0) - 0.2
    )
    assert context.buy_now.base_quantity == 2.0
    assert context.exit_at_horizon.base_quantity == 2.0
    assert "training-cost-v1" in context.buy_now.evidence_version
    assert context.buy_now.evidence_version == context.exit_at_horizon.evidence_version


def test_unavailable_overlay_keeps_entry_and_exit_unknown() -> None:
    row = _available_row()
    unavailable = replace(
        row,
        venue="pump_fun_bonding_curve",
        status=FastTrainingEconomicsStatus.UNSUPPORTED_VENUE,
        requested_base_quantity_raw=None,
        entry_reserve=None,
        exit_reserve=None,
        entry_projection=None,
        exit_projection=None,
        entry_fee=None,
        exit_fee=None,
    )
    context = build_entry_counterfactual_context_from_training_economics(
        unavailable,
        policy=_policy(),
        overlay_manifest_fingerprint_sha256="b" * 64,
        base_quantity=2.0,
        horizon_complete=True,
    )
    assert context.buy_now is None
    assert context.exit_at_horizon is None


def test_exit_cost_rate_at_or_above_one_hundred_percent_fails_closed() -> None:
    row = replace(
        _available_row(),
        exit_fee=_fee("endpoint-fee-high", 11, 1_200, 9_980),
    )
    with pytest.raises(ValueError, match="exit.*100|exit.*rate"):
        build_entry_counterfactual_context_from_training_economics(
            row,
            policy=_policy(),
            overlay_manifest_fingerprint_sha256="c" * 64,
            base_quantity=2.0,
            horizon_complete=True,
        )
