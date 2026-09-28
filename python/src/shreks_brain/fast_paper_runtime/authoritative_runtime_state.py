from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Mapping

from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import (
    FastPaperCheckpointRecord,
    load_latest_fast_paper_checkpoint,
)

from .codec import verify_fast_paper_runtime_bindings
from .models import FastPaperRuntimeManifest

if TYPE_CHECKING:
    from .authoritative_handoff import FastPaperAuthoritativeBinding


FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_NAME = (
    "shreks.fast_paper_authoritative_runtime_state"
)
FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_VERSION = 1
FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE = (
    "fast_paper_authoritative_runtime_states"
)

_STATE_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "binding_fingerprint_sha256",
        "execution_policy_fingerprint_sha256",
        "paper_checkpoint_sequence",
        "paper_checkpoint_payload_sha256",
        "market_positions",
        "last_processed_source_sequence",
        "last_processed_source_event_id",
        "last_processed_decision_evidence_fingerprint_sha256",
        "state_fingerprint_sha256",
    }
)
_POSITION_FIELDS = frozenset(
    {
        "market_key",
        "position_id",
        "mint",
        "current_exposure_fraction",
        "current_base_quantity_raw",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeMarketPosition:
    market_key: str
    position_id: str
    mint: str
    current_exposure_fraction: float
    current_base_quantity_raw: int

    def __post_init__(self) -> None:
        for name in ("market_key", "position_id", "mint"):
            _require_text(name, getattr(self, name))
        if (
            isinstance(self.current_exposure_fraction, bool)
            or not isinstance(
                self.current_exposure_fraction,
                (int, float),
            )
            or not math.isfinite(float(self.current_exposure_fraction))
            or not 0.0 < float(self.current_exposure_fraction) <= 1.0
        ):
            raise ValueError(
                "current_exposure_fraction must be finite within (0,1]"
            )
        object.__setattr__(
            self,
            "current_exposure_fraction",
            float(self.current_exposure_fraction),
        )
        _require_positive_int(
            "current_base_quantity_raw",
            self.current_base_quantity_raw,
        )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeRuntimeState:
    schema_name: str
    schema_version: int
    binding_fingerprint_sha256: str
    execution_policy_fingerprint_sha256: str
    paper_checkpoint_sequence: int
    paper_checkpoint_payload_sha256: str
    market_positions: tuple[FastPaperAuthoritativeMarketPosition, ...]
    last_processed_source_sequence: int | None
    last_processed_source_event_id: str | None
    last_processed_decision_evidence_fingerprint_sha256: str | None
    state_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_NAME
        ):
            raise ValueError(
                "authoritative runtime state schema_name is incompatible"
            )
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_VERSION
        ):
            raise ValueError(
                "authoritative runtime state schema_version is incompatible"
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
            not isinstance(self.market_positions, tuple)
            or not all(
                type(value) is FastPaperAuthoritativeMarketPosition
                for value in self.market_positions
            )
        ):
            raise ValueError(
                "market_positions must contain exact FastPaperAuthoritativeMarketPosition values"
            )
        market_keys = tuple(
            value.market_key for value in self.market_positions
        )
        if market_keys != tuple(sorted(market_keys)):
            raise ValueError(
                "authoritative runtime market positions must use canonical market-key order"
            )
        if len(market_keys) != len(set(market_keys)):
            raise ValueError(
                "authoritative runtime market position keys must be unique"
            )
        position_ids = tuple(
            value.position_id for value in self.market_positions
        )
        if len(position_ids) != len(set(position_ids)):
            raise ValueError(
                "authoritative runtime position IDs must be unique"
            )

        identity = (
            self.last_processed_source_sequence,
            self.last_processed_source_event_id,
            self.last_processed_decision_evidence_fingerprint_sha256,
        )
        if any(value is None for value in identity):
            if any(value is not None for value in identity):
                raise ValueError(
                    "last processed learned identity fields must be all present or all absent"
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
                "authoritative runtime state fingerprint mismatch"
            )


