from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.fast_paper_runtime.shadow_provision import (
    provision_fast_paper_shadow,
)
from shreks_brain.fast_paper_runtime.shadow_supervisor import (
    bootstrap_fast_paper_shadow_supervisor,
)
from shreks_brain.fast_paper_shadow_sample_proof import (
    FastPaperShadowSamplePolicy,
    canonical_fast_paper_shadow_sample_proof,
    collect_fast_paper_shadow_independent_sample,
)

import shreks_brain.fast_paper_shadow_trade_economics as economics

from test_fast_paper_shadow_executor import _record_at
from test_fast_paper_shadow_first_buy_e2e import (
    _DECISION_AT,
    _HORIZON_MS,
    _runtime_fixture,
)
from test_fast_paper_shadow_supervised_lifecycle_e2e import (
    _insert_open_quotes,
    _install_decisions,
    _install_feature_feed,
    _run_action,
)


def _lifecycle_fixture(monkeypatch, tmp_path: Path):
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
            signature="economics-hold",
            sequence=2,
            at=_DECISION_AT + 300,
        ),
        _record_at(
            first_feature,
            signature="economics-reduce",
            sequence=3,
            at=_DECISION_AT + 600,
        ),
        _record_at(
            first_feature,
            signature="economics-sell",
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
    _install_feature_feed(monkeypatch, manifest, records)
    _install_decisions(monkeypatch, manifest)
    provision_fast_paper_shadow(
        provision_config,
        clock_unix_ms=lambda: _DECISION_AT - 1_000,
    )

    bootstrap = bootstrap_fast_paper_shadow_supervisor(supervisor_config)
    for sequence, decision_at, execution_at in (
        (1, _DECISION_AT + 100, _DECISION_AT + 350),
        (2, _DECISION_AT + 400, _DECISION_AT + 650),
        (3, _DECISION_AT + 700, _DECISION_AT + 950),
        (4, _DECISION_AT + 1_000, _DECISION_AT + 1_100),
    ):
        bootstrap, _evidence = _run_action(
            bootstrap,
            manifest=manifest,
            config=supervisor_config,
            sequence=sequence,
            decision_at=decision_at,
            execution_at=execution_at,
        )

    assert authoritative_paper.read_bytes() == authoritative_bytes
    return manifest, supervisor_config, bootstrap


def _sample_policy(*, min_closed_positions: int = 1):
    return FastPaperShadowSamplePolicy(
        version="fl11.2a-test-sample-v1",
        min_decision_count=4,
        min_distinct_market_count=1,
        min_distinct_mint_count=1,
        min_observation_span_ms=1,
        min_closed_position_count=min_closed_positions,
        min_distinct_traded_mint_count=1,
        min_distinct_buy_regime_count=1,
        min_distinct_selected_horizon_count=1,
    )


def _write_sample(
    tmp_path: Path,
    *,
    manifest,
    config,
    since: int,
    until: int,
    min_closed_positions: int = 1,
):
    sample = collect_fast_paper_shadow_independent_sample(
        manifest_path=config.decision_config.manifest_path,
        execution_policy_path=config.execution_config.execution_policy_path,
        ledger_database_path=config.execution_config.ledger_database_path,
        run_id=config.execution_config.run_id,
        decision_evidence_directory=config.decision_config.evidence_directory,
        execution_source_directory=config.execution_config.source_directory,
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=since,
        until_unix_ms=until,
        policy=_sample_policy(
            min_closed_positions=min_closed_positions,
        ),
    )
    path = tmp_path / "fl11.1-sample.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        canonical_fast_paper_shadow_sample_proof(sample),
        encoding="utf-8",
    )
    return path, sample


def _collect(
    *,
    manifest,
    config,
    sample_path: Path,
    since: int,
    until: int,
):
    return economics.collect_fast_paper_shadow_trade_economics(
        manifest_path=config.decision_config.manifest_path,
        execution_policy_path=config.execution_config.execution_policy_path,
        ledger_database_path=config.execution_config.ledger_database_path,
        run_id=config.execution_config.run_id,
        decision_evidence_directory=config.decision_config.evidence_directory,
        execution_source_directory=config.execution_config.source_directory,
        pending_buy_retry_source_directory=(
            config.pending_buy_retry_source_directory
        ),
        sample_proof_path=sample_path,
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=since,
        until_unix_ms=until,
        evaluation_policy_version="fl11.2a-test-e5-v1",
        calibration_bucket_count=10,
    )


