from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from shreks_brain.evaluation import (
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.fast_campaign import (
    fast_campaign_result_to_paper_assessment,
)
from shreks_brain.paper import (
    PaperLedgerReasonCode,
    PaperLedgerUpdateState,
)
from shreks_brain.paper_evaluation import build_evaluated_trades
from shreks_brain.paper_evaluation.fast import (
    FAST_PAPER_EVALUATION_ADAPTER_VERSION,
    FastPaperEntryEvaluationContext,
    FastPaperEvaluationIdentity,
    FastPaperExecutionEvidenceInput,
    extract_fast_paper_evaluation_evidence,
)
from shreks_brain.regime import MarketRegime

from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow import (
    read_fast_paper_shadow_decision_evidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .fast_paper_runtime.shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_execution_source import (
    FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME,
    read_fast_paper_shadow_execution_input_source_record,
)
from .fast_paper_runtime.shadow_executor import (
    reconstruct_fast_paper_shadow_decision,
    reconstruct_fast_paper_shadow_pending_buy_retry,
)
from .fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    load_fast_paper_shadow_ledger_checkpoint_at_or_before,
    load_fast_paper_shadow_ledger_checkpoint_by_sequence,
)
from .fast_paper_runtime.shadow_pending_buy_retry_source import (
    FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME,
    read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint,
)
from .fast_paper_runtime.shadow_runtime_state import (
    load_fast_paper_shadow_runtime_state_by_checkpoint_sequence,
)
from .fast_paper_shadow_sample_proof import (
    FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME,
    FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION,
)


FAST_PAPER_SHADOW_TRADE_ECONOMICS_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_trade_economics"
)
FAST_PAPER_SHADOW_TRADE_ECONOMICS_SCHEMA_VERSION = 1
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_SAMPLE_REPORT_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy_version",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_version",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "binding_fingerprint_sha256",
        "window_since_unix_ms",
        "window_until_unix_ms",
        "window_duration_ms",
        "first_source_sequence",
        "last_source_sequence",
        "decision_count",
        "distinct_market_count",
        "distinct_mint_count",
        "observation_span_ms",
        "closed_position_count",
        "distinct_traded_mint_count",
        "distinct_buy_regime_count",
        "distinct_selected_horizon_count",
        "missing_buy_execution_source_count",
        "action_counts",
        "selected_horizon_counts",
        "buy_regime_counts",
        "gate_results",
        "decision",
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
        "live_authority",
        "report_fingerprint_sha256",
    }
)


class FastPaperShadowTradeEconomicsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _EntryMetadata:
    source_event_id: str
    mint: str
    market_regime: MarketRegime
    selected_horizon_ms: int
    selected_value_bps: float
    trading_capital_usd: float

    def __post_init__(self) -> None:
        for name in ("source_event_id", "mint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be non-empty")
        if type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be exact MarketRegime")
        if (
            isinstance(self.selected_horizon_ms, bool)
            or not isinstance(self.selected_horizon_ms, int)
            or self.selected_horizon_ms <= 0
        ):
            raise ValueError("selected_horizon_ms must be positive integer")
        _finite("selected_value_bps", self.selected_value_bps)
        _positive("trading_capital_usd", self.trading_capital_usd)


@dataclass(frozen=True, slots=True)
class _Reconstruction:
    capture: object
    position_metadata: Mapping[str, _EntryMetadata]
    final_checkpoint: object