def build_fast_paper_authoritative_runtime_state(
    manifest: FastPaperRuntimeManifest,
    binding: object,
    paper_checkpoint: FastPaperCheckpointRecord,
    *,
    market_positions: tuple[FastPaperAuthoritativeMarketPosition, ...],
    execution_policy_fingerprint_sha256: str,
    last_processed_source_sequence: int | None = None,
    last_processed_source_event_id: str | None = None,
    last_processed_decision_evidence_fingerprint_sha256: str | None = None,
) -> FastPaperAuthoritativeRuntimeState:
    _require_manifest_binding(manifest, binding)
    if type(paper_checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "paper_checkpoint must be exact FastPaperCheckpointRecord"
        )
    if paper_checkpoint.run_id != getattr(binding, "fast_run_id"):
        raise ValueError(
            "authoritative runtime checkpoint run_id does not match binding"
        )
    _require_sha256(
        "execution_policy_fingerprint_sha256",
        execution_policy_fingerprint_sha256,
    )
    if (
        execution_policy_fingerprint_sha256
        != getattr(binding, "execution_policy_fingerprint_sha256")
    ):
        raise ValueError(
            "authoritative runtime execution policy fingerprint mismatch"
        )
    if (
        not isinstance(market_positions, tuple)
        or not all(
            type(value) is FastPaperAuthoritativeMarketPosition
            for value in market_positions
        )
    ):
        raise ValueError(
            "market_positions must contain exact FastPaperAuthoritativeMarketPosition values"
        )

    canonical_positions = tuple(
        sorted(market_positions, key=lambda value: value.market_key)
    )
    _validate_market_positions(
        paper_checkpoint,
        canonical_positions,
    )
    _validate_last_processed_identity(
        paper_checkpoint,
        last_processed_source_sequence=last_processed_source_sequence,
        last_processed_source_event_id=last_processed_source_event_id,
        last_processed_decision_evidence_fingerprint_sha256=(
            last_processed_decision_evidence_fingerprint_sha256
        ),
    )

    values: dict[str, object] = {
        "schema_name": FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_NAME,
        "schema_version": FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_VERSION,
        "binding_fingerprint_sha256": getattr(
            binding,
            "binding_fingerprint_sha256",
        ),
        "execution_policy_fingerprint_sha256": (
            execution_policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": paper_checkpoint.sequence,
        "paper_checkpoint_payload_sha256": (
            paper_checkpoint.payload_sha256
        ),
        "market_positions": canonical_positions,
        "last_processed_source_sequence": last_processed_source_sequence,
        "last_processed_source_event_id": last_processed_source_event_id,
        "last_processed_decision_evidence_fingerprint_sha256": (
            last_processed_decision_evidence_fingerprint_sha256
        ),
    }
    material = _state_document_from_values(values)
    fingerprint = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    return FastPaperAuthoritativeRuntimeState(
        **values,
        state_fingerprint_sha256=fingerprint,
    )


def load_latest_fast_paper_authoritative_runtime_state(
    manifest: FastPaperRuntimeManifest,
    binding: object,
) -> FastPaperAuthoritativeRuntimeState:
    _require_manifest_binding(manifest, binding)
    database = _database_path(binding)
    connection = _connect(database)
    try:
        _require_runtime_table(connection)
        row = connection.execute(
            f"""
            SELECT
                paper_checkpoint_sequence,
                paper_checkpoint_payload_sha256,
                state_schema_version,
                created_at_unix_ms,
                payload_sha256,
                payload_json
            FROM {FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE}
            WHERE fast_run_id = ?
            ORDER BY paper_checkpoint_sequence DESC
            LIMIT 1
            """,
            (getattr(binding, "fast_run_id"),),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(
            "authoritative runtime state is missing"
        )
    state = _decode_stored_row(row)
    _require_state_binding(binding, state)

    latest = load_latest_fast_paper_checkpoint(
        database,
        getattr(binding, "fast_run_id"),
    )
    if latest is None:
        raise ValueError(
            "authoritative Fast PAPER checkpoint is missing"
        )
    if (
        state.paper_checkpoint_sequence != latest.sequence
        or state.paper_checkpoint_payload_sha256
        != latest.payload_sha256
    ):
        raise ValueError(
            "authoritative checkpoint/runtime pair is torn"
        )
    _validate_market_positions(latest, state.market_positions)
    _validate_last_processed_identity(
        latest,
        last_processed_source_sequence=(
            state.last_processed_source_sequence
        ),
        last_processed_source_event_id=(
            state.last_processed_source_event_id
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            state.last_processed_decision_evidence_fingerprint_sha256
        ),
    )
    return state


def encode_fast_paper_authoritative_runtime_state(
    state: FastPaperAuthoritativeRuntimeState,
) -> str:
    if type(state) is not FastPaperAuthoritativeRuntimeState:
        raise ValueError(
            "state must be exact FastPaperAuthoritativeRuntimeState"
        )
    return _canonical(_state_document(state))


def decode_fast_paper_authoritative_runtime_state(
    payload: str,
) -> FastPaperAuthoritativeRuntimeState:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "authoritative runtime state payload must be non-empty text"
        )
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "authoritative runtime state JSON is invalid"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "authoritative runtime state must be a JSON object"
        )
    if frozenset(document) != _STATE_FIELDS:
        raise ValueError(
            "authoritative runtime state has unknown or missing fields"
        )
    if payload != _canonical(document):
        raise ValueError(
            "authoritative runtime state must use canonical JSON"
        )
    positions_raw = document["market_positions"]
    if not isinstance(positions_raw, list):
        raise ValueError(
            "authoritative runtime market_positions must be an array"
        )
    positions: list[FastPaperAuthoritativeMarketPosition] = []
    for value in positions_raw:
        if not isinstance(value, dict) or frozenset(value) != _POSITION_FIELDS:
            raise ValueError(
                "authoritative runtime market position is malformed"
            )
        positions.append(
            FastPaperAuthoritativeMarketPosition(**value)
        )
    values = dict(document)
    values["market_positions"] = tuple(positions)
    try:
        return FastPaperAuthoritativeRuntimeState(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "authoritative runtime state content is incompatible"
        ) from exc


