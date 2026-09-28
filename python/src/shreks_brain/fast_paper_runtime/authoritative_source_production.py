from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from typing import Callable

from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignRiskEnvironment,
)
from shreks_brain.fast_deterministic_campaign.risk_context import (
    build_fast_deterministic_campaign_risk_context,
)
from shreks_brain.fast_deterministic_offline import (
    FastChampionEntryExecutionEvidence,
    build_fast_champion_entry_execution_evidence,
)
from shreks_brain.fast_deterministic_offline.entry_authority import (
    derive_fast_deterministic_entry_authority_offline,
)
from shreks_brain.observer_campaign import (
    ObserverCampaignStore,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.observer_market import ObserverMarketStore
from shreks_brain.regime import assess_regime
from shreks_brain.risk_control import load_operator_risk_control_state

from .authoritative_file_authority import (
    build_fast_paper_authoritative_buy_authority_source_record,
    build_fast_paper_authoritative_pending_buy_retry_source_record,
    build_fast_paper_authoritative_reduction_source_record,
    read_fast_paper_authoritative_buy_authority_source_record,
    read_fast_paper_authoritative_pending_buy_retry_source_record,
    read_fast_paper_authoritative_reduction_source_record,
    write_fast_paper_authoritative_buy_authority_source_record,
    write_fast_paper_authoritative_pending_buy_retry_source_record,
    write_fast_paper_authoritative_reduction_source_record,
)
from .authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionBootstrap,
    fast_paper_authoritative_decision_position,
)
from .feed import fetch_fast_paper_runtime_feature_batch
from .persisted_quotes import (
    FastPaperShadowQuoteReadPolicy,
    _open_query_only_database,
    _require_candidate_mint,
    _resolve_base_decimals,
    _resolve_quote,
    _validate_schema,
    resolve_fast_paper_shadow_cycle_input,
)
from .shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .shadow_buy_authority_evidence_adapter import (
    FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION,
    _entry_notional_usd,
    _price_impact,
    _require_policy_bindings,
    _source_fingerprint,
)
from .shadow_buy_authority_producer import (
    _require_external_risk_facts,
    _require_feature_decision_binding,
)
from .shadow_buy_authority_writer import _execution_economics_by_horizon
from .shadow_buy_writer_policy import FastPaperShadowBuyWriterPolicy
from .shadow_executor import FastPaperShadowPendingBuyRetryInput
from .shadow_open_quote_writer import (
    _persisted_exit_input_amounts,
    _require_replayed_raw_authority,
    _select_reduction_reads,
)
from .shadow_quote_usd_source import (
    build_fast_paper_shadow_quote_usd_source_record,
    read_fast_paper_shadow_quote_usd_source_record,
    write_fast_paper_shadow_quote_usd_source_record,
)
from .shadow_execution_input import FastPaperShadowQuoteUsdEvidence
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    _resolve_candidate_id,
)


FAST_PAPER_AUTHORITATIVE_SOURCE_PRODUCTION_VERSION = (
    "fast-paper-authoritative-source-production-v1"
)
_QUOTE_USD_SOURCE_VERSION = (
    "fast-paper-authoritative-quote-usd-persisted-market-v1"
)


