from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_SCHEMA_NAME = "shreks.g1c_v2_entry_sizing_proposal"
_SCHEMA_VERSION = 1
_STATUS = "PROPOSAL_EVIDENCE_ONLY"
_SIZING_POLICY = "preserve_source_quote_notional_floor"
_REFERENCE_AUTHORITY = "EXPLICIT_REFERENCE_ONLY"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_U64 = 2**64 - 1


class G1CV2EntrySizingProposalError(ValueError):
    """Raised when an evidence-only G1C v2 sizing proposal is invalid."""


def propose_g1c_v2_entry_sizing(
    *,
    source_runtime_manifest_path: str | Path,
    target_quote_mint: str,
    target_quote_decimals: int,
    target_quote_usd_per_token: str,
    quote_evidence_fingerprint_sha256: str,
    quote_evidence_observed_at_unix_ms: int,
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
        raise G1CV2EntrySizingProposalError(
            f"source runtime manifest authentication failed: {error}"
        ) from error

    if (
        source.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    ):
        raise G1CV2EntrySizingProposalError(
            "source runtime manifest must be canonical v1 authority"
        )

    _require_non_empty_text("target_quote_mint", target_quote_mint)
    source_bundle = source.policy_bundle
    source_quote = source_bundle.quote_asset
    if target_quote_mint == source_quote.mint:
        raise G1CV2EntrySizingProposalError(
            "target quote mint must be different from source quote mint"
        )
    _require_decimals("target_quote_decimals", target_quote_decimals)
    target_usd = _parse_positive_decimal(
        "target_quote_usd_per_token",
        target_quote_usd_per_token,
    )
    _require_sha256(
        "quote_evidence_fingerprint_sha256",
        quote_evidence_fingerprint_sha256,
    )
    _require_non_negative_int(
        "quote_evidence_observed_at_unix_ms",
        quote_evidence_observed_at_unix_ms,
    )

    source_entry_raw = source_bundle.entry_quote_identity.input_amount
    if (
        isinstance(source_entry_raw, bool)
        or not isinstance(source_entry_raw, int)
        or source_entry_raw <= 0
    ):
        raise G1CV2EntrySizingProposalError(
            "source entry input amount must be a positive integer"
        )
    source_decimals = source_quote.decimals
    _require_decimals("source_quote_decimals", source_decimals)
    source_usd = _parse_positive_decimal(
        "source_quote_usd_per_token",
        str(source_quote.usd_per_token),
    )

    source_scale = Decimal(10) ** source_decimals
    source_token_amount = Decimal(source_entry_raw) / source_scale
    source_notional = source_token_amount * source_usd
    if not source_notional.is_finite() or source_notional <= 0:
        raise G1CV2EntrySizingProposalError(
            "source quote notional must be positive and finite"
        )

    target_scale_int = 10**target_quote_decimals
    target_scale = Decimal(target_scale_int)
    proposed_raw_decimal = (
        (source_notional / target_usd) * target_scale
    ).to_integral_value(rounding=ROUND_FLOOR)
    proposed_raw = int(proposed_raw_decimal)
    if proposed_raw <= 0:
        raise G1CV2EntrySizingProposalError(
            "target quote reference produces a zero raw proposal"
        )
    if proposed_raw > _MAX_U64:
        raise G1CV2EntrySizingProposalError(
            "target quote reference produces a raw proposal above u64"
        )

    proposed_token_amount = Decimal(proposed_raw) / target_scale
    proposed_notional = proposed_token_amount * target_usd
    notional_shortfall = source_notional - proposed_notional
    if notional_shortfall < 0:
        raise G1CV2EntrySizingProposalError(
            "floor sizing unexpectedly exceeded source quote notional"
        )
    one_raw_unit_notional = target_usd / target_scale
    if notional_shortfall >= one_raw_unit_notional:
        raise G1CV2EntrySizingProposalError(
            "floor sizing shortfall is not bounded by one target raw unit"
        )

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    if source_after != source_payload:
        raise G1CV2EntrySizingProposalError(
            "source runtime manifest changed while proposal was derived"
        )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "sizing_policy": _SIZING_POLICY,
        "source_manifest_sha256": hashlib.sha256(source_payload).hexdigest(),
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_quote_mint": source_quote.mint,
        "source_quote_decimals": source_decimals,
        "source_quote_usd_per_token": _decimal_text(source_usd),
        "source_entry_input_amount": source_entry_raw,
        "source_quote_token_amount": _decimal_text(source_token_amount),
        "source_quote_notional_usd": _decimal_text(source_notional),
        "target_quote_mint": target_quote_mint,
        "target_quote_decimals": target_quote_decimals,
        "target_quote_usd_per_token": _decimal_text(target_usd),
        "quote_evidence_fingerprint_sha256": (
            quote_evidence_fingerprint_sha256
        ),
        "quote_evidence_observed_at_unix_ms": (
            quote_evidence_observed_at_unix_ms
        ),
        "quote_evidence_authority": _REFERENCE_AUTHORITY,
        "proposed_entry_input_amount": proposed_raw,
        "proposed_quote_token_amount": _decimal_text(
            proposed_token_amount
        ),
        "proposed_quote_notional_usd": _decimal_text(proposed_notional),
        "notional_shortfall_usd": _decimal_text(notional_shortfall),
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    proposal = {
        **material,
        "proposal_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination, proposal)
    written = Path(destination).expanduser().resolve()
    verified = decode_g1c_v2_entry_sizing_proposal(
        written.read_text(encoding="utf-8")
    )
    if verified != proposal:
        raise G1CV2EntrySizingProposalError(
            "written entry sizing proposal did not round-trip"
        )
    return proposal


def decode_g1c_v2_entry_sizing_proposal(payload: str) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "sizing_policy",
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_quote_mint",
        "source_quote_decimals",
        "source_quote_usd_per_token",
        "source_entry_input_amount",
        "source_quote_token_amount",
        "source_quote_notional_usd",
        "target_quote_mint",
        "target_quote_decimals",
        "target_quote_usd_per_token",
        "quote_evidence_fingerprint_sha256",
        "quote_evidence_observed_at_unix_ms",
        "quote_evidence_authority",
        "proposed_entry_input_amount",
        "proposed_quote_token_amount",
        "proposed_quote_notional_usd",
        "notional_shortfall_usd",
        "candidate_value_authority",
        "candidate_authoring_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "proposal_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal has unknown or missing fields"
        )

    static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "sizing_policy": _SIZING_POLICY,
        "quote_evidence_authority": _REFERENCE_AUTHORITY,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static.items():
        if document.get(name) != expected:
            raise G1CV2EntrySizingProposalError(
                f"entry sizing proposal {name} authority is unsupported"
            )

    for name in (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "quote_evidence_fingerprint_sha256",
        "proposal_fingerprint_sha256",
    ):
        _require_sha256(name, document.get(name))

    for name in (
        "source_paper_run_id",
        "source_quote_mint",
        "target_quote_mint",
    ):
        _require_non_empty_text(name, document.get(name))
    if document["source_quote_mint"] == document["target_quote_mint"]:
        raise G1CV2EntrySizingProposalError(
            "target quote mint must differ from source quote mint"
        )

    _require_decimals(
        "source_quote_decimals",
        document.get("source_quote_decimals"),
    )
    _require_decimals(
        "target_quote_decimals",
        document.get("target_quote_decimals"),
    )
    for name in (
        "source_quote_usd_per_token",
        "source_quote_token_amount",
        "source_quote_notional_usd",
        "target_quote_usd_per_token",
        "proposed_quote_token_amount",
        "proposed_quote_notional_usd",
    ):
        _parse_positive_decimal(name, document.get(name))
    _parse_non_negative_decimal(
        "notional_shortfall_usd",
        document.get("notional_shortfall_usd"),
    )
    _require_positive_u64(
        "source_entry_input_amount",
        document.get("source_entry_input_amount"),
    )
    _require_positive_u64(
        "proposed_entry_input_amount",
        document.get("proposed_entry_input_amount"),
    )
    _require_non_negative_int(
        "quote_evidence_observed_at_unix_ms",
        document.get("quote_evidence_observed_at_unix_ms"),
    )

    source_notional = _parse_positive_decimal(
        "source_quote_notional_usd",
        document["source_quote_notional_usd"],
    )
    proposed_notional = _parse_positive_decimal(
        "proposed_quote_notional_usd",
        document["proposed_quote_notional_usd"],
    )
    shortfall = _parse_non_negative_decimal(
        "notional_shortfall_usd",
        document["notional_shortfall_usd"],
    )
    if proposed_notional > source_notional:
        raise G1CV2EntrySizingProposalError(
            "proposed quote notional exceeds source quote notional"
        )
    if source_notional - proposed_notional != shortfall:
        raise G1CV2EntrySizingProposalError(
            "proposal notional shortfall is inconsistent"
        )

    claimed = document["proposal_fingerprint_sha256"]
    material = dict(document)
    del material["proposal_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal fingerprint mismatch"
        )
    return document


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise G1CV2EntrySizingProposalError(
            "decimal value must be finite"
        )
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _parse_positive_decimal(name: str, value: object) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a positive finite decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a positive finite decimal string"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a positive finite decimal string"
        )
    if _decimal_text(parsed) != value:
        raise G1CV2EntrySizingProposalError(
            f"{name} must use canonical decimal text"
        )
    return parsed


