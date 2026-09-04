from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_evaluation import FastForecastEvaluationContext
from shreks_brain.fast_first_champion import (
    FastForecastEvaluationContextCorpus,
    build_fast_forecast_evaluation_context_corpus,
    read_fast_forecast_evaluation_context_corpus,
    write_fast_forecast_evaluation_context_corpus,
)
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
    FastForecastTrainingPolicy,
    FastForecastTrainingRequest,
)
from shreks_brain.fast_validation import (
    FastChronologicalValidationPolicy,
    FastChronologicalValidationRun,
    run_fast_chronological_validation,
)
from shreks_brain.observer_campaign import (
    ObserverCampaignStore,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_market import ObserverMarketStore
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.regime import RegimePolicy, assess_regime
from shreks_brain.research.fast_training_bundle import (
    FastTrainingBundle,
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.safety import SafetyPolicy


FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_NAME = (
    "shreks.fast_forecast_context_hydration_policy"
)
FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_VERSION = 1
FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_NAME = (
    "shreks.fast_forecast_context_hydration_artifact"
)
FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_VERSION = 1
FAST_FORECAST_CONTEXT_HYDRATION_RESULT_VERSION = (
    "fl9-context-hydration-result-v1"
)
FAST_CONTEXT_POPULATION_MODEL_VERSION = "fl9-context-population-mean-v1"
FAST_CONTEXT_POPULATION_TRAINING_POLICY_VERSION = (
    "fl9-context-population-naive-v1"
)

_CONTEXT_FILE = "contexts.json"
_POLICY_FILE = "policy.json"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset({_CONTEXT_FILE, _POLICY_FILE, _MANIFEST_FILE})

_POLICY_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy",
        "policy_fingerprint_sha256",
    }
)
_POLICY_KEYS = frozenset(
    {
        "version",
        "strategy_families",
        "regime_read_policy",
        "regime_policy",
        "safety_policy",
        "safety_probe_identity",
        "global_risk_halt",
        "exit_quote_provider",
        "quote_asset_decimals",
        "max_exit_quote_age_ms",
        "execution_cost_policy_version",
        "expected_round_trip_cost_bps",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "validation_policy_version",
        "horizon_ms",
        "training_bundle_fingerprint_sha256",
        "feature_source_jsonl_sha256",
        "observer_database_sha256",
        "observer_database_wal_sha256",
        "hydration_policy_fingerprint_sha256",
        "population_validation_run_fingerprint_sha256",
        "context_fingerprint_sha256",
        "context_count",
        "available_exit_capacity_count",
        "unavailable_exit_route_count",
        "missing_or_stale_exit_quote_count",
        "contexts_file_sha256",
        "policy_file_sha256",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastForecastContextHydrationPolicy:
    version: str
    strategy_families: tuple[str, ...]
    regime_read_policy: ObserverRegimeReadPolicy
    regime_policy: RegimePolicy
    safety_policy: SafetyPolicy
    safety_probe_identity: ObserverSafetyProbeIdentity
    global_risk_halt: bool
    exit_quote_provider: str
    quote_asset_decimals: int
    max_exit_quote_age_ms: int
    execution_cost_policy_version: str
    expected_round_trip_cost_bps: float | int | None

    def __post_init__(self) -> None:
        _require_non_empty("version", self.version)
        if (
            not isinstance(self.strategy_families, tuple)
            or not self.strategy_families
            or not all(
                isinstance(value, str) and value.strip()
                for value in self.strategy_families
            )
        ):
            raise ValueError(
                "strategy_families must be a non-empty tuple of non-empty strings"
            )
        if self.strategy_families != tuple(sorted(self.strategy_families)):
            raise ValueError("strategy_families must be in canonical sorted order")
        if len(set(self.strategy_families)) != len(self.strategy_families):
            raise ValueError("strategy_families must be unique")

        if type(self.regime_read_policy) is not ObserverRegimeReadPolicy:
            raise ValueError(
                "regime_read_policy must be exact ObserverRegimeReadPolicy"
            )
        if type(self.regime_policy) is not RegimePolicy:
            raise ValueError("regime_policy must be exact RegimePolicy")
        if type(self.safety_policy) is not SafetyPolicy:
            raise ValueError("safety_policy must be exact SafetyPolicy")
        if type(self.safety_probe_identity) is not ObserverSafetyProbeIdentity:
            raise ValueError(
                "safety_probe_identity must be exact ObserverSafetyProbeIdentity"
            )
        if type(self.global_risk_halt) is not bool:
            raise ValueError("global_risk_halt must be a boolean")
        _require_non_empty("exit_quote_provider", self.exit_quote_provider)
        _require_non_empty(
            "execution_cost_policy_version",
            self.execution_cost_policy_version,
        )
        if (
            isinstance(self.quote_asset_decimals, bool)
            or not isinstance(self.quote_asset_decimals, int)
            or not 0 <= self.quote_asset_decimals <= 255
        ):
            raise ValueError(
                "quote_asset_decimals must be an integer within [0, 255]"
            )
        _require_non_negative_int(
            "max_exit_quote_age_ms",
            self.max_exit_quote_age_ms,
        )
        if self.expected_round_trip_cost_bps is not None:
            _require_non_negative_finite(
                "expected_round_trip_cost_bps",
                self.expected_round_trip_cost_bps,
            )

        regime = self.regime_read_policy
        probe = self.safety_probe_identity
        if regime.entry_probe_policy_version != probe.probe_policy_version:
            raise ValueError(
                "regime and exit probe policy versions must match"
            )
        if regime.quote_asset_mint != probe.output_mint:
            raise ValueError(
                "regime quote asset and exit probe output mint must match"
            )
        if regime.taker != probe.taker:
            raise ValueError("regime and exit probe takers must match")
        if regime.slippage_bps != probe.slippage_bps:
            raise ValueError(
                "regime and exit probe slippage policies must match"
            )


@dataclass(frozen=True, slots=True)
class FastForecastContextHydrationResult:
    version: str
    hydration_policy_fingerprint_sha256: str
    population_validation_run: FastChronologicalValidationRun
    context_corpus: FastForecastEvaluationContextCorpus
    context_count: int
    available_exit_capacity_count: int
    unavailable_exit_route_count: int
    missing_or_stale_exit_quote_count: int

    def __post_init__(self) -> None:
        if self.version != FAST_FORECAST_CONTEXT_HYDRATION_RESULT_VERSION:
            raise ValueError("unsupported context hydration result version")
        _require_sha256(
            "hydration_policy_fingerprint_sha256",
            self.hydration_policy_fingerprint_sha256,
        )
        if type(self.population_validation_run) is not FastChronologicalValidationRun:
            raise ValueError(
                "population_validation_run must be exact FastChronologicalValidationRun"
            )
        if type(self.context_corpus) is not FastForecastEvaluationContextCorpus:
            raise ValueError(
                "context_corpus must be exact FastForecastEvaluationContextCorpus"
            )
        _require_positive_int("context_count", self.context_count)
        for name in (
            "available_exit_capacity_count",
            "unavailable_exit_route_count",
            "missing_or_stale_exit_quote_count",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if self.context_count != len(self.context_corpus.contexts):
            raise ValueError("context_count does not match context corpus")
        if (
            self.available_exit_capacity_count
            + self.unavailable_exit_route_count
            + self.missing_or_stale_exit_quote_count
            != self.context_count
        ):
            raise ValueError("exit evidence counts do not reconcile")


@dataclass(frozen=True, slots=True)
class FastForecastContextHydrationArtifactManifest:
    schema_name: str
    schema_version: int
    validation_policy_version: str
    horizon_ms: int
    training_bundle_fingerprint_sha256: str
    feature_source_jsonl_sha256: str
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    hydration_policy_fingerprint_sha256: str
    population_validation_run_fingerprint_sha256: str
    context_fingerprint_sha256: str
    context_count: int
    available_exit_capacity_count: int
    unavailable_exit_route_count: int
    missing_or_stale_exit_quote_count: int
    contexts_file_sha256: str
    policy_file_sha256: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_NAME:
            raise ValueError(
                "unsupported context hydration artifact schema_name"
            )
        if self.schema_version != FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported context hydration artifact schema_version"
            )
        _require_non_empty(
            "validation_policy_version",
            self.validation_policy_version,
        )
        _require_positive_int("horizon_ms", self.horizon_ms)
        for name in (
            "training_bundle_fingerprint_sha256",
            "feature_source_jsonl_sha256",
            "observer_database_sha256",
            "hydration_policy_fingerprint_sha256",
            "population_validation_run_fingerprint_sha256",
            "context_fingerprint_sha256",
            "contexts_file_sha256",
            "policy_file_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.observer_database_wal_sha256 is not None:
            _require_sha256(
                "observer_database_wal_sha256",
                self.observer_database_wal_sha256,
            )
        _require_positive_int("context_count", self.context_count)
        for name in (
            "available_exit_capacity_count",
            "unavailable_exit_route_count",
            "missing_or_stale_exit_quote_count",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if (
            self.available_exit_capacity_count
            + self.unavailable_exit_route_count
            + self.missing_or_stale_exit_quote_count
            != self.context_count
        ):
            raise ValueError("artifact exit evidence counts do not reconcile")


@dataclass(frozen=True, slots=True)
class FastForecastContextHydrationArtifact:
    path: Path
    manifest: FastForecastContextHydrationArtifactManifest
    policy: FastForecastContextHydrationPolicy
    context_corpus: FastForecastEvaluationContextCorpus
    population_validation_run_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        if type(self.manifest) is not FastForecastContextHydrationArtifactManifest:
            raise ValueError(
                "manifest must be exact FastForecastContextHydrationArtifactManifest"
            )
        if type(self.policy) is not FastForecastContextHydrationPolicy:
            raise ValueError(
                "policy must be exact FastForecastContextHydrationPolicy"
            )
        if type(self.context_corpus) is not FastForecastEvaluationContextCorpus:
            raise ValueError(
                "context_corpus must be exact FastForecastEvaluationContextCorpus"
            )
        _require_sha256(
            "population_validation_run_fingerprint_sha256",
            self.population_validation_run_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class _DatabaseSnapshot:
    database_sha256: str
    wal_sha256: str | None


def fast_forecast_context_hydration_policy_fingerprint_sha256(
    policy: FastForecastContextHydrationPolicy,
) -> str:
    if type(policy) is not FastForecastContextHydrationPolicy:
        raise ValueError(
            "policy must be exact FastForecastContextHydrationPolicy"
        )
    return _sha256_canonical(_policy_document(policy))


def encode_fast_forecast_context_hydration_policy(
    policy: FastForecastContextHydrationPolicy,
) -> str:
    fingerprint = fast_forecast_context_hydration_policy_fingerprint_sha256(
        policy
    )
    return _canonical(
        {
            "schema_name": FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_NAME,
            "schema_version": (
                FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_VERSION
            ),
            "policy": _policy_document(policy),
            "policy_fingerprint_sha256": fingerprint,
        }
    )


def decode_fast_forecast_context_hydration_policy(
    payload: str,
) -> FastForecastContextHydrationPolicy:
    document = _load_canonical(
        payload,
        label="forecast context hydration policy",
    )
    if frozenset(document) != _POLICY_TOP_KEYS:
        raise ValueError(
            "forecast context hydration policy has unknown or missing top-level fields"
        )
    if (
        document["schema_name"]
        != FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_NAME
        or document["schema_version"]
        != FAST_FORECAST_CONTEXT_HYDRATION_POLICY_SCHEMA_VERSION
    ):
        raise ValueError("unsupported forecast context hydration policy schema")
    raw = document["policy"]
    if not isinstance(raw, dict) or frozenset(raw) != _POLICY_KEYS:
        raise ValueError(
            "forecast context hydration policy fields are incompatible"
        )

    policy = FastForecastContextHydrationPolicy(
        version=_text(raw["version"], "version"),
        strategy_families=_string_tuple(
            raw["strategy_families"],
            "strategy_families",
        ),
        regime_read_policy=_decode_regime_read_policy(
            raw["regime_read_policy"]
        ),
        regime_policy=_decode_regime_policy(raw["regime_policy"]),
        safety_policy=_decode_safety_policy(raw["safety_policy"]),
        safety_probe_identity=_decode_safety_probe_identity(
            raw["safety_probe_identity"]
        ),
        global_risk_halt=_boolean(
            raw["global_risk_halt"],
            "global_risk_halt",
        ),
        exit_quote_provider=_text(
            raw["exit_quote_provider"],
            "exit_quote_provider",
        ),
        quote_asset_decimals=_integer(
            raw["quote_asset_decimals"],
            "quote_asset_decimals",
        ),
        max_exit_quote_age_ms=_integer(
            raw["max_exit_quote_age_ms"],
            "max_exit_quote_age_ms",
        ),
        execution_cost_policy_version=_text(
            raw["execution_cost_policy_version"],
            "execution_cost_policy_version",
        ),
        expected_round_trip_cost_bps=_decode_optional_numeric(
            raw["expected_round_trip_cost_bps"],
            "expected_round_trip_cost_bps",
        ),
    )
    claimed = _text(
        document["policy_fingerprint_sha256"],
        "policy_fingerprint_sha256",
    )
    _require_sha256("policy_fingerprint_sha256", claimed)
    expected = fast_forecast_context_hydration_policy_fingerprint_sha256(
        policy
    )
    if claimed != expected:
        raise ValueError("forecast context hydration policy fingerprint mismatch")
    if encode_fast_forecast_context_hydration_policy(policy) != payload:
        raise ValueError(
            "forecast context hydration policy must use canonical JSON"
        )
    return policy


def hydrate_fast_forecast_evaluation_contexts(
    *,
    bundle: FastTrainingBundle,
    observer_database_path: str | Path,
    validation_policy: FastChronologicalValidationPolicy,
    horizon_ms: int,
    hydration_policy: FastForecastContextHydrationPolicy,
) -> FastForecastContextHydrationResult:
    _validate_inputs(
        bundle=bundle,
        validation_policy=validation_policy,
        horizon_ms=horizon_ms,
        hydration_policy=hydration_policy,
    )
    database = Path(observer_database_path).expanduser().resolve()
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "context hydration observer database must be an existing regular file"
        )

    population_run = run_fast_chronological_validation(
        bundle,
        FastForecastTrainingRequest(
            model_version=(
                f"{FAST_CONTEXT_POPULATION_MODEL_VERSION}:{horizon_ms}ms"
            ),
            model_family=FastForecastModelFamily.MEAN_REGRESSOR,
            target=FastForecastTarget.ENDPOINT_RETURN_BPS,
            horizon_ms=horizon_ms,
            training_policy=FastForecastTrainingPolicy(
                version=FAST_CONTEXT_POPULATION_TRAINING_POLICY_VERSION,
            ),
        ),
        validation_policy,
    )
    identities = _population_identities(population_run)
    records_by_identity = {
        record.decision_identity: record for record in bundle.features.records
    }
    if any(identity not in records_by_identity for identity in identities):
        raise ValueError(
            "context population contains an identity absent from the training bundle"
        )

    market_store = ObserverMarketStore(database)
    campaign_store = ObserverCampaignStore(database)
    contexts: list[FastForecastEvaluationContext] = []
    available = 0
    unavailable = 0
    missing_or_stale = 0

    for identity in identities:
        record = records_by_identity[identity]
        if (
            record.quote_mint
            != hydration_policy.regime_read_policy.quote_asset_mint
            or record.quote_mint
            != hydration_policy.safety_probe_identity.output_mint
        ):
            raise ValueError(
                "decision quote mint does not match hydration quote policy"
            )

        try:
            candidate = market_store.resolve_candidate(record.mint)
        except ValueError as exc:
            raise ValueError(
                f"context candidate resolution failed for {record.decision_signature}: {exc}"
            ) from exc
        if candidate.discovered_at_unix_ms > record.decision_observed_at_unix_ms:
            raise ValueError(
                "observer candidate was discovered after the decision timestamp"
            )
        if candidate.venue != record.venue:
            raise ValueError(
                "observer candidate venue does not match decision venue"
            )

        regime_market = campaign_store.build_regime_market_window(
            record.decision_observed_at_unix_ms,
            hydration_policy.regime_read_policy,
            hydration_policy.safety_policy,
            hydration_policy.safety_probe_identity,
            global_risk_halt=hydration_policy.global_risk_halt,
        )
        regime = assess_regime(
            regime_market,
            hydration_policy.regime_policy,
            None,
        )

        quote_identity = ObserverPaperQuoteIdentity(
            candidate_id=candidate.candidate_id,
            purpose=ObserverPaperQuotePurpose.EXIT,
            provider=hydration_policy.exit_quote_provider,
            probe_policy_version=(
                hydration_policy.safety_probe_identity.probe_policy_version
            ),
            input_mint=record.mint,
            output_mint=record.quote_mint,
            taker=hydration_policy.safety_probe_identity.taker,
            input_amount=hydration_policy.safety_probe_identity.input_amount,
            slippage_bps=hydration_policy.safety_probe_identity.slippage_bps,
        )
        quote = campaign_store.latest_paper_quote(
            quote_identity,
            record.decision_observed_at_unix_ms,
        )
        capacity: float | None
        if quote is None:
            capacity = None
            missing_or_stale += 1
        else:
            if quote.quoted_at_unix_ms > record.decision_observed_at_unix_ms:
                raise ValueError(
                    "persisted exit quote is later than the decision timestamp"
                )
            age = (
                record.decision_observed_at_unix_ms
                - quote.quoted_at_unix_ms
            )
            if age > hydration_policy.max_exit_quote_age_ms:
                capacity = None
                missing_or_stale += 1
            elif not quote.route_available:
                capacity = 0.0
                unavailable += 1
            else:
                capacity = (
                    quote.minimum_output_amount
                    / (10 ** hydration_policy.quote_asset_decimals)
                )
                if not math.isfinite(capacity) or capacity < 0:
                    raise ValueError(
                        "derived executable exit capacity is invalid"
                    )
                available += 1

        contexts.append(
            FastForecastEvaluationContext(
                decision_identity=record.decision_identity,
                as_of_unix_ms=record.decision_observed_at_unix_ms,
                market_regime=regime.regime.value,
                strategy_families=hydration_policy.strategy_families,
                executable_exit_capacity_quote=capacity,
                expected_round_trip_cost_bps=(
                    hydration_policy.expected_round_trip_cost_bps
                ),
            )
        )

    corpus = build_fast_forecast_evaluation_context_corpus(
        tuple(contexts)
    )
    return FastForecastContextHydrationResult(
        version=FAST_FORECAST_CONTEXT_HYDRATION_RESULT_VERSION,
        hydration_policy_fingerprint_sha256=(
            fast_forecast_context_hydration_policy_fingerprint_sha256(
                hydration_policy
            )
        ),
        population_validation_run=population_run,
        context_corpus=corpus,
        context_count=len(corpus.contexts),
        available_exit_capacity_count=available,
        unavailable_exit_route_count=unavailable,
        missing_or_stale_exit_quote_count=missing_or_stale,
    )


def write_fast_forecast_context_hydration_artifact(
    *,
    bundle: FastTrainingBundle,
    observer_database_path: str | Path,
    validation_policy: FastChronologicalValidationPolicy,
    horizon_ms: int,
    hydration_policy: FastForecastContextHydrationPolicy,
    destination: str | Path,
) -> FastForecastContextHydrationArtifactManifest:
    _validate_inputs(
        bundle=bundle,
        validation_policy=validation_policy,
        horizon_ms=horizon_ms,
        hydration_policy=hydration_policy,
    )
    database = Path(observer_database_path).expanduser().resolve()
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "context hydration observer database must be an existing regular file"
        )
    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "context hydration artifact destination already exists"
        )

    before = _capture_database(database)
    result = hydrate_fast_forecast_evaluation_contexts(
        bundle=bundle,
        observer_database_path=database,
        validation_policy=validation_policy,
        horizon_ms=horizon_ms,
        hydration_policy=hydration_policy,
    )
    after = _capture_database(database)
    if after != before:
        raise ValueError(
            "context hydration observer database source changed during hydration"
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.tmp-",
            dir=destination_path.parent,
        )
    )
    staging.chmod(0o700)
    try:
        context_path = staging / _CONTEXT_FILE
        policy_path = staging / _POLICY_FILE
        write_fast_forecast_evaluation_context_corpus(
            result.context_corpus,
            context_path,
        )
        policy_path.write_text(
            encode_fast_forecast_context_hydration_policy(
                hydration_policy
            ),
            encoding="utf-8",
        )
        context_path.chmod(0o600)
        policy_path.chmod(0o600)

        material = {
            "schema_name": (
                FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_NAME
            ),
            "schema_version": (
                FAST_FORECAST_CONTEXT_HYDRATION_ARTIFACT_SCHEMA_VERSION
            ),
            "validation_policy_version": validation_policy.version,
            "horizon_ms": horizon_ms,
            "training_bundle_fingerprint_sha256": (
                bundle.manifest.bundle_fingerprint_sha256
            ),
            "feature_source_jsonl_sha256": bundle.features.source_sha256,
            "observer_database_sha256": before.database_sha256,
            "observer_database_wal_sha256": before.wal_sha256,
            "hydration_policy_fingerprint_sha256": (
                result.hydration_policy_fingerprint_sha256
            ),
            "population_validation_run_fingerprint_sha256": (
                result.population_validation_run.validation_run_fingerprint_sha256
            ),
            "context_fingerprint_sha256": (
                result.context_corpus.context_fingerprint_sha256
            ),
            "context_count": result.context_count,
            "available_exit_capacity_count": (
                result.available_exit_capacity_count
            ),
            "unavailable_exit_route_count": (
                result.unavailable_exit_route_count
            ),
            "missing_or_stale_exit_quote_count": (
                result.missing_or_stale_exit_quote_count
            ),
            "contexts_file_sha256": _sha256_file_stable(context_path),
            "policy_file_sha256": _sha256_file_stable(policy_path),
        }
        manifest = FastForecastContextHydrationArtifactManifest(
            schema_name=material["schema_name"],
            schema_version=material["schema_version"],
            validation_policy_version=material[
                "validation_policy_version"
            ],
            horizon_ms=material["horizon_ms"],
            training_bundle_fingerprint_sha256=material[
                "training_bundle_fingerprint_sha256"
            ],
            feature_source_jsonl_sha256=material[
                "feature_source_jsonl_sha256"
            ],
            observer_database_sha256=material[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=material[
                "observer_database_wal_sha256"
            ],
            hydration_policy_fingerprint_sha256=material[
                "hydration_policy_fingerprint_sha256"
            ],
            population_validation_run_fingerprint_sha256=material[
                "population_validation_run_fingerprint_sha256"
            ],
            context_fingerprint_sha256=material[
                "context_fingerprint_sha256"
            ],
            context_count=material["context_count"],
            available_exit_capacity_count=material[
                "available_exit_capacity_count"
            ],
            unavailable_exit_route_count=material[
                "unavailable_exit_route_count"
            ],
            missing_or_stale_exit_quote_count=material[
                "missing_or_stale_exit_quote_count"
            ],
            contexts_file_sha256=material["contexts_file_sha256"],
            policy_file_sha256=material["policy_file_sha256"],
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fast_forecast_context_hydration_artifact(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged context hydration artifact did not round-trip"
            )
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "context hydration artifact destination appeared during write"
            )
        staging.rename(destination_path)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_forecast_context_hydration_artifact(
    path: str | Path,
) -> FastForecastContextHydrationArtifact:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "context hydration artifact must be an existing real directory"
        )
    actual = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "context hydration artifact may contain regular files only"
            )
        actual.add(child.name)
    if actual != _ROOT_ENTRIES:
        raise ValueError(
            "context hydration artifact has unknown or missing entries"
        )

    document = _load_canonical(
        (root / _MANIFEST_FILE).read_text(encoding="utf-8"),
        label="context hydration artifact manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
        raise ValueError(
            "context hydration artifact manifest has unknown or missing fields"
        )
    manifest = FastForecastContextHydrationArtifactManifest(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        validation_policy_version=document[
            "validation_policy_version"
        ],
        horizon_ms=document["horizon_ms"],
        training_bundle_fingerprint_sha256=document[
            "training_bundle_fingerprint_sha256"
        ],
        feature_source_jsonl_sha256=document[
            "feature_source_jsonl_sha256"
        ],
        observer_database_sha256=document[
            "observer_database_sha256"
        ],
        observer_database_wal_sha256=document[
            "observer_database_wal_sha256"
        ],
        hydration_policy_fingerprint_sha256=document[
            "hydration_policy_fingerprint_sha256"
        ],
        population_validation_run_fingerprint_sha256=document[
            "population_validation_run_fingerprint_sha256"
        ],
        context_fingerprint_sha256=document[
            "context_fingerprint_sha256"
        ],
        context_count=document["context_count"],
        available_exit_capacity_count=document[
            "available_exit_capacity_count"
        ],
        unavailable_exit_route_count=document[
            "unavailable_exit_route_count"
        ],
        missing_or_stale_exit_quote_count=document[
            "missing_or_stale_exit_quote_count"
        ],
        contexts_file_sha256=document["contexts_file_sha256"],
        policy_file_sha256=document["policy_file_sha256"],
        artifact_fingerprint_sha256=document[
            "artifact_fingerprint_sha256"
        ],
    )
    material = dict(document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "context hydration artifact fingerprint mismatch"
        )

    context_path = root / _CONTEXT_FILE
    policy_path = root / _POLICY_FILE
    if _sha256_file_stable(context_path) != manifest.contexts_file_sha256:
        raise ValueError("context hydration contexts file hash mismatch")
    if _sha256_file_stable(policy_path) != manifest.policy_file_sha256:
        raise ValueError("context hydration policy file hash mismatch")

    policy = decode_fast_forecast_context_hydration_policy(
        policy_path.read_text(encoding="utf-8")
    )
    policy_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(policy)
    )
    if policy_fingerprint != manifest.hydration_policy_fingerprint_sha256:
        raise ValueError(
            "context hydration policy fingerprint does not match manifest"
        )
    corpus = read_fast_forecast_evaluation_context_corpus(context_path)
    if (
        corpus.context_fingerprint_sha256
        != manifest.context_fingerprint_sha256
        or len(corpus.contexts) != manifest.context_count
    ):
        raise ValueError(
            "context hydration corpus does not match manifest"
        )

    return FastForecastContextHydrationArtifact(
        path=root,
        manifest=manifest,
        policy=policy,
        context_corpus=corpus,
        population_validation_run_fingerprint_sha256=(
            manifest.population_validation_run_fingerprint_sha256
        ),
    )


