from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
    FastDeterministicLifecycleDecision,
    build_fast_deterministic_lifecycle_results,
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
from shreks_brain.risk import RiskPolicy

from .engine import run_fast_deterministic_lifecycle_paper_candidate
from .models import (
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperRunResult,
)


FAST_DETERMINISTIC_PAPER_SESSION_VERSION = "fl9-deterministic-paper-session-v1"
_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class FastDeterministicPaperPosture:
    market_key: str
    posture: str
    current_exposure_fraction: float | None
    position_id: str | None
    opened_at_unix_ms: int | None

    def __post_init__(self) -> None:
        _require_non_empty_string("market_key", self.market_key)
        if self.posture == "FLAT":
            if any(
                value is not None
                for value in (
                    self.current_exposure_fraction,
                    self.position_id,
                    self.opened_at_unix_ms,
                )
            ):
                raise ValueError("FLAT posture cannot carry OPEN position state")
            return
        if self.posture != "OPEN":
            raise ValueError("posture must be FLAT or OPEN")
        if self.current_exposure_fraction is None:
            raise ValueError("OPEN posture requires current_exposure_fraction")
        _require_exposure(
            "current_exposure_fraction",
            self.current_exposure_fraction,
        )
        if self.position_id is None:
            raise ValueError("OPEN posture requires position_id")
        _require_non_empty_string("position_id", self.position_id)
        if self.opened_at_unix_ms is None:
            raise ValueError("OPEN posture requires opened_at_unix_ms")
        _require_non_negative_int("opened_at_unix_ms", self.opened_at_unix_ms)


@dataclass(frozen=True, slots=True)
class FastDeterministicPaperSession:
    version: str
    manifest: FastDeterministicCandidateManifest
    paper_run_id: str
    assessment_version: str
    starting_ledger: PaperLedger
    fill_policy: PaperFillPolicy
    risk_policy: RiskPolicy
    position_policy: FastPaperPositionActionPolicy
    evaluation_policy: TradingEvaluationPolicy
    decisions: tuple[FastDeterministicLifecycleDecision, ...]
    evidence: tuple[FastCampaignPaperDecisionEvidence, ...]
    latest_result: FastCampaignPaperRunResult | None

    def __post_init__(self) -> None:
        if self.version != FAST_DETERMINISTIC_PAPER_SESSION_VERSION:
            raise ValueError("unsupported deterministic PAPER session version")
        if type(self.manifest) is not FastDeterministicCandidateManifest:
            raise ValueError("manifest must be exact FastDeterministicCandidateManifest")
        _require_non_empty_string("paper_run_id", self.paper_run_id)
        _require_non_empty_string("assessment_version", self.assessment_version)
        if type(self.starting_ledger) is not PaperLedger:
            raise ValueError("starting_ledger must be exact PaperLedger")
        if type(self.fill_policy) is not PaperFillPolicy:
            raise ValueError("fill_policy must be exact PaperFillPolicy")
        if type(self.risk_policy) is not RiskPolicy:
            raise ValueError("risk_policy must be exact RiskPolicy")
        if type(self.position_policy) is not FastPaperPositionActionPolicy:
            raise ValueError(
                "position_policy must be exact FastPaperPositionActionPolicy"
            )
        if type(self.evaluation_policy) is not TradingEvaluationPolicy:
            raise ValueError(
                "evaluation_policy must be exact TradingEvaluationPolicy"
            )
        if (
            not isinstance(self.decisions, tuple)
            or not all(
                type(value) is FastDeterministicLifecycleDecision
                for value in self.decisions
            )
        ):
            raise ValueError(
                "decisions must be a tuple of exact FastDeterministicLifecycleDecision values"
            )
        if (
            not isinstance(self.evidence, tuple)
            or not all(
                type(value) is FastCampaignPaperDecisionEvidence
                for value in self.evidence
            )
        ):
            raise ValueError(
                "evidence must be a tuple of exact FastCampaignPaperDecisionEvidence values"
            )
        if len(self.decisions) != len(self.evidence):
            raise ValueError("session decision/evidence lengths must match")
        if self.decisions:
            if type(self.latest_result) is not FastCampaignPaperRunResult:
                raise ValueError(
                    "non-empty session requires exact latest FastCampaignPaperRunResult"
                )
            assert self.latest_result is not None
            if self.latest_result.identity.candidate_version != self.manifest.candidate_version:
                raise ValueError("session result candidate identity mismatch")
            if (
                self.latest_result.identity.candidate_fingerprint_sha256
                != self.manifest.candidate_fingerprint_sha256
            ):
                raise ValueError("session result candidate fingerprint mismatch")
        elif self.latest_result is not None:
            raise ValueError("empty session cannot carry latest_result")