def _parse_non_negative_decimal(name: str, value: object) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a non-negative finite decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a non-negative finite decimal string"
        ) from error
    if not parsed.is_finite() or parsed < 0:
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a non-negative finite decimal string"
        )
    if _decimal_text(parsed) != value:
        raise G1CV2EntrySizingProposalError(
            f"{name} must use canonical decimal text"
        )
    return parsed


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2EntrySizingProposalError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2EntrySizingProposalError(
            f"{label} must be an existing regular non-symlink file"
        )
    return path.resolve()


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2EntrySizingProposalError(
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
        raise G1CV2EntrySizingProposalError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(destination: str | Path, value: dict[str, object]) -> None:
    try:
        path = Path(destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "entry sizing proposal destination already exists"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal parent must be a real directory"
        )
    payload = _canonical_json(value).encode("utf-8")
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
                "entry sizing proposal destination appeared during write"
            )
        temporary.rename(path)
        path.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _decode_canonical_text(payload: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2EntrySizingProposalError(
            "entry sizing proposal must use canonical JSON"
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
        raise G1CV2EntrySizingProposalError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 18
    ):
        raise G1CV2EntrySizingProposalError(
            f"{name} must be an integer within [0, 18]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_U64
    ):
        raise G1CV2EntrySizingProposalError(
            f"{name} must be a positive u64 amount"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-entry-sizing-proposal",
        description=(
            "Create one evidence-only G1C v2 raw entry sizing proposal by "
            "preserving authenticated source quote notional and flooring "
            "to target raw units."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--target-quote-mint", required=True)
    parser.add_argument("--target-quote-decimals", required=True, type=int)
    parser.add_argument("--target-quote-usd-per-token", required=True)
    parser.add_argument("--quote-evidence-fingerprint-sha256", required=True)
    parser.add_argument(
        "--quote-evidence-observed-at-unix-ms",
        required=True,
        type=int,
    )
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        proposal = propose_g1c_v2_entry_sizing(
            source_runtime_manifest_path=args.source_runtime_manifest,
            target_quote_mint=args.target_quote_mint,
            target_quote_decimals=args.target_quote_decimals,
            target_quote_usd_per_token=args.target_quote_usd_per_token,
            quote_evidence_fingerprint_sha256=(
                args.quote_evidence_fingerprint_sha256
            ),
            quote_evidence_observed_at_unix_ms=(
                args.quote_evidence_observed_at_unix_ms
            ),
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2EntrySizingProposalError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            _canonical_json({"status": "FAILED", "error": str(error)}),
            end="",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(_canonical_json(proposal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
