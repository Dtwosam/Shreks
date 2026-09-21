from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    G1CV2RuntimeManifestCandidateAuthoringError,
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)


G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_NAME = (
    "shreks.g1c_v2_runtime_manifest_candidate_authority"
)
G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_VERSION = 1

_AUTHORITY_KIND = "explicit_new_run_candidate_inputs"
_AUTHORITY_STATUS = "BOUND_EXACT_CANONICAL_CANDIDATE"
_CANDIDATE_AUTHORING_AUTHORITY = "EXPLICIT_INPUTS_BOUND"
_NOT_GRANTED = "NOT_GRANTED"
_PAPER_PROMOTION_BLOCKED = "BLOCKED"
_LIVE_DISABLED = "DISABLED"
_QUOTE_USD_VALUATION_MODE = "exact_market_ratio"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_U64 = 2**64 - 1


class G1CV2RuntimeManifestCandidateAuthorityError(RuntimeError):
    """Raised when explicit G1C v2 candidate inputs cannot be bound safely."""


def bind_g1c_v2_runtime_manifest_candidate_authority(
    *,
    source_runtime_manifest_path: str | Path,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
    paper_run_id: str,
    start_at_unix_ms: int,
    quote_asset_mint: str,
    quote_asset_decimals: int,
    entry_input_amount: int,
    destination: str | Path,
) -> dict[str, object]:
    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"source runtime manifest authentication failed: {error}"
        ) from error

    if (
        source.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "source runtime manifest must be canonical v1 authority"
        )

    try:
        request_authority = (
            discovery.authenticate_fl9_v2_discovery_request_authority(
                cohort_path=cohort_path,
                v2_host_request_authority_path=(
                    v2_host_request_authority_path
                ),
            )
        )
        cohort = discovery.read_fl9_v2_cohort_acceptance(cohort_path)
    except (
        discovery.RuntimeManifestDiscoveryError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"frozen V2 request/cohort authority authentication failed: {error}"
        ) from error

    cohort_fingerprint = cohort.manifest.artifact_fingerprint_sha256
    if (
        cohort_fingerprint
        != request_authority.cohort_artifact_fingerprint_sha256
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "frozen V2 cohort changed after request authority authentication"
        )

    cohort_quote_mint = _single_cohort_quote_mint(
        cohort.accepted_decisions
    )
    if quote_asset_mint != cohort_quote_mint:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "explicit candidate quote asset must equal frozen cohort quote mint"
        )

    try:
        candidate = author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=source_path,
            paper_run_id=paper_run_id,
            start_at_unix_ms=start_at_unix_ms,
            quote_asset_mint=quote_asset_mint,
            quote_asset_decimals=quote_asset_decimals,
            entry_input_amount=entry_input_amount,
        )
        candidate_payload = encode_observer_paper_campaign_runtime_manifest(
            candidate
        )
        decoded_candidate = decode_observer_paper_campaign_runtime_manifest(
            candidate_payload
        )
    except (
        G1CV2RuntimeManifestCandidateAuthoringError,
        ObserverPaperCampaignRuntimeManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"explicit candidate inputs were rejected: {error}"
        ) from error

    if decoded_candidate != candidate:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "canonical candidate round-trip changed derived content"
        )

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    if source_after != source_payload:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "source runtime manifest changed while candidate authority was bound"
        )

    valuation_policy = candidate.quote_usd_valuation_policy
    if (
        valuation_policy is None
        or valuation_policy.mode.value != _QUOTE_USD_VALUATION_MODE
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "derived candidate quote valuation authority is unsupported"
        )

    source_bundle = source.policy_bundle
    candidate_bundle = candidate.policy_bundle
    material: dict[str, object] = {
        "schema_name": (
            G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_NAME
        ),
        "schema_version": (
            G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_VERSION
        ),
        "authority_kind": _AUTHORITY_KIND,
        "authority_status": _AUTHORITY_STATUS,
        "source_manifest_sha256": hashlib.sha256(source_payload).hexdigest(),
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_quote_asset_mint": source_bundle.quote_asset.mint,
        "candidate_manifest_sha256": hashlib.sha256(
            candidate_payload
        ).hexdigest(),
        "candidate_runtime_manifest_fingerprint_sha256": (
            candidate.manifest_fingerprint_sha256
        ),
        "candidate_paper_run_id": candidate.paper_run_id,
        "candidate_start_at_unix_ms": (
            candidate.initial_state.last_cycle_at_unix_ms
        ),
        "candidate_quote_asset_mint": candidate_bundle.quote_asset.mint,
        "candidate_quote_asset_decimals": (
            candidate_bundle.quote_asset.decimals
        ),
        "candidate_entry_input_amount": (
            candidate_bundle.entry_quote_identity.input_amount
        ),
        "candidate_quote_usd_valuation_mode": (
            valuation_policy.mode.value
        ),
        "cohort_artifact_fingerprint_sha256": cohort_fingerprint,
        "cohort_quote_mint": cohort_quote_mint,
        "request_fingerprint_sha256": (
            request_authority.request_fingerprint_sha256
        ),
        "request_release_source_sha": (
            request_authority.request_release_source_sha
        ),
        "request_hydration_policy_fingerprint_sha256": (
            request_authority.hydration_policy_fingerprint_sha256
        ),
        "candidate_authoring_authority": _CANDIDATE_AUTHORING_AUTHORITY,
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _PAPER_PROMOTION_BLOCKED,
        "live_authority": _LIVE_DISABLED,
    }
    authority = {
        **material,
        "authority_fingerprint_sha256": _sha256_canonical(material),
    }

    _write_authority_once(destination, authority)
    written = Path(destination).expanduser().resolve()
    verified = decode_g1c_v2_runtime_manifest_candidate_authority(
        written.read_text(encoding="utf-8")
    )
    if verified != authority:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "written candidate authority did not round-trip"
        )
    return authority