def create_fast_deterministic_paper_session(
    *,
    manifest: FastDeterministicCandidateManifest,
    paper_run_id: str,
    assessment_version: str,
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicPaperSession:
    if type(starting_ledger) is not PaperLedger:
        raise ValueError("starting_ledger must be exact PaperLedger")
    if any(
        position.state is PaperPositionState.OPEN
        for position in starting_ledger.positions
    ):
        raise ValueError(
            "deterministic PAPER session requires a starting ledger with no OPEN positions"
        )
    return FastDeterministicPaperSession(
        version=FAST_DETERMINISTIC_PAPER_SESSION_VERSION,
        manifest=manifest,
        paper_run_id=paper_run_id,
        assessment_version=assessment_version,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
        decisions=(),
        evidence=(),
        latest_result=None,
    )


def fast_deterministic_paper_session_posture(
    session: FastDeterministicPaperSession,
    market_key: str,
) -> FastDeterministicPaperPosture:
    if type(session) is not FastDeterministicPaperSession:
        raise ValueError("session must be exact FastDeterministicPaperSession")
    _require_non_empty_string("market_key", market_key)
    if session.latest_result is None:
        return FastDeterministicPaperPosture(
            market_key=market_key,
            posture="FLAT",
            current_exposure_fraction=None,
            position_id=None,
            opened_at_unix_ms=None,
        )

    market_positions, market_exposures = _reconstruct_market_state(session)
    position_id = market_positions.get(market_key)
    if position_id is None:
        if market_key in market_exposures:
            raise ValueError("FLAT reconstructed market cannot retain exposure")
        return FastDeterministicPaperPosture(
            market_key=market_key,
            posture="FLAT",
            current_exposure_fraction=None,
            position_id=None,
            opened_at_unix_ms=None,
        )

    exposure = market_exposures.get(market_key)
    if exposure is None:
        raise ValueError("OPEN reconstructed market is missing exposure")
    result = session.latest_result
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
            "reconstructed OPEN market must match authoritative OPEN ledger position"
        )
    return FastDeterministicPaperPosture(
        market_key=market_key,
        posture="OPEN",
        current_exposure_fraction=exposure,
        position_id=position_id,
        opened_at_unix_ms=position.opened_at_unix_ms,
    )


