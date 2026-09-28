from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Callable

from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicCampaignRiskEnvironment,
    FastDeterministicComparisonExecutionPolicy,
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
from shreks_brain.research.fast_training_features import (
    feature_logical_fingerprint_sha256,
)

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
from .authoritative_runtime_state import (
    fast_paper_authoritative_decision_position,
)
from .authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionBootstrap,
)
from .feed import fetch_fast_paper_runtime_feature_batch
from .persisted_quotes import (
    FastPaperShadowQuoteReadPolicy,
    resolve_fast_paper_shadow_cycle_input,
)
from .shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .shadow_buy_writer_policy import FastPaperShadowBuyWriterPolicy
from .shadow_execution_input import FastPaperShadowQuoteUsdEvidence
from .shadow_executor import FastPaperShadowPendingBuyRetryInput
from .shadow_open_quote_writer import (
    _persisted_exit_input_amounts,
    _require_replayed_raw_authority,
    _select_reduction_reads,
)
from .shadow_pending_buy_retry_source import (
    _record_filename as _pending_retry_filename,
)
from .shadow_quote_usd_source import (
    build_fast_paper_shadow_quote_usd_source_record,
    read_fast_paper_shadow_quote_usd_source_record,
    write_fast_paper_shadow_quote_usd_source_record,
)
from .shadow_reduction_source import (
    _record_filename as _reduction_filename,
)
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    _resolve_candidate_id,
)


FAST_PAPER_AUTHORITATIVE_QUOTE_USD_WRITER_VERSION = (
    "fast-paper-authoritative-quote-usd-persisted-market-v1"
)
FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_WRITER_VERSION = (
    "fast-paper-authoritative-buy-authority-persisted-evidence-v1"
)


def run_fast_paper_authoritative_source_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    *,
    decision_evidence_directory: str | Path,
    buy_authority_source_directory: str | Path,
    quote_usd_source_directory: str | Path,
    reduction_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    clock_unix_ms: Callable[[], int] | None = None,
) -> int:
    _require_bootstraps(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
    )
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    now = _clock_value(clock)
    written = 0

    written += run_fast_paper_authoritative_open_quote_writer_cycle(
        decision_bootstrap,
        execution_bootstrap,
        reduction_source_directory=reduction_source_directory,
        clock_unix_ms=lambda: now,
    )
    written += run_fast_paper_authoritative_quote_usd_writer_cycle(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
        decision_evidence_directory=decision_evidence_directory,
        quote_usd_source_directory=quote_usd_source_directory,
    )
    written += run_fast_paper_authoritative_buy_authority_writer_cycle(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
        decision_evidence_directory=decision_evidence_directory,
        buy_authority_source_directory=buy_authority_source_directory,
        quote_usd_source_directory=quote_usd_source_directory,
    )
    written += run_fast_paper_authoritative_pending_buy_retry_writer_cycle(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
        decision_evidence_directory=decision_evidence_directory,
        pending_buy_retry_source_directory=(
            pending_buy_retry_source_directory
        ),
        clock_unix_ms=lambda: now,
    )
    return written


def run_fast_paper_authoritative_quote_usd_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    *,
    decision_evidence_directory: str | Path,
    quote_usd_source_directory: str | Path,
) -> int:
    _require_bootstraps(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
    )
    manifest = decision_bootstrap.manifest
    decision_root = _require_directory(
        decision_evidence_directory,
        "authoritative quote/USD decision evidence",
    )
    quote_root = _require_directory(
        quote_usd_source_directory,
        "authoritative quote/USD source",
    )
    evidence = _oldest_unexecuted_decision(
        manifest,
        execution_bootstrap,
        decision_root,
    )
    if evidence is None or evidence.decision.action == "SKIP":
        return 0

    path = quote_root / f"{evidence.evidence_fingerprint_sha256}.json"
    if path.is_symlink():
        raise ValueError("authoritative quote/USD source path is a symlink")
    if path.exists():
        if not path.is_file():
            raise ValueError(
                "authoritative quote/USD source path must be a regular file"
            )
        read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            quote_root,
        )
        return 0

    usd = _quote_usd_for_decision(
        decision_bootstrap,
        writer_policy,
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
            quote_root,
        )
    except FileExistsError:
        restored = read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            quote_root,
        )
        if restored != record:
            raise ValueError(
                "authoritative quote/USD writer collision read-back mismatch"
            )
        return 0
    return 1


