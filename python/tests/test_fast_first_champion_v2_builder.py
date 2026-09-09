from __future__ import annotations

from types import SimpleNamespace

import pytest

from fast_forecast_fixtures import training_bundle
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationContext,
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
)
from shreks_brain.fast_first_champion_v2 import builder as builder_module
from shreks_brain.fast_first_champion_v2.builder import (
    _generalization_policy,
    build_fast_first_champion_v2,
)
from shreks_brain.fast_first_champion_v2.models import (
    FastFirstChampionV2Policy,
)
from shreks_brain.fast_learning import FastForecastBaselineArtifact
from shreks_brain.fast_validation_v2 import (
    FastChronologicalGeneralizationRun,
)
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptanceArtifact,
)


def _evaluation_policy() -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fixture-eval-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=2,
        liquidity_capacity_quote_boundaries=(10.0,),
        round_trip_cost_bps_boundaries=(10.0,),
        binary_log_loss_clip_epsilon=1e-12,
    )


def _context(bundle) -> FastForecastEvaluationContext:
    identity = bundle.features.records[0].decision_identity
    return FastForecastEvaluationContext(
        decision_identity=identity,
        as_of_unix_ms=identity[6],
        market_regime="FIXTURE",
        strategy_families=("fixture",),
        executable_exit_capacity_quote=1.0,
        expected_round_trip_cost_bps=1.0,
    )


def _run_shell(request, bundle_fingerprint: str, index: int):
    value = object.__new__(FastChronologicalGeneralizationRun)
    object.__setattr__(value, "training_request", request)
    object.__setattr__(
        value,
        "training_bundle_fingerprint_sha256",
        bundle_fingerprint,
    )
    object.__setattr__(
        value,
        "validation_run_fingerprint_sha256",
        f"{index + 1:064x}",
    )
    return value


def _report_shell(
    *,
    run,
    scored: int,
    fingerprint_seed: int,
):
    value = object.__new__(FastForecastEvaluationReport)
    request = run.training_request
    object.__setattr__(value, "target", request.target)
    object.__setattr__(value, "model_family", request.model_family)
    object.__setattr__(value, "horizon_ms", request.horizon_ms)
    object.__setattr__(
        value,
        "training_bundle_fingerprint_sha256",
        run.training_bundle_fingerprint_sha256,
    )
    object.__setattr__(
        value,
        "validation_run_fingerprint_sha256",
        run.validation_run_fingerprint_sha256,
    )
    object.__setattr__(
        value,
        "evaluation_report_fingerprint_sha256",
        f"{fingerprint_seed:064x}",
    )
    object.__setattr__(
        value,
        "overall",
        SimpleNamespace(
            scored_observation_count=scored,
            target_unavailable_count=0,
        ),
    )
    return value


def _cohort_shell():
    value = object.__new__(Fl9V2CohortAcceptanceArtifact)
    object.__setattr__(
        value,
        "manifest",
        SimpleNamespace(
            artifact_fingerprint_sha256=(
                "bd6875c4d65ee9b2eb67783e7ecfa233"
                "2305bf6c3251f5d474e66465fd17d93a"
            ),
            accepted_identity_fingerprint_sha256=(
                "75cf6dbac938286f508d978a14149cd0"
                "83ff7a8470c8fce20fca9abbc1faf56b"
            ),
            test_unseen_mint_identity_fingerprint_sha256="a" * 64,
        ),
    )
    return value


def _artifact_shell(request, policy, index: int):
    value = object.__new__(FastForecastBaselineArtifact)
    object.__setattr__(value, "target", request.target)
    object.__setattr__(value, "model_family", request.model_family)
    object.__setattr__(value, "horizon_ms", request.horizon_ms)
    object.__setattr__(
        value,
        "artifact_fingerprint_sha256",
        f"{index + 100:064x}",
    )
    object.__setattr__(
        value,
        "min_training_decision_observed_at_unix_ms",
        policy.training_started_at_unix_ms,
    )
    object.__setattr__(
        value,
        "max_training_decision_observed_at_unix_ms",
        policy.selection_at_unix_ms - policy.horizon_ms,
    )
    return value


def _patch_authority_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        builder_module,
        "_validate_cohort",
        lambda cohort, policy: None,
    )
    monkeypatch.setattr(
        builder_module,
        "_require_bundle_matches_cohort",
        lambda cohort, bundle, policy: None,
    )
    monkeypatch.setattr(
        builder_module,
        "_reconcile_run_to_cohort",
        lambda cohort, run, policy: None,
    )


def test_v2_builder_uses_exact_frozen_generalization_policy() -> None:
    policy = FastFirstChampionV2Policy()
    generalization = _generalization_policy(policy)

    assert generalization.version == policy.generalization_policy_version
    assert (
        generalization.feature_identity_firewall_fingerprint_sha256
        == policy.feature_identity_firewall_fingerprint_sha256
    )
    assert len(generalization.folds) == 1
    fold = generalization.folds[0]
    assert (
        fold.training_started_at_unix_ms,
        fold.training_ended_at_unix_ms,
        fold.validation_started_at_unix_ms,
        fold.validation_ended_at_unix_ms,
        fold.test_started_at_unix_ms,
        fold.test_ended_at_unix_ms,
    ) == (
        policy.training_started_at_unix_ms,
        policy.training_ended_at_unix_ms,
        policy.validation_started_at_unix_ms,
        policy.validation_ended_at_unix_ms,
        policy.test_started_at_unix_ms,
        policy.test_ended_at_unix_ms,
    )