def run_fast_paper_authoritative_source_production_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    buy_writer_policy: FastPaperShadowBuyWriterPolicy,
    *,
    decision_evidence_directory: str | Path,
    buy_authority_source_directory: str | Path,
    quote_usd_source_directory: str | Path,
    reduction_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    clock_unix_ms: Callable[[], int] | None = None,
) -> int:
    if type(decision_bootstrap) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if (
        type(execution_bootstrap)
        is not FastPaperAuthoritativeServiceExecutionBootstrap
    ):
        raise ValueError(
            "execution_bootstrap must be exact "
            "FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    if type(buy_writer_policy) is not FastPaperShadowBuyWriterPolicy:
        raise ValueError(
            "buy_writer_policy must be exact FastPaperShadowBuyWriterPolicy"
        )
    manifest = decision_bootstrap.manifest
    _require_pair(manifest, execution_bootstrap)
    decision_root = _require_directory(
        decision_evidence_directory,
        "authoritative decision evidence",
    )
    buy_root = _require_directory(
        buy_authority_source_directory,
        "authoritative BUY authority source",
    )
    quote_root = _require_directory(
        quote_usd_source_directory,
        "authoritative quote/USD source",
    )
    reduction_root = _require_directory(
        reduction_source_directory,
        "authoritative reduction source",
    )
    retry_root = _require_directory(
        pending_buy_retry_source_directory,
        "authoritative pending BUY retry source",
    )
    now = _clock_value(
        _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    )

    written = 0
    if execution_bootstrap.checkpoint.state.pending_buy is not None:
        evidence = _processed_decision_evidence(
            manifest,
            execution_bootstrap,
            decision_root,
        )
        written += _write_pending_buy_retry(
            decision_bootstrap,
            execution_bootstrap,
            buy_writer_policy,
            evidence,
            retry_root,
            evaluated_at_unix_ms=now,
        )
        return written

    written += _write_open_reduction_source(
        decision_bootstrap,
        execution_bootstrap,
        reduction_root,
        evaluated_at_unix_ms=now,
    )

    evidence = _unexecuted_decision(
        manifest,
        decision_bootstrap,
        execution_bootstrap,
        decision_root,
    )
    if evidence is None:
        return written

    written += _write_quote_usd_source(
        decision_bootstrap,
        buy_writer_policy,
        evidence,
        quote_root,
    )
    if evidence.decision.action == "BUY":
        written += _write_buy_authority_source(
            decision_bootstrap,
            execution_bootstrap,
            buy_writer_policy,
            evidence,
            buy_root,
            quote_root,
        )
    return written


def _write_quote_usd_source(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
    destination: Path,
) -> int:
    manifest = decision_bootstrap.manifest
    path = destination / f"{evidence.evidence_fingerprint_sha256}.json"
    if path.is_symlink():
        raise ValueError(
            "authoritative quote/USD source path must not be a symlink"
        )
    if path.exists():
        restored = read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            destination,
        )
        _require_quote_usd_record_matches_persisted_market(
            decision_bootstrap,
            policy,
            evidence,
            restored.quote_usd_evidence,
        )
        return 0

    usd = _quote_usd_for_decision(
        decision_bootstrap,
        policy,
        evidence,
    )
    record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        usd,
    )
    try:
        write_fast_paper_shadow_quote_usd_source_record(
            record,
            destination,
        )
    except FileExistsError:
        restored = read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            destination,
        )
        if restored != record:
            raise ValueError(
                "authoritative quote/USD writer collision read-back mismatch"
            )
        return 0
    return 1