def run_fast_paper_authoritative_buy_authority_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    *,
    decision_evidence_directory: str | Path,
    buy_authority_source_directory: str | Path,
    quote_usd_source_directory: str | Path,
) -> int:
    _require_bootstraps(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
    )
    manifest = decision_bootstrap.manifest
    decision_root = _require_directory(
        decision_evidence_directory,
        "authoritative BUY decision evidence",
    )
    authority_root = _require_directory(
        buy_authority_source_directory,
        "authoritative BUY source",
    )
    quote_root = _require_directory(
        quote_usd_source_directory,
        "authoritative BUY quote/USD source",
    )
    evidence = _oldest_unexecuted_decision(
        manifest,
        execution_bootstrap,
        decision_root,
    )
    if evidence is None or evidence.decision.action != "BUY":
        return 0

    path = authority_root / f"{evidence.evidence_fingerprint_sha256}.json"
    if path.is_symlink():
        raise ValueError("authoritative BUY source path is a symlink")
    if path.exists():
        if not path.is_file():
            raise ValueError(
                "authoritative BUY source path must be a regular file"
            )
        read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            authority_root,
        )
        return 0

    quote_path = quote_root / f"{evidence.evidence_fingerprint_sha256}.json"
    if not quote_path.is_file() or quote_path.is_symlink():
        return 0

    record = _produce_authoritative_buy_authority(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
        evidence,
        quote_usd_source_directory=quote_root,
    )
    if record is None:
        return 0
    try:
        write_fast_paper_authoritative_buy_authority_source_record(
            record,
            authority_root,
        )
    except FileExistsError:
        restored = read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            authority_root,
        )
        if restored != record:
            raise ValueError(
                "authoritative BUY writer collision read-back mismatch"
            )
        return 0
    return 1


def run_fast_paper_authoritative_open_quote_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    *,
    reduction_source_directory: str | Path,
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
            "execution_bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    manifest = decision_bootstrap.manifest
    source_root = _require_directory(
        reduction_source_directory,
        "authoritative OPEN reduction source",
    )
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
            "authoritative OPEN quote writer preview must contain at most one row"
        )
    feature = preview.records[0]
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
    if feature.quote_mint != manifest.quote_mint:
        raise ValueError(
            "authoritative OPEN preview quote mint does not match runtime manifest"
        )

    path = source_root / _reduction_filename(
        execution_bootstrap.runtime_state.state_fingerprint_sha256,
        market_key,
    )
    if path.is_symlink():
        raise ValueError("authoritative OPEN reduction source path is a symlink")
    if path.exists():
        if not path.is_file():
            raise ValueError(
                "authoritative OPEN reduction source path must be a regular file"
            )
        read_fast_paper_authoritative_reduction_source_record(
            manifest,
            execution_bootstrap,
            market_key,
            source_root,
        )
        return 0

    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    evaluated_at = _clock_value(
        clock,
        minimum=feature.decision_observed_at_unix_ms,
    )
    policy = decision_bootstrap.policy
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evaluated_at,
        max_quote_age_ms=policy.max_quote_age_ms,
    )
    minimum_observed_at = max(
        feature.decision_observed_at_unix_ms,
        evaluated_at - policy.max_quote_age_ms,
    )
    persisted_inputs = _persisted_exit_input_amounts(
        manifest.observer_database_path,
        candidate_id=candidate_id,
        mint=feature.mint,
        quote_mint=manifest.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        minimum_observed_at_unix_ms=minimum_observed_at,
        evaluated_at_unix_ms=evaluated_at,
    )
    if mapping.current_base_quantity_raw not in persisted_inputs:
        return 0
    reads = _select_reduction_reads(
        manifest.action_policy.reduce_target_exposure_candidates,
        persisted_inputs,
        current_base_quantity_raw=mapping.current_base_quantity_raw,
        current_exposure_fraction=mapping.current_exposure_fraction,
    )
    if reads is None:
        return 0

    quote_read_policy = FastPaperShadowQuoteReadPolicy(
        version=policy.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        exit_input_amount_raw=mapping.current_base_quantity_raw,
        max_quote_age_ms=policy.max_quote_age_ms,
        reduction_reads=reads,
    )
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        position,
        quote_read_policy,
        evaluated_at_unix_ms=evaluated_at,
        max_exposure_fraction=policy.max_exposure_fraction,
        force_sell=False,
    )
    _require_replayed_raw_authority(
        cycle,
        full_exit_input_amount_raw=mapping.current_base_quantity_raw,
        reduction_reads=reads,
    )

    record = build_fast_paper_authoritative_reduction_source_record(
        manifest,
        execution_bootstrap,
        market_key,
        reads,
    )
    try:
        write_fast_paper_authoritative_reduction_source_record(
            record,
            source_root,
        )
    except FileExistsError:
        restored = read_fast_paper_authoritative_reduction_source_record(
            manifest,
            execution_bootstrap,
            market_key,
            source_root,
        )
        if restored != record:
            raise ValueError(
                "authoritative OPEN reduction writer collision mismatch"
            )
        return 0
    return 1


