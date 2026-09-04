from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_NAME,
    FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION,
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicCandidatePaperAuthority,
    FastDeterministicComparisonEvidenceBundle,
    FastDeterministicComparisonEvidenceProvenance,
    FastDeterministicComparisonEvidenceRow,
    read_fast_deterministic_comparison_evidence_bundle,
    write_fast_deterministic_comparison_evidence_bundle,
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
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
    feature_logical_fingerprint_sha256,
)


T0 = 60_000_000
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
        decision_signature="bundle-sig",
        decision_ordinal=0,
        decision_sequence=1,
        mint="mint-bundle",
        quote_mint="quote-bundle",
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=T0 + 100,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 + 99,
        decision_occurred_at_unix_ms=T0 + 98,
        decision_slot=111,
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


def _dataset(record: FastTrainingFeatureRecord) -> FastTrainingFeatureDataset:
    records = (record,)
    return FastTrainingFeatureDataset(
        records=records,
        logical_fingerprint_sha256=feature_logical_fingerprint_sha256(records),
        source_sha256="a" * 64,
    )


def _catalog():
    return decode_fast_deterministic_comparison_catalog(
        CATALOG_FIXTURE.read_text(encoding="utf-8")
    )


def _entry_authority() -> FastCampaignPaperEntryAuthority:
    return FastCampaignPaperEntryAuthority(
        mint="mint-bundle",
        quote_mint="quote-bundle",
        intended_base_quantity=10.0,
        decision_executable_entry_price_quote=10.0,
        maximum_acceptable_entry_price_quote=10.5,
        expected_entry_variable_cost_bps=200,
        expected_entry_fixed_cost_quote=0.10,
    )


def _quote(*, execution: float) -> FastCampaignPaperQuoteEvidence:
    return FastCampaignPaperQuoteEvidence(
        provider="jupiter",
        mint="mint-bundle",
        quote_mint="quote-bundle",
        observed_at_unix_ms=T0 + 150,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=execution,
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
        market_observed_at_unix_ms=T0 + 120,
        data_healthy=True,
        execution_healthy=True,
        kill_switch_active=False,
        active_intent_keys=frozenset({"already-seen"}),
    )


def _provenance(
    record: FastTrainingFeatureRecord,
) -> FastDeterministicComparisonEvidenceProvenance:
    return FastDeterministicComparisonEvidenceProvenance(
        source_event_id=f"{record.decision_signature}:{record.decision_ordinal}",
        entry_quote_source_version="jupiter-entry-probe-v2",
        exit_quote_source_version="jupiter-exit-probe-v2",
        entry_forecast_source_version=None,
        entry_forecast_horizon_ms=None,
        execution_cost_source_version=None,
        exit_capacity_source_version=None,
        wallet_source_version=None,
        graduation_context_source_version="fl8.1-hydration-v1",
        continuation_forecast_source_version=None,
        regime_source_version="regime-v1",
        risk_environment_source_version="risk-environment-v1",
        entry_authority_source_version="entry-authority-v1",
    )


def _row(record: FastTrainingFeatureRecord) -> FastDeterministicComparisonEvidenceRow:
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
        state_version="state-real-v2",
        evaluated_at_unix_ms=T0 + 200,
        quote=None,
        market_regime=MarketRegime.NORMAL,
        risk_environment=_risk_environment(),
        candidate_authorities=authorities,
        entry_quote=_quote(execution=10.1),
        exit_quote=_quote(execution=9.9),
    )


def test_bundle_round_trip_is_self_contained_immutable_and_fingerprinted(
    tmp_path: Path,
) -> None:
    record = _record()
    dataset = _dataset(record)
    catalog = _catalog()
    destination = tmp_path / "comparison-bundle"

    manifest = write_fast_deterministic_comparison_evidence_bundle(
        feature_dataset=dataset,
        catalog=catalog,
        rows=(_row(record),),
        provenance=(_provenance(record),),
        destination=destination,
    )

    assert manifest.schema_name == FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_NAME
    assert manifest.schema_version == FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION
    assert manifest.row_count == 1
    assert manifest.feature_logical_fingerprint_sha256 == (
        dataset.logical_fingerprint_sha256
    )
    assert manifest.catalog_fingerprint_sha256 == catalog.catalog_fingerprint_sha256
    assert len(manifest.evidence_logical_fingerprint_sha256) == 64
    assert len(manifest.bundle_fingerprint_sha256) == 64
    assert {path.name for path in destination.iterdir()} == {
        "fast_training_features.parquet",
        "comparison_evidence.jsonl",
        "manifest.json",
    }

    loaded = read_fast_deterministic_comparison_evidence_bundle(destination)
    assert type(loaded) is FastDeterministicComparisonEvidenceBundle
    assert loaded.manifest == manifest
    assert loaded.features == dataset
    assert loaded.rows == (_row(record),)
    assert loaded.provenance == (_provenance(record),)

    with pytest.raises(FileExistsError, match="immutable"):
        write_fast_deterministic_comparison_evidence_bundle(
            feature_dataset=dataset,
            catalog=catalog,
            rows=(_row(record),),
            provenance=(_provenance(record),),
            destination=destination,
        )