def collect_fast_paper_shadow_trade_economics(
    *,
    manifest_path: str | Path,
    execution_policy_path: str | Path,
    ledger_database_path: str | Path,
    run_id: str,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    sample_proof_path: str | Path,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
    evaluation_policy_version: str,
    calibration_bucket_count: int,
) -> dict[str, object]:
    expected_sha = _release_sha(expected_release_sha)
    since, until = _window(since_unix_ms, until_unix_ms)
    if not isinstance(run_id, str) or not run_id.strip():
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics run id must be non-empty"
        )
    if (
        not isinstance(evaluation_policy_version, str)
        or not evaluation_policy_version.strip()
    ):
        raise FastPaperShadowTradeEconomicsError(
            "evaluation policy version must be non-empty"
        )
    if (
        isinstance(calibration_bucket_count, bool)
        or not isinstance(calibration_bucket_count, int)
        or calibration_bucket_count < 2
        or calibration_bucket_count > 100
    ):
        raise FastPaperShadowTradeEconomicsError(
            "calibration bucket count must be within [2, 100]"
        )

    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
        execution_policy = read_fast_paper_shadow_execution_policy(
            manifest,
            execution_policy_path,
        )
        binding = build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id=run_id,
            database_path=ledger_database_path,
        )
    except Exception as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics authority authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics release identity mismatch"
        )

    sample = _read_sample_proof(sample_proof_path)
    _require_sample_matches(
        sample,
        manifest=manifest,
        binding=binding,
        expected_release_sha=expected_sha,
        since_unix_ms=since,
        until_unix_ms=until,
    )

    reconstruction = _reconstruct_evaluation_capture(
        manifest=manifest,
        execution_policy=execution_policy,
        binding=binding,
        decision_evidence_directory=decision_evidence_directory,
        execution_source_directory=execution_source_directory,
        pending_buy_retry_source_directory=pending_buy_retry_source_directory,
        until_unix_ms=until,
    )
    capture = reconstruction.capture
    try:
        all_trades = build_evaluated_trades(
            binding.run_id,
            manifest.champion_version,
            capture.entry_provenance,
            capture.executions,
            capture.closures,
            capture.orphan_costs,
        )
    except Exception as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics E11 trade normalization failed"
        ) from exc
    trades = tuple(
        trade
        for trade in all_trades
        if since <= trade.closed_at_unix_ms < until
    )

    if len(trades) != sample["closed_position_count"]:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics closed-trade count does not reconcile with FL11.1"
        )
    if len({trade.candidate_mint for trade in trades}) != sample[
        "distinct_traded_mint_count"
    ]:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics traded-mint count does not reconcile with FL11.1"
        )

    starting_equity = reconstruction.final_checkpoint.state.ledger.starting_cash_usd
    evaluation_policy = TradingEvaluationPolicy(
        version=evaluation_policy_version,
        starting_equity_usd=starting_equity,
        calibration_bucket_count=calibration_bucket_count,
    )
    try:
        e5_report = evaluate_trading_performance(
            trades,
            (),
            evaluation_policy,
            manifest.champion_version,
        )
    except Exception as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics sealed E5 evaluation failed"
        ) from exc

    metadata = reconstruction.position_metadata
    for trade in trades:
        if trade.position_id not in metadata:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics evaluated trade lacks authenticated entry metadata"
            )

    horizon_performance = _horizon_performance(
        trades,
        metadata,
        evaluation_policy,
        manifest.champion_version,
    )
    calibration = _expected_realized_calibration(trades, metadata)
    tail = _loss_tail(trades)
    entry_efficiency = _entry_efficiency(trades, capture.executions)
    exit_timing = _exit_timing(
        trades,
        capture.executions,
        capture.closures,
        metadata,
    )
    capital = _entry_capital_utilization(trades, metadata)

    material: dict[str, object] = {
        "schema_name": FAST_PAPER_SHADOW_TRADE_ECONOMICS_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_TRADE_ECONOMICS_SCHEMA_VERSION,
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "strategy_family": manifest.strategy_family,
        "strategy_version": manifest.strategy_version,
        "action_policy_version": manifest.action_policy.version,
        "binding_fingerprint_sha256": binding.binding_fingerprint_sha256,
        "window_since_unix_ms": since,
        "window_until_unix_ms": until,
        "window_duration_ms": until - since,
        "sample_proof_fingerprint_sha256": sample[
            "report_fingerprint_sha256"
        ],
        "sample_policy_version": sample["policy_version"],
        "evaluation_policy_version": evaluation_policy.version,
        "closed_trade_count": len(trades),
        "sealed_e5_report": asdict(e5_report),
        "horizon_performance": horizon_performance,
        "expected_realized_value_bps": calibration,
        "loss_tail": tail,
        "entry_efficiency": entry_efficiency,
        "exit_timing": exit_timing,
        "entry_capital_utilization": capital,
        "counterfactual_missed_opportunity_evidence": "NOT_INCLUDED_FL11_2A",
        "fee_slippage_sensitivity_evidence": "NOT_INCLUDED_FL11_2A",
        "promotion_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    return _finalize(material)


def _reconstruct_evaluation_capture(
    *,
    manifest: object,
    execution_policy: object,
    binding: object,
    decision_evidence_directory: str | Path,
    execution_source_directory: str | Path,
    pending_buy_retry_source_directory: str | Path,
    until_unix_ms: int,
) -> _Reconstruction:
    decision_root = _directory(
        decision_evidence_directory,
        "decision evidence",
    )
    source_root = _directory(
        execution_source_directory,
        "execution source",
    )
    retry_root = _directory(
        pending_buy_retry_source_directory,
        "pending BUY retry source",
    )
    try:
        final_checkpoint = load_fast_paper_shadow_ledger_checkpoint_at_or_before(
            manifest,
            binding,
            as_of_unix_ms=until_unix_ms - 1,
        )
    except Exception as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics final checkpoint read failed"
        ) from exc
    if final_checkpoint is None:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics requires a checkpoint before window end"
        )

    decisions = _decision_index(
        decision_root,
        manifest=manifest,
        until_unix_ms=until_unix_ms,
    )
    fresh = _fresh_source_index(source_root)
    retries = _retry_source_index(retry_root)

    required_sequences = set(range(final_checkpoint.sequence))
    available_sequences = set(fresh) | set(retries)
    if set(fresh) & set(retries):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics checkpoint has both fresh and retry sources"
        )
    if available_sequences & required_sequences != required_sequences:
        missing = sorted(required_sequences - available_sequences)
        raise FastPaperShadowTradeEconomicsError(
            f"shadow economics durable source coverage is incomplete at sequences {missing}"
        )

    identity = FastPaperEvaluationIdentity(
        version=FAST_PAPER_EVALUATION_ADAPTER_VERSION,
        paper_run_id=binding.run_id,
        candidate_version=manifest.champion_version,
        candidate_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        strategy_version=manifest.strategy_version,
        allowed_assessment_strategy_versions=(manifest.strategy_version,),
    )
    execution_inputs: list[FastPaperExecutionEvidenceInput] = []
    entry_contexts: list[FastPaperEntryEvaluationContext] = []
    event_metadata: dict[str, _EntryMetadata] = {}
    position_metadata: dict[str, _EntryMetadata] = {}

    for sequence in range(final_checkpoint.sequence):
        try:
            pre_checkpoint = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
                manifest,
                binding,
                sequence=sequence,
            )
            pre_runtime = load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                manifest,
                binding,
                sequence=sequence,
            )
            successor = load_fast_paper_shadow_ledger_checkpoint_by_sequence(
                manifest,
                binding,
                sequence=sequence + 1,
            )
            successor_runtime = (
                load_fast_paper_shadow_runtime_state_by_checkpoint_sequence(
                    manifest,
                    binding,
                    sequence=sequence + 1,
                )
            )
        except Exception as exc:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics historical checkpoint/runtime read failed"
            ) from exc
        if (
            pre_checkpoint is None
            or pre_runtime is None
            or successor is None
            or successor_runtime is None
        ):
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics durable checkpoint/runtime history is incomplete"
            )

        if sequence in fresh:
            bindings = fresh[sequence]
            fingerprint = bindings["decision_evidence_fingerprint_sha256"]
            evidence = decisions.get(fingerprint)
            if evidence is None:
                raise FastPaperShadowTradeEconomicsError(
                    "shadow economics fresh source references missing decision evidence"
                )
            try:
                record = read_fast_paper_shadow_execution_input_source_record(
                    manifest,
                    execution_policy,
                    evidence,
                    source_root,
                    paper_checkpoint_sequence=pre_checkpoint.sequence,
                    paper_checkpoint_payload_sha256=pre_checkpoint.payload_sha256,
                    shadow_runtime_state_fingerprint_sha256=(
                        pre_runtime.state_fingerprint_sha256
                    ),
                )
                transition = reconstruct_fast_paper_shadow_decision(
                    manifest,
                    execution_policy,
                    binding,
                    pre_checkpoint,
                    pre_runtime,
                    record.execution_input,
                )
            except Exception as exc:
                raise FastPaperShadowTradeEconomicsError(
                    "shadow economics fresh transition reconstruction failed"
                ) from exc
            _require_fresh_successor(
                transition,
                successor,
                successor_runtime,
                evidence,
                execution_policy,
            )
            if transition.replayed:
                raise FastPaperShadowTradeEconomicsError(
                    "shadow economics durable fresh transition cannot be replayed"
                )

            assessment = fast_campaign_result_to_paper_assessment(
                evidence.decision,
                assessment_version=manifest.assessment_version,
                strategy_family=manifest.strategy_family,
                strategy_version=manifest.strategy_version,
            )
            if evidence.decision.action == "BUY":
                regime = record.execution_input.market_regime
                risk = record.execution_input.risk_context
                horizon = evidence.decision.selected_horizon_ms
                if type(regime) is not MarketRegime or risk is None:
                    raise FastPaperShadowTradeEconomicsError(
                        "shadow economics BUY source lacks regime/risk context"
                    )
                event_metadata[evidence.source_event_id] = _EntryMetadata(
                    source_event_id=evidence.source_event_id,
                    mint=evidence.feature_record.mint,
                    market_regime=regime,
                    selected_horizon_ms=_positive_int(
                        "selected BUY horizon",
                        horizon,
                    ),
                    selected_value_bps=_finite(
                        "selected BUY value",
                        evidence.decision.selected_value_bps,
                    ),
                    trading_capital_usd=_positive(
                        "BUY trading capital",
                        risk.trading_capital_usd,
                    ),
                )

            buy = transition.buy_result
            position = transition.position_result
            if buy is not None and buy.execution is not None:
                if buy.ledger_update is None:
                    raise FastPaperShadowTradeEconomicsError(
                        "shadow economics terminal BUY execution lacks ledger update"
                    )
                execution_inputs.append(
                    FastPaperExecutionEvidenceInput(
                        assessment=assessment,
                        execution=buy.execution,
                        ledger_update=buy.ledger_update,
                    )
                )
            if position is not None and position.execution is not None:
                if position.execution_ledger_update is None:
                    raise FastPaperShadowTradeEconomicsError(
                        "shadow economics terminal position execution lacks ledger update"
                    )
                execution_inputs.append(
                    FastPaperExecutionEvidenceInput(
                        assessment=position.applied_assessment,
                        execution=position.execution,
                        ledger_update=position.execution_ledger_update,
                    )
                )

            opened = _new_opened_position_id(
                pre_checkpoint,
                successor,
            )
            if opened is not None:
                metadata = event_metadata.get(evidence.source_event_id)
                if metadata is None:
                    raise FastPaperShadowTradeEconomicsError(
                        "shadow economics opening BUY lacks entry metadata"
                    )
                _record_open_position(
                    opened,
                    metadata,
                    entry_contexts,
                    position_metadata,
                )
            continue

        bindings = retries[sequence]
        if (
            bindings["paper_checkpoint_payload_sha256"]
            != pre_checkpoint.payload_sha256
            or bindings["shadow_runtime_state_fingerprint_sha256"]
            != pre_runtime.state_fingerprint_sha256
        ):
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics retry source historical binding mismatch"
            )
        try:
            retry_record = (
                read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint(
                    manifest,
                    binding,
                    execution_policy,
                    pre_checkpoint,
                    pre_runtime,
                    retry_root,
                )
            )
            transition = reconstruct_fast_paper_shadow_pending_buy_retry(
                manifest,
                execution_policy,
                binding,
                pre_checkpoint,
                pre_runtime,
                retry_record.retry_input,
            )
        except Exception as exc:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics pending BUY retry reconstruction failed"
            ) from exc
        _require_retry_successor(
            transition,
            pre_runtime,
            successor,
            successor_runtime,
            execution_policy,
        )
        buy = transition.buy_result
        if buy is None:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics retry transition lacks BUY result"
            )
        approval = pre_checkpoint.state.pending_buy
        if approval is None:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics retry pre-state lacks pending BUY approval"
            )
        if buy.execution is not None:
            if buy.ledger_update is None:
                raise FastPaperShadowTradeEconomicsError(
                    "shadow economics retry execution lacks ledger update"
                )
            execution_inputs.append(
                FastPaperExecutionEvidenceInput(
                    assessment=approval.assessment,
                    execution=buy.execution,
                    ledger_update=buy.ledger_update,
                )
            )
        opened = _new_opened_position_id(pre_checkpoint, successor)
        if opened is not None:
            metadata = event_metadata.get(retry_record.pending_source_event_id)
            if metadata is None:
                raise FastPaperShadowTradeEconomicsError(
                    "shadow economics retry opening lacks original learned entry metadata"
                )
            metadata = _EntryMetadata(
                source_event_id=metadata.source_event_id,
                mint=metadata.mint,
                market_regime=metadata.market_regime,
                selected_horizon_ms=metadata.selected_horizon_ms,
                selected_value_bps=metadata.selected_value_bps,
                trading_capital_usd=_positive(
                    "retry trading capital",
                    retry_record.retry_input.risk_context.trading_capital_usd,
                ),
            )
            _record_open_position(
                opened,
                metadata,
                entry_contexts,
                position_metadata,
            )

    try:
        capture = extract_fast_paper_evaluation_evidence(
            identity,
            tuple(entry_contexts),
            tuple(execution_inputs),
        )
    except Exception as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics E11 evidence adaptation failed"
        ) from exc
    return _Reconstruction(
        capture=capture,
        position_metadata=dict(position_metadata),
        final_checkpoint=final_checkpoint,
    )


