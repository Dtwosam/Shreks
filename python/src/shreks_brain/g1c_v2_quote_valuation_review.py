from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from shreks_brain.g1c_v2_quote_valuation_reference import (
    G1CV2QuoteValuationReferenceError,
    decode_g1c_v2_quote_valuation_reference,
)


_SCHEMA_NAME = "shreks.g1c_v2_quote_valuation_review"
_SCHEMA_VERSION = 1
_STATUS = "REVIEW_EVIDENCE_ONLY"
_REVIEW_POLICY = "median_exact_reference_values"
_NOT_GRANTED = "NOT_GRANTED"
_BLOCKED = "BLOCKED"
_DISABLED = "DISABLED"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G1CV2QuoteValuationReviewError(ValueError):
    """Raised when canonical quote references cannot form a safe review."""


def review_g1c_v2_quote_valuation_references(
    *,
    reference_paths: list[str | Path] | tuple[str | Path, ...],
    destination: str | Path,
) -> dict[str, object]:
    if not isinstance(reference_paths, (list, tuple)):
        raise G1CV2QuoteValuationReviewError(
            "reference_paths must be a list or tuple"
        )
    if len(reference_paths) < 3:
        raise G1CV2QuoteValuationReviewError(
            "at least three quote references are required"
        )

    references: list[dict[str, object]] = []
    source_paths: set[Path] = set()

    for raw_path in reference_paths:
        path = _resolve_existing_regular_file(
            raw_path,
            label="quote reference",
        )
        if path in source_paths:
            raise G1CV2QuoteValuationReviewError(
                "quote reference paths must be unique"
            )
        source_paths.add(path)
        payload = _read_regular_file_stable(
            path,
            label="quote reference",
        )
        try:
            reference = decode_g1c_v2_quote_valuation_reference(
                payload.decode("utf-8")
            )
        except (
            G1CV2QuoteValuationReferenceError,
            UnicodeDecodeError,
            ValueError,
        ) as error:
            raise G1CV2QuoteValuationReviewError(
                f"quote reference authentication failed: {error}"
            ) from error
        if reference["selection_mode"] != "expected_exact_market_row":
            raise G1CV2QuoteValuationReviewError(
                "review requires exact expected market-row references"
            )
        if reference["expected_market_row_id"] != reference["market_row_id"]:
            raise G1CV2QuoteValuationReviewError(
                "reference expected market row does not match selected row"
            )
        references.append(reference)

    as_of_values = {int(item["as_of_unix_ms"]) for item in references}
    quote_mints = {str(item["quote_mint"]) for item in references}
    sources = {str(item["source"]) for item in references}
    if len(as_of_values) != 1:
        raise G1CV2QuoteValuationReviewError(
            "all quote references must share one as_of_unix_ms"
        )
    if len(quote_mints) != 1:
        raise G1CV2QuoteValuationReviewError(
            "all quote references must share one quote mint"
        )
    if len(sources) != 1:
        raise G1CV2QuoteValuationReviewError(
            "all quote references must share one source"
        )

    market_row_ids = [int(item["market_row_id"]) for item in references]
    fingerprints = [
        str(item["reference_fingerprint_sha256"])
        for item in references
    ]
    if len(set(market_row_ids)) != len(market_row_ids):
        raise G1CV2QuoteValuationReviewError(
            "quote references must use unique market row ids"
        )
    if len(set(fingerprints)) != len(fingerprints):
        raise G1CV2QuoteValuationReviewError(
            "quote references must use unique reference fingerprints"
        )

    compact = sorted(
        (
            {
                "market_row_id": int(item["market_row_id"]),
                "candidate_id": int(item["candidate_id"]),
                "observed_at_unix_ms": int(
                    item["observed_at_unix_ms"]
                ),
                "venue": str(item["venue"]),
                "pair_address": str(item["pair_address"]),
                "base_mint": str(item["base_mint"]),
                "quote_asset_usd_per_token": _canonical_positive_decimal(
                    "quote_asset_usd_per_token",
                    item["quote_asset_usd_per_token"],
                ),
                "reference_fingerprint_sha256": str(
                    item["reference_fingerprint_sha256"]
                ),
            }
            for item in references
        ),
        key=lambda item: (
            item["market_row_id"],
            item["reference_fingerprint_sha256"],
        ),
    )

    statistics = _review_statistics(compact)
    as_of_unix_ms = next(iter(as_of_values))
    quote_mint = next(iter(quote_mints))
    source = next(iter(sources))
    venues = sorted({str(item["venue"]) for item in compact})

    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "review_policy": _REVIEW_POLICY,
        "reference_count": len(compact),
        "as_of_unix_ms": as_of_unix_ms,
        "quote_mint": quote_mint,
        "source": source,
        "venues": venues,
        "references": compact,
        **statistics,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    review = {
        **material,
        "review_fingerprint_sha256": _sha256_canonical(material),
    }
    destination_path = _resolve_new_destination(destination)
    _write_once(destination_path, review)
    verified = decode_g1c_v2_quote_valuation_review(
        destination_path.read_text(encoding="utf-8")
    )
    if verified != review:
        raise G1CV2QuoteValuationReviewError(
            "written quote-valuation review did not round-trip"
        )
    return review


