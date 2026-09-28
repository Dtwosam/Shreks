from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowPendingBuyRetryInput,
    build_fast_paper_shadow_pending_buy_retry_source_record,
    execute_fast_paper_shadow_decision,
    produce_fast_paper_shadow_execution_input_source_record,
    retry_fast_paper_shadow_pending_buy,
    write_fast_paper_runtime_manifest,
    write_fast_paper_shadow_decision_evidence,
    write_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_execution_policy,
    write_fast_paper_shadow_pending_buy_retry_source_record,
)
from shreks_brain.fast_paper_shadow_sample_proof import (
    FastPaperShadowSamplePolicy,
    canonical_fast_paper_shadow_sample_proof,
    summarize_fast_paper_shadow_independent_sample,
)
from shreks_brain.paper import PaperPositionState
from shreks_brain.regime import MarketRegime

import shreks_brain.fast_paper_shadow_latency_proof as latency

from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _risk, _usd
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _persist,
    _record_at,
    _runtime_fixture,
    _source,
)


def _proof_policy(
    *,
    version: str = "fl11.3-test-v1",
    max_fraction: float = 1.0,
    max_unbooked: float = 0.0,
) -> latency.FastPaperShadowLatencyProofPolicy:
    return latency.FastPaperShadowLatencyProofPolicy(
        version=version,
        min_buy_decision_count=1,
        min_booked_entry_count=1,
        min_distinct_selected_horizon_count=1,
        max_unbooked_buy_fraction=max_unbooked,
        max_p95_event_to_booked_horizon_fraction=max_fraction,
        max_p99_event_to_booked_horizon_fraction=max_fraction,
    )


def _sample_checkpoint(mint: str):
    return SimpleNamespace(
        state=SimpleNamespace(
            ledger=SimpleNamespace(
                positions=(
                    SimpleNamespace(
                        position_id="latency-closed-fixture",
                        mint=mint,
                        state=PaperPositionState.CLOSED,
                        closed_at_unix_ms=20_500,
                    ),
                )
            )
        )
    )


