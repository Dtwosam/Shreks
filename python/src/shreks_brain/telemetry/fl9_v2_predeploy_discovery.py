from __future__ import annotations

import os
from pathlib import Path
import pwd
import sys
from typing import Final, Sequence

from shreks_brain.fl9_v2_runtime_quote_evidence import (
    RUNTIME_QUOTE_EVIDENCE_SCHEMA_NAME,
    RUNTIME_QUOTE_EVIDENCE_SCHEMA_VERSION,
    read_fl9_v2_runtime_quote_evidence,
)

from .fl9_v2_discovery_control import (
    process_pending_fl9_v2_discovery_requests,
    publish_fl9_v2_discovery_control_result,
)


_PREDEPLOY_MARKER_DIRECTORY: Final = Path("/var/tmp")
_RESULT_MARKER_DIRECTORY: Final = Path("/dev/shm")
_RUNTIME_USER: Final = "shreks"
_OBSERVER_DATABASE: Final = Path("/var/lib/shreks/shreks.db")
_RUNTIME_QUOTE_SAMPLE_LIMIT: Final = 128


def _drop_to_runtime_identity() -> None:
    identity = pwd.getpwnam(_RUNTIME_USER)
    if identity.pw_uid <= 0 or identity.pw_gid <= 0:
        raise RuntimeError("runtime identity must be unprivileged")
    os.setgroups([])
    os.setgid(identity.pw_gid)
    os.setuid(identity.pw_uid)


def run_predeploy_discovery() -> int:
    if os.geteuid() != 0:
        print("fl9_v2_predeploy_discovery=requires-root-preflight", file=sys.stderr)
        return 1

    try:
        results = process_pending_fl9_v2_discovery_requests(
            marker_directory=_PREDEPLOY_MARKER_DIRECTORY,
            persist_receipts=False,
        )
    except Exception:
        print("fl9_v2_predeploy_discovery=processing-failed", file=sys.stderr)
        return 1

    if not results:
        return 0

    enriched_results = tuple(_enrich_hold_result(result) for result in results)

    try:
        _drop_to_runtime_identity()
        for result in enriched_results:
            published = publish_fl9_v2_discovery_control_result(
                result,
                marker_directory=_RESULT_MARKER_DIRECTORY,
            )
            if not published:
                print(
                    "fl9_v2_predeploy_discovery=result-exchange-missing",
                    file=sys.stderr,
                )
                return 1
    except Exception:
        print("fl9_v2_predeploy_discovery=publish-failed", file=sys.stderr)
        return 1
    return 0


def _enrich_hold_result(result: dict[str, object]) -> dict[str, object]:
    if result.get("status") != "HOLD_NO_COMPATIBLE":
        return result

    report = result.get("discovery_report")
    if not isinstance(report, dict):
        return result
    cohort_quote_mint = report.get("cohort_quote_mint")
    candidates = report.get("candidates")
    if (
        not isinstance(cohort_quote_mint, str)
        or not cohort_quote_mint.strip()
        or not isinstance(candidates, list)
    ):
        return result

    try:
        diagnostic = read_fl9_v2_runtime_quote_evidence(
            _OBSERVER_DATABASE,
            sample_limit=_RUNTIME_QUOTE_SAMPLE_LIMIT,
        )
    except Exception:
        diagnostic = {
            "schema_name": RUNTIME_QUOTE_EVIDENCE_SCHEMA_NAME,
            "schema_version": RUNTIME_QUOTE_EVIDENCE_SCHEMA_VERSION,
            "status": "UNAVAILABLE",
            "sample_limit": _RUNTIME_QUOTE_SAMPLE_LIMIT,
            "sampled_row_count": 0,
            "quote_assets": [],
        }

    enriched = dict(result)
    enriched["runtime_quote_evidence_diagnostic"] = diagnostic
    return enriched



def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args:
        return 2
    return run_predeploy_discovery()


if __name__ == "__main__":
    raise SystemExit(main())