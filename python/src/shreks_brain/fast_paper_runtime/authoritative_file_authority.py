from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.paper import PaperPositionState, derive_paper_risk_accounting_facts
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext

from .authoritative_coordinator import FastPaperAuthoritativeExecutionAuthority
from .authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionBootstrap,
    _require_exact_pair,
    fast_paper_authoritative_decision_position,
)
from .models import FastPaperRuntimeManifest
from .persisted_quotes import FastPaperShadowReductionRead
from .shadow import (
    FastPaperShadowDecisionEvidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import FastPaperShadowExecutionInput
from .shadow_execution_source import (
    _canonical_json,
    _decode_entry_authority,
    _decode_risk_context,
    _encode_entry_authority,
    _encode_risk_context,
    _float_tag,
    _fsync_directory,
    _reject_duplicate_pairs,
    _reject_json_constant,
    _require_exact_int,
    _require_exact_text,
    _require_sha256_value,
)
from .shadow_executor import (
    FastPaperShadowPendingBuyRetryInput,
    _validate_pending_retry_quote,
)
from .shadow_pending_buy_retry_source import (
    _decode_quote,
    _encode_quote,
    _record_filename as _pending_retry_filename,
)
from .shadow_quote_usd_source import (
    _record_filename as _quote_usd_filename,
    read_fast_paper_shadow_quote_usd_source_record,
)
from .shadow_reduction_source import (
    _record_filename as _reduction_filename,
)


FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_buy_authority_source"
)
FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION = 1
FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_reduction_source"
)
FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_VERSION = 1
FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_pending_buy_retry_source"
)
FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION = 1

_BUY_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "runtime_state_fingerprint_sha256",
        "decision_evidence_fingerprint_sha256",
        "source_event_id",
        "market_key",
        "mint",
        "quote_mint",
        "evaluated_at_unix_ms",
        "risk_day_started_at_unix_ms",
        "source_observed_at_unix_ms",
        "entry_authority",
        "risk_context",
        "market_regime",
        "source_version",
        "source_fingerprint_sha256",
        "record_fingerprint_sha256",
    }
)
_REDUCTION_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "runtime_state_fingerprint_sha256",
        "market_key",
        "position_id",
        "mint",
        "current_exposure_fraction_hex",
        "current_base_quantity_raw",
        "exit_input_amount_raw",
        "reduction_reads",
        "record_fingerprint_sha256",
    }
)
_REDUCTION_READ_KEYS = frozenset(
    {"target_exposure_fraction_hex", "input_amount_raw"}
)
_RETRY_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "runtime_state_fingerprint_sha256",
        "decision_evidence_fingerprint_sha256",
        "pending_source_event_id",
        "pending_market_key",
        "pending_mint",
        "risk_day_started_at_unix_ms",
        "source_observed_at_unix_ms",
        "retry_input",
        "record_fingerprint_sha256",
    }
)
_RETRY_INPUT_KEYS = frozenset(
    {
        "evaluated_at_unix_ms",
        "quote",
        "risk_context",
        "quote_usd_evidence",
    }
)


class FastPaperAuthoritativeAuthorityUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeBuyAuthoritySourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    runtime_state_fingerprint_sha256: str
    decision_evidence_fingerprint_sha256: str
    source_event_id: str
    market_key: str
    mint: str
    quote_mint: str
    evaluated_at_unix_ms: int
    risk_day_started_at_unix_ms: int
    source_observed_at_unix_ms: int
    entry_authority: FastCampaignPaperEntryAuthority
    risk_context: RiskContext
    market_regime: MarketRegime
    source_version: str
    source_fingerprint_sha256: str
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_NAME
            or type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "authoritative BUY authority source schema is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "runtime_state_fingerprint_sha256",
            "decision_evidence_fingerprint_sha256",
            "source_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256_value(name, getattr(self, name))
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        for name in (
            "source_event_id",
            "market_key",
            "mint",
            "quote_mint",
            "source_version",
        ):
            _require_exact_text(name, getattr(self, name))
        for name in (
            "evaluated_at_unix_ms",
            "risk_day_started_at_unix_ms",
            "source_observed_at_unix_ms",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if type(self.entry_authority) is not FastCampaignPaperEntryAuthority:
            raise ValueError(
                "entry_authority must be exact FastCampaignPaperEntryAuthority"
            )
        if type(self.risk_context) is not RiskContext:
            raise ValueError("risk_context must be exact RiskContext")
        if type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be exact MarketRegime")
        if self.risk_day_started_at_unix_ms > self.evaluated_at_unix_ms:
            raise ValueError(
                "authoritative BUY risk day cannot start after evaluation"
            )
        if self.source_observed_at_unix_ms > self.evaluated_at_unix_ms:
            raise ValueError(
                "authoritative BUY source observation cannot be from the future"
            )
        if _buy_record_fingerprint(self) != self.record_fingerprint_sha256:
            raise ValueError(
                "authoritative BUY authority source fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeReductionSourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    runtime_state_fingerprint_sha256: str
    market_key: str
    position_id: str
    mint: str
    current_exposure_fraction: float
    current_base_quantity_raw: int
    exit_input_amount_raw: int
    reduction_reads: tuple[FastPaperShadowReductionRead, ...]
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_NAME
            or type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "authoritative reduction source schema is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "runtime_state_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256_value(name, getattr(self, name))
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        for name in ("market_key", "position_id", "mint"):
            _require_exact_text(name, getattr(self, name))
        _require_exposure(
            "current_exposure_fraction",
            self.current_exposure_fraction,
        )
        _require_positive_int(
            "current_base_quantity_raw",
            self.current_base_quantity_raw,
        )
        _require_positive_int(
            "exit_input_amount_raw",
            self.exit_input_amount_raw,
        )
        if self.exit_input_amount_raw != self.current_base_quantity_raw:
            raise ValueError(
                "authoritative full-exit input must equal current raw inventory"
            )
        if (
            not isinstance(self.reduction_reads, tuple)
            or not all(
                type(value) is FastPaperShadowReductionRead
                for value in self.reduction_reads
            )
        ):
            raise ValueError(
                "reduction_reads must contain exact FastPaperShadowReductionRead values"
            )
        previous = -1.0
        for value in self.reduction_reads:
            target = value.target_exposure_fraction
            if target >= self.current_exposure_fraction or target <= previous:
                raise ValueError(
                    "authoritative reduction targets must be strictly increasing below current exposure"
                )
            previous = target
        if (
            _reduction_record_fingerprint(self)
            != self.record_fingerprint_sha256
        ):
            raise ValueError(
                "authoritative reduction source fingerprint mismatch"
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativePendingBuyRetrySourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    runtime_state_fingerprint_sha256: str
    decision_evidence_fingerprint_sha256: str
    pending_source_event_id: str
    pending_market_key: str
    pending_mint: str
    risk_day_started_at_unix_ms: int
    source_observed_at_unix_ms: int
    retry_input: FastPaperShadowPendingBuyRetryInput
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME
            or type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "authoritative pending BUY retry source schema is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "runtime_state_fingerprint_sha256",
            "decision_evidence_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256_value(name, getattr(self, name))
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        for name in (
            "pending_source_event_id",
            "pending_market_key",
            "pending_mint",
        ):
            _require_exact_text(name, getattr(self, name))
        for name in (
            "risk_day_started_at_unix_ms",
            "source_observed_at_unix_ms",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if type(self.retry_input) is not FastPaperShadowPendingBuyRetryInput:
            raise ValueError(
                "retry_input must be exact FastPaperShadowPendingBuyRetryInput"
            )
        if (
            _retry_record_fingerprint(self)
            != self.record_fingerprint_sha256
        ):
            raise ValueError(
                "authoritative pending BUY retry source fingerprint mismatch"
            )


def build_fast_paper_authoritative_buy_authority_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    entry_authority: FastCampaignPaperEntryAuthority,
    risk_context: RiskContext,
    market_regime: MarketRegime,
    *,
    risk_day_started_at_unix_ms: int,
    source_observed_at_unix_ms: int,
    source_version: str,
    source_fingerprint_sha256: str,
) -> FastPaperAuthoritativeBuyAuthoritySourceRecord:
    _require_bootstrap_pair(manifest, bootstrap)
    _require_decision(manifest, decision_evidence)
    if decision_evidence.decision.action != "BUY":
        raise ValueError(
            "authoritative BUY authority source requires learned BUY"
        )
    if decision_evidence.position.kind != "FLAT":
        raise ValueError(
            "authoritative BUY authority source requires FLAT posture"
        )
    if (
        fast_paper_authoritative_decision_position(
            bootstrap.runtime_state,
            decision_evidence.market_key,
        )
        != decision_evidence.position
    ):
        raise ValueError(
            "authoritative BUY decision posture does not match durable state"
        )
    _require_non_negative_int(
        "risk_day_started_at_unix_ms",
        risk_day_started_at_unix_ms,
    )
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )
    _require_exact_text("source_version", source_version)
    _require_sha256_value(
        "source_fingerprint_sha256",
        source_fingerprint_sha256,
    )
    if risk_day_started_at_unix_ms > decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative BUY risk day cannot start after evaluation"
        )
    if source_observed_at_unix_ms > decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative BUY source observation cannot be from the future"
        )
    if (
        source_observed_at_unix_ms
        < decision_evidence.entry_quote.observed_at_unix_ms
    ):
        raise ValueError(
            "authoritative BUY source observation predates sealed entry quote"
        )
    if type(entry_authority) is not FastCampaignPaperEntryAuthority:
        raise ValueError(
            "entry_authority must be exact FastCampaignPaperEntryAuthority"
        )
    if type(risk_context) is not RiskContext:
        raise ValueError("risk_context must be exact RiskContext")
    if type(market_regime) is not MarketRegime:
        raise ValueError("market_regime must be exact MarketRegime")
    quote = decision_evidence.entry_quote
    if (
        quote.state != "EXECUTABLE"
        or quote.reference_price_quote is None
        or entry_authority.mint != quote.mint
        or entry_authority.quote_mint != quote.quote_mint
        or entry_authority.decision_executable_entry_price_quote
        != quote.reference_price_quote
        or entry_authority.intended_base_quantity
        != quote.quoted_base_quantity
    ):
        raise ValueError(
            "authoritative BUY entry authority conflicts with sealed entry quote"
        )
    if risk_context.as_of_unix_ms != decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative BUY risk context must use decision evaluation time"
        )
    _require_risk_matches_checkpoint(
        bootstrap.checkpoint,
        risk_context,
        day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )
    values = {
        "schema_name": (
            FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_AUTHORITATIVE_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION
        ),
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "binding_fingerprint_sha256": (
            bootstrap.binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            bootstrap.execution_policy.policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": bootstrap.checkpoint.sequence,
        "paper_checkpoint_payload_sha256": bootstrap.checkpoint.payload_sha256,
        "runtime_state_fingerprint_sha256": (
            bootstrap.runtime_state.state_fingerprint_sha256
        ),
        "decision_evidence_fingerprint_sha256": (
            decision_evidence.evidence_fingerprint_sha256
        ),
        "source_event_id": decision_evidence.source_event_id,
        "market_key": decision_evidence.market_key,
        "mint": quote.mint,
        "quote_mint": quote.quote_mint,
        "evaluated_at_unix_ms": decision_evidence.evaluated_at_unix_ms,
        "risk_day_started_at_unix_ms": risk_day_started_at_unix_ms,
        "source_observed_at_unix_ms": source_observed_at_unix_ms,
        "entry_authority": entry_authority,
        "risk_context": risk_context,
        "market_regime": market_regime,
        "source_version": source_version,
        "source_fingerprint_sha256": source_fingerprint_sha256,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_buy_document_values(values))
    ).hexdigest()
    return FastPaperAuthoritativeBuyAuthoritySourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def build_fast_paper_authoritative_reduction_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    market_key: str,
    reduction_reads: tuple[FastPaperShadowReductionRead, ...],
) -> FastPaperAuthoritativeReductionSourceRecord:
    _require_bootstrap_pair(manifest, bootstrap)
    _require_exact_text("market_key", market_key)
    mapping = _market_mapping(bootstrap, market_key)
    _require_open_position(
        bootstrap,
        position_id=mapping.position_id,
        mint=mapping.mint,
    )
    expected_targets = tuple(
        target
        for target in manifest.action_policy.reduce_target_exposure_candidates
        if target < mapping.current_exposure_fraction
    )
    actual_targets = tuple(
        value.target_exposure_fraction for value in reduction_reads
    )
    if actual_targets != expected_targets:
        raise ValueError(
            "authoritative reduction source must cover complete eligible target set"
        )
    values = {
        "schema_name": (
            FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_AUTHORITATIVE_REDUCTION_SOURCE_SCHEMA_VERSION
        ),
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "binding_fingerprint_sha256": (
            bootstrap.binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            bootstrap.execution_policy.policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": bootstrap.checkpoint.sequence,
        "paper_checkpoint_payload_sha256": bootstrap.checkpoint.payload_sha256,
        "runtime_state_fingerprint_sha256": (
            bootstrap.runtime_state.state_fingerprint_sha256
        ),
        "market_key": mapping.market_key,
        "position_id": mapping.position_id,
        "mint": mapping.mint,
        "current_exposure_fraction": mapping.current_exposure_fraction,
        "current_base_quantity_raw": mapping.current_base_quantity_raw,
        "exit_input_amount_raw": mapping.current_base_quantity_raw,
        "reduction_reads": reduction_reads,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_reduction_document_values(values))
    ).hexdigest()
    return FastPaperAuthoritativeReductionSourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def build_fast_paper_authoritative_pending_buy_retry_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    retry_input: FastPaperShadowPendingBuyRetryInput,
    *,
    risk_day_started_at_unix_ms: int,
    source_observed_at_unix_ms: int,
) -> FastPaperAuthoritativePendingBuyRetrySourceRecord:
    _require_bootstrap_pair(manifest, bootstrap)
    _require_decision(manifest, decision_evidence)
    approval = bootstrap.checkpoint.state.pending_buy
    if approval is None:
        raise ValueError(
            "authoritative pending BUY retry source requires durable pending BUY"
        )
    state = bootstrap.runtime_state
    identity = (
        state.last_processed_source_sequence,
        state.last_processed_source_event_id,
        state.last_processed_decision_evidence_fingerprint_sha256,
    )
    expected = (
        decision_evidence.source_sequence,
        decision_evidence.source_event_id,
        decision_evidence.evidence_fingerprint_sha256,
    )
    if identity != expected or decision_evidence.decision.action != "BUY":
        raise ValueError(
            "authoritative pending BUY retry original decision identity mismatch"
        )
    if (
        approval.assessment.source_event_id != decision_evidence.source_event_id
        or approval.assessment.market_key != decision_evidence.market_key
        or approval.mint != decision_evidence.entry_quote.mint
    ):
        raise ValueError(
            "authoritative pending BUY approval conflicts with original decision"
        )
    _require_non_negative_int(
        "risk_day_started_at_unix_ms",
        risk_day_started_at_unix_ms,
    )
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )
    if risk_day_started_at_unix_ms > retry_input.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative pending BUY retry risk day starts after evaluation"
        )
    if retry_input.evaluated_at_unix_ms < bootstrap.checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "authoritative pending BUY retry predates durable pending state"
        )
    if source_observed_at_unix_ms > retry_input.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative pending BUY retry source observation is from the future"
        )
    if source_observed_at_unix_ms < max(
        retry_input.quote.observed_at_unix_ms,
        retry_input.quote_usd_evidence.observed_at_unix_ms,
    ):
        raise ValueError(
            "authoritative pending BUY retry source observation predates quote evidence"
        )
    _validate_pending_retry_quote(
        manifest,
        approval,
        retry_input,
        minimum_observed_at_unix_ms=bootstrap.checkpoint.state.as_of_unix_ms,
    )
    _require_risk_matches_checkpoint(
        bootstrap.checkpoint,
        retry_input.risk_context,
        day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )
    values = {
        "schema_name": (
            FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_AUTHORITATIVE_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION
        ),
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "binding_fingerprint_sha256": (
            bootstrap.binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            bootstrap.execution_policy.policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": bootstrap.checkpoint.sequence,
        "paper_checkpoint_payload_sha256": bootstrap.checkpoint.payload_sha256,
        "runtime_state_fingerprint_sha256": (
            bootstrap.runtime_state.state_fingerprint_sha256
        ),
        "decision_evidence_fingerprint_sha256": (
            decision_evidence.evidence_fingerprint_sha256
        ),
        "pending_source_event_id": decision_evidence.source_event_id,
        "pending_market_key": decision_evidence.market_key,
        "pending_mint": approval.mint,
        "risk_day_started_at_unix_ms": risk_day_started_at_unix_ms,
        "source_observed_at_unix_ms": source_observed_at_unix_ms,
        "retry_input": retry_input,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_retry_document_values(values))
    ).hexdigest()
    return FastPaperAuthoritativePendingBuyRetrySourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_authoritative_buy_authority_source_record(
    record: FastPaperAuthoritativeBuyAuthoritySourceRecord,
    directory: str | Path,
) -> Path:
    return _write_record(
        record,
        directory,
        f"{record.decision_evidence_fingerprint_sha256}.json",
        _buy_document,
    )


