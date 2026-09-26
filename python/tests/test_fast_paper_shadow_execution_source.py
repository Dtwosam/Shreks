from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_VERSION,
    FastPaperShadowExecutionInput,
    build_fast_paper_shadow_execution_input_source_record,
    read_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_execution_input_source_record,
)
from shreks_brain.regime import MarketRegime

from test_fast_paper_shadow_execution_input import (
    _entry,
    _execution_policy,
    _risk,
    _shadow_evidence,
    _usd,
)


_CHECKPOINT_SEQUENCE = 7
_CHECKPOINT_SHA256 = "c" * 64
_RUNTIME_STATE_SHA256 = "d" * 64


def _build(manifest, policy, source, *, source_observed_at_unix_ms):
    return build_fast_paper_shadow_execution_input_source_record(
        manifest,
        policy,
        source,
        paper_checkpoint_sequence=_CHECKPOINT_SEQUENCE,
        paper_checkpoint_payload_sha256=_CHECKPOINT_SHA256,
        shadow_runtime_state_fingerprint_sha256=_RUNTIME_STATE_SHA256,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
    )


def _read(manifest, policy, evidence, directory, **changes):
    values = {
        "paper_checkpoint_sequence": _CHECKPOINT_SEQUENCE,
        "paper_checkpoint_payload_sha256": _CHECKPOINT_SHA256,
        "shadow_runtime_state_fingerprint_sha256": _RUNTIME_STATE_SHA256,
    }
    values.update(changes)
    return read_fast_paper_shadow_execution_input_source_record(
        manifest,
        policy,
        evidence,
        directory,
        **values,
    )


def _buy_source(monkeypatch, tmp_path: Path):
    manifest, record, evidence = _shadow_evidence(
        monkeypatch,
        tmp_path,
        action="BUY",
    )
    policy = _execution_policy(manifest)
    source = FastPaperShadowExecutionInput(
        decision_evidence=evidence,
        entry_authority=_entry(record),
        risk_context=_risk(evidence.evaluated_at_unix_ms),
        market_regime=MarketRegime.NORMAL,
        quote_usd_evidence=_usd(record),
    )
    return manifest, policy, evidence, source


def test_execution_input_source_is_exact_write_once_and_round_trips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, policy, evidence, source = _buy_source(
        monkeypatch,
        tmp_path,
    )
    record = _build(
        manifest,
        policy,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms - 1,
    )

    assert (
        record.schema_name
        == FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME
    )
    assert (
        record.schema_version
        == FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_VERSION
    )
    assert (
        record.manifest_fingerprint_sha256
        == manifest.manifest_fingerprint_sha256
    )
    assert (
        record.execution_policy_fingerprint_sha256
        == policy.policy_fingerprint_sha256
    )
    assert (
        record.decision_evidence_fingerprint_sha256
        == evidence.evidence_fingerprint_sha256
    )
    assert record.paper_checkpoint_sequence == _CHECKPOINT_SEQUENCE
    assert record.paper_checkpoint_payload_sha256 == _CHECKPOINT_SHA256
    assert (
        record.shadow_runtime_state_fingerprint_sha256
        == _RUNTIME_STATE_SHA256
    )
    assert len(record.record_fingerprint_sha256) == 64

    directory = tmp_path / "execution-inputs"
    directory.mkdir()
    path = write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )
    assert path.name == f"{evidence.evidence_fingerprint_sha256}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    restored = _read(
        manifest,
        policy,
        evidence,
        directory,
    )
    assert restored == record
    assert restored.execution_input == source

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_execution_input_source_record(
            record,
            directory,
        )


def test_execution_input_source_rejects_future_source_and_binding_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, policy, evidence, source = _buy_source(
        monkeypatch,
        tmp_path,
    )

    with pytest.raises(ValueError, match="future|observation|evaluation"):
        _build(
            manifest,
            policy,
            source,
            source_observed_at_unix_ms=evidence.evaluated_at_unix_ms + 1,
        )

    directory = tmp_path / "execution-inputs"
    directory.mkdir()
    record = _build(
        manifest,
        policy,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )

    with pytest.raises(ValueError, match="policy|fingerprint"):
        _read(
            manifest,
            replace(
                policy,
                policy_fingerprint_sha256="f" * 64,
            ),
            evidence,
            directory,
        )

    drifted_evidence = replace(
        evidence,
        decision_latency_ns=evidence.decision_latency_ns + 1,
    )
    with pytest.raises(ValueError, match="decision|fingerprint|source"):
        _read(
            manifest,
            policy,
            drifted_evidence,
            directory,
        )


def test_execution_input_source_rejects_stale_checkpoint_or_posture_binding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, policy, evidence, source = _buy_source(
        monkeypatch,
        tmp_path,
    )
    record = _build(
        manifest,
        policy,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    directory = tmp_path / "execution-inputs"
    directory.mkdir()
    write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )

    with pytest.raises(ValueError, match="checkpoint|sequence"):
        _read(
            manifest,
            policy,
            evidence,
            directory,
            paper_checkpoint_sequence=_CHECKPOINT_SEQUENCE + 1,
        )
    with pytest.raises(ValueError, match="checkpoint|fingerprint"):
        _read(
            manifest,
            policy,
            evidence,
            directory,
            paper_checkpoint_payload_sha256="e" * 64,
        )
    with pytest.raises(ValueError, match="runtime-state|fingerprint"):
        _read(
            manifest,
            policy,
            evidence,
            directory,
            shadow_runtime_state_fingerprint_sha256="f" * 64,
        )


def test_execution_input_source_rejects_tamper_unknown_fields_and_symlink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, policy, evidence, source = _buy_source(
        monkeypatch,
        tmp_path,
    )
    record = _build(
        manifest,
        policy,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    directory = tmp_path / "execution-inputs"
    directory.mkdir()
    path = write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )

    document = json.loads(path.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing|canonical"):
        _read(
            manifest,
            policy,
            evidence,
            directory,
        )

    path.unlink()
    write_fast_paper_shadow_execution_input_source_record(
        record,
        directory,
    )
    target = tmp_path / "target.json"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symlink|regular"):
        _read(
            manifest,
            policy,
            evidence,
            directory,
        )


def test_execution_input_source_supports_action_compatible_non_buy_records(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for action in ("SKIP", "HOLD", "REDUCE", "SELL"):
        case = tmp_path / action.lower()
        case.mkdir()
        manifest, record, evidence = _shadow_evidence(
            monkeypatch,
            case,
            action=action,
        )
        policy = _execution_policy(manifest)
        source = FastPaperShadowExecutionInput(
            decision_evidence=evidence,
            entry_authority=None,
            risk_context=None,
            market_regime=None,
            quote_usd_evidence=(
                None
                if action == "SKIP"
                else _usd(record)
            ),
        )
        built = _build(
            manifest,
            policy,
            source,
            source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        )
        directory = case / "execution-inputs"
        directory.mkdir()
        write_fast_paper_shadow_execution_input_source_record(
            built,
            directory,
        )
        restored = _read(
            manifest,
            policy,
            evidence,
            directory,
        )
        assert restored.execution_input == source


def test_execution_input_source_has_no_score_network_execution_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_execution_source.py"
    ).read_text(encoding="utf-8")

    for required in (
        "FastPaperShadowExecutionInput",
        "FastCampaignPaperEntryAuthority",
        "RiskContext",
        "MarketRegime",
        "FastPaperShadowQuoteUsdEvidence",
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
        "sqlite3",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