def test_closed_trade_economics_reuses_sealed_e11_e5_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, config, bootstrap = _lifecycle_fixture(
        monkeypatch,
        tmp_path,
    )
    since = _DECISION_AT - 100
    until = _DECISION_AT + 2_000
    sample_path, sample = _write_sample(
        tmp_path,
        manifest=manifest,
        config=config,
        since=since,
        until=until,
    )
    assert sample["decision"] == "SUFFICIENT_SAMPLE"
    assert sample["closed_position_count"] == 1

    report = _collect(
        manifest=manifest,
        config=config,
        sample_path=sample_path,
        since=since,
        until=until,
    )

    assert report["closed_trade_count"] == 1
    metrics = report["sealed_e5_report"]["metrics"]
    assert metrics["trade_count"] == 1
    assert metrics["turnover_usd"] > 0.0
    assert metrics["explicit_cost_usd"] >= 0.0
    assert metrics["execution_friction_usd"] >= 0.0
    assert metrics["net_expectancy_usd"] == pytest.approx(
        metrics["net_pnl_usd"]
    )
    assert report["sealed_e5_report"]["calibration"] is None
    assert sum(
        item["metrics"]["trade_count"]
        for item in report["horizon_performance"]
    ) == 1
    assert report["horizon_performance"][0][
        "selected_horizon_ms"
    ] == _HORIZON_MS
    assert report["expected_realized_value_bps"]["observation_count"] == 1
    assert report["entry_efficiency"]["observation_count"] == 1
    assert report["exit_timing"]["observation_count"] == 1
    assert report["entry_capital_utilization"]["observation_count"] == 1
    assert report["counterfactual_missed_opportunity_evidence"] == (
        "NOT_INCLUDED_FL11_2A"
    )
    assert report["fee_slippage_sensitivity_evidence"] == (
        "NOT_INCLUDED_FL11_2A"
    )
    assert report["promotion_authority"] == "NOT_GRANTED"
    assert report["production_paper_cutover"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"

    fingerprint = report["report_fingerprint_sha256"]
    material = dict(report)
    material.pop("report_fingerprint_sha256")
    assert fingerprint == economics.hashlib.sha256(
        economics.canonical_fast_paper_shadow_trade_economics(
            material
        ).encode("utf-8")
    ).hexdigest()

    assert bootstrap.execution_bootstrap.checkpoint.sequence == 4


def test_fl11_2a_requires_sufficient_exact_window_sample(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, config, _bootstrap = _lifecycle_fixture(
        monkeypatch,
        tmp_path,
    )
    since = _DECISION_AT - 100
    until = _DECISION_AT + 2_000
    sample_path, sample = _write_sample(
        tmp_path,
        manifest=manifest,
        config=config,
        since=since,
        until=until,
        min_closed_positions=2,
    )
    assert sample["decision"] == "INSUFFICIENT_SAMPLE"

    with pytest.raises(
        economics.FastPaperShadowTradeEconomicsError,
        match="SUFFICIENT_SAMPLE",
    ):
        _collect(
            manifest=manifest,
            config=config,
            sample_path=sample_path,
            since=since,
            until=until,
        )

    sufficient_path, _sample = _write_sample(
        tmp_path / "other",
        manifest=manifest,
        config=config,
        since=since,
        until=until,
    )
    with pytest.raises(
        economics.FastPaperShadowTradeEconomicsError,
        match="window_until|mismatch",
    ):
        _collect(
            manifest=manifest,
            config=config,
            sample_path=sufficient_path,
            since=since,
            until=until + 1,
        )


def test_fl11_2a_fails_closed_when_durable_source_history_is_incomplete(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, config, _bootstrap = _lifecycle_fixture(
        monkeypatch,
        tmp_path,
    )
    since = _DECISION_AT - 100
    until = _DECISION_AT + 2_000
    sample_path, _sample = _write_sample(
        tmp_path,
        manifest=manifest,
        config=config,
        since=since,
        until=until,
    )

    sources = sorted(Path(config.execution_config.source_directory).glob("*.json"))
    assert len(sources) == 4
    sources[1].unlink()

    with pytest.raises(
        economics.FastPaperShadowTradeEconomicsError,
        match="source coverage|missing|incomplete",
    ):
        _collect(
            manifest=manifest,
            config=config,
            sample_path=sample_path,
            since=since,
            until=until,
        )


def test_fl11_2a_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(economics.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-trade-economics = '
        '"shreks_brain.fast_paper_shadow_trade_economics:main"'
    ) in pyproject

    for required in (
        "extract_fast_paper_evaluation_evidence",
        "build_evaluated_trades",
        "evaluate_trading_performance",
        "reconstruct_fast_paper_shadow_pending_buy_retry",
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
