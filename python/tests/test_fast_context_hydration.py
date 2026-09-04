from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import shreks_brain.fast_context_hydration as hydration_module
from fast_chronological_fixtures import (
    HORIZON_MS,
    chronological_bundle,
)
from fast_forecast_evaluation_fixtures import chronological_policy
from fast_forecast_fixtures import WSOL
from shreks_brain.fast_context_hydration import (
    FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_NAME,
    FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_VERSION,
    FastForecastContextHydrationPolicy,
    decode_fast_forecast_context_hydration_policy,
    encode_fast_forecast_context_hydration_policy,
    hydrate_fast_forecast_evaluation_contexts,
    read_fast_forecast_context_hydration_artifact,
    write_fast_forecast_context_hydration_artifact,
)
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_market import ObserverCandidateIdentity
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.regime import RegimeMarketWindow, RegimePolicy
from shreks_brain.safety import SafetyPolicy


TAKER = "TakerContext111"


def _policy(**overrides) -> FastForecastContextHydrationPolicy:
    values = dict(
        version="fl9-context-hydration-v1",
        strategy_families=("fast-learned",),
        regime_read_policy=ObserverRegimeReadPolicy(
            version="regime-read-context-v1",
            window_ms=1_000,
            max_snapshot_age_ms=500,
            source_priority=("dexscreener",),
            entry_probe_policy_version="probe-context-v1",
            quote_asset_mint=WSOL,
            entry_input_amount=1_000_000_000,
            taker=TAKER,
            slippage_bps=75,
        ),
        regime_policy=RegimePolicy(
            version="regime-context-v1",
            max_source_age_ms=500,
            min_window_seconds=1.0,
            min_candidate_samples=1,
            dead_max_candidate_rate_per_hour=0.0,
            weak_min_candidate_rate_per_hour=0.0,
            hot_min_candidate_rate_per_hour=0.1,
            dead_max_executable_fraction=0.0,
            weak_min_executable_fraction=0.0,
            hot_min_executable_fraction=0.5,
            weak_min_median_liquidity_usd=0.0,
            hot_min_median_liquidity_usd=1.0,
            weak_min_median_volume_m5_usd=0.0,
            hot_min_median_volume_m5_usd=1.0,
            min_performance_sample_count=1,
            dead_performance_expectancy_pct=-10.0,
            weak_performance_expectancy_pct=0.0,
        ),
        safety_policy=SafetyPolicy(
            version="safety-context-v1",
            min_liquidity_usd=0.0,
            soft_min_liquidity_usd=0.0,
            max_top_holder_concentration_pct=100.0,
            soft_max_top_holder_concentration_pct=100.0,
            soft_max_creator_concentration_pct=100.0,
            soft_max_exit_price_impact_pct=100.0,
            max_critical_data_age_ms=1_000,
        ),
        safety_probe_identity=ObserverSafetyProbeIdentity(
            probe_policy_version="probe-context-v1",
            output_mint=WSOL,
            input_amount=1_000_000,
            taker=TAKER,
            slippage_bps=75,
        ),
        global_risk_halt=False,
        exit_quote_provider="jupiter",
        quote_asset_decimals=9,
        max_exit_quote_age_ms=100,
        execution_cost_policy_version="cost-context-v1",
        expected_round_trip_cost_bps=12.5,
    )
    values.update(overrides)
    return FastForecastContextHydrationPolicy(**values)


class _FakeMarketStore:
    records_by_mint = {}

    def __init__(self, _path) -> None:
        pass

    def resolve_candidate(self, mint: str):
        record = self.records_by_mint[mint]
        return ObserverCandidateIdentity(
            candidate_id=record.decision_sequence,
            mint=mint,
            pair_address=f"pair-{record.decision_sequence}",
            discovery_source="fixture",
            discovered_at_unix_ms=max(
                0, record.decision_observed_at_unix_ms - 500
            ),
            venue=record.venue,
        )


