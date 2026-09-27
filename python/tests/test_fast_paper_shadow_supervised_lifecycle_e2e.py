from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
import shreks_brain.fast_paper_runtime.shadow_open_quote_writer as open_quote_writer
import shreks_brain.fast_paper_runtime.shadow_service as shadow_service
from shreks_brain.fast_campaign import (
    FastCampaignDecisionResult,
    FastCampaignDecisionResults,
)
from shreks_brain.fast_campaign.models import FastCampaignActionCandidate
from shreks_brain.fast_paper_runtime import (
    FastPaperRuntimeCursor,
    FastPaperShadowQuoteUsdEvidence,
    build_fast_paper_runtime_state,
    build_fast_paper_shadow_quote_usd_source_record,
    write_fast_paper_shadow_quote_usd_source_record,
)
from shreks_brain.fast_paper_runtime.shadow import (
    read_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_provision import (
    provision_fast_paper_shadow,
)
from shreks_brain.fast_paper_runtime.shadow_supervisor import (
    bootstrap_fast_paper_shadow_supervisor,
    run_fast_paper_shadow_supervisor_cycle,
)
from shreks_brain.paper import PaperPositionState

from test_fast_paper_shadow_decision import _result_fingerprint
from test_fast_paper_shadow_executor import _record_at
from test_fast_paper_shadow_first_buy_e2e import (
    _BASE_RAW,
    _DECISION_AT,
    _ENTRY_QUOTE_RAW,
    _HORIZON_MS,
    _QUOTE_RATE_USD,
    _runtime_fixture,
)


_REDUCED_RAW = _BASE_RAW // 2
_ACTIONS = {
    1: ("BUY", 0.0, 0.5),
    2: ("HOLD", 0.5, 0.5),
    3: ("REDUCE", 0.5, 0.25),
    4: ("SELL", 0.25, 0.0),
}


def _action_results(manifest, request) -> FastCampaignDecisionResults:
    action, current, target = _ACTIONS[request.source_sequence]
    selected_horizon = None if action == "SELL" else _HORIZON_MS
    reason = f"{action}_SELECTED"
    selected_reward = 0.0 if action == "SELL" else 100.0
    selected_risk = 0.0 if action == "SELL" else 25.0
    selected_cost = (
        150.0
        if action == "REDUCE"
        else 200.0
        if action == "SELL"
        else 0.0
    )
    selected_value = 0.0 if action == "SELL" else 20.0
    candidate_cost = (
        37.5
        if action == "REDUCE"
        else 100.0
        if action == "SELL"
        else 0.0
    )

    decision = FastCampaignDecisionResult(
        source_event_id=request.source_event_id,
        market_key=request.market_key,
        source_sequence=request.source_sequence,
        as_of_unix_ms=request.as_of_unix_ms,
        policy_version=manifest.action_policy.version,
        action=action,
        reason=reason,
        selected_horizon_ms=selected_horizon,
        current_exposure_fraction=current,
        target_exposure_fraction=target,
        selected_reward_bps=selected_reward,
        selected_risk_bps=selected_risk,
        selected_execution_cost_bps=selected_cost,
        selected_value_bps=selected_value,
        horizon_evidence=(),
        candidates=(
            FastCampaignActionCandidate(
                action=action,
                horizon_ms=selected_horizon,
                target_exposure_fraction=target,
                reward_bps=selected_reward,
                risk_bps=selected_risk,
                execution_cost_penalty_bps=candidate_cost,
                comparison_value_bps=selected_value,
                eligible=True,
            ),
        ),
    )
    return FastCampaignDecisionResults(
        schema_name="shreks.fast_campaign_decision_results",
        schema_version=1,
        champion_version=manifest.champion_version,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        decisions=(decision,),
        batch_fingerprint_sha256=_result_fingerprint(
            manifest,
            decision,
        ),
    )


def _cursor_for(record) -> FastPaperRuntimeCursor:
    return FastPaperRuntimeCursor(
        decision_sequence=record.decision_sequence,
        decision_signature=record.decision_signature,
        decision_ordinal=record.decision_ordinal,
        decision_observed_at_unix_ms=record.decision_observed_at_unix_ms,
    )


def _install_feature_feed(
    monkeypatch,
    manifest,
    records,
) -> None:
    by_sequence = {
        record.decision_sequence: record for record in records
    }

    def feed(_manifest, state, *, maximum_decisions):
        assert (
            _manifest.manifest_fingerprint_sha256
            == manifest.manifest_fingerprint_sha256
        )
        assert maximum_decisions == 1
        current_sequence = (
            0
            if state.cursor is None
            else state.cursor.decision_sequence
        )
        next_record = by_sequence.get(current_sequence + 1)
        if next_record is None:
            return SimpleNamespace(
                records=(),
                next_state=state,
            )
        return SimpleNamespace(
            records=(next_record,),
            next_state=build_fast_paper_runtime_state(
                _manifest,
                cursor=_cursor_for(next_record),
            ),
        )

    monkeypatch.setattr(
        shadow_service,
        "fetch_fast_paper_runtime_feature_batch",
        feed,
    )
    monkeypatch.setattr(
        open_quote_writer,
        "fetch_fast_paper_runtime_feature_batch",
        feed,
    )


def _install_decisions(monkeypatch, manifest) -> None:
    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _action_results(manifest, batch.decisions[0])
        ),
    )
    tick = [1_000]

    def monotonic_ns() -> int:
        tick[0] += 250
        return tick[0]

    monkeypatch.setattr(
        shadow.time,
        "monotonic_ns",
        monotonic_ns,
    )