def run_fast_paper_authoritative_pending_buy_retry_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    *,
    decision_evidence_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    clock_unix_ms: Callable[[], int] | None = None,
) -> int:
    _require_bootstraps(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
    )
    checkpoint = execution_bootstrap.checkpoint
    if checkpoint.state.pending_buy is None:
        return 0
    runtime = execution_bootstrap.runtime_state
    if runtime.last_processed_decision_evidence_fingerprint_sha256 is None:
        raise ValueError(
            "authoritative pending BUY lacks durable decision fingerprint"
        )

    manifest = decision_bootstrap.manifest
    decision_root = _require_directory(
        decision_evidence_directory,
        "authoritative pending BUY decision evidence",
    )
    retry_root = _require_directory(
        pending_buy_retry_source_directory,
        "authoritative pending BUY retry source",
    )
    evidence = _decision_by_fingerprint(
        manifest,
        decision_root,
        runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    path = retry_root / _pending_retry_filename(
        runtime.state_fingerprint_sha256,
        evidence.source_event_id,
    )
    if path.is_symlink():
        raise ValueError(
            "authoritative pending BUY retry source path is a symlink"
        )
    if path.exists():
        if not path.is_file():
            raise ValueError(
                "authoritative pending BUY retry source path must be a regular file"
            )
        read_fast_paper_authoritative_pending_buy_retry_source_record(
            manifest,
            execution_bootstrap,
            evidence,
            retry_root,
        )
        return 0

    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms
    evaluated_at = _clock_value(
        clock,
        minimum=checkpoint.state.as_of_unix_ms,
    )
    retry_candidate = _pending_retry_input(
        decision_bootstrap,
        execution_bootstrap,
        writer_policy,
        evidence,
        evaluated_at_unix_ms=evaluated_at,
    )
    if retry_candidate is None:
        return 0
    retry_input, source_observed_at = retry_candidate
    record = build_fast_paper_authoritative_pending_buy_retry_source_record(
        manifest,
        execution_bootstrap,
        evidence,
        retry_input,
        risk_day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at,
    )
    try:
        write_fast_paper_authoritative_pending_buy_retry_source_record(
            record,
            retry_root,
        )
    except FileExistsError:
        restored = (
            read_fast_paper_authoritative_pending_buy_retry_source_record(
                manifest,
                execution_bootstrap,
                evidence,
                retry_root,
            )
        )
        if restored != record:
            raise ValueError(
                "authoritative pending BUY retry writer collision mismatch"
            )
        return 0
    return 1


def _produce_authoritative_buy_authority(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
    *,
    quote_usd_source_directory: Path,
):
    manifest = decision_bootstrap.manifest
    feature = evidence.feature_record
    economics = _execution_economics_by_horizon(
        manifest,
        writer_policy.execution_economics_policies,
    )
    horizon = evidence.decision.selected_horizon_ms
    if horizon is None or horizon not in economics:
        raise ValueError(
            "authoritative BUY learned horizon lacks exact economics policy"
        )
    economics_policy = economics[horizon]
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
        decision_observed_at_unix_ms=feature.decision_observed_at_unix_ms,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
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
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        evidence.position,
        quote_policy,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_exposure_fraction=evidence.decision.target_exposure_fraction,
    )
    if cycle.entry_quote != evidence.entry_quote:
        raise ValueError(
            "authoritative BUY persisted ENTRY quote drifted from decision"
        )
    if cycle.exit_quote != evidence.exit_quote:
        raise ValueError(
            "authoritative BUY persisted EXIT quote drifted from decision"
        )
    if (
        cycle.entry_quote.state != "EXECUTABLE"
        or cycle.exit_quote.state != "EXECUTABLE"
    ):
        return None
    base_quantity = cycle.entry_quote.quoted_base_quantity
    exit_capacity = cycle.exit_quote.available_base_quantity
    if base_quantity is None or exit_capacity is None:
        raise ValueError(
            "authoritative BUY executable quotes require exact quantities"
        )

    execution_evidence = build_fast_champion_entry_execution_evidence(
        champion_path=manifest.champion_path,
        record=feature,
        horizon_ms=economics_policy.horizon_ms,
        cost_model=economics_policy.cost_model,
        base_quantity=base_quantity,
        exit_capacity_base=exit_capacity,
        required_edge_bps=economics_policy.required_edge_bps,
        risk_margin_bps=economics_policy.risk_margin_bps,
        execution_policy_source_version=economics_policy.version,
        exit_capacity_source_version=manifest.route_evidence_version,
    )
    if type(execution_evidence) is not FastChampionEntryExecutionEvidence:
        raise ValueError(
            "authoritative BUY execution evidence type is incompatible"
        )
    if (
        execution_evidence.champion_version != manifest.champion_version
        or execution_evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative BUY execution evidence champion does not match runtime manifest"
        )

    store = ObserverMarketStore(manifest.observer_database_path)
    market_window = store.load_window(
        candidate_id,
        evidence.evaluated_at_unix_ms,
        writer_policy.market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    if (
        market_window.candidate.candidate_id != candidate_id
        or market_window.candidate.mint != feature.mint
    ):
        raise ValueError(
            "authoritative BUY market window candidate does not match learned decision"
        )
    campaign = ObserverCampaignStore(manifest.observer_database_path)
    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=quote_policy.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature.mint,
        taker=quote_policy.taker,
        input_amount=quote_policy.entry_input_amount_raw,
        slippage_bps=quote_policy.slippage_bps,
    )
    raw_entry = campaign.latest_paper_quote(
        entry_identity,
        evidence.evaluated_at_unix_ms,
    )
    if raw_entry is None:
        raise ValueError(
            "authoritative BUY persisted ENTRY price-impact evidence is missing"
        )
    if raw_entry.identity != entry_identity:
        raise ValueError(
            "authoritative BUY persisted ENTRY quote identity mismatch"
        )
    if not raw_entry.route_available:
        return None
    if (
        raw_entry.quoted_at_unix_ms
        != evidence.entry_quote.observed_at_unix_ms
    ):
        raise ValueError(
            "authoritative BUY persisted ENTRY quote timestamp drifted"
        )

    quote_usd_record = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        quote_usd_source_directory,
    )
    quote_usd = quote_usd_record.quote_usd_evidence
    regime_market = campaign.build_regime_market_window(
        evidence.evaluated_at_unix_ms,
        writer_policy.regime_read_policy,
        writer_policy.safety_policy,
        writer_policy.safety_probe_identity,
        global_risk_halt=writer_policy.global_risk_halt,
    )
    regime = assess_regime(
        regime_market,
        writer_policy.regime_policy,
        performance=None,
    )
    controls = load_operator_risk_control_state(
        writer_policy.operator_risk_control_path
    )
    if controls.updated_at_unix_ms > evidence.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative BUY operator control is from after evaluation"
        )
    impact = _price_impact(raw_entry.price_impact_pct)
    impact_notional = (
        None
        if impact is None
        else _entry_notional_usd(
            quote_policy.entry_input_amount_raw,
            quote_decimals=manifest.quote_decimals,
            quote_to_usd_rate=quote_usd.quote_to_usd_rate,
        )
    )
    market_observed_at = min(
        market_window.current.observed_at_unix_ms,
        raw_entry.quoted_at_unix_ms,
        quote_usd.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
    )
    source_observed_at = max(
        market_window.current.observed_at_unix_ms,
        raw_entry.quoted_at_unix_ms,
        cycle.exit_quote.observed_at_unix_ms,
        quote_usd.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
        controls.updated_at_unix_ms,
    )
    risk_environment = FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=(
            execution_bootstrap.checkpoint.state.ledger.starting_cash_usd
        ),
        day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
        liquidity_usd=market_window.current.liquidity_usd,
        expected_price_impact_pct=impact,
        price_impact_notional_usd=impact_notional,
        market_observed_at_unix_ms=market_observed_at,
        data_healthy=writer_policy.data_healthy,
        execution_healthy=writer_policy.execution_healthy,
        kill_switch_active=(
            writer_policy.global_risk_halt or controls.kill_switch_active
        ),
        active_intent_keys=frozenset(),
        operator_entry_halt_active=controls.halt_new_entries,
    )
    entry_authority = derive_fast_deterministic_entry_authority_offline(
        binary_path=writer_policy.entry_authority_binary_path,
        record=feature,
        execution=execution_evidence.execution,
    )
    if entry_authority is None:
        return None
    risk_context = build_fast_deterministic_campaign_risk_context(
        execution_bootstrap.checkpoint.state.ledger,
        risk_environment,
        as_of_unix_ms=evidence.evaluated_at_unix_ms,
    )
    persisted_facts_fingerprint = _persisted_facts_fingerprint(
        manifest=manifest,
        decision_evidence=evidence,
        feature_record=feature,
        quote_read_policy=quote_policy,
        market_window=market_window,
        raw_entry_quote=raw_entry,
        quote_usd_record_fingerprint=(
            quote_usd_record.record_fingerprint_sha256
        ),
        regime_market=regime_market,
        regime_policy_version=writer_policy.regime_policy.version,
        regime_value=regime.regime.value,
        execution_evidence=execution_evidence,
        controls=controls,
        day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
        data_healthy=writer_policy.data_healthy,
        execution_healthy=writer_policy.execution_healthy,
        global_risk_halt=writer_policy.global_risk_halt,
    )
    source_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "version": (
                    FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_WRITER_VERSION
                ),
                "persisted_facts_fingerprint_sha256": (
                    persisted_facts_fingerprint
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return build_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        execution_bootstrap,
        evidence,
        entry_authority,
        risk_context,
        regime.regime,
        risk_day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
        source_observed_at_unix_ms=source_observed_at,
        source_version=FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_WRITER_VERSION,
        source_fingerprint_sha256=source_fingerprint,
    )


