from __future__ import annotations

from pathlib import Path

from shreks_brain.fast_deterministic_campaign.risk_context import (
    FastDeterministicCampaignRiskEnvironment,
    build_fast_deterministic_campaign_risk_context,
)
from shreks_brain.fast_deterministic_offline.entry_authority import (
    derive_fast_deterministic_entry_authority_offline,
)
from shreks_brain.fast_deterministic_offline.models import (
    FastOfflineEntryExecution,
)
from shreks_brain.paper_validation import FastPaperCheckpointRecord
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    feature_logical_fingerprint_sha256,
)

from .models import FastPaperRuntimeManifest
from .shadow import FastPaperShadowDecisionEvidence
from .shadow_buy_authority_source import (
    FastPaperShadowBuyAuthoritySourceRecord,
    build_fast_paper_shadow_buy_authority_source_record,
)
from .shadow_execution_input import FastPaperShadowExecutionPolicy
from .shadow_ledger import FastPaperShadowLedgerBinding
from .shadow_runtime_state import FastPaperShadowRuntimeState


def produce_fast_paper_shadow_buy_authority_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
    feature_record: FastTrainingFeatureRecord,
    entry_execution: FastOfflineEntryExecution,
    risk_environment: FastDeterministicCampaignRiskEnvironment,
    market_regime: MarketRegime,
    *,
    entry_authority_binary_path: str | Path,
    source_observed_at_unix_ms: int,
    source_version: str,
    source_fingerprint_sha256: str,
) -> FastPaperShadowBuyAuthoritySourceRecord | None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError("binding must be exact FastPaperShadowLedgerBinding")
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(paper_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if type(runtime_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "runtime_state must be exact FastPaperShadowRuntimeState"
        )
    if type(decision_evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    if type(feature_record) is not FastTrainingFeatureRecord:
        raise ValueError(
            "feature_record must be exact FastTrainingFeatureRecord"
        )
    if type(entry_execution) is not FastOfflineEntryExecution:
        raise ValueError(
            "entry_execution must be exact FastOfflineEntryExecution"
        )
    if (
        type(risk_environment)
        is not FastDeterministicCampaignRiskEnvironment
    ):
        raise ValueError(
            "risk_environment must be exact "
            "FastDeterministicCampaignRiskEnvironment"
        )
    if type(market_regime) is not MarketRegime:
        raise ValueError("market_regime must be exact MarketRegime")
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )

    _require_feature_decision_binding(
        decision_evidence,
        feature_record,
    )
    _require_external_risk_facts(
        paper_checkpoint,
        decision_evidence,
        risk_environment,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
    )

    entry_authority = derive_fast_deterministic_entry_authority_offline(
        binary_path=entry_authority_binary_path,
        record=feature_record,
        execution=entry_execution,
    )
    if entry_authority is None:
        return None

    risk_context = build_fast_deterministic_campaign_risk_context(
        paper_checkpoint.state.ledger,
        risk_environment,
        as_of_unix_ms=decision_evidence.evaluated_at_unix_ms,
    )

    return build_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
        entry_authority,
        risk_context,
        market_regime,
        risk_day_started_at_unix_ms=(
            risk_environment.day_started_at_unix_ms
        ),
        source_observed_at_unix_ms=source_observed_at_unix_ms,
        source_version=source_version,
        source_fingerprint_sha256=source_fingerprint_sha256,
    )


def _require_feature_decision_binding(
    decision_evidence: FastPaperShadowDecisionEvidence,
    feature_record: FastTrainingFeatureRecord,
) -> None:
    expected_fingerprint = feature_logical_fingerprint_sha256(
        (feature_record,)
    )
    if (
        decision_evidence.feature_record_fingerprint_sha256
        != expected_fingerprint
    ):
        raise ValueError(
            "BUY authority producer feature fingerprint does not match "
            "sealed decision evidence"
        )

    expected_source_event_id = (
        f"{feature_record.decision_signature}:"
        f"{feature_record.decision_ordinal}"
    )
    if decision_evidence.source_event_id != expected_source_event_id:
        raise ValueError(
            "BUY authority producer feature source identity does not match "
            "sealed decision evidence"
        )
    if decision_evidence.source_sequence != feature_record.decision_sequence:
        raise ValueError(
            "BUY authority producer feature sequence does not match "
            "sealed decision evidence"
        )
    if (
        decision_evidence.as_of_unix_ms
        != feature_record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "BUY authority producer feature decision timestamp does not match "
            "sealed decision evidence"
        )

    if decision_evidence.decision.action != "BUY":
        raise ValueError(
            "BUY authority producer requires a learned BUY action"
        )
    if decision_evidence.position.kind != "FLAT":
        raise ValueError(
            "BUY authority producer requires FLAT learned posture"
        )

    quote = decision_evidence.entry_quote
    if quote.mint != feature_record.mint:
        raise ValueError(
            "BUY authority producer feature mint does not match entry quote"
        )
    if quote.quote_mint != feature_record.quote_mint:
        raise ValueError(
            "BUY authority producer feature quote mint does not match "
            "entry quote"
        )
    if (
        quote.reference_price_quote
        != feature_record.decision_executable_entry_price_quote
    ):
        raise ValueError(
            "BUY authority producer feature decision price does not match "
            "sealed entry reference price"
        )


def _require_external_risk_facts(
    paper_checkpoint: FastPaperCheckpointRecord,
    decision_evidence: FastPaperShadowDecisionEvidence,
    risk_environment: FastDeterministicCampaignRiskEnvironment,
    *,
    source_observed_at_unix_ms: int,
) -> None:
    ledger = paper_checkpoint.state.ledger
    if risk_environment.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "BUY authority producer risk trading capital must equal "
            "isolated ledger starting cash"
        )
    if risk_environment.active_intent_keys:
        raise ValueError(
            "BUY authority producer cannot claim external active intents"
        )

    evaluated_at = decision_evidence.evaluated_at_unix_ms
    if risk_environment.day_started_at_unix_ms > evaluated_at:
        raise ValueError(
            "BUY authority producer risk day start cannot be later than "
            "evaluation"
        )
    if risk_environment.market_observed_at_unix_ms > evaluated_at:
        raise ValueError(
            "BUY authority producer risk market observation cannot be from "
            "the future"
        )
    if source_observed_at_unix_ms > evaluated_at:
        raise ValueError(
            "BUY authority producer source observation cannot be later than "
            "evaluation"
        )
    if (
        source_observed_at_unix_ms
        < risk_environment.market_observed_at_unix_ms
    ):
        raise ValueError(
            "BUY authority producer source observation cannot predate risk "
            "market observation"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