def _decision_index(
    root: Path,
    *,
    manifest: object,
    until_unix_ms: int,
) -> dict[str, object]:
    by_fingerprint: dict[str, object] = {}
    source_sequences: set[int] = set()
    for path in sorted(root.glob("shadow-*.json")):
        if path.is_symlink() or not path.is_file():
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics decision evidence path is unsafe"
            )
        try:
            evidence = read_fast_paper_shadow_decision_evidence(path)
            validate_fast_paper_shadow_decision_evidence(evidence)
        except Exception as exc:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics decision evidence authentication failed"
            ) from exc
        if (
            evidence.release_source_sha != manifest.release_source_sha
            or evidence.manifest_fingerprint_sha256
            != manifest.manifest_fingerprint_sha256
            or evidence.champion_version != manifest.champion_version
            or evidence.champion_fingerprint_sha256
            != manifest.champion_fingerprint_sha256
            or evidence.action_policy_version != manifest.action_policy.version
        ):
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics decision runtime identity mismatch"
            )
        if evidence.source_sequence in source_sequences:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics decision source sequence is duplicated"
            )
        source_sequences.add(evidence.source_sequence)
        fp = evidence.evidence_fingerprint_sha256
        if fp in by_fingerprint:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics decision fingerprint is duplicated"
            )
        if evidence.as_of_unix_ms < until_unix_ms:
            by_fingerprint[fp] = evidence
    return by_fingerprint


