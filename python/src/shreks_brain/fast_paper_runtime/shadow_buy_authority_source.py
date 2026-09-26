from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_campaign_paper import FastCampaignPaperEntryAuthority
from shreks_brain.paper import derive_paper_risk_accounting_facts
from shreks_brain.paper_validation import FastPaperCheckpointRecord
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import RiskContext

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest
from .shadow import FastPaperShadowDecisionEvidence
from .shadow_execution_input import FastPaperShadowExecutionPolicy
from .shadow_execution_source import (
    _canonical_json,
    _decode_entry_authority,
    _decode_risk_context,
    _encode_entry_authority,
    _encode_risk_context,
    _fsync_directory,
    _reject_duplicate_pairs,
    _reject_json_constant,
    _require_exact_int,
    _require_exact_text,
    _require_sha256_value,
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


FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_buy_authority_source"
)
FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION = 1

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


@dataclass(frozen=True, slots=True)
class FastPaperShadowBuyAuthoritySourceRecord:
    schema_name: str
    schema_version: int
    manifest_fingerprint_sha256: str
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    shadow_runtime_state_fingerprint_sha256: str
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
        if self.schema_name != FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_NAME:
            raise ValueError(
                "shadow BUY authority source schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow BUY authority source schema_version is incompatible"
            )
        for name in (
            "manifest_fingerprint_sha256",
            "binding_fingerprint_sha256",
            "execution_policy_fingerprint_sha256",
            "paper_checkpoint_payload_sha256",
            "shadow_runtime_state_fingerprint_sha256",
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
                "shadow BUY authority risk day cannot start after evaluation"
            )
        if self.source_observed_at_unix_ms > self.evaluated_at_unix_ms:
            raise ValueError(
                "shadow BUY authority source observation cannot be from the future"
            )
        if _record_fingerprint(self) != self.record_fingerprint_sha256:
            raise ValueError(
                "shadow BUY authority source record fingerprint mismatch"
            )


