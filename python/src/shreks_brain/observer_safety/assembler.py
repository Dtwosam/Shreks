from __future__ import annotations

import math

from shreks_brain.observer_market.models import ObservedMarketWindow
from shreks_brain.safety import SafetyAssessment, SafetyInputs, SafetyPolicy, assess_safety

from .models import ObserverSafetyProbeIdentity
from .store import ObserverSafetyEvidenceStore


class ObserverSafetyAssemblyError(ValueError):
    """Raised when persisted safety evidence cannot be assembled without guessing."""


def build_safety_inputs(
    window: ObservedMarketWindow,
    evidence_store: ObserverSafetyEvidenceStore,
    probe_identity: ObserverSafetyProbeIdentity,
    global_risk_halt: bool,
) -> SafetyInputs:
    if type(window) is not ObservedMarketWindow:
        raise ValueError("window must be an ObservedMarketWindow")
    if type(evidence_store) is not ObserverSafetyEvidenceStore:
        raise ValueError("evidence_store must be an ObserverSafetyEvidenceStore")
    if type(probe_identity) is not ObserverSafetyProbeIdentity:
        raise ValueError("probe_identity must be an ObserverSafetyProbeIdentity")
    if type(global_risk_halt) is not bool:
        raise ValueError("global_risk_halt must be a boolean")

    candidate_id = window.candidate.candidate_id
    mint = window.candidate.mint
    as_of_unix_ms = window.as_of_unix_ms

    mint_evidence = evidence_store.latest_mint_state(
        candidate_id,
        mint,
        as_of_unix_ms,
    )
    holder_evidence = evidence_store.latest_holder_distribution(
        candidate_id,
        mint,
        as_of_unix_ms,
    )
    quote_evidence = evidence_store.latest_exit_quote(
        candidate_id,
        mint,
        probe_identity,
        as_of_unix_ms,
    )

    if mint_evidence is None:
        mint_authority_active = None
        freeze_authority_active = None
    else:
        mint_authority_active = mint_evidence.mint_authority is not None
        freeze_authority_active = mint_evidence.freeze_authority is not None

    top_holder_concentration_pct = (
        None
        if holder_evidence is None
        else holder_evidence.top_holder_concentration_pct
    )

    if quote_evidence is None:
        exit_quote_available = None
        exit_price_impact_pct = None
    elif not quote_evidence.route_available:
        exit_quote_available = False
        exit_price_impact_pct = None
    else:
        exit_quote_available = True
        exit_price_impact_pct = _parse_price_impact_pct(quote_evidence.price_impact_pct)

    consumed_timestamps = [window.current.observed_at_unix_ms]
    if mint_evidence is not None:
        consumed_timestamps.append(mint_evidence.observed_at_unix_ms)
    if holder_evidence is not None:
        consumed_timestamps.append(holder_evidence.observed_at_unix_ms)
    if quote_evidence is not None:
        consumed_timestamps.append(quote_evidence.quoted_at_unix_ms)

    return SafetyInputs(
        as_of_unix_ms=as_of_unix_ms,
        mint_authority_active=mint_authority_active,
        freeze_authority_active=freeze_authority_active,
        liquidity_usd=window.current.liquidity_usd,
        top_holder_concentration_pct=top_holder_concentration_pct,
        creator_concentration_pct=None,
        exit_quote_available=exit_quote_available,
        exit_price_impact_pct=exit_price_impact_pct,
        execution_trap_detected=False,
        critical_data_observed_at_unix_ms=min(consumed_timestamps),
        critical_data_contradictory=False,
        global_risk_halt=global_risk_halt,
    )


def assess_observer_safety(
    window: ObservedMarketWindow,
    evidence_store: ObserverSafetyEvidenceStore,
    probe_identity: ObserverSafetyProbeIdentity,
    policy: SafetyPolicy,
    *,
    global_risk_halt: bool,
) -> SafetyAssessment:
    if type(policy) is not SafetyPolicy:
        raise ValueError("policy must be a SafetyPolicy")
    inputs = build_safety_inputs(
        window,
        evidence_store,
        probe_identity,
        global_risk_halt,
    )
    return assess_safety(inputs, policy)


def _parse_price_impact_pct(raw: str | None) -> float | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or raw.strip() != raw:
        raise ObserverSafetyAssemblyError(
            "exit quote price impact must be clean numeric percentage text"
        )
    try:
        value = float(raw)
    except ValueError as error:
        raise ObserverSafetyAssemblyError(
            "exit quote price impact is not numeric percentage text"
        ) from error
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ObserverSafetyAssemblyError(
            "exit quote price impact must be finite and within [0, 100] percentage points"
        )
    return value
