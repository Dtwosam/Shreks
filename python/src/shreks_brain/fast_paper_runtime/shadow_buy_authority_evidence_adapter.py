from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path

from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicComparisonExecutionPolicy,
)
from shreks_brain.fast_deterministic_offline import (
    FastChampionEntryExecutionEvidence,
    build_fast_champion_entry_execution_evidence,
)
from shreks_brain.observer_campaign import (
    ObserverCampaignStore,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverRegimeReadPolicy,
)
from shreks_brain.observer_market import (
    ObserverMarketReadPolicy,
    ObserverMarketStore,
)
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.paper_validation import FastPaperCheckpointRecord
from shreks_brain.regime import RegimePolicy, assess_regime
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    feature_logical_fingerprint_sha256,
)
from shreks_brain.risk_control import load_operator_risk_control_state
from shreks_brain.safety import SafetyPolicy

from .models import FastPaperRuntimeManifest
from .persisted_quotes import (
    FastPaperShadowQuoteReadPolicy,
    resolve_fast_paper_shadow_cycle_input,
)
from .shadow import FastPaperShadowDecisionEvidence
from .shadow_buy_authority_producer import (
    produce_fast_paper_shadow_buy_authority_source_record,
)
from .shadow_buy_authority_source import FastPaperShadowBuyAuthoritySourceRecord
from .shadow_execution_input import FastPaperShadowExecutionPolicy
from .shadow_ledger import FastPaperShadowLedgerBinding
from .shadow_quote_usd_source import (
    read_fast_paper_shadow_quote_usd_source_record,
)
from .shadow_runtime_state import FastPaperShadowRuntimeState


FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION = (
    "fast-paper-shadow-buy-authority-evidence-adapter-v1"
)