def _quote_usd_for_decision(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
) -> FastPaperShadowQuoteUsdEvidence:
    feature = evidence.feature_record
    service = decision_bootstrap.policy
    candidate_id = _resolve_candidate_id(
        decision_bootstrap.manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=decision_bootstrap.manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    return _quote_usd_from_market(
        decision_bootstrap.manifest,
        policy,
        candidate_id=candidate_id,
        base_mint=feature.mint,
        as_of_unix_ms=evidence.evaluated_at_unix_ms,
    )


def _quote_usd_from_market(
    manifest,
    policy: FastPaperShadowBuyWriterPolicy,
    *,
    candidate_id: int,
    base_mint: str,
    as_of_unix_ms: int,
) -> FastPaperShadowQuoteUsdEvidence:
    store = ObserverMarketStore(manifest.observer_database_path)
    window = store.load_window(
        candidate_id,
        as_of_unix_ms,
        policy.market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    current = window.current
    evidence = store.quote_asset_usd_evidence(
        candidate_id,
        as_of_unix_ms,
        source=current.source,
        venue=current.venue,
        base_mint=base_mint,
        quote_mint=manifest.quote_mint,
        max_age_ms=policy.market_read_policy.max_current_age_ms,
        expected_market_row_id=current.row_id,
    )
    material = {
        "version": _QUOTE_USD_SOURCE_VERSION,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "market_row_id": evidence.market_row_id,
        "candidate_id": evidence.candidate_id,
        "observed_at_unix_ms": evidence.observed_at_unix_ms,
        "source": evidence.source,
        "venue": evidence.venue,
        "pair_address": evidence.pair_address,
        "base_mint": evidence.base_mint,
        "quote_mint": evidence.quote_mint,
        "base_price_quote": evidence.base_price_quote,
        "base_price_usd_hex": float(evidence.base_price_usd).hex(),
        "quote_to_usd_rate_hex": float(
            evidence.quote_asset_usd_per_token
        ).hex(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return FastPaperShadowQuoteUsdEvidence(
        quote_mint=manifest.quote_mint,
        observed_at_unix_ms=evidence.observed_at_unix_ms,
        quote_to_usd_rate=evidence.quote_asset_usd_per_token,
        source_version=_QUOTE_USD_SOURCE_VERSION,
        source_fingerprint_sha256=fingerprint,
    )


def _require_quote_usd_record_matches_persisted_market(
    decision_bootstrap,
    policy,
    evidence,
    restored,
) -> None:
    expected = _quote_usd_for_decision(
        decision_bootstrap,
        policy,
        evidence,
    )
    if restored != expected:
        raise ValueError(
            "authoritative quote/USD source drifted from exact persisted market evidence"
        )


def _write_buy_authority_source(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
    destination: Path,
    quote_usd_directory: Path,
) -> int:
    manifest = decision_bootstrap.manifest
    path = destination / f"{evidence.evidence_fingerprint_sha256}.json"
    if path.is_symlink():
        raise ValueError(
            "authoritative BUY authority source path must not be a symlink"
        )
    if path.exists():
        read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            destination,
        )
        return 0

    feature = evidence.feature_record
    service = decision_bootstrap.policy
    economics = _execution_economics_by_horizon(
        manifest,
        policy.execution_economics_policies,
    )
    selected_horizon = evidence.decision.selected_horizon_ms
    if selected_horizon is None:
        raise ValueError(
            "authoritative learned BUY requires selected horizon"
        )
    try:
        economics_policy = economics[selected_horizon]
    except KeyError as exc:
        raise ValueError(
            "authoritative learned BUY horizon lacks exact economics policy"
        ) from exc

    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    quote_read_policy = FastPaperShadowQuoteReadPolicy(
        version=service.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        exit_input_amount_raw=service.exit_input_amount_raw,
        max_quote_age_ms=service.max_quote_age_ms,
        reduction_reads=(),
    )
    _require_policy_bindings(
        manifest,
        quote_read_policy,
        policy.regime_read_policy,
        policy.safety_probe_identity,
        economics_policy,
        evidence,
        feature,
    )
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        evidence.position,
        quote_read_policy,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_exposure_fraction=evidence.decision.target_exposure_fraction,
    )
    if cycle.entry_quote != evidence.entry_quote:
        raise ValueError(
            "authoritative BUY persisted ENTRY quote drifted from sealed decision"
        )
    if cycle.exit_quote != evidence.exit_quote:
        raise ValueError(
            "authoritative BUY persisted EXIT quote drifted from sealed decision"
        )
    if cycle.entry_quote.state != "EXECUTABLE":
        return 0
    if cycle.exit_quote.state != "EXECUTABLE":
        return 0
    base_quantity = cycle.entry_quote.quoted_base_quantity
    exit_capacity_base = cycle.exit_quote.available_base_quantity
    if base_quantity is None or exit_capacity_base is None:
        raise ValueError(
            "authoritative BUY executable quotes require exact quantities"
        )

    execution_evidence = build_fast_champion_entry_execution_evidence(
        champion_path=manifest.champion_path,
        record=feature,
        horizon_ms=economics_policy.horizon_ms,
        cost_model=economics_policy.cost_model,
        base_quantity=base_quantity,
        exit_capacity_base=exit_capacity_base,
        required_edge_bps=economics_policy.required_edge_bps,
        risk_margin_bps=economics_policy.risk_margin_bps,
        execution_policy_source_version=economics_policy.version,
        exit_capacity_source_version=manifest.route_evidence_version,
    )
    if type(execution_evidence) is not FastChampionEntryExecutionEvidence:
        raise ValueError(
            "authoritative BUY execution evidence is incompatible"
        )
    if (
        execution_evidence.champion_version != manifest.champion_version
        or execution_evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative BUY execution evidence champion drift"
        )

    evaluated_at = evidence.evaluated_at_unix_ms
    market_store = ObserverMarketStore(manifest.observer_database_path)
    market_window = market_store.load_window(
        candidate_id,
        evaluated_at,
        policy.market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    campaign_store = ObserverCampaignStore(
        manifest.observer_database_path
    )
    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature.mint,
        taker=service.taker,
        input_amount=service.entry_input_amount_raw,
        slippage_bps=service.slippage_bps,
    )
    raw_entry_quote = campaign_store.latest_paper_quote(
        entry_identity,
        evaluated_at,
    )
    if raw_entry_quote is None:
        raise ValueError(
            "authoritative BUY persisted ENTRY price-impact evidence is missing"
        )
    if (
        raw_entry_quote.identity != entry_identity
        or raw_entry_quote.quoted_at_unix_ms
        != evidence.entry_quote.observed_at_unix_ms
    ):
        raise ValueError(
            "authoritative BUY persisted ENTRY quote identity drift"
        )
    if not raw_entry_quote.route_available:
        return 0

    quote_usd = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        quote_usd_directory,
    )
    usd = quote_usd.quote_usd_evidence
    regime_market = campaign_store.build_regime_market_window(
        evaluated_at,
        policy.regime_read_policy,
        policy.safety_policy,
        policy.safety_probe_identity,
        global_risk_halt=policy.global_risk_halt,
    )
    regime_assessment = assess_regime(
        regime_market,
        policy.regime_policy,
        performance=None,
    )
    controls = load_operator_risk_control_state(
        policy.operator_risk_control_path
    )
    if controls.updated_at_unix_ms > evaluated_at:
        raise ValueError(
            "authoritative BUY operator controls are from after evaluation"
        )
    expected_price_impact_pct = _price_impact(
        raw_entry_quote.price_impact_pct
    )
    price_impact_notional_usd = (
        None
        if expected_price_impact_pct is None
        else _entry_notional_usd(
            service.entry_input_amount_raw,
            quote_decimals=manifest.quote_decimals,
            quote_to_usd_rate=usd.quote_to_usd_rate,
        )
    )
    market_observed_at = min(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        usd.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
    )
    source_observed_at = max(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        cycle.exit_quote.observed_at_unix_ms,
        usd.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
        controls.updated_at_unix_ms,
    )
    if source_observed_at > evaluated_at:
        raise ValueError(
            "authoritative BUY persisted source observation is from the future"
        )
    risk_environment = FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=(
            execution_bootstrap.checkpoint.state.ledger.starting_cash_usd
        ),
        day_started_at_unix_ms=policy.day_started_at_unix_ms,
        liquidity_usd=market_window.current.liquidity_usd,
        expected_price_impact_pct=expected_price_impact_pct,
        price_impact_notional_usd=price_impact_notional_usd,
        market_observed_at_unix_ms=market_observed_at,
        data_healthy=policy.data_healthy,
        execution_healthy=policy.execution_healthy,
        kill_switch_active=(
            policy.global_risk_halt or controls.kill_switch_active
        ),
        active_intent_keys=frozenset(),
        operator_entry_halt_active=controls.halt_new_entries,
    )
    _require_feature_decision_binding(evidence, feature)
    _require_external_risk_facts(
        execution_bootstrap.checkpoint,
        evidence,
        risk_environment,
        source_observed_at_unix_ms=source_observed_at,
    )
    entry_authority = derive_fast_deterministic_entry_authority_offline(
        binary_path=policy.entry_authority_binary_path,
        record=feature,
        execution=execution_evidence.execution,
    )
    if entry_authority is None:
        return 0
    risk_context = build_fast_deterministic_campaign_risk_context(
        execution_bootstrap.checkpoint.state.ledger,
        risk_environment,
        as_of_unix_ms=evaluated_at,
    )
    source_fingerprint = _source_fingerprint(
        manifest=manifest,
        decision_evidence=evidence,
        feature_record=feature,
        quote_read_policy=quote_read_policy,
        market_window=market_window,
        raw_entry_quote=raw_entry_quote,
        quote_usd_record_fingerprint=(
            quote_usd.record_fingerprint_sha256
        ),
        regime_market=regime_market,
        regime_policy_version=policy.regime_policy.version,
        regime_value=regime_assessment.regime.value,
        execution_evidence=execution_evidence,
        controls=controls,
        day_started_at_unix_ms=policy.day_started_at_unix_ms,
        data_healthy=policy.data_healthy,
        execution_healthy=policy.execution_healthy,
        global_risk_halt=policy.global_risk_halt,
    )
    record = build_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        execution_bootstrap,
        evidence,
        entry_authority,
        risk_context,
        regime_assessment.regime,
        risk_day_started_at_unix_ms=policy.day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at,
        source_version=(
            FAST_PAPER_SHADOW_BUY_AUTHORITY_EVIDENCE_ADAPTER_VERSION
        ),
        source_fingerprint_sha256=source_fingerprint,
    )
    try:
        write_fast_paper_authoritative_buy_authority_source_record(
            record,
            destination,
        )
    except FileExistsError:
        restored = read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            destination,
        )
        if restored != record:
            raise ValueError(
                "authoritative BUY writer collision read-back mismatch"
            )
        return 0
    return 1


