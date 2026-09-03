from __future__ import annotations

from pathlib import Path

from fast_forecast_evaluation_fixtures import evaluation_contexts, evaluation_policy
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    read_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    evaluate_fast_forecasts,
)
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    predict_fast_forecast,
    train_fast_forecast_baseline,
)
from shreks_brain.fast_validation import run_fast_chronological_validation
from shreks_brain.research.fast_training_bundle import read_fast_training_bundle
from test_fast_chronological_integration import _policy, _request, _write_fl81_bundle


def test_real_fl81_to_fl84_evidence_packages_runtime_loadable_champion(tmp_path: Path) -> None:
    bundle = read_fast_training_bundle(_write_fl81_bundle(tmp_path / "source"))
    sources = []
    for family, target in (
        (FastForecastModelFamily.RIDGE_REGRESSION, FastForecastTarget.ENDPOINT_RETURN_BPS),
        (FastForecastModelFamily.LOGISTIC_REGRESSION, FastForecastTarget.REVERSAL_OCCURRED),
    ):
        request = _request(family, target)
        runtime_artifact = train_fast_forecast_baseline(bundle, request)
        validation_run = run_fast_chronological_validation(bundle, request, _policy())
        report = evaluate_fast_forecasts(
            bundle,
            validation_run,
            evaluation_contexts(validation_run),
            evaluation_policy(FastForecastEvaluationPartition.TEST),
        )
        sources.append((runtime_artifact, validation_run, report))

    champion = build_fast_forecast_champion(
        champion_version="fl8-5-disk-fixture-v1",
        decision_reference="fixture-explicit-selection-001",
        decided_at_unix_ms=20_000,
        reason="fixture-only packaging decision; not a production promotion",
        member_sources=tuple(sources),
    )
    assert len(champion.members) == 2
    output = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, output)
    loaded = read_fast_forecast_champion(output)
    assert loaded == champion

    record = bundle.features.records[0]
    for member in champion.members:
        loaded_member = loaded.member_for(
            member.forecast_artifact.target,
            member.forecast_artifact.horizon_ms,
        )
        assert predict_fast_forecast(loaded_member.forecast_artifact, record) == predict_fast_forecast(
            member.forecast_artifact,
            record,
        )