def _validate_inputs(
    *,
    bundle: FastTrainingBundle,
    validation_policy: FastChronologicalValidationPolicy,
    horizon_ms: int,
    hydration_policy: FastForecastContextHydrationPolicy,
) -> None:
    if type(bundle) is not FastTrainingBundle:
        raise ValueError("bundle must be exact FastTrainingBundle")
    if (
        bundle.manifest.bundle_fingerprint_sha256
        != bundle_logical_fingerprint_sha256(bundle.manifest)
    ):
        raise ValueError("training bundle manifest fingerprint is invalid")
    if type(validation_policy) is not FastChronologicalValidationPolicy:
        raise ValueError(
            "validation_policy must be exact FastChronologicalValidationPolicy"
        )
    _require_positive_int("horizon_ms", horizon_ms)
    if type(hydration_policy) is not FastForecastContextHydrationPolicy:
        raise ValueError(
            "hydration_policy must be exact FastForecastContextHydrationPolicy"
        )


def _population_identities(
    run: FastChronologicalValidationRun,
) -> tuple[tuple[object, ...], ...]:
    identities = tuple(
        prediction.decision_identity
        for fold in run.fold_results
        for prediction in (
            *fold.validation_predictions,
            *fold.test_predictions,
        )
    )
    if not identities:
        raise ValueError("context population validation emitted no predictions")
    if len(set(identities)) != len(identities):
        raise ValueError(
            "context population validation emitted duplicate prediction identities"
        )
    return identities