def apply_fast_deterministic_paper_session_step(
    session: FastDeterministicPaperSession,
    decision: FastDeterministicLifecycleDecision,
    evidence: FastCampaignPaperDecisionEvidence,
) -> FastDeterministicPaperSession:
    if type(session) is not FastDeterministicPaperSession:
        raise ValueError("session must be exact FastDeterministicPaperSession")
    if type(decision) is not FastDeterministicLifecycleDecision:
        raise ValueError(
            "decision must be exact FastDeterministicLifecycleDecision"
        )
    if type(evidence) is not FastCampaignPaperDecisionEvidence:
        raise ValueError(
            "evidence must be exact FastCampaignPaperDecisionEvidence"
        )
    if evidence.source_event_id != decision.source_event_id:
        raise ValueError("decision/evidence source_event_id mismatch")

    posture = fast_deterministic_paper_session_posture(
        session,
        decision.market_key,
    )
    if decision.posture != posture.posture:
        raise ValueError(
            "deterministic lifecycle decision posture does not match actual PAPER session posture"
        )
    if posture.posture == "FLAT":
        if decision.current_exposure_fraction is not None:
            raise ValueError(
                "FLAT deterministic lifecycle decision must have null current exposure"
            )
    else:
        assert posture.current_exposure_fraction is not None
        if decision.current_exposure_fraction is None or not math.isclose(
            decision.current_exposure_fraction,
            posture.current_exposure_fraction,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        ):
            raise ValueError(
                "OPEN deterministic lifecycle decision current exposure does not match actual PAPER session exposure"
            )

    decisions = (*session.decisions, decision)
    evidence_points = (*session.evidence, evidence)
    batch = build_fast_deterministic_lifecycle_results(
        session.manifest.lifecycle_policy,
        decisions,
    )
    result = run_fast_deterministic_lifecycle_paper_candidate(
        manifest=session.manifest,
        paper_run_id=session.paper_run_id,
        assessment_version=session.assessment_version,
        decisions=batch,
        evidence=evidence_points,
        starting_ledger=session.starting_ledger,
        fill_policy=session.fill_policy,
        risk_policy=session.risk_policy,
        position_policy=session.position_policy,
        evaluation_policy=session.evaluation_policy,
    )
    return FastDeterministicPaperSession(
        version=session.version,
        manifest=session.manifest,
        paper_run_id=session.paper_run_id,
        assessment_version=session.assessment_version,
        starting_ledger=session.starting_ledger,
        fill_policy=session.fill_policy,
        risk_policy=session.risk_policy,
        position_policy=session.position_policy,
        evaluation_policy=session.evaluation_policy,
        decisions=decisions,
        evidence=evidence_points,
        latest_result=result,
    )


def _reconstruct_market_state(
    session: FastDeterministicPaperSession,
) -> tuple[dict[str, str], dict[str, float]]:
    result = session.latest_result
    if result is None:
        return {}, {}

    buy_results = iter(result.buy_results)
    position_results = iter(result.position_results)
    market_positions: dict[str, str] = {}
    market_exposures: dict[str, float] = {}
    decision_targets = {
        decision.source_event_id: decision.target_exposure_fraction
        for decision in session.decisions
    }

    for decision in session.decisions:
        if decision.action == "SKIP":
            continue
        if decision.action == "BUY":
            try:
                buy_result = next(buy_results)
            except StopIteration as exc:
                raise ValueError(
                    "session PAPER result is missing BUY outcome"
                ) from exc
            if buy_result.source_event_id != decision.source_event_id:
                raise ValueError("session BUY result source identity mismatch")
            if buy_result.outcome is FastPaperBuyOutcome.FILLED:
                update = buy_result.ledger_update
                if (
                    update is None
                    or update.state is not PaperLedgerUpdateState.APPLIED
                    or update.position_id is None
                ):
                    raise ValueError(
                        "FILLED session BUY requires authoritative APPLIED position update"
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
                "session PAPER result is missing position-action outcome"
            ) from exc
        if (
            position_result.applied_assessment.source_event_id
            != decision.source_event_id
        ):
            raise ValueError(
                "session position result source identity mismatch"
            )
        if decision.market_key not in market_positions:
            raise ValueError(
                "session position result exists without reconstructed OPEN market"
            )

        if position_result.outcome is FastPaperPositionOutcome.SOLD:
            market_positions.pop(decision.market_key, None)
            market_exposures.pop(decision.market_key, None)
        elif position_result.outcome is FastPaperPositionOutcome.REDUCED:
            active_exit = position_result.active_exit
            if active_exit is None:
                raise ValueError(
                    "REDUCED session position result requires active exit approval"
                )
            target = decision_targets.get(
                active_exit.assessment.source_event_id
            )
            if target is None:
                raise ValueError(
                    "REDUCED session position result references unknown decision target"
                )
            _require_exposure("reduced target exposure", target)
            market_exposures[decision.market_key] = target

    try:
        next(buy_results)
    except StopIteration:
        pass
    else:
        raise ValueError("session PAPER result contains extra BUY outcomes")

    try:
        next(position_results)
    except StopIteration:
        pass
    else:
        raise ValueError(
            "session PAPER result contains extra position-action outcomes"
        )

    return market_positions, market_exposures


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
        or value > 1.0
    ):
        raise ValueError(f"{name} must be finite and within (0, 1]")
