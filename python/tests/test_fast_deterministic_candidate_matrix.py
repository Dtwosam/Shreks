from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.evaluation import (
    TradingEvaluationEvidence,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.fast_campaign_paper import FastCampaignPaperQuoteEvidence
from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignPaperEvidence,
    FastDeterministicCampaignRow,
    FastDeterministicCandidateCampaignSpec,
    FastDeterministicCandidateMatrixResult,
    run_fast_deterministic_candidate_matrix,
)
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_candidate_manifest,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
)
from shreks_brain.fast_paper import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperEventRecord,
    FastPaperLoopState,
    FastPaperMarketCursor,
)
from shreks_brain.fast_policy_proof import (
    FastPolicyRunEvidence,
    build_fast_policy_run_evidence,
)
from shreks_brain.paper import PaperQuoteState, create_paper_ledger
from shreks_brain.research.fast_training_features import (
    DEFAULT_FAST_WINDOWS_MS,
    FastTrainingFeatureRecord,
    FastTrainingWindowSummary,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_candidate_manifest_v1.json"
)
T0 = 40_000_000
MARKET = "pump_fun_bonding_curve:mint-matrix:quote-matrix"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _manifest(version: str):
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["candidate_version"] = version
    document["strategy_version"] = f"{version}-strategy"
    document.pop("candidate_fingerprint_sha256")
    document["candidate_fingerprint_sha256"] = hashlib.sha256(
        _canonical(document).encode("utf-8")
    ).hexdigest()
    return decode_fast_deterministic_candidate_manifest(_canonical(document))


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


def _record(signature: str = "matrix-1", sequence: int = 1) -> FastTrainingFeatureRecord:
    return FastTrainingFeatureRecord(
        schema_name="shreks.fast_lane_training_features",
        schema_version=1,
        decision_signature=signature,
        decision_ordinal=0,
        decision_sequence=sequence,
        mint="mint-matrix",
        quote_mint="quote-matrix",
        venue="pump_fun_bonding_curve",
        decision_observed_at_unix_ms=T0 + sequence * 100,
        decision_provider="helius",
        decision_source_observed_at_unix_ms=T0 + sequence * 100 - 1,
        decision_occurred_at_unix_ms=T0 + sequence * 100 - 2,
        decision_slot=100 + sequence,
        decision_event_kind="buy",
        decision_actor=None,
        decision_executable_entry_price_quote=10.0,
        decision_entry_total_quote=100.0,
        snapshot_as_of_unix_ms=T0 + sequence * 100,
        snapshot_last_sequence=sequence,
        snapshot_last_price_quote=10.0,
        last_reserve_context=None,
        last_lifecycle_event=None,
        windows=tuple(_window(value) for value in DEFAULT_FAST_WINDOWS_MS),
    )


def _quote(execution: float = 10.1) -> FastCampaignPaperQuoteEvidence:
    return FastCampaignPaperQuoteEvidence(
        provider="fixture",
        mint="mint-matrix",
        quote_mint="quote-matrix",
        observed_at_unix_ms=T0 + 200,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=10.0,
        execution_price_quote=execution,
        quoted_base_quantity=10.0,
        available_base_quantity=10.0,
        quote_to_usd_rate=1.0,
    )


def _paper(
    source_event_id: str = "matrix-1:0",
    *,
    state_version: str = "state-v1",
    quote: FastCampaignPaperQuoteEvidence | None = None,
) -> FastDeterministicCampaignPaperEvidence:
    return FastDeterministicCampaignPaperEvidence(
        source_event_id=source_event_id,
        state_version=state_version,
        evaluated_at_unix_ms=T0 + 200,
        quote=_quote() if quote is None else quote,
        risk_context=None,
        entry_authority=None,
        market_regime=None,
    )


def _row(
    *,
    record: FastTrainingFeatureRecord | None = None,
    paper: FastDeterministicCampaignPaperEvidence | None = None,
) -> FastDeterministicCampaignRow:
    return FastDeterministicCampaignRow(
        record=_record() if record is None else record,
        flat_evidence=FastOfflineImpulseScalpEvidence(execution=None),
        open_evidence=FastOfflineLongerRunnerEvidence(
            protective=FastOfflineLongerRunnerProtective(
                hard_stop_triggered=False,
                risk_limit_exit_required=False,
                liquidity_exit_required=False,
            ),
            continuation=None,
        ),
        paper_evidence=_paper() if paper is None else paper,
    )


def _spec(version: str, row: FastDeterministicCampaignRow | None = None):
    return FastDeterministicCandidateCampaignSpec(
        manifest=_manifest(version),
        rows=(_row() if row is None else row,),
        paper_run_id=f"paper-{version}",
    )


def _evaluation_policy() -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="matrix-eval-v1",
        starting_equity_usd=10_000.0,
        calibration_bucket_count=10,
    )