def _pending_retry_input(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
    *,
    evaluated_at_unix_ms: int,
) -> tuple[FastPaperShadowPendingBuyRetryInput, int] | None:
    manifest = decision_bootstrap.manifest
    service = decision_bootstrap.policy
    feature = evidence.feature_record
    pending = execution_bootstrap.runtime_state.pending_buy
    if pending is None:
        raise ValueError("authoritative pending BUY runtime mapping is missing")
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=feature.decision_observed_at_unix_ms,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
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
    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        feature,
        evidence.position,
        quote_policy,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        max_exposure_fraction=pending.target_exposure_fraction,
    )
    quote = cycle.entry_quote
    if quote.state != "EXECUTABLE":
        return None
    usd, market_window = _quote_usd_for_feature(
        decision_bootstrap,
        writer_policy,
        feature,
        candidate_id=candidate_id,
        evaluated_at_unix_ms=evaluated_at_unix_ms,
    )
    campaign = ObserverCampaignStore(manifest.observer_database_path)
    entry_identity = ObserverPaperQuoteIdentity(
        candidate_id=candidate_id,
        purpose=ObserverPaperQuotePurpose.ENTRY,
        provider=manifest.quote_provider,
        probe_policy_version=quote_policy.probe_policy_version,
        input_mint=manifest.quote_mint,
        output_mint=feature.mint,
        taker=quote_policy.taker,
        input_amount=quote_policy.entry_input_amount_raw,
        slippage_bps=quote_policy.slippage_bps,
    )
    raw_entry = campaign.latest_paper_quote(
        entry_identity,
        evaluated_at_unix_ms,
    )
    if raw_entry is None:
        return None
    if raw_entry.identity != entry_identity:
        raise ValueError(
            "authoritative pending BUY persisted ENTRY quote identity mismatch"
        )
    if not raw_entry.route_available:
        return None
    if raw_entry.quoted_at_unix_ms != quote.observed_at_unix_ms:
        raise ValueError(
            "authoritative pending BUY persisted ENTRY quote timestamp drifted"
        )
    regime_market = campaign.build_regime_market_window(
        evaluated_at_unix_ms,
        writer_policy.regime_read_policy,
        writer_policy.safety_policy,
        writer_policy.safety_probe_identity,
        global_risk_halt=writer_policy.global_risk_halt,
    )
    controls = load_operator_risk_control_state(
        writer_policy.operator_risk_control_path
    )
    if controls.updated_at_unix_ms > evaluated_at_unix_ms:
        raise ValueError(
            "authoritative pending BUY operator control is from the future"
        )
    impact = _price_impact(raw_entry.price_impact_pct)
    impact_notional = (
        None
        if impact is None
        else _entry_notional_usd(
            quote_policy.entry_input_amount_raw,
            quote_decimals=manifest.quote_decimals,
            quote_to_usd_rate=usd.quote_to_usd_rate,
        )
    )
    risk_environment = FastDeterministicCampaignRiskEnvironment(
        trading_capital_usd=(
            execution_bootstrap.checkpoint.state.ledger.starting_cash_usd
        ),
        day_started_at_unix_ms=writer_policy.day_started_at_unix_ms,
        liquidity_usd=market_window.current.liquidity_usd,
        expected_price_impact_pct=impact,
        price_impact_notional_usd=impact_notional,
        market_observed_at_unix_ms=min(
            market_window.current.observed_at_unix_ms,
            usd.observed_at_unix_ms,
            regime_market.source_observed_at_unix_ms,
        ),
        data_healthy=writer_policy.data_healthy,
        execution_healthy=writer_policy.execution_healthy,
        kill_switch_active=(
            writer_policy.global_risk_halt or controls.kill_switch_active
        ),
        active_intent_keys=frozenset(),
        operator_entry_halt_active=controls.halt_new_entries,
    )
    risk_context = build_fast_deterministic_campaign_risk_context(
        execution_bootstrap.checkpoint.state.ledger,
        risk_environment,
        as_of_unix_ms=evaluated_at_unix_ms,
    )
    source_observed_at = max(
        quote.observed_at_unix_ms,
        usd.observed_at_unix_ms,
        market_window.current.observed_at_unix_ms,
        regime_market.source_observed_at_unix_ms,
        controls.updated_at_unix_ms,
    )
    return (
        FastPaperShadowPendingBuyRetryInput(
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            quote=quote,
            risk_context=risk_context,
            quote_usd_evidence=usd,
        ),
        source_observed_at,
    )