def _policy_document(
    policy: FastForecastContextHydrationPolicy,
) -> dict[str, object]:
    return {
        "version": policy.version,
        "strategy_families": list(policy.strategy_families),
        "regime_read_policy": _canonicalize(
            asdict(policy.regime_read_policy)
        ),
        "regime_policy": _canonicalize(asdict(policy.regime_policy)),
        "safety_policy": _canonicalize(asdict(policy.safety_policy)),
        "safety_probe_identity": _canonicalize(
            asdict(policy.safety_probe_identity)
        ),
        "global_risk_halt": policy.global_risk_halt,
        "exit_quote_provider": policy.exit_quote_provider,
        "quote_asset_decimals": policy.quote_asset_decimals,
        "max_exit_quote_age_ms": policy.max_exit_quote_age_ms,
        "execution_cost_policy_version": (
            policy.execution_cost_policy_version
        ),
        "expected_round_trip_cost_bps": _canonicalize(
            policy.expected_round_trip_cost_bps
        ),
    }


def _decode_regime_read_policy(
    raw: object,
) -> ObserverRegimeReadPolicy:
    values = _typed_mapping(
        raw,
        ObserverRegimeReadPolicy,
        "regime_read_policy",
    )
    return ObserverRegimeReadPolicy(
        version=_text(values["version"], "regime_read_policy.version"),
        window_ms=_integer(
            values["window_ms"],
            "regime_read_policy.window_ms",
        ),
        max_snapshot_age_ms=_integer(
            values["max_snapshot_age_ms"],
            "regime_read_policy.max_snapshot_age_ms",
        ),
        source_priority=_string_tuple(
            values["source_priority"],
            "regime_read_policy.source_priority",
        ),
        entry_probe_policy_version=_text(
            values["entry_probe_policy_version"],
            "regime_read_policy.entry_probe_policy_version",
        ),
        quote_asset_mint=_text(
            values["quote_asset_mint"],
            "regime_read_policy.quote_asset_mint",
        ),
        entry_input_amount=_integer(
            values["entry_input_amount"],
            "regime_read_policy.entry_input_amount",
        ),
        taker=_text(values["taker"], "regime_read_policy.taker"),
        slippage_bps=_integer(
            values["slippage_bps"],
            "regime_read_policy.slippage_bps",
        ),
    )


