from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION,
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicComparisonExecutionPolicy,
    FastDeterministicComparisonPointInTimeContext,
    FastDeterministicCampaignRequest,
    FastDeterministicCampaignJsonlRequest,
    build_fast_deterministic_campaign_request,
    build_fast_deterministic_campaign_jsonl_request,
    decode_fast_deterministic_campaign_request,
    encode_fast_deterministic_campaign_request,
    run_fast_deterministic_campaign_request_file,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineWalletCohortEvidence,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.paper import PaperFillPolicy
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskPolicy


T0 = 120_000_000
TOKEN = "MintRequest111"
QUOTE = "QuoteRequest111"


def _leg() -> FastOfflineExecutionLegCost:
    return FastOfflineExecutionLegCost(
        effective_fee_bps=50,
        expected_impact_bps=20,
        expected_slippage_bps=30,
        expected_latency_bps=10,
        network_fee_quote=0.01,
        priority_fee_quote=0.02,
        expected_failure_cost_quote=0.03,
    )


def _execution_policy() -> FastDeterministicComparisonExecutionPolicy:
    return FastDeterministicComparisonExecutionPolicy(
        version="fl9-real-execution-v1",
        horizon_ms=30_000,
        cost_model=FastOfflineExecutionCostModel(
            version=1,
            entry=_leg(),
            exit=_leg(),
        ),
        required_edge_bps=200,
        risk_margin_bps=100,
    )


def _context() -> FastDeterministicComparisonPointInTimeContext:
    return FastDeterministicComparisonPointInTimeContext(
        observer_candidate_id=7,
        state_version="observer-state-v1",
        evaluated_at_unix_ms=T0 + 100,
        entry_quote_identity=ObserverPaperQuoteIdentity(
            candidate_id=7,
            purpose=ObserverPaperQuotePurpose.ENTRY,
            provider="jupiter",
            probe_policy_version="probe-v2",
            input_mint=QUOTE,
            output_mint=TOKEN,
            taker="Taker111",
            input_amount=100_000_000,
            slippage_bps=75,
        ),
        exit_quote_identity=ObserverPaperQuoteIdentity(
            candidate_id=7,
            purpose=ObserverPaperQuotePurpose.EXIT,
            provider="jupiter",
            probe_policy_version="probe-v2",
            input_mint=TOKEN,
            output_mint=QUOTE,
            taker="Taker111",
            input_amount=10_000_000,
            slippage_bps=75,
        ),
        quote_asset=ObserverPaperQuoteAsset(
            mint=QUOTE,
            decimals=6,
            usd_per_token=1.0,
        ),
        graduation_boost_context=None,
        wallet_cohort_evidence=FastOfflineWalletCohortEvidence(
            evidence=None
        ),
        longer_runner_evidence=FastOfflineLongerRunnerEvidence(
            protective=FastOfflineLongerRunnerProtective(
                hard_stop_triggered=False,
                risk_limit_exit_required=False,
                liquidity_exit_required=False,
            ),
            continuation=None,
        ),
        market_regime=MarketRegime.NORMAL,
        risk_environment=FastDeterministicCampaignRiskEnvironment(
            trading_capital_usd=20_000.0,
            day_started_at_unix_ms=T0 - 10_000,
            liquidity_usd=100_000.0,
            expected_price_impact_pct=0.25,
            price_impact_notional_usd=100.0,
            market_observed_at_unix_ms=T0 + 50,
            data_healthy=True,
            execution_healthy=True,
            kill_switch_active=False,
            active_intent_keys=frozenset({"existing-intent"}),
        ),
        wallet_source_version=None,
        graduation_context_source_version="fl8.1-snapshot-v1",
        continuation_forecast_source_version=None,
        regime_source_version="observer-regime-v1",
        risk_environment_source_version="observer-risk-v1",
    )