class _FakeCampaignStore:
    records_by_sequence = {}
    mutate_database: Path | None = None

    def __init__(self, _path) -> None:
        pass

    def build_regime_market_window(
        self,
        as_of_unix_ms,
        _regime_read_policy,
        _safety_policy,
        _safety_probe_identity,
        *,
        global_risk_halt,
    ):
        assert global_risk_halt is False
        if self.mutate_database is not None:
            path = self.mutate_database
            self.__class__.mutate_database = None
            path.write_bytes(path.read_bytes() + b"mutation")
        return RegimeMarketWindow(
            as_of_unix_ms=as_of_unix_ms,
            source_observed_at_unix_ms=as_of_unix_ms - 1,
            window_started_at_unix_ms=max(0, as_of_unix_ms - 1_000),
            candidate_count=1,
            executable_candidate_count=1,
            median_liquidity_usd=100.0,
            median_volume_m5_usd=50.0,
        )

    def latest_paper_quote(
        self,
        identity: ObserverPaperQuoteIdentity,
        as_of_unix_ms: int,
    ):
        assert identity.purpose is ObserverPaperQuotePurpose.EXIT
        sequence = identity.candidate_id
        if sequence % 5 == 0:
            return None
        if sequence % 4 == 0:
            quoted_at = as_of_unix_ms - 101
        else:
            quoted_at = as_of_unix_ms - 10
        if sequence % 3 == 0:
            return ObserverPaperQuoteEvidence(
                identity=identity,
                output_amount=0,
                minimum_output_amount=0,
                route_available=False,
                price_impact_pct=None,
                route_labels=(),
                quoted_at_unix_ms=quoted_at,
            )
        return ObserverPaperQuoteEvidence(
            identity=identity,
            output_amount=2_600_000_000,
            minimum_output_amount=2_500_000_000,
            route_available=True,
            price_impact_pct="0.2",
            route_labels=("Raydium",),
            quoted_at_unix_ms=quoted_at,
        )


def _install_stores(monkeypatch, bundle) -> None:
    records = {value.mint: value for value in bundle.features.records}
    _FakeMarketStore.records_by_mint = records
    _FakeCampaignStore.records_by_sequence = {
        value.decision_sequence: value for value in bundle.features.records
    }
    _FakeCampaignStore.mutate_database = None
    monkeypatch.setattr(
        hydration_module,
        "ObserverMarketStore",
        _FakeMarketStore,
    )
    monkeypatch.setattr(
        hydration_module,
        "ObserverCampaignStore",
        _FakeCampaignStore,
    )


def _prediction_identities(run):
    return tuple(
        prediction.decision_identity
        for fold in run.fold_results
        for prediction in (
            *fold.validation_predictions,
            *fold.test_predictions,
        )
    )


def test_hydration_policy_codec_is_canonical_and_authenticated() -> None:
    policy = _policy()

    payload = encode_fast_forecast_context_hydration_policy(policy)
    assert payload.endswith("\n")
    assert '"$float"' in payload
    decoded = decode_fast_forecast_context_hydration_policy(payload)
    assert decoded == policy
    assert encode_fast_forecast_context_hydration_policy(decoded) == payload


def test_hydrator_uses_exact_sealed_fl83_prediction_population(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle(shared_mint=True)
    _install_stores(monkeypatch, bundle)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")

    result = hydrate_fast_forecast_evaluation_contexts(
        bundle=bundle,
        observer_database_path=database,
        validation_policy=chronological_policy(),
        horizon_ms=HORIZON_MS,
        hydration_policy=_policy(),
    )

    expected = _prediction_identities(result.population_validation_run)
    actual = tuple(value.decision_identity for value in result.context_corpus.contexts)
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)
    assert len(actual) < len(bundle.features.records)
    assert all(value.strategy_families == ("fast-learned",) for value in result.context_corpus.contexts)
    assert all(value.market_regime == "HOT" for value in result.context_corpus.contexts)
    assert all(value.expected_round_trip_cost_bps == 12.5 for value in result.context_corpus.contexts)
    assert result.context_count == len(actual)
    assert (
        result.available_exit_capacity_count
        + result.unavailable_exit_route_count
        + result.missing_or_stale_exit_quote_count
        == result.context_count
    )


