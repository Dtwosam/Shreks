from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
import os

from shreks_brain.decision import DecisionPolicy
from shreks_brain.exits import ExitExecutionContext, ExitPolicy, ExitRouteState
from shreks_brain.features import (
    FEATURE_SCHEMA_VERSION,
    FeatureInputs,
    build_feature_vector,
)
from shreks_brain.observer_market import (
    ObserverMarketReadPolicy,
    ObserverMarketStore,
    build_market_feature_points,
)
from shreks_brain.observer_safety import (
    ObserverSafetyEvidenceStore,
    ObserverSafetyProbeIdentity,
    build_safety_inputs,
)
from shreks_brain.paper import PaperQuote, PaperQuoteState
from shreks_brain.paper_loop import (
    FreshLaunchSetupInput,
    PaperCycleInput,
    PaperEntryCandidate,
    PaperExitObservation,
    PaperLoopState,
)
from shreks_brain.regime import (
    RecentStrategyPerformance,
    RegimePolicy,
    assess_regime,
)
from shreks_brain.risk import RiskPolicy
from shreks_brain.safety import SafetyPolicy, assess_safety
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FRESH_LAUNCH_SETUP_NAME, FreshLaunchPolicy

from .models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
    ObserverRegimeReadPolicy,
)
from .quotes import build_entry_paper_quote, build_exit_paper_quote
from .risk_context import build_observer_risk_context
from .store import ObserverCampaignStore


OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION = "e15-observer-paper-cycle-audit-v1"


class ObserverPaperAssemblyError(ValueError):
    """Raised when one observer paper cycle cannot be assembled without guessing."""


@dataclass(frozen=True, slots=True)
class ObserverFreshLaunchPolicyBundle:
    market_read_policy: ObserverMarketReadPolicy
    safety_policy: SafetyPolicy
    safety_probe_identity: ObserverSafetyProbeIdentity
    regime_read_policy: ObserverRegimeReadPolicy
    regime_policy: RegimePolicy
    fresh_launch_policy: FreshLaunchPolicy
    score_policy: ScorePolicy
    decision_policy: DecisionPolicy
    risk_policy: RiskPolicy
    exit_policy: ExitPolicy
    quote_asset: ObserverPaperQuoteAsset
    entry_quote_identity: ObserverPaperQuoteIdentity
    setup_name: str = FRESH_LAUNCH_SETUP_NAME

    def __post_init__(self) -> None:
        expected_types = (
            ("market_read_policy", self.market_read_policy, ObserverMarketReadPolicy),
            ("safety_policy", self.safety_policy, SafetyPolicy),
            (
                "safety_probe_identity",
                self.safety_probe_identity,
                ObserverSafetyProbeIdentity,
            ),
            ("regime_read_policy", self.regime_read_policy, ObserverRegimeReadPolicy),
            ("regime_policy", self.regime_policy, RegimePolicy),
            ("fresh_launch_policy", self.fresh_launch_policy, FreshLaunchPolicy),
            ("score_policy", self.score_policy, ScorePolicy),
            ("decision_policy", self.decision_policy, DecisionPolicy),
            ("risk_policy", self.risk_policy, RiskPolicy),
            ("exit_policy", self.exit_policy, ExitPolicy),
            ("quote_asset", self.quote_asset, ObserverPaperQuoteAsset),
            (
                "entry_quote_identity",
                self.entry_quote_identity,
                ObserverPaperQuoteIdentity,
            ),
        )
        for name, value, expected_type in expected_types:
            if type(value) is not expected_type:
                raise ObserverPaperAssemblyError(
                    f"{name} must be an exact {expected_type.__name__}"
                )

        if self.setup_name != FRESH_LAUNCH_SETUP_NAME:
            raise ObserverPaperAssemblyError(
                "E15 V1 supports Fresh Launch assembly only"
            )
        entry = self.entry_quote_identity
        if entry.purpose is not ObserverPaperQuotePurpose.ENTRY:
            raise ObserverPaperAssemblyError(
                "entry_quote_identity must have ENTRY purpose"
            )
        if entry.provider != "jupiter":
            raise ObserverPaperAssemblyError(
                "entry quote provider must match the sealed regime reader provider"
            )
        if entry.input_mint != self.quote_asset.mint:
            raise ObserverPaperAssemblyError(
                "entry quote input mint must match the explicit quote asset"
            )

        regime_read = self.regime_read_policy
        if (
            regime_read.entry_probe_policy_version != entry.probe_policy_version
            or regime_read.quote_asset_mint != entry.input_mint
            or regime_read.entry_input_amount != entry.input_amount
            or regime_read.taker != entry.taker
            or regime_read.slippage_bps != entry.slippage_bps
        ):
            raise ObserverPaperAssemblyError(
                "regime read entry quote identity must match entry_quote_identity"
            )

        safety_probe = self.safety_probe_identity
        if (
            safety_probe.probe_policy_version != entry.probe_policy_version
            or safety_probe.output_mint != self.quote_asset.mint
            or safety_probe.taker != entry.taker
            or safety_probe.slippage_bps != entry.slippage_bps
        ):
            raise ObserverPaperAssemblyError(
                "safety probe and entry quote identities must describe one quote pair"
            )

        if self.score_policy.required_feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ObserverPaperAssemblyError(
                "score policy must require the sealed B2 feature schema"
            )
        if self.decision_policy.required_score_policy_version != self.score_policy.version:
            raise ObserverPaperAssemblyError(
                "decision policy must require the bundled score policy"
            )
        if (
            self.risk_policy.required_decision_policy_version
            != self.decision_policy.version
        ):
            raise ObserverPaperAssemblyError(
                "risk policy must require the bundled decision policy"
            )
        if self.risk_policy.required_feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ObserverPaperAssemblyError(
                "risk policy must require the sealed B2 feature schema"
            )
        if self.exit_policy.required_feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ObserverPaperAssemblyError(
                "exit policy must require the sealed B2 feature schema"
            )


