from __future__ import annotations

from shreks_brain.backtest import ReplayDecisionInput, ReplayOutcomeBundle

from .models import BaselineSuite, BaselineSuitePolicy


def build_baseline_suite(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policy: BaselineSuitePolicy,
) -> BaselineSuite:
    raise NotImplementedError("E2 baseline behavior is not implemented yet")
