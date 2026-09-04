from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_COMPARISON_EVIDENCE_BINDER_VERSION,
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicCandidatePaperAuthority,
    FastDeterministicComparisonEvidenceRow,
    FastDeterministicComparisonEvidenceSpec,
    bind_fast_deterministic_comparison_evidence,
    run_fast_deterministic_comparison_catalog_matrix,
)
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_comparison_catalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineMarketSnapshot,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
)


T0 = 50_000_000
CATALOG_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_comparison_catalog_v1.json"
)


def _window(window_ms: int) -> FastTrainingWindowSummary:
    return FastTrainingWindowSummary(
        window_ms=window_ms,
        buy_count=0,
        sell_count=0,
        unique_buy_actors=0,
        unique_sell_actors=0,
        buy_arrival_rate_per_second=0.0,
        sell_arrival_rate_per_second=0.0,
        count_imbalance=0.0,
        buy_base_quantity=0.0,
        sell_base_quantity=0.0,
        buy_quote_quantity=0.0,
        sell_quote_quantity=0.0,
        net_quote_quantity=0.0,
        quote_flow_imbalance=0.0,
        quote_flow_velocity_per_second=0.0,
        quote_flow_acceleration_per_second2=0.0,
        local_high_price_quote=None,
        local_high_sequence=None,
        local_high_observed_at_unix_ms=None,
        local_low_price_quote=None,
        local_low_sequence=None,
        local_low_observed_at_unix_ms=None,
        post_high_low_price_quote=None,
        post_high_low_sequence=None,
        post_high_low_observed_at_unix_ms=None,
        last_price_quote=10.0,
        drawdown_from_local_high=0.0,
        recovery_from_local_low=0.0,
    )


def _record() -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature="binder-1",
        decision_ordinal=0,
        decision_sequence=1,
        mint="mint-binder",
        quote_mint="quote-binder",
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=T0 + 100,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 + 99,
        decision_occurred_at_unix_ms=T0 + 98,
        decision_slot=101,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=T0 + 100,
        snapshot_last_sequence=1,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _quote() -> FastCampaignPaperQuoteEvidence:
    return FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint="mint-binder",
        quote_mint="quote-binder",
        observed_at_unix_ms=T0 + 150,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=10.1,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )


def _risk_environment() -> FastDeterministicCampaignRiskEnvironment:
    return FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=20_000.0,
        day_started_at_unix_ms=T0,
        liquidity_usd=100_000.0,
        expected_price_impact_pct=0.1,
        price_impact_notional_usd=500.0,
        market_observed_at_unix_ms=T0 + 100,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset(),
    )


def _entry_authority() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint="mint-binder",
        quote_mint="quote-binder",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _catalog():
    return decode_fast_deterministic_comparison_catalog(
        CATALOG_FIXTURE.read_text(encoding="utf-8")
    )


def _row() -> FastDeterministicComparisonEvidenceRow:
    record = _record()
    snapshot = FastOfflineMarketSnapshot(
        mint=record.mint,
        quote_mint=record.quote_mint,
        venue=record.venue,
        as_of_unix_ms=record.snapshot_as_of_unix_ms,
        last_sequence=record.snapshot_last_sequence,
        last_price_quote=record.snapshot_last_price_quote,
        last_reserve_context=record.last_reserve_context,
        last_lifecycle_event=record.last_lifecycle_event,
        windows=record.windows,
    )
    authorities = tuple(
        FastDeterministicCandidatePaperAuthority(
            candidate_version=manifest.candidate_version,
            entry_authority=_entry_authority(),
        )
        for manifest in _catalog().candidates
    )
    return FastDeterministicComparisonEvidenceRow(
        record=record,
        impulse_scalp_evidence=FastOfflineImpulseScalpEvidence(execution=None),
        micro_pullback_evidence=FastOfflineMicroPullbackEvidence(execution=None),
        pre_graduation_evidence=FastOfflinePreGraduationEvidence(execution=None),
        graduation_flow_evidence=FastOfflineGraduationFlowEvidence(
            pre_snapshot=snapshot,
            boost_context=None,
            execution=None,
        ),
        wallet_cohort_evidence=FastOfflineWalletCohortEvidence(evidence=None),
        longer_runner_evidence=FastOfflineLongerRunnerEvidence(
            protective=FastOfflineLongerRunnerProtective(
                hard_stop_triggered=False,
                risk_limit_exit_required=False,
                liquidity_exit_required=False,
            ),
            continuation=None,
        ),
        state_version="state-v1",
        evaluated_at_unix_ms=T0 + 150,
        quote=_quote(),
        market_regime=MarketRegime.NORMAL,
        risk_environment=_risk_environment(),
        candidate_authorities=authorities,
    )


