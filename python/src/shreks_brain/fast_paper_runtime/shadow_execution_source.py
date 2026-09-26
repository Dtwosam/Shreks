from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext

from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowDecisionEvidence,
    validate_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
    FastPaperShadowQuoteUsdEvidence,
    materialize_fast_paper_shadow_execution_evidence,
)


FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_execution_input_source"
)
FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "decision_evidence_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "shadow_runtime_state_fingerprint_sha256",
        "source_event_id",
        "evaluated_at_unix_ms",
        "source_observed_at_unix_ms",
        "execution_input",
        "record_fingerprint_sha256",
    }
)
_INPUT_KEYS = frozenset(
    {
        "entry_authority",
        "risk_context",
        "market_regime",
        "quote_usd_evidence",
    }
)
_ENTRY_KEYS = frozenset(
    {
        "mint",
        "quote_mint",
        "intended_base_quantity",
        "decision_executable_entry_price_quote",
        "maximum_acceptable_entry_price_quote",
        "expected_entry_variable_cost_bps",
        "expected_entry_fixed_cost_quote",
    }
)
_RISK_KEYS = frozenset(
    {
        "as_of_unix_ms",
        "trading_capital_usd",
        "open_position_count",
        "aggregate_open_risk_usd",
        "daily_realized_pnl_usd",
        "rolling_drawdown_pct",
        "consecutive_losses",
        "last_loss_at_unix_ms",
        "liquidity_usd",
        "expected_price_impact_pct",
        "price_impact_notional_usd",
        "market_data_age_ms",
        "data_healthy",
        "execution_healthy",
        "kill_switch_active",
        "active_intent_keys",
        "operator_entry_halt_active",
    }
)
_USD_KEYS = frozenset(
    {
        "quote_mint",
        "observed_at_unix_ms",
        "quote_to_usd_rate",
        "source_version",
        "source_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowExecutionInputSourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    decision_evidence_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    shadow_runtime_state_fingerprint_sha256: str
    source_event_id: str
    evaluated_at_unix_ms: int
    source_observed_at_unix_ms: int
    execution_input: FastPaperShadowExecutionInput
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME
        ):
            raise ValueError(
                "shadow execution input source schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow execution input source schema_version is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "decision_evidence_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "shadow_runtime_state_fingerprint_sha256",
            "record_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        _require_text("source_event_id", self.source_event_id)
        _require_non_negative_int(
            "evaluated_at_unix_ms",
            self.evaluated_at_unix_ms,
        )
        _require_non_negative_int(
            "source_observed_at_unix_ms",
            self.source_observed_at_unix_ms,
        )
        if self.source_observed_at_unix_ms > self.evaluated_at_unix_ms:
            raise ValueError(
                "shadow execution input source observation cannot be from the future"
            )
        if type(self.execution_input) is not FastPaperShadowExecutionInput:
            raise ValueError(
                "execution_input must be exact FastPaperShadowExecutionInput"
            )
        evidence = self.execution_input.decision_evidence
        if self.source_event_id != evidence.source_event_id:
            raise ValueError(
                "shadow execution input source event identity mismatch"
            )
        if self.evaluated_at_unix_ms != evidence.evaluated_at_unix_ms:
            raise ValueError(
                "shadow execution input source evaluation timestamp mismatch"
            )
        if (
            self.decision_evidence_fingerprint_sha256
            != evidence.evidence_fingerprint_sha256
        ):
            raise ValueError(
                "shadow execution input source decision fingerprint mismatch"
            )
        if (
            _record_fingerprint(self)
            != self.record_fingerprint_sha256
        ):
            raise ValueError(
                "shadow execution input source record fingerprint mismatch"
            )


def build_fast_paper_shadow_execution_input_source_record(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    source: FastPaperShadowExecutionInput,
    *,
    paper_checkpoint_sequence: int,
    paper_checkpoint_payload_sha256: str,
    shadow_runtime_state_fingerprint_sha256: str,
    source_observed_at_unix_ms: int,
) -> FastPaperShadowExecutionInputSourceRecord:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )
    _require_non_negative_int(
        "paper_checkpoint_sequence",
        paper_checkpoint_sequence,
    )
    _require_sha256(
        "paper_checkpoint_payload_sha256",
        paper_checkpoint_payload_sha256,
    )
    _require_sha256(
        "shadow_runtime_state_fingerprint_sha256",
        shadow_runtime_state_fingerprint_sha256,
    )
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )
    evidence = source.decision_evidence
    if source_observed_at_unix_ms > evidence.evaluated_at_unix_ms:
        raise ValueError(
            "shadow execution input source observation cannot be later than decision evaluation"
        )

    # Reuse the sealed materializer as the full external-binding validator.
    materialize_fast_paper_shadow_execution_evidence(
        manifest,
        execution_policy,
        source,
    )

    values = {
        "schema_name": (
            FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_SHADOW_EXECUTION_INPUT_SOURCE_SCHEMA_VERSION
        ),
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            execution_policy.policy_fingerprint_sha256
        ),
        "decision_evidence_fingerprint_sha256": (
            evidence.evidence_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": paper_checkpoint_sequence,
        "paper_checkpoint_payload_sha256": (
            paper_checkpoint_payload_sha256
        ),
        "shadow_runtime_state_fingerprint_sha256": (
            shadow_runtime_state_fingerprint_sha256
        ),
        "source_event_id": evidence.source_event_id,
        "evaluated_at_unix_ms": evidence.evaluated_at_unix_ms,
        "source_observed_at_unix_ms": source_observed_at_unix_ms,
        "execution_input": source,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_record_document_values(values))
    ).hexdigest()
    return FastPaperShadowExecutionInputSourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_execution_input_source_record(
    record: FastPaperShadowExecutionInputSourceRecord,
    directory: str | Path,
) -> Path:
    if type(record) is not FastPaperShadowExecutionInputSourceRecord:
        raise ValueError(
            "record must be exact FastPaperShadowExecutionInputSourceRecord"
        )
    if _record_fingerprint(record) != record.record_fingerprint_sha256:
        raise ValueError(
            "shadow execution input source record fingerprint mismatch"
        )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow execution input source directory must be an existing regular non-symlink directory"
        )
    destination = root / (
        f"{record.decision_evidence_fingerprint_sha256}.json"
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "shadow execution input source record already exists"
        )

    payload = _canonical_json(_record_document(record)) + b"\n"
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