def produce_fast_paper_shadow_buy_authority_from_persisted_evidence(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
    feature_record: FastTrainingFeatureRecord,
    quote_read_policy: FastPaperShadowQuoteReadPolicy,
    market_read_policy: ObserverMarketReadPolicy,
    regime_read_policy: ObserverRegimeReadPolicy,
    regime_policy: RegimePolicy,
    safety_policy: SafetyPolicy,
    safety_probe_identity: ObserverSafetyProbeIdentity,
    execution_economics_policy: FastDeterministicComparisonExecutionPolicy,
    *,
    quote_usd_source_directory: str | Path,
    operator_risk_control_path: str | Path,
    entry_authority_binary_path: str | Path,
    day_started_at_unix_ms: int,
    data_healthy: bool | None,
    execution_healthy: bool | None,
    global_risk_halt: bool,
) -> FastPaperShadowBuyAuthoritySourceRecord | None:
    _require_inputs(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
        feature_record,
        quote_read_policy,
        market_read_policy,
        regime_read_policy,
        regime_policy,
        safety_policy,
        safety_probe_identity,
        execution_economics_policy,
        day_started_at_unix_ms=day_started_at_unix_ms,
        data_healthy=data_healthy,
        execution_healthy=execution_healthy,
        global_risk_halt=global_risk_halt,
    )
    _require_policy_bindings(
        manifest,
        quote_read_policy,
        regime_read_policy,
        safety_probe_identity,
        execution_economics_policy,
        decision_evidence,
        feature_record,
    )

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature_record,
        decision_evidence.position,
        quote_read_policy,
        evaluated_at_unix_ms=decision_evidence.evaluated_at_unix_ms,
        max_exposure_fraction=decision_evidence.decision.target_exposure_fraction,
    )
    if cycle.entry_quote != decision_evidence.entry_quote:
        raise ValueError(
            "BUY authority persisted ENTRY quote drifted from sealed decision"
        )
    if cycle.exit_quote != decision_evidence.exit_quote:
        raise ValueError(
            "BUY authority persisted EXIT quote drifted from sealed decision"
        )
    if cycle.entry_quote.state != "EXECUTABLE":
        return None
    if cycle.exit_quote.state != "EXECUTABLE":
        return None
    base_quantity = cycle.entry_quote.quoted_base_quantity
    exit_capacity_base = cycle.exit_quote.available_base_quantity
    if base_quantity is None or exit_capacity_base is None:
        raise ValueError(
            "executable BUY authority quotes require exact quantities"
        )

    execution_evidence = build_fast_champion_entry_execution_evidence(
        champion_path=manifest.champion_path,
        record=feature_record,
        horizon_ms=execution_economics_policy.horizon_ms,
        cost_model=execution_economics_policy.cost_model,
        base_quantity=base_quantity,
        exit_capacity_base=exit_capacity_base,
        required_edge_bps=execution_economics_policy.required_edge_bps,
        risk_margin_bps=execution_economics_policy.risk_margin_bps,
        execution_policy_source_version=execution_economics_policy.version,
        exit_capacity_source_version=manifest.route_evidence_version,
    )
    if type(execution_evidence) is not FastChampionEntryExecutionEvidence:
        raise ValueError(
            "BUY authority execution evidence must be exact "
            "FastChampionEntryExecutionEvidence"
        )
    if (
        execution_evidence.champion_version != manifest.champion_version
        or execution_evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority execution evidence champion does not match runtime manifest"
        )

    evaluated_at = decision_evidence.evaluated_at_unix_ms
    market_store = ObserverMarketStore(manifest.observer_database_path)
    market_window = market_store.load_window(
        quote_read_policy.candidate_id,
        evaluated_at,
        market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    if (
        market_window.candidate.candidate_id != quote_read_policy.candidate_id
        or market_window.candidate.mint != feature_record.mint
    ):
        raise ValueError(
            "BUY authority market window candidate does not match learned decision"
        )

    campaign_store = ObserverCampaignStore(manifest.observer_database_path)
    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=quote_read_policy.candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=quote_read_policy.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature_record.mint,
        taker=quote_read_policy.taker,
        input_amount=quote_read_policy.entry_input_amount_raw,
        slippage_bps=quote_read_policy.slippage_bps,
    )
    raw_entry_quote = campaign_store.latest_paper_quote(
        entry_identity,
        evaluated_at,
    )
    if raw_entry_quote is None:
        raise ValueError(
            "BUY authority persisted ENTRY price-impact evidence is missing"
        )
    if raw_entry_quote.identity != entry_identity:
        raise ValueError(
            "BUY authority persisted ENTRY quote identity mismatch"
        )
    if (
        raw_entry_quote.quoted_at_unix_ms
        != decision_evidence.entry_quote.observed_at_unix_ms
    ):
        raise ValueError(
            "BUY authority persisted ENTRY quote timestamp drifted from sealed decision"
        )
    if not raw_entry_quote.route_available:
        return None

    quote_usd = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        decision_evidence,
        quote_usd_source_directory,
    )
    quote_usd_evidence = quote_usd.quote_usd_evidence

    regime_market = campaign_store.build_regime_market_window(
        evaluated_at,
        regime_read_policy,
        safety_policy,
        safety_probe_identity,
        global_risk_halt=global_risk_halt,
    )
    regime_assessment = assess_regime(
        regime_market,
        regime_policy,
        performance=None,
    )

    controls = load_operator_risk_control_state(
        Path(operator_risk_control_path).expanduser()
    )
    if controls.updated_at_unix_ms > evaluated_at:
        raise ValueError(
            "BUY authority operator control state is from after decision evaluation"
        )

    expected_price_impact_pct = _price_impact(
        raw_entry_quote.price_impact_pct
    )
    price_impact_notional_usd = (
        None
        if expected_price_impact_pct is None
        else _entry_notional_usd(
            quote_read_policy.entry_input_amount_raw,
            quote_decimals=manifest.quote_decimals,
            quote_to_usd_rate=quote_usd_evidence.quote_to_usd_rate,
        )
    )

    market_observed_at = min(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        quote_usd_evidence.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
    )
    source_observed_at = max(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        cycle.exit_quote.observed_at_unix_ms,
        quote_usd_evidence.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
        controls.updated_at_unix_ms,
    )
    if source_observed_at > evaluated_at:
        raise ValueError(
            "BUY authority persisted source observation is from the future"
        )

    risk_environment = FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=paper_checkpoint.state.ledger.starting_cash_usd,
        day_started_at_unix_ms=day_started_at_unix_ms,
        liquidity_usd=market_window.current.liquidity_usd,
        expected_price_impact_pct=expected_price_impact_pct,
        price_impact_notional_usd=price_impact_notional_usd,
        market_observed_at_unix_ms=market_observed_at,
        data_healthy=data_healthy,
        execution_healthy=execution_healthy,
        kill_switch_active=(
            global_risk_halt or controls.kill_switch_active
        ),
        active_intent_keys=frozenset(),
        operator_entry_halt_active=controls.halt_new_entries,
    )

    source_fingerprint = _source_fingerprint(
        manifest=manifest,
        decision_evidence=decision_evidence,
        feature_record=feature_record,
        quote_read_policy=quote_read_policy,
        market_window=market_window,
        raw_entry_quote=raw_entry_quote,
        quote_usd_record_fingerprint=quote_usd.record_fingerprint_sha256,
        regime_market=regime_market,
        regime_policy_version=regime_policy.version,
        regime_value=regime_assessment.regime.value,
        execution_evidence=execution_evidence,
        controls=controls,
        day_started_at_unix_ms=day_started_at_unix_ms,
        data_healthy=data_healthy,
        execution_healthy=execution_healthy,
        global_risk_halt=global_risk_halt,
    )

    return produce_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
        feature_record,
        execution_evidence.execution,
        risk_environment,
        regime_assessment.regime,
        entry_authority_binary_path=entry_authority_binary_path,
        source_observed_at_unix_ms=source_observed_at,
        source_version=(
            FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION
        ),
        source_fingerprint_sha256=source_fingerprint,
    )


