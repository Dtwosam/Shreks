from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import (
    FastCampaignDecisionPosition,
)
from shreks_brain.fast_paper_runtime import (
    build_fast_paper_runtime_manifest,
    build_fast_paper_shadow_ledger_binding,
    write_fast_paper_runtime_manifest,
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_shadow_sample_proof import (
    FastPaperShadowSamplePolicy,
    canonical_fast_paper_shadow_sample_proof,
    summarize_fast_paper_shadow_independent_sample,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime

import shreks_brain.fast_paper_shadow_missed_opportunity as missed

from test_fast_paper_shadow_decision import (
    _manifest as _base_manifest,
    _record,
)
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record_at,
)


def _manifest(tmp_path: Path):
    base = _base_manifest(tmp_path)
    policy = replace(
        base.action_policy,
        horizons_ms=(250, 500),
    )
    return build_fast_paper_runtime_manifest(
        release_source_sha=base.release_source_sha,
        champion_path=base.champion_path,
        decision_binary_path=base.decision_binary_path,
        feature_feed_binary_path=base.feature_feed_binary_path,
        action_policy=policy,
        state_version=base.state_version,
        risk_policy_version=base.risk_policy_version,
        fill_policy_version=base.fill_policy_version,
        position_action_policy_version=(
            base.position_action_policy_version
        ),
        strategy_family=base.strategy_family,
        strategy_version=base.strategy_version,
        assessment_version=base.assessment_version,
        observer_database_path=base.observer_database_path,
        paper_evidence_path=base.paper_evidence_path,
        checkpoint_path=base.checkpoint_path,
        quote_provider=base.quote_provider,
        quote_mint=base.quote_mint,
        quote_decimals=base.quote_decimals,
        route_evidence_version=base.route_evidence_version,
    )


def _database(path: Path, skip) -> None:
    feature = skip.feature_record
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE fast_events (
                sequence INTEGER NOT NULL,
                signature TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                mint TEXT NOT NULL,
                quote_mint TEXT NOT NULL,
                venue TEXT NOT NULL,
                observed_at_unix_ms INTEGER NOT NULL,
                price_quote REAL NOT NULL,
                PRIMARY KEY (signature, ordinal)
            );
            CREATE TABLE fast_future_path_labels (
                decision_signature TEXT NOT NULL,
                decision_ordinal INTEGER NOT NULL,
                decision_sequence INTEGER NOT NULL,
                decision_mint TEXT NOT NULL,
                decision_quote_mint TEXT NOT NULL,
                decision_venue TEXT NOT NULL,
                decision_observed_at_unix_ms INTEGER NOT NULL,
                decision_entry_price_quote REAL NOT NULL,
                decision_entry_total_quote REAL,
                coverage_complete_through_unix_ms INTEGER NOT NULL,
                coverage_contiguous INTEGER NOT NULL,
                horizon_ms INTEGER NOT NULL,
                label_version INTEGER NOT NULL,
                completeness TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                no_trade_events INTEGER NOT NULL,
                endpoint_signature TEXT,
                endpoint_ordinal INTEGER,
                endpoint_observed_at_unix_ms INTEGER,
                endpoint_price_quote REAL,
                endpoint_return_bps REAL,
                mfe_bps REAL,
                mae_bps REAL,
                time_to_peak_ms INTEGER,
                time_to_trough_ms INTEGER,
                reversal_occurred INTEGER,
                first_reversal_after_ms INTEGER,
                min_exit_capacity_base REAL,
                endpoint_exit_capacity_base REAL,
                route_unavailability_observed INTEGER,
                best_cost_adjusted_return_bps REAL,
                endpoint_cost_adjusted_return_bps REAL
            );
            CREATE TABLE pump_trade_evidence_conflicts (
                signature TEXT NOT NULL,
                ordinal INTEGER NOT NULL
            );
            CREATE TABLE pump_swap_trade_evidence_conflicts (
                signature TEXT NOT NULL,
                ordinal INTEGER NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                feature.decision_sequence,
                feature.decision_signature,
                feature.decision_ordinal,
                feature.mint,
                feature.quote_mint,
                feature.venue,
                feature.decision_observed_at_unix_ms,
                feature.decision_executable_entry_price_quote,
            ),
        )
        connection.execute(
            "INSERT INTO fast_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                feature.decision_sequence + 100,
                "missed-opportunity-endpoint",
                0,
                feature.mint,
                feature.quote_mint,
                feature.venue,
                feature.decision_observed_at_unix_ms + 100,
                feature.decision_executable_entry_price_quote * 1.01,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _insert_label(
    database: Path,
    skip,
    *,
    horizon_ms: int,
    kind: str = "scorable",
    best_cost_adjusted_return_bps: float = 120.0,
) -> None:
    feature = skip.feature_record
    decision_time = feature.decision_observed_at_unix_ms
    endpoint_time = decision_time + 100

    if kind == "incomplete":
        coverage = decision_time
        contiguous = 0
        completeness = "incomplete"
        event_count = 0
        no_trade = 0
        path = (None,) * 16
    elif kind == "no_trade":
        coverage = decision_time + horizon_ms
        contiguous = 1
        completeness = "complete"
        event_count = 0
        no_trade = 1
        path = (None,) * 16
    else:
        coverage = decision_time + horizon_ms
        contiguous = 1
        completeness = "complete"
        event_count = 1
        no_trade = 0
        best = (
            None
            if kind == "economics_missing"
            else best_cost_adjusted_return_bps
        )
        path = (
            "missed-opportunity-endpoint",
            0,
            endpoint_time,
            feature.decision_executable_entry_price_quote * 1.01,
            100.0,
            150.0,
            -30.0,
            100,
            100,
            0,
            None,
            8.0,
            8.0,
            0,
            best,
            80.0 if best is not None else None,
        )

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """INSERT INTO fast_future_path_labels VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )""",
            (
                feature.decision_signature,
                feature.decision_ordinal,
                feature.decision_sequence,
                feature.mint,
                feature.quote_mint,
                feature.venue,
                feature.decision_observed_at_unix_ms,
                feature.decision_executable_entry_price_quote,
                feature.decision_entry_total_quote or 10.0,
                coverage,
                contiguous,
                horizon_ms,
                1,
                completeness,
                event_count,
                no_trade,
                *path,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    sample_min_decisions: int = 2,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)

    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="fl11-2b-test-run",
        database_path=tmp_path / "shadow-ledger.sqlite3",
    )
    evidence_directory = tmp_path / "decisions"
    evidence_directory.mkdir()

    feature1 = _record()
    skip = _evidence_for(
        monkeypatch,
        manifest,
        feature1,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    feature2 = _record_at(
        feature1,
        signature="missed-opportunity-buy",
        sequence=2,
        at=20_300,
    )
    buy = _evidence_for(
        monkeypatch,
        manifest,
        feature2,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_320,
        entry_observed_at=20_310,
        exit_observed_at=20_315,
    )
    for evidence in (skip, buy):
        write_fast_paper_shadow_decision_evidence(
            evidence,
            evidence_directory
            / f"shadow-{evidence.source_sequence:020d}-"
            f"{evidence.evidence_fingerprint_sha256[:16]}.json",
        )

    checkpoint = SimpleNamespace(
        state=SimpleNamespace(
            ledger=SimpleNamespace(
                positions=(
                    SimpleNamespace(
                        position_id="closed-fixture",
                        mint=buy.feature_record.mint,
                        state=PaperPositionState.CLOSED,
                        closed_at_unix_ms=20_500,
                    ),
                )
            )
        )
    )
    sample = summarize_fast_paper_shadow_independent_sample(
        (skip, buy),
        buy_regimes={
            buy.evidence_fingerprint_sha256: MarketRegime.NORMAL,
        },
        missing_buy_execution_source_count=0,
        checkpoint=checkpoint,
        policy=FastPaperShadowSamplePolicy(
            version="fl11.2b-test-sample-v1",
            min_decision_count=sample_min_decisions,
            min_distinct_market_count=1,
            min_distinct_mint_count=1,
            min_observation_span_ms=1,
            min_closed_position_count=1,
            min_distinct_traded_mint_count=1,
            min_distinct_buy_regime_count=1,
            min_distinct_selected_horizon_count=1,
        ),
        expected_release_sha=manifest.release_source_sha,
        binding_fingerprint_sha256=binding.binding_fingerprint_sha256,
        since_unix_ms=19_000,
        until_unix_ms=21_000,
    )
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(
        canonical_fast_paper_shadow_sample_proof(sample),
        encoding="utf-8",
    )
    _database(Path(manifest.observer_database_path), skip)
    return SimpleNamespace(
        manifest=manifest,
        manifest_path=manifest_path,
        binding=binding,
        evidence_directory=evidence_directory,
        sample=sample,
        sample_path=sample_path,
        skip=skip,
        buy=buy,
        database=Path(manifest.observer_database_path),
    )


def _collect(fixture):
    return missed.collect_fast_paper_shadow_missed_opportunity(
        manifest_path=fixture.manifest_path,
        ledger_database_path=Path(fixture.binding.database_path),
        run_id=fixture.binding.run_id,
        decision_evidence_directory=fixture.evidence_directory,
        sample_proof_path=fixture.sample_path,
        expected_release_sha=fixture.manifest.release_source_sha,
        since_unix_ms=19_000,
        until_unix_ms=21_000,
        future_path_label_version=1,
    )


def test_scores_complete_policy_horizons_and_clips_negative_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=250,
        best_cost_adjusted_return_bps=120.0,
    )
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=500,
        best_cost_adjusted_return_bps=-40.0,
    )

    report = _collect(fixture)

    assert report["decision_count"] == 2
    assert report["skip_decision_count"] == 1
    assert report["policy_horizons_ms"] == [250, 500]
    assert report["missed_opportunity_evidence_state"] == "COMPLETE"
    assert report["fully_scorable_skip_count"] == 1
    assert report["partially_or_unscorable_skip_count"] == 0
    assert report["positive_missed_opportunity_count"] == 1
    assert report["positive_missed_opportunity_rate"] == 1.0
    assert report["best_missed_opportunity_bps"] == {
        "mean": 120.0,
        "p50": 120.0,
        "p95": 120.0,
        "min": 120.0,
        "max": 120.0,
    }
    decision = report["per_skip_decision"][0]
    assert decision["best_missed_opportunity_bps"] == 120.0
    assert decision["best_missed_opportunity_horizon_ms"] == 250
    by_horizon = {
        row["horizon_ms"]: row
        for row in decision["horizons"]
    }
    assert by_horizon[250]["missed_opportunity_bps"] == 120.0
    assert by_horizon[500]["best_cost_adjusted_return_bps"] == -40.0
    assert by_horizon[500]["missed_opportunity_bps"] == 0.0
    assert set(report["future_path_dataset_fingerprints_sha256"]) == {
        "250",
        "500",
    }
    assert report["promotion_authority"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"

    fingerprint = report["report_fingerprint_sha256"]
    material = dict(report)
    material.pop("report_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        missed.canonical_fast_paper_shadow_missed_opportunity(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_no_trade_is_zero_but_incomplete_horizon_blocks_cross_horizon_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=250,
        kind="no_trade",
    )
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=500,
        kind="incomplete",
    )

    report = _collect(fixture)

    assert report["missed_opportunity_evidence_state"] == "PARTIAL"
    assert report["fully_scorable_skip_count"] == 0
    assert report["partially_or_unscorable_skip_count"] == 1
    assert report["positive_missed_opportunity_rate"] is None
    assert report["best_missed_opportunity_bps"]["mean"] is None
    decision = report["per_skip_decision"][0]
    assert decision["fully_scorable_across_policy_horizons"] is False
    assert decision["best_missed_opportunity_bps"] is None
    by_horizon = {
        row["horizon_ms"]: row
        for row in decision["horizons"]
    }
    assert by_horizon[250] == {
        "horizon_ms": 250,
        "status": "SCORABLE_NO_TRADE_EVENTS",
        "best_cost_adjusted_return_bps": None,
        "missed_opportunity_bps": 0.0,
    }
    assert by_horizon[500]["status"] == "INCOMPLETE_FUTURE_PATH"
    assert by_horizon[500]["missed_opportunity_bps"] is None


