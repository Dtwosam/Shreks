from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from shreks_brain.fast_campaign import (
    FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    FastCampaignActionConstraints,
    FastCampaignDecisionPosition,
    FastCampaignDecisionResult,
    FastCampaignReduceExecutionCost,
    build_fast_campaign_decision_batch,
    build_fast_campaign_decision_request,
    decode_fast_campaign_decision_results,
)
from shreks_brain.fast_campaign_offline import (
    evaluate_fast_campaign_decision_batch_offline,
)
from shreks_brain.fast_champion import read_fast_forecast_champion
from shreks_brain.fast_learning import FastForecastTarget
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
)

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest


FAST_PAPER_SHADOW_DECISION_SCHEMA_NAME = "shreks.fast_paper_shadow_decision"
FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION = 1

_EXECUTABLE = "EXECUTABLE"
_UNAVAILABLE = "UNAVAILABLE"
_ACTIVE_FORECAST_TARGETS = (
    FastForecastTarget.ENDPOINT_COST_ADJUSTED_RETURN_BPS,
    FastForecastTarget.ENDPOINT_RETURN_BPS,
    FastForecastTarget.MAE_BPS,
    FastForecastTarget.REVERSAL_OCCURRED,
    FastForecastTarget.ROUTE_UNAVAILABILITY_OBSERVED,
)
_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "source_event_id",
        "market_key",
        "source_sequence",
        "as_of_unix_ms",
        "evaluated_at_unix_ms",
        "decision_latency_ns",
        "position",
        "constraints",
        "entry_quote",
        "exit_quote",
        "reduction_quotes",
        "entry_execution_cost_bps",
        "exit_execution_cost_bps",
        "decision",
        "result_batch_fingerprint_sha256",
        "evidence_fingerprint_sha256",
    }
)
_QUOTE_KEYS = frozenset(
    {
        "provider",
        "mint",
        "quote_mint",
        "observed_at_unix_ms",
        "state",
        "reference_price_quote",
        "execution_price_quote",
        "quoted_base_quantity",
        "available_base_quantity",
    }
)
_REDUCTION_KEYS = frozenset({"target_exposure_fraction", "quote"})
_POSITION_FLAT_KEYS = frozenset({"kind"})
_POSITION_OPEN_KEYS = frozenset({"kind", "current_exposure_fraction"})
_CONSTRAINT_KEYS = frozenset(
    {
        "max_exposure_fraction",
        "buy_economically_allowed",
        "expected_future_exit_cost_bps",
        "reduce_execution_costs",
        "sell_executable",
        "sell_now_cost_bps",
        "force_sell",
    }
)
_REDUCE_COST_KEYS = frozenset(
    {"target_exposure_fraction", "execution_cost_bps"}
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowQuoteEvidence:
    provider: str
    mint: str
    quote_mint: str
    observed_at_unix_ms: int
    state: str
    reference_price_quote: float | None
    execution_price_quote: float | None
    quoted_base_quantity: float | None
    available_base_quantity: float | None

    def __post_init__(self) -> None:
        for name in ("provider", "mint", "quote_mint"):
            _require_non_empty(name, getattr(self, name))
        _require_non_negative_int(
            "observed_at_unix_ms", self.observed_at_unix_ms
        )
        if self.state not in {_EXECUTABLE, _UNAVAILABLE}:
            raise ValueError(
                "shadow quote state must be EXECUTABLE or UNAVAILABLE"
            )
        values = (
            self.reference_price_quote,
            self.execution_price_quote,
            self.quoted_base_quantity,
            self.available_base_quantity,
        )
        if self.state == _EXECUTABLE:
            if any(value is None for value in values):
                raise ValueError(
                    "executable shadow quote requires complete price/capacity evidence"
                )
            for name in (
                "reference_price_quote",
                "execution_price_quote",
                "quoted_base_quantity",
                "available_base_quantity",
            ):
                _require_positive_finite(name, getattr(self, name))
        elif any(value is not None for value in values):
            raise ValueError(
                "unavailable shadow quote cannot carry price/capacity evidence"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowReductionQuote:
    target_exposure_fraction: float
    quote: FastPaperShadowQuoteEvidence

    def __post_init__(self) -> None:
        _require_finite_interval(
            "target_exposure_fraction",
            self.target_exposure_fraction,
            minimum=0.0,
            maximum=1.0,
            minimum_open=False,
            maximum_open=True,
        )
        if type(self.quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "reduction quote must be exact FastPaperShadowQuoteEvidence"
            )


@dataclass(frozen=True, slots=True)
class FastPaperShadowDecisionEvidence:
    schema_name: str
    schema_version: int
    release_source_sha: str
    manifest_fingerprint_sha256: str
    champion_version: str
    champion_fingerprint_sha256: str
    action_policy_version: int
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    evaluated_at_unix_ms: int
    decision_latency_ns: int
    position: FastCampaignDecisionPosition
    constraints: FastCampaignActionConstraints
    entry_quote: FastPaperShadowQuoteEvidence
    exit_quote: FastPaperShadowQuoteEvidence
    reduction_quotes: tuple[FastPaperShadowReductionQuote, ...]
    entry_execution_cost_bps: float | None
    exit_execution_cost_bps: float | None
    decision: FastCampaignDecisionResult
    result_batch_fingerprint_sha256: str
    evidence_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_DECISION_SCHEMA_NAME:
            raise ValueError("shadow decision schema_name is incompatible")
        if self.schema_version != FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION:
            raise ValueError("shadow decision schema_version is incompatible")
        _require_source_sha("release_source_sha", self.release_source_sha)
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )
        _require_non_empty("champion_version", self.champion_version)
        _require_sha256(
            "champion_fingerprint_sha256",
            self.champion_fingerprint_sha256,
        )
        _require_positive_int(
            "action_policy_version", self.action_policy_version
        )
        _require_non_empty("source_event_id", self.source_event_id)
        _require_non_empty("market_key", self.market_key)
        _require_positive_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int(
            "evaluated_at_unix_ms", self.evaluated_at_unix_ms
        )
        _require_non_negative_int(
            "decision_latency_ns", self.decision_latency_ns
        )
        if type(self.position) is not FastCampaignDecisionPosition:
            raise ValueError(
                "position must be exact FastCampaignDecisionPosition"
            )
        if type(self.constraints) is not FastCampaignActionConstraints:
            raise ValueError(
                "constraints must be exact FastCampaignActionConstraints"
            )
        if type(self.entry_quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "entry_quote must be exact FastPaperShadowQuoteEvidence"
            )
        if type(self.exit_quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "exit_quote must be exact FastPaperShadowQuoteEvidence"
            )
        if (
            not isinstance(self.reduction_quotes, tuple)
            or not all(
                type(value) is FastPaperShadowReductionQuote
                for value in self.reduction_quotes
            )
        ):
            raise ValueError(
                "reduction_quotes must contain exact FastPaperShadowReductionQuote values"
            )
        for name in (
            "entry_execution_cost_bps",
            "exit_execution_cost_bps",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_finite(name, value)
        if type(self.decision) is not FastCampaignDecisionResult:
            raise ValueError(
                "decision must be exact FastCampaignDecisionResult"
            )
        _require_sha256(
            "result_batch_fingerprint_sha256",
            self.result_batch_fingerprint_sha256,
        )
        _require_sha256(
            "evidence_fingerprint_sha256",
            self.evidence_fingerprint_sha256,
        )
        _validate_evidence_internal(self)


def evaluate_fast_paper_shadow_decision(
    manifest: FastPaperRuntimeManifest,
    record: FastTrainingFeatureRecord,
    position: FastCampaignDecisionPosition,
    *,
    evaluated_at_unix_ms: int,
    max_exposure_fraction: float,
    entry_quote: FastPaperShadowQuoteEvidence,
    exit_quote: FastPaperShadowQuoteEvidence,
    reduction_quotes: tuple[FastPaperShadowReductionQuote, ...] = (),
    force_sell: bool = False,
) -> FastPaperShadowDecisionEvidence:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError(
            "record must be exact FastTrainingFeatureRecord"
        )
    if type(position) is not FastCampaignDecisionPosition:
        raise ValueError(
            "position must be exact FastCampaignDecisionPosition"
        )
    if type(entry_quote) is not FastPaperShadowQuoteEvidence:
        raise ValueError(
            "entry_quote must be exact FastPaperShadowQuoteEvidence"
        )
    if type(exit_quote) is not FastPaperShadowQuoteEvidence:
        raise ValueError(
            "exit_quote must be exact FastPaperShadowQuoteEvidence"
        )
    if (
        not isinstance(reduction_quotes, tuple)
        or not all(
            type(value) is FastPaperShadowReductionQuote
            for value in reduction_quotes
        )
    ):
        raise ValueError(
            "reduction_quotes must contain exact FastPaperShadowReductionQuote values"
        )
    _require_non_negative_int(
        "evaluated_at_unix_ms", evaluated_at_unix_ms
    )
    if evaluated_at_unix_ms < record.decision_observed_at_unix_ms:
        raise ValueError(
            "shadow evaluation timestamp cannot precede decision timestamp"
        )
    _require_finite_interval(
        "max_exposure_fraction",
        max_exposure_fraction,
        minimum=0.0,
        maximum=1.0,
    )
    if type(force_sell) is not bool:
        raise ValueError("force_sell must be bool")

    verify_fast_paper_runtime_bindings(manifest)
    _validate_champion_chronology(manifest, record)

    constraints, entry_cost, exit_cost = _constraints_from_quotes(
        record,
        position=position,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        max_exposure_fraction=max_exposure_fraction,
        entry_quote=entry_quote,
        exit_quote=exit_quote,
        reduction_quotes=reduction_quotes,
        force_sell=force_sell,
    )
    request = build_fast_campaign_decision_request(
        record,
        position,
        constraints,
    )
    batch = build_fast_campaign_decision_batch(
        manifest.action_policy,
        (request,),
    )

    started = time.monotonic_ns()
    results = evaluate_fast_campaign_decision_batch_offline(
        binary_path=manifest.decision_binary_path,
        champion_path=manifest.champion_path,
        batch=batch,
    )
    finished = time.monotonic_ns()
    if finished < started:
        raise ValueError("monotonic shadow decision clock regressed")
    latency = finished - started

    verify_fast_paper_runtime_bindings(manifest)
    if results.champion_version != manifest.champion_version:
        raise ValueError(
            "shadow Rust result champion version mismatch"
        )
    if (
        results.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "shadow Rust result champion fingerprint mismatch"
        )
    if len(results.decisions) != 1:
        raise ValueError(
            "shadow Rust result must contain exactly one decision"
        )
    decision = results.decisions[0]
    _validate_result_identity(
        request_source_event_id=request.source_event_id,
        request_market_key=request.market_key,
        request_sequence=request.source_sequence,
        request_as_of_unix_ms=request.as_of_unix_ms,
        expected_policy_version=manifest.action_policy.version,
        decision=decision,
    )
    _validate_results_fingerprint(
        champion_version=results.champion_version,
        champion_fingerprint_sha256=(
            results.champion_fingerprint_sha256
        ),
        decision=decision,
        fingerprint=results.batch_fingerprint_sha256,
    )

    values = {
        "schema_name": FAST_PAPER_SHADOW_DECISION_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION,
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
        "source_event_id": request.source_event_id,
        "market_key": request.market_key,
        "source_sequence": request.source_sequence,
        "as_of_unix_ms": request.as_of_unix_ms,
        "evaluated_at_unix_ms": evaluated_at_unix_ms,
        "decision_latency_ns": latency,
        "position": position,
        "constraints": constraints,
        "entry_quote": entry_quote,
        "exit_quote": exit_quote,
        "reduction_quotes": reduction_quotes,
        "entry_execution_cost_bps": entry_cost,
        "exit_execution_cost_bps": exit_cost,
        "decision": decision,
        "result_batch_fingerprint_sha256": (
            results.batch_fingerprint_sha256
        ),
    }
    fingerprint = _sha256_canonical(_evidence_material(values))
    return FastPaperShadowDecisionEvidence(
        **values,
        evidence_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_decision_evidence(
    evidence: FastPaperShadowDecisionEvidence,
    destination: str | Path,
) -> None:
    if type(evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "evidence must be exact FastPaperShadowDecisionEvidence"
        )
    _validate_evidence_fingerprint(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "shadow decision evidence destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(_document(evidence)) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    os.chmod(path, 0o600)


def read_fast_paper_shadow_decision_evidence(
    source: str | Path,
) -> FastPaperShadowDecisionEvidence:
    path = Path(source)
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow decision evidence source must be a regular non-symlink file"
        )
    payload = path.read_text(encoding="utf-8")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            "shadow decision evidence must have exactly one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "shadow decision evidence is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "shadow decision evidence must be a JSON object"
        )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow decision evidence has unknown or missing fields"
        )
    if payload != _canonical(document) + "\n":
        raise ValueError(
            "shadow decision evidence must use canonical JSON"
        )

    position = _decode_position(document["position"])
    constraints = _decode_constraints(document["constraints"])
    entry_quote = _decode_quote(document["entry_quote"])
    exit_quote = _decode_quote(document["exit_quote"])
    raw_reductions = document["reduction_quotes"]
    if not isinstance(raw_reductions, list):
        raise ValueError(
            "shadow decision reduction_quotes must be a list"
        )
    reduction_quotes = tuple(
        _decode_reduction_quote(value)
        for value in raw_reductions
    )
    decision = _decode_decision(
        champion_version=document["champion_version"],
        champion_fingerprint_sha256=document[
            "champion_fingerprint_sha256"
        ],
        fingerprint=document["result_batch_fingerprint_sha256"],
        value=document["decision"],
    )
    evidence = FastPaperShadowDecisionEvidence(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        release_source_sha=document["release_source_sha"],
        manifest_fingerprint_sha256=document[
            "manifest_fingerprint_sha256"
        ],
        champion_version=document["champion_version"],
        champion_fingerprint_sha256=document[
            "champion_fingerprint_sha256"
        ],
        action_policy_version=document["action_policy_version"],
        source_event_id=document["source_event_id"],
        market_key=document["market_key"],
        source_sequence=document["source_sequence"],
        as_of_unix_ms=document["as_of_unix_ms"],
        evaluated_at_unix_ms=document["evaluated_at_unix_ms"],
        decision_latency_ns=document["decision_latency_ns"],
        position=position,
        constraints=constraints,
        entry_quote=entry_quote,
        exit_quote=exit_quote,
        reduction_quotes=reduction_quotes,
        entry_execution_cost_bps=document[
            "entry_execution_cost_bps"
        ],
        exit_execution_cost_bps=document[
            "exit_execution_cost_bps"
        ],
        decision=decision,
        result_batch_fingerprint_sha256=document[
            "result_batch_fingerprint_sha256"
        ],
        evidence_fingerprint_sha256=document[
            "evidence_fingerprint_sha256"
        ],
    )
    _validate_evidence_fingerprint(evidence)
    return evidence


def _constraints_from_quotes(
    record: FastTrainingFeatureRecord,
    *,
    position: FastCampaignDecisionPosition,
    evaluated_at_unix_ms: int,
    max_exposure_fraction: float,
    entry_quote: FastPaperShadowQuoteEvidence,
    exit_quote: FastPaperShadowQuoteEvidence,
    reduction_quotes: tuple[FastPaperShadowReductionQuote, ...],
    force_sell: bool,
) -> tuple[FastCampaignActionConstraints, float | None, float | None]:
    _validate_quote(
        record,
        entry_quote,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        direction="ENTRY",
    )
    _validate_quote(
        record,
        exit_quote,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        direction="EXIT",
    )
    if position.kind == "FLAT" and reduction_quotes:
        raise ValueError(
            "FLAT shadow position cannot carry reduction quote evidence"
        )

    entry_cost = (
        _execution_cost_bps(entry_quote, direction="BUY")
        if entry_quote.state == _EXECUTABLE
        else None
    )
    exit_cost = (
        _execution_cost_bps(exit_quote, direction="SELL")
        if exit_quote.state == _EXECUTABLE
        else None
    )
    reduce_costs: list[FastCampaignReduceExecutionCost] = []
    previous_target: float | None = None
    for item in reduction_quotes:
        target = item.target_exposure_fraction
        if previous_target is not None and target <= previous_target:
            raise ValueError(
                "shadow reduction quotes must be in strictly increasing target order"
            )
        previous_target = target
        _validate_quote(
            record,
            item.quote,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            direction="REDUCE",
        )
        if position.kind != "OPEN":
            raise ValueError(
                "reduction quote requires OPEN shadow position"
            )
        current = position.current_exposure_fraction
        assert current is not None
        if target >= current:
            raise ValueError(
                "shadow reduction target must be below current exposure"
            )
        if item.quote.state == _EXECUTABLE:
            reduce_costs.append(
                FastCampaignReduceExecutionCost(
                    target_exposure_fraction=target,
                    execution_cost_bps=_execution_cost_bps(
                        item.quote,
                        direction="SELL",
                    ),
                )
            )

    sell_executable = exit_quote.state == _EXECUTABLE
    buy_allowed = (
        entry_quote.state == _EXECUTABLE
        and sell_executable
        and max_exposure_fraction > 0.0
    )
    constraints = FastCampaignActionConstraints(
        max_exposure_fraction=max_exposure_fraction,
        buy_economically_allowed=buy_allowed,
        expected_future_exit_cost_bps=(
            0.0 if exit_cost is None else exit_cost
        ),
        reduce_execution_costs=tuple(reduce_costs),
        sell_executable=sell_executable,
        sell_now_cost_bps=0.0 if exit_cost is None else exit_cost,
        force_sell=force_sell,
    )
    return constraints, entry_cost, exit_cost


def _validate_quote(
    record: FastTrainingFeatureRecord,
    quote: FastPaperShadowQuoteEvidence,
    *,
    evaluated_at_unix_ms: int,
    direction: str,
) -> None:
    if quote.mint != record.mint:
        raise ValueError(
            f"shadow {direction} quote mint mismatch"
        )
    if quote.quote_mint != record.quote_mint:
        raise ValueError(
            f"shadow {direction} quote quote-mint mismatch"
        )
    if not (
        record.decision_observed_at_unix_ms
        <= quote.observed_at_unix_ms
        <= evaluated_at_unix_ms
    ):
        raise ValueError(
            f"shadow {direction} quote chronology is outside decision-safe timestamp bounds"
        )
    if quote.state == _EXECUTABLE:
        reference = quote.reference_price_quote
        assert reference is not None
        if not math.isclose(
            reference,
            record.decision_executable_entry_price_quote,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError(
                f"shadow {direction} quote reference price provenance mismatch"
            )


def _validate_champion_chronology(
    manifest: FastPaperRuntimeManifest,
    record: FastTrainingFeatureRecord,
) -> None:
    champion = read_fast_forecast_champion(
        Path(manifest.champion_path)
    )
    if champion.champion_version != manifest.champion_version:
        raise ValueError(
            "shadow champion version drift"
        )
    if (
        champion.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "shadow champion fingerprint drift"
        )
    if champion.feature_schema_version != record.schema_version:
        raise ValueError(
            "shadow champion/feature schema mismatch"
        )
    if (
        champion.selection.decided_at_unix_ms
        > record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "shadow decision precedes champion selection chronology"
        )

    max_training_at = -1
    for horizon_ms in manifest.action_policy.horizons_ms:
        for target in _ACTIVE_FORECAST_TARGETS:
            try:
                member = champion.member_for(target, horizon_ms)
            except KeyError as exc:
                raise ValueError(
                    "shadow champion is missing an active target/horizon member"
                ) from exc
            max_training_at = max(
                max_training_at,
                member.forecast_artifact.max_training_decision_observed_at_unix_ms,
            )
    if max_training_at >= record.decision_observed_at_unix_ms:
        raise ValueError(
            "shadow champion training chronology reaches or exceeds decision timestamp"
        )


def _validate_result_identity(
    *,
    request_source_event_id: str,
    request_market_key: str,
    request_sequence: int,
    request_as_of_unix_ms: int,
    expected_policy_version: int,
    decision: FastCampaignDecisionResult,
) -> None:
    expected = (
        request_source_event_id,
        request_market_key,
        request_sequence,
        request_as_of_unix_ms,
        expected_policy_version,
    )
    actual = (
        decision.source_event_id,
        decision.market_key,
        decision.source_sequence,
        decision.as_of_unix_ms,
        decision.policy_version,
    )
    if actual != expected:
        raise ValueError(
            "shadow Rust result identity/policy mismatch"
        )


def _validate_results_fingerprint(
    *,
    champion_version: str,
    champion_fingerprint_sha256: str,
    decision: FastCampaignDecisionResult,
    fingerprint: str,
) -> None:
    _require_sha256("result batch fingerprint", fingerprint)
    material = {
        "schema_name": FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
        "schema_version": FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        "champion_version": champion_version,
        "champion_fingerprint_sha256": champion_fingerprint_sha256,
        "decisions": [_decision_document(decision)],
    }
    if _sha256_canonical(material) != fingerprint:
        raise ValueError(
            "shadow Rust result batch fingerprint mismatch"
        )


def _validate_evidence_internal(
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    decision = evidence.decision
    if (
        decision.source_event_id != evidence.source_event_id
        or decision.market_key != evidence.market_key
        or decision.source_sequence != evidence.source_sequence
        or decision.as_of_unix_ms != evidence.as_of_unix_ms
        or decision.policy_version != evidence.action_policy_version
    ):
        raise ValueError(
            "shadow evidence decision identity/policy mismatch"
        )
    expected_current = (
        0.0
        if evidence.position.kind == "FLAT"
        else evidence.position.current_exposure_fraction
    )
    assert expected_current is not None
    if not math.isclose(
        decision.current_exposure_fraction,
        expected_current,
        rel_tol=1e-12,
        abs_tol=1e-15,
    ):
        raise ValueError(
            "shadow evidence decision exposure does not match position"
        )

    quotes = (
        evidence.entry_quote,
        evidence.exit_quote,
        *(item.quote for item in evidence.reduction_quotes),
    )
    for quote in quotes:
        if not (
            evidence.as_of_unix_ms
            <= quote.observed_at_unix_ms
            <= evidence.evaluated_at_unix_ms
        ):
            raise ValueError(
                "shadow evidence quote chronology is incompatible"
            )
        if not evidence.market_key.endswith(
            f":{quote.mint}:{quote.quote_mint}"
        ):
            raise ValueError(
                "shadow evidence quote market attribution mismatch"
            )

    executable_references = tuple(
        quote.reference_price_quote
        for quote in quotes
        if quote.state == _EXECUTABLE
    )
    if executable_references:
        reference = executable_references[0]
        assert reference is not None
        if any(
            value is None
            or not math.isclose(
                value,
                reference,
                rel_tol=1e-12,
                abs_tol=1e-15,
            )
            for value in executable_references
        ):
            raise ValueError(
                "shadow evidence executable quote reference prices drift"
            )

    expected_entry_cost = (
        _execution_cost_bps(
            evidence.entry_quote,
            direction="BUY",
        )
        if evidence.entry_quote.state == _EXECUTABLE
        else None
    )
    expected_exit_cost = (
        _execution_cost_bps(
            evidence.exit_quote,
            direction="SELL",
        )
        if evidence.exit_quote.state == _EXECUTABLE
        else None
    )
    if not _optional_close(
        evidence.entry_execution_cost_bps,
        expected_entry_cost,
    ):
        raise ValueError(
            "shadow evidence entry execution cost mismatch"
        )
    if not _optional_close(
        evidence.exit_execution_cost_bps,
        expected_exit_cost,
    ):
        raise ValueError(
            "shadow evidence exit execution cost mismatch"
        )

    if evidence.position.kind == "FLAT" and evidence.reduction_quotes:
        raise ValueError(
            "FLAT shadow evidence cannot carry reduction quotes"
        )
    expected_reduce = tuple(
        FastCampaignReduceExecutionCost(
            target_exposure_fraction=item.target_exposure_fraction,
            execution_cost_bps=_execution_cost_bps(
                item.quote,
                direction="SELL",
            ),
        )
        for item in evidence.reduction_quotes
        if item.quote.state == _EXECUTABLE
    )
    if evidence.position.kind == "OPEN":
        current = evidence.position.current_exposure_fraction
        assert current is not None
        if any(
            item.target_exposure_fraction >= current
            for item in evidence.reduction_quotes
        ):
            raise ValueError(
                "shadow evidence reduction target is not below current exposure"
            )

    constraints = evidence.constraints
    expected_sell_executable = (
        evidence.exit_quote.state == _EXECUTABLE
    )
    expected_buy_allowed = (
        evidence.entry_quote.state == _EXECUTABLE
        and expected_sell_executable
        and constraints.max_exposure_fraction > 0.0
    )
    if constraints.buy_economically_allowed != expected_buy_allowed:
        raise ValueError(
            "shadow evidence BUY executability constraint mismatch"
        )
    if constraints.sell_executable != expected_sell_executable:
        raise ValueError(
            "shadow evidence SELL executability constraint mismatch"
        )
    normalized_exit_cost = (
        0.0 if expected_exit_cost is None else expected_exit_cost
    )
    if not math.isclose(
        constraints.expected_future_exit_cost_bps,
        normalized_exit_cost,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "shadow evidence future exit cost constraint mismatch"
        )
    if not math.isclose(
        constraints.sell_now_cost_bps,
        normalized_exit_cost,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "shadow evidence current sell cost constraint mismatch"
        )
    if len(constraints.reduce_execution_costs) != len(expected_reduce):
        raise ValueError(
            "shadow evidence reduction execution-cost population mismatch"
        )
    for actual, expected in zip(
        constraints.reduce_execution_costs,
        expected_reduce,
    ):
        if (
            not math.isclose(
                actual.target_exposure_fraction,
                expected.target_exposure_fraction,
                rel_tol=1e-12,
                abs_tol=1e-15,
            )
            or not math.isclose(
                actual.execution_cost_bps,
                expected.execution_cost_bps,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                "shadow evidence reduction execution cost mismatch"
            )

    _validate_results_fingerprint(
        champion_version=evidence.champion_version,
        champion_fingerprint_sha256=(
            evidence.champion_fingerprint_sha256
        ),
        decision=decision,
        fingerprint=evidence.result_batch_fingerprint_sha256,
    )


def _validate_evidence_fingerprint(
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    values = {
        name: getattr(evidence, name)
        for name in (
            "schema_name",
            "schema_version",
            "release_source_sha",
            "manifest_fingerprint_sha256",
            "champion_version",
            "champion_fingerprint_sha256",
            "action_policy_version",
            "source_event_id",
            "market_key",
            "source_sequence",
            "as_of_unix_ms",
            "evaluated_at_unix_ms",
            "decision_latency_ns",
            "position",
            "constraints",
            "entry_quote",
            "exit_quote",
            "reduction_quotes",
            "entry_execution_cost_bps",
            "exit_execution_cost_bps",
            "decision",
            "result_batch_fingerprint_sha256",
        )
    }
    expected = _sha256_canonical(_evidence_material(values))
    if evidence.evidence_fingerprint_sha256 != expected:
        raise ValueError(
            "shadow decision evidence fingerprint mismatch"
        )


def _document(
    evidence: FastPaperShadowDecisionEvidence,
) -> dict[str, object]:
    values = {
        name: getattr(evidence, name)
        for name in (
            "schema_name",
            "schema_version",
            "release_source_sha",
            "manifest_fingerprint_sha256",
            "champion_version",
            "champion_fingerprint_sha256",
            "action_policy_version",
            "source_event_id",
            "market_key",
            "source_sequence",
            "as_of_unix_ms",
            "evaluated_at_unix_ms",
            "decision_latency_ns",
            "position",
            "constraints",
            "entry_quote",
            "exit_quote",
            "reduction_quotes",
            "entry_execution_cost_bps",
            "exit_execution_cost_bps",
            "decision",
            "result_batch_fingerprint_sha256",
        )
    }
    return {
        **_evidence_material(values),
        "evidence_fingerprint_sha256": (
            evidence.evidence_fingerprint_sha256
        ),
    }


def _evidence_material(
    values: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "release_source_sha": values["release_source_sha"],
        "manifest_fingerprint_sha256": values[
            "manifest_fingerprint_sha256"
        ],
        "champion_version": values["champion_version"],
        "champion_fingerprint_sha256": values[
            "champion_fingerprint_sha256"
        ],
        "action_policy_version": values["action_policy_version"],
        "source_event_id": values["source_event_id"],
        "market_key": values["market_key"],
        "source_sequence": values["source_sequence"],
        "as_of_unix_ms": values["as_of_unix_ms"],
        "evaluated_at_unix_ms": values["evaluated_at_unix_ms"],
        "decision_latency_ns": values["decision_latency_ns"],
        "position": _position_document(values["position"]),
        "constraints": _constraints_document(values["constraints"]),
        "entry_quote": _quote_document(values["entry_quote"]),
        "exit_quote": _quote_document(values["exit_quote"]),
        "reduction_quotes": [
            _reduction_quote_document(item)
            for item in values["reduction_quotes"]
        ],
        "entry_execution_cost_bps": values[
            "entry_execution_cost_bps"
        ],
        "exit_execution_cost_bps": values[
            "exit_execution_cost_bps"
        ],
        "decision": _decision_document(values["decision"]),
        "result_batch_fingerprint_sha256": values[
            "result_batch_fingerprint_sha256"
        ],
    }


def _position_document(
    value: object,
) -> dict[str, object]:
    if type(value) is not FastCampaignDecisionPosition:
        raise ValueError(
            "shadow position must be exact FastCampaignDecisionPosition"
        )
    if value.kind == "FLAT":
        return {"kind": "FLAT"}
    return {
        "kind": "OPEN",
        "current_exposure_fraction": value.current_exposure_fraction,
    }


def _constraints_document(
    value: object,
) -> dict[str, object]:
    if type(value) is not FastCampaignActionConstraints:
        raise ValueError(
            "shadow constraints must be exact FastCampaignActionConstraints"
        )
    return {
        "max_exposure_fraction": value.max_exposure_fraction,
        "buy_economically_allowed": value.buy_economically_allowed,
        "expected_future_exit_cost_bps": (
            value.expected_future_exit_cost_bps
        ),
        "reduce_execution_costs": [
            {
                "target_exposure_fraction": item.target_exposure_fraction,
                "execution_cost_bps": item.execution_cost_bps,
            }
            for item in value.reduce_execution_costs
        ],
        "sell_executable": value.sell_executable,
        "sell_now_cost_bps": value.sell_now_cost_bps,
        "force_sell": value.force_sell,
    }


def _quote_document(
    value: object,
) -> dict[str, object]:
    if type(value) is not FastPaperShadowQuoteEvidence:
        raise ValueError(
            "shadow quote must be exact FastPaperShadowQuoteEvidence"
        )
    return asdict(value)


def _reduction_quote_document(
    value: object,
) -> dict[str, object]:
    if type(value) is not FastPaperShadowReductionQuote:
        raise ValueError(
            "shadow reduction quote must be exact FastPaperShadowReductionQuote"
        )
    return {
        "target_exposure_fraction": value.target_exposure_fraction,
        "quote": _quote_document(value.quote),
    }


def _decision_document(
    value: object,
) -> dict[str, object]:
    if type(value) is not FastCampaignDecisionResult:
        raise ValueError(
            "shadow decision must be exact FastCampaignDecisionResult"
        )
    return asdict(value)


def _decode_position(value: object) -> FastCampaignDecisionPosition:
    if not isinstance(value, dict):
        raise ValueError("shadow position must be an object")
    kind = value.get("kind")
    if kind == "FLAT":
        if frozenset(value) != _POSITION_FLAT_KEYS:
            raise ValueError("FLAT shadow position fields are invalid")
        return FastCampaignDecisionPosition(kind="FLAT")
    if kind == "OPEN":
        if frozenset(value) != _POSITION_OPEN_KEYS:
            raise ValueError("OPEN shadow position fields are invalid")
        return FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=value[
                "current_exposure_fraction"
            ],
        )
    raise ValueError("shadow position kind is unsupported")


def _decode_constraints(value: object) -> FastCampaignActionConstraints:
    if not isinstance(value, dict) or frozenset(value) != _CONSTRAINT_KEYS:
        raise ValueError(
            "shadow constraints have unknown or missing fields"
        )
    raw_reduce = value["reduce_execution_costs"]
    if not isinstance(raw_reduce, list):
        raise ValueError(
            "shadow reduce_execution_costs must be a list"
        )
    costs = []
    for item in raw_reduce:
        if (
            not isinstance(item, dict)
            or frozenset(item) != _REDUCE_COST_KEYS
        ):
            raise ValueError(
                "shadow reduction cost has unknown or missing fields"
            )
        costs.append(FastCampaignReduceExecutionCost(**item))
    return FastCampaignActionConstraints(
        max_exposure_fraction=value["max_exposure_fraction"],
        buy_economically_allowed=value["buy_economically_allowed"],
        expected_future_exit_cost_bps=value[
            "expected_future_exit_cost_bps"
        ],
        reduce_execution_costs=tuple(costs),
        sell_executable=value["sell_executable"],
        sell_now_cost_bps=value["sell_now_cost_bps"],
        force_sell=value["force_sell"],
    )


def _decode_quote(value: object) -> FastPaperShadowQuoteEvidence:
    if not isinstance(value, dict) or frozenset(value) != _QUOTE_KEYS:
        raise ValueError(
            "shadow quote has unknown or missing fields"
        )
    return FastPaperShadowQuoteEvidence(**value)


def _decode_reduction_quote(
    value: object,
) -> FastPaperShadowReductionQuote:
    if not isinstance(value, dict) or frozenset(value) != _REDUCTION_KEYS:
        raise ValueError(
            "shadow reduction quote has unknown or missing fields"
        )
    return FastPaperShadowReductionQuote(
        target_exposure_fraction=value[
            "target_exposure_fraction"
        ],
        quote=_decode_quote(value["quote"]),
    )


def _decode_decision(
    *,
    champion_version: str,
    champion_fingerprint_sha256: str,
    fingerprint: str,
    value: object,
) -> FastCampaignDecisionResult:
    material = {
        "schema_name": FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME,
        "schema_version": FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        "champion_version": champion_version,
        "champion_fingerprint_sha256": champion_fingerprint_sha256,
        "decisions": [value],
    }
    document = {
        **material,
        "batch_fingerprint_sha256": fingerprint,
    }
    results = decode_fast_campaign_decision_results(
        _canonical(document)
    )
    if len(results.decisions) != 1:
        raise ValueError(
            "shadow evidence Rust result must contain one decision"
        )
    return results.decisions[0]


def _execution_cost_bps(
    quote: FastPaperShadowQuoteEvidence,
    *,
    direction: str,
) -> float:
    if quote.state != _EXECUTABLE:
        raise ValueError(
            "execution cost requires an executable shadow quote"
        )
    reference = quote.reference_price_quote
    execution = quote.execution_price_quote
    assert reference is not None and execution is not None
    if direction == "BUY":
        value = max(0.0, execution / reference - 1.0) * 10_000.0
    elif direction == "SELL":
        value = max(0.0, 1.0 - execution / reference) * 10_000.0
    else:
        raise ValueError("unsupported shadow execution-cost direction")
    _require_non_negative_finite("execution_cost_bps", value)
    return value


def _optional_close(
    left: float | None,
    right: float | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(
        left,
        right,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} must be positive and finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")


def _require_finite_interval(
    name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
    minimum_open: bool = False,
    maximum_open: bool = False,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{name} must be finite")
    scalar = float(value)
    lower = scalar > minimum if minimum_open else scalar >= minimum
    upper = scalar < maximum if maximum_open else scalar <= maximum
    if not lower or not upper:
        raise ValueError(f"{name} is outside the permitted interval")


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be 40 lowercase hex characters")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