def test_binder_expands_catalog_to_eight_same_population_specs() -> None:
    catalog = _catalog()

    bound = bind_fast_deterministic_comparison_evidence(
        catalog=catalog,
        rows=(_row(),),
        paper_run_id_prefix="fl9-baseline",
    )

    assert type(bound) is FastDeterministicComparisonEvidenceSpec
    assert bound.version == FAST_DETERMINISTIC_COMPARISON_EVIDENCE_BINDER_VERSION
    assert bound.catalog_fingerprint_sha256 == catalog.catalog_fingerprint_sha256
    assert tuple(
        spec.manifest.candidate_version for spec in bound.specs
    ) == tuple(manifest.candidate_version for manifest in catalog.candidates)
    assert len(bound.specs) == 8

    quotes = set()
    records = set()
    for spec in bound.specs:
        assert spec.paper_run_id == (
            f"fl9-baseline:{spec.manifest.candidate_version}"
        )
        row = spec.rows[0]
        assert row.flat_evidence.kind == (
            spec.manifest.lifecycle_policy.entry_baseline_kind
        )
        assert row.open_evidence.kind == (
            spec.manifest.lifecycle_policy.manager_baseline_kind
        )
        quotes.add(row.paper_evidence.quote)
        records.add(row.record)
        assert row.paper_evidence.risk_context is None
        assert row.paper_evidence.risk_environment == _risk_environment()
        assert row.paper_evidence.entry_authority == _entry_authority()

    assert len(quotes) == 1
    assert len(records) == 1


def test_binder_requires_exact_catalog_candidate_authority_coverage() -> None:
    catalog = _catalog()
    row = _row()
    bad = FastDeterministicComparisonEvidenceRow(
        record=row.record,
        impulse_scalp_evidence=row.impulse_scalp_evidence,
        micro_pullback_evidence=row.micro_pullback_evidence,
        pre_graduation_evidence=row.pre_graduation_evidence,
        graduation_flow_evidence=row.graduation_flow_evidence,
        wallet_cohort_evidence=row.wallet_cohort_evidence,
        longer_runner_evidence=row.longer_runner_evidence,
        state_version=row.state_version,
        evaluated_at_unix_ms=row.evaluated_at_unix_ms,
        quote=row.quote,
        market_regime=row.market_regime,
        risk_environment=row.risk_environment,
        candidate_authorities=row.candidate_authorities[:-1],
    )

    with pytest.raises(ValueError, match="authority|candidate|coverage"):
        bind_fast_deterministic_comparison_evidence(
            catalog=catalog,
            rows=(bad,),
            paper_run_id_prefix="fl9-baseline",
        )


def test_binder_requires_quote_contemporaneous_with_decision() -> None:
    row = _row()
    stale_quote = FastCampaignPaperQuoteEvidence(
        provider=row.quote.provider,
        mint=row.quote.mint,
        quote_mint=row.quote.quote_mint,
        observed_at_unix_ms=T0,
        state=row.quote.state,
        reference_price_quote=row.quote.reference_price_quote,
        execution_price_quote=row.quote.execution_price_quote,
        quoted_base_quantity=row.quote.quoted_base_quantity,
        available_base_quantity=row.quote.available_base_quantity,
        quote_to_usd_rate=row.quote.quote_to_usd_rate,
    )

    with pytest.raises(ValueError, match="quote|contemporaneous|decision"):
        FastDeterministicComparisonEvidenceRow(
            record=row.record,
            impulse_scalp_evidence=row.impulse_scalp_evidence,
            micro_pullback_evidence=row.micro_pullback_evidence,
            pre_graduation_evidence=row.pre_graduation_evidence,
            graduation_flow_evidence=row.graduation_flow_evidence,
            wallet_cohort_evidence=row.wallet_cohort_evidence,
            longer_runner_evidence=row.longer_runner_evidence,
            state_version=row.state_version,
            evaluated_at_unix_ms=row.evaluated_at_unix_ms,
            quote=stale_quote,
            market_regime=row.market_regime,
            risk_environment=row.risk_environment,
            candidate_authorities=row.candidate_authorities,
        )