def read_fast_paper_shadow_execution_input_source_record(
    manifest: FastPaperRuntimeManifest,
    execution_policy: FastPaperShadowExecutionPolicy,
    decision_evidence: FastPaperShadowDecisionEvidence,
    directory: str | Path,
    *,
    paper_checkpoint_sequence: int,
    paper_checkpoint_payload_sha256: str,
    shadow_runtime_state_fingerprint_sha256: str,
) -> FastPaperShadowExecutionInputSourceRecord:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(decision_evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    validate_fast_paper_shadow_decision_evidence(decision_evidence)
    _require_non_negative_int(
        "paper_checkpoint_sequence",
        paper_checkpoint_sequence,
    )
    _require_sha256(
        "paper_checkpoint_payload_sha256",
        paper_checkpoint_payload_sha256,
    )
    _require_sha256(
        "shadow_runtime_state_fingerprint_sha256",
        shadow_runtime_state_fingerprint_sha256,
    )

    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow execution input source directory must be an existing regular non-symlink directory"
        )
    path = root / (
        f"{decision_evidence.evidence_fingerprint_sha256}.json"
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow execution input source record must be a regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow execution input source record must have exactly one trailing newline"
        )
    raw = payload[:-1]
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "shadow execution input source record is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow execution input source record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow execution input source record must use canonical JSON"
        )

    try:
        execution_input = _decode_execution_input(
            document["execution_input"],
            decision_evidence,
        )
        record = FastPaperShadowExecutionInputSourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=(
                document["manifest_fingerprint_sha256"]
            ),
            execution_policy_fingerprint_sha256=(
                document["execution_policy_fingerprint_sha256"]
            ),
            decision_evidence_fingerprint_sha256=(
                document["decision_evidence_fingerprint_sha256"]
            ),
            paper_checkpoint_sequence=document[
                "paper_checkpoint_sequence"
            ],
            paper_checkpoint_payload_sha256=document[
                "paper_checkpoint_payload_sha256"
            ],
            shadow_runtime_state_fingerprint_sha256=document[
                "shadow_runtime_state_fingerprint_sha256"
            ],
            source_event_id=document["source_event_id"],
            evaluated_at_unix_ms=document["evaluated_at_unix_ms"],
            source_observed_at_unix_ms=(
                document["source_observed_at_unix_ms"]
            ),
            execution_input=execution_input,
            record_fingerprint_sha256=(
                document["record_fingerprint_sha256"]
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"shadow execution input source record content is incompatible: {exc}"
        ) from exc

    if (
        record.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution input source manifest fingerprint mismatch"
        )
    if (
        record.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution input source execution policy fingerprint mismatch"
        )
    if (
        record.decision_evidence_fingerprint_sha256
        != decision_evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution input source decision fingerprint mismatch"
        )
    if record.paper_checkpoint_sequence != paper_checkpoint_sequence:
        raise ValueError(
            "shadow execution input source checkpoint sequence mismatch"
        )
    if (
        record.paper_checkpoint_payload_sha256
        != paper_checkpoint_payload_sha256
    ):
        raise ValueError(
            "shadow execution input source checkpoint fingerprint mismatch"
        )
    if (
        record.shadow_runtime_state_fingerprint_sha256
        != shadow_runtime_state_fingerprint_sha256
    ):
        raise ValueError(
            "shadow execution input source runtime-state fingerprint mismatch"
        )
    if record.source_event_id != decision_evidence.source_event_id:
        raise ValueError(
            "shadow execution input source event identity mismatch"
        )
    if record.evaluated_at_unix_ms != decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "shadow execution input source evaluation timestamp mismatch"
        )

    materialize_fast_paper_shadow_execution_evidence(
        manifest,
        execution_policy,
        record.execution_input,
    )
    return record