def _ensure_authoritative_runtime_state_table(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS
            {FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE} (
                fast_run_id TEXT NOT NULL,
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
                PRIMARY KEY (
                    fast_run_id,
                    paper_checkpoint_sequence
                )
            )
        """
    )


def _insert_runtime_state_row(
    connection: sqlite3.Connection,
    binding: object,
    state: FastPaperAuthoritativeRuntimeState,
    *,
    created_at_unix_ms: int,
) -> None:
    _require_non_negative_int(
        "created_at_unix_ms",
        created_at_unix_ms,
    )
    _require_state_binding(binding, state)
    payload = encode_fast_paper_authoritative_runtime_state(state)
    payload_sha256 = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    connection.execute(
        f"""
        INSERT INTO {FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE}(
            fast_run_id,
            paper_checkpoint_sequence,
            paper_checkpoint_payload_sha256,
            state_schema_version,
            created_at_unix_ms,
            payload_sha256,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            getattr(binding, "fast_run_id"),
            state.paper_checkpoint_sequence,
            state.paper_checkpoint_payload_sha256,
            state.schema_version,
            created_at_unix_ms,
            payload_sha256,
            payload,
        ),
    )


def _runtime_state_row(
    state: FastPaperAuthoritativeRuntimeState,
    *,
    created_at_unix_ms: int,
) -> tuple[object, ...]:
    payload = encode_fast_paper_authoritative_runtime_state(state)
    return (
        state.paper_checkpoint_sequence,
        state.paper_checkpoint_payload_sha256,
        state.schema_version,
        created_at_unix_ms,
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        payload,
    )


