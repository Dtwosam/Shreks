from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import os
from pathlib import Path

from shreks_brain.fast_campaign_paper import FastCampaignPaperQuoteEvidence
from shreks_brain.fast_deterministic_offline import (
    FastChampionEntryExecutionEvidence,
    FastOfflineExecutionCostModel,
    build_fast_champion_entry_execution_evidence,
)
from shreks_brain.observer_campaign import (
    ObserverCampaignStore,
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord


FAST_OBSERVER_DIRECTIONAL_PROBE_EVIDENCE_VERSION = (
    "fl9-observer-directional-probe-evidence-v1"
)


@dataclass(frozen=True, slots=True)
class FastObserverDirectionalProbeEvidence:
    version: str
    source_event_id: str
    observer_candidate_id: int
    evaluated_at_unix_ms: int
    token_decimals: int
    entry_evidence: ObserverPaperQuoteEvidence
    exit_evidence: ObserverPaperQuoteEvidence
    entry_quote: FastCampaignPaperQuoteEvidence
    exit_quote: FastCampaignPaperQuoteEvidence
    intended_base_quantity: float | None
    exit_capacity_base: float | None
    entry_input_notional_usd: float
    entry_price_impact_pct: float | None
    entry_quote_source_version: str
    exit_quote_source_version: str

    def __post_init__(self) -> None:
        if self.version != FAST_OBSERVER_DIRECTIONAL_PROBE_EVIDENCE_VERSION:
            raise ValueError("unsupported observer directional probe version")
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_positive_int("observer_candidate_id", self.observer_candidate_id)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        if (
            isinstance(self.token_decimals, bool)
            or not isinstance(self.token_decimals, int)
            or not 0 <= self.token_decimals <= 255
        ):
            raise ValueError("token_decimals must be within [0, 255]")
        if type(self.entry_evidence) is not ObserverPaperQuoteEvidence:
            raise ValueError(
                "entry_evidence must be exact ObserverPaperQuoteEvidence"
            )
        if type(self.exit_evidence) is not ObserverPaperQuoteEvidence:
            raise ValueError(
                "exit_evidence must be exact ObserverPaperQuoteEvidence"
            )
        if type(self.entry_quote) is not FastCampaignPaperQuoteEvidence:
            raise ValueError(
                "entry_quote must be exact FastCampaignPaperQuoteEvidence"
            )
        if type(self.exit_quote) is not FastCampaignPaperQuoteEvidence:
            raise ValueError(
                "exit_quote must be exact FastCampaignPaperQuoteEvidence"
            )
        if self.intended_base_quantity is not None:
            _require_positive_finite(
                "intended_base_quantity",
                self.intended_base_quantity,
            )
        if self.exit_capacity_base is not None:
            _require_positive_finite(
                "exit_capacity_base",
                self.exit_capacity_base,
            )
        _require_positive_finite(
            "entry_input_notional_usd",
            self.entry_input_notional_usd,
        )
        if self.entry_price_impact_pct is not None:
            _require_non_negative_finite(
                "entry_price_impact_pct",
                self.entry_price_impact_pct,
            )
        _require_non_empty_string(
            "entry_quote_source_version",
            self.entry_quote_source_version,
        )
        _require_non_empty_string(
            "exit_quote_source_version",
            self.exit_quote_source_version,
        )

        if self.entry_evidence.identity.purpose is not ObserverPaperQuotePurpose.ENTRY:
            raise ValueError("entry_evidence must have ENTRY purpose")
        if self.exit_evidence.identity.purpose is not ObserverPaperQuotePurpose.EXIT:
            raise ValueError("exit_evidence must have EXIT purpose")
        if (
            self.entry_evidence.identity.candidate_id
            != self.observer_candidate_id
            or self.exit_evidence.identity.candidate_id
            != self.observer_candidate_id
        ):
            raise ValueError("directional probe observer candidate mismatch")

        if self.entry_evidence.route_available:
            if self.intended_base_quantity is None:
                raise ValueError(
                    "executable ENTRY probe requires intended base quantity"
                )
        elif self.intended_base_quantity is not None:
            raise ValueError(
                "unavailable ENTRY probe cannot carry intended base quantity"
            )

        if self.exit_evidence.route_available:
            if self.exit_capacity_base is None:
                raise ValueError(
                    "executable EXIT probe requires exit capacity"
                )
        elif self.exit_capacity_base is not None:
            raise ValueError(
                "unavailable EXIT probe cannot carry exit capacity"
            )


def load_fast_observer_directional_probe(
    *,
    database_path: str | os.PathLike[str],
    record: FastTrainingFeatureRecord,
    observer_candidate_id: int,
    evaluated_at_unix_ms: int,
    entry_quote_identity: ObserverPaperQuoteIdentity,
    exit_quote_identity: ObserverPaperQuoteIdentity,
    quote_asset: ObserverPaperQuoteAsset,
) -> FastObserverDirectionalProbeEvidence:
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    _require_positive_int("observer_candidate_id", observer_candidate_id)
    _require_non_negative_int(
        "evaluated_at_unix_ms",
        evaluated_at_unix_ms,
    )
    if evaluated_at_unix_ms < record.decision_observed_at_unix_ms:
        raise ValueError(
            "observer probe evaluation cannot precede FL8.1 decision"
        )
    if type(entry_quote_identity) is not ObserverPaperQuoteIdentity:
        raise ValueError(
            "entry_quote_identity must be exact ObserverPaperQuoteIdentity"
        )
    if type(exit_quote_identity) is not ObserverPaperQuoteIdentity:
        raise ValueError(
            "exit_quote_identity must be exact ObserverPaperQuoteIdentity"
        )
    if type(quote_asset) is not ObserverPaperQuoteAsset:
        raise ValueError("quote_asset must be exact ObserverPaperQuoteAsset")

    _validate_market_attribution(
        record,
        observer_candidate_id=observer_candidate_id,
        entry_quote_identity=entry_quote_identity,
        exit_quote_identity=exit_quote_identity,
        quote_asset=quote_asset,
    )

    store = ObserverCampaignStore(database_path)
    token_decimals = store.latest_token_decimals(
        observer_candidate_id,
        record.mint,
        evaluated_at_unix_ms,
    )
    if token_decimals is None:
        raise ValueError("observer probe token decimals unavailable")

    entry_evidence = store.latest_paper_quote(
        entry_quote_identity,
        evaluated_at_unix_ms,
    )
    exit_evidence = store.latest_paper_quote(
        exit_quote_identity,
        evaluated_at_unix_ms,
    )
    if entry_evidence is None or exit_evidence is None:
        raise ValueError(
            "observer probe requires persisted ENTRY and EXIT quote evidence"
        )

    _validate_quote_chronology(
        record,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        evidence=entry_evidence,
        direction="ENTRY",
    )
    _validate_quote_chronology(
        record,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        evidence=exit_evidence,
        direction="EXIT",
    )

    entry_quote = _campaign_quote(
        record,
        entry_evidence,
        token_decimals=token_decimals,
        quote_asset=quote_asset,
    )
    exit_quote = _campaign_quote(
        record,
        exit_evidence,
        token_decimals=token_decimals,
        quote_asset=quote_asset,
    )

    intended_base_quantity = (
        _raw_quantity(
            entry_evidence.output_amount,
            token_decimals,
            "ENTRY token output",
        )
        if entry_evidence.route_available
        else None
    )
    exit_capacity_base = (
        _raw_quantity(
            exit_evidence.identity.input_amount,
            token_decimals,
            "EXIT token input",
        )
        if exit_evidence.route_available
        else None
    )
    entry_input_notional_usd = (
        _raw_quantity(
            entry_evidence.identity.input_amount,
            quote_asset.decimals,
            "ENTRY quote input",
        )
        * quote_asset.usd_per_token
    )
    _require_positive_finite(
        "entry_input_notional_usd",
        entry_input_notional_usd,
    )
    entry_price_impact_pct = _price_impact(entry_evidence.price_impact_pct)

    return FastObserverDirectionalProbeEvidence(
        version=FAST_OBSERVER_DIRECTIONAL_PROBE_EVIDENCE_VERSION,
        source_event_id=(
            f"{record.decision_signature}:{record.decision_ordinal}"
        ),
        observer_candidate_id=observer_candidate_id,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        token_decimals=token_decimals,
        entry_evidence=entry_evidence,
        exit_evidence=exit_evidence,
        entry_quote=entry_quote,
        exit_quote=exit_quote,
        intended_base_quantity=intended_base_quantity,
        exit_capacity_base=exit_capacity_base,
        entry_input_notional_usd=entry_input_notional_usd,
        entry_price_impact_pct=entry_price_impact_pct,
        entry_quote_source_version=_quote_source_version(entry_evidence),
        exit_quote_source_version=_quote_source_version(exit_evidence),
    )


def build_fast_observer_champion_entry_execution(
    *,
    probe: FastObserverDirectionalProbeEvidence,
    champion_path: str | Path,
    record: FastTrainingFeatureRecord,
    horizon_ms: int,
    cost_model: FastOfflineExecutionCostModel,
    required_edge_bps: int,
    risk_margin_bps: int,
    execution_policy_source_version: str,
) -> FastChampionEntryExecutionEvidence | None:
    if type(probe) is not FastObserverDirectionalProbeEvidence:
        raise ValueError(
            "probe must be exact FastObserverDirectionalProbeEvidence"
        )
    if type(record) is not FastTrainingFeatureRecord:
        raise ValueError("record must be exact FastTrainingFeatureRecord")
    expected_source_event_id = (
        f"{record.decision_signature}:{record.decision_ordinal}"
    )
    if probe.source_event_id != expected_source_event_id:
        raise ValueError(
            "observer probe source identity does not match FL8.1 record"
        )
    if probe.entry_quote.mint != record.mint or probe.exit_quote.mint != record.mint:
        raise ValueError("observer probe mint does not match FL8.1 record")
    if (
        probe.entry_quote.quote_mint != record.quote_mint
        or probe.exit_quote.quote_mint != record.quote_mint
    ):
        raise ValueError(
            "observer probe quote mint does not match FL8.1 record"
        )

    if (
        probe.intended_base_quantity is None
        or probe.exit_capacity_base is None
    ):
        return None

    return build_fast_champion_entry_execution_evidence(
        champion_path=champion_path,
        record=record,
        horizon_ms=horizon_ms,
        cost_model=cost_model,
        base_quantity=probe.intended_base_quantity,
        exit_capacity_base=probe.exit_capacity_base,
        required_edge_bps=required_edge_bps,
        risk_margin_bps=risk_margin_bps,
        execution_policy_source_version=execution_policy_source_version,
        exit_capacity_source_version=probe.exit_quote_source_version,
    )


def _validate_market_attribution(
    record: FastTrainingFeatureRecord,
    *,
    observer_candidate_id: int,
    entry_quote_identity: ObserverPaperQuoteIdentity,
    exit_quote_identity: ObserverPaperQuoteIdentity,
    quote_asset: ObserverPaperQuoteAsset,
) -> None:
    if entry_quote_identity.candidate_id != observer_candidate_id:
        raise ValueError("ENTRY probe observer candidate identity mismatch")
    if exit_quote_identity.candidate_id != observer_candidate_id:
        raise ValueError("EXIT probe observer candidate identity mismatch")
    if entry_quote_identity.purpose is not ObserverPaperQuotePurpose.ENTRY:
        raise ValueError("entry_quote_identity must have ENTRY purpose")
    if exit_quote_identity.purpose is not ObserverPaperQuotePurpose.EXIT:
        raise ValueError("exit_quote_identity must have EXIT purpose")
    if quote_asset.mint != record.quote_mint:
        raise ValueError("observer probe quote asset does not match FL8.1 quote mint")
    if (
        entry_quote_identity.input_mint != record.quote_mint
        or entry_quote_identity.output_mint != record.mint
    ):
        raise ValueError("observer ENTRY probe market attribution mismatch")
    if (
        exit_quote_identity.input_mint != record.mint
        or exit_quote_identity.output_mint != record.quote_mint
    ):
        raise ValueError("observer EXIT probe market attribution mismatch")


def _validate_quote_chronology(
    record: FastTrainingFeatureRecord,
    *,
    evaluated_at_unix_ms: int,
    evidence: ObserverPaperQuoteEvidence,
    direction: str,
) -> None:
    if not (
        record.decision_observed_at_unix_ms
        <= evidence.quoted_at_unix_ms
        <= evaluated_at_unix_ms
    ):
        raise ValueError(
            f"observer {direction} probe is outside decision-safe chronology"
        )


def _campaign_quote(
    record: FastTrainingFeatureRecord,
    evidence: ObserverPaperQuoteEvidence,
    *,
    token_decimals: int,
    quote_asset: ObserverPaperQuoteAsset,
) -> FastCampaignPaperQuoteEvidence:
    if evidence.identity.provider != "jupiter":
        raise ValueError("observer PAPER quote provider must be jupiter")
    if not evidence.route_available:
        return FastCampaignPaperQuoteEvidence(
            provider=evidence.identity.provider,
            mint=record.mint,
            quote_mint=record.quote_mint,
            observed_at_unix_ms=evidence.quoted_at_unix_ms,
            state=PaperQuoteState.UNAVAILABLE,
            reference_price_quote=None,
            execution_price_quote=None,
            quoted_base_quantity=None,
            available_base_quantity=None,
            quote_to_usd_rate=quote_asset.usd_per_token,
        )

    if evidence.identity.purpose is ObserverPaperQuotePurpose.ENTRY:
        quote_quantity = _raw_quantity(
            evidence.identity.input_amount,
            quote_asset.decimals,
            "ENTRY quote input",
        )
        base_quantity = _raw_quantity(
            evidence.output_amount,
            token_decimals,
            "ENTRY token output",
        )
    elif evidence.identity.purpose is ObserverPaperQuotePurpose.EXIT:
        base_quantity = _raw_quantity(
            evidence.identity.input_amount,
            token_decimals,
            "EXIT token input",
        )
        quote_quantity = _raw_quantity(
            evidence.output_amount,
            quote_asset.decimals,
            "EXIT quote output",
        )
    else:
        raise ValueError("unsupported observer probe quote purpose")

    _require_positive_finite("base_quantity", base_quantity)
    _require_positive_finite("quote_quantity", quote_quantity)
    execution_price = quote_quantity / base_quantity
    _require_positive_finite("execution_price", execution_price)

    return FastCampaignPaperQuoteEvidence(
        provider=evidence.identity.provider,
        mint=record.mint,
        quote_mint=record.quote_mint,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_quote=record.decision_executable_entry_price_quote,
        execution_price_quote=execution_price,
        quoted_base_quantity=base_quantity,
        available_base_quantity=base_quantity,
        quote_to_usd_rate=quote_asset.usd_per_token,
    )


def _quote_source_version(evidence: ObserverPaperQuoteEvidence) -> str:
    identity = evidence.identity
    return (
        f"observer:{identity.provider}:"
        f"{identity.probe_policy_version}:{identity.purpose.value}"
    )


def _price_impact(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(Decimal(value))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError("observer ENTRY price impact is malformed") from exc
    _require_non_negative_finite("entry_price_impact_pct", parsed)
    return parsed


def _raw_quantity(raw_amount: int, decimals: int, name: str) -> float:
    if (
        isinstance(raw_amount, bool)
        or not isinstance(raw_amount, int)
        or raw_amount < 0
    ):
        raise ValueError(f"{name} raw amount is invalid")
    if (
        isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or not 0 <= decimals <= 255
    ):
        raise ValueError(f"{name} decimals are invalid")
    try:
        value = Decimal(raw_amount) / (Decimal(10) ** decimals)
        converted = float(value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be converted safely") from exc
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return converted


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


def _require_non_negative_finite(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