def _record_fingerprint(
    record: FastPaperShadowExecutionInputSourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            _record_document_values(
                {
                    "schema_name": record.schema_name,
                    "schema_version": record.schema_version,
                    "manifest_fingerprint_sha256": (
                        record.manifest_fingerprint_sha256
                    ),
                    "execution_policy_fingerprint_sha256": (
                        record.execution_policy_fingerprint_sha256
                    ),
                    "decision_evidence_fingerprint_sha256": (
                        record.decision_evidence_fingerprint_sha256
                    ),
                    "paper_checkpoint_sequence": (
                        record.paper_checkpoint_sequence
                    ),
                    "paper_checkpoint_payload_sha256": (
                        record.paper_checkpoint_payload_sha256
                    ),
                    "shadow_runtime_state_fingerprint_sha256": (
                        record.shadow_runtime_state_fingerprint_sha256
                    ),
                    "source_event_id": record.source_event_id,
                    "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
                    "source_observed_at_unix_ms": (
                        record.source_observed_at_unix_ms
                    ),
                    "execution_input": record.execution_input,
                }
            )
        )
    ).hexdigest()


def _record_document(
    record: FastPaperShadowExecutionInputSourceRecord,
) -> dict[str, object]:
    document = _record_document_values(
        {
            "schema_name": record.schema_name,
            "schema_version": record.schema_version,
            "manifest_fingerprint_sha256": (
                record.manifest_fingerprint_sha256
            ),
            "execution_policy_fingerprint_sha256": (
                record.execution_policy_fingerprint_sha256
            ),
            "decision_evidence_fingerprint_sha256": (
                record.decision_evidence_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": record.paper_checkpoint_sequence,
            "paper_checkpoint_payload_sha256": (
                record.paper_checkpoint_payload_sha256
            ),
            "shadow_runtime_state_fingerprint_sha256": (
                record.shadow_runtime_state_fingerprint_sha256
            ),
            "source_event_id": record.source_event_id,
            "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
            "source_observed_at_unix_ms": (
                record.source_observed_at_unix_ms
            ),
            "execution_input": record.execution_input,
        }
    )
    document["record_fingerprint_sha256"] = (
        record.record_fingerprint_sha256
    )
    return document


def _record_document_values(
    values: dict[str, object],
) -> dict[str, object]:
    execution_input = values["execution_input"]
    if type(execution_input) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "shadow execution input source requires exact execution input"
        )
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": (
            values["manifest_fingerprint_sha256"]
        ),
        "execution_policy_fingerprint_sha256": (
            values["execution_policy_fingerprint_sha256"]
        ),
        "decision_evidence_fingerprint_sha256": (
            values["decision_evidence_fingerprint_sha256"]
        ),
        "paper_checkpoint_sequence": values[
            "paper_checkpoint_sequence"
        ],
        "paper_checkpoint_payload_sha256": values[
            "paper_checkpoint_payload_sha256"
        ],
        "shadow_runtime_state_fingerprint_sha256": values[
            "shadow_runtime_state_fingerprint_sha256"
        ],
        "source_event_id": values["source_event_id"],
        "evaluated_at_unix_ms": values["evaluated_at_unix_ms"],
        "source_observed_at_unix_ms": (
            values["source_observed_at_unix_ms"]
        ),
        "execution_input": _encode_execution_input(execution_input),
    }