def _decode_regime_policy(raw: object) -> RegimePolicy:
    values = _typed_mapping(raw, RegimePolicy, "regime_policy")
    kwargs: dict[str, object] = {}
    integer_fields = {
        "max_source_age_ms",
        "min_candidate_samples",
        "min_performance_sample_count",
    }
    for field in fields(RegimePolicy):
        value = values[field.name]
        if field.name == "version":
            kwargs[field.name] = _text(
                value,
                f"regime_policy.{field.name}",
            )
        elif field.name in integer_fields:
            kwargs[field.name] = _integer(
                value,
                f"regime_policy.{field.name}",
            )
        else:
            kwargs[field.name] = _decode_numeric(
                value,
                f"regime_policy.{field.name}",
            )
    return RegimePolicy(**kwargs)


def _decode_safety_policy(raw: object) -> SafetyPolicy:
    values = _typed_mapping(raw, SafetyPolicy, "safety_policy")
    kwargs: dict[str, object] = {}
    bool_fields = {
        "require_known_authorities",
        "require_liquidity",
        "require_holder_concentration",
        "require_exit_quote",
    }
    for field in fields(SafetyPolicy):
        value = values[field.name]
        if field.name == "version":
            kwargs[field.name] = _text(
                value,
                f"safety_policy.{field.name}",
            )
        elif field.name == "max_critical_data_age_ms":
            kwargs[field.name] = _integer(
                value,
                f"safety_policy.{field.name}",
            )
        elif field.name in bool_fields:
            kwargs[field.name] = _boolean(
                value,
                f"safety_policy.{field.name}",
            )
        else:
            kwargs[field.name] = _decode_optional_numeric(
                value,
                f"safety_policy.{field.name}",
            )
    return SafetyPolicy(**kwargs)