def _fresh_source_index(root: Path) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for path in sorted(root.glob("*.json")):
        document = _canonical_document(path, "fresh execution source")
        if document.get("schema_name") != FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics fresh execution source schema is incompatible"
            )
        sequence = _non_negative_int(
            "fresh source checkpoint sequence",
            document.get("paper_checkpoint_sequence"),
        )
        if sequence in result:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics fresh source checkpoint sequence is duplicated"
            )
        result[sequence] = {
            "decision_evidence_fingerprint_sha256": _sha256(
                "fresh source decision fingerprint",
                document.get("decision_evidence_fingerprint_sha256"),
            ),
            "paper_checkpoint_payload_sha256": _sha256(
                "fresh source checkpoint fingerprint",
                document.get("paper_checkpoint_payload_sha256"),
            ),
            "shadow_runtime_state_fingerprint_sha256": _sha256(
                "fresh source runtime fingerprint",
                document.get("shadow_runtime_state_fingerprint_sha256"),
            ),
        }
    return result


def _retry_source_index(root: Path) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for path in sorted(root.glob("*.json")):
        document = _canonical_document(path, "pending BUY retry source")
        if document.get("schema_name") != FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics pending BUY retry source schema is incompatible"
            )
        sequence = _non_negative_int(
            "retry source checkpoint sequence",
            document.get("paper_checkpoint_sequence"),
        )
        if sequence in result:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics retry source checkpoint sequence is duplicated"
            )
        result[sequence] = {
            "paper_checkpoint_payload_sha256": _sha256(
                "retry source checkpoint fingerprint",
                document.get("paper_checkpoint_payload_sha256"),
            ),
            "shadow_runtime_state_fingerprint_sha256": _sha256(
                "retry source runtime fingerprint",
                document.get("shadow_runtime_state_fingerprint_sha256"),
            ),
        }
    return result