def _write_open_reduction_source(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    destination: Path,
    *,
    evaluated_at_unix_ms: int,
) -> int:
    manifest = decision_bootstrap.manifest
    if not execution_bootstrap.runtime_state.market_positions:
        return 0
    preview = fetch_fast_paper_runtime_feature_batch(
        manifest,
        decision_bootstrap.state,
        maximum_decisions=1,
    )
    if not preview.records:
        return 0
    if len(preview.records) != 1:
        raise ValueError(
            "authoritative OPEN quote preview must contain at most one row"
        )
    feature = preview.records[0]
    evaluated_at = max(
        evaluated_at_unix_ms,
        feature.decision_observed_at_unix_ms,
    )
    market_key = f"{feature.venue}:{feature.mint}:{feature.quote_mint}"
    position = fast_paper_authoritative_decision_position(
        execution_bootstrap.runtime_state,
        market_key,
    )
    if position.kind == "FLAT":
        return 0
    mapping = _market_mapping(execution_bootstrap, market_key)
    if feature.mint != mapping.mint:
        raise ValueError(
            "authoritative OPEN preview mint does not match durable mapping"
        )

    service = decision_bootstrap.policy
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evaluated_at,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    minimum_observed_at = max(
        feature.decision_observed_at_unix_ms,
        evaluated_at - service.max_quote_age_ms,
    )
    persisted_inputs = _persisted_exit_input_amounts(
        manifest.observer_database_path,
        candidate_id=candidate_id,
        mint=feature.mint,
        quote_mint=manifest.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        minimum_observed_at_unix_ms=minimum_observed_at,
        evaluated_at_unix_ms=evaluated_at,
    )
    if mapping.current_base_quantity_raw not in persisted_inputs:
        return 0
    reduction_reads = _select_reduction_reads(
        manifest.action_policy.reduce_target_exposure_candidates,
        persisted_inputs,
        current_base_quantity_raw=mapping.current_base_quantity_raw,
        current_exposure_fraction=mapping.current_exposure_fraction,
    )
    if reduction_reads is None:
        return 0
    quote_policy = FastPaperShadowQuoteReadPolicy(
        version=service.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        exit_input_amount_raw=mapping.current_base_quantity_raw,
        max_quote_age_ms=service.max_quote_age_ms,
        reduction_reads=reduction_reads,
    )
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        position,
        quote_policy,
        evaluated_at_unix_ms=evaluated_at,
        max_exposure_fraction=service.max_exposure_fraction,
        force_sell=False,
    )
    _require_replayed_raw_authority(
        cycle,
        full_exit_input_amount_raw=mapping.current_base_quantity_raw,
        reduction_reads=reduction_reads,
    )
    record = build_fast_paper_authoritative_reduction_source_record(
        manifest,
        execution_bootstrap,
        market_key,
        reduction_reads,
    )
    try:
        write_fast_paper_authoritative_reduction_source_record(
            record,
            destination,
        )
    except FileExistsError:
        restored = read_fast_paper_authoritative_reduction_source_record(
            manifest,
            execution_bootstrap,
            market_key,
            destination,
        )
        if restored != record:
            raise ValueError(
                "authoritative OPEN writer collision read-back mismatch"
            )
        return 0
    return 1