def write_fast_paper_authoritative_reduction_source_record(
    record: FastPaperAuthoritativeReductionSourceRecord,
    directory: str | Path,
) -> Path:
    return _write_record(
        record,
        directory,
        _reduction_filename(
            record.runtime_state_fingerprint_sha256,
            record.market_key,
        ),
        _reduction_document,
    )


def write_fast_paper_authoritative_pending_buy_retry_source_record(
    record: FastPaperAuthoritativePendingBuyRetrySourceRecord,
    directory: str | Path,
) -> Path:
    return _write_record(
        record,
        directory,
        _pending_retry_filename(
            record.runtime_state_fingerprint_sha256,
            record.pending_source_event_id,
        ),
        _retry_document,
    )


def read_fast_paper_authoritative_buy_authority_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    directory: str | Path,
) -> FastPaperAuthoritativeBuyAuthoritySourceRecord:
    root = _require_directory(directory, "authoritative BUY authority source")
    path = root / f"{decision_evidence.evidence_fingerprint_sha256}.json"
    document = _read_document(path, _BUY_KEYS, "authoritative BUY authority")
    try:
        entry = _decode_entry_authority(document["entry_authority"])
        risk = _decode_risk_context(document["risk_context"])
        if entry is None or risk is None:
            raise ValueError("BUY authority requires entry and risk facts")
        record = FastPaperAuthoritativeBuyAuthoritySourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
            binding_fingerprint_sha256=document[
                "binding_fingerprint_sha256"
            ],
            execution_policy_fingerprint_sha256=document[
                "execution_policy_fingerprint_sha256"
            ],
            paper_checkpoint_sequence=document[
                "paper_checkpoint_sequence"
            ],
            paper_checkpoint_payload_sha256=document[
                "paper_checkpoint_payload_sha256"
            ],
            runtime_state_fingerprint_sha256=document[
                "runtime_state_fingerprint_sha256"
            ],
            decision_evidence_fingerprint_sha256=document[
                "decision_evidence_fingerprint_sha256"
            ],
            source_event_id=document["source_event_id"],
            market_key=document["market_key"],
            mint=document["mint"],
            quote_mint=document["quote_mint"],
            evaluated_at_unix_ms=document["evaluated_at_unix_ms"],
            risk_day_started_at_unix_ms=document[
                "risk_day_started_at_unix_ms"
            ],
            source_observed_at_unix_ms=document[
                "source_observed_at_unix_ms"
            ],
            entry_authority=entry,
            risk_context=risk,
            market_regime=MarketRegime(
                _require_exact_text(
                    "market_regime",
                    document["market_regime"],
                )
            ),
            source_version=document["source_version"],
            source_fingerprint_sha256=document[
                "source_fingerprint_sha256"
            ],
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"authoritative BUY authority source content is incompatible: {exc}"
        ) from exc
    expected = build_fast_paper_authoritative_buy_authority_source_record(
        manifest,
        bootstrap,
        decision_evidence,
        record.entry_authority,
        record.risk_context,
        record.market_regime,
        risk_day_started_at_unix_ms=record.risk_day_started_at_unix_ms,
        source_observed_at_unix_ms=record.source_observed_at_unix_ms,
        source_version=record.source_version,
        source_fingerprint_sha256=record.source_fingerprint_sha256,
    )
    if record != expected:
        raise ValueError(
            "authoritative BUY authority source does not match current state"
        )
    return record


