from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.fast_paper_runtime import (
    FastPaperShadowPendingBuyRetryInput,
    FastPaperShadowQuoteUsdEvidence,
    build_fast_paper_shadow_execution_policy,
    build_fast_paper_shadow_pending_buy_retry_source_record,
    write_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_pending_buy_retry_source_record,
)
from shreks_brain.fast_paper_runtime.shadow_provision import (
    provision_fast_paper_shadow,
)
from shreks_brain.fast_paper_runtime.shadow_supervisor import (
    bootstrap_fast_paper_shadow_supervisor,
    run_fast_paper_shadow_supervisor_cycle,
)
from shreks_brain.paper import PaperPositionState

from test_fast_paper_shadow_execution_input import _risk
from test_fast_paper_shadow_first_buy_e2e import (
    _DECISION_AT,
    _PROVISIONED_AT,
    _QUOTE_RATE_USD,
    _runtime_fixture,
)
from test_fast_paper_shadow_supervised_lifecycle_e2e import (
    _evidence_for_sequence,
    _install_decisions,
    _install_feature_feed,
    _publish_quote_usd,
)


def test_fl10_3_restart_reconstructs_pending_buy_open_position_and_idempotency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _service,
        feature,
        _quote_policy,
        execution_policy,
        supervisor_config,
        provision_config,
        authoritative_paper,
        authoritative_bytes,
    ) = _runtime_fixture(tmp_path)

    deferred_policy = build_fast_paper_shadow_execution_policy(
        manifest,
        risk_policy=execution_policy.risk_policy,
        fill_policy=replace(
            execution_policy.fill_policy,
            assumed_latency_ms=100,
        ),
        position_action_policy=execution_policy.position_action_policy,
    )
    write_fast_paper_shadow_execution_policy(
        deferred_policy,
        supervisor_config.execution_config.execution_policy_path,
    )

    _install_feature_feed(
        monkeypatch,
        manifest,
        (feature,),
    )
    _install_decisions(
        monkeypatch,
        manifest,
    )

    provisioned = provision_fast_paper_shadow(
        provision_config,
        clock_unix_ms=lambda: _PROVISIONED_AT,
    )
    assert provisioned.created is True
    before_authoritative = authoritative_paper.read_bytes()

    bootstrap = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )
    bootstrap, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        bootstrap,
        supervisor_config,
        clock_unix_ms=lambda: _DECISION_AT + 20,
    )
    assert produced == 1
    assert committed == 0

    evidence = _evidence_for_sequence(
        supervisor_config.decision_config.evidence_directory,
        1,
    )
    _publish_quote_usd(
        manifest,
        supervisor_config,
        evidence,
    )

    bootstrap, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        bootstrap,
        supervisor_config,
        clock_unix_ms=lambda: _DECISION_AT + 30,
    )
    assert produced == 0
    assert committed == 1

    decision_state = bootstrap.decision_bootstrap.state
    execution = bootstrap.execution_bootstrap
    assert decision_state.cursor is not None
    assert decision_state.cursor.decision_sequence == 1
    assert execution.runtime_state.last_processed_source_sequence == 1
    assert execution.runtime_state.pending_buy is not None
    assert execution.runtime_state.market_positions == ()
    assert execution.checkpoint.sequence == 1
    assert len(execution.checkpoint.state.ledger.positions) == 0
    assert len(execution.checkpoint.state.ledger.processed_intent_keys) == 0

    restarted_pending = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )
    assert restarted_pending.decision_bootstrap.state == decision_state
    assert restarted_pending.execution_bootstrap.checkpoint == (
        execution.checkpoint
    )
    assert restarted_pending.execution_bootstrap.runtime_state == (
        execution.runtime_state
    )

    blocked, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        restarted_pending,
        supervisor_config,
        clock_unix_ms=lambda: _DECISION_AT + 40,
    )
    assert produced == 0
    assert committed == 0
    assert blocked.decision_bootstrap.state == decision_state
    assert blocked.execution_bootstrap.checkpoint == execution.checkpoint
    assert blocked.execution_bootstrap.runtime_state == execution.runtime_state

    retry_at = _DECISION_AT + 200
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=retry_at,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=_DECISION_AT + 150,
        ),
        risk_context=_risk(retry_at),
        quote_usd_evidence=FastPaperShadowQuoteUsdEvidence(
            quote_mint=manifest.quote_mint,
            observed_at_unix_ms=_DECISION_AT + 190,
            quote_to_usd_rate=_QUOTE_RATE_USD,
            source_version="fl10.3-restart-retry-v1",
            source_fingerprint_sha256="e" * 64,
        ),
    )
    retry_record = build_fast_paper_shadow_pending_buy_retry_source_record(
        manifest,
        blocked.execution_bootstrap.binding,
        blocked.execution_bootstrap.execution_policy,
        blocked.execution_bootstrap.checkpoint,
        blocked.execution_bootstrap.runtime_state,
        retry,
        risk_day_started_at_unix_ms=0,
        source_observed_at_unix_ms=_DECISION_AT + 195,
    )
    write_fast_paper_shadow_pending_buy_retry_source_record(
        retry_record,
        supervisor_config.pending_buy_retry_source_directory,
    )

    restarted_retry = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )
    assert restarted_retry.execution_bootstrap.runtime_state.pending_buy == (
        execution.runtime_state.pending_buy
    )

    recovered, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        restarted_retry,
        supervisor_config,
        clock_unix_ms=lambda: _DECISION_AT + 210,
    )
    assert produced == 0
    assert committed == 1

    recovered_execution = recovered.execution_bootstrap
    assert recovered.decision_bootstrap.state == decision_state
    assert recovered_execution.runtime_state.last_processed_source_sequence == 1
    assert recovered_execution.runtime_state.pending_buy is None
    assert len(recovered_execution.runtime_state.market_positions) == 1
    assert recovered_execution.checkpoint.sequence == 2

    ledger = recovered_execution.checkpoint.state.ledger
    assert len(ledger.positions) == 1
    position = ledger.positions[0]
    assert position.state is PaperPositionState.OPEN
    assert position.buy_fill_count == 1
    assert position.sell_fill_count == 0
    assert len(ledger.processed_intent_keys) == 1

    restarted_open = bootstrap_fast_paper_shadow_supervisor(
        supervisor_config
    )
    assert restarted_open.decision_bootstrap.state == decision_state
    assert restarted_open.execution_bootstrap.checkpoint == (
        recovered_execution.checkpoint
    )
    assert restarted_open.execution_bootstrap.runtime_state == (
        recovered_execution.runtime_state
    )
    assert len(
        restarted_open.execution_bootstrap.runtime_state.market_positions
    ) == 1

    stable, produced, committed = run_fast_paper_shadow_supervisor_cycle(
        restarted_open,
        supervisor_config,
        clock_unix_ms=lambda: _DECISION_AT + 220,
    )
    assert produced == 0
    assert committed == 0
    assert stable.execution_bootstrap.checkpoint == (
        recovered_execution.checkpoint
    )
    assert stable.execution_bootstrap.runtime_state == (
        recovered_execution.runtime_state
    )

    stable_ledger = stable.execution_bootstrap.checkpoint.state.ledger
    assert stable_ledger == ledger
    assert len(stable_ledger.positions) == 1
    assert stable_ledger.positions[0].buy_fill_count == 1
    assert len(stable_ledger.processed_intent_keys) == 1

    assert authoritative_paper.read_bytes() == before_authoritative
    assert before_authoritative == authoritative_bytes
    assert manifest.runtime_mode == "PAPER"
