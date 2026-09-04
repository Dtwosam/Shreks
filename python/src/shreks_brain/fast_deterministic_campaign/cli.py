from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Sequence

from .invocation import run_fast_deterministic_campaign_invocation_file


FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_NAME = (
    "shreks.fast_deterministic_campaign_cli_result"
)
FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_VERSION = 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-deterministic-campaign",
        description=(
            "Run one authenticated deterministic FL9 PAPER campaign invocation."
        ),
    )
    parser.add_argument(
        "request_path",
        type=Path,
        help="canonical FL9 campaign request JSON",
    )
    args = parser.parse_args(argv)

    seal = run_fast_deterministic_campaign_invocation_file(
        args.request_path
    )
    manifest = seal.manifest
    result = {
        "schema_name": FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_VERSION,
        "request_fingerprint_sha256": (
            manifest.request_fingerprint_sha256
        ),
        "source_snapshot_fingerprint_sha256": (
            manifest.source_snapshot_fingerprint_sha256
        ),
        "campaign_artifact_fingerprint_sha256": (
            manifest.campaign_artifact_fingerprint_sha256
        ),
        "invocation_fingerprint_sha256": (
            manifest.invocation_fingerprint_sha256
        ),
        "invocation_path": str(seal.path),
    }
    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0