def read_fast_paper_authoritative_reduction_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    market_key: str,
    directory: str | Path,
) -> FastPaperAuthoritativeReductionSourceRecord:
    root = _require_directory(directory, "authoritative reduction source")
    path = root / _reduction_filename(
        bootstrap.runtime_state.state_fingerprint_sha256,
        market_key,
    )
    document = _read_document(
        path,
        _REDUCTION_KEYS,
        "authoritative reduction source",
    )
    try:
        record = FastPaperAuthoritativeReductionSourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
            binding_fingerprint_sha256=document[
                "binding_fingerprint_sha256"
            ],
            execution_policy_fingerprint_sha256=document[
                "execution_policy_fingerprint_sha256"
            ],
            paper_checkpoint_sequence=document[
                "paper_checkpoint_sequence"
            ],
            paper_checkpoint_payload_sha256=document[
                "paper_checkpoint_payload_sha256"
            ],
            runtime_state_fingerprint_sha256=document[
                "runtime_state_fingerprint_sha256"
            ],
            market_key=document["market_key"],
            position_id=document["position_id"],
            mint=document["mint"],
            current_exposure_fraction=_decode_float_hex(
                "current_exposure_fraction_hex",
                document["current_exposure_fraction_hex"],
            ),
            current_base_quantity_raw=_decode_positive_int_text(
                "current_base_quantity_raw",
                document["current_base_quantity_raw"],
            ),
            exit_input_amount_raw=_decode_positive_int_text(
                "exit_input_amount_raw",
                document["exit_input_amount_raw"],
            ),
            reduction_reads=_decode_reduction_reads(
                document["reduction_reads"]
            ),
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"authoritative reduction source content is incompatible: {exc}"
        ) from exc
    expected = build_fast_paper_authoritative_reduction_source_record(
        manifest,
        bootstrap,
        market_key,
        record.reduction_reads,
    )
    if record != expected:
        raise ValueError(
            "authoritative reduction source does not match current state"
        )
    return record