def _insert_open_quotes(
    database_path: Path,
    *,
    service,
    manifest,
    records,
) -> None:
    connection = sqlite3.connect(database_path)
    try:
        next_id = 100
        for record, full_exit_raw, reduction_raw in (
            (records[1], _BASE_RAW, _REDUCED_RAW),
            (records[2], _BASE_RAW, _REDUCED_RAW),
            (records[3], _REDUCED_RAW, None),
        ):
            entry_at = record.decision_observed_at_unix_ms + 10
            exit_at = record.decision_observed_at_unix_ms + 15
            connection.execute(
                """
                INSERT INTO paper_quote_snapshots
                    (id, candidate_id, purpose, provider,
                     probe_policy_version, input_mint, output_mint,
                     taker, input_amount, output_amount,
                     minimum_output_amount, slippage_bps,
                     route_available, price_impact_pct,
                     route_labels_json, quoted_at_unix_ms)
                VALUES
                    (?, 7, 'entry', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     1, '0.2', '["route-lifecycle"]', ?)
                """,
                (
                    next_id,
                    manifest.quote_provider,
                    service.probe_policy_version,
                    record.quote_mint,
                    record.mint,
                    service.taker,
                    str(_ENTRY_QUOTE_RAW),
                    str(_BASE_RAW),
                    str(_BASE_RAW),
                    service.slippage_bps,
                    entry_at,
                ),
            )
            next_id += 1

            full_output_raw = full_exit_raw * 1_000
            connection.execute(
                """
                INSERT INTO paper_quote_snapshots
                    (id, candidate_id, purpose, provider,
                     probe_policy_version, input_mint, output_mint,
                     taker, input_amount, output_amount,
                     minimum_output_amount, slippage_bps,
                     route_available, price_impact_pct,
                     route_labels_json, quoted_at_unix_ms)
                VALUES
                    (?, 7, 'exit', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     1, '0.2', '["route-lifecycle"]', ?)
                """,
                (
                    next_id,
                    manifest.quote_provider,
                    service.probe_policy_version,
                    record.mint,
                    record.quote_mint,
                    service.taker,
                    str(full_exit_raw),
                    str(full_output_raw),
                    str(full_output_raw),
                    service.slippage_bps,
                    exit_at,
                ),
            )
            next_id += 1

            if reduction_raw is not None:
                reduction_output_raw = reduction_raw * 1_000
                connection.execute(
                    """
                    INSERT INTO paper_quote_snapshots
                        (id, candidate_id, purpose, provider,
                         probe_policy_version, input_mint, output_mint,
                         taker, input_amount, output_amount,
                         minimum_output_amount, slippage_bps,
                         route_available, price_impact_pct,
                         route_labels_json, quoted_at_unix_ms)
                    VALUES
                        (?, 7, 'exit', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         1, '0.2', '["route-lifecycle-reduce"]', ?)
                    """,
                    (
                        next_id,
                        manifest.quote_provider,
                        service.probe_policy_version,
                        record.mint,
                        record.quote_mint,
                        service.taker,
                        str(reduction_raw),
                        str(reduction_output_raw),
                        str(reduction_output_raw),
                        service.slippage_bps,
                        exit_at + 1,
                    ),
                )
                next_id += 1
        connection.commit()
    finally:
        connection.close()


def _evidence_for_sequence(directory: Path, sequence: int):
    matches = []
    for path in sorted(directory.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        if evidence.source_sequence == sequence:
            matches.append(evidence)
    assert len(matches) == 1
    return matches[0]


def _publish_quote_usd(manifest, config, evidence) -> None:
    marker = format(evidence.source_sequence, "x")
    quote_usd = FastPaperShadowQuoteUsdEvidence(
        quote_mint=manifest.quote_mint,
        observed_at_unix_ms=evidence.evaluated_at_unix_ms - 1,
        quote_to_usd_rate=_QUOTE_RATE_USD,
        source_version=(
            f"supervised-lifecycle-e2e-{evidence.source_sequence}"
        ),
        source_fingerprint_sha256=marker * 64,
    )
    record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        quote_usd,
    )
    write_fast_paper_shadow_quote_usd_source_record(
        record,
        config.quote_usd_source_directory,
    )


def _run_action(
    bootstrap,
    *,
    manifest,
    config,
    sequence: int,
    decision_at: int,
    execution_at: int,
):
    bootstrap, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: decision_at,
    )
    assert produced == 1
    assert committed == 0

    evidence = _evidence_for_sequence(
        config.decision_config.evidence_directory,
        sequence,
    )
    _publish_quote_usd(
        manifest,
        config,
        evidence,
    )

    bootstrap, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: execution_at,
    )
    assert produced == 0
    assert committed == 1
    return bootstrap, evidence


