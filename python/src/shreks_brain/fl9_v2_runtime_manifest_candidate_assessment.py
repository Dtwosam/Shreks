from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from shreks_brain.fl9_v2_runtime_manifest_discovery import (
    RuntimeManifestDiscoveryError,
    assess_fl9_v2_runtime_manifest_candidate_from_v2_request_authority,
)


FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_NAME = (
    "shreks.fl9_v2_runtime_manifest_candidate_assessment"
)
FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_VERSION = 1


class RuntimeManifestCandidateAssessmentError(RuntimeError):
    """Raised when one runtime-manifest candidate cannot be assessed safely."""


def assess_fl9_v2_runtime_manifest_candidate(
    *,
    cohort_path: str | Path,
    runtime_manifest_path: str | Path,
    v2_host_request_authority_path: str | Path,
) -> dict[str, object]:
    try:
        assessment = (
            assess_fl9_v2_runtime_manifest_candidate_from_v2_request_authority(
                cohort_path=cohort_path,
                runtime_manifest_path=runtime_manifest_path,
                v2_host_request_authority_path=v2_host_request_authority_path,
            )
        )
    except RuntimeManifestDiscoveryError as error:
        raise RuntimeManifestCandidateAssessmentError(str(error)) from error

    return {
        "schema_name": FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_NAME,
        "schema_version": (
            FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_VERSION
        ),
        **assessment,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-runtime-manifest-candidate-assessment",
        description=(
            "Authenticate and assess one PAPER runtime-manifest candidate "
            "against the frozen FL9 V2 cohort and preserved request authority."
        ),
    )
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--runtime-manifest", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    args = parser.parse_args(argv)

    try:
        report = assess_fl9_v2_runtime_manifest_candidate(
            cohort_path=args.cohort,
            runtime_manifest_path=args.runtime_manifest,
            v2_host_request_authority_path=args.v2_host_request_authority,
        )
    except (RuntimeManifestCandidateAssessmentError, TypeError, ValueError) as error:
        print(
            _canonical_json(
                {
                    "schema_name": (
                        FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_NAME
                    ),
                    "schema_version": (
                        FL9_V2_RUNTIME_MANIFEST_CANDIDATE_ASSESSMENT_SCHEMA_VERSION
                    ),
                    "status": "FAILED",
                    "error": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 1

    print(_canonical_json(report))
    return 0


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
