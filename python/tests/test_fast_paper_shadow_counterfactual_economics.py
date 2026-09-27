from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    write_fast_paper_runtime_manifest,
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_shadow_sample_proof import (
    FastPaperShadowSamplePolicy,
    canonical_fast_paper_shadow_sample_proof,
    summarize_fast_paper_shadow_independent_sample,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime
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
    encode_fast_training_execution_cost_policy,
)

import shreks_brain.fast_paper_shadow_counterfactual_economics as economics

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record_at,
    _runtime_fixture,
)


def _cost_policy(
    version: str,
    *,
    entry_slippage_bps: int,
    exit_slippage_bps: int,
    entry_latency_bps: int = 5,
    exit_latency_bps: int = 5,
    network_fee_quote: float = 0.0,
) -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version=version,
        additional_entry_slippage_bps=entry_slippage_bps,
        additional_exit_slippage_bps=exit_slippage_bps,
        entry_latency_bps=entry_latency_bps,
        exit_latency_bps=exit_latency_bps,
        entry_network_fee_quote=network_fee_quote,
        exit_network_fee_quote=network_fee_quote,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def _reserve(
    *,
    signature: str,
    ordinal: int,
    sequence: int,
    observed_at: int,
) -> FastTrainingEconomicsReserveProvenance:
    return FastTrainingEconomicsReserveProvenance(
        source_signature=signature,
        source_ordinal=ordinal,
        source_sequence=sequence,
        source_observed_at_unix_ms=observed_at,
        pool_base_reserve_raw=10_000_000_000,
        pool_quote_reserve_raw=5_000_000_000,
        virtual_quote_reserve_raw=1_000_000_000,
        base_decimals=6,
        quote_decimals=9,
    )


def _fee(
    *,
    signature: str,
    ordinal: int,
    sequence: int,
    observed_at: int,
    bps: int,
) -> FastTrainingEconomicsFeeProvenance:
    market_quote_amount_raw = 100_000_000
    signed = market_quote_amount_raw * bps // 10_000
    return FastTrainingEconomicsFeeProvenance(
        source_signature=signature,
        source_ordinal=ordinal,
        source_sequence=sequence,
        source_observed_at_unix_ms=observed_at,
        age_ms=0,
        market_quote_amount_raw=market_quote_amount_raw,
        user_quote_amount_raw=market_quote_amount_raw + signed,
        signed_user_cost_quote_raw=signed,
        effective_fee_bps=bps,
    )


def _available_row(
    feature,
    *,
    horizon_ms: int,
    endpoint_suffix: str,
    exit_quote: float,
) -> FastTrainingEconomicsOverlayRow:
    endpoint_signature = f"endpoint-{endpoint_suffix}"
    endpoint_sequence = feature.decision_sequence + horizon_ms // 100 + 1
    endpoint_at = feature.decision_observed_at_unix_ms + min(
        horizon_ms,
        max(1, horizon_ms - 10),
    )
    return FastTrainingEconomicsOverlayRow(
        decision_signature=feature.decision_signature,
        decision_ordinal=feature.decision_ordinal,
        decision_sequence=feature.decision_sequence,
        decision_observed_at_unix_ms=feature.decision_observed_at_unix_ms,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        venue="pump_swap",
        horizon_ms=horizon_ms,
        future_path_label_version=1,
        counterfactual_base_quantity="2",
        endpoint_signature=endpoint_signature,
        endpoint_ordinal=feature.decision_ordinal,
        endpoint_sequence=endpoint_sequence,
        endpoint_observed_at_unix_ms=endpoint_at,
        status=FastTrainingEconomicsStatus.AVAILABLE,
        requested_base_quantity_raw=2_000_000,
        entry_reserve=_reserve(
            signature=feature.decision_signature,
            ordinal=feature.decision_ordinal,
            sequence=feature.decision_sequence,
            observed_at=feature.decision_observed_at_unix_ms - 1,
        ),
        exit_reserve=_reserve(
            signature=endpoint_signature,
            ordinal=feature.decision_ordinal,
            sequence=endpoint_sequence,
            observed_at=endpoint_at - 1,
        ),
        entry_projection=FastTrainingEconomicsEntryProjection(
            base_quantity_raw=2_000_000,
            quote_input_raw=100_000_000_000,
            base_quantity=2.0,
            quote_input=100.0,
            average_price_quote=50.0,
        ),
        exit_projection=FastTrainingEconomicsExitProjection(
            base_quantity_raw=2_000_000,
            quote_output_raw=int(exit_quote * 1_000_000_000),
            base_quantity=2.0,
            quote_output=exit_quote,
            average_price_quote=exit_quote / 2.0,
        ),
        entry_fee=_fee(
            signature=f"entry-fee-{endpoint_suffix}",
            ordinal=feature.decision_ordinal,
            sequence=feature.decision_sequence,
            observed_at=feature.decision_observed_at_unix_ms,
            bps=50,
        ),
        exit_fee=_fee(
            signature=f"exit-fee-{endpoint_suffix}",
            ordinal=feature.decision_ordinal,
            sequence=endpoint_sequence,
            observed_at=endpoint_at,
            bps=40,
        ),
    )


