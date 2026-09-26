from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from shreks_brain.fast_paper import (
    FastPaperPositionActionPolicy,
    create_fast_paper_loop_state,
)
from shreks_brain.paper import PaperFillPolicy, create_paper_ledger
from shreks_brain.paper_validation import (
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperCheckpointRecord,
    FastPaperRuntimeState,
    load_latest_fast_paper_checkpoint,
    save_fast_paper_checkpoint,
)

from .models import FastPaperRuntimeManifest


FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_ledger_binding"
)
FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_VERSION = 1

_BINDING_TABLE = "fast_paper_shadow_ledger_bindings"
_CHECKPOINT_TABLE = "paper_loop_checkpoints"
_BINDING_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "run_id",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "state_version",
        "risk_policy_version",
        "fill_policy_version",
        "position_action_policy_version",
        "database_path",
        "binding_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowLedgerBinding:
    schema_name: str
    schema_version: int
    run_id: str
    release_source_sha: str
    manifest_fingerprint_sha256: str
    champion_fingerprint_sha256: str
    action_policy_version: int
    state_version: str
    risk_policy_version: str
    fill_policy_version: str
    position_action_policy_version: str
    database_path: str
    binding_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_NAME:
            raise ValueError("shadow ledger binding schema_name is incompatible")
        if (
            self.schema_version
            != FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_VERSION
        ):
            raise ValueError(
                "shadow ledger binding schema_version is incompatible"
            )
        for name in (
            "run_id",
            "state_version",
            "risk_policy_version",
            "fill_policy_version",
            "position_action_policy_version",
            "database_path",
        ):
            _require_text(name, getattr(self, name))
        _require_source_sha("release_source_sha", self.release_source_sha)
        _require_sha256(
            "manifest_fingerprint_sha256",
            self.manifest_fingerprint_sha256,
        )
        _require_sha256(
            "champion_fingerprint_sha256",
            self.champion_fingerprint_sha256,
        )
        _require_sha256(
            "binding_fingerprint_sha256",
            self.binding_fingerprint_sha256,
        )
        if (
            isinstance(self.action_policy_version, bool)
            or not isinstance(self.action_policy_version, int)
            or self.action_policy_version <= 0
        ):
            raise ValueError(
                "action_policy_version must be a positive integer"
            )
        if not Path(self.database_path).is_absolute():
            raise ValueError("database_path must be absolute")
        if (
            _binding_fingerprint(self)
            != self.binding_fingerprint_sha256
        ):
            raise ValueError("shadow ledger binding fingerprint mismatch")


def build_fast_paper_shadow_ledger_binding(
    manifest: FastPaperRuntimeManifest,
    *,
    run_id: str,
    database_path: str | Path,
) -> FastPaperShadowLedgerBinding:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    _require_text("run_id", run_id)
    database = _shadow_database_path(manifest, database_path)

    provisional = FastPaperShadowLedgerBinding(
        schema_name=FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_VERSION,
        run_id=run_id,
        release_source_sha=manifest.release_source_sha,
        manifest_fingerprint_sha256=(
            manifest.manifest_fingerprint_sha256
        ),
        champion_fingerprint_sha256=(
            manifest.champion_fingerprint_sha256
        ),
        action_policy_version=manifest.action_policy.version,
        state_version=manifest.state_version,
        risk_policy_version=manifest.risk_policy_version,
        fill_policy_version=manifest.fill_policy_version,
        position_action_policy_version=(
            manifest.position_action_policy_version
        ),
        database_path=str(database),
        binding_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        binding_fingerprint_sha256=_binding_fingerprint(provisional),
    )


