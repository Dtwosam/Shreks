from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.observer_market.store import (
    ObserverMarketReadError,
    ObserverMarketStore,
)


_SCHEMA_NAME = "shreks.g1c_v2_quote_valuation_reference"
_SCHEMA_VERSION = 1
_STATUS = "REFERENCE_EVIDENCE_ONLY"
_VALUATION_MODE = "exact_market_ratio"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G1CV2QuoteValuationReferenceError(ValueError):
    """Raised when a read-only quote-valuation reference cannot be captured safely."""


def capture_g1c_v2_quote_valuation_reference(
    *,
    database_path: str | Path,
    candidate_id: int,
    as_of_unix_ms: int,
    source: str,
    venue: str,
    base_mint: str,
    quote_mint: str,
    max_age_ms: int,
    expected_market_row_id: int | None,
    destination: str | Path,
) -> dict[str, object]:
    database = _resolve_existing_regular_file(
        database_path,
        label="observer database",
    )
    destination_path = _resolve_new_destination(destination)

    _require_positive_int("candidate_id", candidate_id)
    _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
    _require_non_empty_text("source", source)
    _require_non_empty_text("venue", venue)
    _require_non_empty_text("base_mint", base_mint)
    _require_non_empty_text("quote_mint", quote_mint)
    _require_non_negative_int("max_age_ms", max_age_ms)
    if expected_market_row_id is not None:
        _require_positive_int("expected_market_row_id", expected_market_row_id)

    try:
        evidence = ObserverMarketStore(database).quote_asset_usd_evidence(
            candidate_id,
            as_of_unix_ms,
            source=source,
            venue=venue,
            base_mint=base_mint,
            quote_mint=quote_mint,
            max_age_ms=max_age_ms,
            expected_market_row_id=expected_market_row_id,
        )
    except (ObserverMarketReadError, OSError, TypeError, ValueError) as error:
        raise G1CV2QuoteValuationReferenceError(
            f"exact read-only market evidence could not be captured: {error}"
        ) from error

    if evidence.candidate_id != candidate_id:
        raise G1CV2QuoteValuationReferenceError(
            "market evidence changed candidate identity"
        )
    if evidence.source != source or evidence.venue != venue:
        raise G1CV2QuoteValuationReferenceError(
            "market evidence changed source or venue identity"
        )
    if evidence.base_mint != base_mint or evidence.quote_mint != quote_mint:
        raise G1CV2QuoteValuationReferenceError(
            "market evidence changed base or quote mint identity"
        )
    if evidence.observed_at_unix_ms > as_of_unix_ms:
        raise G1CV2QuoteValuationReferenceError(
            "market evidence observation is later than requested as-of boundary"
        )
    if as_of_unix_ms - evidence.observed_at_unix_ms > max_age_ms:
        raise G1CV2QuoteValuationReferenceError(
            "market evidence exceeds requested freshness boundary"
        )

    base_price_quote = _require_positive_decimal_text(
        "base_price_quote",
        evidence.base_price_quote,
        canonical=False,
    )
    base_price_usd = _decimal_from_number(
        "base_price_usd",
        evidence.base_price_usd,
    )
    quote_usd = _decimal_from_number(
        "quote_asset_usd_per_token",
        evidence.quote_asset_usd_per_token,
    )

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "valuation_mode": _VALUATION_MODE,
        "selection_mode": (
            "expected_exact_market_row"
            if expected_market_row_id is not None
            else "latest_exact_market_within_freshness"
        ),
        "expected_market_row_id": expected_market_row_id,
        "market_row_id": evidence.market_row_id,
        "candidate_id": evidence.candidate_id,
        "observed_at_unix_ms": evidence.observed_at_unix_ms,
        "as_of_unix_ms": as_of_unix_ms,
        "max_age_ms": max_age_ms,
        "source": evidence.source,
        "venue": evidence.venue,
        "pair_address": evidence.pair_address,
        "base_mint": evidence.base_mint,
        "quote_mint": evidence.quote_mint,
        "base_price_quote": base_price_quote,
        "base_price_usd": _decimal_text(base_price_usd),
        "quote_asset_usd_per_token": _decimal_text(quote_usd),
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    reference = {
        **material,
        "reference_fingerprint_sha256": _sha256_canonical(material),
    }
    _write_once(destination_path, reference)
    verified = decode_g1c_v2_quote_valuation_reference(
        destination_path.read_text(encoding="utf-8")
    )
    if verified != reference:
        raise G1CV2QuoteValuationReferenceError(
            "written quote-valuation reference did not round-trip"
        )
    return reference