def decode_g1c_v2_runtime_manifest_candidate_authority(
    payload: str,
) -> dict[str, object]:
    if not isinstance(payload, str):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate authority payload must be text"
        )
    document = _decode_canonical_text(
        payload,
        label="candidate authority",
    )

    expected_keys = {
        "schema_name",
        "schema_version",
        "authority_kind",
        "authority_status",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_paper_run_id",
        "candidate_start_at_unix_ms",
        "candidate_quote_asset_mint",
        "candidate_quote_asset_decimals",
        "candidate_entry_input_amount",
        "candidate_quote_usd_valuation_mode",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
        "candidate_authoring_authority",
        "installation_authority",
        "activation_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "authority_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate authority has unknown or missing fields"
        )

    static_values = {
        "schema_name": (
            G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_NAME
        ),
        "schema_version": (
            G1C_V2_RUNTIME_MANIFEST_CANDIDATE_AUTHORITY_SCHEMA_VERSION
        ),
        "authority_kind": _AUTHORITY_KIND,
        "authority_status": _AUTHORITY_STATUS,
        "candidate_quote_usd_valuation_mode": _QUOTE_USD_VALUATION_MODE,
        "candidate_authoring_authority": _CANDIDATE_AUTHORING_AUTHORITY,
        "installation_authority": _NOT_GRANTED,
        "activation_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _PAPER_PROMOTION_BLOCKED,
        "live_authority": _LIVE_DISABLED,
    }
    for name, expected in static_values.items():
        if document.get(name) != expected:
            raise G1CV2RuntimeManifestCandidateAuthorityError(
                f"candidate authority {name} is unsupported"
            )

    for name in (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "cohort_artifact_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_hydration_policy_fingerprint_sha256",
        "authority_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))

    _require_source_sha(
        "request_release_source_sha",
        document.get("request_release_source_sha"),
    )

    for name in (
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_paper_run_id",
        "candidate_quote_asset_mint",
        "cohort_quote_mint",
    ):
        _require_non_empty_text(name, document.get(name))

    if document["source_paper_run_id"] == document["candidate_paper_run_id"]:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate paper_run_id must differ from source"
        )
    if (
        document["source_quote_asset_mint"]
        == document["candidate_quote_asset_mint"]
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate quote asset must differ from source"
        )
    if (
        document["candidate_quote_asset_mint"]
        != document["cohort_quote_mint"]
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate quote asset must equal frozen cohort quote mint"
        )

    _require_non_negative_int(
        "candidate_start_at_unix_ms",
        document.get("candidate_start_at_unix_ms"),
    )
    _require_decimals(
        "candidate_quote_asset_decimals",
        document.get("candidate_quote_asset_decimals"),
    )
    _require_positive_u64(
        "candidate_entry_input_amount",
        document.get("candidate_entry_input_amount"),
    )

    claimed = document["authority_fingerprint_sha256"]
    material = dict(document)
    del material["authority_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate authority fingerprint mismatch"
        )
    return document