def _write_sample(
    tmp_path: Path,
    *,
    manifest,
    binding,
    buy,
    skip,
) -> Path:
    sample = summarize_fast_paper_shadow_independent_sample(
        (buy, skip),
        buy_regimes={
            buy.evidence_fingerprint_sha256: MarketRegime.NORMAL,
        },
        missing_buy_execution_source_count=0,
        checkpoint=_sample_checkpoint(buy.feature_record.mint),
        policy=FastPaperShadowSamplePolicy(
            version="fl11.3-test-sample-v1",
            min_decision_count=2,
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
        since_unix_ms=19_900,
        until_unix_ms=21_000,
    )
    assert sample["decision"] == "SUFFICIENT_SAMPLE"
    path = tmp_path / "sample.json"
    path.write_text(
        canonical_fast_paper_shadow_sample_proof(sample),
        encoding="utf-8",
    )
    return path


def _authority_files(tmp_path: Path, manifest, policy):
    manifest_path = tmp_path / "manifest.json"
    policy_path = tmp_path / "execution-policy.json"
    write_fast_paper_runtime_manifest(manifest, manifest_path)
    write_fast_paper_shadow_execution_policy(policy, policy_path)
    return manifest_path, policy_path


def _decision_population(monkeypatch, manifest):
    base = _record()
    buy = _evidence_for(
        monkeypatch,
        manifest,
        base,
        action="BUY",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    skip_record = _record_at(
        base,
        signature="latency-skip",
        sequence=2,
        at=20_300,
    )
    skip = _evidence_for(
        monkeypatch,
        manifest,
        skip_record,
        action="SKIP",
        position=FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at=20_320,
        entry_observed_at=20_310,
        exit_observed_at=20_315,
    )
    return base, buy, skip


def _write_decisions(root: Path, *values) -> None:
    root.mkdir()
    for evidence in values:
        write_fast_paper_shadow_decision_evidence(
            evidence,
            root
            / f"shadow-{evidence.source_sequence:020d}-"
            f"{evidence.evidence_fingerprint_sha256[:16]}.json",
        )


def _collect(
    *,
    manifest,
    binding,
    manifest_path: Path,
    policy_path: Path,
    decision_root: Path,
    source_root: Path,
    retry_root: Path,
    sample_path: Path,
    proof_policy: latency.FastPaperShadowLatencyProofPolicy,
):
    return latency.collect_fast_paper_shadow_latency_proof(
        manifest_path=manifest_path,
        execution_policy_path=policy_path,
        ledger_database_path=Path(binding.database_path),
        run_id=binding.run_id,
        decision_evidence_directory=decision_root,
        execution_source_directory=source_root,
        pending_buy_retry_source_directory=retry_root,
        sample_proof_path=sample_path,
        latency_policy=proof_policy,
        expected_release_sha=manifest.release_source_sha,
        since_unix_ms=19_900,
        until_unix_ms=21_000,
    )


def test_immediate_buy_latency_is_joined_from_event_to_booked_entry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint0, posture0 = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base, buy, skip = _decision_population(monkeypatch, manifest)
    source_root = tmp_path / "sources"
    retry_root = tmp_path / "retries"
    decision_root = tmp_path / "decisions"
    source_root.mkdir()
    retry_root.mkdir()
    _write_decisions(decision_root, buy, skip)

    source = _source(base, buy)
    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint0,
        posture0,
        source,
        source_observed_at_unix_ms=buy.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        source_root,
    )
    transition = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint0,
        posture0,
        source,
    )
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        transition,
        sequence=1,
        created_at=20_020,
    )
    assert checkpoint1.state.ledger.positions[0].state.value == "OPEN"
    assert len(posture1.market_positions) == 1

    manifest_path, policy_path = _authority_files(
        tmp_path,
        manifest,
        policy,
    )
    sample_path = _write_sample(
        tmp_path,
        manifest=manifest,
        binding=binding,
        buy=buy,
        skip=skip,
    )

    report = _collect(
        manifest=manifest,
        binding=binding,
        manifest_path=manifest_path,
        policy_path=policy_path,
        decision_root=decision_root,
        source_root=source_root,
        retry_root=retry_root,
        sample_path=sample_path,
        proof_policy=_proof_policy(),
    )

    assert report["decision"] == "LATENCY_PROVEN"
    assert report["buy_decision_count"] == 1
    assert report["booked_entry_count"] == 1
    observation = report["buy_observations"][0]
    assert observation["status"] == "BOOKED_IMMEDIATE"
    assert observation["event_to_evaluation_ms"] == pytest.approx(20.0)
    assert observation["decision_to_booked_entry_ms"] == pytest.approx(0.0)
    assert observation["event_to_booked_entry_ms"] == pytest.approx(20.0)
    assert observation[
        "event_to_booked_fraction_of_selected_horizon"
    ] == pytest.approx(20.0 / 250.0)
    assert observation["within_selected_horizon"] is True
    assert report["event_to_booked_entry_ms"]["p95"] == pytest.approx(20.0)
    assert report["promotion_authority"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"


def test_deferred_buy_retry_latency_is_attributed_to_original_buy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint0, posture0 = _runtime_fixture(
        tmp_path,
    )
    base, buy, skip = _decision_population(monkeypatch, manifest)
    source_root = tmp_path / "sources"
    retry_root = tmp_path / "retries"
    decision_root = tmp_path / "decisions"
    source_root.mkdir()
    retry_root.mkdir()
    _write_decisions(decision_root, buy, skip)

    source = _source(base, buy)
    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint0,
        posture0,
        source,
        source_observed_at_unix_ms=buy.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
    )
    write_fast_paper_shadow_execution_input_source_record(
        source_record,
        source_root,
    )
    deferred = execute_fast_paper_shadow_decision(
        manifest,
        policy,
        binding,
        checkpoint0,
        posture0,
        source,
    )
    checkpoint1, posture1 = _persist(
        manifest,
        binding,
        deferred,
        sequence=1,
        created_at=20_020,
    )
    assert checkpoint1.state.pending_buy is not None

    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=20_200,
        quote=replace(
            buy.entry_quote,
            observed_at_unix_ms=20_150,
            reference_price_quote=1.02,
            execution_price_quote=1.03,
        ),
        risk_context=_risk(20_200),
        quote_usd_evidence=_usd(base, observed_at=20_190),
    )
    retry_source = build_fast_paper_shadow_pending_buy_retry_source_record(
        manifest,
        binding,
        policy,
        checkpoint1,
        posture1,
        retry,
        risk_day_started_at_unix_ms=0,
        source_observed_at_unix_ms=20_195,
    )
    write_fast_paper_shadow_pending_buy_retry_source_record(
        retry_source,
        retry_root,
    )
    filled = retry_fast_paper_shadow_pending_buy(
        manifest,
        policy,
        binding,
        checkpoint1,
        posture1,
        retry,
    )
    checkpoint2, posture2 = _persist(
        manifest,
        binding,
        filled,
        sequence=2,
        created_at=20_200,
    )
    assert checkpoint2.state.pending_buy is None
    assert len(posture2.market_positions) == 1

    manifest_path, policy_path = _authority_files(
        tmp_path,
        manifest,
        policy,
    )
    sample_path = _write_sample(
        tmp_path,
        manifest=manifest,
        binding=binding,
        buy=buy,
        skip=skip,
    )

    report = _collect(
        manifest=manifest,
        binding=binding,
        manifest_path=manifest_path,
        policy_path=policy_path,
        decision_root=decision_root,
        source_root=source_root,
        retry_root=retry_root,
        sample_path=sample_path,
        proof_policy=_proof_policy(),
    )

    observation = report["buy_observations"][0]
    assert observation["status"] == "BOOKED_RETRY"
    assert observation["retry_count"] == 1
    assert observation["event_to_evaluation_ms"] == pytest.approx(20.0)
    assert observation["decision_to_booked_entry_ms"] == pytest.approx(180.0)
    assert observation["event_to_booked_entry_ms"] == pytest.approx(200.0)
    assert observation[
        "event_to_booked_fraction_of_selected_horizon"
    ] == pytest.approx(0.8)
    assert report["decision"] == "LATENCY_PROVEN"

    strict = _collect(
        manifest=manifest,
        binding=binding,
        manifest_path=manifest_path,
        policy_path=policy_path,
        decision_root=decision_root,
        source_root=source_root,
        retry_root=retry_root,
        sample_path=sample_path,
        proof_policy=_proof_policy(
            version="fl11.3-strict-v1",
            max_fraction=0.5,
        ),
    )
    assert strict["decision"] == "LATENCY_NOT_PROVEN"
    by_code = {
        gate["code"]: gate
        for gate in strict["gate_results"]
    }
    assert by_code[
        "MAX_P95_EVENT_TO_BOOKED_HORIZON_FRACTION"
    ]["status"] == "FAIL"