def _decode_safety_probe_identity(
    raw: object,
) -> ObserverSafetyProbeIdentity:
    values = _typed_mapping(
        raw,
        ObserverSafetyProbeIdentity,
        "safety_probe_identity",
    )
    return ObserverSafetyProbeIdentity(
        probe_policy_version=_text(
            values["probe_policy_version"],
            "safety_probe_identity.probe_policy_version",
        ),
        output_mint=_text(
            values["output_mint"],
            "safety_probe_identity.output_mint",
        ),
        input_amount=_integer(
            values["input_amount"],
            "safety_probe_identity.input_amount",
        ),
        taker=_text(
            values["taker"],
            "safety_probe_identity.taker",
        ),
        slippage_bps=_integer(
            values["slippage_bps"],
            "safety_probe_identity.slippage_bps",
        ),
    )


def _typed_mapping(raw: object, cls, name: str) -> dict[str, object]:
    expected = frozenset(field.name for field in fields(cls))
    if not isinstance(raw, dict) or frozenset(raw) != expected:
        raise ValueError(f"{name} fields are incompatible")
    return raw


def _canonicalize(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite policy float is forbidden")
        return {"$float": value.hex()}
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in value.items()
        }
    raise TypeError(
        f"unsupported context hydration policy scalar: {type(value).__name__}"
    )


