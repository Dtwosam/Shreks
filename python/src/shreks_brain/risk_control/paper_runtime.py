from __future__ import annotations

from shreks_brain.observer_campaign.coordinator import (
    ObserverCampaignCoordinatorError,
    ObserverPaperCampaignCoordinatorRunner,
    _coordinator_idempotent_replay_result,
    assemble_observer_paper_campaign_cycle,
)
from shreks_brain.paper_loop import PaperCycleResult, run_paper_cycle
from shreks_brain.paper_validation import (
    PaperCheckpointError,
    save_paper_checkpoint,
    validate_restart_equivalence,
)

from .integration import apply_operator_controls_to_paper_cycle


class ControlledObserverPaperCampaignCoordinatorRunner(
    ObserverPaperCampaignCoordinatorRunner
):
    """G7 wrapper that overlays one already-read operator state before execution."""

    def __init__(
        self,
        *args: object,
        operator_entry_halt_active: bool,
        operator_kill_switch_active: bool,
        **kwargs: object,
    ) -> None:
        _require_bool("operator_entry_halt_active", operator_entry_halt_active)
        _require_bool("operator_kill_switch_active", operator_kill_switch_active)
        if operator_kill_switch_active and not operator_entry_halt_active:
            raise ObserverCampaignCoordinatorError(
                "operator kill switch requires entry halt"
            )
        super().__init__(*args, **kwargs)
        self._operator_entry_halt_active = operator_entry_halt_active
        self._operator_kill_switch_active = operator_kill_switch_active

    @property
    def operator_entry_halt_active(self) -> bool:
        return self._operator_entry_halt_active

    @property
    def operator_kill_switch_active(self) -> bool:
        return self._operator_kill_switch_active

    def run_cycle(
        self,
        as_of_unix_ms: int,
        created_at_unix_ms: int,
    ) -> PaperCycleResult:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        _require_non_negative_int("created_at_unix_ms", created_at_unix_ms)
        if created_at_unix_ms < as_of_unix_ms:
            raise ObserverCampaignCoordinatorError(
                "created_at_unix_ms cannot precede cycle as_of_unix_ms"
            )

        state, checkpoint = self._load_state_and_checkpoint()
        if as_of_unix_ms < state.last_cycle_at_unix_ms:
            raise ObserverCampaignCoordinatorError(
                "cycle timestamp cannot precede restored paper state"
            )
        if as_of_unix_ms == state.last_cycle_at_unix_ms:
            if checkpoint is None:
                raise ObserverCampaignCoordinatorError(
                    "cycle timestamp matches initial state but no completed checkpoint exists"
                )
            return _coordinator_idempotent_replay_result(state, as_of_unix_ms)

        cycle, _audit = assemble_observer_paper_campaign_cycle(
            self._observer_database_path,
            state,
            as_of_unix_ms,
            self._policy_bundle,
            self._risk_environment,
            self._selection_policy,
            recent_performance=self._recent_performance,
            global_risk_halt=self._global_risk_halt,
        )
        cycle = apply_operator_controls_to_paper_cycle(
            cycle,
            halt_new_entries=self._operator_entry_halt_active,
            kill_switch_active=self._operator_kill_switch_active,
        )

        try:
            result = run_paper_cycle(state, cycle)
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"sealed paper cycle execution failed: {error}"
            ) from error

        self._require_accounting_not_invalid(result.next_state, "cycle result")

        try:
            evidence = self._evidence_store.record_cycle(
                self._paper_run_id,
                self._candidate,
                result,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
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
            raise ObserverCampaignCoordinatorError(
                f"paper checkpoint write failed: {error}"
            ) from error

        restored = self._load_checkpoint()
        if restored is None or restored.sequence != saved.sequence:
            raise ObserverCampaignCoordinatorError(
                "paper checkpoint reload did not return the saved sequence"
            )
        restart_report = validate_restart_equivalence(
            result.next_state,
            restored.state,
        )
        if not restart_report.equivalent:
            raise ObserverCampaignCoordinatorError(
                "paper checkpoint restart equivalence failed"
            )
        self._require_accounting_not_invalid(restored.state, "restored checkpoint")
        return result


def _require_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise ObserverCampaignCoordinatorError(f"{name} must be a boolean")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverCampaignCoordinatorError(
            f"{name} must be a non-negative integer"
        )
