from __future__ import annotations

import hashlib
from pathlib import Path

import shreks_brain.fast_proof_workspace as workspace_module


def test_capture_database_normalizes_missing_and_empty_wal(tmp_path: Path) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable-observer-db")
    wal = Path(str(database) + "-wal")

    missing = workspace_module._capture_database(database)
    assert missing.wal_sha256 is None

    wal.write_bytes(b"")
    empty = workspace_module._capture_database(database)
    assert empty.database_sha256 == missing.database_sha256
    assert empty.wal_sha256 is None


def test_capture_database_still_fingerprints_non_empty_wal(tmp_path: Path) -> None:
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable-observer-db")
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"committed-wal-bytes")

    captured = workspace_module._capture_database(database)

    assert captured.wal_sha256 == hashlib.sha256(
        b"committed-wal-bytes"
    ).hexdigest()
