from __future__ import annotations

import os
from pathlib import Path

from shreks_brain.paper_evaluation import (
    PaperEvaluationEvidenceStore,
    PaperEvaluationLedger,
)
from shreks_brain.paper_loop import (
    PaperCycleResult,
    PaperLoopFinding,
    PaperLoopReasonCode,
    PaperLoopState,
    run_paper_cycle,
)
from shreks_brain.paper_validation import (
    AccountingValidationStatus,
    PaperCheckpointError,
    PaperCheckpointRecord,
    load_latest_paper_checkpoint,
    save_paper_checkpoint,
    validate_paper_accounting,
    validate_restart_equivalence,
)
from shreks_brain.registry import RegistryCandidate

from .assembler import (
    ObserverFreshLaunchPolicyBundle,
    ObserverPaperAssemblyError,
    assemble_observer_paper_cycle,
)
from .models import ObserverPaperRiskEnvironment


class ObserverPaperCampaignError(ValueError):
    """Raised when an observer-backed paper campaign cannot advance safely."""


class ObserverPaperCampaignRunner:
    """Restart-safe paper-only bridge from observer evidence to C5/C6/E11."""

    def __init__(
        self,
        observer_database_path: str | os.PathLike[str],
        evidence_path: str | os.PathLike[str],
        candidate: RegistryCandidate,
        paper_run_id: str,
        initial_state: PaperLoopState,
        policy_bundle: ObserverFreshLaunchPolicyBundle,
        risk_environment: ObserverPaperRiskEnvironment,
        *,
        global_risk_halt: bool,
    ) -> None:
        if type(candidate) is not RegistryCandidate:
            raise ObserverPaperCampaignError(
                "candidate must be an exact RegistryCandidate"
            )
        if not isinstance(paper_run_id, str) or not paper_run_id.strip():
            raise ObserverPaperCampaignError("paper_run_id must be non-empty")
        if type(initial_state) is not PaperLoopState:
            raise ObserverPaperCampaignError(
                "initial_state must be an exact PaperLoopState"
            )
        if type(policy_bundle) is not ObserverFreshLaunchPolicyBundle:
            raise ObserverPaperCampaignError(
                "policy_bundle must be an exact ObserverFreshLaunchPolicyBundle"
            )
        if type(risk_environment) is not ObserverPaperRiskEnvironment:
            raise ObserverPaperCampaignError(
                "risk_environment must be an exact ObserverPaperRiskEnvironment"
            )
        if type(global_risk_halt) is not bool:
            raise ObserverPaperCampaignError("global_risk_halt must be a boolean")
        if candidate.strategy_version != policy_bundle.fresh_launch_policy.version:
            raise ObserverPaperCampaignError(
                "registry candidate strategy attribution does not match Fresh Launch policy"
            )
        if candidate.feature_schema_version != policy_bundle.score_policy.required_feature_schema_version:
            raise ObserverPaperCampaignError(
                "registry candidate feature attribution does not match bundled score policy"
            )

        try:
            self._observer_database_path = Path(observer_database_path).expanduser().resolve()
            self._evidence_path = Path(evidence_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ObserverPaperCampaignError("campaign paths are invalid") from error

        self._candidate = candidate
        self._paper_run_id = paper_run_id
        self._initial_state = initial_state
        self._policy_bundle = policy_bundle
        self._risk_environment = risk_environment
        self._global_risk_halt = global_risk_halt
        self._evidence_store = PaperEvaluationEvidenceStore(self._evidence_path)

        self._require_accounting_not_invalid(initial_state, "initial state")

    def load_state(self) -> PaperLoopState:
        state, _ = self._load_state_and_checkpoint()
        return state

    def run_cycle(
        self,
        as_of_unix_ms: int,
        created_at_unix_ms: int,
    ) -> PaperCycleResult:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
        if created_at_unix_ms < as_of_unix_ms:
            raise ObserverPaperCampaignError(
                "created_at_unix_ms cannot precede cycle as_of_unix_ms"
            )

        state, checkpoint = self._load_state_and_checkpoint()
        if as_of_unix_ms < state.last_cycle_at_unix_ms:
            raise ObserverPaperCampaignError(
                "cycle timestamp cannot precede restored paper state"
            )
        if as_of_unix_ms == state.last_cycle_at_unix_ms:
            if checkpoint is None:
                raise ObserverPaperCampaignError(
                    "cycle timestamp matches initial state but no completed checkpoint exists"
                )
            return _idempotent_replay_result(state, as_of_unix_ms)

        try:
            cycle, _audit = assemble_observer_paper_cycle(
                self._observer_database_path,
                state,
                as_of_unix_ms,
                self._policy_bundle,
                self._risk_environment,
                global_risk_halt=self._global_risk_halt,
            )
        except ObserverPaperAssemblyError as error:
            raise ObserverPaperCampaignError(
                f"observer cycle assembly failed: {error}"
            ) from error

        try:
            result = run_paper_cycle(state, cycle)
        except (TypeError, ValueError) as error:
            raise ObserverPaperCampaignError(
                f"sealed paper cycle execution failed: {error}"
            ) from error

        self._require_accounting_not_invalid(result.next_state, "cycle result")

        # Evidence is committed before the checkpoint. E11 merge is semantic and
        # idempotent, so an interrupted checkpoint write can be safely retried.
        try:
            evidence = self._evidence_store.record_cycle(
                self._paper_run_id,
                self._candidate,
                result,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ObserverPaperCampaignError(
                f"paper evaluation evidence write failed: {error}"
            ) from error
        self._require_evidence_attribution(evidence)

        sequence = 1 if checkpoint is None else checkpoint.sequence + 1
        try:
            saved = save_paper_checkpoint(
                self._observer_database_path,
                self._paper_run_id,
                sequence,
                result.next_state,
                created_at_unix_ms,
            )
        except PaperCheckpointError as error:
            raise ObserverPaperCampaignError(
                f"paper checkpoint write failed: {error}"
            ) from error

        restored = self._load_checkpoint()
        if restored is None or restored.sequence != saved.sequence:
            raise ObserverPaperCampaignError(
                "paper checkpoint reload did not return the saved sequence"
            )
        restart_report = validate_restart_equivalence(
            result.next_state,
            restored.state,
        )
        if not restart_report.equivalent:
            raise ObserverPaperCampaignError(
                "paper checkpoint restart equivalence failed"
            )
        self._require_accounting_not_invalid(restored.state, "restored checkpoint")
        return result

    def evaluated_trades(self):
        evidence = self._load_evidence()
        self._require_evidence_attribution(evidence)
        try:
            return self._evidence_store.evaluated_trades(
                self._paper_run_id,
                self._candidate.candidate_version,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ObserverPaperCampaignError(
                f"paper evaluation evidence normalization failed: {error}"
            ) from error

    def _load_state_and_checkpoint(
        self,
    ) -> tuple[PaperLoopState, PaperCheckpointRecord | None]:
        evidence = self._load_evidence()
        self._require_evidence_attribution(evidence)
        checkpoint = self._load_checkpoint()
        state = self._initial_state if checkpoint is None else checkpoint.state
        self._require_accounting_not_invalid(state, "restored state")
        return state, checkpoint

    def _load_checkpoint(self) -> PaperCheckpointRecord | None:
        try:
            return load_latest_paper_checkpoint(
                self._observer_database_path,
                self._paper_run_id,
            )
        except PaperCheckpointError as error:
            raise ObserverPaperCampaignError(
                f"paper checkpoint load failed: {error}"
            ) from error

    def _load_evidence(self) -> PaperEvaluationLedger:
        try:
            return self._evidence_store.load()
        except (OSError, TypeError, ValueError) as error:
            raise ObserverPaperCampaignError(
                f"paper evaluation evidence load failed: {error}"
            ) from error

    def _require_evidence_attribution(
        self,
        ledger: PaperEvaluationLedger,
    ) -> None:
        expected = (
            self._candidate.candidate_version,
            self._candidate.candidate_fingerprint_sha256,
            self._candidate.strategy_version,
        )
        values = (
            ledger.entry_provenance
            + ledger.executions
            + ledger.closures
            + ledger.orphan_costs
        )
        for value in values:
            if value.paper_run_id != self._paper_run_id:
                continue
            actual = (
                value.candidate_version,
                value.candidate_fingerprint_sha256,
                value.strategy_version,
            )
            if actual != expected:
                raise ObserverPaperCampaignError(
                    "paper-run attribution conflicts with the registry candidate"
                )

    @staticmethod
    def _require_accounting_not_invalid(
        state: PaperLoopState,
        label: str,
    ) -> None:
        try:
            report = validate_paper_accounting(state)
        except (TypeError, ValueError) as error:
            raise ObserverPaperCampaignError(
                f"{label} accounting validation failed: {error}"
            ) from error
        if report.status is AccountingValidationStatus.INVALID:
            raise ObserverPaperCampaignError(
                f"{label} accounting is invalid"
            )


def _idempotent_replay_result(
    state: PaperLoopState,
    as_of_unix_ms: int,
) -> PaperCycleResult:
    return PaperCycleResult(
        policy_version=state.loop_policy.version,
        as_of_unix_ms=as_of_unix_ms,
        next_state=state,
        pending_entry_result=None,
        entry_results=(),
        exit_results=(),
        findings=(
            PaperLoopFinding(
                PaperLoopReasonCode.CYCLE_APPLIED,
                "exact completed paper cycle replay is idempotent",
            ),
        ),
    )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverPaperCampaignError(
            f"{name} must be a non-negative integer"
        )