def test_bundle_v2_rejects_legacy_single_quote_rows(tmp_path: Path) -> None:
    record = _record()
    directional = _row(record)
    legacy = FastDeterministicComparisonEvidenceRow(
        record=directional.record,
        impulse_scalp_evidence=directional.impulse_scalp_evidence,
        micro_pullback_evidence=directional.micro_pullback_evidence,
        pre_graduation_evidence=directional.pre_graduation_evidence,
        graduation_flow_evidence=directional.graduation_flow_evidence,
        wallet_cohort_evidence=directional.wallet_cohort_evidence,
        longer_runner_evidence=directional.longer_runner_evidence,
        state_version=directional.state_version,
        evaluated_at_unix_ms=directional.evaluated_at_unix_ms,
        quote=_quote(execution=10.0),
        market_regime=directional.market_regime,
        risk_environment=directional.risk_environment,
        candidate_authorities=directional.candidate_authorities,
    )

    with pytest.raises(ValueError, match="v2|legacy|directional"):
        write_fast_deterministic_comparison_evidence_bundle(
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            rows=(legacy,),
            provenance=(_provenance(record),),
            destination=tmp_path / "legacy",
        )


def test_bundle_rejects_feature_population_drift(tmp_path: Path) -> None:
    record = _record()
    changed = FastTrainingFeatureRecord(
        **{
            **{name: getattr(record, name) for name in record.__dataclass_fields__},
            "decision_signature": "other-sig",
        }
    )

    with pytest.raises(ValueError, match="population|feature|row"):
        write_fast_deterministic_comparison_evidence_bundle(
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            rows=(_row(changed),),
            provenance=(_provenance(changed),),
            destination=tmp_path / "drift",
        )


def test_bundle_rejects_provenance_population_drift(tmp_path: Path) -> None:
    record = _record()
    bad = FastDeterministicComparisonEvidenceProvenance(
        source_event_id="wrong:0",
        entry_quote_source_version="jupiter-entry-probe-v2",
        exit_quote_source_version="jupiter-exit-probe-v2",
        entry_forecast_source_version=None,
        entry_forecast_horizon_ms=None,
        execution_cost_source_version=None,
        exit_capacity_source_version=None,
        wallet_source_version=None,
        graduation_context_source_version="fl8.1-hydration-v1",
        continuation_forecast_source_version=None,
        regime_source_version="regime-v1",
        risk_environment_source_version="risk-environment-v1",
        entry_authority_source_version="entry-authority-v1",
    )

    with pytest.raises(ValueError, match="provenance|population|source"):
        write_fast_deterministic_comparison_evidence_bundle(
            feature_dataset=_dataset(record),
            catalog=_catalog(),
            rows=(_row(record),),
            provenance=(bad,),
            destination=tmp_path / "bad-provenance",
        )


def test_bundle_detects_sidecar_tampering(tmp_path: Path) -> None:
    record = _record()
    destination = tmp_path / "tampered"
    write_fast_deterministic_comparison_evidence_bundle(
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        rows=(_row(record),),
        provenance=(_provenance(record),),
        destination=destination,
    )
    evidence_path = destination / "comparison_evidence.jsonl"
    payload = evidence_path.read_text(encoding="utf-8")
    evidence_path.write_text(payload.replace("state-real-v2", "state-tampered-v2"), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint|evidence"):
        read_fast_deterministic_comparison_evidence_bundle(destination)


def test_bundle_manifest_detects_feature_file_tampering(tmp_path: Path) -> None:
    record = _record()
    destination = tmp_path / "feature-tampered"
    write_fast_deterministic_comparison_evidence_bundle(
        feature_dataset=_dataset(record),
        catalog=_catalog(),
        rows=(_row(record),),
        provenance=(_provenance(record),),
        destination=destination,
    )
    feature_path = destination / "fast_training_features.parquet"
    feature_path.write_bytes(feature_path.read_bytes() + b"tamper")

    with pytest.raises((ValueError, OSError), match="fingerprint|Parquet|parquet|magic"):
        read_fast_deterministic_comparison_evidence_bundle(destination)


def test_bundle_source_excludes_future_labels_io_authority_and_live() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "evidence_bundle.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "future_path",
        "counterfactual",
        "sqlite3",
        "requests.",
        "httpx",
        "subprocess",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source