def test_binder_preserves_absent_buy_authority_for_truthful_fl3_skip() -> None:
    row = _row()
    first = row.candidate_authorities[0]
    authorities = (
        FastDeterministicCandidatePaperAuthority(
            candidate_version=first.candidate_version,
            entry_authority=None,
        ),
        *row.candidate_authorities[1:],
    )
    updated = FastDeterministicComparisonEvidenceRow(
        record=row.record,
        impulse_scalp_evidence=row.impulse_scalp_evidence,
        micro_pullback_evidence=row.micro_pullback_evidence,
        pre_graduation_evidence=row.pre_graduation_evidence,
        graduation_flow_evidence=row.graduation_flow_evidence,
        wallet_cohort_evidence=row.wallet_cohort_evidence,
        longer_runner_evidence=row.longer_runner_evidence,
        state_version=row.state_version,
        evaluated_at_unix_ms=row.evaluated_at_unix_ms,
        quote=row.quote,
        market_regime=row.market_regime,
        risk_environment=row.risk_environment,
        candidate_authorities=authorities,
        entry_quote=row.entry_quote,
        exit_quote=row.exit_quote,
    )

    bound = bind_fast_deterministic_comparison_evidence(
        catalog=_catalog(),
        rows=(updated,),
        paper_run_id_prefix="fl9-baseline",
    )

    assert bound.specs[0].rows[0].paper_evidence.entry_authority is None
    assert all(
        spec.rows[0].paper_evidence.entry_authority is not None
        for spec in bound.specs[1:]
    )


def test_comparison_row_rejects_entry_authority_provenance_drift() -> None:
    row = _row()
    first = row.candidate_authorities[0]
    bad_entry = FastCampaignPaperEntryAuthority(
        mint=row.record.mint,
        quote_mint=row.record.quote_mint,
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=9.9,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )
    authorities = (
        FastDeterministicCandidatePaperAuthority(
            candidate_version=first.candidate_version,
            entry_authority=bad_entry,
        ),
        *row.candidate_authorities[1:],
    )

    with pytest.raises(ValueError, match="authority|decision|price|provenance"):
        FastDeterministicComparisonEvidenceRow(
            record=row.record,
            impulse_scalp_evidence=row.impulse_scalp_evidence,
            micro_pullback_evidence=row.micro_pullback_evidence,
            pre_graduation_evidence=row.pre_graduation_evidence,
            graduation_flow_evidence=row.graduation_flow_evidence,
            wallet_cohort_evidence=row.wallet_cohort_evidence,
            longer_runner_evidence=row.longer_runner_evidence,
            state_version=row.state_version,
            evaluated_at_unix_ms=row.evaluated_at_unix_ms,
            quote=row.quote,
            market_regime=row.market_regime,
            risk_environment=row.risk_environment,
            candidate_authorities=authorities,
        )


def test_run_wrapper_invokes_only_sealed_matrix(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    sentinel = SimpleNamespace(version="matrix-sentinel")

    def fake_matrix(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.comparison.run_fast_deterministic_candidate_matrix",
        fake_matrix,
    )

    result = run_fast_deterministic_comparison_catalog_matrix(
        binary_path=tmp_path / "row-binary",
        catalog=_catalog(),
        rows=(_row(),),
        paper_run_id_prefix="fl9-baseline",
        assessment_version="assessment-v1",
        starting_ledger=object(),
        fill_policy=object(),
        risk_policy=object(),
        position_policy=object(),
        evaluation_policy=object(),
    )

    assert result is sentinel
    assert len(captured["specs"]) == 8
    assert tuple(
        spec.manifest.candidate_version for spec in captured["specs"]
    ) == tuple(
        manifest.candidate_version for manifest in _catalog().candidates
    )


def test_binder_source_has_no_provider_superiority_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "comparison.py"
    ).read_text(encoding="utf-8")

    assert "run_fast_deterministic_candidate_matrix(" in source
    for forbidden in (
        "evaluate_fast_policy_superiority",
        "requests.",
        "sqlite3",
        "subprocess",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
