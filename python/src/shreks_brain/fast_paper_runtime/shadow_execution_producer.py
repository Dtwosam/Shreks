from __future__ import annotations

from shreks_brain.paper import derive_paper_risk_accounting_facts
from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .models import FastPaperRuntimeManifest
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
)
from .shadow_execution_source import (
    FastPaperShadowExecutionInputSourceRecord,
    build_fast_paper_shadow_execution_input_source_record,
)
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FastPaperShadowRuntimeState,
    fast_paper_shadow_decision_position,
    load_latest_fast_paper_shadow_runtime_state,
)


def produce_fast_paper_shadow_execution_input_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    shadow_state: FastPaperShadowRuntimeState,
    source: FastPaperShadowExecutionInput,
    *,
    source_observed_at_unix_ms: int,
    risk_day_started_at_unix_ms: int | None,
) -> FastPaperShadowExecutionInputSourceRecord:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(paper_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if type(shadow_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "shadow_state must be exact FastPaperShadowRuntimeState"
        )
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )

    latest_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest_checkpoint is None:
        raise ValueError(
            "shadow execution source producer requires a durable checkpoint"
        )
    latest_shadow_state = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_shadow_state is None:
        raise ValueError(
            "shadow execution source producer requires durable runtime state"
        )
    if paper_checkpoint != latest_checkpoint:
        raise ValueError(
            "shadow execution source producer requires the exact latest checkpoint"
        )
    if shadow_state != latest_shadow_state:
        raise ValueError(
            "shadow execution source producer requires the exact latest runtime state"
        )
    if (
        shadow_state.paper_checkpoint_sequence
        != paper_checkpoint.sequence
        or shadow_state.paper_checkpoint_payload_sha256
        != paper_checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow execution source producer checkpoint/runtime pair is torn"
        )
    if (
        shadow_state.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution source producer execution policy fingerprint drift"
        )

    evidence = source.decision_evidence
    current_position = fast_paper_shadow_decision_position(
        shadow_state,
        evidence.market_key,
    )
    if evidence.position != current_position:
        raise ValueError(
            "shadow execution source producer decision posture does not match durable position state"
        )
    if evidence.as_of_unix_ms < paper_checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "shadow execution source producer decision predates durable PAPER state"
        )
    if source_observed_at_unix_ms > evidence.evaluated_at_unix_ms:
        raise ValueError(
            "shadow execution source producer observation cannot be later than evaluation"
        )

    action = evidence.decision.action
    if action == "BUY":
        if risk_day_started_at_unix_ms is None:
            raise ValueError(
                "BUY shadow execution source production requires a risk day start"
            )
        _require_non_negative_int(
            "risk_day_started_at_unix_ms",
            risk_day_started_at_unix_ms,
        )
        if risk_day_started_at_unix_ms > evidence.evaluated_at_unix_ms:
            raise ValueError(
                "BUY risk day start cannot be later than evaluation"
            )
        if (
            paper_checkpoint.state.pending_buy is not None
            or shadow_state.pending_buy is not None
        ):
            raise ValueError(
                "BUY shadow execution source production requires no unresolved pending BUY"
            )
        risk = source.risk_context
        assert risk is not None
        _require_buy_risk_context_matches_checkpoint(
            paper_checkpoint,
            risk,
            day_started_at_unix_ms=risk_day_started_at_unix_ms,
        )
    elif risk_day_started_at_unix_ms is not None:
        raise ValueError(
            "non-BUY shadow execution source production cannot carry a risk day start"
        )

    return build_fast_paper_shadow_execution_input_source_record(
        manifest,
        execution_policy,
        source,
        paper_checkpoint_sequence=paper_checkpoint.sequence,
        paper_checkpoint_payload_sha256=paper_checkpoint.payload_sha256,
        shadow_runtime_state_fingerprint_sha256=(
            shadow_state.state_fingerprint_sha256
        ),
        source_observed_at_unix_ms=source_observed_at_unix_ms,
    )


def _require_buy_risk_context_matches_checkpoint(
    paper_checkpoint: FastPaperCheckpointRecord,
    risk: object,
    *,
    day_started_at_unix_ms: int,
) -> None:
    from shreks_brain.risk import RiskContext

    if type(risk) is not RiskContext:
        raise ValueError(
            "BUY shadow execution source production requires exact RiskContext"
        )
    ledger = paper_checkpoint.state.ledger
    if risk.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "BUY risk trading capital must equal isolated ledger starting cash"
        )
    if risk.active_intent_keys:
        raise ValueError(
            "BUY shadow execution source production cannot claim external active intents"
        )

    accounting = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=day_started_at_unix_ms,
    )
    expected = {
        "open position count": accounting.open_position_count,
        "aggregate open risk": accounting.aggregate_open_risk_usd,
        "daily realized PnL": accounting.daily_realized_pnl_usd,
        "rolling drawdown": accounting.rolling_drawdown_pct,
        "consecutive losses": accounting.consecutive_losses,
        "last loss timestamp": accounting.last_loss_at_unix_ms,
    }
    actual = {
        "open position count": risk.open_position_count,
        "aggregate open risk": risk.aggregate_open_risk_usd,
        "daily realized PnL": risk.daily_realized_pnl_usd,
        "rolling drawdown": risk.rolling_drawdown_pct,
        "consecutive losses": risk.consecutive_losses,
        "last loss timestamp": risk.last_loss_at_unix_ms,
    }
    for name, value in expected.items():
        if actual[name] != value:
            raise ValueError(
                f"BUY risk accounting {name} does not match durable ledger"
            )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