def initialize_fast_paper_shadow_ledger_database(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
) -> None:
    _require_manifest_binding(manifest, binding)
    database = Path(binding.database_path)
    parent = database.parent
    if parent.is_symlink():
        raise ValueError(
            "shadow ledger database parent must not be a symlink"
        )
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(
            "shadow ledger database parent must remain a regular directory"
        )
    os.chmod(parent, 0o700)

    if database.is_symlink():
        raise ValueError(
            "shadow ledger database must not be a symlink"
        )
    if database.exists() and not database.is_file():
        raise ValueError(
            "shadow ledger database path must identify a regular file"
        )

    connection = _connect(database)
    try:
        connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {_CHECKPOINT_TABLE} (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence >= 0),
                checkpoint_schema_version TEXT NOT NULL,
                state_as_of_unix_ms INTEGER NOT NULL
                    CHECK (state_as_of_unix_ms >= 0),
                created_at_unix_ms INTEGER NOT NULL
                    CHECK (created_at_unix_ms >= 0),
                payload_sha256 TEXT NOT NULL
                    CHECK (length(payload_sha256) = 64),
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS
                idx_paper_loop_checkpoints_run_latest
                ON {_CHECKPOINT_TABLE} (run_id, sequence DESC);
            CREATE TABLE IF NOT EXISTS {_BINDING_TABLE} (
                run_id TEXT PRIMARY KEY,
                binding_fingerprint_sha256 TEXT NOT NULL
                    CHECK (length(binding_fingerprint_sha256) = 64),
                binding_json TEXT NOT NULL
            );
            """
        )
        document = _binding_document(binding)
        payload = _canonical(document)
        existing = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE run_id = ?
            """,
            (binding.run_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                f"""
                INSERT INTO {_BINDING_TABLE}(
                    run_id,
                    binding_fingerprint_sha256,
                    binding_json
                ) VALUES (?, ?, ?)
                """,
                (
                    binding.run_id,
                    binding.binding_fingerprint_sha256,
                    payload,
                ),
            )
        elif existing != (
            binding.binding_fingerprint_sha256,
            payload,
        ):
            raise ValueError(
                "shadow ledger binding conflicts with existing run namespace"
            )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()

    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "shadow ledger database must remain a regular file"
        )
    os.chmod(database, 0o600)
    _fsync_directory(parent)


def build_initial_fast_paper_shadow_ledger_state(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    *,
    starting_cash_usd: float,
    as_of_unix_ms: int,
    fill_policy: PaperFillPolicy,
    position_action_policy: FastPaperPositionActionPolicy,
) -> FastPaperRuntimeState:
    _require_manifest_binding(manifest, binding)
    if (
        isinstance(starting_cash_usd, bool)
        or not isinstance(starting_cash_usd, (int, float))
        or not math.isfinite(float(starting_cash_usd))
        or float(starting_cash_usd) <= 0.0
    ):
        raise ValueError(
            "starting_cash_usd must be finite and strictly positive"
        )
    if (
        isinstance(as_of_unix_ms, bool)
        or not isinstance(as_of_unix_ms, int)
        or as_of_unix_ms < 0
    ):
        raise ValueError(
            "as_of_unix_ms must be a non-negative integer"
        )
    if type(fill_policy) is not PaperFillPolicy:
        raise ValueError("fill_policy must be exact PaperFillPolicy")
    if fill_policy.version != manifest.fill_policy_version:
        raise ValueError(
            "shadow fill policy version does not match runtime manifest"
        )
    if type(position_action_policy) is not FastPaperPositionActionPolicy:
        raise ValueError(
            "position_action_policy must be exact FastPaperPositionActionPolicy"
        )
    if (
        position_action_policy.version
        != manifest.position_action_policy_version
    ):
        raise ValueError(
            "shadow position-action policy version does not match runtime manifest"
        )

    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=as_of_unix_ms,
        event_loop_state=create_fast_paper_loop_state(),
        ledger=create_paper_ledger(
            float(starting_cash_usd),
            as_of_unix_ms,
        ),
        fill_policy=fill_policy,
        position_action_policy=position_action_policy,
        pending_buy=None,
        position_action_states=(),
    )


def save_fast_paper_shadow_ledger_checkpoint(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
    state: FastPaperRuntimeState,
    *,
    sequence: int,
    created_at_unix_ms: int,
) -> FastPaperCheckpointRecord:
    _require_manifest_binding(manifest, binding)
    _require_persisted_binding(binding)
    _require_state_policy_binding(manifest, state)
    return save_fast_paper_checkpoint(
        binding.database_path,
        binding.run_id,
        sequence,
        state,
        created_at_unix_ms,
    )


def load_latest_fast_paper_shadow_ledger_checkpoint(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
) -> FastPaperCheckpointRecord | None:
    _require_manifest_binding(manifest, binding)
    _require_persisted_binding(binding)
    record = load_latest_fast_paper_checkpoint(
        binding.database_path,
        binding.run_id,
    )
    if record is not None:
        _require_state_policy_binding(manifest, record.state)
    return record


def _require_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperShadowLedgerBinding,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperShadowLedgerBinding:
        raise ValueError(
            "binding must be exact FastPaperShadowLedgerBinding"
        )
    expected = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id=binding.run_id,
        database_path=binding.database_path,
    )
    if binding != expected:
        raise ValueError(
            "shadow ledger binding does not match runtime manifest"
        )