def build_fast_paper_shadow_buy_authority_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
    entry_authority: FastCampaignPaperEntryAuthority,
    risk_context: RiskContext,
    market_regime: MarketRegime,
    *,
    risk_day_started_at_unix_ms: int,
    source_observed_at_unix_ms: int,
    source_version: str,
    source_fingerprint_sha256: str,
) -> FastPaperShadowBuyAuthoritySourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
    )
    _require_buy_decision_binding(
        manifest,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
    )
    if type(entry_authority) is not FastCampaignPaperEntryAuthority:
        raise ValueError(
            "entry_authority must be exact FastCampaignPaperEntryAuthority"
        )
    if type(risk_context) is not RiskContext:
        raise ValueError("risk_context must be exact RiskContext")
    if type(market_regime) is not MarketRegime:
        raise ValueError("market_regime must be exact MarketRegime")
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
            "BUY authority risk day start cannot be later than evaluation"
        )
    if source_observed_at_unix_ms > decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "BUY authority source observation cannot be later than evaluation"
        )
    if (
        source_observed_at_unix_ms
        < decision_evidence.entry_quote.observed_at_unix_ms
    ):
        raise ValueError(
            "BUY authority source observation cannot predate sealed entry quote"
        )

    quote = decision_evidence.entry_quote
    if quote.state != "EXECUTABLE" or quote.reference_price_quote is None:
        raise ValueError(
            "BUY authority source requires executable sealed entry quote"
        )
    if entry_authority.mint != quote.mint:
        raise ValueError("BUY entry authority mint mismatch")
    if entry_authority.quote_mint != quote.quote_mint:
        raise ValueError("BUY entry authority quote mint mismatch")
    if (
        entry_authority.decision_executable_entry_price_quote
        != quote.reference_price_quote
    ):
        raise ValueError(
            "BUY entry authority decision price does not match sealed entry reference price"
        )

    if risk_context.as_of_unix_ms != decision_evidence.evaluated_at_unix_ms:
        raise ValueError(
            "BUY risk context must use the decision evaluation timestamp"
        )
    _require_buy_risk_context_matches_checkpoint(
        paper_checkpoint,
        risk_context,
        day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )

    values = {
        "schema_name": FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_SCHEMA_VERSION,
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
        "paper_checkpoint_payload_sha256": paper_checkpoint.payload_sha256,
        "shadow_runtime_state_fingerprint_sha256": (
            runtime_state.state_fingerprint_sha256
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
        _canonical_json(_document_values(values))
    ).hexdigest()
    return FastPaperShadowBuyAuthoritySourceRecord(
        **values,
        record_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_buy_authority_source_record(
    record: FastPaperShadowBuyAuthoritySourceRecord,
    directory: str | Path,
) -> Path:
    if type(record) is not FastPaperShadowBuyAuthoritySourceRecord:
        raise ValueError(
            "record must be exact FastPaperShadowBuyAuthoritySourceRecord"
        )
    if _record_fingerprint(record) != record.record_fingerprint_sha256:
        raise ValueError(
            "shadow BUY authority source record fingerprint mismatch"
        )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow BUY authority source directory must be an existing regular non-symlink directory"
        )
    destination = root / _record_filename(
        record.decision_evidence_fingerprint_sha256
    )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            "shadow BUY authority source record already exists"
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


def read_fast_paper_shadow_buy_authority_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
    directory: str | Path,
) -> FastPaperShadowBuyAuthoritySourceRecord:
    _require_exact_latest_pair(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
    )
    _require_buy_decision_binding(
        manifest,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
    )
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow BUY authority source directory must be an existing regular non-symlink directory"
        )
    path = root / _record_filename(
        decision_evidence.evidence_fingerprint_sha256
    )
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "shadow BUY authority source record must be an existing regular non-symlink file"
        )
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise ValueError(
            "shadow BUY authority source record must have exactly one trailing newline"
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
            "shadow BUY authority source record is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "shadow BUY authority source record has unknown or missing fields"
        )
    if _canonical_json(document) != raw:
        raise ValueError(
            "shadow BUY authority source record must use canonical JSON"
        )

    try:
        entry = _decode_entry_authority(document["entry_authority"])
        risk = _decode_risk_context(document["risk_context"])
        if entry is None or risk is None:
            raise ValueError(
                "shadow BUY authority source requires entry and risk authority"
            )
        regime = MarketRegime(
            _require_exact_text(
                "market_regime",
                document["market_regime"],
            )
        )
        record = FastPaperShadowBuyAuthoritySourceRecord(
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
            shadow_runtime_state_fingerprint_sha256=document[
                "shadow_runtime_state_fingerprint_sha256"
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
            market_regime=regime,
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
            f"shadow BUY authority source record content is incompatible: {exc}"
        ) from exc

    expected = build_fast_paper_shadow_buy_authority_source_record(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
        decision_evidence,
        record.entry_authority,
        record.risk_context,
        record.market_regime,
        risk_day_started_at_unix_ms=(
            record.risk_day_started_at_unix_ms
        ),
        source_observed_at_unix_ms=(
            record.source_observed_at_unix_ms
        ),
        source_version=record.source_version,
        source_fingerprint_sha256=record.source_fingerprint_sha256,
    )
    if record != expected:
        raise ValueError(
            "shadow BUY authority source record does not match current durable state"
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
            "shadow BUY authority source requires exact latest paper checkpoint"
        )
    latest_runtime = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )
    if latest_runtime is None or latest_runtime != runtime_state:
        raise ValueError(
            "shadow BUY authority source requires exact latest runtime state"
        )
    if (
        runtime_state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "shadow BUY authority source runtime binding fingerprint mismatch"
        )
    if (
        runtime_state.paper_checkpoint_sequence
        != paper_checkpoint.sequence
        or runtime_state.paper_checkpoint_payload_sha256
        != paper_checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow BUY authority source checkpoint/runtime pair is torn"
        )
    if (
        runtime_state.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "shadow BUY authority source execution policy fingerprint mismatch"
        )