def test_missing_execution_source_stays_explicit_and_cannot_prove_latency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, _checkpoint0, _posture0 = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    _base, buy, skip = _decision_population(monkeypatch, manifest)
    source_root = tmp_path / "sources"
    retry_root = tmp_path / "retries"
    decision_root = tmp_path / "decisions"
    source_root.mkdir()
    retry_root.mkdir()
    _write_decisions(decision_root, buy, skip)

    manifest_path, policy_path = _authority_files(
        tmp_path,
        manifest,
        policy,
    )
    sample_path = _write_sample(
        tmp_path,
        manifest=manifest,
        binding=binding,
        buy=buy,
        skip=skip,
    )

    report = _collect(
        manifest=manifest,
        binding=binding,
        manifest_path=manifest_path,
        policy_path=policy_path,
        decision_root=decision_root,
        source_root=source_root,
        retry_root=retry_root,
        sample_path=sample_path,
        proof_policy=_proof_policy(max_unbooked=1.0),
    )

    assert report["decision"] == "LATENCY_NOT_PROVEN"
    assert report["booked_entry_count"] == 0
    assert report["unbooked_buy_count"] == 1
    assert report["status_counts"] == {
        "MISSING_EXECUTION_SOURCE": 1,
    }
    assert report["event_to_booked_entry_ms"]["p95"] is None