def _decode_stored_row(
    row: tuple[object, ...],
) -> FastPaperAuthoritativeRuntimeState:
    if len(row) != 6:
        raise ValueError(
            "authoritative runtime state row shape is incompatible"
        )
    sequence, checkpoint_sha, schema_version, created_at, payload_sha, payload = row
    _require_non_negative_int(
        "stored paper checkpoint sequence",
        sequence,
    )
    _require_sha256(
        "stored paper checkpoint payload fingerprint",
        checkpoint_sha,
    )
    if (
        type(schema_version) is not int
        or schema_version
        != FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_SCHEMA_VERSION
    ):
        raise ValueError(
            "stored authoritative runtime state schema version is incompatible"
        )
    _require_non_negative_int(
        "stored authoritative runtime created_at_unix_ms",
        created_at,
    )
    _require_sha256(
        "stored authoritative runtime payload fingerprint",
        payload_sha,
    )
    if not isinstance(payload, str):
        raise ValueError(
            "stored authoritative runtime payload must be text"
        )
    if (
        hashlib.sha256(payload.encode("utf-8")).hexdigest()
        != payload_sha
    ):
        raise ValueError(
            "authoritative runtime payload checksum mismatch"
        )
    state = decode_fast_paper_authoritative_runtime_state(payload)
    if (
        state.paper_checkpoint_sequence != sequence
        or state.paper_checkpoint_payload_sha256 != checkpoint_sha
        or state.schema_version != schema_version
    ):
        raise ValueError(
            "authoritative runtime row metadata does not match payload"
        )
    return state


def _validate_market_positions(
    checkpoint: FastPaperCheckpointRecord,
    market_positions: tuple[FastPaperAuthoritativeMarketPosition, ...],
) -> None:
    open_positions = tuple(
        position
        for position in checkpoint.state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    open_by_id = {
        position.position_id: position
        for position in open_positions
    }
    mapped_ids = {
        value.position_id for value in market_positions
    }
    if mapped_ids != set(open_by_id):
        raise ValueError(
            "authoritative runtime market mapping must exactly cover OPEN positions"
        )
    for value in market_positions:
        position = open_by_id[value.position_id]
        if value.mint != position.mint:
            raise ValueError(
                "authoritative runtime market mapping mint does not match OPEN position"
            )


def _validate_last_processed_identity(
    checkpoint: FastPaperCheckpointRecord,
    *,
    last_processed_source_sequence: int | None,
    last_processed_source_event_id: str | None,
    last_processed_decision_evidence_fingerprint_sha256: str | None,
) -> None:
    identity = (
        last_processed_source_sequence,
        last_processed_source_event_id,
        last_processed_decision_evidence_fingerprint_sha256,
    )
    records = checkpoint.state.event_loop_state.records
    if any(value is None for value in identity):
        if any(value is not None for value in identity):
            raise ValueError(
                "last processed learned identity fields must be all present or all absent"
            )
        if records:
            raise ValueError(
                "authoritative runtime state with Fast event records requires the latest learned identity"
            )
        return
    _require_positive_int(
        "last_processed_source_sequence",
        last_processed_source_sequence,
    )
    _require_text(
        "last_processed_source_event_id",
        last_processed_source_event_id,
    )
    _require_sha256(
        "last_processed_decision_evidence_fingerprint_sha256",
        last_processed_decision_evidence_fingerprint_sha256,
    )
    if not records:
        raise ValueError(
            "last processed learned identity is not recorded in Fast PAPER event state"
        )
    latest_sequence = max(record.source_sequence for record in records)
    latest = tuple(
        record
        for record in records
        if record.source_sequence == latest_sequence
    )
    if len(latest) != 1:
        raise ValueError(
            "latest Fast PAPER source sequence is ambiguous"
        )
    record = latest[0]
    if (
        record.source_event_id != last_processed_source_event_id
        or record.source_sequence != last_processed_source_sequence
    ):
        raise ValueError(
            "last processed learned identity does not match the latest recorded Fast event"
        )


def _require_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    binding: object,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    try:
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise ValueError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    required = {
        "fast_run_id": str,
        "binding_fingerprint_sha256": str,
        "execution_policy_fingerprint_sha256": str,
        "release_source_sha": str,
        "manifest_fingerprint_sha256": str,
        "champion_fingerprint_sha256": str,
        "action_policy_version": int,
        "database_path": str,
    }
    for name, kind in required.items():
        value = getattr(binding, name, None)
        if not isinstance(value, kind):
            raise ValueError(
                f"authoritative binding {name} is missing or incompatible"
            )
    _require_text("fast_run_id", getattr(binding, "fast_run_id"))
    _require_sha256(
        "binding_fingerprint_sha256",
        getattr(binding, "binding_fingerprint_sha256"),
    )
    _require_sha256(
        "execution_policy_fingerprint_sha256",
        getattr(binding, "execution_policy_fingerprint_sha256"),
    )
    expected = {
        "release_source_sha": manifest.release_source_sha,
        "manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "action_policy_version": manifest.action_policy.version,
    }
    for name, value in expected.items():
        if getattr(binding, name) != value:
            raise ValueError(
                f"authoritative binding {name} does not match runtime manifest"
            )
    expected_database = Path(
        manifest.observer_database_path
    ).expanduser()
    actual_database = Path(
        getattr(binding, "database_path")
    ).expanduser()
    if (
        expected_database.is_symlink()
        or actual_database.is_symlink()
        or not expected_database.is_file()
        or not actual_database.is_file()
    ):
        raise ValueError(
            "authoritative observer database must be an existing regular non-symlink file"
        )
    try:
        if not actual_database.samefile(expected_database):
            raise ValueError(
                "authoritative binding database does not match runtime manifest"
            )
    except OSError as exc:
        raise ValueError(
            "authoritative observer database identity cannot be resolved"
        ) from exc


def _require_state_binding(
    binding: object,
    state: FastPaperAuthoritativeRuntimeState,
) -> None:
    if type(state) is not FastPaperAuthoritativeRuntimeState:
        raise ValueError(
            "state must be exact FastPaperAuthoritativeRuntimeState"
        )
    if (
        state.binding_fingerprint_sha256
        != getattr(binding, "binding_fingerprint_sha256")
    ):
        raise ValueError(
            "authoritative runtime binding fingerprint mismatch"
        )
    if (
        state.execution_policy_fingerprint_sha256
        != getattr(binding, "execution_policy_fingerprint_sha256")
    ):
        raise ValueError(
            "authoritative runtime execution policy fingerprint mismatch"
        )


def _database_path(binding: object) -> Path:
    path = Path(getattr(binding, "database_path"))
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "authoritative runtime database must be an existing regular non-symlink file"
        )
    return path