def _require_inputs(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
    feature_record: FastTrainingFeatureRecord,
    quote_read_policy: FastPaperShadowQuoteReadPolicy,
    market_read_policy: ObserverMarketReadPolicy,
    regime_read_policy: ObserverRegimeReadPolicy,
    regime_policy: RegimePolicy,
    safety_policy: SafetyPolicy,
    safety_probe_identity: ObserverSafetyProbeIdentity,
    execution_economics_policy: FastDeterministicComparisonExecutionPolicy,
    *,
    day_started_at_unix_ms: int,
    data_healthy: bool | None,
    execution_healthy: bool | None,
    global_risk_halt: bool,
) -> None:
    exact = (
        ("manifest", manifest, FastPaperRuntimeManifest),
        ("binding", binding, FastPaperShadowLedgerBinding),
        ("execution_policy", execution_policy, FastPaperShadowExecutionPolicy),
        ("paper_checkpoint", paper_checkpoint, FastPaperCheckpointRecord),
        ("runtime_state", runtime_state, FastPaperShadowRuntimeState),
        ("decision_evidence", decision_evidence, FastPaperShadowDecisionEvidence),
        ("feature_record", feature_record, FastTrainingFeatureRecord),
        ("quote_read_policy", quote_read_policy, FastPaperShadowQuoteReadPolicy),
        ("market_read_policy", market_read_policy, ObserverMarketReadPolicy),
        ("regime_read_policy", regime_read_policy, ObserverRegimeReadPolicy),
        ("regime_policy", regime_policy, RegimePolicy),
        ("safety_policy", safety_policy, SafetyPolicy),
        (
            "safety_probe_identity",
            safety_probe_identity,
            ObserverSafetyProbeIdentity,
        ),
        (
            "execution_economics_policy",
            execution_economics_policy,
            FastDeterministicComparisonExecutionPolicy,
        ),
    )
    for name, value, expected in exact:
        if type(value) is not expected:
            raise ValueError(
                f"{name} must be exact {expected.__name__}"
            )
    _require_non_negative_int(
        "day_started_at_unix_ms",
        day_started_at_unix_ms,
    )
    _require_optional_bool("data_healthy", data_healthy)
    _require_optional_bool("execution_healthy", execution_healthy)
    if type(global_risk_halt) is not bool:
        raise ValueError("global_risk_halt must be bool")


def _require_policy_bindings(
    manifest: FastPaperRuntimeManifest,
    quote_read_policy: FastPaperShadowQuoteReadPolicy,
    regime_read_policy: ObserverRegimeReadPolicy,
    safety_probe_identity: ObserverSafetyProbeIdentity,
    execution_economics_policy: FastDeterministicComparisonExecutionPolicy,
    decision_evidence: FastPaperShadowDecisionEvidence,
    feature_record: FastTrainingFeatureRecord,
) -> None:
    if decision_evidence.decision.action != "BUY":
        raise ValueError("BUY authority adapter requires learned BUY decision")
    if decision_evidence.position.kind != "FLAT":
        raise ValueError("BUY authority adapter requires FLAT learned posture")
    if (
        decision_evidence.feature_record_fingerprint_sha256
        != feature_logical_fingerprint_sha256((feature_record,))
    ):
        raise ValueError(
            "BUY authority adapter feature fingerprint does not match sealed decision"
        )
    expected_event_id = (
        f"{feature_record.decision_signature}:{feature_record.decision_ordinal}"
    )
    if decision_evidence.source_event_id != expected_event_id:
        raise ValueError(
            "BUY authority adapter feature source identity does not match sealed decision"
        )
    if manifest.quote_provider != "jupiter":
        raise ValueError(
            "BUY authority aggregate regime reader requires jupiter quote provider"
        )
    if quote_read_policy.version != manifest.route_evidence_version:
        raise ValueError(
            "BUY authority quote-read policy version does not match runtime manifest"
        )
    expected_regime = (
        quote_read_policy.probe_policy_version,
        manifest.quote_mint,
        quote_read_policy.entry_input_amount_raw,
        quote_read_policy.taker,
        quote_read_policy.slippage_bps,
    )
    actual_regime = (
        regime_read_policy.entry_probe_policy_version,
        regime_read_policy.quote_asset_mint,
        regime_read_policy.entry_input_amount,
        regime_read_policy.taker,
        regime_read_policy.slippage_bps,
    )
    if actual_regime != expected_regime:
        raise ValueError(
            "BUY authority regime read policy does not match exact ENTRY quote identity"
        )
    if (
        safety_probe_identity.probe_policy_version
        != quote_read_policy.probe_policy_version
        or safety_probe_identity.output_mint != manifest.quote_mint
        or safety_probe_identity.taker != quote_read_policy.taker
        or safety_probe_identity.slippage_bps
        != quote_read_policy.slippage_bps
    ):
        raise ValueError(
            "BUY authority safety probe does not match quote-read identity"
        )
    horizon = decision_evidence.decision.selected_horizon_ms
    if horizon is None:
        raise ValueError(
            "BUY authority learned BUY requires selected horizon"
        )
    if execution_economics_policy.horizon_ms != horizon:
        raise ValueError(
            "BUY authority execution-economics horizon does not match learned BUY"
        )