def test_third_member_floor_failure_prevents_every_runtime_refit(
    monkeypatch,
) -> None:
    policy = FastFirstChampionV2Policy()
    bundle = training_bundle()
    cohort = _cohort_shell()
    _patch_authority_checks(monkeypatch)

    run_index = 0
    events: list[str] = []

    def fake_run(bundle_arg, request, generalization_policy):
        nonlocal run_index
        value = _run_shell(
            request,
            bundle.manifest.bundle_fingerprint_sha256,
            run_index,
        )
        run_index += 1
        return value

    def fake_evaluate(
        bundle_arg,
        run,
        contexts,
        evaluation_policy,
        *,
        unseen_mint_only,
    ):
        role = "unseen" if unseen_mint_only else "natural"
        events.append(f"eval:{run.training_request.target.value}:{role}")
        scored = (
            policy.minimum_unseen_mint_test_scored_observations
            if unseen_mint_only
            else policy.minimum_natural_test_scored_observations
        )
        if (
            run.training_request.target.value == "mae_bps"
            and not unseen_mint_only
        ):
            scored -= 1
        return _report_shell(
            run=run,
            scored=scored,
            fingerprint_seed=len(events) + 200,
        )

    monkeypatch.setattr(
        builder_module,
        "run_fast_chronological_generalization",
        fake_run,
    )
    monkeypatch.setattr(
        builder_module,
        "evaluate_fast_first_champion_v2_test",
        fake_evaluate,
    )

    def forbidden_refit(*args, **kwargs):
        raise AssertionError("runtime refit must not start before all floors pass")

    monkeypatch.setattr(
        builder_module,
        "train_fast_forecast_baseline_for_decision_identities",
        forbidden_refit,
    )

    with pytest.raises(ValueError, match="natural TEST"):
        build_fast_first_champion_v2(
            cohort=cohort,
            bundle=bundle,
            contexts=(_context(bundle),),
            evaluation_policy=_evaluation_policy(),
            champion_version="fixture",
            decision_reference="fixture",
            reason="fixture",
            model_version_prefix="fixture",
            training_policy_version="fixture",
            policy=policy,
        )

    assert events == [
        "eval:endpoint_cost_adjusted_return_bps:natural",
        "eval:endpoint_cost_adjusted_return_bps:unseen",
        "eval:endpoint_return_bps:natural",
        "eval:endpoint_return_bps:unseen",
        "eval:mae_bps:natural",
        "eval:mae_bps:unseen",
    ]


def test_v2_builder_refits_only_after_all_ten_test_gates_pass(
    monkeypatch,
) -> None:
    policy = FastFirstChampionV2Policy()
    bundle = training_bundle()
    cohort = _cohort_shell()
    _patch_authority_checks(monkeypatch)

    events: list[str] = []
    requests = []

    def fake_run(bundle_arg, request, generalization_policy):
        requests.append(request)
        return _run_shell(
            request,
            bundle.manifest.bundle_fingerprint_sha256,
            len(requests) - 1,
        )

    def fake_evaluate(
        bundle_arg,
        run,
        contexts,
        evaluation_policy,
        *,
        unseen_mint_only,
    ):
        role = "unseen" if unseen_mint_only else "natural"
        events.append(f"eval:{run.training_request.target.value}:{role}")
        scored = (
            policy.minimum_unseen_mint_test_scored_observations
            if unseen_mint_only
            else policy.minimum_natural_test_scored_observations
        )
        return _report_shell(
            run=run,
            scored=scored,
            fingerprint_seed=len(events) + 300,
        )

    monkeypatch.setattr(
        builder_module,
        "run_fast_chronological_generalization",
        fake_run,
    )
    monkeypatch.setattr(
        builder_module,
        "evaluate_fast_first_champion_v2_test",
        fake_evaluate,
    )
    monkeypatch.setattr(
        builder_module,
        "_target_mature_accepted_identities",
        lambda cohort, bundle, policy: (bundle.features.records[0].decision_identity,),
    )

    def fake_refit(bundle_arg, request, identities):
        events.append(f"refit:{request.target.value}")
        return _artifact_shell(request, policy, len(events))

    monkeypatch.setattr(
        builder_module,
        "train_fast_forecast_baseline_for_decision_identities",
        fake_refit,
    )
    champion = object()
    monkeypatch.setattr(
        builder_module,
        "build_fast_first_champion_v2_runtime_champion",
        lambda **kwargs: champion,
    )
    monkeypatch.setattr(
        builder_module,
        "FastFirstChampionV2BuildResult",
        lambda **kwargs: kwargs,
    )

    result = build_fast_first_champion_v2(
        cohort=cohort,
        bundle=bundle,
        contexts=(_context(bundle),),
        evaluation_policy=_evaluation_policy(),
        champion_version="fixture",
        decision_reference="fixture",
        reason="fixture",
        model_version_prefix="fixture",
        training_policy_version="fixture",
        policy=policy,
    )

    assert tuple(
        (request.target, request.model_family)
        for request in requests
    ) == policy.required_members
    assert events[:10] == [
        f"eval:{target.value}:{role}"
        for target, _ in policy.required_members
        for role in ("natural", "unseen")
    ]
    assert events[10:] == [
        f"refit:{target.value}"
        for target, _ in policy.required_members
    ]
    assert result["champion"] is champion