def _single_cohort_quote_mint(accepted_decisions) -> str:
    quote_mints: set[str] = set()
    count = 0
    for row in accepted_decisions:
        count += 1
        identity = tuple(row.decision_identity)
        if len(identity) != 7:
            raise G1CV2RuntimeManifestCandidateAuthorityError(
                "frozen V2 cohort decision identity is malformed"
            )
        quote_mint = identity[4]
        if not isinstance(quote_mint, str) or not quote_mint.strip():
            raise G1CV2RuntimeManifestCandidateAuthorityError(
                "frozen V2 cohort quote mint is malformed"
            )
        quote_mints.add(quote_mint)
    if count == 0:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "frozen V2 cohort contains no accepted decisions"
        )
    if len(quote_mints) != 1:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "frozen V2 cohort does not use one single quote mint"
        )
    return next(iter(quote_mints))


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} must be an existing regular non-symlink file"
        )
    return path.resolve()


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} could not be read"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} changed while being read"
        )
    return payload


def _write_authority_once(
    destination: str | Path,
    authority: dict[str, object],
) -> None:
    try:
        path = Path(destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate authority destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "candidate authority destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            "candidate authority destination parent must be a real directory"
        )

    payload = _canonical_json(authority).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if path.exists() or path.is_symlink():
            raise FileExistsError(
                "candidate authority destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decode_canonical_text(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} must use canonical JSON with one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{label} must use canonical JSON"
        )
    return document


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical_json(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_source_sha(name: str, value: object) -> None:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be 40 lowercase hex characters"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be an integer within [0, 255]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_U64
    ):
        raise G1CV2RuntimeManifestCandidateAuthorityError(
            f"{name} must be a positive u64 amount"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-runtime-manifest-candidate-authority-bind",
        description=(
            "Bind explicit G1C v2 new-run candidate inputs to exact "
            "authenticated source/cohort/request authority without granting "
            "installation, rotation, scoring, promotion, or LIVE authority."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    parser.add_argument("--paper-run-id", required=True)
    parser.add_argument("--start-at-unix-ms", required=True, type=int)
    parser.add_argument("--quote-asset-mint", required=True)
    parser.add_argument("--quote-asset-decimals", required=True, type=int)
    parser.add_argument("--entry-input-amount", required=True, type=int)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        authority = bind_g1c_v2_runtime_manifest_candidate_authority(
            source_runtime_manifest_path=args.source_runtime_manifest,
            cohort_path=args.cohort,
            v2_host_request_authority_path=args.v2_host_request_authority,
            paper_run_id=args.paper_run_id,
            start_at_unix_ms=args.start_at_unix_ms,
            quote_asset_mint=args.quote_asset_mint,
            quote_asset_decimals=args.quote_asset_decimals,
            entry_input_amount=args.entry_input_amount,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2RuntimeManifestCandidateAuthorityError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            _canonical_json(
                {
                    "status": "FAILED",
                    "error": str(error),
                }
            ),
            end="",
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(_canonical_json(authority))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
