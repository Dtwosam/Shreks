from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION,
    FastPaperShadowPendingBuyRetryInput,
    FastPaperShadowPendingBuyRetrySourceRecord,
    build_fast_paper_shadow_pending_buy_retry_source_record,
    build_fast_paper_shadow_runtime_state,
    read_fast_paper_shadow_pending_buy_retry_source_record,
    save_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_runtime_state,
    write_fast_paper_shadow_pending_buy_retry_source_record,
)
from shreks_brain.fast_paper_runtime import execute_fast_paper_shadow_decision

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _risk, _usd
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _runtime_fixture,
    _source,
)


def _pending_fixture(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(tmp_path)
    feature = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action="BUY",
        position=__import__(
            "shreks_brain.fast_campaign",
            fromlist=["FastCampaignDecisionPosition"],
        ).FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    deferred = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint,
        posture,
        _source(feature, evidence),
    )
    checkpoint, posture = _persist(
        manifest,
        binding,
        deferred,
        sequence=1,
        created_at=20_020,
    )
    assert checkpoint.state.pending_buy is not None
    assert posture.pending_buy is not None

    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=20_200,
        quote=replace(
            evidence.entry_quote,
            observed_at_unix_ms=20_150,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=_risk(20_200),
        quote_usd_evidence=_usd(feature, observed_at=20_190),
    )
    return manifest, binding, policy, checkpoint, posture, retry


def _build(
    manifest,
    binding,
    policy,
    checkpoint,
    posture,
    retry,
    *,
    risk_day_started_at_unix_ms: int = 0,
    source_observed_at_unix_ms: int = 20_195,
):
    return build_fast_paper_shadow_pending_buy_retry_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        retry,
        risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
    )


def test_pending_buy_retry_source_binds_exact_pending_state_and_round_trips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture, retry = _pending_fixture(
        monkeypatch,
        tmp_path,
    )
    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        retry,
    )

    assert type(record) is FastPaperShadowPendingBuyRetrySourceRecord
    assert (
        record.schema_name
        == FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME
    )
    assert (
        record.schema_version
        == FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION
    )
    assert (
        record.manifest_fingerprint_sha256
        == manifest.manifest_fingerprint_sha256
    )
    assert (
        record.binding_fingerprint_sha256
        == binding.binding_fingerprint_sha256
    )
    assert (
        record.execution_policy_fingerprint_sha256
        == policy.policy_fingerprint_sha256
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
    assert record.pending_source_event_id == posture.pending_buy.source_event_id
    assert record.pending_market_key == posture.pending_buy.market_key
    assert record.pending_mint == posture.pending_buy.mint
    assert (
        record.pending_target_exposure_fraction
        == posture.pending_buy.target_exposure_fraction
    )
    assert record.risk_day_started_at_unix_ms == 0
    assert record.source_observed_at_unix_ms == 20_195
    assert record.retry_input == retry
    assert len(record.record_fingerprint_sha256) == 64

    directory = tmp_path / "retry-sources"
    directory.mkdir(mode=0o700)
    path = write_fast_paper_shadow_pending_buy_retry_source_record(
        record,
        directory,
    )
    restored = read_fast_paper_shadow_pending_buy_retry_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        directory,
    )

    assert restored == record
    assert restored.retry_input == retry
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8").endswith("\n")

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_pending_buy_retry_source_record(
            record,
            directory,
        )


def test_pending_buy_retry_source_recomputes_ledger_risk_accounting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture, retry = _pending_fixture(
        monkeypatch,
        tmp_path,
    )
    drifted = replace(
        retry,
        risk_context=replace(
            retry.risk_context,
            open_position_count=1,
        ),
    )
    with pytest.raises(ValueError, match="risk|accounting|open position"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            drifted,
        )

    external_intent = replace(
        retry,
        risk_context=replace(
            retry.risk_context,
            active_intent_keys=frozenset({"external-intent"}),
        ),
    )
    with pytest.raises(ValueError, match="active intent|external"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            external_intent,
        )


def test_pending_buy_retry_source_requires_truthful_source_chronology(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture, retry = _pending_fixture(
        monkeypatch,
        tmp_path,
    )

    with pytest.raises(ValueError, match="source|observation|quote"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            retry,
            source_observed_at_unix_ms=20_180,
        )
    with pytest.raises(ValueError, match="source|observation|evaluation|future"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            retry,
            source_observed_at_unix_ms=20_201,
        )
    with pytest.raises(ValueError, match="risk day|evaluation"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            retry,
            risk_day_started_at_unix_ms=20_201,
        )


def test_pending_buy_retry_source_fails_closed_after_state_advance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture, retry = _pending_fixture(
        monkeypatch,
        tmp_path,
    )
    directory = tmp_path / "retry-sources"
    directory.mkdir()
    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        retry,
    )
    write_fast_paper_shadow_pending_buy_retry_source_record(record, directory)

    advanced = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        checkpoint.state,
        sequence=checkpoint.sequence + 1,
        created_at_unix_ms=checkpoint.created_at_unix_ms + 1,
    )
    advanced_posture = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        advanced,
        market_positions=posture.market_positions,
        execution_policy_fingerprint_sha256=(
            posture.execution_policy_fingerprint_sha256
        ),
        pending_buy=posture.pending_buy,
        last_processed_source_sequence=(
            posture.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            posture.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            posture.last_processed_decision_evidence_fingerprint_sha256
        ),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        advanced_posture,
        created_at_unix_ms=advanced.created_at_unix_ms,
    )

    with pytest.raises(ValueError, match="source|record|state|latest|checkpoint"):
        read_fast_paper_shadow_pending_buy_retry_source_record(
            manifest,
            binding,
            policy,
            advanced,
            advanced_posture,
            directory,
        )


def test_pending_buy_retry_source_rejects_tamper_unknown_fields_and_symlink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint, posture, retry = _pending_fixture(
        monkeypatch,
        tmp_path,
    )
    directory = tmp_path / "retry-sources"
    directory.mkdir()
    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        retry,
    )
    path = write_fast_paper_shadow_pending_buy_retry_source_record(
        record,
        directory,
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing|canonical|fingerprint"):
        read_fast_paper_shadow_pending_buy_retry_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            directory,
        )

    path.unlink()
    write_fast_paper_shadow_pending_buy_retry_source_record(record, directory)
    real = path.with_suffix(".real")
    path.rename(real)
    path.symlink_to(real.name)
    with pytest.raises(ValueError, match="symlink|regular"):
        read_fast_paper_shadow_pending_buy_retry_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            directory,
        )


def test_pending_buy_retry_source_has_no_execution_network_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime.shadow_pending_buy_retry_source as source

    payload = Path(source.__file__).read_text(encoding="utf-8")
    for required in (
        "FastPaperShadowPendingBuyRetryInput",
        "derive_paper_risk_accounting_facts",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
    ):
        assert required in payload

    for forbidden in (
        "execute_fast_paper_buy",
        "retry_fast_paper_shadow_pending_buy(",
        "commit_fast_paper_shadow_transition_atomically",
        "shreks_brain.scoring",
        "score_candidate",
        "requests.",
        "httpx",
        "aiohttp",
        "sqlite3",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in payload
