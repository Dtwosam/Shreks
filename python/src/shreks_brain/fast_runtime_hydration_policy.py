from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile

from shreks_brain.fast_context_hydration import (
    FastForecastContextHydrationPolicy,
    encode_fast_forecast_context_hydration_policy,
    fast_forecast_context_hydration_policy_fingerprint_sha256,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifest,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)


FAST_RUNTIME_HYDRATION_POLICY_BRIDGE_VERSION = 1
FAST_RUNTIME_HYDRATION_POLICY_STATUS_SCHEMA_NAME = (
    "shreks.fast_runtime_hydration_policy_status"
)
FAST_RUNTIME_HYDRATION_POLICY_STATUS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FastRuntimeHydrationPolicyWriteResult:
    path: Path
    runtime_manifest_fingerprint_sha256: str
    policy_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        _require_sha256(
            "runtime_manifest_fingerprint_sha256",
            self.runtime_manifest_fingerprint_sha256,
        )
        _require_sha256(
            "policy_fingerprint_sha256",
            self.policy_fingerprint_sha256,
        )


def build_fast_forecast_context_hydration_policy_from_runtime_manifest(
    manifest: ObserverPaperCampaignRuntimeManifest,
    *,
    version: str,
    strategy_families: tuple[str, ...],
    max_exit_quote_age_ms: int,
    execution_cost_policy_version: str,
    expected_round_trip_cost_bps: float | int | None,
) -> FastForecastContextHydrationPolicy:
    if type(manifest) is not ObserverPaperCampaignRuntimeManifest:
        raise ValueError(
            "manifest must be exact ObserverPaperCampaignRuntimeManifest"
        )

    # The sealed encoder verifies the manifest's logical fingerprint against
    # its complete content. This prevents a hand-constructed/stale dataclass
    # from being treated as authenticated runtime evidence.
    encode_observer_paper_campaign_runtime_manifest(manifest)

    _require_non_empty("version", version)
    _require_non_empty(
        "execution_cost_policy_version",
        execution_cost_policy_version,
    )
    families = _canonical_strategy_families(strategy_families)
    _require_non_negative_int(
        "max_exit_quote_age_ms",
        max_exit_quote_age_ms,
    )
    if expected_round_trip_cost_bps is not None:
        _require_non_negative_finite(
            "expected_round_trip_cost_bps",
            expected_round_trip_cost_bps,
        )

    bundle = manifest.policy_bundle
    return FastForecastContextHydrationPolicy(
        version=version,
        strategy_families=families,
        regime_read_policy=bundle.regime_read_policy,
        regime_policy=bundle.regime_policy,
        safety_policy=bundle.safety_policy,
        safety_probe_identity=bundle.safety_probe_identity,
        global_risk_halt=manifest.global_risk_halt,
        exit_quote_provider=bundle.entry_quote_identity.provider,
        quote_asset_decimals=bundle.quote_asset.decimals,
        max_exit_quote_age_ms=max_exit_quote_age_ms,
        execution_cost_policy_version=execution_cost_policy_version,
        expected_round_trip_cost_bps=expected_round_trip_cost_bps,
    )


