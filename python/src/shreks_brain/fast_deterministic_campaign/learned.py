from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
    FastCampaignDecisionRequest,
    FastCampaignDecisionResults,
    build_fast_campaign_decision_batch,
    build_fast_campaign_decision_request,
)
from shreks_brain.fast_campaign_offline import (
    evaluate_fast_campaign_decision_batch_offline,
)
from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperCandidateIdentity,
    FastCampaignPaperRunResult,
    run_fast_campaign_paper_candidate,
)
from shreks_brain.fast_paper import (
    FastPaperBuyOutcome,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
)
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPositionState,
)
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord
from shreks_brain.risk import RiskPolicy

from .paper_evidence import (
    FastDeterministicCampaignPaperEvidence,
    materialize_fast_campaign_paper_evidence,
)
from .risk_context import build_fast_deterministic_campaign_risk_context


_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class FastLearnedCampaignRow:
    record: FastTrainingFeatureRecord
    flat_constraints: FastCampaignActionConstraints
    open_constraints: FastCampaignActionConstraints
    paper_evidence: FastDeterministicCampaignPaperEvidence

    def __post_init__(self) -> None:
        if type(self.record) is not FastTrainingFeatureRecord:
            raise ValueError("record must be exact FastTrainingFeatureRecord")
        if type(self.flat_constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "flat_constraints must be exact FastCampaignActionConstraints"
            )
        if type(self.open_constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "open_constraints must be exact FastCampaignActionConstraints"
            )
        if (
            type(self.paper_evidence)
            is not FastDeterministicCampaignPaperEvidence
        ):
            raise ValueError(
                "paper_evidence must be exact FastDeterministicCampaignPaperEvidence"
            )