def _encode_execution_input(
    value: FastPaperShadowExecutionInput,
) -> dict[str, object]:
    return {
        "entry_authority": _encode_entry_authority(
            value.entry_authority
        ),
        "risk_context": _encode_risk_context(value.risk_context),
        "market_regime": (
            None
            if value.market_regime is None
            else value.market_regime.value
        ),
        "quote_usd_evidence": _encode_quote_usd(
            value.quote_usd_evidence
        ),
    }


def _decode_execution_input(
    value: object,
    decision_evidence: FastPaperShadowDecisionEvidence,
) -> FastPaperShadowExecutionInput:
    if type(value) is not dict or frozenset(value) != _INPUT_KEYS:
        raise ValueError(
            "shadow execution input source execution_input has unknown or missing fields"
        )
    raw_regime = value["market_regime"]
    regime = (
        None
        if raw_regime is None
        else MarketRegime(_require_exact_text("market_regime", raw_regime))
    )
    return FastPaperShadowExecutionInput(
        decision_evidence=decision_evidence,
        entry_authority=_decode_entry_authority(
            value["entry_authority"]
        ),
        risk_context=_decode_risk_context(value["risk_context"]),
        market_regime=regime,
        quote_usd_evidence=_decode_quote_usd(
            value["quote_usd_evidence"]
        ),
    )