def write_fast_forecast_context_hydration_policy_from_runtime_manifest(
    *,
    runtime_manifest_path: str | Path,
    destination: str | Path,
    version: str,
    strategy_families: tuple[str, ...],
    max_exit_quote_age_ms: int,
    execution_cost_policy_version: str,
    expected_round_trip_cost_bps: float | int | None,
) -> FastRuntimeHydrationPolicyWriteResult:
    source = Path(runtime_manifest_path).expanduser().resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError(
            "runtime manifest path must be an existing regular file"
        )
    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "hydration policy destination already exists"
        )

    source_payload = _read_bytes_stable(source)
    manifest = decode_observer_paper_campaign_runtime_manifest(
        source_payload
    )
    policy = (
        build_fast_forecast_context_hydration_policy_from_runtime_manifest(
            manifest,
            version=version,
            strategy_families=strategy_families,
            max_exit_quote_age_ms=max_exit_quote_age_ms,
            execution_cost_policy_version=execution_cost_policy_version,
            expected_round_trip_cost_bps=expected_round_trip_cost_bps,
        )
    )
    policy_payload = encode_fast_forecast_context_hydration_policy(
        policy
    ).encode("utf-8")
    policy_fingerprint = (
        fast_forecast_context_hydration_policy_fingerprint_sha256(
            policy
        )
    )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.tmp-",
        dir=destination_path.parent,
    )
    staging = Path(staging_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(policy_payload)
            handle.flush()
            os.fsync(handle.fileno())
        staging.chmod(0o600)

        if _read_bytes_stable(source) != source_payload:
            raise ValueError(
                "runtime manifest source changed during policy derivation"
            )
        if staging.read_bytes() != policy_payload:
            raise ValueError(
                "staged hydration policy bytes changed before publish"
            )
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "hydration policy destination appeared during write"
            )
        staging.rename(destination_path)
    except Exception:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return FastRuntimeHydrationPolicyWriteResult(
        path=destination_path,
        runtime_manifest_fingerprint_sha256=(
            manifest.manifest_fingerprint_sha256
        ),
        policy_fingerprint_sha256=policy_fingerprint,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-context-policy-from-runtime",
        description=(
            "Derive the manifest-backed parts of the sealed FL9 forecast "
            "context hydration policy without inventing missing assumptions."
        ),
    )
    parser.add_argument("--runtime-manifest", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--strategy-family",
        action="append",
        required=True,
        dest="strategy_families",
    )
    parser.add_argument(
        "--max-exit-quote-age-ms",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--execution-cost-policy-version",
        required=True,
    )
    parser.add_argument(
        "--expected-round-trip-cost-bps",
        required=True,
        help="Non-negative number, or the literal 'unknown'.",
    )
    args = parser.parse_args(argv)

    expected_cost = _parse_expected_round_trip_cost_bps(
        args.expected_round_trip_cost_bps
    )
    result = (
        write_fast_forecast_context_hydration_policy_from_runtime_manifest(
            runtime_manifest_path=args.runtime_manifest,
            destination=args.destination,
            version=args.version,
            strategy_families=tuple(args.strategy_families),
            max_exit_quote_age_ms=args.max_exit_quote_age_ms,
            execution_cost_policy_version=(
                args.execution_cost_policy_version
            ),
            expected_round_trip_cost_bps=expected_cost,
        )
    )
    print(
        json.dumps(
            {
                "schema_name": (
                    FAST_RUNTIME_HYDRATION_POLICY_STATUS_SCHEMA_NAME
                ),
                "schema_version": (
                    FAST_RUNTIME_HYDRATION_POLICY_STATUS_SCHEMA_VERSION
                ),
                "status": "SUCCEEDED",
                "path": str(result.path),
                "runtime_manifest_fingerprint_sha256": (
                    result.runtime_manifest_fingerprint_sha256
                ),
                "policy_fingerprint_sha256": (
                    result.policy_fingerprint_sha256
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


def _parse_expected_round_trip_cost_bps(
    value: str,
) -> float | None:
    if not isinstance(value, str):
        raise ValueError(
            "expected round-trip cost must be text"
        )
    if value == "unknown":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(
            "expected round-trip cost must be a non-negative number or 'unknown'"
        ) from exc
    _require_non_negative_finite(
        "expected_round_trip_cost_bps",
        parsed,
    )
    return parsed


def _canonical_strategy_families(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError(
            "strategy_families must be a non-empty tuple"
        )
    if not all(
        isinstance(value, str) and bool(value.strip())
        for value in values
    ):
        raise ValueError(
            "strategy_families must contain only non-empty strings"
        )
    if len(set(values)) != len(values):
        raise ValueError(
            "strategy_families must not contain duplicates"
        )
    return tuple(sorted(values))


def _read_bytes_stable(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "runtime manifest source must remain a regular file"
        )
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "runtime manifest source changed while reading"
        )
    return payload


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_non_negative_int(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_non_negative_finite(
    name: str,
    value: object,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be a non-negative finite number"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(
            character not in "0123456789abcdef"
            for character in value
        )
    ):
        raise ValueError(
            f"{name} must be lowercase SHA-256 hex"
        )