def decode_g1c_v2_quote_valuation_review(
    payload: str,
) -> dict[str, object]:
    document = _decode_canonical_text(payload)
    expected_keys = {
        "schema_name",
        "schema_version",
        "status",
        "review_policy",
        "reference_count",
        "as_of_unix_ms",
        "quote_mint",
        "source",
        "venues",
        "references",
        "min_quote_asset_usd_per_token",
        "median_quote_asset_usd_per_token",
        "max_quote_asset_usd_per_token",
        "median_absolute_deviation_usd",
        "range_spread_bps_of_median",
        "oldest_reference_observed_at_unix_ms",
        "newest_reference_observed_at_unix_ms",
        "quote_evidence_observed_at_unix_ms",
        "candidate_value_authority",
        "candidate_authoring_authority",
        "rotation_authority",
        "scoring_authority",
        "paper_promotion_authority",
        "live_authority",
        "review_fingerprint_sha256",
    }
    if set(document) != expected_keys:
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review has unknown or missing fields"
        )

    static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "review_policy": _REVIEW_POLICY,
        "candidate_value_authority": _NOT_GRANTED,
        "candidate_authoring_authority": _NOT_GRANTED,
        "rotation_authority": _NOT_GRANTED,
        "scoring_authority": _NOT_GRANTED,
        "paper_promotion_authority": _BLOCKED,
        "live_authority": _DISABLED,
    }
    for name, expected in static.items():
        if document.get(name) != expected:
            raise G1CV2QuoteValuationReviewError(
                f"quote-valuation review {name} authority is unsupported"
            )

    reference_count = document.get("reference_count")
    if (
        isinstance(reference_count, bool)
        or not isinstance(reference_count, int)
        or reference_count < 3
    ):
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review requires at least three references"
        )
    _require_non_negative_int(
        "as_of_unix_ms",
        document.get("as_of_unix_ms"),
    )
    _require_non_empty_text("quote_mint", document.get("quote_mint"))
    _require_non_empty_text("source", document.get("source"))

    venues = document.get("venues")
    if (
        not isinstance(venues, list)
        or not venues
        or venues != sorted(set(venues))
        or any(not isinstance(value, str) or not value for value in venues)
    ):
        raise G1CV2QuoteValuationReviewError(
            "venues must be one sorted unique non-empty string list"
        )

    references = document.get("references")
    if not isinstance(references, list) or len(references) != reference_count:
        raise G1CV2QuoteValuationReviewError(
            "reference_count does not match references"
        )
    compact: list[dict[str, object]] = []
    for item in references:
        if not isinstance(item, dict):
            raise G1CV2QuoteValuationReviewError(
                "every review reference must be an object"
            )
        expected_reference_keys = {
            "market_row_id",
            "candidate_id",
            "observed_at_unix_ms",
            "venue",
            "pair_address",
            "base_mint",
            "quote_asset_usd_per_token",
            "reference_fingerprint_sha256",
        }
        if set(item) != expected_reference_keys:
            raise G1CV2QuoteValuationReviewError(
                "review reference has unknown or missing fields"
            )
        _require_positive_int("market_row_id", item.get("market_row_id"))
        _require_positive_int("candidate_id", item.get("candidate_id"))
        _require_non_negative_int(
            "observed_at_unix_ms",
            item.get("observed_at_unix_ms"),
        )
        _require_non_empty_text("venue", item.get("venue"))
        if not isinstance(item.get("pair_address"), str):
            raise G1CV2QuoteValuationReviewError(
                "pair_address must be a string"
            )
        _require_non_empty_text("base_mint", item.get("base_mint"))
        quote_value = _canonical_positive_decimal(
            "quote_asset_usd_per_token",
            item.get("quote_asset_usd_per_token"),
        )
        _require_sha256(
            "reference_fingerprint_sha256",
            item.get("reference_fingerprint_sha256"),
        )
        compact.append(
            {
                **item,
                "quote_asset_usd_per_token": quote_value,
            }
        )

    expected_sorted = sorted(
        compact,
        key=lambda item: (
            item["market_row_id"],
            item["reference_fingerprint_sha256"],
        ),
    )
    if compact != expected_sorted:
        raise G1CV2QuoteValuationReviewError(
            "review references must use canonical row/fingerprint ordering"
        )
    row_ids = [int(item["market_row_id"]) for item in compact]
    fingerprints = [
        str(item["reference_fingerprint_sha256"]) for item in compact
    ]
    if len(set(row_ids)) != len(row_ids):
        raise G1CV2QuoteValuationReviewError(
            "review market row ids must be unique"
        )
    if len(set(fingerprints)) != len(fingerprints):
        raise G1CV2QuoteValuationReviewError(
            "review reference fingerprints must be unique"
        )
    if sorted({str(item["venue"]) for item in compact}) != venues:
        raise G1CV2QuoteValuationReviewError(
            "venues do not match embedded references"
        )

    statistics = _review_statistics(compact)
    for name, expected in statistics.items():
        if document.get(name) != expected:
            raise G1CV2QuoteValuationReviewError(
                f"quote-valuation review {name} is inconsistent"
            )

    _require_sha256(
        "review_fingerprint_sha256",
        document.get("review_fingerprint_sha256"),
    )
    claimed = document["review_fingerprint_sha256"]
    material = dict(document)
    del material["review_fingerprint_sha256"]
    if _sha256_canonical(material) != claimed:
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review fingerprint mismatch"
        )
    return document