def _write_pending_buy_retry(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
    destination: Path,
    *,
    evaluated_at_unix_ms: int,
) -> int:
    manifest = decision_bootstrap.manifest
    state = execution_bootstrap.runtime_state
    pending = state.pending_buy
    approval = execution_bootstrap.checkpoint.state.pending_buy
    if pending is None or approval is None:
        raise ValueError(
            "authoritative retry writer requires paired pending BUY state"
        )
    filename = _pending_retry_filename(
        state.state_fingerprint_sha256,
        evidence.source_event_id,
    )
    path = destination / filename
    if path.is_symlink():
        raise ValueError(
            "authoritative pending BUY retry source path must not be a symlink"
        )
    if path.exists():
        read_fast_paper_authoritative_pending_buy_retry_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            destination,
        )
        return 0

    feature = evidence.feature_record
    service = decision_bootstrap.policy
    evaluated_at = max(
        evaluated_at_unix_ms,
        execution_bootstrap.checkpoint.state.as_of_unix_ms,
        feature.decision_observed_at_unix_ms,
    )
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evaluated_at,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    quote_policy = FastPaperShadowQuoteReadPolicy(
        version=service.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        exit_input_amount_raw=service.exit_input_amount_raw,
        max_quote_age_ms=service.max_quote_age_ms,
        reduction_reads=(),
    )
    connection = _open_query_only_database(
        manifest.observer_database_path
    )
    try:
        _validate_schema(connection)
        _require_candidate_mint(
            connection,
            candidate_id=candidate_id,
            expected_mint=feature.mint,
        )
        base_decimals = _resolve_base_decimals(
            connection,
            candidate_id=candidate_id,
            evaluated_at_unix_ms=evaluated_at,
        )
        quote = _resolve_quote(
            connection,
            manifest=manifest,
            record=feature,
            read_policy=quote_policy,
            purpose="entry",
            input_mint=manifest.quote_mint,
            output_mint=feature.mint,
            input_amount_raw=service.entry_input_amount_raw,
            base_decimals=base_decimals,
            evaluated_at_unix_ms=evaluated_at,
        )
    finally:
        connection.close()
    if quote.observed_at_unix_ms < (
        execution_bootstrap.checkpoint.state.as_of_unix_ms
    ):
        return 0

    usd = _quote_usd_from_market(
        manifest,
        policy,
        candidate_id=candidate_id,
        base_mint=feature.mint,
        as_of_unix_ms=evaluated_at,
    )
    if usd.observed_at_unix_ms < (
        execution_bootstrap.checkpoint.state.as_of_unix_ms
    ):
        return 0

    campaign_store = ObserverCampaignStore(
        manifest.observer_database_path
    )
    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature.mint,
        taker=service.taker,
        input_amount=service.entry_input_amount_raw,
        slippage_bps=service.slippage_bps,
    )
    raw_entry_quote = campaign_store.latest_paper_quote(
        entry_identity,
        evaluated_at,
    )
    if raw_entry_quote is None or not raw_entry_quote.route_available:
        return 0
    if raw_entry_quote.quoted_at_unix_ms != quote.observed_at_unix_ms:
        raise ValueError(
            "authoritative pending BUY retry quote identity drift"
        )
    market_store = ObserverMarketStore(manifest.observer_database_path)
    market_window = market_store.load_window(
        candidate_id,
        evaluated_at,
        policy.market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    controls = load_operator_risk_control_state(
        policy.operator_risk_control_path
    )
    if controls.updated_at_unix_ms > evaluated_at:
        raise ValueError(
            "authoritative pending BUY controls are from the future"
        )
    expected_price_impact_pct = _price_impact(
        raw_entry_quote.price_impact_pct
    )
    price_impact_notional_usd = (
        None
        if expected_price_impact_pct is None
        else _entry_notional_usd(
            service.entry_input_amount_raw,
            quote_decimals=manifest.quote_decimals,
            quote_to_usd_rate=usd.quote_to_usd_rate,
        )
    )
    market_observed_at = min(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        usd.observed_at_unix_ms,
    )
    source_observed_at = max(
        market_window.current.observed_at_unix_ms,
        raw_entry_quote.quoted_at_unix_ms,
        usd.observed_at_unix_ms,
        controls.updated_at_unix_ms,
    )
    if source_observed_at > evaluated_at:
        raise ValueError(
            "authoritative pending BUY source observation is from the future"
        )
    risk_environment = FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=(
            execution_bootstrap.checkpoint.state.ledger.starting_cash_usd
        ),
        day_started_at_unix_ms=policy.day_started_at_unix_ms,
        liquidity_usd=market_window.current.liquidity_usd,
        expected_price_impact_pct=expected_price_impact_pct,
        price_impact_notional_usd=price_impact_notional_usd,
        market_observed_at_unix_ms=market_observed_at,
        data_healthy=policy.data_healthy,
        execution_healthy=policy.execution_healthy,
        kill_switch_active=(
            policy.global_risk_halt or controls.kill_switch_active
        ),
        active_intent_keys=frozenset(),
        operator_entry_halt_active=controls.halt_new_entries,
    )
    risk_context = build_fast_deterministic_campaign_risk_context(
        execution_bootstrap.checkpoint.state.ledger,
        risk_environment,
        as_of_unix_ms=evaluated_at,
    )
    retry = FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=evaluated_at,
        quote=quote,
        risk_context=risk_context,
        quote_usd_evidence=usd,
    )
    record = build_fast_paper_authoritative_pending_buy_retry_source_record(
        manifest,
        execution_bootstrap,
        evidence,
        retry,
        risk_day_started_at_unix_ms=policy.day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at,
    )
    try:
        write_fast_paper_authoritative_pending_buy_retry_source_record(
            record,
            destination,
        )
    except FileExistsError:
        restored = (
            read_fast_paper_authoritative_pending_buy_retry_source_record(
                manifest,
                execution_bootstrap,
                evidence,
                destination,
            )
        )
        if restored != record:
            raise ValueError(
                "authoritative pending BUY retry writer collision mismatch"
            )
        return 0
    return 1