def _write_overlay(tmp_path: Path, rows: tuple[FastTrainingEconomicsOverlayRow, ...]) -> Path:
    root = tmp_path / "training-economics"
    root.mkdir(parents=True)
    ordered = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_sequence,
                row.horizon_ms,
                row.decision_signature,
                row.decision_ordinal,
                row.future_path_label_version,
            ),
        )
    )
    encoded_rows = b"".join(
        json.dumps(
            asdict(row),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for row in ordered
    )
    (root / "rows.jsonl").write_bytes(encoded_rows)
    status_counts: dict[str, int] = {}
    for row in ordered:
        status_counts[row.status.value] = status_counts.get(row.status.value, 0) + 1
    manifest = {
        "schema_name": FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME,
        "schema_version": FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION,
        "row_count": len(ordered),
        "available_row_count": sum(
            row.status is FastTrainingEconomicsStatus.AVAILABLE
            for row in ordered
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "feature_source_jsonl_sha256": "a" * 64,
        "future_path_logical_fingerprint_sha256": "b" * 64,
        "future_path_label_version": 1,
        "counterfactual_base_quantity": "2",
        "pump_swap_fee_maximum_age_ms": 60_000,
        "min_decision_observed_at_unix_ms": min(
            row.decision_observed_at_unix_ms for row in ordered
        ),
        "max_decision_observed_at_unix_ms": max(
            row.decision_observed_at_unix_ms for row in ordered
        ),
        "ordered_row_logical_fingerprint_sha256": hashlib.sha256(
            encoded_rows
        ).hexdigest(),
    }
    manifest["manifest_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return root


def _write_policy(tmp_path: Path, name: str, policy: FastTrainingExecutionCostPolicy) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(
        encode_fast_training_execution_cost_policy(policy),
        encoding="utf-8",
    )
    return path


def _sample_checkpoint(mint: str):
    position = SimpleNamespace(
        position_id="sample-closed-position",
        mint=mint,
        state=PaperPositionState.CLOSED,
        closed_at_unix_ms=20_500,
    )
    return SimpleNamespace(
        state=SimpleNamespace(
            ledger=SimpleNamespace(positions=(position,))
        )
    )


def _fixture(monkeypatch, tmp_path: Path):
    manifest, binding, _policy, _checkpoint, _posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base = _record()
    buy = _evidence_for(
        monkeypatch,
        manifest,
        base,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    skip_record = _record_at(
        base,
        signature="fl11-2b-skip",
        sequence=2,
        at=20_100,
    )
    skip = _evidence_for(
        monkeypatch,
        manifest,
        skip_record,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_120,
        entry_observed_at=20_110,
        exit_observed_at=20_115,
    )

    manifest_path = tmp_path / "manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    decision_root = tmp_path / "decisions"
    decision_root.mkdir()
    for evidence in (buy, skip):
        write_fast_paper_shadow_decision_evidence(
            evidence,
            decision_root
            / f"shadow-{evidence.source_sequence:020d}-"
            f"{evidence.evidence_fingerprint_sha256[:16]}.json",
        )

    since = 19_900
    until = 21_000
    sample = summarize_fast_paper_shadow_independent_sample(
        (buy, skip),
        buy_regimes={
            buy.evidence_fingerprint_sha256: MarketRegime.NORMAL
        },
        missing_buy_execution_source_count=0,
        checkpoint=_sample_checkpoint(base.mint),
        policy=FastPaperShadowSamplePolicy(
            version="fl11.2b-test-sample-v1",
            min_decision_count=2,
            min_distinct_market_count=1,
            min_distinct_mint_count=1,
            min_observation_span_ms=1,
            min_closed_position_count=1,
            min_distinct_traded_mint_count=1,
            min_distinct_buy_regime_count=1,
            min_distinct_selected_horizon_count=1,
        ),
        expected_release_sha=manifest.release_source_sha,
        binding_fingerprint_sha256=binding.binding_fingerprint_sha256,
        since_unix_ms=since,
        until_unix_ms=until,
    )
    assert sample["decision"] == "SUFFICIENT_SAMPLE"
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(
        canonical_fast_paper_shadow_sample_proof(sample),
        encoding="utf-8",
    )
    return (
        manifest,
        binding,
        skip,
        manifest_path,
        decision_root,
        sample_path,
        since,
        until,
    )


def test_counterfactual_economics_reports_missed_profit_avoided_loss_and_sensitivity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        skip,
        manifest_path,
        decision_root,
        sample_path,
        since,
        until,
    ) = _fixture(monkeypatch, tmp_path)
    feature = skip.feature_record
    overlay = _write_overlay(
        tmp_path,
        (
            _available_row(
                feature,
                horizon_ms=500,
                endpoint_suffix="profit",
                exit_quote=120.0,
            ),
            _available_row(
                feature,
                horizon_ms=1_000,
                endpoint_suffix="loss",
                exit_quote=80.0,
            ),
        ),
    )
    baseline = _cost_policy(
        "baseline-v1",
        entry_slippage_bps=0,
        exit_slippage_bps=0,
    )
    stressed = _cost_policy(
        "stress-v1",
        entry_slippage_bps=2_000,
        exit_slippage_bps=2_000,
    )

    report = economics.collect_fast_paper_shadow_counterfactual_economics(
        manifest_path=manifest_path,
        ledger_database_path=Path(binding.database_path),
        run_id=binding.run_id,
        decision_evidence_directory=decision_root,
        sample_proof_path=sample_path,
        training_economics_overlay_path=overlay,
        baseline_cost_policy_path=_write_policy(
            tmp_path,
            "baseline",
            baseline,
        ),
        sensitivity_cost_policy_paths=(
            _write_policy(tmp_path, "stress", stressed),
        ),
        horizons_ms=(1_000, 500),
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )

    assert report["horizons_ms"] == [500, 1_000]
    assert report["skip_decision_count"] == 1
    base = report["baseline"]
    assert base["overall"]["observation_count"] == 2
    assert base["overall"]["executable_count"] == 2
    assert base["overall"]["profitable_missed_opportunity_count"] == 1
    assert base["overall"]["avoided_loss_count"] == 1
    assert base["overall"]["missed_positive_opportunity_quote"] > 0.0
    assert base["overall"]["avoided_loss_quote"] > 0.0
    assert sum(
        item["observation_count"] for item in base["by_horizon"]
    ) == 2

    stress = report["sensitivity"][0]
    assert stress["cost_policy"]["version"] == "stress-v1"
    assert (
        stress["overall"]["signed_net_opportunity_quote"]
        < base["overall"]["signed_net_opportunity_quote"]
    )
    assert stress["delta_vs_baseline"]["sign_flip_count"] >= 1
    assert stress["delta_vs_baseline"]["comparable_executable_count"] == 2
    assert report["actual_trade_fee_slippage_burden"] == "MEASURED_BY_FL11_2A"
    assert report["latency_sensitivity"] == "NOT_INCLUDED_FL11_2B"
    assert report["promotion_authority"] == "NOT_GRANTED"
    assert report["production_paper_cutover"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"

    fingerprint = report["report_fingerprint_sha256"]
    material = dict(report)
    material.pop("report_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        economics.canonical_fast_paper_shadow_counterfactual_economics(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_counterfactual_economics_rejects_latency_sensitivity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        skip,
        manifest_path,
        decision_root,
        sample_path,
        since,
        until,
    ) = _fixture(monkeypatch, tmp_path)
    overlay = _write_overlay(
        tmp_path,
        (
            _available_row(
                skip.feature_record,
                horizon_ms=500,
                endpoint_suffix="profit",
                exit_quote=120.0,
            ),
        ),
    )
    baseline = _cost_policy(
        "baseline-v1",
        entry_slippage_bps=0,
        exit_slippage_bps=0,
    )
    latency_changed = _cost_policy(
        "latency-changed-v1",
        entry_slippage_bps=10,
        exit_slippage_bps=10,
        entry_latency_bps=6,
    )

    with pytest.raises(
        economics.FastPaperShadowCounterfactualEconomicsError,
        match="latency",
    ):
        economics.collect_fast_paper_shadow_counterfactual_economics(
            manifest_path=manifest_path,
            ledger_database_path=Path(binding.database_path),
            run_id=binding.run_id,
            decision_evidence_directory=decision_root,
            sample_proof_path=sample_path,
            training_economics_overlay_path=overlay,
            baseline_cost_policy_path=_write_policy(
                tmp_path,
                "baseline-latency",
                baseline,
            ),
            sensitivity_cost_policy_paths=(
                _write_policy(
                    tmp_path,
                    "changed-latency",
                    latency_changed,
                ),
            ),
            horizons_ms=(500,),
            expected_release_sha=manifest.release_source_sha,
            since_unix_ms=since,
            until_unix_ms=until,
        )


def test_counterfactual_economics_does_not_infer_missing_skip_row(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        skip,
        manifest_path,
        decision_root,
        sample_path,
        since,
        until,
    ) = _fixture(monkeypatch, tmp_path)
    feature = skip.feature_record
    unrelated = replace(
        _available_row(
            feature,
            horizon_ms=1_000,
            endpoint_suffix="unrelated",
            exit_quote=120.0,
        ),
        decision_signature="other-decision",
        entry_reserve=replace(
            _available_row(
                feature,
                horizon_ms=1_000,
                endpoint_suffix="unrelated-reserve",
                exit_quote=120.0,
            ).entry_reserve,
            source_signature="other-decision",
        ),
    )
    overlay = _write_overlay(
        tmp_path,
        (
            _available_row(
                feature,
                horizon_ms=500,
                endpoint_suffix="covered",
                exit_quote=120.0,
            ),
            unrelated,
        ),
    )
    baseline = _cost_policy(
        "baseline-v1",
        entry_slippage_bps=0,
        exit_slippage_bps=0,
    )
    stress = _cost_policy(
        "stress-v1",
        entry_slippage_bps=100,
        exit_slippage_bps=100,
    )

    report = economics.collect_fast_paper_shadow_counterfactual_economics(
        manifest_path=manifest_path,
        ledger_database_path=Path(binding.database_path),
        run_id=binding.run_id,
        decision_evidence_directory=decision_root,
        sample_proof_path=sample_path,
        training_economics_overlay_path=overlay,
        baseline_cost_policy_path=_write_policy(
            tmp_path,
            "baseline-missing",
            baseline,
        ),
        sensitivity_cost_policy_paths=(
            _write_policy(tmp_path, "stress-missing", stress),
        ),
        horizons_ms=(500, 1_000),
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )

    assert report["baseline"]["overall"]["missing_row_count"] == 1
    missing = [
        item
        for item in report["baseline"]["observations"]
        if item["execution_status"] == "MISSING_ROW"
    ]
    assert len(missing) == 1
    assert missing[0]["counterfactual_net_pnl_quote_vs_skip"] is None


def test_counterfactual_economics_requires_exact_sufficient_sample(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        skip,
        manifest_path,
        decision_root,
        sample_path,
        since,
        until,
    ) = _fixture(monkeypatch, tmp_path)
    overlay = _write_overlay(
        tmp_path,
        (
            _available_row(
                skip.feature_record,
                horizon_ms=500,
                endpoint_suffix="sample",
                exit_quote=120.0,
            ),
        ),
    )
    baseline = _cost_policy(
        "baseline-v1",
        entry_slippage_bps=0,
        exit_slippage_bps=0,
    )
    stress = _cost_policy(
        "stress-v1",
        entry_slippage_bps=100,
        exit_slippage_bps=100,
    )

    with pytest.raises(
        economics.FastPaperShadowCounterfactualEconomicsError,
        match="prerequisite|mismatch",
    ):
        economics.collect_fast_paper_shadow_counterfactual_economics(
            manifest_path=manifest_path,
            ledger_database_path=Path(binding.database_path),
            run_id=binding.run_id,
            decision_evidence_directory=decision_root,
            sample_proof_path=sample_path,
            training_economics_overlay_path=overlay,
            baseline_cost_policy_path=_write_policy(
                tmp_path,
                "baseline-window",
                baseline,
            ),
            sensitivity_cost_policy_paths=(
                _write_policy(tmp_path, "stress-window", stress),
            ),
            horizons_ms=(500,),
            expected_release_sha=manifest.release_source_sha,
            since_unix_ms=since,
            until_unix_ms=until + 1,
        )


def test_counterfactual_economics_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(economics.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-counterfactual-economics = '
        '"shreks_brain.fast_paper_shadow_counterfactual_economics:main"'
    ) in pyproject

    for required in (
        "build_entry_counterfactual_context_from_training_economics",
        "label_entry_counterfactuals",
        "read_fast_training_economics_overlay_for_horizon",
        "fast_training_execution_cost_policy_fingerprint_sha256",
    ):
        assert required in source

    for forbidden in (
        "execute_fast_paper_shadow_decision(",
        "retry_fast_paper_shadow_pending_buy(",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "commit_fast_paper_shadow_transition_atomically",
        "ChampionChallengerRegistry",
        "score_candidate",
        "shreks_brain.scoring",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