def test_supervised_buy_hold_reduce_restart_sell_lifecycle_end_to_end(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        service,
        first_feature,
        _quote_policy,
        _execution_policy,
        supervisor_config,
        provision_config,
        authoritative_paper,
        authoritative_bytes,
    ) = _runtime_fixture(tmp_path)

    records = (
        first_feature,
        _record_at(
            first_feature,
            signature="supervised-lifecycle-hold",
            sequence=2,
            at=_DECISION_AT + 300,
        ),
        _record_at(
            first_feature,
            signature="supervised-lifecycle-reduce",
            sequence=3,
            at=_DECISION_AT + 600,
        ),
        _record_at(
            first_feature,
            signature="supervised-lifecycle-sell",
            sequence=4,
            at=_DECISION_AT + 900,
        ),
    )
    _insert_open_quotes(
        Path(manifest.observer_database_path),
        service=service,
        manifest=manifest,
        records=records,
    )
    _install_feature_feed(
        monkeypatch,
        manifest,
        records,
    )
    _install_decisions(
        monkeypatch,
        manifest,
    )

    provisioned = provision_fast_paper_shadow(
        provision_config,
        clock_unix_ms=lambda: _DECISION_AT - 1_000,
    )
    assert provisioned.created is True
    before_authoritative = authoritative_paper.read_bytes()

    bootstrap = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )

    bootstrap, buy = _run_action(
        bootstrap,
        manifest=manifest,
        config=supervisor_config,
        sequence=1,
        decision_at=_DECISION_AT + 100,
        execution_at=_DECISION_AT + 350,
    )
    assert buy.decision.action == "BUY"
    assert len(bootstrap.execution_bootstrap.runtime_state.market_positions) == 1
    bought_mapping = (
        bootstrap.execution_bootstrap.runtime_state.market_positions[0]
    )
    assert bought_mapping.current_exposure_fraction == pytest.approx(0.5)
    assert bought_mapping.current_base_quantity_raw == _BASE_RAW

    bootstrap, hold = _run_action(
        bootstrap,
        manifest=manifest,
        config=supervisor_config,
        sequence=2,
        decision_at=_DECISION_AT + 400,
        execution_at=_DECISION_AT + 650,
    )
    assert hold.decision.action == "HOLD"
    held_mapping = (
        bootstrap.execution_bootstrap.runtime_state.market_positions[0]
    )
    assert held_mapping.current_exposure_fraction == pytest.approx(0.5)
    assert held_mapping.current_base_quantity_raw == _BASE_RAW

    bootstrap, reduce = _run_action(
        bootstrap,
        manifest=manifest,
        config=supervisor_config,
        sequence=3,
        decision_at=_DECISION_AT + 700,
        execution_at=_DECISION_AT + 950,
    )
    assert reduce.decision.action == "REDUCE"
    assert len(reduce.reduction_quotes) == 1
    assert (
        reduce.reduction_quotes[0].quote.input_amount_raw
        == _REDUCED_RAW
    )
    reduced_mapping = (
        bootstrap.execution_bootstrap.runtime_state.market_positions[0]
    )
    assert reduced_mapping.current_exposure_fraction == pytest.approx(0.25)
    assert reduced_mapping.current_base_quantity_raw == _REDUCED_RAW

    restarted = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )
    assert restarted.execution_bootstrap.checkpoint == (
        bootstrap.execution_bootstrap.checkpoint
    )
    assert restarted.execution_bootstrap.runtime_state == (
        bootstrap.execution_bootstrap.runtime_state
    )
    assert len(restarted.execution_bootstrap.runtime_state.market_positions) == 1
    restarted_mapping = (
        restarted.execution_bootstrap.runtime_state.market_positions[0]
    )
    assert restarted_mapping.current_exposure_fraction == pytest.approx(0.25)
    assert restarted_mapping.current_base_quantity_raw == _REDUCED_RAW

    bootstrap, sell = _run_action(
        restarted,
        manifest=manifest,
        config=supervisor_config,
        sequence=4,
        decision_at=_DECISION_AT + 1_000,
        execution_at=_DECISION_AT + 1_100,
    )
    assert sell.decision.action == "SELL"
    assert sell.position.current_exposure_fraction == pytest.approx(0.25)
    assert sell.exit_quote.input_amount_raw == _REDUCED_RAW

    execution = bootstrap.execution_bootstrap
    assert execution.runtime_state.last_processed_source_sequence == 4
    assert execution.runtime_state.market_positions == ()
    assert execution.runtime_state.pending_buy is None
    assert execution.checkpoint.sequence == 4

    ledger = execution.checkpoint.state.ledger
    assert len(ledger.positions) == 1
    position = ledger.positions[0]
    assert position.state is PaperPositionState.CLOSED
    assert position.buy_fill_count == 1
    assert position.sell_fill_count == 2
    assert len(ledger.processed_intent_keys) == 3

    assert authoritative_paper.read_bytes() == before_authoritative
    assert before_authoritative == authoritative_bytes
    assert manifest.runtime_mode == "PAPER"
