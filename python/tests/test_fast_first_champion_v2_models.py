from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)
import shreks_brain.fast_first_champion_v2 as v2


def test_v2_policy_is_exact_and_frozen() -> None:
    policy = v2.FastFirstChampionV2Policy()

    assert policy.version == "fl9-v2-first-champion-v1"
    assert policy.cohort_policy_version == "fl9-v2-cohort-acceptance-v1"
    assert (
        policy.expected_cohort_artifact_fingerprint_sha256
        == "bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a"
    )
    assert (
        policy.expected_accepted_identity_fingerprint_sha256
        == "75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b"
    )
    assert policy.horizon_ms == 30_000
    assert policy.selection_at_unix_ms == 1_788_902_319_835
    assert policy.training_started_at_unix_ms == 1_788_878_323_281
    assert policy.training_ended_at_unix_ms == 1_788_892_302_791
    assert policy.validation_started_at_unix_ms == 1_788_892_302_791
    assert policy.validation_ended_at_unix_ms == 1_788_898_931_418
    assert policy.test_started_at_unix_ms == 1_788_898_931_418
    assert policy.test_ended_at_unix_ms == 1_788_902_289_835
    assert policy.minimum_natural_test_scored_observations == 40_000
    assert policy.minimum_unseen_mint_test_scored_observations == 35_000
    assert (
        policy.feature_identity_firewall_fingerprint_sha256
        == "e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("version", "changed"),
        ("horizon_ms", 10_000),
        ("selection_at_unix_ms", 1_788_902_319_836),
        ("training_ended_at_unix_ms", 1_788_892_302_792),
        ("validation_ended_at_unix_ms", 1_788_898_931_419),
        ("test_ended_at_unix_ms", 1_788_902_289_836),
        ("minimum_natural_test_scored_observations", 39_999),
        ("minimum_unseen_mint_test_scored_observations", 34_999),
    ),
)
def test_v2_policy_changes_require_a_new_version(
    field: str,
    value: object,
) -> None:
    policy = v2.FastFirstChampionV2Policy()
    with pytest.raises(ValueError, match="immutable"):
        replace(policy, **{field: value})


def test_v2_required_member_population_is_exact() -> None:
    assert v2.FastFirstChampionV2Policy().required_members == (
        (
            FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
            FastForecastModelFamily.MEAN_REGRESSOR,
        ),
        (
            FastForecastTarget.ENDPOINT_RETURN_BPS,
            FastForecastModelFamily.MEAN_REGRESSOR,
        ),
        (
            FastForecastTarget.MAE_BPS,
            FastForecastModelFamily.MEAN_REGRESSOR,
        ),
        (
            FastForecastTarget.REVERSAL_OCCURRED,
            FastForecastModelFamily.PRIOR_CLASSIFIER,
        ),
        (
            FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
            FastForecastModelFamily.PRIOR_CLASSIFIER,
        ),
    )


def test_v2_member_evidence_enforces_both_scoring_floors() -> None:
    policy = v2.FastFirstChampionV2Policy()
    common = dict(
        target=FastForecastTarget.ENDPOINT_RETURN_BPS,
        model_family=FastForecastModelFamily.MEAN_REGRESSOR,
        horizon_ms=policy.horizon_ms,
        runtime_artifact_fingerprint_sha256="1" * 64,
        generalization_run_fingerprint_sha256="2" * 64,
        natural_test_report_fingerprint_sha256="3" * 64,
        natural_test_scored_observation_count=40_000,
        natural_test_target_unavailable_count=0,
        unseen_mint_test_report_fingerprint_sha256="4" * 64,
        unseen_mint_test_scored_observation_count=35_000,
        unseen_mint_test_target_unavailable_count=0,
        unseen_mint_test_identity_fingerprint_sha256="5" * 64,
    )
    value = v2.FastFirstChampionV2MemberEvidence(**common)
    assert value.natural_test_scored_observation_count == 40_000
    assert value.unseen_mint_test_scored_observation_count == 35_000

    with pytest.raises(ValueError, match="natural TEST"):
        v2.FastFirstChampionV2MemberEvidence(
            **{
                **common,
                "natural_test_scored_observation_count": 39_999,
            }
        )
    with pytest.raises(ValueError, match="unseen-mint TEST"):
        v2.FastFirstChampionV2MemberEvidence(
            **{
                **common,
                "unseen_mint_test_scored_observation_count": 34_999,
            }
        )


def test_v2_build_result_reconciles_every_evidence_cross_link() -> None:
    from fast_first_champion_v2_fixtures import synthetic_v2_build_result

    build = synthetic_v2_build_result()
    assert len(build.member_evidence) == 5
    assert build.champion.training_bundle_fingerprint_sha256 == (
        build.training_bundle_fingerprint_sha256
    )

    reordered = (
        build.natural_test_reports[1],
        build.natural_test_reports[0],
        *build.natural_test_reports[2:],
    )
    with pytest.raises(ValueError, match="canonical|required member order"):
        replace(build, natural_test_reports=reordered)

    bad_evidence = replace(
        build.member_evidence[0],
        natural_test_report_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="member evidence.*reconcile"):
        replace(
            build,
            member_evidence=(bad_evidence, *build.member_evidence[1:]),
        )

    bad_member = replace(
        build.champion.members[0],
        test_evaluation_report_fingerprint_sha256="e" * 64,
    )
    bad_champion = replace(
        build.champion,
        members=(bad_member, *build.champion.members[1:]),
    )
    with pytest.raises(ValueError, match="runtime champion member.*reconcile"):
        replace(build, champion=bad_champion)

    with pytest.raises(ValueError, match="training bundle fingerprint"):
        replace(build, training_bundle_fingerprint_sha256="d" * 64)
