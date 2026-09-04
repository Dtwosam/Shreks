from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from shreks_brain.fast_champion import (
    FastForecastChampionArtifact,
    read_fast_forecast_champion,
)
from shreks_brain.fast_learning import (
    FastForecastPrediction,
    FastForecastTarget,
    predict_fast_forecast,
)
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
)

from .models import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionTrade,
)


FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION = (
    "fl9-champion-entry-execution-evidence-v1"
)


@dataclass(frozen=True, slots=True)
class FastChampionEntryExecutionEvidence:
    version: str
    champion_version: str
    champion_fingerprint_sha256: str
    member_key: str
    validation_run_fingerprint_sha256: str
    test_evaluation_report_fingerprint_sha256: str
    prediction: FastForecastPrediction
    execution: FastOfflineEntryExecution
    forecast_source_version: str
    execution_policy_source_version: str
    exit_capacity_source_version: str

    def __post_init__(self) -> None:
        if self.version != FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION:
            raise ValueError(
                "unsupported champion entry execution evidence version"
            )
        for name in (
            "champion_version",
            "member_key",
            "forecast_source_version",
            "execution_policy_source_version",
            "exit_capacity_source_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        for name in (
            "champion_fingerprint_sha256",
            "validation_run_fingerprint_sha256",
            "test_evaluation_report_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if type(self.prediction) is not FastForecastPrediction:
            raise ValueError(
                "prediction must be exact FastForecastPrediction"
            )
        if type(self.execution) is not FastOfflineEntryExecution:
            raise ValueError(
                "execution must be exact FastOfflineEntryExecution"
            )


def build_fast_champion_entry_execution_evidence(
    *,
    champion_path: str | Path,
    record: FastTrainingFeatureRecord,
    horizon_ms: int,
    cost_model: FastOfflineExecutionCostModel,
    base_quantity: float,
    exit_capacity_base: float,
    required_edge_bps: int,
    risk_margin_bps: int,
    execution_policy_source_version: str,
    exit_capacity_source_version: str,
) -> FastChampionEntryExecutionEvidence:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError(
            "record must be exact FastTrainingFeatureRecord"
        )
    if type(cost_model) is not FastOfflineExecutionCostModel:
        raise ValueError(
            "cost_model must be exact FastOfflineExecutionCostModel"
        )
    _require_positive_int("horizon_ms", horizon_ms)
    _require_positive_finite("base_quantity", base_quantity)
    _require_positive_finite(
        "exit_capacity_base",
        exit_capacity_base,
    )
    _require_non_negative_int("required_edge_bps", required_edge_bps)
    _require_non_negative_int("risk_margin_bps", risk_margin_bps)
    _require_non_empty_string(
        "execution_policy_source_version",
        execution_policy_source_version,
    )
    _require_non_empty_string(
        "exit_capacity_source_version",
        exit_capacity_source_version,
    )

    champion = read_fast_forecast_champion(champion_path)
    _validate_champion_chronology(champion, record)

    try:
        member = champion.member_for(
            FastForecastTarget.ENDPOINT_RETURN_BPS,
            horizon_ms,
        )
    except KeyError as exc:
        raise ValueError(
            "champion has no exact raw endpoint-return member for requested horizon"
        ) from exc

    artifact = member.forecast_artifact
    if artifact.target is not FastForecastTarget.ENDPOINT_RETURN_BPS:
        raise ValueError(
            "champion execution evidence requires raw endpoint return"
        )
    if artifact.horizon_ms != horizon_ms:
        raise ValueError(
            "champion endpoint-return horizon mismatch"
        )
    if (
        artifact.max_training_decision_observed_at_unix_ms
        >= record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "champion runtime artifact training reaches the decision and would leak future chronology"
        )

    prediction = predict_fast_forecast(artifact, record)
    if prediction.target is not FastForecastTarget.ENDPOINT_RETURN_BPS:
        raise ValueError(
            "champion prediction target is not raw endpoint return"
        )
    if prediction.horizon_ms != horizon_ms:
        raise ValueError(
            "champion prediction horizon mismatch"
        )
    if prediction.decision_identity != record.decision_identity:
        raise ValueError(
            "champion prediction decision identity mismatch"
        )

    forecast_exit_price_quote = _forecast_exit_price_quote(
        record.decision_executable_entry_price_quote,
        prediction.predicted_value,
    )
    execution = FastOfflineEntryExecution(
        cost_model=cost_model,
        trade=FastOfflineExecutionTrade(
            base_quantity=float(base_quantity),
            executable_entry_price_quote=(
                record.decision_executable_entry_price_quote
            ),
            forecast_exit_price_quote=forecast_exit_price_quote,
            exit_capacity_base=float(exit_capacity_base),
            required_edge_bps=required_edge_bps,
            risk_margin_bps=risk_margin_bps,
        ),
    )

    member_key = member.member_key
    forecast_source_version = (
        f"fl8-champion:{champion.champion_version}:"
        f"{champion.champion_fingerprint_sha256}:"
        f"{member_key}:{artifact.model_version}:"
        f"{artifact.artifact_fingerprint_sha256}"
    )
    return FastChampionEntryExecutionEvidence(
        version=FAST_CHAMPION_ENTRY_EXECUTION_EVIDENCE_VERSION,
        champion_version=champion.champion_version,
        champion_fingerprint_sha256=(
            champion.champion_fingerprint_sha256
        ),
        member_key=member_key,
        validation_run_fingerprint_sha256=(
            member.validation_run_fingerprint_sha256
        ),
        test_evaluation_report_fingerprint_sha256=(
            member.test_evaluation_report_fingerprint_sha256
        ),
        prediction=prediction,
        execution=execution,
        forecast_source_version=forecast_source_version,
        execution_policy_source_version=(
            execution_policy_source_version
        ),
        exit_capacity_source_version=exit_capacity_source_version,
    )


def _validate_champion_chronology(
    champion: FastForecastChampionArtifact,
    record: FastTrainingFeatureRecord,
) -> None:
    if champion.selection.decided_at_unix_ms > (
        record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "champion selection occurs after the FL8.1 decision"
        )


def _forecast_exit_price_quote(
    executable_entry_price_quote: float,
    endpoint_return_bps: float,
) -> float:
    _require_positive_finite(
        "executable_entry_price_quote",
        executable_entry_price_quote,
    )
    if (
        isinstance(endpoint_return_bps, bool)
        or not isinstance(endpoint_return_bps, (int, float))
        or not math.isfinite(float(endpoint_return_bps))
    ):
        raise ValueError("endpoint_return_bps must be finite")
    forecast = float(executable_entry_price_quote) * (
        1.0 + float(endpoint_return_bps) / 10_000.0
    )
    if not math.isfinite(forecast) or forecast <= 0.0:
        raise ValueError(
            "forecast exit price must be positive and finite"
        )
    return forecast


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} must be positive and finite")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