def read_fast_paper_authoritative_pending_buy_retry_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    directory: str | Path,
) -> FastPaperAuthoritativePendingBuyRetrySourceRecord:
    root = _require_directory(
        directory,
        "authoritative pending BUY retry source",
    )
    path = root / _pending_retry_filename(
        bootstrap.runtime_state.state_fingerprint_sha256,
        decision_evidence.source_event_id,
    )
    document = _read_document(
        path,
        _RETRY_KEYS,
        "authoritative pending BUY retry source",
    )
    try:
        risk = _decode_risk_context(
            document["retry_input"]["risk_context"]
        )
        usd = _decode_quote_usd_required(
            document["retry_input"]["quote_usd_evidence"]
        )
        if risk is None:
            raise ValueError("retry risk context is required")
        retry = FastPaperShadowPendingBuyRetryInput(
            evaluated_at_unix_ms=_require_exact_int(
                "evaluated_at_unix_ms",
                document["retry_input"]["evaluated_at_unix_ms"],
            ),
            quote=_decode_quote(document["retry_input"]["quote"]),
            risk_context=risk,
            quote_usd_evidence=usd,
        )
        record = FastPaperAuthoritativePendingBuyRetrySourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
            binding_fingerprint_sha256=document[
                "binding_fingerprint_sha256"
            ],
            execution_policy_fingerprint_sha256=document[
                "execution_policy_fingerprint_sha256"
            ],
            paper_checkpoint_sequence=document[
                "paper_checkpoint_sequence"
            ],
            paper_checkpoint_payload_sha256=document[
                "paper_checkpoint_payload_sha256"
            ],
            runtime_state_fingerprint_sha256=document[
                "runtime_state_fingerprint_sha256"
            ],
            decision_evidence_fingerprint_sha256=document[
                "decision_evidence_fingerprint_sha256"
            ],
            pending_source_event_id=document[
                "pending_source_event_id"
            ],
            pending_market_key=document["pending_market_key"],
            pending_mint=document["pending_mint"],
            risk_day_started_at_unix_ms=document[
                "risk_day_started_at_unix_ms"
            ],
            source_observed_at_unix_ms=document[
                "source_observed_at_unix_ms"
            ],
            retry_input=retry,
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"authoritative pending BUY retry source content is incompatible: {exc}"
        ) from exc
    expected = (
        build_fast_paper_authoritative_pending_buy_retry_source_record(
            manifest,
            bootstrap,
            decision_evidence,
            record.retry_input,
            risk_day_started_at_unix_ms=(
                record.risk_day_started_at_unix_ms
            ),
            source_observed_at_unix_ms=(
                record.source_observed_at_unix_ms
            ),
        )
    )
    if record != expected:
        raise ValueError(
            "authoritative pending BUY retry source does not match current state"
        )
    return record