def _unexecuted_decision(
    manifest,
    decision_bootstrap,
    execution_bootstrap,
    directory: Path,
) -> FastPaperShadowDecisionEvidence | None:
    decision_cursor = (
        0
        if decision_bootstrap.state.cursor is None
        else decision_bootstrap.state.cursor.decision_sequence
    )
    processed = (
        execution_bootstrap.runtime_state.last_processed_source_sequence
    )
    if processed is None:
        if execution_bootstrap.checkpoint.sequence != 0:
            raise ValueError(
                "authoritative non-initial runtime lacks processed decision identity"
            )
        records = _decision_records(manifest, directory)
        if not records:
            return None
        expected = decision_cursor
    else:
        expected = processed + 1
        if decision_cursor < processed:
            raise ValueError(
                "authoritative decision cursor trails economic execution cursor"
            )
    matches = [
        evidence
        for evidence in _decision_records(manifest, directory)
        if evidence.source_sequence == expected
    ]
    if processed is not None and decision_cursor == processed:
        if matches:
            raise ValueError(
                "authoritative evidence exists ahead of a caught-up decision cursor"
            )
        return None
    if decision_cursor == 0:
        return None
    if decision_cursor < expected:
        return None
    if decision_cursor != expected:
        raise ValueError(
            "authoritative source production cursor gap exceeds one decision"
        )
    if len(matches) != 1:
        raise ValueError(
            "authoritative source production requires exactly one pending decision"
        )
    return matches[0]