def _new_opened_position_id(pre_checkpoint: object, successor: object) -> str | None:
    before = pre_checkpoint.state.ledger.entries
    after = successor.state.ledger.entries
    if after[: len(before)] != before:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics successor ledger is not append-only"
        )
    new = after[len(before) :]
    if len(new) > 1:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics transition appended multiple ledger entries"
        )
    if not new:
        return None
    entry = new[0]
    if entry.ledger_reason_code is not PaperLedgerReasonCode.POSITION_OPENED:
        return None
    if not isinstance(entry.position_id, str) or not entry.position_id:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics opening journal lacks position id"
        )
    return entry.position_id


def _record_open_position(
    position_id: str,
    metadata: _EntryMetadata,
    contexts: list[FastPaperEntryEvaluationContext],
    positions: dict[str, _EntryMetadata],
) -> None:
    if position_id in positions:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics position entry metadata is duplicated"
        )
    if any(value.source_event_id == metadata.source_event_id for value in contexts):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics entry context source event is duplicated"
        )
    contexts.append(
        FastPaperEntryEvaluationContext(
            source_event_id=metadata.source_event_id,
            market_regime=metadata.market_regime,
        )
    )
    positions[position_id] = metadata


def _require_fresh_successor(
    transition: object,
    successor: object,
    successor_runtime: object,
    evidence: object,
    execution_policy: object,
) -> None:
    if successor.state != transition.next_paper_state:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics fresh successor PAPER state differs from reconstruction"
        )
    if (
        successor_runtime.paper_checkpoint_sequence != successor.sequence
        or successor_runtime.paper_checkpoint_payload_sha256
        != successor.payload_sha256
        or successor_runtime.market_positions != transition.next_market_positions
        or successor_runtime.pending_buy != transition.next_pending_buy
        or successor_runtime.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics fresh successor runtime differs from reconstruction"
        )
    actual = (
        successor_runtime.last_processed_source_sequence,
        successor_runtime.last_processed_source_event_id,
        successor_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    expected = (
        evidence.source_sequence,
        evidence.source_event_id,
        evidence.evidence_fingerprint_sha256,
    )
    if actual != expected:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics fresh successor processed identity mismatch"
        )