def test_latency_proof_fails_closed_on_historical_source_binding_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, binding, policy, checkpoint0, posture0 = _runtime_fixture(
        tmp_path,
        zero_latency=True,
    )
    base, buy, skip = _decision_population(monkeypatch, manifest)
    source_root = tmp_path / "sources"
    retry_root = tmp_path / "retries"
    decision_root = tmp_path / "decisions"
    source_root.mkdir()
    retry_root.mkdir()
    _write_decisions(decision_root, buy, skip)

    source_record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        binding,
        policy,
        checkpoint0,
        posture0,
        _source(base, buy),
        source_observed_at_unix_ms=buy.evaluated_at_unix_ms,
        risk_day_started_at_unix_ms=0,
    )
    source_path = write_fast_paper_shadow_execution_input_source_record(
        source_record,
        source_root,
    )
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["paper_checkpoint_payload_sha256"] = "f" * 64
    source_path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path, policy_path = _authority_files(
        tmp_path,
        manifest,
        policy,
    )
    sample_path = _write_sample(
        tmp_path,
        manifest=manifest,
        binding=binding,
        buy=buy,
        skip=skip,
    )

    with pytest.raises(
        latency.FastPaperShadowLatencyProofError,
        match="binding|historical|source",
    ):
        _collect(
            manifest=manifest,
            binding=binding,
            manifest_path=manifest_path,
            policy_path=policy_path,
            decision_root=decision_root,
            source_root=source_root,
            retry_root=retry_root,
            sample_path=sample_path,
            proof_policy=_proof_policy(max_unbooked=1.0),
        )


def test_latency_horizon_aggregation_reconciles_multiple_horizons() -> None:
    base = {
        "source_sequence": 1,
        "source_event_id": "event-a",
        "decision_evidence_fingerprint_sha256": "a" * 64,
        "as_of_unix_ms": 1_000,
        "evaluated_at_unix_ms": 1_010,
        "selected_horizon_ms": 100,
        "event_to_evaluation_ms": 10.0,
        "decision_compute_ms": 0.2,
    }
    observations = (
        latency._booked(
            base,
            status="BOOKED_IMMEDIATE",
            booked_at_unix_ms=1_020,
            retry_count=0,
        ),
        latency._booked(
            {
                **base,
                "source_sequence": 2,
                "source_event_id": "event-b",
                "decision_evidence_fingerprint_sha256": "b" * 64,
                "as_of_unix_ms": 2_000,
                "evaluated_at_unix_ms": 2_020,
                "selected_horizon_ms": 200,
                "event_to_evaluation_ms": 20.0,
                "decision_compute_ms": 0.4,
            },
            status="BOOKED_RETRY",
            booked_at_unix_ms=2_100,
            retry_count=1,
        ),
        latency._booked(
            {
                **base,
                "source_sequence": 3,
                "source_event_id": "event-c",
                "decision_evidence_fingerprint_sha256": "c" * 64,
                "as_of_unix_ms": 3_000,
                "evaluated_at_unix_ms": 3_030,
                "selected_horizon_ms": 200,
                "event_to_evaluation_ms": 30.0,
                "decision_compute_ms": 0.6,
            },
            status="BOOKED_RETRY",
            booked_at_unix_ms=3_180,
            retry_count=2,
        ),
    )

    overall = latency._summarize_observations(observations)
    by_horizon = latency._summarize_by_horizon(observations)
    latency._reconcile_horizons(overall, by_horizon)

    assert [item["selected_horizon_ms"] for item in by_horizon] == [
        100,
        200,
    ]
    assert sum(item["buy_decision_count"] for item in by_horizon) == 3
    assert sum(item["booked_entry_count"] for item in by_horizon) == 3
    assert overall["event_to_booked_entry_ms"] == {
        "p50": 100.0,
        "p95": 180.0,
        "p99": 180.0,
        "max": 180.0,
    }
    assert overall["event_to_booked_fraction_of_selected_horizon"][
        "p95"
    ] == pytest.approx(0.9)


def test_latency_policy_codec_and_packaging_firewall() -> None:
    policy = _proof_policy()
    payload = latency.encode_fast_paper_shadow_latency_proof_policy(
        policy
    )
    assert (
        latency.decode_fast_paper_shadow_latency_proof_policy(payload)
        == policy
    )
    assert latency.fast_paper_shadow_latency_proof_policy_fingerprint_sha256(
        policy
    ) == latency.hashlib.sha256(payload.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError):
        replace(policy, max_unbooked_buy_fraction=1.1)
    with pytest.raises(ValueError):
        replace(policy, min_booked_entry_count=0)

    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(latency.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-latency-proof = '
        '"shreks_brain.fast_paper_shadow_latency_proof:main"'
    ) in pyproject

    for required in (
        "reconstruct_fast_paper_shadow_decision",
        "reconstruct_fast_paper_shadow_pending_buy_retry",
        "_require_successor",
        "_require_retry_successor",
        "event_to_booked_fraction_of_selected_horizon",
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