def _processed_decision_evidence(
    manifest,
    execution_bootstrap,
    directory: Path,
) -> FastPaperShadowDecisionEvidence:
    state = execution_bootstrap.runtime_state
    sequence = state.last_processed_source_sequence
    event_id = state.last_processed_source_event_id
    fingerprint = (
        state.last_processed_decision_evidence_fingerprint_sha256
    )
    if sequence is None or event_id is None or fingerprint is None:
        raise ValueError(
            "authoritative pending BUY lacks durable learned identity"
        )
    matches = [
        value
        for value in _decision_records(manifest, directory)
        if (
            value.source_sequence == sequence
            and value.source_event_id == event_id
            and value.evidence_fingerprint_sha256 == fingerprint
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            "authoritative pending BUY requires one original decision record"
        )
    return matches[0]


def _decision_records(
    manifest,
    directory: Path,
) -> tuple[FastPaperShadowDecisionEvidence, ...]:
    values = []
    for path in sorted(directory.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        if (
            evidence.release_source_sha != manifest.release_source_sha
            or evidence.manifest_fingerprint_sha256
            != manifest.manifest_fingerprint_sha256
            or evidence.champion_fingerprint_sha256
            != manifest.champion_fingerprint_sha256
            or evidence.action_policy_version
            != manifest.action_policy.version
        ):
            raise ValueError(
                "authoritative source decision does not match manifest"
            )
        values.append(evidence)
    return tuple(values)


def _market_mapping(
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    market_key: str,
):
    matches = tuple(
        value
        for value in bootstrap.runtime_state.market_positions
        if value.market_key == market_key
    )
    if len(matches) != 1:
        raise ValueError(
            "authoritative source production requires one OPEN market mapping"
        )
    return matches[0]


def _require_pair(manifest, bootstrap) -> None:
    if (
        bootstrap.binding.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative source binding does not match manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative source execution policy does not match manifest"
        )
    state = bootstrap.runtime_state
    if (
        state.binding_fingerprint_sha256
        != bootstrap.binding.binding_fingerprint_sha256
        or state.execution_policy_fingerprint_sha256
        != bootstrap.execution_policy.policy_fingerprint_sha256
        or state.paper_checkpoint_sequence != bootstrap.checkpoint.sequence
        or state.paper_checkpoint_payload_sha256
        != bootstrap.checkpoint.payload_sha256
    ):
        raise ValueError(
            "authoritative source checkpoint/runtime pair is torn"
        )


def _require_directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"{label} must be an existing regular non-symlink directory"
        )
    return root.resolve(strict=True)


def _pending_retry_filename(
    runtime_state_fingerprint_sha256: str,
    source_event_id: str,
) -> str:
    from .shadow_pending_buy_retry_source import _record_filename

    return _record_filename(
        runtime_state_fingerprint_sha256,
        source_event_id,
    )


def _clock_value(clock: Callable[[], int]) -> int:
    value = clock()
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            "authoritative source production clock must return non-negative integer"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000