def _price_impact(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            "BUY authority persisted ENTRY price impact is malformed"
        ) from exc
    converted = float(parsed)
    if not parsed.is_finite() or not math.isfinite(converted) or converted < 0.0:
        raise ValueError(
            "BUY authority persisted ENTRY price impact must be finite and non-negative"
        )
    return converted


def _entry_notional_usd(
    input_amount_raw: int,
    *,
    quote_decimals: int,
    quote_to_usd_rate: float,
) -> float:
    try:
        value = (
            Decimal(input_amount_raw)
            / (Decimal(10) ** quote_decimals)
            * Decimal(str(quote_to_usd_rate))
        )
        converted = float(value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(
            "BUY authority ENTRY price-impact notional could not be derived safely"
        ) from exc
    if not value.is_finite() or not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(
            "BUY authority ENTRY price-impact notional must be positive and finite"
        )
    return converted


def _source_fingerprint(
    *,
    manifest,
    decision_evidence,
    feature_record,
    quote_read_policy,
    market_window,
    raw_entry_quote,
    quote_usd_record_fingerprint,
    regime_market,
    regime_policy_version,
    regime_value,
    execution_evidence,
    controls,
    day_started_at_unix_ms,
    data_healthy,
    execution_healthy,
    global_risk_halt,
) -> str:
    material = {
        "adapter_version": (
            FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION
        ),
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "decision_evidence_fingerprint_sha256": (
            decision_evidence.evidence_fingerprint_sha256
        ),
        "feature_record_fingerprint_sha256": (
            feature_logical_fingerprint_sha256((feature_record,))
        ),
        "candidate_id": quote_read_policy.candidate_id,
        "entry_quote_observed_at_unix_ms": raw_entry_quote.quoted_at_unix_ms,
        "entry_price_impact_pct": raw_entry_quote.price_impact_pct,
        "exit_quote_observed_at_unix_ms": (
            decision_evidence.exit_quote.observed_at_unix_ms
        ),
        "market_row_id": market_window.current.row_id,
        "market_observed_at_unix_ms": (
            market_window.current.observed_at_unix_ms
        ),
        "market_liquidity_usd_hex": _float_hex(
            market_window.current.liquidity_usd
        ),
        "quote_usd_record_fingerprint_sha256": (
            quote_usd_record_fingerprint
        ),
        "regime_policy_version": regime_policy_version,
        "regime_value": regime_value,
        "regime_source_observed_at_unix_ms": (
            regime_market.source_observed_at_unix_ms
        ),
        "forecast_source_version": execution_evidence.forecast_source_version,
        "execution_policy_source_version": (
            execution_evidence.execution_policy_source_version
        ),
        "exit_capacity_source_version": (
            execution_evidence.exit_capacity_source_version
        ),
        "operator_control_revision": controls.revision,
        "operator_control_updated_at_unix_ms": controls.updated_at_unix_ms,
        "operator_halt_new_entries": controls.halt_new_entries,
        "operator_kill_switch_active": controls.kill_switch_active,
        "day_started_at_unix_ms": day_started_at_unix_ms,
        "data_healthy": data_healthy,
        "execution_healthy": execution_healthy,
        "global_risk_halt": global_risk_halt,
    }
    payload = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _float_hex(value: object) -> str | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(
            "BUY authority persisted market liquidity must be finite or None"
        )
    return float(value).hex()


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_bool(name: str, value: object) -> None:
    if value is not None and type(value) is not bool:
        raise ValueError(f"{name} must be bool or None")
