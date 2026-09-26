from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.paper import derive_paper_risk_accounting_facts
from shreks_brain.paper_validation import FastPaperCheckpointRecord
from shreks_brain.risk import RiskContext

from .models import FastPaperRuntimeManifest
from .shadow import FastPaperShadowQuoteEvidence
from .shadow_execution_input import FastPaperShadowExecutionPolicy
from .shadow_execution_source import (
    _canonical_json,
    _decode_optional_float_tag,
    _decode_quote_usd,
    _decode_risk_context,
    _encode_quote_usd,
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
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from .shadow_runtime_state import (
    FastPaperShadowRuntimeState,
    load_latest_fast_paper_shadow_runtime_state,
)


FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_pending_buy_retry_source"
)
FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "shadow_runtime_state_fingerprint_sha256",
        "pending_source_event_id",
        "pending_market_key",
        "pending_mint",
        "pending_target_exposure_fraction",
        "risk_day_started_at_unix_ms",
        "source_observed_at_unix_ms",
        "retry_input",
        "record_fingerprint_sha256",
    }
)
_RETRY_KEYS = frozenset(
    {
        "evaluated_at_unix_ms",
        "quote",
        "risk_context",
        "quote_usd_evidence",
    }
)
_QUOTE_KEYS = frozenset(
    {
        "provider",
        "mint",
        "quote_mint",
        "observed_at_unix_ms",
        "state",
        "reference_price_quote",
        "execution_price_quote",
        "quoted_base_quantity",
        "available_base_quantity",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowPendingBuyRetrySourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    shadow_runtime_state_fingerprint_sha256: str
    pending_source_event_id: str
    pending_market_key: str
    pending_mint: str
    pending_target_exposure_fraction: float
    risk_day_started_at_unix_ms: int
    source_observed_at_unix_ms: int
    retry_input: FastPaperShadowPendingBuyRetryInput
    record_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME
        ):
            raise ValueError(
                "shadow pending BUY retry source schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow pending BUY retry source schema_version is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "shadow_runtime_state_fingerprint_sha256",
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
        _require_exposure(
            "pending_target_exposure_fraction",
            self.pending_target_exposure_fraction,
        )
        _require_non_negative_int(
            "risk_day_started_at_unix_ms",
            self.risk_day_started_at_unix_ms,
        )
        _require_non_negative_int(
            "source_observed_at_unix_ms",
            self.source_observed_at_unix_ms,
        )
        if type(self.retry_input) is not FastPaperShadowPendingBuyRetryInput:
            raise ValueError(
                "retry_input must be exact FastPaperShadowPendingBuyRetryInput"
            )
        if (
            self.risk_day_started_at_unix_ms
            > self.retry_input.evaluated_at_unix_ms
        ):
            raise ValueError(
                "shadow pending BUY retry risk day cannot start after evaluation"
            )
        if (
            self.source_observed_at_unix_ms
            > self.retry_input.evaluated_at_unix_ms
        ):
            raise ValueError(
                "shadow pending BUY retry source observation cannot be from the future"
            )
        if self.source_observed_at_unix_ms < max(
            self.retry_input.quote.observed_at_unix_ms,
            self.retry_input.quote_usd_evidence.observed_at_unix_ms,
        ):
            raise ValueError(
                "shadow pending BUY retry source observation cannot predate supplied quote evidence"
            )
        if _record_fingerprint(self) != self.record_fingerprint_sha256:
            raise ValueError(
                "shadow pending BUY retry source record fingerprint mismatch"
            )


def build_fast_paper_shadow_pending_buy_retry_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    retry_input: FastPaperShadowPendingBuyRetryInput,
    *,
    risk_day_started_at_unix_ms: int,
    source_observed_at_unix_ms: int,
) -> FastPaperShadowPendingBuyRetrySourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
    )
    if type(retry_input) is not FastPaperShadowPendingBuyRetryInput:
        raise ValueError(
            "retry_input must be exact FastPaperShadowPendingBuyRetryInput"
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
            "pending BUY retry risk day start cannot be later than evaluation"
        )
    if retry_input.evaluated_at_unix_ms < paper_checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "pending BUY retry source evaluation predates durable pending state"
        )
    if source_observed_at_unix_ms > retry_input.evaluated_at_unix_ms:
        raise ValueError(
            "pending BUY retry source observation cannot be later than evaluation"
        )
    if source_observed_at_unix_ms < max(
        retry_input.quote.observed_at_unix_ms,
        retry_input.quote_usd_evidence.observed_at_unix_ms,
    ):
        raise ValueError(
            "pending BUY retry source observation cannot predate supplied quote evidence"
        )

    approval, pending = _require_pending_pair(
        paper_checkpoint,
        runtime_state,
    )
    _validate_pending_retry_quote(
        manifest,
        approval,
        retry_input,
        minimum_observed_at_unix_ms=(
            paper_checkpoint.state.as_of_unix_ms
        ),
    )
    _require_retry_risk_context_matches_checkpoint(
        paper_checkpoint,
        retry_input.risk_context,
        day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )

    values = {
        "schema_name": (
            FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_NAME
        ),
        "schema_version": (
            FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_SCHEMA_VERSION
        ),
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            execution_policy.policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": paper_checkpoint.sequence,
        "paper_checkpoint_payload_sha256": (
            paper_checkpoint.payload_sha256
        ),
        "shadow_runtime_state_fingerprint_sha256": (
            runtime_state.state_fingerprint_sha256
        ),
        "pending_source_event_id": pending.source_event_id,
        "pending_market_key": pending.market_key,
        "pending_mint": pending.mint,
        "pending_target_exposure_fraction": (
            pending.target_exposure_fraction
        ),
        "risk_day_started_at_unix_ms": risk_day_started_at_unix_ms,
        "source_observed_at_unix_ms": source_observed_at_unix_ms,
        "retry_input": retry_input,
    }
    fingerprint = hashlib.sha256(
        _canonical_json(_document_values(values))
    ).hexdigest()
    return FastPaperShadowPendingBuyRetrySourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_pending_buy_retry_source_record(
    record: FastPaperShadowPendingBuyRetrySourceRecord,
    directory: str | Path,
) -> Path:
    if type(record) is not FastPaperShadowPendingBuyRetrySourceRecord:
        raise ValueError(
            "record must be exact FastPaperShadowPendingBuyRetrySourceRecord"
        )
    if _record_fingerprint(record) != record.record_fingerprint_sha256:
        raise ValueError(
            "shadow pending BUY retry source record fingerprint mismatch"
        )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow pending BUY retry source directory must be an existing regular non-symlink directory"
        )
    destination = root / _record_filename(
        record.shadow_runtime_state_fingerprint_sha256,
        record.pending_source_event_id,
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "shadow pending BUY retry source record already exists"
        )

    payload = _canonical_json(_document(record)) + b"\n"
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