def _review_statistics(
    references: list[dict[str, object]],
) -> dict[str, object]:
    values = [
        Decimal(str(item["quote_asset_usd_per_token"]))
        for item in references
    ]
    ordered = sorted(values)
    median_value = _median_decimal(ordered)
    deviations = sorted(abs(value - median_value) for value in ordered)
    median_absolute_deviation = _median_decimal(deviations)
    minimum = ordered[0]
    maximum = ordered[-1]
    with localcontext() as context:
        context.prec = 80
        range_spread_bps = (
            (maximum - minimum) / median_value * Decimal(10_000)
        )
    observations = [
        int(item["observed_at_unix_ms"]) for item in references
    ]
    oldest = min(observations)
    newest = max(observations)
    return {
        "min_quote_asset_usd_per_token": _decimal_text(minimum),
        "median_quote_asset_usd_per_token": _decimal_text(median_value),
        "max_quote_asset_usd_per_token": _decimal_text(maximum),
        "median_absolute_deviation_usd": _decimal_text(
            median_absolute_deviation
        ),
        "range_spread_bps_of_median": _decimal_text(range_spread_bps),
        "oldest_reference_observed_at_unix_ms": oldest,
        "newest_reference_observed_at_unix_ms": newest,
        "quote_evidence_observed_at_unix_ms": oldest,
    }


def _median_decimal(ordered: list[Decimal]) -> Decimal:
    if not ordered:
        raise G1CV2QuoteValuationReviewError(
            "cannot compute median of empty evidence"
        )
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _canonical_positive_decimal(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a positive canonical decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a positive canonical decimal string"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a positive canonical decimal string"
        )
    canonical = _decimal_text(parsed)
    if canonical != value:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must use canonical decimal text"
        )
    return canonical


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise G1CV2QuoteValuationReviewError(
            "decimal value must be finite"
        )
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2QuoteValuationReviewError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2QuoteValuationReviewError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2QuoteValuationReviewError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2QuoteValuationReviewError(
            f"{label} could not be read"
        ) from error
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or len(payload) != before.st_size:
        raise G1CV2QuoteValuationReviewError(
            f"{label} changed while being read"
        )
    return payload


def _resolve_new_destination(raw_path: str | Path) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError, OSError) as error:
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review destination path is invalid"
        ) from error
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            "quote-valuation review destination already exists"
        )
    return path


def _write_once(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review parent must be a real directory"
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
                "quote-valuation review destination appeared during write"
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
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review must be text"
        )
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review must have one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review is malformed JSON"
        ) from error
    if not isinstance(document, dict):
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review must be one JSON object"
        )
    if _canonical_json(document) != payload:
        raise G1CV2QuoteValuationReviewError(
            "quote-valuation review must use canonical JSON"
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
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be lowercase SHA-256 hex"
        )


def _require_non_empty_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise G1CV2QuoteValuationReviewError(
            f"{name} must be a positive integer"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-quote-valuation-review",
        description=(
            "Review three or more canonical G1C v2 quote references using "
            "an exact Decimal median without granting candidate authority."
        ),
    )
    parser.add_argument(
        "--reference",
        action="append",
        required=True,
        dest="references",
    )
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        review = review_g1c_v2_quote_valuation_references(
            reference_paths=args.references,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2QuoteValuationReviewError,
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

    sys.stdout.write(_canonical_json(review))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