def _require_retry_successor(
    transition: object,
    pre_runtime: object,
    successor: object,
    successor_runtime: object,
    execution_policy: object,
) -> None:
    if successor.state != transition.next_paper_state:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics retry successor PAPER state differs from reconstruction"
        )
    if (
        successor_runtime.paper_checkpoint_sequence != successor.sequence
        or successor_runtime.paper_checkpoint_payload_sha256
        != successor.payload_sha256
        or successor_runtime.market_positions != transition.next_market_positions
        or successor_runtime.pending_buy != transition.next_pending_buy
        or successor_runtime.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics retry successor runtime differs from reconstruction"
        )
    actual = (
        successor_runtime.last_processed_source_sequence,
        successor_runtime.last_processed_source_event_id,
        successor_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    expected = (
        pre_runtime.last_processed_source_sequence,
        pre_runtime.last_processed_source_event_id,
        pre_runtime.last_processed_decision_evidence_fingerprint_sha256,
    )
    if actual != expected:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics retry advanced learned decision cursor"
        )


def _horizon_performance(
    trades: tuple[object, ...],
    metadata: Mapping[str, _EntryMetadata],
    policy: TradingEvaluationPolicy,
    candidate_version: str,
) -> list[dict[str, object]]:
    groups: dict[int, list[object]] = {}
    for trade in trades:
        horizon = metadata[trade.position_id].selected_horizon_ms
        groups.setdefault(horizon, []).append(trade)
    values: list[dict[str, object]] = []
    for horizon in sorted(groups):
        report = evaluate_trading_performance(
            tuple(groups[horizon]),
            (),
            policy,
            candidate_version,
        )
        values.append(
            {
                "selected_horizon_ms": horizon,
                "metrics": asdict(report.metrics),
            }
        )
    if sum(value["metrics"]["trade_count"] for value in values) != len(trades):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics horizon trade counts do not reconcile"
        )
    return values


def _expected_realized_calibration(
    trades: tuple[object, ...],
    metadata: Mapping[str, _EntryMetadata],
) -> dict[str, object]:
    expected: list[float] = []
    realized: list[float] = []
    errors: list[float] = []
    absolute: list[float] = []
    for trade in trades:
        exp = metadata[trade.position_id].selected_value_bps
        real = trade.net_pnl_usd / trade.entry_notional_usd * 10_000.0
        error = real - exp
        expected.append(exp)
        realized.append(real)
        errors.append(error)
        absolute.append(abs(error))
    return {
        "observation_count": len(trades),
        "expected_mean_bps": _mean_or_none(expected),
        "realized_mean_bps": _mean_or_none(realized),
        "mean_error_bps": _mean_or_none(errors),
        "mean_absolute_error_bps": _mean_or_none(absolute),
        "absolute_error_p50_bps": _percentile_or_none(absolute, 50),
        "absolute_error_p95_bps": _percentile_or_none(absolute, 95),
    }


def _loss_tail(trades: tuple[object, ...]) -> dict[str, object]:
    losses = [trade for trade in trades if trade.net_pnl_usd < 0.0]
    magnitudes = [abs(trade.net_pnl_usd) for trade in losses]
    return_magnitudes = [
        abs(trade.net_pnl_usd / trade.entry_notional_usd * 10_000.0)
        for trade in losses
    ]
    return {
        "loss_count": len(losses),
        "worst_net_pnl_usd": (
            None if not losses else min(trade.net_pnl_usd for trade in losses)
        ),
        "worst_net_return_bps": (
            None
            if not losses
            else min(
                trade.net_pnl_usd / trade.entry_notional_usd * 10_000.0
                for trade in losses
            )
        ),
        "absolute_loss_p95_usd": _percentile_or_none(magnitudes, 95),
        "absolute_loss_p95_bps": _percentile_or_none(
            return_magnitudes,
            95,
        ),
    }


def _entry_efficiency(
    trades: tuple[object, ...],
    executions: tuple[object, ...],
) -> dict[str, object]:
    slippage: list[float] = []
    explicit: list[float] = []
    for trade in trades:
        buys = [
            value
            for value in executions
            if value.position_id == trade.position_id
            and value.side.value == "BUY"
            and value.filled_notional_usd is not None
        ]
        buys.sort(key=lambda value: value.ledger_sequence)
        if not buys:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics evaluated trade lacks opening BUY execution"
            )
        opener = buys[0]
        if (
            opener.signed_slippage_usd is None
            or opener.filled_notional_usd is None
            or opener.filled_notional_usd <= 0.0
        ):
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics opening BUY fill evidence is incomplete"
            )
        slippage.append(
            opener.signed_slippage_usd
            / opener.filled_notional_usd
            * 10_000.0
        )
        explicit.append(
            opener.explicit_cost_usd
            / opener.filled_notional_usd
            * 10_000.0
        )
    return {
        "observation_count": len(trades),
        "signed_slippage_bps": _summary(slippage),
        "explicit_cost_bps": _summary(explicit),
    }