def read_fast_paper_shadow_pending_buy_retry_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    directory: str | Path,
) -> FastPaperShadowPendingBuyRetrySourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
    )
    _approval, pending = _require_pending_pair(
        paper_checkpoint,
        runtime_state,
    )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow pending BUY retry source directory must be an existing regular non-symlink directory"
        )
    path = root / _record_filename(
        runtime_state.state_fingerprint_sha256,
        pending.source_event_id,
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow pending BUY retry source record must be an existing regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow pending BUY retry source record must have exactly one trailing newline"
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
            "shadow pending BUY retry source record is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow pending BUY retry source record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow pending BUY retry source record must use canonical JSON"
        )

    try:
        retry_input = _decode_retry_input(document["retry_input"])
        record = FastPaperShadowPendingBuyRetrySourceRecord(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=(
                document["manifest_fingerprint_sha256"]
            ),
            binding_fingerprint_sha256=(
                document["binding_fingerprint_sha256"]
            ),
            execution_policy_fingerprint_sha256=(
                document["execution_policy_fingerprint_sha256"]
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
            pending_source_event_id=document[
                "pending_source_event_id"
            ],
            pending_market_key=document["pending_market_key"],
            pending_mint=document["pending_mint"],
            pending_target_exposure_fraction=(
                _decode_required_float(
                    "pending_target_exposure_fraction",
                    document["pending_target_exposure_fraction"],
                )
            ),
            risk_day_started_at_unix_ms=document[
                "risk_day_started_at_unix_ms"
            ],
            source_observed_at_unix_ms=document[
                "source_observed_at_unix_ms"
            ],
            retry_input=retry_input,
            record_fingerprint_sha256=document[
                "record_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"shadow pending BUY retry source record content is incompatible: {exc}"
        ) from exc

    expected = build_fast_paper_shadow_pending_buy_retry_source_record(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
        record.retry_input,
        risk_day_started_at_unix_ms=(
            record.risk_day_started_at_unix_ms
        ),
        source_observed_at_unix_ms=(
            record.source_observed_at_unix_ms
        ),
    )
    if record != expected:
        raise ValueError(
            "shadow pending BUY retry source record does not match current durable state"
        )
    return record


def _require_exact_latest_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
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
    if type(runtime_state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "runtime_state must be exact FastPaperShadowRuntimeState"
        )

    latest_checkpoint = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest_checkpoint is None or latest_checkpoint != paper_checkpoint:
        raise ValueError(
            "shadow pending BUY retry source requires exact latest paper checkpoint"
        )
    latest_runtime = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_runtime is None or latest_runtime != runtime_state:
        raise ValueError(
            "shadow pending BUY retry source requires exact latest runtime state"
        )
    if (
        runtime_state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "shadow pending BUY retry source runtime binding fingerprint mismatch"
        )
    if (
        runtime_state.paper_checkpoint_sequence
        != paper_checkpoint.sequence
        or runtime_state.paper_checkpoint_payload_sha256
        != paper_checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow pending BUY retry source checkpoint/runtime pair is torn"
        )
    if (
        runtime_state.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow pending BUY retry source execution policy fingerprint mismatch"
        )


def _require_pending_pair(
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
):
    approval = paper_checkpoint.state.pending_buy
    pending = runtime_state.pending_buy
    if approval is None or pending is None:
        raise ValueError(
            "shadow pending BUY retry source requires durable pending BUY authority"
        )
    if (
        pending.source_event_id != approval.assessment.source_event_id
        or pending.market_key != approval.assessment.market_key
        or pending.mint != approval.mint
    ):
        raise ValueError(
            "shadow pending BUY retry source pending identity mismatch"
        )
    return approval, pending


def _require_retry_risk_context_matches_checkpoint(
    paper_checkpoint: FastPaperCheckpointRecord,
    risk: RiskContext,
    *,
    day_started_at_unix_ms: int,
) -> None:
    if type(risk) is not RiskContext:
        raise ValueError(
            "pending BUY retry source requires exact RiskContext"
        )
    ledger = paper_checkpoint.state.ledger
    if risk.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "pending BUY retry risk trading capital must equal isolated ledger starting cash"
        )
    if risk.active_intent_keys:
        raise ValueError(
            "pending BUY retry source cannot claim external active intents"
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
                f"pending BUY retry risk accounting {name} does not match durable ledger"
            )


def _record_filename(
    runtime_state_fingerprint_sha256: str,
    pending_source_event_id: str,
) -> str:
    _require_sha256_value(
        "runtime_state_fingerprint_sha256",
        runtime_state_fingerprint_sha256,
    )
    _require_exact_text(
        "pending_source_event_id",
        pending_source_event_id,
    )
    digest = hashlib.sha256(
        _canonical_json(
            {
                "pending_source_event_id": pending_source_event_id,
                "runtime_state_fingerprint_sha256": (
                    runtime_state_fingerprint_sha256
                ),
            }
        )
    ).hexdigest()
    return f"{digest}.json"


def _record_fingerprint(
    record: FastPaperShadowPendingBuyRetrySourceRecord,
) -> str:
    return hashlib.sha256(
        _canonical_json(
            _document_values(
                {
                    "schema_name": record.schema_name,
                    "schema_version": record.schema_version,
                    "manifest_fingerprint_sha256": (
                        record.manifest_fingerprint_sha256
                    ),
                    "binding_fingerprint_sha256": (
                        record.binding_fingerprint_sha256
                    ),
                    "execution_policy_fingerprint_sha256": (
                        record.execution_policy_fingerprint_sha256
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
                    "pending_source_event_id": (
                        record.pending_source_event_id
                    ),
                    "pending_market_key": record.pending_market_key,
                    "pending_mint": record.pending_mint,
                    "pending_target_exposure_fraction": (
                        record.pending_target_exposure_fraction
                    ),
                    "risk_day_started_at_unix_ms": (
                        record.risk_day_started_at_unix_ms
                    ),
                    "source_observed_at_unix_ms": (
                        record.source_observed_at_unix_ms
                    ),
                    "retry_input": record.retry_input,
                }
            )
        )
    ).hexdigest()


def _document(
    record: FastPaperShadowPendingBuyRetrySourceRecord,
) -> dict[str, object]:
    document = _document_values(
        {
            "schema_name": record.schema_name,
            "schema_version": record.schema_version,
            "manifest_fingerprint_sha256": (
                record.manifest_fingerprint_sha256
            ),
            "binding_fingerprint_sha256": (
                record.binding_fingerprint_sha256
            ),
            "execution_policy_fingerprint_sha256": (
                record.execution_policy_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": record.paper_checkpoint_sequence,
            "paper_checkpoint_payload_sha256": (
                record.paper_checkpoint_payload_sha256
            ),
            "shadow_runtime_state_fingerprint_sha256": (
                record.shadow_runtime_state_fingerprint_sha256
            ),
            "pending_source_event_id": record.pending_source_event_id,
            "pending_market_key": record.pending_market_key,
            "pending_mint": record.pending_mint,
            "pending_target_exposure_fraction": (
                record.pending_target_exposure_fraction
            ),
            "risk_day_started_at_unix_ms": (
                record.risk_day_started_at_unix_ms
            ),
            "source_observed_at_unix_ms": (
                record.source_observed_at_unix_ms
            ),
            "retry_input": record.retry_input,
        }
    )
    document["record_fingerprint_sha256"] = (
        record.record_fingerprint_sha256
    )
    return document


def _document_values(
    values: dict[str, object],
) -> dict[str, object]:
    retry = values["retry_input"]
    if type(retry) is not FastPaperShadowPendingBuyRetryInput:
        raise ValueError(
            "shadow pending BUY retry source requires exact retry input"
        )
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "manifest_fingerprint_sha256": (
            values["manifest_fingerprint_sha256"]
        ),
        "binding_fingerprint_sha256": (
            values["binding_fingerprint_sha256"]
        ),
        "execution_policy_fingerprint_sha256": (
            values["execution_policy_fingerprint_sha256"]
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
        "pending_source_event_id": values["pending_source_event_id"],
        "pending_market_key": values["pending_market_key"],
        "pending_mint": values["pending_mint"],
        "pending_target_exposure_fraction": _float_tag(
            values["pending_target_exposure_fraction"]
        ),
        "risk_day_started_at_unix_ms": values[
            "risk_day_started_at_unix_ms"
        ],
        "source_observed_at_unix_ms": values[
            "source_observed_at_unix_ms"
        ],
        "retry_input": _encode_retry_input(retry),
    }


def _encode_retry_input(
    value: FastPaperShadowPendingBuyRetryInput,
) -> dict[str, object]:
    return {
        "evaluated_at_unix_ms": value.evaluated_at_unix_ms,
        "quote": _encode_quote(value.quote),
        "risk_context": _encode_risk_context(value.risk_context),
        "quote_usd_evidence": _encode_quote_usd(
            value.quote_usd_evidence
        ),
    }


def _decode_retry_input(
    value: object,
) -> FastPaperShadowPendingBuyRetryInput:
    if type(value) is not dict or frozenset(value) != _RETRY_KEYS:
        raise ValueError(
            "shadow pending BUY retry source retry_input has unknown or missing fields"
        )
    risk = _decode_risk_context(value["risk_context"])
    usd = _decode_quote_usd(value["quote_usd_evidence"])
    if risk is None or usd is None:
        raise ValueError(
            "shadow pending BUY retry source requires risk and quote/USD evidence"
        )
    return FastPaperShadowPendingBuyRetryInput(
        evaluated_at_unix_ms=_require_exact_int(
            "evaluated_at_unix_ms",
            value["evaluated_at_unix_ms"],
        ),
        quote=_decode_quote(value["quote"]),
        risk_context=risk,
        quote_usd_evidence=usd,
    )


def _encode_quote(
    value: FastPaperShadowQuoteEvidence,
) -> dict[str, object]:
    if type(value) is not FastPaperShadowQuoteEvidence:
        raise ValueError(
            "shadow pending BUY retry source quote must be exact FastPaperShadowQuoteEvidence"
        )
    return {
        "provider": value.provider,
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "observed_at_unix_ms": value.observed_at_unix_ms,
        "state": value.state,
        "reference_price_quote": _optional_float_tag(
            value.reference_price_quote
        ),
        "execution_price_quote": _optional_float_tag(
            value.execution_price_quote
        ),
        "quoted_base_quantity": _optional_float_tag(
            value.quoted_base_quantity
        ),
        "available_base_quantity": _optional_float_tag(
            value.available_base_quantity
        ),
    }


def _decode_quote(value: object) -> FastPaperShadowQuoteEvidence:
    if type(value) is not dict or frozenset(value) != _QUOTE_KEYS:
        raise ValueError(
            "shadow pending BUY retry source quote has unknown or missing fields"
        )
    return FastPaperShadowQuoteEvidence(
        provider=_require_exact_text("provider", value["provider"]),
        mint=_require_exact_text("mint", value["mint"]),
        quote_mint=_require_exact_text(
            "quote_mint",
            value["quote_mint"],
        ),
        observed_at_unix_ms=_require_exact_int(
            "observed_at_unix_ms",
            value["observed_at_unix_ms"],
        ),
        state=_require_exact_text("state", value["state"]),
        reference_price_quote=_decode_optional_float_tag(
            "reference_price_quote",
            value["reference_price_quote"],
        ),
        execution_price_quote=_decode_optional_float_tag(
            "execution_price_quote",
            value["execution_price_quote"],
        ),
        quoted_base_quantity=_decode_optional_float_tag(
            "quoted_base_quantity",
            value["quoted_base_quantity"],
        ),
        available_base_quantity=_decode_optional_float_tag(
            "available_base_quantity",
            value["available_base_quantity"],
        ),
    )


def _optional_float_tag(value: float | None) -> dict[str, str] | None:
    return None if value is None else _float_tag(value)


def _decode_required_float(name: str, value: object) -> float:
    result = _decode_optional_float_tag(name, value)
    if result is None:
        raise ValueError(f"{name} is required")
    return result


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ValueError(
            f"{name} must be finite within (0,1]"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
