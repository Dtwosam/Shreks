from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowPendingBuyRetryInput,
    build_fast_paper_shadow_pending_buy_retry_source_record,
    produce_fast_paper_shadow_execution_input_source_record,
    read_fast_paper_shadow_pending_buy_retry_source_record,
    read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint,
    reconstruct_fast_paper_shadow_pending_buy_retry,
    retry_fast_paper_shadow_pending_buy,
    write_fast_paper_shadow_decision_evidence,
    write_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_pending_buy_retry_source_record,
)
import shreks_brain.fast_paper_shadow_execution_telemetry as telemetry

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _risk, _usd
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _runtime_fixture,
    _source,
)


def _case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    retry_execution_price: float = 1.03,
    persist_retry: bool = True,
):
    manifest, binding, policy, checkpoint0, posture0 = _runtime_fixture(
        tmp_path
    )
    feature = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    source = _source(feature, evidence)

    decisions = tmp_path / "decisions"
    sources = tmp_path / "execution-sources"
    retries = tmp_path / "pending-buy-retry-sources"
    decisions.mkdir()
    sources.mkdir()
    retries.mkdir()

    write_fast_paper_shadow_decision_evidence(
        evidence,
        decisions / "shadow-00000000000000000001.json",
    )
    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint0,
        posture0,
        source,
        source_observed_at_unix_ms=20_020,
        risk_day_started_at_unix_ms=0,
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        sources,
    )

    deferred = retry_source_transition = None
    deferred = __import__(
        "shreks_brain.fast_paper_runtime",
        fromlist=["execute_fast_paper_shadow_decision"],
    ).execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint0,
        posture0,
        source,
    )
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED

    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        deferred,
        sequence=1,
        created_at=20_020,
    )
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=20_200,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=20_150,
            reference_price_quote=1.02,
            execution_price_quote=retry_execution_price,
        ),
        risk_context=_risk(20_200),
        quote_usd_evidence=_usd(feature, observed_at=20_190),
    )
    retry_record = (
        build_fast_paper_shadow_pending_buy_retry_source_record(
            manifest,
            binding,
            policy,
            checkpoint1,
            posture1,
            retry,
            risk_day_started_at_unix_ms=0,
            source_observed_at_unix_ms=20_195,
        )
    )
    write_fast_paper_shadow_pending_buy_retry_source_record(
        retry_record,
        retries,
    )

    retry_source_transition = retry_fast_paper_shadow_pending_buy(
        manifest,
        policy,
        binding,
        checkpoint1,
        posture1,
        retry,
    )
    checkpoint2 = posture2 = None
    if persist_retry:
        checkpoint2, posture2 = _persist(
            manifest,
            binding,
            retry_source_transition,
            sequence=2,
            created_at=20_240,
        )

    return {
        "manifest": manifest,
        "binding": binding,
        "policy": policy,
        "checkpoint1": checkpoint1,
        "posture1": posture1,
        "retry": retry,
        "retry_record": retry_record,
        "retry_transition": retry_source_transition,
        "checkpoint2": checkpoint2,
        "posture2": posture2,
        "decisions": decisions,
        "sources": sources,
        "retries": retries,
    }


def test_retry_historical_reader_and_reconstruction_preserve_latest_gates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _case(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="latest|checkpoint|state"):
        read_fast_paper_shadow_pending_buy_retry_source_record(
            case["manifest"],
            case["binding"],
            case["policy"],
            case["checkpoint1"],
            case["posture1"],
            case["retries"],
        )

    restored = (
        read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint(
            case["manifest"],
            case["binding"],
            case["policy"],
            case["checkpoint1"],
            case["posture1"],
            case["retries"],
        )
    )
    assert restored == case["retry_record"]

    with pytest.raises(ValueError, match="latest durable|latest.*checkpoint|stale"):
        retry_fast_paper_shadow_pending_buy(
            case["manifest"],
            case["policy"],
            case["binding"],
            case["checkpoint1"],
            case["posture1"],
            case["retry"],
        )

    reconstructed = reconstruct_fast_paper_shadow_pending_buy_retry(
        case["manifest"],
        case["policy"],
        case["binding"],
        case["checkpoint1"],
        case["posture1"],
        case["retry"],
    )
    assert reconstructed == case["retry_transition"]
    assert reconstructed.next_paper_state == case["checkpoint2"].state