def run_fast_learned_chronological_campaign(
    *,
    decision_binary_path: str | Path,
    champion_path: str | Path,
    identity: FastCampaignPaperCandidateIdentity,
    policy: FastCampaignContinuousActionPolicy,
    rows: tuple[FastLearnedCampaignRow, ...],
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastCampaignPaperRunResult:
    binary, champion = _preflight(
        decision_binary_path=decision_binary_path,
        champion_path=champion_path,
        identity=identity,
        policy=policy,
        rows=rows,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
    )

    requests: tuple[FastCampaignDecisionRequest, ...] = ()
    latest_decisions: FastCampaignDecisionResults | None = None
    evidence_points = ()
    latest_result: FastCampaignPaperRunResult | None = None

    for row in rows:
        market_key = _market_key(row.record)
        position = _paper_position(
            latest_decisions,
            latest_result,
            market_key,
        )
        constraints = (
            row.flat_constraints
            if position.kind == "FLAT"
            else row.open_constraints
        )
        request = build_fast_campaign_decision_request(
            row.record,
            position,
            constraints,
        )
        requests = (*requests, request)
        batch = build_fast_campaign_decision_batch(policy, requests)
        results = evaluate_fast_campaign_decision_batch_offline(
            binary_path=binary,
            champion_path=champion,
            batch=batch,
        )

        _require_stable_prefix(
            previous=latest_decisions,
            current=results,
        )
        decision = results.decisions[-1]
        _require_decision_matches_position(decision, position)

        raw_evidence = _resolve_candidate_risk_context(
            latest_result=latest_result,
            starting_ledger=starting_ledger,
            action=decision.action,
            evidence=row.paper_evidence,
        )
        paper_evidence = materialize_fast_campaign_paper_evidence(
            source_event_id=decision.source_event_id,
            action=decision.action,
            as_of_unix_ms=decision.as_of_unix_ms,
            evidence=raw_evidence,
        )
        evidence_points = (*evidence_points, paper_evidence)
        latest_result = run_fast_campaign_paper_candidate(
            identity=identity,
            decisions=results,
            evidence=evidence_points,
            starting_ledger=starting_ledger,
            fill_policy=fill_policy,
            risk_policy=risk_policy,
            position_policy=position_policy,
            evaluation_policy=evaluation_policy,
        )
        latest_decisions = results

    if latest_result is None:
        raise ValueError(
            "non-empty learned campaign must produce a final PAPER result"
        )
    return latest_result


def _preflight(
    *,
    decision_binary_path: str | Path,
    champion_path: str | Path,
    identity: FastCampaignPaperCandidateIdentity,
    policy: FastCampaignContinuousActionPolicy,
    rows: tuple[FastLearnedCampaignRow, ...],
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> tuple[Path, Path]:
    binary = _source_file(
        decision_binary_path,
        "decision_binary_path",
    )
    champion = _source_file(champion_path, "champion_path")
    if type(identity) is not FastCampaignPaperCandidateIdentity:
        raise ValueError(
            "identity must be exact FastCampaignPaperCandidateIdentity"
        )
    if type(policy) is not FastCampaignContinuousActionPolicy:
        raise ValueError(
            "policy must be exact FastCampaignContinuousActionPolicy"
        )
    if type(starting_ledger) is not PaperLedger:
        raise ValueError("starting_ledger must be exact PaperLedger")
    if type(fill_policy) is not PaperFillPolicy:
        raise ValueError("fill_policy must be exact PaperFillPolicy")
    if type(risk_policy) is not RiskPolicy:
        raise ValueError("risk_policy must be exact RiskPolicy")
    if type(position_policy) is not FastPaperPositionActionPolicy:
        raise ValueError(
            "position_policy must be exact FastPaperPositionActionPolicy"
        )
    if type(evaluation_policy) is not TradingEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact TradingEvaluationPolicy"
        )
    if not math.isclose(
        evaluation_policy.starting_equity_usd,
        starting_ledger.starting_cash_usd,
        rel_tol=_REL_TOL,
        abs_tol=_ABS_TOL,
    ):
        raise ValueError(
            "evaluation starting equity must equal starting PAPER cash"
        )
    if any(
        value.state is PaperPositionState.OPEN
        for value in starting_ledger.positions
    ):
        raise ValueError(
            "learned campaign requires a starting ledger with no OPEN positions"
        )
    if (
        not isinstance(rows, tuple)
        or not rows
        or not all(type(value) is FastLearnedCampaignRow for value in rows)
    ):
        raise ValueError(
            "rows must be a non-empty tuple of exact FastLearnedCampaignRow values"
        )

    seen: set[str] = set()
    previous_sequence: int | None = None
    latest_at_by_market: dict[str, int] = {}
    for index, row in enumerate(rows):
        record = row.record
        source_event_id = (
            f"{record.decision_signature}:{record.decision_ordinal}"
        )
        if row.paper_evidence.source_event_id != source_event_id:
            raise ValueError(
                f"learned campaign PAPER source identity mismatch at row {index}"
            )
        if source_event_id in seen:
            raise ValueError(
                "learned campaign contains duplicate source identity"
            )
        seen.add(source_event_id)
        if (
            previous_sequence is not None
            and record.decision_sequence <= previous_sequence
        ):
            raise ValueError(
                "learned campaign decision sequence must strictly increase"
            )
        previous_sequence = record.decision_sequence

        market_key = _market_key(record)
        previous_at = latest_at_by_market.get(market_key)
        if (
            previous_at is not None
            and record.decision_observed_at_unix_ms < previous_at
        ):
            raise ValueError(
                "learned campaign per-market decision time cannot move backward"
            )
        latest_at_by_market[market_key] = (
            record.decision_observed_at_unix_ms
        )
    return binary, champion


def _require_stable_prefix(
    *,
    previous: FastCampaignDecisionResults | None,
    current: FastCampaignDecisionResults,
) -> None:
    if type(current) is not FastCampaignDecisionResults:
        raise ValueError(
            "Rust learned campaign result must be exact FastCampaignDecisionResults"
        )
    if previous is None:
        if len(current.decisions) != 1:
            raise ValueError(
                "first learned campaign Rust prefix must contain exactly one decision"
            )
        return
    if current.champion_version != previous.champion_version:
        raise ValueError("learned campaign champion version drift")
    if (
        current.champion_fingerprint_sha256
        != previous.champion_fingerprint_sha256
    ):
        raise ValueError("learned campaign champion fingerprint drift")
    if len(current.decisions) != len(previous.decisions) + 1:
        raise ValueError(
            "learned campaign Rust prefix length drift"
        )
    if current.decisions[:-1] != previous.decisions:
        raise ValueError(
            "learned campaign Rust history drift in prior decision prefix"
        )


def _require_decision_matches_position(
    decision: object,
    position: FastCampaignDecisionPosition,
) -> None:
    current = getattr(decision, "current_exposure_fraction", None)
    if position.kind == "FLAT":
        if not isinstance(current, (int, float)) or not math.isclose(
            float(current),
            0.0,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        ):
            raise ValueError(
                "learned FLAT decision current exposure does not match actual PAPER posture"
            )
        return
    expected = position.current_exposure_fraction
    assert expected is not None
    if (
        isinstance(current, bool)
        or not isinstance(current, (int, float))
        or not math.isclose(
            float(current),
            expected,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        )
    ):
        raise ValueError(
            "learned OPEN decision current exposure does not match actual PAPER posture"
        )


def _paper_position(
    decisions: FastCampaignDecisionResults | None,
    result: FastCampaignPaperRunResult | None,
    market_key: str,
) -> FastCampaignDecisionPosition:
    if decisions is None or result is None:
        return FastCampaignDecisionPosition(kind="FLAT")

    market_positions, market_exposures = _reconstruct_market_state(
        decisions,
        result,
    )
    position_id = market_positions.get(market_key)
    if position_id is None:
        if market_key in market_exposures:
            raise ValueError(
                "FLAT learned market cannot retain reconstructed exposure"
            )
        return FastCampaignDecisionPosition(kind="FLAT")

    exposure = market_exposures.get(market_key)
    if exposure is None:
        raise ValueError(
            "OPEN learned market is missing reconstructed exposure"
        )
    position = next(
        (
            value
            for value in result.final_ledger.positions
            if value.position_id == position_id
        ),
        None,
    )
    if position is None or position.state is not PaperPositionState.OPEN:
        raise ValueError(
            "reconstructed learned OPEN market must match authoritative OPEN ledger position"
        )
    return FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=exposure,
    )