def decode_g1c_v2_quote_valuation_reference(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "valuation_mode",
        "selection_mode",
        "expected_market_row_id",
        "market_row_id",
        "candidate_id",
        "observed_at_unix_ms",
        "as_of_unix_ms",
        "max_age_ms",
        "source",
        "venue",
        "pair_address",
        "base_mint",
        "quote_mint",
        "base_price_quote",
        "base_price_usd",
        "quote_asset_usd_per_token",
        "candidate_value_authority",
        "candidate_authoring_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "reference_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference has unknown or missing fields"
        )

    static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "valuation_mode": _VALUATION_MODE,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static.items():
        if document.get(name) != expected:
            raise G1CV2QuoteValuationReferenceError(
                f"quote-valuation reference {name} authority is unsupported"
            )

    selection_mode = document.get("selection_mode")
    expected_row = document.get("expected_market_row_id")
    if selection_mode == "expected_exact_market_row":
        _require_positive_int("expected_market_row_id", expected_row)
        if document.get("market_row_id") != expected_row:
            raise G1CV2QuoteValuationReferenceError(
                "selected market row does not match expected market row"
            )
    elif selection_mode == "latest_exact_market_within_freshness":
        if expected_row is not None:
            raise G1CV2QuoteValuationReferenceError(
                "latest-row selection cannot carry expected market row"
            )
    else:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference selection_mode is unsupported"
        )

    _require_positive_int("market_row_id", document.get("market_row_id"))
    _require_positive_int("candidate_id", document.get("candidate_id"))
    _require_non_negative_int(
        "observed_at_unix_ms",
        document.get("observed_at_unix_ms"),
    )
    _require_non_negative_int(
        "as_of_unix_ms",
        document.get("as_of_unix_ms"),
    )
    _require_non_negative_int("max_age_ms", document.get("max_age_ms"))
    if document["observed_at_unix_ms"] > document["as_of_unix_ms"]:
        raise G1CV2QuoteValuationReferenceError(
            "reference observation is later than as-of boundary"
        )
    if (
        document["as_of_unix_ms"] - document["observed_at_unix_ms"]
        > document["max_age_ms"]
    ):
        raise G1CV2QuoteValuationReferenceError(
            "reference observation exceeds freshness boundary"
        )

    for name in ("source", "venue", "base_mint", "quote_mint"):
        _require_non_empty_text(name, document.get(name))
    if not isinstance(document.get("pair_address"), str):
        raise G1CV2QuoteValuationReferenceError(
            "pair_address must be a string"
        )

    _require_positive_decimal_text(
        "base_price_quote",
        document.get("base_price_quote"),
        canonical=False,
    )
    _require_positive_decimal_text(
        "base_price_usd",
        document.get("base_price_usd"),
        canonical=True,
    )
    _require_positive_decimal_text(
        "quote_asset_usd_per_token",
        document.get("quote_asset_usd_per_token"),
        canonical=True,
    )
    _require_sha256(
        "reference_fingerprint_sha256",
        document.get("reference_fingerprint_sha256"),
    )

    claimed = document["reference_fingerprint_sha256"]
    material = dict(document)
    del material["reference_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference fingerprint mismatch"
        )
    return document


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2QuoteValuationReferenceError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2QuoteValuationReferenceError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2QuoteValuationReferenceError(
            f"{label} could not be resolved"
        ) from error


def _resolve_new_destination(raw_path: str | Path) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "quote-valuation reference destination already exists"
        )
    return path


def _decimal_from_number(name: str, value: object) -> Decimal:
    if isinstance(value, bool):
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be positive and finite"
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be positive and finite"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be positive and finite"
        )
    return parsed


def _require_positive_decimal_text(
    name: str,
    value: object,
    *,
    canonical: bool,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a positive finite decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a positive finite decimal string"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a positive finite decimal string"
        )
    if canonical and _decimal_text(parsed) != value:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must use canonical decimal text"
        )
    return value


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise G1CV2QuoteValuationReferenceError(
            "decimal value must be finite"
        )
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _write_once(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference parent must be a real directory"
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
                "quote-valuation reference destination appeared during write"
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
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2QuoteValuationReferenceError(
            "quote-valuation reference must use canonical JSON"
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
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise G1CV2QuoteValuationReferenceError(
            f"{name} must be a positive integer"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-quote-valuation-reference",
        description=(
            "Capture one canonical evidence-only G1C v2 quote-valuation "
            "reference from an exact persisted observer market row."
        ),
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--candidate-id", required=True, type=int)
    parser.add_argument("--as-of-unix-ms", required=True, type=int)
    parser.add_argument("--source", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--base-mint", required=True)
    parser.add_argument("--quote-mint", required=True)
    parser.add_argument("--max-age-ms", required=True, type=int)
    parser.add_argument("--expected-market-row-id", type=int)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        reference = capture_g1c_v2_quote_valuation_reference(
            database_path=args.database,
            candidate_id=args.candidate_id,
            as_of_unix_ms=args.as_of_unix_ms,
            source=args.source,
            venue=args.venue,
            base_mint=args.base_mint,
            quote_mint=args.quote_mint,
            max_age_ms=args.max_age_ms,
            expected_market_row_id=args.expected_market_row_id,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2QuoteValuationReferenceError,
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

    sys.stdout.write(_canonical_json(reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