def test_combined_execution_telemetry_joins_pending_buy_retry_fill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _case(monkeypatch, tmp_path)
    transition = case["retry_transition"]
    assert transition.buy_result is not None
    assert transition.buy_result.outcome is FastPaperBuyOutcome.FILLED
    assert transition.buy_result.execution is not None
    assert transition.buy_result.execution.fill is not None
    fill = transition.buy_result.execution.fill

    result = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decisions"],
        execution_source_directory=case["sources"],
        pending_buy_retry_source_directory=case["retries"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )

    assert result["schema_version"] == 2
    assert result["decision_count"] == 1
    assert result["outcome_counts"] == {"DEFERRED": 1}
    assert result["pending_buy_retry_joined"] is True
    assert result["pending_buy_retry_count"] == 1
    assert result["joined_pending_buy_retry_count"] == 1
    assert result["missing_retry_successor_commit_count"] == 0
    assert result["pending_buy_retry_outcome_counts"] == {"FILLED": 1}
    assert result["pending_buy_retry_terminal_count"] == 1
    assert result["pending_buy_retry_deferred_count"] == 0
    assert result["pending_buy_retry_max_entry_price_abort_count"] == 0
    assert result["retry_to_commit_latency_ms"] == {
        "mean": 40.0,
        "p50": 40.0,
        "p95": 40.0,
    }
    assert result["retry_to_booked_entry_latency_ms"] == {
        "mean": 0.0,
        "p50": 0.0,
        "p95": 0.0,
    }

    quote = case["retry"].quote
    expected_quote_cost = (
        quote.execution_price_quote / quote.reference_price_quote - 1.0
    ) * 10_000.0
    assert result["retry_quote_price_cost_bps"]["mean"] == pytest.approx(
        expected_quote_cost
    )
    assert result["retry_realized_price_cost_bps"]["mean"] == pytest.approx(
        fill.signed_slippage_bps
    )
    assert result[
        "retry_realized_minus_quote_price_cost_bps"
    ]["mean"] == pytest.approx(
        fill.signed_slippage_bps - expected_quote_cost
    )
    explicit_bps = (
        fill.explicit_cost_usd / fill.filled_notional_usd * 10_000.0
    )
    assert result["retry_realized_explicit_cost_bps"]["mean"] == pytest.approx(
        explicit_bps
    )
    assert result[
        "retry_realized_total_execution_burden_bps"
    ]["mean"] == pytest.approx(
        fill.signed_slippage_bps + explicit_bps
    )


def test_retry_telemetry_attributes_max_entry_price_abort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _case(
        monkeypatch,
        tmp_path,
        retry_execution_price=1.06,
    )
    result_transition = case["retry_transition"].buy_result
    assert result_transition is not None
    assert (
        result_transition.outcome
        is FastPaperBuyOutcome.ABORTED_PRICE_ABOVE_MAXIMUM
    )
    assert result_transition.execution is None

    result = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decisions"],
        execution_source_directory=case["sources"],
        pending_buy_retry_source_directory=case["retries"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )
    assert result["pending_buy_retry_outcome_counts"] == {
        "ABORTED_PRICE_ABOVE_MAXIMUM": 1
    }
    assert result["pending_buy_retry_max_entry_price_abort_count"] == 1
    assert result["pending_buy_retry_terminal_count"] == 1
    assert result["retry_to_booked_entry_latency_ms"]["mean"] is None
    assert result["retry_realized_price_cost_bps"]["mean"] is None


def test_retry_telemetry_counts_missing_successor_as_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = _case(monkeypatch, tmp_path, persist_retry=False)
    result = telemetry.summarize_fast_paper_shadow_execution_telemetry(
        manifest=case["manifest"],
        execution_policy=case["policy"],
        binding=case["binding"],
        decision_evidence_directory=case["decisions"],
        execution_source_directory=case["sources"],
        pending_buy_retry_source_directory=case["retries"],
        expected_release_sha=case["manifest"].release_source_sha,
        since_unix_ms=20_000,
        until_unix_ms=21_000,
    )
    assert result["pending_buy_retry_count"] == 1
    assert result["joined_pending_buy_retry_count"] == 0
    assert result["missing_retry_successor_commit_count"] == 1


def test_retry_join_telemetry_authority_firewall_and_cli_surface() -> None:
    source = Path(telemetry.__file__).read_text(encoding="utf-8")
    assert "--pending-buy-retry-source-directory" in source
    assert "reconstruct_fast_paper_shadow_pending_buy_retry" in source
    assert (
        "read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint"
        in source
    )

    for forbidden in (
        "run_fast_paper_shadow_service_pending_buy_retry",
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
