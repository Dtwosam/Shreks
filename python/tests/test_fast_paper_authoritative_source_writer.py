from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.authoritative_source_writer as writer
from shreks_brain.fast_paper import FastPaperBuyOutcome
from shreks_brain.fast_paper_runtime.authoritative_service_execution import (
    run_fast_paper_authoritative_service_execution,
)
from shreks_brain.fast_paper_runtime.codec import build_fast_paper_runtime_state
from shreks_brain.fast_paper_runtime.shadow import (
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_buy_writer_policy import (
    build_fast_paper_shadow_buy_writer_policy,
)
from shreks_brain.fast_paper_runtime.shadow_quote_usd_source import (
    read_fast_paper_shadow_quote_usd_source_record,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceBootstrap,
)
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_fast_paper_authoritative_file_runtime import (
    _buy_source,
    _fixture,
)
from test_fast_paper_shadow_buy_authority_evidence_adapter import (
    _execution_policy as _economics_policy,
    _market_policy,
    _regime_policy,
    _regime_read_policy,
    _safety_policy,
    _safety_probe,
)
from test_fast_paper_shadow_buy_authority_writer import _service_policy
from test_fast_paper_shadow_buy_writer_supervisor_policy import _quote_policy
from test_fast_paper_shadow_decision import _executable, _record


def _writer_policy(manifest, tmp_path: Path):
    service = _service_policy(manifest)
    quote_policy = _quote_policy(manifest)
    operator = tmp_path / "operator-risk-control.json"
    initialize_operator_risk_control_state(
        operator,
        observed_at_unix_ms=0,
    )
    authority_binary = _executable(
        tmp_path / "shreks-fast-entry-authority"
    )
    return build_fast_paper_shadow_buy_writer_policy(
        market_read_policy=_market_policy(),
        regime_read_policy=_regime_read_policy(manifest, quote_policy),
        regime_policy=_regime_policy(),
        safety_policy=_safety_policy(),
        safety_probe_identity=_safety_probe(manifest, quote_policy),
        execution_economics_policies=(
            _economics_policy(_record()),
        ),
        operator_risk_control_path=operator,
        entry_authority_binary_path=authority_binary,
        entry_authority_binary_sha256=hashlib.sha256(
            authority_binary.read_bytes()
        ).hexdigest(),
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )


def _decision_bootstrap(manifest):
    return FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=_service_policy(manifest),
        state=build_fast_paper_runtime_state(
            manifest,
            cursor=None,
        ),
    )


def test_authoritative_source_writer_cycle_orders_open_usd_buy_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _handoff,
        execution_bootstrap,
        config,
        _fixture_policy,
    ) = _fixture(tmp_path)
    decision = _decision_bootstrap(manifest)
    policy = _writer_policy(manifest, tmp_path / "writer")
    order: list[str] = []

    monkeypatch.setattr(
        writer,
        "run_fast_paper_authoritative_open_quote_writer_cycle",
        lambda *_args, **_kwargs: order.append("open") or 1,
    )
    monkeypatch.setattr(
        writer,
        "run_fast_paper_authoritative_quote_usd_writer_cycle",
        lambda *_args, **_kwargs: order.append("usd") or 1,
    )
    monkeypatch.setattr(
        writer,
        "run_fast_paper_authoritative_buy_authority_writer_cycle",
        lambda *_args, **_kwargs: order.append("buy") or 1,
    )
    monkeypatch.setattr(
        writer,
        "run_fast_paper_authoritative_pending_buy_retry_writer_cycle",
        lambda *_args, **_kwargs: order.append("retry") or 1,
    )

    written = writer.run_fast_paper_authoritative_source_writer_cycle(
        decision,
        execution_bootstrap,
        policy,
        decision_evidence_directory=config.decision_config.evidence_directory,
        buy_authority_source_directory=config.buy_authority_source_directory,
        quote_usd_source_directory=config.quote_usd_source_directory,
        reduction_source_directory=config.reduction_source_directory,
        pending_buy_retry_source_directory=(
            config.pending_buy_retry_source_directory
        ),
        clock_unix_ms=lambda: 123_456,
    )

    assert written == 4
    assert order == ["open", "usd", "buy", "retry"]


