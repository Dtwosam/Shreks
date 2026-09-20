from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path


WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "shreks.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE paper_quote_snapshots (
                id INTEGER PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                purpose TEXT NOT NULL,
                provider TEXT NOT NULL,
                probe_policy_version TEXT NOT NULL,
                input_mint TEXT NOT NULL,
                output_mint TEXT NOT NULL,
                taker TEXT NOT NULL,
                input_amount TEXT NOT NULL,
                output_amount TEXT,
                minimum_output_amount TEXT,
                slippage_bps INTEGER NOT NULL,
                route_available INTEGER NOT NULL,
                price_impact_pct TEXT,
                route_labels_json TEXT NOT NULL,
                quoted_at_unix_ms INTEGER NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _insert(
    path: Path,
    *,
    row_id: int,
    purpose: str,
    candidate_mint: str,
    quote_mint: str,
    quoted_at_unix_ms: int,
) -> None:
    if purpose == "entry":
        input_mint, output_mint = quote_mint, candidate_mint
    else:
        input_mint, output_mint = candidate_mint, quote_mint
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots (
                id, candidate_id, purpose, provider, probe_policy_version,
                input_mint, output_mint, taker, input_amount, output_amount,
                minimum_output_amount, slippage_bps, route_available,
                price_impact_pct, route_labels_json, quoted_at_unix_ms
            ) VALUES (?, ?, ?, 'jupiter', 'probe-v1', ?, ?, 'taker', '1',
                      '1', '1', 50, 1, '0', '[]', ?)
            """,
            (
                row_id,
                row_id,
                purpose,
                input_mint,
                output_mint,
                quoted_at_unix_ms,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _module():
    return importlib.import_module("shreks_brain.fl9_v2_runtime_quote_evidence")


def test_recent_paper_quote_evidence_reports_one_quote_asset_without_mutation(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _database(tmp_path)
    _insert(
        path,
        row_id=1,
        purpose="entry",
        candidate_mint="MintA",
        quote_mint=WSOL,
        quoted_at_unix_ms=1000,
    )
    _insert(
        path,
        row_id=2,
        purpose="exit",
        candidate_mint="MintB",
        quote_mint=WSOL,
        quoted_at_unix_ms=2000,
    )
    before = path.stat().st_mtime_ns

    result = module.read_fl9_v2_runtime_quote_evidence(path, sample_limit=128)

    assert result["schema_name"] == "shreks.fl9_v2_runtime_quote_evidence"
    assert result["schema_version"] == 1
    assert result["status"] == "ONE_QUOTE_ASSET"
    assert result["sample_limit"] == 128
    assert result["sampled_row_count"] == 2
    assert result["quote_assets"] == [
        {
            "mint": WSOL,
            "row_count": 2,
            "latest_quoted_at_unix_ms": 2000,
        }
    ]
    assert path.stat().st_mtime_ns == before


def test_recent_paper_quote_evidence_reports_ambiguous_assets(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _database(tmp_path)
    _insert(
        path,
        row_id=1,
        purpose="entry",
        candidate_mint="MintA",
        quote_mint=USDC,
        quoted_at_unix_ms=1000,
    )
    _insert(
        path,
        row_id=2,
        purpose="exit",
        candidate_mint="MintB",
        quote_mint=WSOL,
        quoted_at_unix_ms=2000,
    )

    result = module.read_fl9_v2_runtime_quote_evidence(path, sample_limit=128)

    assert result["status"] == "AMBIGUOUS_QUOTE_ASSETS"
    assert [item["mint"] for item in result["quote_assets"]] == sorted([USDC, WSOL])


def test_recent_paper_quote_evidence_reports_no_rows(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _database(tmp_path)

    result = module.read_fl9_v2_runtime_quote_evidence(path, sample_limit=128)

    assert result["status"] == "NO_EVIDENCE"
    assert result["sampled_row_count"] == 0
    assert result["quote_assets"] == []


def test_runtime_quote_evidence_rejects_invalid_purpose_without_guessing(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            INSERT INTO paper_quote_snapshots (
                id, candidate_id, purpose, provider, probe_policy_version,
                input_mint, output_mint, taker, input_amount, output_amount,
                minimum_output_amount, slippage_bps, route_available,
                price_impact_pct, route_labels_json, quoted_at_unix_ms
            ) VALUES (1, 1, 'OTHER', 'jupiter', 'probe-v1', 'A', 'B', 'taker',
                      '1', '1', '1', 50, 1, '0', '[]', 1000)
            """
        )
        connection.commit()
    finally:
        connection.close()

    try:
        module.read_fl9_v2_runtime_quote_evidence(path, sample_limit=128)
    except module.RuntimeQuoteEvidenceError as error:
        assert "purpose" in str(error).lower()
    else:
        raise AssertionError("invalid quote purpose must fail closed")

def test_runtime_quote_evidence_rejects_noncanonical_uppercase_purpose(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _database(tmp_path)
    _insert(
        path,
        row_id=1,
        purpose="ENTRY",
        candidate_mint="MintA",
        quote_mint=WSOL,
        quoted_at_unix_ms=1000,
    )

    try:
        module.read_fl9_v2_runtime_quote_evidence(path, sample_limit=128)
    except module.RuntimeQuoteEvidenceError as error:
        assert "purpose" in str(error).lower()
    else:
        raise AssertionError("noncanonical uppercase purpose must fail closed")