def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-fill-v1",
        assumed_latency_ms=0,
        max_quote_lag_ms=5_000,
        swap_fee_bps=25,
        network_fee_usd=0.01,
        allow_partial_fills=False,
        min_partial_fill_fraction=1.0,
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        version="risk-v1",
        required_decision_policy_version="not-applicable:fast-deterministic",
        required_feature_schema_version="1",
        target_position_notional_usd=100.0,
        max_notional_per_position_usd=500.0,
        max_capital_fraction_per_position=0.10,
        max_simultaneous_positions=5,
        max_aggregate_open_risk_usd=2_500.0,
        max_daily_realized_loss_usd=1_000.0,
        max_rolling_drawdown_pct=20.0,
        cooldown_after_consecutive_losses=3,
        cooldown_seconds=60,
        min_liquidity_usd=10_000.0,
        max_expected_price_impact_pct=2.0,
        max_slippage_bps=500,
        max_market_data_age_ms=5_000,
    )


def _request() -> FastDeterministicCampaignRequest:
    return build_fast_deterministic_campaign_request(
        observer_database_path="evidence/observer.db",
        feature_parquet_path="evidence/fast_training_features.parquet",
        comparison_catalog_path="evidence/comparison_catalog.json",
        champion_path="models/champion.json",
        entry_authority_binary_path="bin/shreks-fast-entry-authority",
        candidate_binary_path="bin/shreks-fast-deterministic-row",
        destination_path="output/fl9-campaign",
        execution_policy=_execution_policy(),
        contexts=(_context(),),
        paper_run_id_prefix="fl9-real",
        assessment_version="assessment-v1",
        starting_cash_usd=20_000.0,
        starting_ledger_as_of_unix_ms=T0 - 20_000,
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=FastPaperPositionActionPolicy(
            version="position-v1",
            max_slippage_bps=500,
        ),
        evaluation_policy=TradingEvaluationPolicy(
            version="evaluation-v1",
            starting_equity_usd=20_000.0,
            calibration_bucket_count=10,
        ),
    )


