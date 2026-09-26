from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION,
    FastPaperShadowBuyAuthoritySourceRecord,
    build_fast_paper_shadow_buy_authority_source_record,
    build_fast_paper_shadow_runtime_state,
    read_fast_paper_shadow_buy_authority_source_record,
    save_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_runtime_state,
    write_fast_paper_shadow_buy_authority_source_record,
)
from shreks_brain.regime import MarketRegime

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _entry, _risk
from test_fast_paper_shadow_executor import _evidence_for, _runtime_fixture


_SOURCE_VERSION = "fast-paper-shadow-buy-authority-fixture-v1"
_SOURCE_FINGERPRINT = "a" * 64


def _fixture(monkeypatch, tmp_path: Path):
    manifest, binding, policy, checkpoint, posture = _runtime_fixture(tmp_path)
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
    return (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        feature,
        evidence,
        _entry(feature),
        _risk(evidence.evaluated_at_unix_ms),
    )


def _build(
    manifest,
    binding,
    policy,
    checkpoint,
    posture,
    evidence,
    entry,
    risk,
    *,
    market_regime: MarketRegime = MarketRegime.NORMAL,
    risk_day_started_at_unix_ms: int = 0,
    source_observed_at_unix_ms: int = 20_019,
):
    return build_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        entry,
        risk,
        market_regime,
        risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
        source_version=_SOURCE_VERSION,
        source_fingerprint_sha256=_SOURCE_FINGERPRINT,
    )


def test_buy_authority_source_binds_exact_flat_buy_state_and_round_trips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        _feature,
        evidence,
        entry,
        risk,
    ) = _fixture(monkeypatch, tmp_path)

    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        entry,
        risk,
    )

    assert type(record) is FastPaperShadowBuyAuthoritySourceRecord
    assert record.schema_name == FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_NAME
    assert (
        record.schema_version
        == FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION
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
    assert (
        record.decision_evidence_fingerprint_sha256
        == evidence.evidence_fingerprint_sha256
    )
    assert record.source_event_id == evidence.source_event_id
    assert record.market_key == evidence.market_key
    assert record.mint == evidence.entry_quote.mint
    assert record.quote_mint == evidence.entry_quote.quote_mint
    assert record.evaluated_at_unix_ms == evidence.evaluated_at_unix_ms
    assert record.risk_day_started_at_unix_ms == 0
    assert record.source_observed_at_unix_ms == 20_019
    assert record.entry_authority == entry
    assert record.risk_context == risk
    assert record.market_regime is MarketRegime.NORMAL
    assert record.source_version == _SOURCE_VERSION
    assert record.source_fingerprint_sha256 == _SOURCE_FINGERPRINT
    assert len(record.record_fingerprint_sha256) == 64

    directory = tmp_path / "buy-authority-sources"
    directory.mkdir(mode=0o700)
    path = write_fast_paper_shadow_buy_authority_source_record(
        record,
        directory,
    )
    restored = read_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        directory,
    )

    assert restored == record
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8").endswith("\n")

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_buy_authority_source_record(record, directory)


def test_buy_authority_source_recomputes_isolated_ledger_risk(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        _feature,
        evidence,
        entry,
        risk,
    ) = _fixture(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="risk|accounting|open position"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            replace(risk, open_position_count=1),
        )

    with pytest.raises(ValueError, match="trading capital|starting cash"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            replace(risk, trading_capital_usd=19_999.0),
        )

    with pytest.raises(ValueError, match="active intent|external"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            replace(
                risk,
                active_intent_keys=frozenset({"external-intent"}),
            ),
        )


def test_buy_authority_source_requires_exact_buy_authority_and_chronology(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        feature,
        evidence,
        entry,
        risk,
    ) = _fixture(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="entry|price|authority"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            replace(
                entry,
                decision_executable_entry_price_quote=0.99,
            ),
            risk,
        )

    with pytest.raises(ValueError, match="source|observation|quote|chronology"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            risk,
            source_observed_at_unix_ms=20_009,
        )

    with pytest.raises(ValueError, match="source|observation|evaluation|future"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            risk,
            source_observed_at_unix_ms=20_021,
        )

    with pytest.raises(ValueError, match="risk day|evaluation"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            entry,
            risk,
            risk_day_started_at_unix_ms=20_021,
        )

    skip = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    with pytest.raises(ValueError, match="BUY|action"):
        _build(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            skip,
            entry,
            risk,
        )


def test_buy_authority_source_fails_closed_after_state_advance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        _feature,
        evidence,
        entry,
        risk,
    ) = _fixture(monkeypatch, tmp_path)
    directory = tmp_path / "buy-authority-sources"
    directory.mkdir()

    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        entry,
        risk,
    )
    write_fast_paper_shadow_buy_authority_source_record(record, directory)

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
        read_fast_paper_shadow_buy_authority_source_record(
            manifest,
            binding,
            policy,
            advanced,
            advanced_posture,
            evidence,
            directory,
        )


def test_buy_authority_source_rejects_tamper_unknown_fields_and_symlink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        _feature,
        evidence,
        entry,
        risk,
    ) = _fixture(monkeypatch, tmp_path)
    directory = tmp_path / "buy-authority-sources"
    directory.mkdir()

    record = _build(
        manifest,
        binding,
        policy,
        checkpoint,
        posture,
        evidence,
        entry,
        risk,
    )
    path = write_fast_paper_shadow_buy_authority_source_record(record, directory)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing|canonical|fingerprint"):
        read_fast_paper_shadow_buy_authority_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            directory,
        )

    path.unlink()
    write_fast_paper_shadow_buy_authority_source_record(record, directory)
    real = path.with_suffix(".real")
    path.rename(real)
    path.symlink_to(real.name)
    with pytest.raises(ValueError, match="symlink|regular"):
        read_fast_paper_shadow_buy_authority_source_record(
            manifest,
            binding,
            policy,
            checkpoint,
            posture,
            evidence,
            directory,
        )


def test_buy_authority_source_has_no_execution_network_scoring_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime.shadow_buy_authority_source as source

    payload = Path(source.__file__).read_text(encoding="utf-8")
    for required in (
        "FastCampaignPaperEntryAuthority",
        "RiskContext",
        "MarketRegime",
        "derive_paper_risk_accounting_facts",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
    ):
        assert required in payload

    for forbidden in (
        "execute_fast_paper_buy",
        "execute_fast_paper_shadow_decision(",
        "produce_fast_paper_shadow_execution_input_source_record(",
        "commit_fast_paper_shadow_transition_atomically",
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
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