def test_quote_usd_writer_uses_exact_persisted_market_row_and_replays(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _handoff,
        execution_bootstrap,
        config,
        _fixture_policy,
    ) = _fixture(tmp_path)
    decision = _decision_bootstrap(manifest)
    policy = _writer_policy(manifest, tmp_path / "writer")
    _feature, evidence, _source = _buy_source(
        monkeypatch,
        manifest,
        execution_bootstrap,
        signature="authoritative-usd-writer",
    )
    evidence_path = (
        config.decision_config.evidence_directory
        / "shadow-00000000000000000001.json"
    )
    write_fast_paper_shadow_decision_evidence(
        evidence,
        evidence_path,
    )

    observed_at = evidence.evaluated_at_unix_ms - 1
    current = SimpleNamespace(
        row_id=17,
        source="dexscreener",
        venue="pump_fun_bonding_curve",
        observed_at_unix_ms=observed_at,
    )
    window = SimpleNamespace(current=current)
    usd_evidence = SimpleNamespace(
        market_row_id=17,
        candidate_id=7,
        observed_at_unix_ms=observed_at,
        source=current.source,
        venue=current.venue,
        pair_address="pair-17",
        base_mint=evidence.feature_record.mint,
        quote_mint=manifest.quote_mint,
        base_price_quote="1",
        base_price_usd=150.0,
        quote_asset_usd_per_token=150.0,
    )
    calls: list[tuple[str, object]] = []

    class Store:
        def __init__(self, path):
            calls.append(("database", Path(path)))

        def load_window(
            self,
            candidate_id,
            evaluated_at,
            market_policy,
            *,
            required_quote_mint,
        ):
            calls.append(
                (
                    "window",
                    (
                        candidate_id,
                        evaluated_at,
                        market_policy,
                        required_quote_mint,
                    ),
                )
            )
            return window

        def quote_asset_usd_evidence(
            self,
            candidate_id,
            evaluated_at,
            *,
            source,
            venue,
            base_mint,
            quote_mint,
            max_age_ms,
            expected_market_row_id,
        ):
            calls.append(
                (
                    "usd",
                    (
                        candidate_id,
                        evaluated_at,
                        source,
                        venue,
                        base_mint,
                        quote_mint,
                        max_age_ms,
                        expected_market_row_id,
                    ),
                )
            )
            return usd_evidence

    monkeypatch.setattr(writer, "ObserverMarketStore", Store)
    monkeypatch.setattr(writer, "_resolve_candidate_id", lambda *_a, **_k: 7)

    first = writer.run_fast_paper_authoritative_quote_usd_writer_cycle(
        decision,
        execution_bootstrap,
        policy,
        decision_evidence_directory=config.decision_config.evidence_directory,
        quote_usd_source_directory=config.quote_usd_source_directory,
    )
    second = writer.run_fast_paper_authoritative_quote_usd_writer_cycle(
        decision,
        execution_bootstrap,
        policy,
        decision_evidence_directory=config.decision_config.evidence_directory,
        quote_usd_source_directory=config.quote_usd_source_directory,
    )

    assert first == 1
    assert second == 0
    restored = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        config.quote_usd_source_directory,
    )
    assert restored.quote_usd_evidence.quote_to_usd_rate == 150.0
    assert restored.quote_usd_evidence.observed_at_unix_ms == observed_at
    assert restored.quote_usd_evidence.source_fingerprint_sha256
    assert any(name == "usd" for name, _value in calls)


def test_pending_buy_retry_writer_backpressures_without_executable_quote(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (
        manifest,
        _handoff,
        execution_bootstrap,
        config,
        _fixture_policy,
    ) = _fixture(tmp_path)
    decision = _decision_bootstrap(manifest)
    policy = _writer_policy(manifest, tmp_path / "writer")
    _feature, evidence, source = _buy_source(
        monkeypatch,
        manifest,
        execution_bootstrap,
        signature="authoritative-retry-writer",
    )
    deferred = run_fast_paper_authoritative_service_execution(
        manifest,
        execution_bootstrap,
        source,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
        committed_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    assert deferred.buy_result is not None
    assert deferred.buy_result.outcome is FastPaperBuyOutcome.DEFERRED
    write_fast_paper_shadow_decision_evidence(
        evidence,
        (
            config.decision_config.evidence_directory
            / "shadow-00000000000000000001.json"
        ),
    )
    restored_execution = SimpleNamespace(
        binding=deferred.binding,
        execution_policy=deferred.execution_policy,
        checkpoint=deferred.checkpoint,
        runtime_state=deferred.runtime_state,
    )
    monkeypatch.setattr(
        writer,
        "_pending_retry_input",
        lambda *_args, **_kwargs: None,
    )

    written = (
        writer.run_fast_paper_authoritative_pending_buy_retry_writer_cycle(
            decision,
            restored_execution,
            policy,
            decision_evidence_directory=(
                config.decision_config.evidence_directory
            ),
            pending_buy_retry_source_directory=(
                config.pending_buy_retry_source_directory
            ),
            clock_unix_ms=lambda: evidence.evaluated_at_unix_ms + 100,
        )
    )

    assert written == 0
    assert tuple(
        config.pending_buy_retry_source_directory.iterdir()
    ) == ()


def test_authoritative_source_writer_has_no_shadow_ledger_or_external_network_authority() -> None:
    source = Path(writer.__file__).read_text(encoding="utf-8")

    required = (
        "ObserverMarketStore",
        "quote_asset_usd_evidence",
        "build_fast_paper_authoritative_buy_authority_source_record",
        "build_fast_paper_authoritative_reduction_source_record",
        "build_fast_paper_authoritative_pending_buy_retry_source_record",
        "execution_bootstrap.checkpoint.state.ledger",
    )
    forbidden = (
        "shadow_ledger",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
        "save_fast_paper_shadow",
        "commit_fast_paper_shadow",
        "requests.",
        "httpx",
        "aiohttp",
        "urllib",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "required_score_threshold",
    )
    for token in required:
        assert token in source
    for token in forbidden:
        assert token not in source
