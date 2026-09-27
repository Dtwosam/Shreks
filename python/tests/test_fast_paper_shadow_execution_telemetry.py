from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime import (
    execute_fast_paper_shadow_decision,
    load_fast_paper_shadow_ledger_checkpoint_by_sequence,
    load_fast_paper_shadow_runtime_state_by_checkpoint_sequence,
    produce_fast_paper_shadow_execution_input_source_record,
    reconstruct_fast_paper_shadow_decision,
    write_fast_paper_shadow_decision_evidence,
    write_fast_paper_shadow_execution_input_source_record,
)
import shreks_brain.fast_paper_shadow_execution_telemetry as telemetry

from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _record,
    _runtime_fixture,
    _source,
)


def _persist_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    max_entry_price: float | None = None,
):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=__import__(
            "shreks_brain.fast_campaign",
            fromlist=["FastCampaignDecisionPosition"],
        ).FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_020,
        exit_observed_at=20_015,
    )
    source = _source(record, evidence)
    if max_entry_price is not None:
        assert source.entry_authority is not None
        source = replace(
            source,
            entry_authority=replace(
                source.entry_authority,
                maximum_acceptable_entry_price_quote=max_entry_price,
            ),
        )

    decisions = tmp_path / "decisions"
    sources = tmp_path / "execution-sources"
    decisions.mkdir()
    sources.mkdir()
    write_fast_paper_shadow_decision_evidence(
        evidence,
        decisions / "shadow-00000000000000000001.json",
    )
    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
        source_observed_at_unix_ms=20_020,
        risk_day_started_at_unix_ms=0,
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        sources,
    )

    transition = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        source,
    )
    successor, successor_posture = _persist(
        manifest,
        binding,
        transition,
        sequence=1,
        created_at=20_060,
    )
    return {
        "manifest": manifest,
        "binding": binding,
        "policy": policy,
        "pre": checkpoint,
        "pre_posture": posture,
        "evidence": evidence,
        "source": source,
        "source_record": source_record,
        "transition": transition,
        "successor": successor,
        "successor_posture": successor_posture,
        "decision_directory": decisions,
        "source_directory": sources,
    }


def test_historical_pair_loaders_and_read_only_reconstruction_preserve_latest_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _persist_case(monkeypatch, tmp_path)

    assert load_fast_paper_shadow_ledger_checkpoint_by_sequence(
        case["manifest"],
        case["binding"],
        sequence=0,
    ) == case["pre"]
    assert load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
        case["manifest"],
        case["binding"],
        sequence=0,
    ) == case["pre_posture"]

    with pytest.raises(ValueError, match="latest durable|latest.*checkpoint|stale"):
        execute_fast_paper_shadow_decision(
            case["manifest"],
            case["policy"],
            case["binding"],
            case["pre"],
            case["pre_posture"],
            case["source"],
        )

    reconstructed = reconstruct_fast_paper_shadow_decision(
        case["manifest"],
        case["policy"],
        case["binding"],
        case["pre"],
        case["pre_posture"],
        case["source"],
    )
    assert reconstructed == case["transition"]
    assert reconstructed.next_paper_state == case["successor"].state