def _decode_optional_numeric(
    value: object,
    name: str,
) -> int | float | None:
    if value is None:
        return None
    return _decode_numeric(value, name)


def _decode_numeric(value: object, name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} boolean is forbidden")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"{name} raw JSON float is forbidden; tagged float is required"
        )
    if not isinstance(value, dict) or frozenset(value) != {"$float"}:
        raise ValueError(
            f"{name} must be an integer or exact tagged float"
        )
    raw = value["$float"]
    if not isinstance(raw, str):
        raise ValueError(f"{name} tagged float must be text")
    try:
        decoded = float.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"{name} tagged float is malformed") from exc
    if not math.isfinite(decoded):
        raise ValueError(f"{name} tagged float must be finite")
    return decoded


def _manifest_document(
    manifest: FastForecastContextHydrationArtifactManifest,
) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "validation_policy_version": manifest.validation_policy_version,
        "horizon_ms": manifest.horizon_ms,
        "training_bundle_fingerprint_sha256": (
            manifest.training_bundle_fingerprint_sha256
        ),
        "feature_source_jsonl_sha256": (
            manifest.feature_source_jsonl_sha256
        ),
        "observer_database_sha256": manifest.observer_database_sha256,
        "observer_database_wal_sha256": (
            manifest.observer_database_wal_sha256
        ),
        "hydration_policy_fingerprint_sha256": (
            manifest.hydration_policy_fingerprint_sha256
        ),
        "population_validation_run_fingerprint_sha256": (
            manifest.population_validation_run_fingerprint_sha256
        ),
        "context_fingerprint_sha256": (
            manifest.context_fingerprint_sha256
        ),
        "context_count": manifest.context_count,
        "available_exit_capacity_count": (
            manifest.available_exit_capacity_count
        ),
        "unavailable_exit_route_count": (
            manifest.unavailable_exit_route_count
        ),
        "missing_or_stale_exit_quote_count": (
            manifest.missing_or_stale_exit_quote_count
        ),
        "contexts_file_sha256": manifest.contexts_file_sha256,
        "policy_file_sha256": manifest.policy_file_sha256,
        "artifact_fingerprint_sha256": (
            manifest.artifact_fingerprint_sha256
        ),
    }


def _capture_database(path: Path) -> _DatabaseSnapshot:
    wal = Path(str(path) + "-wal")
    return _DatabaseSnapshot(
        database_sha256=_sha256_file_stable(path),
        wal_sha256=_sha256_file_stable(wal) if wal.is_file() else None,
    )


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(f"{label} must have exactly one trailing newline")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical(value) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be an existing regular file: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("source changed while fingerprinting")
    return digest.hexdigest()


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty string array")
    return tuple(value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _require_non_empty(name: str, value: object) -> None:
    _text(value, name)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