def _require_runtime_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (FAST_PAPER_AUTHORITATIVE_RUNTIME_STATE_TABLE,),
    ).fetchone()
    if row is None:
        raise ValueError(
            "authoritative runtime state table is missing"
        )


def _state_fingerprint(
    state: FastPaperAuthoritativeRuntimeState,
) -> str:
    material = _state_document(state)
    material.pop("state_fingerprint_sha256")
    return hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()


def _state_document(
    state: FastPaperAuthoritativeRuntimeState,
) -> dict[str, object]:
    return {
        "schema_name": state.schema_name,
        "schema_version": state.schema_version,
        "binding_fingerprint_sha256": (
            state.binding_fingerprint_sha256
        ),
        "execution_policy_fingerprint_sha256": (
            state.execution_policy_fingerprint_sha256
        ),
        "paper_checkpoint_sequence": state.paper_checkpoint_sequence,
        "paper_checkpoint_payload_sha256": (
            state.paper_checkpoint_payload_sha256
        ),
        "market_positions": [
            _position_document(value)
            for value in state.market_positions
        ],
        "last_processed_source_sequence": (
            state.last_processed_source_sequence
        ),
        "last_processed_source_event_id": (
            state.last_processed_source_event_id
        ),
        "last_processed_decision_evidence_fingerprint_sha256": (
            state.last_processed_decision_evidence_fingerprint_sha256
        ),
        "state_fingerprint_sha256": state.state_fingerprint_sha256,
    }


def _state_document_from_values(
    values: Mapping[str, object],
) -> dict[str, object]:
    positions = values["market_positions"]
    assert isinstance(positions, tuple)
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
        "market_positions": [
            _position_document(value)
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


def _position_document(
    value: FastPaperAuthoritativeMarketPosition,
) -> dict[str, object]:
    return {
        "market_key": value.market_key,
        "position_id": value.position_id,
        "mint": value.mint,
        "current_exposure_fraction": value.current_exposure_fraction,
        "current_base_quantity_raw": value.current_base_quantity_raw,
    }


def _connect(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as exc:
        raise ValueError(
            "authoritative runtime database connection failed"
        ) from exc


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(
            f"{name} must be non-empty trimmed text"
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
