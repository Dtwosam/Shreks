from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from shreks_brain.fast_first_champion_v2.models import FastFirstChampionV2Policy
from shreks_brain.fl9_v2_cohort_acceptance import read_fl9_v2_cohort_acceptance


def build_backfill_request_document(artifact, *, policy: FastFirstChampionV2Policy) -> dict[str, object]:
    manifest = artifact.manifest
    if manifest.artifact_fingerprint_sha256 != policy.expected_cohort_artifact_fingerprint_sha256:
        raise ValueError("cohort artifact fingerprint does not match active V2 policy")
    if manifest.accepted_identity_fingerprint_sha256 != policy.expected_accepted_identity_fingerprint_sha256:
        raise ValueError("accepted identity fingerprint does not match active V2 policy")
    if manifest.policy_version != policy.cohort_policy_version:
        raise ValueError("cohort policy version does not match active V2 policy")
    if manifest.horizon_ms != policy.horizon_ms:
        raise ValueError("cohort horizon does not match active V2 policy")

    sessions = tuple(manifest.source_sessions)
    decisions: list[dict[str, object]] = []
    for accepted in artifact.accepted_decisions:
        signature, ordinal, sequence, mint, quote_mint, venue, observed = accepted.decision_identity
        matches = tuple(
            session for session in sessions
            if session.first_notification_observed_at_unix_ms <= observed <= session.last_notification_observed_at_unix_ms
        )
        if len(matches) != 1:
            raise ValueError("accepted cohort decision must map to exactly one frozen coverage session")
        session = matches[0]
        decisions.append({
            "signature": signature,
            "ordinal": ordinal,
            "sequence": sequence,
            "mint": mint,
            "quote_mint": quote_mint,
            "venue": venue,
            "observed_at_unix_ms": observed,
            "coverage_session_id": session.session_id,
            "coverage_complete_through_unix_ms": session.last_notification_observed_at_unix_ms,
        })

    return {
        "schema_name": "shreks.fl9_v2_future_path_backfill_request",
        "schema_version": 1,
        "cohort_artifact_fingerprint_sha256": manifest.artifact_fingerprint_sha256,
        "accepted_identity_fingerprint_sha256": manifest.accepted_identity_fingerprint_sha256,
        "horizon_ms": policy.horizon_ms,
        "source_sessions": [
            {
                "session_id": session.session_id,
                "provider": session.provider,
                "process_session_sequence": session.process_session_sequence,
                "first_notification_observed_at_unix_ms": session.first_notification_observed_at_unix_ms,
                "last_notification_observed_at_unix_ms": session.last_notification_observed_at_unix_ms,
                "notification_count": session.notification_count,
            }
            for session in sessions
        ],
        "decisions": decisions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shreks-fl9-v2-future-path-backfill")
    parser.add_argument("--database", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--observer-binary", default="/opt/shreks/current/target/release/shreks-observe")
    args = parser.parse_args(argv)

    artifact = read_fl9_v2_cohort_acceptance(args.cohort)
    document = build_backfill_request_document(artifact, policy=FastFirstChampionV2Policy())
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="shreks-fl9-v2-backfill-", suffix=".json", delete=False) as handle:
        request_path = Path(handle.name)
        handle.write(payload)
    request_path.chmod(0o600)
    try:
        completed = subprocess.run(
            [args.observer_binary, "populate-cohort-future-path-labels", "--database", args.database, "--request-json", str(request_path)],
            check=False, capture_output=True, text=True,
        )
    finally:
        request_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "cohort FL4 backfill failed")
    print(completed.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