def test_complete_path_without_cost_adjusted_economics_stays_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=250,
        kind="economics_missing",
    )
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=500,
        best_cost_adjusted_return_bps=50.0,
    )

    report = _collect(fixture)

    assert report["missed_opportunity_evidence_state"] == "PARTIAL"
    horizon = {
        row["horizon_ms"]: row
        for row in report["per_horizon"]
    }
    assert horizon[250]["complete_label_count"] == 1
    assert horizon[250]["scorable_count"] == 0
    assert horizon[250]["cost_adjusted_unavailable_count"] == 1
    decision = report["per_skip_decision"][0]
    assert decision["best_missed_opportunity_bps"] is None


def test_missing_future_path_horizon_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(monkeypatch, tmp_path)
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=250,
    )

    with pytest.raises(
        missed.FastPaperShadowMissedOpportunityError,
        match="future-path load failed closed",
    ):
        _collect(fixture)


def test_requires_sufficient_sample_and_reconciles_decision_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    insufficient = _fixture(
        monkeypatch,
        tmp_path / "insufficient",
        sample_min_decisions=3,
    )
    assert insufficient.sample["decision"] == "INSUFFICIENT_SAMPLE"
    with pytest.raises(
        missed.FastPaperShadowMissedOpportunityError,
        match="SUFFICIENT_SAMPLE",
    ):
        _collect(insufficient)

    fixture = _fixture(
        monkeypatch,
        tmp_path / "mismatch",
    )
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=250,
    )
    _insert_label(
        fixture.database,
        fixture.skip,
        horizon_ms=500,
    )
    buy_path = next(
        path
        for path in fixture.evidence_directory.glob("shadow-*.json")
        if f"{fixture.buy.source_sequence:020d}" in path.name
    )
    buy_path.unlink()
    with pytest.raises(
        missed.FastPaperShadowMissedOpportunityError,
        match="decision count",
    ):
        _collect(fixture)


def test_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(missed.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-missed-opportunity = '
        '"shreks_brain.fast_paper_shadow_missed_opportunity:main"'
    ) in pyproject

    for required in (
        "load_future_path_training_labels_for_identities_from_sqlite",
        "feature_record.decision_identity",
        "manifest.action_policy.horizons_ms",
        "best_cost_adjusted_return_bps",
    ):
        assert required in source

    for forbidden in (
        "label_future_paths",
        "record_fast_paper_skip",
        "execute_fast_paper_shadow_decision",
        "retry_fast_paper_shadow_pending_buy",
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