def _exit_timing(
    trades: tuple[object, ...],
    executions: tuple[object, ...],
    closures: tuple[object, ...],
    metadata: Mapping[str, _EntryMetadata],
) -> dict[str, object]:
    booking: list[float] = []
    holding: list[float] = []
    horizon_delta: list[float] = []
    closure_by_position = {value.position_id: value for value in closures}
    for trade in trades:
        closure = closure_by_position.get(trade.position_id)
        if closure is None:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics evaluated trade lacks closure evidence"
            )
        closing = [
            value
            for value in executions
            if value.position_id == trade.position_id
            and value.ledger_sequence == closure.closing_ledger_sequence
        ]
        if len(closing) != 1:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics closure lacks one exact closing execution"
            )
        close = closing[0]
        latency = close.booked_at_unix_ms - close.evaluated_at_unix_ms
        if latency < 0:
            raise FastPaperShadowTradeEconomicsError(
                "shadow economics close booking predates decision evaluation"
            )
        duration = trade.closed_at_unix_ms - trade.opened_at_unix_ms
        booking.append(float(latency))
        holding.append(float(duration))
        horizon_delta.append(
            float(duration - metadata[trade.position_id].selected_horizon_ms)
        )
    return {
        "observation_count": len(trades),
        "decision_to_close_booking_ms": _summary(booking),
        "holding_duration_ms": _summary(holding),
        "holding_minus_selected_horizon_ms": _summary(horizon_delta),
    }


def _entry_capital_utilization(
    trades: tuple[object, ...],
    metadata: Mapping[str, _EntryMetadata],
) -> dict[str, object]:
    values = [
        trade.entry_notional_usd
        / metadata[trade.position_id].trading_capital_usd
        * 100.0
        for trade in trades
    ]
    return {
        "observation_count": len(values),
        "entry_notional_to_trading_capital_pct": _summary(values),
    }


def _read_sample_proof(path: str | Path) -> dict[str, object]:
    document = _canonical_document(Path(path), "FL11.1 sample proof")
    if frozenset(document) != _SAMPLE_REPORT_KEYS:
        raise FastPaperShadowTradeEconomicsError(
            "FL11.1 sample proof has unknown or missing fields"
        )
    fingerprint = document.get("report_fingerprint_sha256")
    material = dict(document)
    material.pop("report_fingerprint_sha256", None)
    _sha256("sample proof fingerprint", fingerprint)
    if fingerprint != hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest():
        raise FastPaperShadowTradeEconomicsError(
            "FL11.1 sample proof fingerprint mismatch"
        )
    if (
        document.get("schema_name")
        != FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_NAME
        or document.get("schema_version")
        != FAST_PAPER_SHADOW_SAMPLE_PROOF_SCHEMA_VERSION
    ):
        raise FastPaperShadowTradeEconomicsError(
            "FL11.1 sample proof schema is incompatible"
        )
    if document.get("decision") != "SUFFICIENT_SAMPLE":
        raise FastPaperShadowTradeEconomicsError(
            "FL11.2a requires FL11.1 SUFFICIENT_SAMPLE"
        )
    for name in (
        "promotion_authority",
        "production_paper_cutover",
        "signing_submission_authority",
    ):
        if document.get(name) != "NOT_GRANTED":
            raise FastPaperShadowTradeEconomicsError(
                "FL11.1 sample proof authority boundary is incompatible"
            )
    if document.get("live_authority") != "DISABLED":
        raise FastPaperShadowTradeEconomicsError(
            "FL11.1 sample proof LIVE boundary is incompatible"
        )
    return document


def _require_sample_matches(
    sample: Mapping[str, object],
    *,
    manifest: object,
    binding: object,
    expected_release_sha: str,
    since_unix_ms: int,
    until_unix_ms: int,
) -> None:
    expected = {
        "release_source_sha": expected_release_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "action_policy_version": manifest.action_policy.version,
        "binding_fingerprint_sha256": binding.binding_fingerprint_sha256,
        "window_since_unix_ms": since_unix_ms,
        "window_until_unix_ms": until_unix_ms,
    }
    for name, value in expected.items():
        if sample.get(name) != value:
            raise FastPaperShadowTradeEconomicsError(
                f"FL11.1 sample proof {name} mismatch"
            )


def canonical_fast_paper_shadow_trade_economics(
    document: Mapping[str, object],
) -> str:
    if not isinstance(document, Mapping):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics document must be a mapping"
        )
    try:
        return _canonical(dict(document))
    except (TypeError, ValueError) as exc:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics document is not canonicalizable"
        ) from exc


