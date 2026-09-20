from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Final


RUNTIME_QUOTE_EVIDENCE_SCHEMA_NAME: Final = "shreks.fl9_v2_runtime_quote_evidence"
RUNTIME_QUOTE_EVIDENCE_SCHEMA_VERSION: Final = 1
_MAX_SAMPLE_LIMIT: Final = 4096
_REQUIRED_COLUMNS: Final = frozenset(
    {
        "id",
        "purpose",
        "input_mint",
        "output_mint",
        "quoted_at_unix_ms",
    }
)
_ALLOWED_PURPOSES: Final = frozenset({"ENTRY", "EXIT"})


class RuntimeQuoteEvidenceError(ValueError):
    """Raised when persisted PAPER quote evidence cannot be trusted read-only."""


def read_fl9_v2_runtime_quote_evidence(
    database_path: str | Path,
    *,
    sample_limit: int,
) -> dict[str, object]:
    if (
        isinstance(sample_limit, bool)
        or not isinstance(sample_limit, int)
        or not 1 <= sample_limit <= _MAX_SAMPLE_LIMIT
    ):
        raise RuntimeQuoteEvidenceError(
            f"sample_limit must be between 1 and {_MAX_SAMPLE_LIMIT}"
        )

    source = Path(database_path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise RuntimeQuoteEvidenceError(
            "runtime quote evidence database must be a real existing file"
        )
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise RuntimeQuoteEvidenceError(
            "runtime quote evidence database could not be resolved"
        ) from error

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{source}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or query_only[0] != 1:
            raise RuntimeQuoteEvidenceError(
                "runtime quote evidence connection is not query-only"
            )

        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(paper_quote_snapshots)"
            ).fetchall()
        }
        if not _REQUIRED_COLUMNS.issubset(columns):
            raise RuntimeQuoteEvidenceError(
                "paper_quote_snapshots schema is missing required quote evidence columns"
            )

        rows = connection.execute(
            """
            SELECT id, purpose, input_mint, output_mint, quoted_at_unix_ms
            FROM paper_quote_snapshots
            ORDER BY quoted_at_unix_ms DESC, id DESC
            LIMIT ?
            """,
            (sample_limit,),
        ).fetchall()
    except RuntimeQuoteEvidenceError:
        raise
    except (sqlite3.Error, OSError, TypeError, ValueError) as error:
        raise RuntimeQuoteEvidenceError(
            "runtime quote evidence read failed"
        ) from error
    finally:
        if connection is not None:
            connection.close()

    aggregates: dict[str, dict[str, int]] = {}
    for row in rows:
        purpose = row["purpose"]
        if not isinstance(purpose, str) or purpose not in _ALLOWED_PURPOSES:
            raise RuntimeQuoteEvidenceError(
                "paper quote evidence purpose is invalid"
            )

        quote_mint = row["input_mint"] if purpose == "ENTRY" else row["output_mint"]
        if not isinstance(quote_mint, str) or not quote_mint.strip():
            raise RuntimeQuoteEvidenceError(
                "paper quote evidence quote mint is invalid"
            )

        quoted_at = row["quoted_at_unix_ms"]
        if isinstance(quoted_at, bool) or not isinstance(quoted_at, int) or quoted_at < 0:
            raise RuntimeQuoteEvidenceError(
                "paper quote evidence timestamp is invalid"
            )

        aggregate = aggregates.setdefault(
            quote_mint,
            {
                "row_count": 0,
                "latest_quoted_at_unix_ms": quoted_at,
            },
        )
        aggregate["row_count"] += 1
        aggregate["latest_quoted_at_unix_ms"] = max(
            aggregate["latest_quoted_at_unix_ms"],
            quoted_at,
        )

    quote_assets = [
        {
            "mint": mint,
            "row_count": values["row_count"],
            "latest_quoted_at_unix_ms": values["latest_quoted_at_unix_ms"],
        }
        for mint, values in sorted(aggregates.items())
    ]
    if not quote_assets:
        status = "NO_EVIDENCE"
    elif len(quote_assets) == 1:
        status = "ONE_QUOTE_ASSET"
    else:
        status = "AMBIGUOUS_QUOTE_ASSETS"

    return {
        "schema_name": RUNTIME_QUOTE_EVIDENCE_SCHEMA_NAME,
        "schema_version": RUNTIME_QUOTE_EVIDENCE_SCHEMA_VERSION,
        "status": status,
        "sample_limit": sample_limit,
        "sampled_row_count": len(rows),
        "quote_assets": quote_assets,
    }