def test_request_codec_is_canonical_authenticated_and_exact() -> None:
    request = _request()
    payload = encode_fast_deterministic_campaign_request(request)

    assert request.schema_name == FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME
    assert request.schema_version == FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION
    assert len(request.request_fingerprint_sha256) == 64
    assert payload == json.dumps(
        json.loads(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert '"$float"' in payload
    assert '"$frozenset"' in payload
    assert '"$enum"' in payload
    assert decode_fast_deterministic_campaign_request(payload) == request
    assert encode_fast_deterministic_campaign_request(
        decode_fast_deterministic_campaign_request(payload)
    ) == payload


def test_request_codec_rejects_noncanonical_raw_float_and_tampering() -> None:
    payload = encode_fast_deterministic_campaign_request(_request())
    document = json.loads(payload)

    with pytest.raises(ValueError, match="canonical"):
        decode_fast_deterministic_campaign_request(
            json.dumps(document, indent=2)
        )

    raw_float = json.loads(payload)
    raw_float["request"]["starting_cash_usd"] = 20_000.0
    with pytest.raises(ValueError, match="float|tag|encoded"):
        decode_fast_deterministic_campaign_request(
            json.dumps(
                raw_float,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    tampered = json.loads(payload)
    tampered["request_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_deterministic_campaign_request(
            json.dumps(
                tampered,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    unknown = json.loads(payload)
    unknown["request"]["execution_policy"] = {
        "$type": "DangerousDynamicType",
        "fields": {},
    }
    unknown_material = {
        "schema_name": unknown["schema_name"],
        "schema_version": unknown["schema_version"],
        "request": unknown["request"],
    }
    unknown["request_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            unknown_material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="unknown|unsupported|type"):
        decode_fast_deterministic_campaign_request(
            json.dumps(
                unknown,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


def test_request_rejects_capital_mismatch() -> None:
    with pytest.raises(ValueError, match="capital|equity|cash"):
        build_fast_deterministic_campaign_request(
            observer_database_path="observer.db",
            feature_parquet_path="features.parquet",
            comparison_catalog_path="catalog.json",
            champion_path="champion.json",
            entry_authority_binary_path="entry-authority",
            candidate_binary_path="candidate",
            destination_path="campaign",
            execution_policy=_execution_policy(),
            contexts=(_context(),),
            paper_run_id_prefix="fl9-real",
            assessment_version="assessment-v1",
            starting_cash_usd=10_000.0,
            starting_ledger_as_of_unix_ms=T0 - 20_000,
            fill_policy=_fill_policy(),
            risk_policy=_risk_policy(),
            position_policy=FastPaperPositionActionPolicy(
                version="position-v1",
                max_slippage_bps=500,
            ),
            evaluation_policy=TradingEvaluationPolicy(
                version="evaluation-v1",
                starting_equity_usd=20_000.0,
                calibration_bucket_count=10,
            ),
        )


def test_file_runner_resolves_paths_and_delegates_exact_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request_dir = tmp_path / "request"
    request_dir.mkdir()
    request = _request()
    request_path = request_dir / "campaign_request.json"
    request_path.write_text(
        encode_fast_deterministic_campaign_request(request),
        encoding="utf-8",
    )

    for relative in (
        request.observer_database_path,
        request.feature_parquet_path,
        request.comparison_catalog_path,
        request.champion_path,
        request.entry_authority_binary_path,
        request.candidate_binary_path,
    ):
        path = (request_dir / relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    features = SimpleNamespace(
        records=(SimpleNamespace(decision_observed_at_unix_ms=T0),)
    )
    catalog = object()
    captured = {}
    sentinel = SimpleNamespace(artifact_fingerprint_sha256="a" * 64)

    def fake_read_features(path):
        captured["feature_read_path"] = Path(path)
        return features

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "read_fast_training_feature_parquet",
        fake_read_features,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "decode_fast_deterministic_comparison_catalog",
        lambda payload: catalog,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "write_fast_deterministic_campaign_artifact",
        lambda **kwargs: (
            captured.update(kwargs)
            or sentinel
        ),
    )

    result = run_fast_deterministic_campaign_request_file(request_path)

    assert result is sentinel
    assert captured["database_path"] == (
        request_dir / request.observer_database_path
    ).resolve()
    assert captured["feature_read_path"] == (
        request_dir / request.feature_parquet_path
    ).resolve()
    assert captured["champion_path"] == (
        request_dir / request.champion_path
    ).resolve()
    assert captured["entry_authority_binary_path"] == (
        request_dir / request.entry_authority_binary_path
    ).resolve()
    assert captured["candidate_binary_path"] == (
        request_dir / request.candidate_binary_path
    ).resolve()
    assert captured["destination"] == (
        request_dir / request.destination_path
    ).resolve()
    assert captured["feature_dataset"] is features
    assert captured["catalog"] is catalog
    assert captured["execution_policy"] == request.execution_policy
    assert captured["contexts"] == request.contexts
    assert captured["starting_ledger"].starting_cash_usd == pytest.approx(
        request.starting_cash_usd
    )
    assert captured["starting_ledger"].as_of_unix_ms == (
        request.starting_ledger_as_of_unix_ms
    )


def test_request_module_has_no_network_superiority_promotion_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "request.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "httpx",
        "evaluate_fast_policy_superiority",
        "promotion",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "pickle",
        "eval(",
        "__import__(",
    ):
        assert forbidden not in source



def _jsonl_request() -> FastDeterministicCampaignJsonlRequest:
    return build_fast_deterministic_campaign_jsonl_request(
        observer_database_path="evidence/observer.db",
        feature_jsonl_path="evidence/fast_training_features.jsonl",
        comparison_catalog_path="evidence/comparison_catalog.json",
        champion_path="models/champion.json",
        entry_authority_binary_path="bin/shreks-fast-entry-authority",
        candidate_binary_path="bin/shreks-fast-deterministic-row",
        destination_path="output/fl9-campaign-jsonl",
        execution_policy=_execution_policy(),
        contexts=(_context(),),
        paper_run_id_prefix="fl9-real-jsonl",
        assessment_version="assessment-v1",
        starting_cash_usd=20_000.0,
        starting_ledger_as_of_unix_ms=T0 - 20_000,
        fill_policy=_fill_policy(),
        risk_policy=_risk_policy(),
        position_policy=FastPaperPositionActionPolicy(
            version="position-v1",
            max_slippage_bps=500,
        ),
        evaluation_policy=TradingEvaluationPolicy(
            version="evaluation-v1",
            starting_equity_usd=20_000.0,
            calibration_bucket_count=10,
        ),
    )


def test_jsonl_request_v2_codec_is_canonical_and_v1_round_trip_stays_exact() -> None:
    v1 = _request()
    v1_payload = encode_fast_deterministic_campaign_request(v1)
    assert decode_fast_deterministic_campaign_request(v1_payload) == v1
    assert encode_fast_deterministic_campaign_request(
        decode_fast_deterministic_campaign_request(v1_payload)
    ) == v1_payload

    request = _jsonl_request()
    payload = encode_fast_deterministic_campaign_request(request)

    assert request.schema_name == FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME
    assert request.schema_version == (
        FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION
    )
    assert "feature_jsonl_path" in json.loads(payload)["request"]
    assert "feature_parquet_path" not in json.loads(payload)["request"]
    assert decode_fast_deterministic_campaign_request(payload) == request
    assert encode_fast_deterministic_campaign_request(
        decode_fast_deterministic_campaign_request(payload)
    ) == payload


def test_jsonl_request_v2_requires_jsonl_source_path() -> None:
    request = _jsonl_request()
    with pytest.raises(ValueError, match="jsonl"):
        build_fast_deterministic_campaign_jsonl_request(
            observer_database_path=request.observer_database_path,
            feature_jsonl_path="features.parquet",
            comparison_catalog_path=request.comparison_catalog_path,
            champion_path=request.champion_path,
            entry_authority_binary_path=request.entry_authority_binary_path,
            candidate_binary_path=request.candidate_binary_path,
            destination_path=request.destination_path,
            execution_policy=request.execution_policy,
            contexts=request.contexts,
            paper_run_id_prefix=request.paper_run_id_prefix,
            assessment_version=request.assessment_version,
            starting_cash_usd=request.starting_cash_usd,
            starting_ledger_as_of_unix_ms=request.starting_ledger_as_of_unix_ms,
            fill_policy=request.fill_policy,
            risk_policy=request.risk_policy,
            position_policy=request.position_policy,
            evaluation_policy=request.evaluation_policy,
        )


def test_jsonl_file_runner_uses_canonical_jsonl_reader_not_parquet(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request_dir = tmp_path / "request"
    request_dir.mkdir()
    request = _jsonl_request()
    request_path = request_dir / "campaign_request.json"
    request_path.write_text(
        encode_fast_deterministic_campaign_request(request),
        encoding="utf-8",
    )

    for relative in (
        request.observer_database_path,
        request.feature_jsonl_path,
        request.comparison_catalog_path,
        request.champion_path,
        request.entry_authority_binary_path,
        request.candidate_binary_path,
    ):
        path = request_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    features = SimpleNamespace(
        records=(SimpleNamespace(decision_observed_at_unix_ms=T0),)
    )
    catalog = object()
    captured = {}
    sentinel = SimpleNamespace(artifact_fingerprint_sha256="a" * 64)

    def fake_read_jsonl(path):
        captured["feature_read_path"] = Path(path)
        return features

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "read_fast_training_feature_jsonl",
        fake_read_jsonl,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "read_fast_training_feature_parquet",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("JSONL v2 must not invoke Parquet reader")
        ),
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "decode_fast_deterministic_comparison_catalog",
        lambda payload: catalog,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.request."
        "write_fast_deterministic_campaign_artifact",
        lambda **kwargs: captured.update(kwargs) or sentinel,
    )

    result = run_fast_deterministic_campaign_request_file(request_path)

    assert result is sentinel
    assert captured["feature_read_path"] == (
        request_dir / request.feature_jsonl_path
    ).resolve()
    assert captured["feature_dataset"] is features
    assert captured["catalog"] is catalog
