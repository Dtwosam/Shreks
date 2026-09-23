from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

from shreks_brain.g1c_v2_entry_sizing_proposal import (
    G1CV2EntrySizingProposalError,
    _REVIEW_AUTHORITY,
    _canonical_json,
    _propose_g1c_v2_entry_sizing_with_authority,
    _write_once,
    decode_g1c_v2_entry_sizing_proposal,
)
from shreks_brain.g1c_v2_quote_valuation_review import (
    G1CV2QuoteValuationReviewError,
    decode_g1c_v2_quote_valuation_review,
)


class G1CV2ReviewBackedEntrySizingError(ValueError):
    """Raised when review-backed evidence-only sizing cannot be derived safely."""


def propose_g1c_v2_entry_sizing_from_review(
    *,
    source_runtime_manifest_path: str | Path,
    review_path: str | Path,
    target_quote_decimals: int,
    destination: str | Path,
) -> dict[str, object]:
    source_file = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    source_payload = _read_regular_file_stable(
        source_file,
        label="source runtime manifest",
    )
    review_file = _resolve_existing_regular_file(
        review_path,
        label="quote-valuation review",
    )
    review_payload = _read_regular_file_stable(
        review_file,
        label="quote-valuation review",
    )
    try:
        review = decode_g1c_v2_quote_valuation_review(
            review_payload.decode("utf-8")
        )
    except (
        G1CV2QuoteValuationReviewError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        raise G1CV2ReviewBackedEntrySizingError(
            f"quote-valuation review authentication failed: {error}"
        ) from error

    try:
        with tempfile.TemporaryDirectory(
            prefix="shreks-g1c-v2-review-backed-sizing-"
        ) as temporary_directory:
            temporary_proposal = (
                Path(temporary_directory) / "entry-sizing-proposal.json"
            )
            proposal = _propose_g1c_v2_entry_sizing_with_authority(
                source_runtime_manifest_path=source_file,
                target_quote_mint=str(review["quote_mint"]),
                target_quote_decimals=target_quote_decimals,
                target_quote_usd_per_token=str(
                    review["median_quote_asset_usd_per_token"]
                ),
                quote_evidence_fingerprint_sha256=str(
                    review["review_fingerprint_sha256"]
                ),
                quote_evidence_observed_at_unix_ms=int(
                    review["quote_evidence_observed_at_unix_ms"]
                ),
                quote_evidence_authority=_REVIEW_AUTHORITY,
                destination=temporary_proposal,
            )

            source_after = _read_regular_file_stable(
                source_file,
                label="source runtime manifest",
            )
            if source_after != source_payload:
                raise G1CV2ReviewBackedEntrySizingError(
                    "source runtime manifest changed while sizing was derived"
                )

            review_after = _read_regular_file_stable(
                review_file,
                label="quote-valuation review",
            )
            if review_after != review_payload:
                raise G1CV2ReviewBackedEntrySizingError(
                    "quote-valuation review changed while sizing was derived"
                )

            _write_once(destination, proposal)
            written = Path(destination).expanduser().resolve()
            verified = decode_g1c_v2_entry_sizing_proposal(
                written.read_text(encoding="utf-8")
            )
            if verified != proposal:
                raise G1CV2ReviewBackedEntrySizingError(
                    "written review-backed entry sizing proposal did not round-trip"
                )
    except G1CV2ReviewBackedEntrySizingError:
        raise
    except (
        FileExistsError,
        G1CV2EntrySizingProposalError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2ReviewBackedEntrySizingError(
            f"review-backed entry sizing failed: {error}"
        ) from error

    return proposal


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2ReviewBackedEntrySizingError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2ReviewBackedEntrySizingError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2ReviewBackedEntrySizingError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2ReviewBackedEntrySizingError(
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
        raise G1CV2ReviewBackedEntrySizingError(
            f"{label} changed while being read"
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-review-backed-entry-sizing",
        description=(
            "Create one evidence-only entry-sizing proposal from an "
            "authenticated multi-reference quote-valuation review."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--target-quote-decimals", required=True, type=int)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        proposal = propose_g1c_v2_entry_sizing_from_review(
            source_runtime_manifest_path=args.source_runtime_manifest,
            review_path=args.review,
            target_quote_decimals=args.target_quote_decimals,
            destination=args.destination,
        )
    except (
        FileExistsError,
        G1CV2ReviewBackedEntrySizingError,
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
