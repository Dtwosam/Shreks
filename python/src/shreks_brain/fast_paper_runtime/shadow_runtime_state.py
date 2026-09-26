from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .models import FastPaperRuntimeManifest
from .shadow_ledger import (
    FastPaperShadowLedgerBinding,
    load_latest_fast_paper_shadow_ledger_checkpoint,
)


FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_runtime_state"
)
FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION = 2

_TABLE_NAME = "fast_paper_shadow_runtime_states"
_STATE_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "pending_buy",
        "market_positions",
        "last_processed_source_sequence",
        "last_processed_source_event_id",
        "last_processed_decision_evidence_fingerprint_sha256",
        "state_fingerprint_sha256",
    }
)
_PENDING_BUY_KEYS = frozenset(
    {
        "market_key",
        "mint",
        "source_event_id",
        "target_exposure_fraction_hex",
    }
)
_POSITION_KEYS = frozenset(
    {
        "market_key",
        "position_id",
        "mint",
        "current_exposure_fraction_hex",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowPendingBuy:
    market_key: str
    mint: str
    source_event_id: str
    target_exposure_fraction: float

    def __post_init__(self) -> None:
        for name in ("market_key", "mint", "source_event_id"):
            _require_text(name, getattr(self, name))
        _require_exposure(
            "target_exposure_fraction",
            self.target_exposure_fraction,
        )
        object.__setattr__(
            self,
            "target_exposure_fraction",
            float(self.target_exposure_fraction),
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowMarketPosition:
    market_key: str
    position_id: str
    mint: str
    current_exposure_fraction: float

    def __post_init__(self) -> None:
        for name in ("market_key", "position_id", "mint"):
            _require_text(name, getattr(self, name))
        _require_exposure(
            "current_exposure_fraction",
            self.current_exposure_fraction,
        )
        object.__setattr__(
            self,
            "current_exposure_fraction",
            float(self.current_exposure_fraction),
        )


@dataclass(frozen=True, slots=True)
class FastPaperShadowRuntimeState:
    schema_name: str
    schema_version: int
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    pending_buy: FastPaperShadowPendingBuy | None
    market_positions: tuple[FastPaperShadowMarketPosition, ...]
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    last_processed_decision_evidence_fingerprint_sha256: str | None
    state_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_NAME:
            raise ValueError(
                "shadow runtime state schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow runtime state schema_version is incompatible"
            )
        _require_sha256(
            "binding_fingerprint_sha256",
            self.binding_fingerprint_sha256,
        )
        _require_sha256(
            "execution_policy_fingerprint_sha256",
            self.execution_policy_fingerprint_sha256,
        )
        _require_non_negative_int(
            "paper_checkpoint_sequence",
            self.paper_checkpoint_sequence,
        )
        _require_sha256(
            "paper_checkpoint_payload_sha256",
            self.paper_checkpoint_payload_sha256,
        )
        if (
            self.pending_buy is not None
            and type(self.pending_buy) is not FastPaperShadowPendingBuy
        ):
            raise ValueError(
                "pending_buy must be exact FastPaperShadowPendingBuy or None"
            )
        if (
            not isinstance(self.market_positions, tuple)
            or not all(
                type(value) is FastPaperShadowMarketPosition
                for value in self.market_positions
            )
        ):
            raise ValueError(
                "market_positions must contain exact FastPaperShadowMarketPosition values"
            )

        market_keys = tuple(
            value.market_key for value in self.market_positions
        )
        if market_keys != tuple(sorted(market_keys)):
            raise ValueError(
                "shadow runtime market positions must use canonical market-key order"
            )
        if len(market_keys) != len(set(market_keys)):
            raise ValueError(
                "shadow runtime market position keys must be unique"
            )
        position_ids = tuple(
            value.position_id for value in self.market_positions
        )
        if len(position_ids) != len(set(position_ids)):
            raise ValueError(
                "shadow runtime position IDs must be unique"
            )

        identity = (
            self.last_processed_source_sequence,
            self.last_processed_source_event_id,
            self.last_processed_decision_evidence_fingerprint_sha256,
        )
        if any(value is None for value in identity):
            if any(value is not None for value in identity):
                raise ValueError(
                    "last processed decision identity fields must be all present or all absent"
                )
        else:
            _require_positive_int(
                "last_processed_source_sequence",
                self.last_processed_source_sequence,
            )
            _require_text(
                "last_processed_source_event_id",
                self.last_processed_source_event_id,
            )
            _require_sha256(
                "last_processed_decision_evidence_fingerprint_sha256",
                self.last_processed_decision_evidence_fingerprint_sha256,
            )

        _require_sha256(
            "state_fingerprint_sha256",
            self.state_fingerprint_sha256,
        )
        if (
            _state_fingerprint(self)
            != self.state_fingerprint_sha256
        ):
            raise ValueError(
                "shadow runtime state fingerprint mismatch"
            )


def build_fast_paper_shadow_runtime_state(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    paper_checkpoint: FastPaperCheckpointRecord,
    *,
    market_positions: tuple[FastPaperShadowMarketPosition, ...],
    execution_policy_fingerprint_sha256: str,
    pending_buy: FastPaperShadowPendingBuy | None = None,
    last_processed_source_sequence: int | None = None,
    last_processed_source_event_id: str | None = None,
    last_processed_decision_evidence_fingerprint_sha256: str | None = None,
) -> FastPaperShadowRuntimeState:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    if type(paper_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    _require_sha256(
        "execution_policy_fingerprint_sha256",
        execution_policy_fingerprint_sha256,
    )
    if (
        pending_buy is not None
        and type(pending_buy) is not FastPaperShadowPendingBuy
    ):
        raise ValueError(
            "pending_buy must be exact FastPaperShadowPendingBuy or None"
        )
    if (
        not isinstance(market_positions, tuple)
        or not all(
            type(value) is FastPaperShadowMarketPosition
            for value in market_positions
        )
    ):
        raise ValueError(
            "market_positions must contain exact FastPaperShadowMarketPosition values"
        )

    latest = _require_latest_checkpoint(
        manifest,
        binding,
        expected=paper_checkpoint,
    )
    canonical_positions = tuple(
        sorted(
            market_positions,
            key=lambda value: value.market_key,
        )
    )
    _validate_market_positions(
        latest,
        canonical_positions,
    )
    _validate_pending_buy(
        latest,
        pending_buy,
        canonical_positions,
    )

    values = {
        "schema_name": FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            execution_policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": latest.sequence,
        "paper_checkpoint_payload_sha256": latest.payload_sha256,
        "pending_buy": pending_buy,
        "market_positions": canonical_positions,
        "last_processed_source_sequence": (
            last_processed_source_sequence
        ),
        "last_processed_source_event_id": (
            last_processed_source_event_id
        ),
        "last_processed_decision_evidence_fingerprint_sha256": (
            last_processed_decision_evidence_fingerprint_sha256
        ),
    }
    fingerprint = hashlib.sha256(
        _canonical(_fingerprint_material(values)).encode("utf-8")
    ).hexdigest()
    return FastPaperShadowRuntimeState(
        **values,
        state_fingerprint_sha256=fingerprint,
    )


def fast_paper_shadow_decision_position(
    state: FastPaperShadowRuntimeState,
    market_key: str,
) -> FastCampaignDecisionPosition:
    if type(state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "state must be exact FastPaperShadowRuntimeState"
        )
    _require_text("market_key", market_key)
    position = next(
        (
            value
            for value in state.market_positions
            if value.market_key == market_key
        ),
        None,
    )
    if position is None:
        return FastCampaignDecisionPosition(kind="FLAT")
    return FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=(
            position.current_exposure_fraction
        ),
    )


def save_fast_paper_shadow_runtime_state(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    state: FastPaperShadowRuntimeState,
    *,
    created_at_unix_ms: int,
) -> FastPaperShadowRuntimeState:
    if type(state) is not FastPaperShadowRuntimeState:
        raise ValueError(
            "state must be exact FastPaperShadowRuntimeState"
        )
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    latest = _require_latest_checkpoint(
        manifest,
        binding,
    )
    _validate_state_against_checkpoint(
        state,
        binding,
        latest,
    )
    if created_at_unix_ms < latest.state_as_of_unix_ms:
        raise ValueError(
            "shadow runtime state creation time cannot precede paper checkpoint state"
        )

    payload = _canonical(_state_document(state))
    payload_sha256 = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    database = _database_path(binding)
    connection = _connect(database)
    try:
        _ensure_table(connection)
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            f"""
            SELECT
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM {_TABLE_NAME}
            WHERE run_id = ? AND paper_checkpoint_sequence = ?
            """,
            (
                binding.run_id,
                state.paper_checkpoint_sequence,
            ),
        ).fetchone()
        expected_row = (
            state.paper_checkpoint_payload_sha256,
            state.schema_version,
            created_at_unix_ms,
            payload_sha256,
            payload,
        )
        if existing is not None:
            if existing == expected_row:
                connection.rollback()
                return state
            connection.rollback()
            raise ValueError(
                "shadow runtime state checkpoint sequence collision"
            )

        previous_row = connection.execute(
            f"""
            SELECT paper_checkpoint_sequence, payload_json
            FROM {_TABLE_NAME}
            WHERE run_id = ?
            ORDER BY paper_checkpoint_sequence DESC
            LIMIT 1
            """,
            (binding.run_id,),
        ).fetchone()
        previous = None if previous_row is None else previous_row[0]
        if previous_row is not None:
            previous_payload = previous_row[1]
            if not isinstance(previous_payload, str):
                connection.rollback()
                raise ValueError(
                    "previous shadow runtime state payload must be text"
                )
            previous_state = _decode_state(previous_payload)
            if (
                previous_state.execution_policy_fingerprint_sha256
                != state.execution_policy_fingerprint_sha256
            ):
                connection.rollback()
                raise ValueError(
                    "shadow runtime execution policy fingerprint cannot change within a run"
                )
        if (
            previous is not None
            and state.paper_checkpoint_sequence < previous
        ):
            connection.rollback()
            raise ValueError(
                "shadow runtime state checkpoint sequence regressed"
            )

        connection.execute(
            f"""
            INSERT INTO {_TABLE_NAME}(
                run_id,
                paper_checkpoint_sequence,
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                binding.run_id,
                state.paper_checkpoint_sequence,
                state.paper_checkpoint_payload_sha256,
                state.schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload,
            ),
        )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()

    os.chmod(database, 0o600)
    return state


def load_latest_fast_paper_shadow_runtime_state(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
) -> FastPaperShadowRuntimeState | None:
    latest = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest is None:
        return None

    database = _database_path(binding)
    connection = _connect(database)
    try:
        _require_table(connection)
        row = connection.execute(
            f"""
            SELECT
                paper_checkpoint_sequence,
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM {_TABLE_NAME}
            WHERE run_id = ?
            ORDER BY paper_checkpoint_sequence DESC
            LIMIT 1
            """,
            (binding.run_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise ValueError(
            "shadow runtime state is missing for the latest paper checkpoint"
        )

    sequence = row[0]
    checkpoint_sha = row[1]
    schema_version = row[2]
    created_at_unix_ms = row[3]
    payload_sha256 = row[4]
    payload = row[5]

    _require_non_negative_int(
        "stored paper checkpoint sequence",
        sequence,
    )
    _require_sha256(
        "stored paper checkpoint payload SHA-256",
        checkpoint_sha,
    )
    if schema_version != FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION:
        raise ValueError(
            "stored shadow runtime state schema version is incompatible"
        )
    _require_non_negative_int(
        "stored shadow runtime creation time",
        created_at_unix_ms,
    )
    _require_sha256(
        "stored shadow runtime payload SHA-256",
        payload_sha256,
    )
    if not isinstance(payload, str):
        raise ValueError(
            "stored shadow runtime state payload must be text"
        )
    actual_payload_sha256 = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    if actual_payload_sha256 != payload_sha256:
        raise ValueError(
            "shadow runtime state payload checksum mismatch"
        )

    state = _decode_state(payload)
    if (
        state.paper_checkpoint_sequence != sequence
        or state.paper_checkpoint_payload_sha256 != checkpoint_sha
        or state.schema_version != schema_version
    ):
        raise ValueError(
            "shadow runtime state row metadata does not match payload"
        )
    if created_at_unix_ms < latest.state_as_of_unix_ms:
        raise ValueError(
            "shadow runtime state creation time precedes paper checkpoint state"
        )

    latest_after = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest_after is None or latest_after != latest:
        raise ValueError(
            "paper checkpoint advanced while shadow runtime state was loading"
        )

    _validate_state_against_checkpoint(
        state,
        binding,
        latest_after,
    )
    return state


def _require_latest_checkpoint(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    *,
    expected: FastPaperCheckpointRecord | None = None,
) -> FastPaperCheckpointRecord:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    latest = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )
    if latest is None:
        raise ValueError(
            "shadow runtime state requires a persisted paper checkpoint"
        )
    if expected is not None and latest != expected:
        raise ValueError(
            "shadow runtime state must bind the exact latest paper checkpoint"
        )
    return latest


def _validate_state_against_checkpoint(
    state: FastPaperShadowRuntimeState,
    binding: FastPaperShadowLedgerBinding,
    checkpoint: FastPaperCheckpointRecord,
) -> None:
    if (
        state.binding_fingerprint_sha256
        != binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "shadow runtime state binding fingerprint mismatch"
        )
    if (
        state.paper_checkpoint_sequence != checkpoint.sequence
        or state.paper_checkpoint_payload_sha256
        != checkpoint.payload_sha256
    ):
        raise ValueError(
            "shadow runtime state is torn from the latest paper checkpoint"
        )
    _validate_market_positions(
        checkpoint,
        state.market_positions,
    )
    _validate_pending_buy(
        checkpoint,
        state.pending_buy,
        state.market_positions,
    )


def _validate_pending_buy(
    checkpoint: FastPaperCheckpointRecord,
    pending_buy: FastPaperShadowPendingBuy | None,
    market_positions: tuple[FastPaperShadowMarketPosition, ...],
) -> None:
    approval = checkpoint.state.pending_buy
    if approval is None:
        if pending_buy is not None:
            raise ValueError(
                "shadow runtime pending BUY exists without canonical checkpoint authority"
            )
        return
    if pending_buy is None:
        raise ValueError(
            "shadow runtime pending BUY target is missing for canonical checkpoint authority"
        )
    expected = (
        approval.assessment.market_key,
        approval.mint,
        approval.assessment.source_event_id,
    )
    actual = (
        pending_buy.market_key,
        pending_buy.mint,
        pending_buy.source_event_id,
    )
    if actual != expected:
        raise ValueError(
            "shadow runtime pending BUY identity does not match canonical checkpoint authority"
        )
    if any(
        value.market_key == pending_buy.market_key
        or value.mint == pending_buy.mint
        for value in market_positions
    ):
        raise ValueError(
            "shadow runtime pending BUY cannot overlap an OPEN market mapping"
        )


def _validate_market_positions(
    checkpoint: FastPaperCheckpointRecord,
    market_positions: tuple[FastPaperShadowMarketPosition, ...],
) -> None:
    open_positions = {
        position.position_id: position
        for position in checkpoint.state.ledger.positions
        if position.state is PaperPositionState.OPEN
    }
    mapped_ids = {
        value.position_id for value in market_positions
    }
    if mapped_ids != set(open_positions):
        raise ValueError(
            "shadow runtime market mapping must exactly cover canonical OPEN positions"
        )

    for mapping in market_positions:
        position = open_positions.get(mapping.position_id)
        if position is None:
            raise ValueError(
                "shadow runtime mapping references a non-OPEN position"
            )
        if mapping.mint != position.mint:
            raise ValueError(
                "shadow runtime mapping mint does not match canonical position mint"
            )


def _state_document(
    state: FastPaperShadowRuntimeState,
) -> dict[str, object]:
    document = _fingerprint_material(
        {
            "schema_name": state.schema_name,
            "schema_version": state.schema_version,
            "binding_fingerprint_sha256": (
                state.binding_fingerprint_sha256
            ),
            "execution_policy_fingerprint_sha256": (
                state.execution_policy_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": (
                state.paper_checkpoint_sequence
            ),
            "paper_checkpoint_payload_sha256": (
                state.paper_checkpoint_payload_sha256
            ),
            "pending_buy": state.pending_buy,
            "market_positions": state.market_positions,
            "last_processed_source_sequence": (
                state.last_processed_source_sequence
            ),
            "last_processed_source_event_id": (
                state.last_processed_source_event_id
            ),
            "last_processed_decision_evidence_fingerprint_sha256": (
                state.last_processed_decision_evidence_fingerprint_sha256
            ),
        }
    )
    document["state_fingerprint_sha256"] = (
        state.state_fingerprint_sha256
    )
    if frozenset(document) != _STATE_KEYS:
        raise ValueError(
            "shadow runtime state document is incomplete"
        )
    return document


def _fingerprint_material(
    values: dict[str, object],
) -> dict[str, object]:
    pending_buy = values["pending_buy"]
    positions = values["market_positions"]
    if not isinstance(positions, tuple):
        raise ValueError(
            "shadow runtime fingerprint positions must be a tuple"
        )
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "binding_fingerprint_sha256": (
            values["binding_fingerprint_sha256"]
        ),
        "execution_policy_fingerprint_sha256": (
            values["execution_policy_fingerprint_sha256"]
        ),
        "paper_checkpoint_sequence": (
            values["paper_checkpoint_sequence"]
        ),
        "paper_checkpoint_payload_sha256": (
            values["paper_checkpoint_payload_sha256"]
        ),
        "pending_buy": (
            None
            if pending_buy is None
            else {
                "market_key": pending_buy.market_key,
                "mint": pending_buy.mint,
                "source_event_id": pending_buy.source_event_id,
                "target_exposure_fraction_hex": (
                    pending_buy.target_exposure_fraction.hex()
                ),
            }
        ),
        "market_positions": [
            {
                "market_key": value.market_key,
                "position_id": value.position_id,
                "mint": value.mint,
                "current_exposure_fraction_hex": (
                    value.current_exposure_fraction.hex()
                ),
            }
            for value in positions
        ],
        "last_processed_source_sequence": (
            values["last_processed_source_sequence"]
        ),
        "last_processed_source_event_id": (
            values["last_processed_source_event_id"]
        ),
        "last_processed_decision_evidence_fingerprint_sha256": (
            values[
                "last_processed_decision_evidence_fingerprint_sha256"
            ]
        ),
    }


def _state_fingerprint(
    state: FastPaperShadowRuntimeState,
) -> str:
    material = _state_document_without_fingerprint(state)
    return hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()


def _state_document_without_fingerprint(
    state: FastPaperShadowRuntimeState,
) -> dict[str, object]:
    return _fingerprint_material(
        {
            "schema_name": state.schema_name,
            "schema_version": state.schema_version,
            "binding_fingerprint_sha256": (
                state.binding_fingerprint_sha256
            ),
            "execution_policy_fingerprint_sha256": (
                state.execution_policy_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": (
                state.paper_checkpoint_sequence
            ),
            "paper_checkpoint_payload_sha256": (
                state.paper_checkpoint_payload_sha256
            ),
            "pending_buy": state.pending_buy,
            "market_positions": state.market_positions,
            "last_processed_source_sequence": (
                state.last_processed_source_sequence
            ),
            "last_processed_source_event_id": (
                state.last_processed_source_event_id
            ),
            "last_processed_decision_evidence_fingerprint_sha256": (
                state.last_processed_decision_evidence_fingerprint_sha256
            ),
        }
    )


def _decode_state(payload: str) -> FastPaperShadowRuntimeState:
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "shadow runtime state payload is invalid JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "shadow runtime state payload must be an object"
        )
    if frozenset(document) != _STATE_KEYS:
        raise ValueError(
            "shadow runtime state payload has unknown or missing fields"
        )
    if payload != _canonical(document):
        raise ValueError(
            "shadow runtime state payload must use canonical JSON"
        )

    raw_pending = document["pending_buy"]
    pending_buy = None
    if raw_pending is not None:
        if (
            not isinstance(raw_pending, dict)
            or frozenset(raw_pending) != _PENDING_BUY_KEYS
        ):
            raise ValueError(
                "shadow runtime pending BUY payload is malformed"
            )
        exposure_hex = raw_pending["target_exposure_fraction_hex"]
        if not isinstance(exposure_hex, str):
            raise ValueError(
                "shadow runtime pending BUY exposure must use canonical float hex"
            )
        try:
            target_exposure = float.fromhex(exposure_hex)
        except ValueError as exc:
            raise ValueError(
                "shadow runtime pending BUY exposure hex is invalid"
            ) from exc
        if target_exposure.hex() != exposure_hex:
            raise ValueError(
                "shadow runtime pending BUY exposure hex is not canonical"
            )
        pending_buy = FastPaperShadowPendingBuy(
            market_key=raw_pending["market_key"],
            mint=raw_pending["mint"],
            source_event_id=raw_pending["source_event_id"],
            target_exposure_fraction=target_exposure,
        )

    raw_positions = document["market_positions"]
    if not isinstance(raw_positions, list):
        raise ValueError(
            "shadow runtime market positions must be a JSON array"
        )
    positions = []
    for raw in raw_positions:
        if not isinstance(raw, dict) or frozenset(raw) != _POSITION_KEYS:
            raise ValueError(
                "shadow runtime market position payload is malformed"
            )
        exposure_hex = raw["current_exposure_fraction_hex"]
        if not isinstance(exposure_hex, str):
            raise ValueError(
                "shadow runtime exposure must use canonical float hex"
            )
        try:
            exposure = float.fromhex(exposure_hex)
        except ValueError as exc:
            raise ValueError(
                "shadow runtime exposure hex is invalid"
            ) from exc
        if exposure.hex() != exposure_hex:
            raise ValueError(
                "shadow runtime exposure hex is not canonical"
            )
        positions.append(
            FastPaperShadowMarketPosition(
                market_key=raw["market_key"],
                position_id=raw["position_id"],
                mint=raw["mint"],
                current_exposure_fraction=exposure,
            )
        )

    try:
        return FastPaperShadowRuntimeState(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            binding_fingerprint_sha256=(
                document["binding_fingerprint_sha256"]
            ),
            execution_policy_fingerprint_sha256=(
                document["execution_policy_fingerprint_sha256"]
            ),
            paper_checkpoint_sequence=(
                document["paper_checkpoint_sequence"]
            ),
            paper_checkpoint_payload_sha256=(
                document["paper_checkpoint_payload_sha256"]
            ),
            pending_buy=pending_buy,
            market_positions=tuple(positions),
            last_processed_source_sequence=(
                document["last_processed_source_sequence"]
            ),
            last_processed_source_event_id=(
                document["last_processed_source_event_id"]
            ),
            last_processed_decision_evidence_fingerprint_sha256=(
                document[
                    "last_processed_decision_evidence_fingerprint_sha256"
                ]
            ),
            state_fingerprint_sha256=(
                document["state_fingerprint_sha256"]
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "shadow runtime state payload content is incompatible"
        ) from exc


def _database_path(
    binding: FastPaperShadowLedgerBinding,
) -> Path:
    database = Path(binding.database_path)
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "shadow runtime state database must be an existing regular non-symlink file"
        )
    return database


def _connect(database: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow runtime state database could not be opened"
        ) from exc


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
            run_id TEXT NOT NULL,
            paper_checkpoint_sequence INTEGER NOT NULL
                CHECK (paper_checkpoint_sequence >= 0),
            paper_checkpoint_payload_sha256 TEXT NOT NULL
                CHECK (length(paper_checkpoint_payload_sha256) = 64),
            state_schema_version INTEGER NOT NULL,
            created_at_unix_ms INTEGER NOT NULL
                CHECK (created_at_unix_ms >= 0),
            payload_sha256 TEXT NOT NULL
                CHECK (length(payload_sha256) = 64),
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, paper_checkpoint_sequence)
        );
        CREATE INDEX IF NOT EXISTS
            idx_fast_paper_shadow_runtime_states_run_latest
            ON {_TABLE_NAME} (run_id, paper_checkpoint_sequence DESC);
        """
    )
    connection.commit()


def _require_table(connection: sqlite3.Connection) -> None:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (_TABLE_NAME,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow runtime state storage schema read failed"
        ) from exc
    if row is None:
        raise ValueError(
            "shadow runtime state storage is missing for the latest paper checkpoint"
        )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(
                "shadow runtime state JSON contains duplicate keys"
            )
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError(
        f"shadow runtime state JSON contains invalid constant {value}"
    )


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{name} must be a positive integer"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_exposure(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) <= 1.0
    ):
        raise ValueError(
            f"{name} must be finite and within (0,1]"
        )