def _finalize(material: Mapping[str, object]) -> dict[str, object]:
    document = dict(material)
    if "report_fingerprint_sha256" in document:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics material may not predefine fingerprint"
        )
    return {
        **document,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(document).encode("utf-8")
        ).hexdigest(),
    }


def _canonical_document(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise FastPaperShadowTradeEconomicsError(
            f"{label} must be a regular non-symlink file"
        )
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FastPaperShadowTradeEconomicsError(
            f"{label} is malformed"
        ) from exc
    if not isinstance(document, dict) or payload != _canonical(document):
        raise FastPaperShadowTradeEconomicsError(
            f"{label} must use canonical JSON"
        )
    return document


def _directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise FastPaperShadowTradeEconomicsError(
            f"shadow economics {label} directory must be regular and non-symlink"
        )
    return root


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "mean": None,
            "p50": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    for value in values:
        _finite("summary value", value)
    ordered = sorted(values)
    return {
        "mean": math.fsum(ordered) / len(ordered),
        "p50": _nearest_rank(ordered, 50),
        "p95": _nearest_rank(ordered, 95),
        "min": ordered[0],
        "max": ordered[-1],
    }


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return math.fsum(values) / len(values)


def _percentile_or_none(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    return _nearest_rank(sorted(values), percentile)


def _nearest_rank(values: list[float], percentile: int) -> float:
    if not values:
        raise FastPaperShadowTradeEconomicsError(
            "nearest-rank percentile requires values"
        )
    rank = max(1, math.ceil(percentile * len(values) / 100.0))
    return float(values[min(rank - 1, len(values) - 1)])


def _release_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics release SHA is invalid"
        )
    return value


def _window(since: object, until: object) -> tuple[int, int]:
    if (
        isinstance(since, bool)
        or not isinstance(since, int)
        or since < 0
        or isinstance(until, bool)
        or not isinstance(until, int)
        or until <= since
    ):
        raise FastPaperShadowTradeEconomicsError(
            "shadow economics window is invalid"
        )
    return since, until


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise FastPaperShadowTradeEconomicsError(
            f"{name} must be lowercase SHA-256"
        )
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperShadowTradeEconomicsError(
            f"{name} must be non-negative integer"
        )
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FastPaperShadowTradeEconomicsError(
            f"{name} must be positive integer"
        )
    return value


def _finite(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FastPaperShadowTradeEconomicsError(
            f"{name} must be finite"
        )
    return float(value)


def _positive(name: str, value: object) -> float:
    result = _finite(name, value)
    if result <= 0.0:
        raise FastPaperShadowTradeEconomicsError(
            f"{name} must be strictly positive"
        )
    return result


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-trade-economics"
    )
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--execution-policy-path", required=True)
    parser.add_argument("--ledger-database-path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision-evidence-directory", required=True)
    parser.add_argument("--execution-source-directory", required=True)
    parser.add_argument("--pending-buy-retry-source-directory", required=True)
    parser.add_argument("--sample-proof-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--since-unix-ms", type=int, required=True)
    parser.add_argument("--until-unix-ms", type=int, required=True)
    parser.add_argument("--evaluation-policy-version", required=True)
    parser.add_argument(
        "--calibration-bucket-count",
        type=int,
        required=True,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = collect_fast_paper_shadow_trade_economics(
            manifest_path=args.manifest_path,
            execution_policy_path=args.execution_policy_path,
            ledger_database_path=args.ledger_database_path,
            run_id=args.run_id,
            decision_evidence_directory=args.decision_evidence_directory,
            execution_source_directory=args.execution_source_directory,
            pending_buy_retry_source_directory=(
                args.pending_buy_retry_source_directory
            ),
            sample_proof_path=args.sample_proof_path,
            expected_release_sha=args.expected_release_sha,
            since_unix_ms=args.since_unix_ms,
            until_unix_ms=args.until_unix_ms,
            evaluation_policy_version=args.evaluation_policy_version,
            calibration_bucket_count=args.calibration_bucket_count,
        )
    except (FastPaperShadowTradeEconomicsError, ValueError) as exc:
        print(
            canonical_fast_paper_shadow_trade_economics(
                {
                    "schema_name": (
                        "shreks.fast_paper_shadow_trade_economics_failure"
                    ),
                    "schema_version": (
                        FAST_PAPER_SHADOW_TRADE_ECONOMICS_SCHEMA_VERSION
                    ),
                    "state": "FAILED",
                    "error_type": type(exc).__name__,
                    "promotion_authority": "NOT_GRANTED",
                    "production_paper_cutover": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1
    print(canonical_fast_paper_shadow_trade_economics(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