def test_execution_join_reports_fill_latency_and_like_for_like_price_cost(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _persist_case(monkeypatch, tmp_path)
    transition = case["transition"]
    assert transition.buy_result is not None
    assert transition.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert transition.buy_result.execution is not None
    assert transition.buy_result.execution.fill is not None
    fill = transition.buy_result.execution.fill

    result = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decision_directory"],
        execution_source_directory=case["source_directory"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )

    assert result["decision_count"] == 1
    assert result["joined_execution_count"] == 1
    assert result["missing_execution_source_count"] == 0
    assert result["missing_successor_commit_count"] == 0
    assert result["action_counts"] == {
        "BUY": 1,
        "SKIP": 0,
        "HOLD": 0,
        "REDUCE": 0,
        "SELL": 0,
    }
    assert result["outcome_counts"] == {"FILLED": 1}
    assert result["max_entry_price_abort_count"] == 0

    assert result["decision_to_commit_latency_ms"] == {
        "mean": 40.0,
        "p50": 40.0,
        "p95": 40.0,
    }
    assert result["decision_to_booked_entry_latency_ms"] == {
        "mean": 0.0,
        "p50": 0.0,
        "p95": 0.0,
    }
    assert result["expected_selected_price_cost_bps"]["mean"] == pytest.approx(
        case["evidence"].entry_execution_cost_bps
    )
    assert result["realized_price_cost_bps"]["mean"] == pytest.approx(
        fill.signed_slippage_bps
    )
    assert result["realized_minus_expected_price_cost_bps"]["mean"] == pytest.approx(
        fill.signed_slippage_bps
        - case["evidence"].entry_execution_cost_bps
    )
    explicit_bps = (
        fill.explicit_cost_usd / fill.filled_notional_usd * 10_000.0
    )
    assert result["realized_explicit_cost_bps"]["mean"] == pytest.approx(
        explicit_bps
    )
    assert result["realized_total_execution_burden_bps"]["mean"] == pytest.approx(
        fill.signed_slippage_bps + explicit_bps
    )

    fingerprint = result["telemetry_fingerprint_sha256"]
    material = dict(result)
    material.pop("telemetry_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        telemetry.canonical_fast_paper_shadow_execution_telemetry(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_execution_join_attributes_max_entry_price_abort_without_fake_fill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _persist_case(
        monkeypatch,
        tmp_path,
        max_entry_price=1.005,
    )
    transition = case["transition"]
    assert transition.buy_result is not None
    assert (
        transition.buy_result.outcome
        is FastPaperBuyOutcome.ABORTED_PRICE_ABOVE_MAXIMUM
    )
    assert transition.buy_result.execution is None
    assert case["successor"].state.ledger.entries == ()

    result = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decision_directory"],
        execution_source_directory=case["source_directory"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )

    assert result["joined_execution_count"] == 1
    assert result["outcome_counts"] == {
        "ABORTED_PRICE_ABOVE_MAXIMUM": 1
    }
    assert result["max_entry_price_abort_count"] == 1
    assert result["decision_to_booked_entry_latency_ms"] == {
        "mean": None,
        "p50": None,
        "p95": None,
    }
    assert result["realized_price_cost_bps"]["mean"] is None
    assert result["realized_explicit_cost_bps"]["mean"] is None


def test_execution_join_counts_missing_source_and_successor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _persist_case(monkeypatch, tmp_path)
    source_file = next(case["source_directory"].glob("*.json"))
    source_file.unlink()

    missing_source = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decision_directory"],
        execution_source_directory=case["source_directory"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )
    assert missing_source["decision_count"] == 1
    assert missing_source["joined_execution_count"] == 0
    assert missing_source["missing_execution_source_count"] == 1

    write_fast_paper_shadow_execution_input_source_record(
        case["source_record"],
        case["source_directory"],
    )
    import sqlite3

    with sqlite3.connect(case["binding"].database_path) as connection:
        connection.execute(
            "DELETE FROM fast_paper_shadow_runtime_states WHERE run_id = ? AND paper_checkpoint_sequence = 1",
            (case["binding"].run_id,),
        )
        connection.execute(
            "DELETE FROM paper_loop_checkpoints WHERE run_id = ? AND sequence = 1",
            (case["binding"].run_id,),
        )
        connection.commit()

    missing_successor = (
        telemetry.summarize_fast_paper_shadow_execution_telemetry(
            manifest=case["manifest"],
            execution_policy=case["policy"],
            binding=case["binding"],
            decision_evidence_directory=case["decision_directory"],
            execution_source_directory=case["source_directory"],
            expected_release_sha=case["manifest"].release_source_sha,
            since_unix_ms=20_000,
            until_unix_ms=21_000,
        )
    )
    assert missing_successor["decision_count"] == 1
    assert missing_successor["joined_execution_count"] == 0
    assert missing_successor["missing_successor_commit_count"] == 1


def test_execution_join_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(telemetry.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-execution-telemetry = '
        '"shreks_brain.fast_paper_shadow_execution_telemetry:main"'
    ) in pyproject

    for forbidden in (
        "run_fast_paper_shadow_service_execution",
        "commit_fast_paper_shadow_transition_atomically",
        "save_fast_paper",
        "write_fast_paper_shadow",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