def resolve_fast_paper_authoritative_execution_authority(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    *,
    buy_authority_source_directory: str | Path,
    quote_usd_source_directory: str | Path,
) -> FastPaperAuthoritativeExecutionAuthority | None:
    _require_bootstrap_pair(manifest, bootstrap)
    _require_decision(manifest, decision_evidence)
    action = decision_evidence.decision.action
    if action == "BUY":
        buy_root = _require_directory(
            buy_authority_source_directory,
            "authoritative BUY authority source",
        )
        quote_root = _require_directory(
            quote_usd_source_directory,
            "authoritative quote/USD source",
        )
        buy_path = buy_root / (
            f"{decision_evidence.evidence_fingerprint_sha256}.json"
        )
        quote_path = quote_root / _quote_usd_filename(
            decision_evidence.evidence_fingerprint_sha256
        )
        if not buy_path.exists() or not quote_path.exists():
            return None
        buy = read_fast_paper_authoritative_buy_authority_source_record(
            manifest,
            bootstrap,
            decision_evidence,
            buy_root,
        )
        quote_usd = read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            decision_evidence,
            quote_root,
        )
        return FastPaperAuthoritativeExecutionAuthority(
            source=FastPaperShadowExecutionInput(
                decision_evidence=decision_evidence,
                entry_authority=buy.entry_authority,
                risk_context=buy.risk_context,
                market_regime=buy.market_regime,
                quote_usd_evidence=quote_usd.quote_usd_evidence,
            ),
            source_observed_at_unix_ms=max(
                buy.source_observed_at_unix_ms,
                quote_usd.quote_usd_evidence.observed_at_unix_ms,
            ),
            risk_day_started_at_unix_ms=(
                buy.risk_day_started_at_unix_ms
            ),
        )
    if action in {"HOLD", "REDUCE", "SELL"}:
        quote_root = _require_directory(
            quote_usd_source_directory,
            "authoritative quote/USD source",
        )
        quote_path = quote_root / _quote_usd_filename(
            decision_evidence.evidence_fingerprint_sha256
        )
        if not quote_path.exists():
            return None
        quote_usd = read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            decision_evidence,
            quote_root,
        )
        return FastPaperAuthoritativeExecutionAuthority(
            source=FastPaperShadowExecutionInput(
                decision_evidence=decision_evidence,
                entry_authority=None,
                risk_context=None,
                market_regime=None,
                quote_usd_evidence=quote_usd.quote_usd_evidence,
            ),
            source_observed_at_unix_ms=(
                decision_evidence.evaluated_at_unix_ms
            ),
            risk_day_started_at_unix_ms=None,
        )
    raise ValueError(
        "authoritative file authority resolver supports BUY/HOLD/REDUCE/SELL"
    )


def resolve_fast_paper_authoritative_pending_buy_retry(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    *,
    pending_buy_retry_source_directory: str | Path,
) -> FastPaperShadowPendingBuyRetryInput | None:
    root = _require_directory(
        pending_buy_retry_source_directory,
        "authoritative pending BUY retry source",
    )
    path = root / _pending_retry_filename(
        bootstrap.runtime_state.state_fingerprint_sha256,
        decision_evidence.source_event_id,
    )
    if not path.exists():
        return None
    return read_fast_paper_authoritative_pending_buy_retry_source_record(
        manifest,
        bootstrap,
        decision_evidence,
        root,
    ).retry_input


def require_fast_paper_authoritative_reduction_source(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    market_key: str,
    *,
    reduction_source_directory: str | Path,
) -> FastPaperAuthoritativeReductionSourceRecord:
    root = _require_directory(
        reduction_source_directory,
        "authoritative reduction source",
    )
    path = root / _reduction_filename(
        bootstrap.runtime_state.state_fingerprint_sha256,
        market_key,
    )
    if not path.exists():
        raise FastPaperAuthoritativeAuthorityUnavailable(
            "authoritative OPEN reduction source is not available yet"
        )
    return read_fast_paper_authoritative_reduction_source_record(
        manifest,
        bootstrap,
        market_key,
        root,
    )


def _require_bootstrap_pair(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
) -> None:
    if type(bootstrap) is not FastPaperAuthoritativeServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    _require_exact_pair(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        bootstrap.checkpoint,
        bootstrap.runtime_state,
    )


