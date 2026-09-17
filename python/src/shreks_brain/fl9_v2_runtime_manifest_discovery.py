from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from shreks_brain.backup.models import BackupArtifactRole, BackupManifestError
from shreks_brain.backup.verify import verify_backup_bundle
from shreks_brain.fast_context_hydration import (
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.fast_first_champion_v2.hydration_policy import (
    require_fast_first_champion_v2_hydration_policy_matches_identities,
)
from shreks_brain.fast_runtime_hydration_policy import (
    build_fast_forecast_context_hydration_policy_from_runtime_manifest,
)
from shreks_brain.fl9_v2_cohort_acceptance import read_fl9_v2_cohort_acceptance
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_NAME = (
    "shreks.fl9_v2_runtime_manifest_discovery"
)
FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_VERSION = 1


class RuntimeManifestDiscoveryError(RuntimeError):
    """Raised when read-only runtime-manifest discovery cannot be trusted."""


def discover_fl9_v2_runtime_manifests(
    *,
    cohort_path: str | Path,
    active_runtime_manifest_path: str | Path,
    backup_root: str | Path,
    hydration_policy_version: str,
    strategy_families: tuple[str, ...],
    max_exit_quote_age_ms: int,
    execution_cost_policy_version: str,
    expected_round_trip_cost_bps: float | int | None,
) -> dict[str, object]:
    try:
        cohort = read_fl9_v2_cohort_acceptance(cohort_path)
    except (OSError, TypeError, ValueError) as error:
        raise RuntimeManifestDiscoveryError(
            "frozen V2 cohort could not be authenticated"
        ) from error

    identities = tuple(
        tuple(row.decision_identity) for row in cohort.accepted_decisions
    )
    cohort_quote_mint = _single_cohort_quote_mint(identities)

    active_path = Path(active_runtime_manifest_path).expanduser().resolve()
    active_payload = _read_regular_file_stable(
        active_path,
        label="active runtime manifest",
    )
    candidates = [
        _evaluate_candidate(
            payload=active_payload,
            source_kind="active",
            source_path=active_path,
            backup_created_at_unix_ms=None,
            expected_backup_fingerprint=None,
            accepted_decision_identities=identities,
            hydration_policy_version=hydration_policy_version,
            strategy_families=strategy_families,
            max_exit_quote_age_ms=max_exit_quote_age_ms,
            execution_cost_policy_version=execution_cost_policy_version,
            expected_round_trip_cost_bps=expected_round_trip_cost_bps,
        )
    ]

    root = Path(backup_root).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise RuntimeManifestDiscoveryError(
            "backup root must be an existing real directory"
        )
    try:
        backup_paths = tuple(
            sorted(
                path
                for path in root.iterdir()
                if not path.name.startswith(".")
                and path.is_dir()
                and not path.is_symlink()
            )
        )
    except OSError as error:
        raise RuntimeManifestDiscoveryError("backup root could not be listed") from error

    for bundle_path in backup_paths:
        try:
            backup_manifest = verify_backup_bundle(bundle_path)
        except (BackupManifestError, OSError, TypeError, ValueError) as error:
            raise RuntimeManifestDiscoveryError(
                "backup bundle verification failed"
            ) from error
        campaign_record = next(
            (
                record
                for record in backup_manifest.artifacts
                if record.role is BackupArtifactRole.CAMPAIGN_MANIFEST
            ),
            None,
        )
        if campaign_record is None:
            raise RuntimeManifestDiscoveryError(
                "verified backup is missing campaign manifest authority"
            )
        campaign_path = bundle_path / campaign_record.relative_path
        payload = _read_regular_file_stable(
            campaign_path,
            label="verified backup campaign manifest",
        )
        try:
            verified_again = verify_backup_bundle(bundle_path)
        except (BackupManifestError, OSError, TypeError, ValueError) as error:
            raise RuntimeManifestDiscoveryError(
                "backup bundle changed during verification"
            ) from error
        if verified_again != backup_manifest:
            raise RuntimeManifestDiscoveryError(
                "backup bundle authority changed during discovery"
            )
        candidates.append(
            _evaluate_candidate(
                payload=payload,
                source_kind="g8_backup",
                source_path=bundle_path.resolve(),
                backup_created_at_unix_ms=backup_manifest.created_at_unix_ms,
                expected_backup_fingerprint=(
                    backup_manifest.campaign_manifest_fingerprint_sha256
                ),
                accepted_decision_identities=identities,
                hydration_policy_version=hydration_policy_version,
                strategy_families=strategy_families,
                max_exit_quote_age_ms=max_exit_quote_age_ms,
                execution_cost_policy_version=execution_cost_policy_version,
                expected_round_trip_cost_bps=expected_round_trip_cost_bps,
            )
        )

    compatible_count = sum(
        candidate["compatibility"] == "COMPATIBLE"
        for candidate in candidates
    )
    return {
        "schema_name": FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_NAME,
        "schema_version": FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_VERSION,
        "status": (
            "FOUND_COMPATIBLE" if compatible_count else "HOLD_NO_COMPATIBLE"
        ),
        "cohort_quote_mint": cohort_quote_mint,
        "candidate_count": len(candidates),
        "compatible_candidate_count": compatible_count,
        "candidates": candidates,
    }


def _evaluate_candidate(
    *,
    payload: bytes,
    source_kind: str,
    source_path: Path,
    backup_created_at_unix_ms: int | None,
    expected_backup_fingerprint: str | None,
    accepted_decision_identities: tuple[tuple[object, ...], ...],
    hydration_policy_version: str,
    strategy_families: tuple[str, ...],
    max_exit_quote_age_ms: int,
    execution_cost_policy_version: str,
    expected_round_trip_cost_bps: float | int | None,
) -> dict[str, object]:
    try:
        manifest = decode_observer_paper_campaign_runtime_manifest(payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise RuntimeManifestDiscoveryError(
            "runtime manifest authentication failed"
        ) from error
    if (
        expected_backup_fingerprint is not None
        and manifest.manifest_fingerprint_sha256 != expected_backup_fingerprint
    ):
        raise RuntimeManifestDiscoveryError(
            "backup campaign fingerprint does not match authenticated runtime manifest"
        )

    try:
        policy = build_fast_forecast_context_hydration_policy_from_runtime_manifest(
            manifest,
            version=hydration_policy_version,
            strategy_families=strategy_families,
            max_exit_quote_age_ms=max_exit_quote_age_ms,
            execution_cost_policy_version=execution_cost_policy_version,
            expected_round_trip_cost_bps=expected_round_trip_cost_bps,
        )
    except (TypeError, ValueError) as error:
        raise RuntimeManifestDiscoveryError(
            "runtime manifest hydration-policy derivation failed"
        ) from error

    try:
        require_fast_first_champion_v2_hydration_policy_matches_identities(
            hydration_policy=policy,
            accepted_decision_identities=accepted_decision_identities,
        )
        compatibility = "COMPATIBLE"
    except ValueError:
        compatibility = "REJECTED_QUOTE_POLICY"

    bundle = manifest.policy_bundle
    return {
        "source_kind": source_kind,
        "source_path": str(source_path),
        "backup_created_at_unix_ms": backup_created_at_unix_ms,
        "authentication": "AUTHENTICATED",
        "compatibility": compatibility,
        "paper_run_id": manifest.paper_run_id,
        "runtime_manifest_fingerprint_sha256": (
            manifest.manifest_fingerprint_sha256
        ),
        "hydration_policy_fingerprint_sha256": (
            fast_forecast_context_hydration_policy_fingerprint_sha256(policy)
        ),
        "regime_quote_asset_mint": bundle.regime_read_policy.quote_asset_mint,
        "safety_probe_output_mint": bundle.safety_probe_identity.output_mint,
        "quote_asset_mint": bundle.quote_asset.mint,
        "quote_asset_decimals": bundle.quote_asset.decimals,
        "quote_provider": bundle.entry_quote_identity.provider,
    }


def _single_cohort_quote_mint(
    identities: tuple[tuple[object, ...], ...],
) -> str:
    if not identities:
        raise RuntimeManifestDiscoveryError(
            "frozen V2 cohort contains no accepted decisions"
        )
    quote_mints: set[str] = set()
    for identity in identities:
        if len(identity) != 7:
            raise RuntimeManifestDiscoveryError(
                "frozen V2 decision identity is malformed"
            )
        quote_mint = identity[4]
        if not isinstance(quote_mint, str) or not quote_mint.strip():
            raise RuntimeManifestDiscoveryError(
                "frozen V2 decision quote mint is malformed"
            )
        quote_mints.add(quote_mint)
    if len(quote_mints) != 1:
        raise RuntimeManifestDiscoveryError(
            "frozen V2 cohort does not use one single quote mint"
        )
    return next(iter(quote_mints))


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RuntimeManifestDiscoveryError(
            f"{label} must be an existing regular file"
        )
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise RuntimeManifestDiscoveryError(f"{label} could not be read") from error
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeManifestDiscoveryError(
            f"{label} changed while being read"
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-runtime-manifest-discovery",
        description=(
            "Read-only discovery and authentication of PAPER runtime manifests "
            "compatible with a frozen FL9 V2 cohort."
        ),
    )
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--active-runtime-manifest", required=True)
    parser.add_argument("--backup-root", required=True)
    parser.add_argument("--hydration-policy-version", required=True)
    parser.add_argument(
        "--strategy-family",
        action="append",
        required=True,
        dest="strategy_families",
    )
    parser.add_argument("--max-exit-quote-age-ms", type=int, required=True)
    parser.add_argument("--execution-cost-policy-version", required=True)
    parser.add_argument("--expected-round-trip-cost-bps", required=True)
    args = parser.parse_args(argv)

    try:
        report = discover_fl9_v2_runtime_manifests(
            cohort_path=args.cohort,
            active_runtime_manifest_path=args.active_runtime_manifest,
            backup_root=args.backup_root,
            hydration_policy_version=args.hydration_policy_version,
            strategy_families=tuple(args.strategy_families),
            max_exit_quote_age_ms=args.max_exit_quote_age_ms,
            execution_cost_policy_version=args.execution_cost_policy_version,
            expected_round_trip_cost_bps=_parse_expected_cost(
                args.expected_round_trip_cost_bps
            ),
        )
    except (RuntimeManifestDiscoveryError, TypeError, ValueError) as error:
        print(
            _canonical_json(
                {
                    "schema_name": FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_NAME,
                    "schema_version": FL9_V2_RUNTIME_MANIFEST_DISCOVERY_SCHEMA_VERSION,
                    "status": "FAILED",
                    "error": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 1

    print(_canonical_json(report))
    return 0


def _parse_expected_cost(value: str) -> float | None:
    if value == "unknown":
        return None
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeManifestDiscoveryError(
            "expected round-trip cost must be non-negative finite or 'unknown'"
        ) from error
    if not math.isfinite(parsed) or parsed < 0:
        raise RuntimeManifestDiscoveryError(
            "expected round-trip cost must be non-negative finite or 'unknown'"
        )
    return parsed


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