def _require_state_policy_binding(
    manifest: FastPaperRuntimeManifest,
    state: FastPaperRuntimeState,
) -> None:
    if type(state) is not FastPaperRuntimeState:
        raise ValueError(
            "state must be exact FastPaperRuntimeState"
        )
    if state.fill_policy.version != manifest.fill_policy_version:
        raise ValueError(
            "shadow checkpoint fill policy does not match runtime manifest"
        )
    if (
        state.position_action_policy.version
        != manifest.position_action_policy_version
    ):
        raise ValueError(
            "shadow checkpoint position-action policy does not match runtime manifest"
        )


def _require_persisted_binding(
    binding: FastPaperShadowLedgerBinding,
) -> None:
    database = Path(binding.database_path)
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "shadow ledger database must be an existing regular non-symlink file"
        )
    connection = _connect(database)
    try:
        row = connection.execute(
            f"""
            SELECT binding_fingerprint_sha256, binding_json
            FROM {_BINDING_TABLE}
            WHERE run_id = ?
            """,
            (binding.run_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError(
            "shadow ledger binding table is missing or unreadable"
        ) from exc
    finally:
        connection.close()

    expected_json = _canonical(_binding_document(binding))
    if row != (
        binding.binding_fingerprint_sha256,
        expected_json,
    ):
        raise ValueError(
            "shadow ledger binding fingerprint or document mismatch"
        )


def _shadow_database_path(
    manifest: FastPaperRuntimeManifest,
    value: str | Path,
) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(
            "shadow ledger database path must be a string or Path"
        )
    if isinstance(value, str) and not value.strip():
        raise ValueError(
            "shadow ledger database path must be explicit and non-empty"
        )
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise ValueError(
            "shadow ledger database path must not be a symlink"
        )
    resolved = raw.resolve(strict=False)
    protected = {
        Path(manifest.observer_database_path)
        .expanduser()
        .resolve(strict=False),
        Path(manifest.paper_evidence_path)
        .expanduser()
        .resolve(strict=False),
        Path(manifest.checkpoint_path)
        .expanduser()
        .resolve(strict=False),
    }
    if resolved in protected:
        raise ValueError(
            "shadow ledger database must be separate from authoritative and decision state paths"
        )
    return resolved


def _binding_document(
    binding: FastPaperShadowLedgerBinding,
) -> dict[str, object]:
    document = {
        "schema_name": binding.schema_name,
        "schema_version": binding.schema_version,
        "run_id": binding.run_id,
        "release_source_sha": binding.release_source_sha,
        "manifest_fingerprint_sha256": (
            binding.manifest_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            binding.champion_fingerprint_sha256
        ),
        "action_policy_version": binding.action_policy_version,
        "state_version": binding.state_version,
        "risk_policy_version": binding.risk_policy_version,
        "fill_policy_version": binding.fill_policy_version,
        "position_action_policy_version": (
            binding.position_action_policy_version
        ),
        "database_path": binding.database_path,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
    }
    if frozenset(document) != _BINDING_KEYS:
        raise ValueError("shadow ledger binding document is incomplete")
    return document


def _binding_fingerprint(
    binding: FastPaperShadowLedgerBinding,
) -> str:
    document = _binding_document_unchecked(binding)
    document.pop("binding_fingerprint_sha256")
    return hashlib.sha256(
        _canonical(document).encode("utf-8")
    ).hexdigest()


def _binding_document_unchecked(
    binding: FastPaperShadowLedgerBinding,
) -> dict[str, object]:
    return {
        "schema_name": binding.schema_name,
        "schema_version": binding.schema_version,
        "run_id": binding.run_id,
        "release_source_sha": binding.release_source_sha,
        "manifest_fingerprint_sha256": (
            binding.manifest_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            binding.champion_fingerprint_sha256
        ),
        "action_policy_version": binding.action_policy_version,
        "state_version": binding.state_version,
        "risk_policy_version": binding.risk_policy_version,
        "fill_policy_version": binding.fill_policy_version,
        "position_action_policy_version": (
            binding.position_action_policy_version
        ),
        "database_path": binding.database_path,
        "binding_fingerprint_sha256": (
            binding.binding_fingerprint_sha256
        ),
    }


def _connect(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except (OSError, sqlite3.Error) as exc:
        raise ValueError(
            "shadow ledger database connection failed"
        ) from exc


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_source_sha(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
