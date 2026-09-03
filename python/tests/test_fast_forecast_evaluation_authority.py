from __future__ import annotations

import inspect
import subprocess
import sys

import shreks_brain.fast_evaluation as fast_evaluation
from shreks_brain.fast_evaluation import codec, engine, models


EXPECTED_PUBLIC_API = {
    "FAST_FORECAST_EVALUATION_SCHEMA_NAME",
    "FAST_FORECAST_EVALUATION_SCHEMA_VERSION",
    "FastForecastEvaluationPartition",
    "FastForecastEvaluationContext",
    "FastForecastEvaluationPolicy",
    "FastCalibrationBucket",
    "FastContinuousForecastMetrics",
    "FastBinaryForecastMetrics",
    "FastForecastMetricPopulation",
    "FastForecastEvaluationReport",
    "evaluate_fast_forecasts",
    "write_fast_forecast_evaluation_report",
    "read_fast_forecast_evaluation_report",
}


def test_public_api_is_exact_and_import_does_not_eagerly_load_ml_runtimes() -> None:
    assert set(fast_evaluation.__all__) == EXPECTED_PUBLIC_API
    code = (
        "import sys; import shreks_brain.fast_evaluation; "
        "assert not any(name == 'sklearn' or name.startswith('sklearn.') for name in sys.modules); "
        "assert not any(name == 'numpy' or name.startswith('numpy.') for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_evaluation_sources_have_no_promotion_execution_or_live_authority() -> None:
    source = "\n".join(inspect.getsource(module) for module in (models, engine, codec))
    forbidden = (
        "shreks_brain.promotion",
        "shreks_brain.registry",
        "shreks_brain.providers",
        "shreks_brain.fast_paper",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "RuntimeMode.Live",
        "submit_transaction",
        "sign_transaction",
        "champion_status",
        "promote_challenger",
    )
    for token in forbidden:
        assert token not in source, f"FL8.4 gained forbidden authority via {token}"