def _require_decision(
    manifest: FastPaperRuntimeManifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if type(evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    validate_fast_paper_shadow_decision_evidence(evidence)
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


def _require_risk_matches_checkpoint(
    checkpoint,
    risk: RiskContext,
    *,
    day_started_at_unix_ms: int,
) -> None:
    if type(risk) is not RiskContext:
        raise ValueError("risk must be exact RiskContext")
    ledger = checkpoint.state.ledger
    if risk.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "authoritative source risk trading capital does not match ledger"
        )
    if risk.active_intent_keys:
        raise ValueError(
            "authoritative source risk cannot claim external active intents"
        )
    accounting = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=day_started_at_unix_ms,
    )
    expected = (
        accounting.open_position_count,
        accounting.aggregate_open_risk_usd,
        accounting.daily_realized_pnl_usd,
        accounting.rolling_drawdown_pct,
        accounting.consecutive_losses,
        accounting.last_loss_at_unix_ms,
    )
    actual = (
        risk.open_position_count,
        risk.aggregate_open_risk_usd,
        risk.daily_realized_pnl_usd,
        risk.rolling_drawdown_pct,
        risk.consecutive_losses,
        risk.last_loss_at_unix_ms,
    )
    if actual != expected:
        raise ValueError(
            "authoritative source risk accounting does not match durable ledger"
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
            "authoritative reduction source requires one OPEN market mapping"
        )
    return matches[0]


def _require_open_position(
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    *,
    position_id: str,
    mint: str,
) -> None:
    matches = tuple(
        value
        for value in bootstrap.checkpoint.state.ledger.positions
        if value.position_id == position_id
    )
    if len(matches) != 1:
        raise ValueError(
            "authoritative reduction source durable position is missing"
        )
    position = matches[0]
    if position.state is not PaperPositionState.OPEN or position.mint != mint:
        raise ValueError(
            "authoritative reduction source durable position mismatch"
        )


def _write_record(record, directory, filename: str, encoder) -> Path:
    root = _require_directory(directory, "authoritative source")
    destination = root / filename
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("authoritative source record already exists")
    payload = _canonical_json(encoder(record)) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=root,
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        published = True
        os.chmod(destination, 0o600)
        _fsync_directory(root)
        temporary.unlink()
        _fsync_directory(root)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if published:
            destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _read_document(
    path: Path,
    keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"{label} record must be an existing regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            f"{label} record must have exactly one trailing newline"
        )
    raw = payload[:-1]
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} record is malformed JSON") from exc
    if type(document) is not dict or frozenset(document) != keys:
        raise ValueError(
            f"{label} record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(f"{label} record must use canonical JSON")
    return document


def _buy_record_fingerprint(
    record: FastPaperAuthoritativeBuyAuthoritySourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(_buy_document_values(record.__dict__))
    ).hexdigest()


def _buy_document(
    record: FastPaperAuthoritativeBuyAuthoritySourceRecord,
) -> dict[str, object]:
    document = _buy_document_values(_slot_values(record))
    document["record_fingerprint_sha256"] = record.record_fingerprint_sha256
    return document


def _buy_document_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": values[
            "manifest_fingerprint_sha256"
        ],
        "binding_fingerprint_sha256": values[
            "binding_fingerprint_sha256"
        ],
        "execution_policy_fingerprint_sha256": values[
            "execution_policy_fingerprint_sha256"
        ],
        "paper_checkpoint_sequence": values[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_payload_sha256": values[
            "paper_checkpoint_payload_sha256"
        ],
        "runtime_state_fingerprint_sha256": values[
            "runtime_state_fingerprint_sha256"
        ],
        "decision_evidence_fingerprint_sha256": values[
            "decision_evidence_fingerprint_sha256"
        ],
        "source_event_id": values["source_event_id"],
        "market_key": values["market_key"],
        "mint": values["mint"],
        "quote_mint": values["quote_mint"],
        "evaluated_at_unix_ms": values["evaluated_at_unix_ms"],
        "risk_day_started_at_unix_ms": values[
            "risk_day_started_at_unix_ms"
        ],
        "source_observed_at_unix_ms": values[
            "source_observed_at_unix_ms"
        ],
        "entry_authority": _encode_entry_authority(
            values["entry_authority"]
        ),
        "risk_context": _encode_risk_context(values["risk_context"]),
        "market_regime": values["market_regime"].value,
        "source_version": values["source_version"],
        "source_fingerprint_sha256": values[
            "source_fingerprint_sha256"
        ],
    }


def _reduction_record_fingerprint(
    record: FastPaperAuthoritativeReductionSourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(_reduction_document_values(_slot_values(record)))
    ).hexdigest()


def _reduction_document(
    record: FastPaperAuthoritativeReductionSourceRecord,
) -> dict[str, object]:
    document = _reduction_document_values(_slot_values(record))
    document["record_fingerprint_sha256"] = record.record_fingerprint_sha256
    return document


