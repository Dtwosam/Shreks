from __future__ import annotations

from shreks_brain.decision import DecisionAction, decide_entry
from shreks_brain.research import ResearchSnapshotInputs
from shreks_brain.scoring import score_candidate
from shreks_brain.setups import (
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)

from .models import (
    BACKTEST_REPLAY_SCHEMA_VERSION,
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    ReplayRun,
    ReplaySetupKind,
)


def replay_entry_decisions(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policies: ReplayPolicySet,
) -> ReplayRun:
    if not isinstance(decision_inputs, tuple):
        raise ValueError("decision_inputs must be a tuple")
    if not decision_inputs:
        raise ValueError("decision_inputs must be non-empty")
    if not all(type(value) is ReplayDecisionInput for value in decision_inputs):
        raise ValueError(
            "decision_inputs must contain exact ReplayDecisionInput values"
        )
    if not isinstance(outcome_bundles, tuple):
        raise ValueError("outcome_bundles must be a tuple")
    if not all(type(value) is ReplayOutcomeBundle for value in outcome_bundles):
        raise ValueError(
            "outcome_bundles must contain exact ReplayOutcomeBundle values"
        )
    if type(policies) is not ReplayPolicySet:
        raise ValueError("policies must be a ReplayPolicySet")

    decision_identities = tuple(_decision_identity(value) for value in decision_inputs)
    if len(set(decision_identities)) != len(decision_identities):
        raise ValueError("duplicate decision replay identity")

    outcome_identities = tuple(_outcome_identity(value) for value in outcome_bundles)
    if len(set(outcome_identities)) != len(outcome_identities):
        raise ValueError("duplicate outcome replay identity")
    if set(decision_identities) != set(outcome_identities):
        raise ValueError("decision and outcome identity sets must match exactly")

    for value in decision_inputs:
        _require_configured_setup_policy(value.setup_kind, policies)

    outcome_by_identity = {
        _outcome_identity(value): value for value in outcome_bundles
    }
    ordered_inputs = tuple(
        sorted(
            decision_inputs,
            key=lambda value: (
                value.market_features.as_of_unix_ms,
                value.candidate_mint,
            ),
        )
    )

    snapshots: list[ResearchSnapshotInputs] = []
    for value in ordered_inputs:
        setup = _assess_setup(value, policies)
        score = score_candidate(
            value.market_features,
            setup,
            value.regime,
            policies.score_policy,
        )
        decision = decide_entry(
            value.candidate_mint,
            score,
            policies.decision_policy,
        )

        bundle = outcome_by_identity[_decision_identity(value)]
        snapshots.append(
            ResearchSnapshotInputs(
                candidate_mint=value.candidate_mint,
                market_features=value.market_features,
                wallet_features=value.wallet_features,
                regime=value.regime,
                score=score,
                decision=decision,
                outcomes=bundle.outcomes,
            )
        )

    snapshot_tuple = tuple(snapshots)
    reject_count = sum(
        value.decision.action is DecisionAction.REJECT for value in snapshot_tuple
    )
    watch_count = sum(
        value.decision.action is DecisionAction.WATCH for value in snapshot_tuple
    )
    enter_count = sum(
        value.decision.action is DecisionAction.ENTER for value in snapshot_tuple
    )
    as_of_values = tuple(
        value.market_features.as_of_unix_ms for value in snapshot_tuple
    )

    return ReplayRun(
        schema_version=BACKTEST_REPLAY_SCHEMA_VERSION,
        policy_set_version=policies.version,
        score_policy_version=policies.score_policy.version,
        decision_policy_version=policies.decision_policy.version,
        snapshots=snapshot_tuple,
        reject_count=reject_count,
        watch_count=watch_count,
        enter_count=enter_count,
        min_as_of_unix_ms=min(as_of_values),
        max_as_of_unix_ms=max(as_of_values),
    )


def _decision_identity(value: ReplayDecisionInput) -> tuple[int, str]:
    return value.market_features.as_of_unix_ms, value.candidate_mint


def _outcome_identity(value: ReplayOutcomeBundle) -> tuple[int, str]:
    return value.as_of_unix_ms, value.candidate_mint


def _require_configured_setup_policy(
    setup_kind: ReplaySetupKind,
    policies: ReplayPolicySet,
) -> None:
    if (
        setup_kind is ReplaySetupKind.FRESH_LAUNCH_CONTINUATION
        and policies.fresh_launch_policy is None
    ):
        raise ValueError("used setup kind requires a configured setup policy")
    if (
        setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT
        and policies.graduation_breakout_policy is None
    ):
        raise ValueError("used setup kind requires a configured setup policy")
    if (
        setup_kind is ReplaySetupKind.FIRST_PULLBACK
        and policies.first_pullback_policy is None
    ):
        raise ValueError("used setup kind requires a configured setup policy")


def _assess_setup(value: ReplayDecisionInput, policies: ReplayPolicySet):
    if value.setup_kind is ReplaySetupKind.FRESH_LAUNCH_CONTINUATION:
        policy = policies.fresh_launch_policy
        if policy is None:
            raise ValueError("used setup kind requires a configured setup policy")
        return assess_fresh_launch(value.market_features, policy)

    if value.setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT:
        policy = policies.graduation_breakout_policy
        if policy is None:
            raise ValueError("used setup kind requires a configured setup policy")
        return assess_graduation_breakout(
            value.market_features,
            value.graduation_context,
            policy,
        )

    policy = policies.first_pullback_policy
    if policy is None:
        raise ValueError("used setup kind requires a configured setup policy")
    return assess_first_pullback(
        value.market_features,
        value.pullback_context,
        policy,
    )