def _run_evidence(manifest, paper_run_id: str, action: FastPaperAction):
    assessment = FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id="matrix-1:0",
        market_key=MARKET,
        source_sequence=1,
        as_of_unix_ms=T0 + 100,
        strategy_family=manifest.strategy_family,
        strategy_version=manifest.strategy_version,
        action=action,
        reasons=("matrix_fixture",),
    )
    loop = FastPaperLoopState(
        version=FAST_PAPER_EVENT_LOOP_VERSION,
        market_cursors=(
            FastPaperMarketCursor(
                market_key=MARKET,
                last_source_sequence=1,
                last_as_of_unix_ms=T0 + 100,
            ),
        ),
        records=(
            FastPaperEventRecord(
                source_event_id="matrix-1:0",
                update_fingerprint="1" * 64,
                market_key=MARKET,
                source_sequence=1,
                as_of_unix_ms=T0 + 100,
                is_material=True,
                assessment=assessment,
            ),
        ),
    )
    policy = _evaluation_policy()
    report = evaluate_trading_performance(
        (),
        (),
        policy,
        manifest.candidate_version,
    )
    evaluation = TradingEvaluationEvidence(
        candidate_version=manifest.candidate_version,
        policy=policy,
        trades=(),
        probability_observations=(),
        report=report,
    )
    return build_fast_policy_run_evidence(
        paper_run_id=paper_run_id,
        candidate_fingerprint_sha256=manifest.candidate_fingerprint_sha256,
        strategy_version=manifest.strategy_version,
        loop_state=loop,
        trading_evaluation=evaluation,
    )


def _common(binary: Path, specs):
    return dict(
        binary_path=binary,
        specs=specs,
        assessment_version="assessment-v1",
        starting_ledger=create_paper_ledger(10_000.0, T0),
        fill_policy=object(),
        risk_policy=object(),
        position_policy=object(),
        evaluation_policy=_evaluation_policy(),
    )


def test_record_population_mismatch_fails_before_any_candidate_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "row"
    binary.write_text("unused", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.matrix.run_fast_deterministic_chronological_campaign",
        lambda **kwargs: calls.append(kwargs["manifest"].candidate_version),
    )
    changed = replace(_record(), decision_sequence=2)
    specs = (
        _spec("baseline-a"),
        _spec("baseline-b", _row(record=changed)),
    )

    with pytest.raises(ValueError, match="population|record"):
        run_fast_deterministic_candidate_matrix(**_common(binary, specs))

    assert calls == []


@pytest.mark.parametrize(
    "changed",
    (
        _paper(state_version="other-state"),
        _paper(quote=_quote(10.2)),
    ),
)
def test_shared_state_or_quote_mismatch_fails_before_run(
    tmp_path: Path,
    monkeypatch,
    changed,
) -> None:
    binary = tmp_path / "row"
    binary.write_text("unused", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.matrix.run_fast_deterministic_chronological_campaign",
        lambda **kwargs: calls.append(kwargs["manifest"].candidate_version),
    )
    specs = (
        _spec("baseline-a"),
        _spec("baseline-b", _row(paper=changed)),
    )

    with pytest.raises(ValueError, match="state|quote|population"):
        run_fast_deterministic_candidate_matrix(**_common(binary, specs))

    assert calls == []


def test_candidates_must_be_unique_and_lexical_before_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "row"
    binary.write_text("unused", encoding="utf-8")
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.matrix.run_fast_deterministic_chronological_campaign",
        lambda **kwargs: pytest.fail("candidate runner must not launch"),
    )

    with pytest.raises(ValueError, match="lexical|order"):
        run_fast_deterministic_candidate_matrix(
            **_common(binary, (_spec("baseline-b"), _spec("baseline-a")))
        )
    with pytest.raises(ValueError, match="duplicate|unique"):
        run_fast_deterministic_candidate_matrix(
            **_common(binary, (_spec("baseline-a"), _spec("baseline-a")))
        )


def test_action_divergence_keeps_same_sealed_population_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    binary = tmp_path / "row"
    binary.write_text("unused", encoding="utf-8")
    specs = (_spec("baseline-a"), _spec("baseline-b"))
    actions = {
        "baseline-a": FastPaperAction.BUY,
        "baseline-b": FastPaperAction.SKIP,
    }

    def fake_runner(**kwargs):
        manifest = kwargs["manifest"]
        run = _run_evidence(
            manifest,
            kwargs["paper_run_id"],
            actions[manifest.candidate_version],
        )
        return SimpleNamespace(latest_result=SimpleNamespace(run_evidence=run))

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.matrix.run_fast_deterministic_chronological_campaign",
        fake_runner,
    )

    result = run_fast_deterministic_candidate_matrix(**_common(binary, specs))

    assert type(result) is FastDeterministicCandidateMatrixResult
    assert tuple(run.candidate_version for run in result.runs) == (
        "baseline-a",
        "baseline-b",
    )
    assert all(type(run) is FastPolicyRunEvidence for run in result.runs)
    assert len({run.event_population_fingerprint_sha256 for run in result.runs}) == 1
    assert result.event_population_fingerprint_sha256 == (
        result.runs[0].event_population_fingerprint_sha256
    )
    assert (
        result.runs[0].action_journal_fingerprint_sha256
        != result.runs[1].action_journal_fingerprint_sha256
    )
    assert all(
        run.trading_evaluation.policy == _evaluation_policy()
        for run in result.runs
    )


def test_matrix_source_has_no_superiority_process_or_execution_authority() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
    )
    source = (root / "matrix.py").read_text(encoding="utf-8")

    assert "run_fast_deterministic_chronological_campaign(" in source
    for forbidden in (
        "evaluate_fast_policy_superiority",
        "import subprocess",
        "subprocess.run",
        "requests.",
        "sqlite3",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "RuntimeMode",
        "sign_transaction",
        "submit_transaction",
        "promotion",
    ):
        assert forbidden not in source