def _reconstruct_market_state(
    decisions: FastCampaignDecisionResults,
    result: FastCampaignPaperRunResult,
) -> tuple[dict[str, str], dict[str, float]]:
    buy_results = iter(result.buy_results)
    position_results = iter(result.position_results)
    market_positions: dict[str, str] = {}
    market_exposures: dict[str, float] = {}

    for decision in decisions.decisions:
        if decision.action == "SKIP":
            continue
        if decision.action == "BUY":
            try:
                buy_result = next(buy_results)
            except StopIteration as exc:
                raise ValueError(
                    "learned PAPER result is missing BUY outcome"
                ) from exc
            if buy_result.source_event_id != decision.source_event_id:
                raise ValueError(
                    "learned PAPER BUY result source identity mismatch"
                )
            if buy_result.outcome is FastPaperBuyOutcome.FILLED:
                update = buy_result.ledger_update
                if (
                    update is None
                    or update.state is not PaperLedgerUpdateState.APPLIED
                    or update.position_id is None
                ):
                    raise ValueError(
                        "FILLED learned BUY requires authoritative APPLIED position update"
                    )
                market_positions[decision.market_key] = update.position_id
                market_exposures[decision.market_key] = (
                    decision.target_exposure_fraction
                )
            continue

        try:
            position_result = next(position_results)
        except StopIteration as exc:
            raise ValueError(
                "learned PAPER result is missing position-action outcome"
            ) from exc
        if (
            position_result.applied_assessment.source_event_id
            != decision.source_event_id
        ):
            raise ValueError(
                "learned PAPER position result source identity mismatch"
            )
        if decision.market_key not in market_positions:
            raise ValueError(
                "learned PAPER position result exists without reconstructed OPEN market"
            )
        if position_result.outcome is FastPaperPositionOutcome.SOLD:
            market_positions.pop(decision.market_key, None)
            market_exposures.pop(decision.market_key, None)
        elif position_result.outcome is FastPaperPositionOutcome.REDUCED:
            target = decision.target_exposure_fraction
            if (
                not math.isfinite(target)
                or target <= 0.0
                or target > 1.0
            ):
                raise ValueError(
                    "learned REDUCE target exposure is invalid"
                )
            market_exposures[decision.market_key] = target

    try:
        next(buy_results)
    except StopIteration:
        pass
    else:
        raise ValueError(
            "learned PAPER result contains extra BUY outcomes"
        )
    try:
        next(position_results)
    except StopIteration:
        pass
    else:
        raise ValueError(
            "learned PAPER result contains extra position-action outcomes"
        )
    return market_positions, market_exposures


def _resolve_candidate_risk_context(
    *,
    latest_result: FastCampaignPaperRunResult | None,
    starting_ledger: PaperLedger,
    action: str,
    evidence: FastDeterministicCampaignPaperEvidence,
) -> FastDeterministicCampaignPaperEvidence:
    if action != "BUY" or evidence.risk_context is not None:
        return evidence
    environment = evidence.risk_environment
    if environment is None:
        return evidence
    ledger = (
        starting_ledger
        if latest_result is None
        else latest_result.final_ledger
    )
    context = build_fast_deterministic_campaign_risk_context(
        ledger,
        environment,
        as_of_unix_ms=evidence.evaluated_at_unix_ms,
    )
    return replace(
        evidence,
        risk_context=context,
        risk_environment=None,
    )


def _market_key(record: FastTrainingFeatureRecord) -> str:
    return f"{record.venue}:{record.mint}:{record.quote_mint}"


def _source_file(value: str | Path, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{name} must be a string or Path")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"{name} must be explicit and non-empty")
    path = Path(value)
    if not path.is_file():
        raise ValueError(f"{name} must identify an existing file")
    return path
