from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    build_fast_paper_shadow_runtime_state,
    produce_fast_paper_shadow_execution_input_source_record,
    read_fast_paper_shadow_execution_input_source_record,
    save_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_runtime_state,
    write_fast_paper_shadow_execution_input_source_record,
)

from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record,
    _runtime_fixture,
    _source,
)


def _buy_case(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    return (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        _source(record, evidence),
    )


def test_execution_source_producer_binds_exact_latest_state_and_round_trips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
    ) = _buy_case(monkeypatch, tmp_path)

    record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
        source_observed_at_unix_ms=20_019,
        risk_day_started_at_unix_ms=0,
    )

    assert record.paper_checkpoint_sequence == checkpoint.sequence
    assert (
        record.paper_checkpoint_payload_sha256
        == checkpoint.payload_sha256
    )
    assert (
        record.shadow_runtime_state_fingerprint_sha256
        == posture.state_fingerprint_sha256
    )

    directory = tmp_path / "execution-inputs"
    directory.mkdir()
    write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )
    restored = read_fast_paper_shadow_execution_input_source_record(
        manifest,
        policy,
        source.decision_evidence,
        directory,
        paper_checkpoint_sequence=checkpoint.sequence,
        paper_checkpoint_payload_sha256=checkpoint.payload_sha256,
        shadow_runtime_state_fingerprint_sha256=(
            posture.state_fingerprint_sha256
        ),
    )
    assert restored == record


def test_execution_source_producer_rejects_stale_durable_pair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
    ) = _buy_case(monkeypatch, tmp_path)

    checkpoint1 = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        checkpoint.state,
        sequence=1,
        created_at_unix_ms=19_001,
    )
    posture1 = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint1,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            policy.policy_fingerprint_sha256
        ),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        posture1,
        created_at_unix_ms=19_001,
    )

    with pytest.raises(ValueError, match="latest|stale|checkpoint"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            source,
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=0,
        )


def test_execution_source_producer_rejects_stale_buy_accounting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
    ) = _buy_case(monkeypatch, tmp_path)
    assert source.risk_context is not None
    stale = replace(
        source,
        risk_context=replace(
            source.risk_context,
            open_position_count=1,
        ),
    )

    with pytest.raises(ValueError, match="accounting|open position"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            stale,
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=0,
        )

    wrong_capital = replace(
        source,
        risk_context=replace(
            source.risk_context,
            trading_capital_usd=19_999.0,
        ),
    )
    with pytest.raises(ValueError, match="capital|starting cash"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            wrong_capital,
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=0,
        )


def test_execution_source_producer_rejects_posture_and_day_start_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="HOLD",
        position=FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    with pytest.raises(ValueError, match="posture|position"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            _source(record, evidence),
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=None,
        )

    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        source,
    ) = _buy_case(monkeypatch, tmp_path / "buy")
    with pytest.raises(ValueError, match="day|future|evaluation"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            source,
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=20_021,
        )


def test_execution_source_producer_rejects_meaningless_non_buy_day_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(
        tmp_path
    )
    record = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        record,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    with pytest.raises(ValueError, match="day|BUY|non-BUY"):
        produce_fast_paper_shadow_execution_input_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            _source(record, evidence),
            source_observed_at_unix_ms=20_019,
            risk_day_started_at_unix_ms=0,
        )


def test_execution_source_producer_has_no_score_network_execution_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_execution_producer.py"
    ).read_text(encoding="utf-8")

    for required in (
        "derive_paper_risk_accounting_facts",
        "fast_paper_shadow_decision_position",
        "build_fast_paper_shadow_execution_input_source_record",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "ScorePolicy",
        "DecisionPolicy",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "aiohttp",
        "ObserverCampaignStore",
        "ObserverMarketStore",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
