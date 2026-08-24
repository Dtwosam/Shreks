from __future__ import annotations

from dataclasses import replace

from shreks_brain.backtest import (
    ReplayDecisionInput,
    ReplayOutcomeBundle,
    ReplayPolicySet,
    replay_entry_decisions,
)
from shreks_brain.decision import DecisionPolicy, SetupDecisionRule

from .models import (
    BASELINE_SUITE_SCHEMA_VERSION,
    BaselineKind,
    BaselineReplayResult,
    BaselineSuite,
    BaselineSuitePolicy,
    ThresholdDeltaBaselineSpec,
)


def _adjust_threshold(value: float | None, delta: float) -> float | None:
    if value is None:
        return None
    return min(100.0, max(0.0, value + delta))


def _adjust_rule(rule: SetupDecisionRule, delta: float) -> SetupDecisionRule:
    return replace(
        rule,
        hot_min_score=_adjust_threshold(rule.hot_min_score, delta),
        normal_min_score=_adjust_threshold(rule.normal_min_score, delta),
        weak_min_score=_adjust_threshold(rule.weak_min_score, delta),
    )


def _derive_policy_set(
    base: ReplayPolicySet,
    *,
    replay_version: str,
    decision_version: str,
    delta: float,
) -> ReplayPolicySet:
    decision_policy: DecisionPolicy = replace(
        base.decision_policy,
        version=decision_version,
        setup_rules=tuple(
            _adjust_rule(rule, delta) for rule in base.decision_policy.setup_rules
        ),
    )
    return replace(
        base,
        version=replay_version,
        decision_policy=decision_policy,
    )


def _zero_policy_set(
    base: ReplayPolicySet,
    *,
    suite_version: str,
) -> ReplayPolicySet:
    return _derive_policy_set(
        base,
        replay_version=f"{suite_version}:zero_score_threshold",
        decision_version=(
            f"{base.decision_policy.version}:e2-zero-score-threshold"
        ),
        delta=-100.0,
    )


def _delta_policy_set(
    base: ReplayPolicySet,
    *,
    suite_version: str,
    spec: ThresholdDeltaBaselineSpec,
) -> ReplayPolicySet:
    canonical_delta = float(spec.delta_points).hex()
    return _derive_policy_set(
        base,
        replay_version=f"{suite_version}:threshold:{spec.name}",
        decision_version=(
            f"{base.decision_policy.version}:e2-threshold:"
            f"{spec.name}:{canonical_delta}"
        ),
        delta=float(spec.delta_points),
    )


def _result(
    *,
    name: str,
    kind: BaselineKind,
    threshold_delta_points: float | None,
    replay,
) -> BaselineReplayResult:
    return BaselineReplayResult(
        name=name,
        kind=kind,
        threshold_delta_points=threshold_delta_points,
        replay_policy_set_version=replay.policy_set_version,
        replay=replay,
    )


def build_baseline_suite(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policy: BaselineSuitePolicy,
) -> BaselineSuite:
    base = policy.base_replay_policies

    v0_replay = replay_entry_decisions(
        decision_inputs,
        outcome_bundles,
        base,
    )
    results = [
        _result(
            name="v0",
            kind=BaselineKind.V0,
            threshold_delta_points=None,
            replay=v0_replay,
        )
    ]

    zero_policy = _zero_policy_set(base, suite_version=policy.version)
    zero_replay = replay_entry_decisions(
        decision_inputs,
        outcome_bundles,
        zero_policy,
    )
    results.append(
        _result(
            name="zero_score_threshold",
            kind=BaselineKind.ZERO_SCORE_THRESHOLD,
            threshold_delta_points=None,
            replay=zero_replay,
        )
    )

    for spec in sorted(policy.threshold_variants, key=lambda value: value.name):
        derived_policy = _delta_policy_set(
            base,
            suite_version=policy.version,
            spec=spec,
        )
        replay = replay_entry_decisions(
            decision_inputs,
            outcome_bundles,
            derived_policy,
        )
        results.append(
            _result(
                name=spec.name,
                kind=BaselineKind.THRESHOLD_DELTA,
                threshold_delta_points=spec.delta_points,
                replay=replay,
            )
        )

    return BaselineSuite(
        schema_version=BASELINE_SUITE_SCHEMA_VERSION,
        policy_version=policy.version,
        results=tuple(results),
    )