def _encode_entry_authority(
    value: FastCampaignPaperEntryAuthority | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not FastCampaignPaperEntryAuthority:
        raise ValueError(
            "entry authority must be exact FastCampaignPaperEntryAuthority"
        )
    return {
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "intended_base_quantity": _float_tag(
            value.intended_base_quantity
        ),
        "decision_executable_entry_price_quote": _float_tag(
            value.decision_executable_entry_price_quote
        ),
        "maximum_acceptable_entry_price_quote": _float_tag(
            value.maximum_acceptable_entry_price_quote
        ),
        "expected_entry_variable_cost_bps": (
            value.expected_entry_variable_cost_bps
        ),
        "expected_entry_fixed_cost_quote": _float_tag(
            value.expected_entry_fixed_cost_quote
        ),
    }


def _decode_entry_authority(
    value: object,
) -> FastCampaignPaperEntryAuthority | None:
    if value is None:
        return None
    if type(value) is not dict or frozenset(value) != _ENTRY_KEYS:
        raise ValueError(
            "shadow execution input source entry authority has unknown or missing fields"
        )
    return FastCampaignPaperEntryAuthority(
        mint=_require_exact_text("mint", value["mint"]),
        quote_mint=_require_exact_text(
            "quote_mint",
            value["quote_mint"],
        ),
        intended_base_quantity=_decode_float_tag(
            "intended_base_quantity",
            value["intended_base_quantity"],
        ),
        decision_executable_entry_price_quote=_decode_float_tag(
            "decision_executable_entry_price_quote",
            value["decision_executable_entry_price_quote"],
        ),
        maximum_acceptable_entry_price_quote=_decode_float_tag(
            "maximum_acceptable_entry_price_quote",
            value["maximum_acceptable_entry_price_quote"],
        ),
        expected_entry_variable_cost_bps=_require_exact_int(
            "expected_entry_variable_cost_bps",
            value["expected_entry_variable_cost_bps"],
        ),
        expected_entry_fixed_cost_quote=_decode_float_tag(
            "expected_entry_fixed_cost_quote",
            value["expected_entry_fixed_cost_quote"],
        ),
    )


def _encode_risk_context(
    value: RiskContext | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not RiskContext:
        raise ValueError(
            "risk context must be exact RiskContext"
        )
    return {
        "as_of_unix_ms": value.as_of_unix_ms,
        "trading_capital_usd": _optional_float_tag(
            value.trading_capital_usd
        ),
        "open_position_count": value.open_position_count,
        "aggregate_open_risk_usd": _optional_float_tag(
            value.aggregate_open_risk_usd
        ),
        "daily_realized_pnl_usd": _optional_float_tag(
            value.daily_realized_pnl_usd
        ),
        "rolling_drawdown_pct": _optional_float_tag(
            value.rolling_drawdown_pct
        ),
        "consecutive_losses": value.consecutive_losses,
        "last_loss_at_unix_ms": value.last_loss_at_unix_ms,
        "liquidity_usd": _optional_float_tag(value.liquidity_usd),
        "expected_price_impact_pct": _optional_float_tag(
            value.expected_price_impact_pct
        ),
        "price_impact_notional_usd": _optional_float_tag(
            value.price_impact_notional_usd
        ),
        "market_data_age_ms": value.market_data_age_ms,
        "data_healthy": value.data_healthy,
        "execution_healthy": value.execution_healthy,
        "kill_switch_active": value.kill_switch_active,
        "active_intent_keys": sorted(value.active_intent_keys),
        "operator_entry_halt_active": (
            value.operator_entry_halt_active
        ),
    }


def _decode_risk_context(value: object) -> RiskContext | None:
    if value is None:
        return None
    if type(value) is not dict or frozenset(value) != _RISK_KEYS:
        raise ValueError(
            "shadow execution input source risk context has unknown or missing fields"
        )
    raw_keys = value["active_intent_keys"]
    if (
        type(raw_keys) is not list
        or not all(type(item) is str and item.strip() for item in raw_keys)
        or raw_keys != sorted(raw_keys)
        or len(set(raw_keys)) != len(raw_keys)
    ):
        raise ValueError(
            "shadow execution input source active intent keys are non-canonical"
        )
    return RiskContext(
        as_of_unix_ms=_require_exact_int(
            "as_of_unix_ms",
            value["as_of_unix_ms"],
        ),
        trading_capital_usd=_decode_optional_float_tag(
            "trading_capital_usd",
            value["trading_capital_usd"],
        ),
        open_position_count=_optional_exact_int(
            "open_position_count",
            value["open_position_count"],
        ),
        aggregate_open_risk_usd=_decode_optional_float_tag(
            "aggregate_open_risk_usd",
            value["aggregate_open_risk_usd"],
        ),
        daily_realized_pnl_usd=_decode_optional_float_tag(
            "daily_realized_pnl_usd",
            value["daily_realized_pnl_usd"],
        ),
        rolling_drawdown_pct=_decode_optional_float_tag(
            "rolling_drawdown_pct",
            value["rolling_drawdown_pct"],
        ),
        consecutive_losses=_optional_exact_int(
            "consecutive_losses",
            value["consecutive_losses"],
        ),
        last_loss_at_unix_ms=_optional_exact_int(
            "last_loss_at_unix_ms",
            value["last_loss_at_unix_ms"],
        ),
        liquidity_usd=_decode_optional_float_tag(
            "liquidity_usd",
            value["liquidity_usd"],
        ),
        expected_price_impact_pct=_decode_optional_float_tag(
            "expected_price_impact_pct",
            value["expected_price_impact_pct"],
        ),
        price_impact_notional_usd=_decode_optional_float_tag(
            "price_impact_notional_usd",
            value["price_impact_notional_usd"],
        ),
        market_data_age_ms=_optional_exact_int(
            "market_data_age_ms",
            value["market_data_age_ms"],
        ),
        data_healthy=_optional_exact_bool(
            "data_healthy",
            value["data_healthy"],
        ),
        execution_healthy=_optional_exact_bool(
            "execution_healthy",
            value["execution_healthy"],
        ),
        kill_switch_active=_require_exact_bool(
            "kill_switch_active",
            value["kill_switch_active"],
        ),
        active_intent_keys=frozenset(raw_keys),
        operator_entry_halt_active=_require_exact_bool(
            "operator_entry_halt_active",
            value["operator_entry_halt_active"],
        ),
    )


def _encode_quote_usd(
    value: FastPaperShadowQuoteUsdEvidence | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not FastPaperShadowQuoteUsdEvidence:
        raise ValueError(
            "quote USD evidence must be exact FastPaperShadowQuoteUsdEvidence"
        )
    return {
        "quote_mint": value.quote_mint,
        "observed_at_unix_ms": value.observed_at_unix_ms,
        "quote_to_usd_rate": _float_tag(
            value.quote_to_usd_rate
        ),
        "source_version": value.source_version,
        "source_fingerprint_sha256": (
            value.source_fingerprint_sha256
        ),
    }


def _decode_quote_usd(
    value: object,
) -> FastPaperShadowQuoteUsdEvidence | None:
    if value is None:
        return None
    if type(value) is not dict or frozenset(value) != _USD_KEYS:
        raise ValueError(
            "shadow execution input source quote USD evidence has unknown or missing fields"
        )
    return FastPaperShadowQuoteUsdEvidence(
        quote_mint=_require_exact_text(
            "quote_mint",
            value["quote_mint"],
        ),
        observed_at_unix_ms=_require_exact_int(
            "observed_at_unix_ms",
            value["observed_at_unix_ms"],
        ),
        quote_to_usd_rate=_decode_float_tag(
            "quote_to_usd_rate",
            value["quote_to_usd_rate"],
        ),
        source_version=_require_exact_text(
            "source_version",
            value["source_version"],
        ),
        source_fingerprint_sha256=_require_sha256_value(
            "source_fingerprint_sha256",
            value["source_fingerprint_sha256"],
        ),
    )


def _float_tag(value: float) -> dict[str, str]:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("shadow execution input source float is invalid")
    return {"$float": float(value).hex()}


def _optional_float_tag(
    value: float | None,
) -> dict[str, str] | None:
    return None if value is None else _float_tag(value)


def _decode_float_tag(name: str, value: object) -> float:
    if type(value) is not dict or set(value) != {"$float"}:
        raise ValueError(f"{name} must use canonical float tagging")
    encoded = value["$float"]
    if type(encoded) is not str:
        raise ValueError(f"{name} float tag must be text")
    try:
        result = float.fromhex(encoded)
    except ValueError as exc:
        raise ValueError(f"{name} float tag is malformed") from exc
    if not math.isfinite(result) or result.hex() != encoded:
        raise ValueError(f"{name} float tag is non-canonical")
    return result


def _decode_optional_float_tag(
    name: str,
    value: object,
) -> float | None:
    return None if value is None else _decode_float_tag(name, value)


def _require_exact_text(name: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be non-empty exact text")
    return value


def _require_exact_int(name: str, value: object) -> int:
    if isinstance(value, bool) or type(value) is not int:
        raise ValueError(f"{name} must be an exact integer")
    return value


def _optional_exact_int(
    name: str,
    value: object,
) -> int | None:
    return None if value is None else _require_exact_int(name, value)


def _require_exact_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be an exact boolean")
    return value


def _optional_exact_bool(
    name: str,
    value: object,
) -> bool | None:
    return None if value is None else _require_exact_bool(name, value)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "shadow execution input source cannot be encoded canonically"
        ) from exc


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                "shadow execution input source JSON contains duplicate keys"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(
        f"shadow execution input source JSON contains invalid constant {value}"
    )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_sha256(name: str, value: object) -> None:
    _require_sha256_value(name, value)


def _require_sha256_value(name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value