def _reduction_document_values(
    values: dict[str, object],
) -> dict[str, object]:
    reads = values["reduction_reads"]
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": values[
            "manifest_fingerprint_sha256"
        ],
        "binding_fingerprint_sha256": values[
            "binding_fingerprint_sha256"
        ],
        "execution_policy_fingerprint_sha256": values[
            "execution_policy_fingerprint_sha256"
        ],
        "paper_checkpoint_sequence": values[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_payload_sha256": values[
            "paper_checkpoint_payload_sha256"
        ],
        "runtime_state_fingerprint_sha256": values[
            "runtime_state_fingerprint_sha256"
        ],
        "market_key": values["market_key"],
        "position_id": values["position_id"],
        "mint": values["mint"],
        "current_exposure_fraction_hex": _float_hex(
            values["current_exposure_fraction"]
        ),
        "current_base_quantity_raw": str(
            values["current_base_quantity_raw"]
        ),
        "exit_input_amount_raw": str(values["exit_input_amount_raw"]),
        "reduction_reads": [
            {
                "target_exposure_fraction_hex": _float_hex(
                    item.target_exposure_fraction
                ),
                "input_amount_raw": str(item.input_amount_raw),
            }
            for item in reads
        ],
    }


def _retry_record_fingerprint(
    record: FastPaperAuthoritativePendingBuyRetrySourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(_retry_document_values(_slot_values(record)))
    ).hexdigest()


def _retry_document(
    record: FastPaperAuthoritativePendingBuyRetrySourceRecord,
) -> dict[str, object]:
    document = _retry_document_values(_slot_values(record))
    document["record_fingerprint_sha256"] = record.record_fingerprint_sha256
    return document


def _retry_document_values(values: dict[str, object]) -> dict[str, object]:
    retry = values["retry_input"]
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": values[
            "manifest_fingerprint_sha256"
        ],
        "binding_fingerprint_sha256": values[
            "binding_fingerprint_sha256"
        ],
        "execution_policy_fingerprint_sha256": values[
            "execution_policy_fingerprint_sha256"
        ],
        "paper_checkpoint_sequence": values[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_payload_sha256": values[
            "paper_checkpoint_payload_sha256"
        ],
        "runtime_state_fingerprint_sha256": values[
            "runtime_state_fingerprint_sha256"
        ],
        "decision_evidence_fingerprint_sha256": values[
            "decision_evidence_fingerprint_sha256"
        ],
        "pending_source_event_id": values["pending_source_event_id"],
        "pending_market_key": values["pending_market_key"],
        "pending_mint": values["pending_mint"],
        "risk_day_started_at_unix_ms": values[
            "risk_day_started_at_unix_ms"
        ],
        "source_observed_at_unix_ms": values[
            "source_observed_at_unix_ms"
        ],
        "retry_input": {
            "evaluated_at_unix_ms": retry.evaluated_at_unix_ms,
            "quote": _encode_quote(retry.quote),
            "risk_context": _encode_risk_context(retry.risk_context),
            "quote_usd_evidence": _encode_quote_usd_required(
                retry.quote_usd_evidence
            ),
        },
    }


def _decode_reduction_reads(
    value: object,
) -> tuple[FastPaperShadowReductionRead, ...]:
    if not isinstance(value, list):
        raise ValueError("reduction_reads must be a list")
    values = []
    for item in value:
        if type(item) is not dict or frozenset(item) != _REDUCTION_READ_KEYS:
            raise ValueError(
                "reduction read has unknown or missing fields"
            )
        values.append(
            FastPaperShadowReductionRead(
                target_exposure_fraction=_decode_float_hex(
                    "target_exposure_fraction_hex",
                    item["target_exposure_fraction_hex"],
                ),
                input_amount_raw=_decode_positive_int_text(
                    "input_amount_raw",
                    item["input_amount_raw"],
                ),
            )
        )
    return tuple(values)


def _encode_quote_usd_required(value) -> dict[str, object]:
    from .shadow_execution_source import _encode_quote_usd

    encoded = _encode_quote_usd(value)
    if encoded is None:
        raise ValueError("quote/USD evidence is required")
    return encoded


def _decode_quote_usd_required(value):
    from .shadow_execution_source import _decode_quote_usd

    decoded = _decode_quote_usd(value)
    if decoded is None:
        raise ValueError("quote/USD evidence is required")
    return decoded


def _slot_values(value) -> dict[str, object]:
    return {
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if name != "record_fingerprint_sha256"
    }


def _float_hex(value: object) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("authoritative source float must be finite")
    return float(value).hex()


def _decode_float_hex(name: str, value: object) -> float:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be hexadecimal float text")
    try:
        result = float.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be hexadecimal float text") from exc
    if not math.isfinite(result) or result.hex() != value:
        raise ValueError(f"{name} must be canonical finite hexadecimal float")
    return result


def _decode_positive_int_text(name: str, value: object) -> int:
    if not isinstance(value, str) or not value.isdigit():
        raise ValueError(f"{name} must be unsigned integer text")
    if value != str(int(value)):
        raise ValueError(f"{name} must be canonical unsigned integer text")
    result = int(value)
    _require_positive_int(name, result)
    return result


def _require_directory(value: str | Path, label: str) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return root.resolve(strict=True)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ValueError(f"{name} must be finite within (0,1]")