def _quote_usd_for_decision(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    evidence: FastPaperShadowDecisionEvidence,
) -> FastPaperShadowQuoteUsdEvidence:
    service = decision_bootstrap.policy
    feature = evidence.feature_record
    manifest = decision_bootstrap.manifest
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=service.probe_policy_version,
        taker=service.taker,
        slippage_bps=service.slippage_bps,
        entry_input_amount_raw=service.entry_input_amount_raw,
        decision_observed_at_unix_ms=feature.decision_observed_at_unix_ms,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_quote_age_ms=service.max_quote_age_ms,
    )
    value, _window = _quote_usd_for_feature(
        decision_bootstrap,
        writer_policy,
        feature,
        candidate_id=candidate_id,
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
    )
    return value


def _quote_usd_for_feature(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
    feature,
    *,
    candidate_id: int,
    evaluated_at_unix_ms: int,
):
    manifest = decision_bootstrap.manifest
    store = ObserverMarketStore(manifest.observer_database_path)
    window = store.load_window(
        candidate_id,
        evaluated_at_unix_ms,
        writer_policy.market_read_policy,
        required_quote_mint=manifest.quote_mint,
    )
    if (
        window.candidate.candidate_id != candidate_id
        or window.candidate.mint != feature.mint
    ):
        raise ValueError(
            "authoritative quote/USD market window candidate does not match learned decision"
        )
    current = window.current
    evidence = store.quote_asset_usd_evidence(
        candidate_id,
        evaluated_at_unix_ms,
        source=current.source,
        venue=current.venue,
        base_mint=feature.mint,
        quote_mint=manifest.quote_mint,
        max_age_ms=writer_policy.market_read_policy.max_current_age_ms,
        expected_market_row_id=current.row_id,
    )
    rate = float(evidence.quote_asset_usd_per_token)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError(
            "authoritative quote/USD persisted rate must be positive and finite"
        )
    material = {
        "version": FAST_PAPER_AUTHORITATIVE_QUOTE_USD_WRITER_VERSION,
        "market_row_id": evidence.market_row_id,
        "candidate_id": evidence.candidate_id,
        "observed_at_unix_ms": evidence.observed_at_unix_ms,
        "source": evidence.source,
        "venue": evidence.venue,
        "pair_address": evidence.pair_address,
        "base_mint": evidence.base_mint,
        "quote_mint": evidence.quote_mint,
        "base_price_quote": evidence.base_price_quote,
        "base_price_usd": evidence.base_price_usd,
        "quote_asset_usd_per_token": rate,
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
    return (
        FastPaperShadowQuoteUsdEvidence(
            quote_mint=manifest.quote_mint,
            observed_at_unix_ms=evidence.observed_at_unix_ms,
            quote_to_usd_rate=rate,
            source_version=FAST_PAPER_AUTHORITATIVE_QUOTE_USD_WRITER_VERSION,
            source_fingerprint_sha256=fingerprint,
        ),
        window,
    )


def _oldest_unexecuted_decision(
    manifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    directory: Path,
) -> FastPaperShadowDecisionEvidence | None:
    last = bootstrap.runtime_state.last_processed_source_sequence
    pending: list[FastPaperShadowDecisionEvidence] = []
    for path in sorted(directory.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_binding(manifest, evidence)
        if last is None or evidence.source_sequence > last:
            pending.append(evidence)
    if not pending:
        return None
    pending.sort(
        key=lambda value: (
            value.source_sequence,
            value.source_event_id,
        )
    )
    if (
        len(pending) > 1
        and pending[0].source_sequence == pending[1].source_sequence
    ):
        raise ValueError(
            "authoritative source writer has ambiguous oldest decision sequence"
        )
    return pending[0]


def _decision_by_fingerprint(
    manifest,
    directory: Path,
    fingerprint: str,
) -> FastPaperShadowDecisionEvidence:
    matches = []
    for path in sorted(directory.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_binding(manifest, evidence)
        if evidence.evidence_fingerprint_sha256 == fingerprint:
            matches.append(evidence)
    if len(matches) != 1:
        raise ValueError(
            "authoritative pending BUY original decision evidence is missing or ambiguous"
        )
    return matches[0]


def _require_decision_binding(
    manifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    expected = (
        manifest.release_source_sha,
        manifest.manifest_fingerprint_sha256,
        manifest.champion_fingerprint_sha256,
        manifest.action_policy.version,
    )
    actual = (
        evidence.release_source_sha,
        evidence.manifest_fingerprint_sha256,
        evidence.champion_fingerprint_sha256,
        evidence.action_policy_version,
    )
    if actual != expected:
        raise ValueError(
            "authoritative source decision does not match runtime manifest"
        )


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
            "authoritative OPEN writer requires one durable market mapping"
        )
    return matches[0]


def _require_bootstraps(
    decision: FastPaperShadowServiceBootstrap,
    execution: FastPaperAuthoritativeServiceExecutionBootstrap,
    writer_policy: FastPaperShadowBuyWriterPolicy,
) -> None:
    if type(decision) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if (
        type(execution)
        is not FastPaperAuthoritativeServiceExecutionBootstrap
    ):
        raise ValueError(
            "execution bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    if type(writer_policy) is not FastPaperShadowBuyWriterPolicy:
        raise ValueError(
            "writer_policy must be exact FastPaperShadowBuyWriterPolicy"
        )
    if (
        execution.binding.manifest_fingerprint_sha256
        != decision.manifest.manifest_fingerprint_sha256
        or execution.execution_policy.manifest_fingerprint_sha256
        != decision.manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative source writer bootstrap manifest binding mismatch"
        )



def _execution_economics_by_horizon(
    manifest,
    policies: tuple[FastDeterministicComparisonExecutionPolicy, ...],
) -> dict[int, FastDeterministicComparisonExecutionPolicy]:
    if not isinstance(policies, tuple) or not policies:
        raise ValueError(
            "authoritative BUY execution economics must be a non-empty tuple"
        )
    by_horizon: dict[int, FastDeterministicComparisonExecutionPolicy] = {}
    for policy in policies:
        if type(policy) is not FastDeterministicComparisonExecutionPolicy:
            raise ValueError(
                "authoritative BUY execution economics must contain exact policies"
            )
        if policy.horizon_ms in by_horizon:
            raise ValueError(
                "authoritative BUY execution economics contains duplicate horizon"
            )
        by_horizon[policy.horizon_ms] = policy
    expected = set(manifest.action_policy.horizons_ms)
    actual = set(by_horizon)
    if actual != expected:
        raise ValueError(
            "authoritative BUY execution economics horizon coverage mismatch; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    return by_horizon


def _price_impact(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            "authoritative BUY persisted ENTRY price impact is malformed"
        ) from exc
    converted = float(parsed)
    if (
        not parsed.is_finite()
        or not math.isfinite(converted)
        or converted < 0.0
    ):
        raise ValueError(
            "authoritative BUY persisted ENTRY price impact must be finite and non-negative"
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
            "authoritative BUY price-impact notional could not be derived safely"
        ) from exc
    if (
        not value.is_finite()
        or not math.isfinite(converted)
        or converted <= 0.0
    ):
        raise ValueError(
            "authoritative BUY price-impact notional must be positive and finite"
        )
    return converted


def _persisted_facts_fingerprint(
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
        "derivation_version": (
            "fast-paper-authoritative-buy-persisted-facts-v1"
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
    return hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _float_hex(value: object) -> str | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(
            "authoritative BUY persisted market liquidity must be finite or None"
        )
    return float(value).hex()

def _require_directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return root.resolve(strict=True)


def _clock_value(
    clock: Callable[[], int],
    *,
    minimum: int = 0,
) -> int:
    value = clock()
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise ValueError(
            "authoritative source writer clock returned invalid timestamp"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000
