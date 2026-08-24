from __future__ import annotations

from .models import ReplayDecisionInput, ReplayOutcomeBundle, ReplayPolicySet, ReplayRun


def replay_entry_decisions(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policies: ReplayPolicySet,
) -> ReplayRun:
    raise NotImplementedError("E1 historical replay behavior is not implemented yet")