@dataclass(frozen=True, slots=True)
class ObserverPaperCycleAudit:
    schema_version: str
    candidate_id: int
    mint: str
    as_of_unix_ms: int
    market_current_observed_at_unix_ms: int
    entry_quote_observed_at_unix_ms: int | None
    exit_quote_observed_at_unix_ms: int | None
    market_fingerprint: str
    safety_fingerprint: str
    feature_fingerprint: str
    regime_fingerprint: str
    risk_context_fingerprint: str
    entry_quote_identity_fingerprint: str
    exit_quote_identity_fingerprint: str
    entry_quote_evidence_fingerprint: str | None
    exit_quote_evidence_fingerprint: str | None
    paper_cycle_fingerprint: str

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION:
            raise ValueError("unsupported observer paper cycle audit schema version")
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_negative_int(
            "market_current_observed_at_unix_ms",
            self.market_current_observed_at_unix_ms,
        )
        for name in (
            "entry_quote_observed_at_unix_ms",
            "exit_quote_observed_at_unix_ms",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_int(name, value)
                if value > self.as_of_unix_ms:
                    raise ValueError(f"{name} cannot be later than as_of_unix_ms")
        for name in (
            "market_fingerprint",
            "safety_fingerprint",
            "feature_fingerprint",
            "regime_fingerprint",
            "risk_context_fingerprint",
            "entry_quote_identity_fingerprint",
            "exit_quote_identity_fingerprint",
            "paper_cycle_fingerprint",
        ):
            _require_sha256(name, getattr(self, name))
        for name in (
            "entry_quote_evidence_fingerprint",
            "exit_quote_evidence_fingerprint",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_sha256(name, value)


def assemble_observer_paper_cycle(
    database_path: str | os.PathLike[str],
    state: PaperLoopState,
    as_of_unix_ms: int,
    bundle: ObserverFreshLaunchPolicyBundle,
    environment: ObserverPaperRiskEnvironment,
    *,
    recent_performance: RecentStrategyPerformance | None = None,
    global_risk_halt: bool,
) -> tuple[PaperCycleInput, ObserverPaperCycleAudit]:
    if type(state) is not PaperLoopState:
        raise ObserverPaperAssemblyError("state must be a PaperLoopState")
    if type(bundle) is not ObserverFreshLaunchPolicyBundle:
        raise ObserverPaperAssemblyError(
            "bundle must be an ObserverFreshLaunchPolicyBundle"
        )
    if type(environment) is not ObserverPaperRiskEnvironment:
        raise ObserverPaperAssemblyError(
            "environment must be an ObserverPaperRiskEnvironment"
        )
    _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    if type(global_risk_halt) is not bool:
        raise ObserverPaperAssemblyError("global_risk_halt must be a boolean")
    if recent_performance is not None and type(recent_performance) is not RecentStrategyPerformance:
        raise ObserverPaperAssemblyError(
            "recent_performance must be a RecentStrategyPerformance or None"
        )
    if as_of_unix_ms < state.last_cycle_at_unix_ms:
        raise ObserverPaperAssemblyError(
            "assembly timestamp cannot precede current paper-loop state"
        )

    try:
        market_store = ObserverMarketStore(database_path)
        safety_store = ObserverSafetyEvidenceStore(database_path)
        campaign_store = ObserverCampaignStore(database_path)

        candidate_id = bundle.entry_quote_identity.candidate_id
        window = market_store.load_window(
            candidate_id,
            as_of_unix_ms,
            bundle.market_read_policy,
        )
        if window.candidate.mint != bundle.entry_quote_identity.output_mint:
            raise ObserverPaperAssemblyError(
                "entry quote candidate mint attribution does not match observer candidate"
            )

        entry_identity = bundle.entry_quote_identity
        exit_identity = _exit_identity(window.candidate.mint, bundle)
        entry_evidence = campaign_store.latest_paper_quote(
            entry_identity,
            as_of_unix_ms,
        )
        exit_evidence = campaign_store.latest_paper_quote(
            exit_identity,
            as_of_unix_ms,
        )
        token_decimals = campaign_store.latest_token_decimals(
            candidate_id,
            window.candidate.mint,
            as_of_unix_ms,
        )
        if (entry_evidence is not None or exit_evidence is not None) and token_decimals is None:
            raise ObserverPaperAssemblyError(
                "token decimals are required to reconstruct persisted paper quotes"
            )

        entry_quote: PaperQuote | None = None
        exit_quote: PaperQuote | None = None
        if entry_evidence is not None:
            assert token_decimals is not None
            entry_quote = build_entry_paper_quote(
                window,
                entry_evidence,
                token_decimals,
                bundle.quote_asset,
            )
        if exit_evidence is not None:
            assert token_decimals is not None
            exit_quote = build_exit_paper_quote(
                window,
                exit_evidence,
                token_decimals,
                bundle.quote_asset,
            )

        safety_inputs = build_safety_inputs(
            window,
            safety_store,
            bundle.safety_probe_identity,
            global_risk_halt,
        )
        safety = assess_safety(safety_inputs, bundle.safety_policy)
        current, one_minute, five_minutes, fifteen_minutes = (
            build_market_feature_points(window)
        )
        features = build_feature_vector(
            FeatureInputs(
                as_of_unix_ms=as_of_unix_ms,
                current=current,
                one_minute_ago=one_minute,
                five_minutes_ago=five_minutes,
                fifteen_minutes_ago=fifteen_minutes,
                pair_created_at_unix_ms=window.pair_created_at_unix_ms,
                local_high_price_usd=window.local_high_price_usd,
                local_low_price_usd=window.local_low_price_usd,
                exit_price_impact_pct=safety_inputs.exit_price_impact_pct,
                safety=safety,
            )
        )

        regime_market = campaign_store.build_regime_market_window(
            as_of_unix_ms,
            bundle.regime_read_policy,
            bundle.safety_policy,
            bundle.safety_probe_identity,
            global_risk_halt=global_risk_halt,
        )
        regime = assess_regime(
            regime_market,
            bundle.regime_policy,
            recent_performance,
        )
        risk_context = build_observer_risk_context(
            state,
            window,
            None
            if entry_evidence is None or entry_quote is None
            else (entry_evidence, entry_quote),
            environment,
        )

        entry_candidate = PaperEntryCandidate(
            mint=window.candidate.mint,
            features=features,
            regime=regime,
            setup=FreshLaunchSetupInput(policy=bundle.fresh_launch_policy),
            score_policy=bundle.score_policy,
            decision_policy=bundle.decision_policy,
            risk_context=risk_context,
            risk_policy=bundle.risk_policy,
            exit_policy=bundle.exit_policy,
        )

        matching_managed = tuple(
            managed
            for managed in state.managed_positions
            if managed.exit_state.mint == window.candidate.mint
        )
        if (
            state.pending_entry is not None
            and state.pending_entry.intent.mint == window.candidate.mint
            and matching_managed
        ):
            raise ObserverPaperAssemblyError(
                "one cycle cannot safely carry both pending ENTRY and managed EXIT quote semantics for one mint"
            )

        exit_observations = tuple(
            PaperExitObservation(
                position_id=managed.position_id,
                features=features,
                execution_context=_exit_execution_context(
                    as_of_unix_ms,
                    window.current.observed_at_unix_ms,
                    exit_evidence,
                    exit_quote,
                    global_risk_halt,
                ),
            )
            for managed in matching_managed
        )

        quotes: tuple[PaperQuote, ...]
        pending_same_mint = (
            state.pending_entry is not None
            and state.pending_entry.intent.mint == window.candidate.mint
        )
        if matching_managed and not pending_same_mint:
            quotes = () if exit_quote is None else (exit_quote,)
        else:
            quotes = () if entry_quote is None else (entry_quote,)

        cycle = PaperCycleInput(
            as_of_unix_ms=as_of_unix_ms,
            entry_candidates=(entry_candidate,),
            exit_observations=exit_observations,
            quotes=quotes,
        )
        audit = ObserverPaperCycleAudit(
            schema_version=OBSERVER_PAPER_CYCLE_AUDIT_SCHEMA_VERSION,
            candidate_id=candidate_id,
            mint=window.candidate.mint,
            as_of_unix_ms=as_of_unix_ms,
            market_current_observed_at_unix_ms=window.current.observed_at_unix_ms,
            entry_quote_observed_at_unix_ms=(
                None if entry_evidence is None else entry_evidence.quoted_at_unix_ms
            ),
            exit_quote_observed_at_unix_ms=(
                None if exit_evidence is None else exit_evidence.quoted_at_unix_ms
            ),
            market_fingerprint=_fingerprint(window),
            safety_fingerprint=_fingerprint(safety),
            feature_fingerprint=_fingerprint(features),
            regime_fingerprint=_fingerprint(regime),
            risk_context_fingerprint=_fingerprint(risk_context),
            entry_quote_identity_fingerprint=_fingerprint(entry_identity),
            exit_quote_identity_fingerprint=_fingerprint(exit_identity),
            entry_quote_evidence_fingerprint=(
                None if entry_evidence is None else _fingerprint(entry_evidence)
            ),
            exit_quote_evidence_fingerprint=(
                None if exit_evidence is None else _fingerprint(exit_evidence)
            ),
            paper_cycle_fingerprint=_fingerprint(cycle),
        )
        return cycle, audit
    except ObserverPaperAssemblyError:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise ObserverPaperAssemblyError(
            f"observer paper cycle assembly failed: {error}"
        ) from error


def _exit_identity(
    candidate_mint: str,
    bundle: ObserverFreshLaunchPolicyBundle,
) -> ObserverPaperQuoteIdentity:
    entry = bundle.entry_quote_identity
    probe = bundle.safety_probe_identity
    return ObserverPaperQuoteIdentity(
        candidate_id=entry.candidate_id,
        purpose=ObserverPaperQuotePurpose.EXIT,
        provider=entry.provider,
        probe_policy_version=probe.probe_policy_version,
        input_mint=candidate_mint,
        output_mint=bundle.quote_asset.mint,
        taker=probe.taker,
        input_amount=probe.input_amount,
        slippage_bps=probe.slippage_bps,
    )


def _exit_execution_context(
    as_of_unix_ms: int,
    market_observed_at_unix_ms: int,
    evidence: ObserverPaperQuoteEvidence | None,
    quote: PaperQuote | None,
    global_risk_halt: bool,
) -> ExitExecutionContext:
    if evidence is None:
        if quote is not None:
            raise ObserverPaperAssemblyError(
                "exit PaperQuote cannot exist without raw exit evidence"
            )
        return ExitExecutionContext(
            as_of_unix_ms=as_of_unix_ms,
            observed_at_unix_ms=market_observed_at_unix_ms,
            route_state=ExitRouteState.UNKNOWN,
            available_exit_notional_usd=None,
            expected_exit_price_impact_pct=None,
            price_impact_notional_usd=None,
            wallet_distribution_detected=None,
            global_halt_active=global_risk_halt,
        )
    if quote is None:
        raise ObserverPaperAssemblyError(
            "raw exit evidence requires a reconstructed exit PaperQuote"
        )
    if evidence.quoted_at_unix_ms != quote.observed_at_unix_ms:
        raise ObserverPaperAssemblyError("exit quote timestamps are contradictory")

    if not evidence.route_available:
        if quote.state is not PaperQuoteState.UNAVAILABLE:
            raise ObserverPaperAssemblyError(
                "unavailable exit evidence requires an unavailable PaperQuote"
            )
        route_state = ExitRouteState.UNAVAILABLE
        available_notional = None
        expected_impact = None
        impact_notional = None
    else:
        if quote.state is not PaperQuoteState.EXECUTABLE:
            raise ObserverPaperAssemblyError(
                "route-available exit evidence requires an executable PaperQuote"
            )
        route_state = ExitRouteState.AVAILABLE
        available_notional = quote.available_notional_usd
        expected_impact = _optional_percentage_text(
            evidence.price_impact_pct,
            "exit price impact",
        )
        impact_notional = (
            quote.quoted_notional_usd if expected_impact is not None else None
        )

    return ExitExecutionContext(
        as_of_unix_ms=as_of_unix_ms,
        observed_at_unix_ms=evidence.quoted_at_unix_ms,
        route_state=route_state,
        available_exit_notional_usd=available_notional,
        expected_exit_price_impact_pct=expected_impact,
        price_impact_notional_usd=impact_notional,
        wallet_distribution_detected=None,
        global_halt_active=global_risk_halt,
    )


def _optional_percentage_text(value: str | None, name: str) -> float | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ObserverPaperAssemblyError(f"{name} is malformed") from error
    converted = float(parsed)
    if (
        not parsed.is_finite()
        or not math.isfinite(converted)
        or converted < 0.0
        or converted > 100.0
    ):
        raise ObserverPaperAssemblyError(
            f"{name} must be finite and within [0, 100]"
        )
    return converted


def _fingerprint(value: object) -> str:
    normalized = _normalize(value)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObserverPaperAssemblyError(
                "non-finite float cannot be fingerprinted"
            )
        return {"__float_hex__": value.hex()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized_items = [_normalize(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise ObserverPaperAssemblyError(
        f"unsupported audit fingerprint value type: {type(value).__name__}"
    )


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


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex string")
    if value.lower() != value:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex string")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex string") from error