def test_hydrator_uses_conservative_exit_capacity_and_preserves_unknowns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle()
    _install_stores(monkeypatch, bundle)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")

    result = hydrate_fast_forecast_evaluation_contexts(
        bundle=bundle,
        observer_database_path=database,
        validation_policy=chronological_policy(),
        horizon_ms=HORIZON_MS,
        hydration_policy=_policy(),
    )
    by_sequence = {
        value.decision_identity[2]: value
        for value in result.context_corpus.contexts
    }

    for sequence, context in by_sequence.items():
        if sequence % 5 == 0 or sequence % 4 == 0:
            assert context.executable_exit_capacity_quote is None
        elif sequence % 3 == 0:
            assert context.executable_exit_capacity_quote == 0.0
        else:
            assert context.executable_exit_capacity_quote == 2.5


def test_hydrator_rejects_candidate_venue_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle()
    _install_stores(monkeypatch, bundle)
    first_eval = next(
        record
        for record in bundle.features.records
        if record.decision_observed_at_unix_ms >= 2_000
    )
    original = _FakeMarketStore.resolve_candidate

    def _wrong(self, mint):
        candidate = original(self, mint)
        if mint == first_eval.mint:
            return replace(candidate, venue="wrong-venue")
        return candidate

    monkeypatch.setattr(_FakeMarketStore, "resolve_candidate", _wrong)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")

    with pytest.raises(ValueError, match="venue"):
        hydrate_fast_forecast_evaluation_contexts(
            bundle=bundle,
            observer_database_path=database,
            validation_policy=chronological_policy(),
            horizon_ms=HORIZON_MS,
            hydration_policy=_policy(),
        )


def test_hydration_artifact_binds_db_wal_policy_population_and_contexts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle()
    _install_stores(monkeypatch, bundle)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"observer-wal")
    destination = tmp_path / "hydration"

    manifest = write_fast_forecast_context_hydration_artifact(
        bundle=bundle,
        observer_database_path=database,
        validation_policy=chronological_policy(),
        horizon_ms=HORIZON_MS,
        hydration_policy=_policy(),
        destination=destination,
    )
    reopened = read_fast_forecast_context_hydration_artifact(destination)

    assert manifest.schema_name == FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_NAME
    assert manifest.schema_version == FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_VERSION
    assert reopened.manifest == manifest
    assert reopened.policy == _policy()
    assert reopened.context_corpus.context_fingerprint_sha256 == (
        manifest.context_fingerprint_sha256
    )
    assert reopened.population_validation_run_fingerprint_sha256 == (
        manifest.population_validation_run_fingerprint_sha256
    )
    assert {value.name for value in destination.iterdir()} == {
        "contexts.json",
        "policy.json",
        "manifest.json",
    }


def test_hydration_artifact_rejects_db_race_and_publishes_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle()
    _install_stores(monkeypatch, bundle)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")
    _FakeCampaignStore.mutate_database = database
    destination = tmp_path / "hydration"

    with pytest.raises(ValueError, match="database.*changed|source.*changed"):
        write_fast_forecast_context_hydration_artifact(
            bundle=bundle,
            observer_database_path=database,
            validation_policy=chronological_policy(),
            horizon_ms=HORIZON_MS,
            hydration_policy=_policy(),
            destination=destination,
        )
    assert not destination.exists()


def test_hydration_reader_rejects_context_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bundle = chronological_bundle()
    _install_stores(monkeypatch, bundle)
    database = tmp_path / "shreks.db"
    database.write_bytes(b"observer-fixture")
    destination = tmp_path / "hydration"
    write_fast_forecast_context_hydration_artifact(
        bundle=bundle,
        observer_database_path=database,
        validation_policy=chronological_policy(),
        horizon_ms=HORIZON_MS,
        hydration_policy=_policy(),
        destination=destination,
    )
    contexts = destination / "contexts.json"
    contexts.write_bytes(contexts.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="hash|fingerprint|canonical|JSON"):
        read_fast_forecast_context_hydration_artifact(destination)


def test_context_hydration_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_context_hydration.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
    ):
        assert forbidden not in source