def _require_buy_decision_binding(
    manifest: FastPaperRuntimeManifest,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperShadowRuntimeState,
    decision_evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if type(decision_evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    verify_fast_paper_runtime_bindings(manifest)
    if decision_evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "shadow BUY authority decision release source mismatch"
        )
    if (
        decision_evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow BUY authority decision manifest fingerprint mismatch"
        )
    if decision_evidence.champion_version != manifest.champion_version:
        raise ValueError(
            "shadow BUY authority decision champion version mismatch"
        )
    if (
        decision_evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "shadow BUY authority decision champion fingerprint mismatch"
        )
    if (
        decision_evidence.action_policy_version
        != manifest.action_policy.version
    ):
        raise ValueError(
            "shadow BUY authority decision action policy version mismatch"
        )
    if decision_evidence.decision.action != "BUY":
        raise ValueError(
            "shadow BUY authority source requires BUY action"
        )
    if decision_evidence.position.kind != "FLAT":
        raise ValueError(
            "shadow BUY authority source requires FLAT learned posture"
        )
    if (
        fast_paper_shadow_decision_position(
            runtime_state,
            decision_evidence.market_key,
        )
        != decision_evidence.position
    ):
        raise ValueError(
            "shadow BUY authority decision posture does not match durable state"
        )
    if (
        paper_checkpoint.state.pending_buy is not None
        or runtime_state.pending_buy is not None
    ):
        raise ValueError(
            "shadow BUY authority source requires no unresolved pending BUY"
        )
    if decision_evidence.as_of_unix_ms < paper_checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "shadow BUY authority decision predates durable PAPER state"
        )


def _require_buy_risk_context_matches_checkpoint(
    paper_checkpoint: FastPaperCheckpointRecord,
    risk: RiskContext,
    *,
    day_started_at_unix_ms: int,
) -> None:
    ledger = paper_checkpoint.state.ledger
    if risk.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "BUY risk trading capital must equal isolated ledger starting cash"
        )
    if risk.active_intent_keys:
        raise ValueError(
            "BUY authority source cannot claim external active intents"
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


def _record_filename(
    decision_evidence_fingerprint_sha256: str,
) -> str:
    _require_sha256_value(
        "decision_evidence_fingerprint_sha256",
        decision_evidence_fingerprint_sha256,
    )
    return f"{decision_evidence_fingerprint_sha256}.json"


def _record_fingerprint(
    record: FastPaperShadowBuyAuthoritySourceRecord,
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
                    "decision_evidence_fingerprint_sha256": (
                        record.decision_evidence_fingerprint_sha256
                    ),
                    "source_event_id": record.source_event_id,
                    "market_key": record.market_key,
                    "mint": record.mint,
                    "quote_mint": record.quote_mint,
                    "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
                    "risk_day_started_at_unix_ms": (
                        record.risk_day_started_at_unix_ms
                    ),
                    "source_observed_at_unix_ms": (
                        record.source_observed_at_unix_ms
                    ),
                    "entry_authority": record.entry_authority,
                    "risk_context": record.risk_context,
                    "market_regime": record.market_regime,
                    "source_version": record.source_version,
                    "source_fingerprint_sha256": (
                        record.source_fingerprint_sha256
                    ),
                }
            )
        )
    ).hexdigest()


def _document(
    record: FastPaperShadowBuyAuthoritySourceRecord,
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
            "decision_evidence_fingerprint_sha256": (
                record.decision_evidence_fingerprint_sha256
            ),
            "source_event_id": record.source_event_id,
            "market_key": record.market_key,
            "mint": record.mint,
            "quote_mint": record.quote_mint,
            "evaluated_at_unix_ms": record.evaluated_at_unix_ms,
            "risk_day_started_at_unix_ms": (
                record.risk_day_started_at_unix_ms
            ),
            "source_observed_at_unix_ms": (
                record.source_observed_at_unix_ms
            ),
            "entry_authority": record.entry_authority,
            "risk_context": record.risk_context,
            "market_regime": record.market_regime,
            "source_version": record.source_version,
            "source_fingerprint_sha256": (
                record.source_fingerprint_sha256
            ),
        }
    )
    document["record_fingerprint_sha256"] = record.record_fingerprint_sha256
    return document


def _document_values(
    values: dict[str, object],
) -> dict[str, object]:
    entry = values["entry_authority"]
    risk = values["risk_context"]
    regime = values["market_regime"]
    if type(entry) is not FastCampaignPaperEntryAuthority:
        raise ValueError(
            "shadow BUY authority source requires exact entry authority"
        )
    if type(risk) is not RiskContext:
        raise ValueError(
            "shadow BUY authority source requires exact risk context"
        )
    if type(regime) is not MarketRegime:
        raise ValueError(
            "shadow BUY authority source requires exact market regime"
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
        "entry_authority": _encode_entry_authority(entry),
        "risk_context": _encode_risk_context(risk),
        "market_regime": regime.value,
        "source_version": values["source_version"],
        "source_fingerprint_sha256": values[
            "source_fingerprint_sha256"
        ],
    }


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
