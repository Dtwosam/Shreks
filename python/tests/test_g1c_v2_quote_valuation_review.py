from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from shreks_brain.g1c_v2_quote_valuation_reference import (
    capture_g1c_v2_quote_valuation_reference,
)
from shreks_brain.g1c_v2_quote_valuation_review import (
    G1CV2QuoteValuationReviewError,
    decode_g1c_v2_quote_valuation_review,
    review_g1c_v2_quote_valuation_references,
)

from test_observer_quote_asset_usd_evidence import (
    AS_OF,
    TOKEN,
    WSOL,
    _database,
    _snapshot,
)


def _references(tmp_path: Path) -> list[Path]:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    inputs = (
        ("pump_swap", AS_OF - 3_000, 0.20),
        ("other_solana", AS_OF - 2_000, 0.25),
        ("pump_fun_bonding_curve", AS_OF - 1_000, 0.30),
    )
    references: list[Path] = []
    for index, (venue, observed_at, price_usd) in enumerate(inputs, start=1):
        row_id = _snapshot(
            database,
            candidate_id,
            observed_at_unix_ms=observed_at,
            venue=venue,
            price_native="0.002",
            price_usd=price_usd,
        )
        path = tmp_path / f"reference-{index}.json"
        capture_g1c_v2_quote_valuation_reference(
            database_path=database,
            candidate_id=candidate_id,
            as_of_unix_ms=AS_OF,
            source="dexscreener",
            venue=venue,
            base_mint=TOKEN,
            quote_mint=WSOL,
            max_age_ms=60_000,
            expected_market_row_id=row_id,
            destination=path,
        )
        references.append(path)
    return references


def test_review_authenticates_references_and_computes_exact_median(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    destination = tmp_path / "review.json"

    review = review_g1c_v2_quote_valuation_references(
        reference_paths=references,
        destination=destination,
    )

    assert review["schema_name"] == "shreks.g1c_v2_quote_valuation_review"
    assert review["schema_version"] == 1
    assert review["status"] == "REVIEW_EVIDENCE_ONLY"
    assert review["review_policy"] == "median_exact_reference_values"
    assert review["reference_count"] == 3
    assert review["as_of_unix_ms"] == AS_OF
    assert review["quote_mint"] == WSOL
    assert review["source"] == "dexscreener"
    assert review["venues"] == [
        "other_solana",
        "pump_fun_bonding_curve",
        "pump_swap",
    ]
    assert review["min_quote_asset_usd_per_token"] == "100"
    assert review["median_quote_asset_usd_per_token"] == "125"
    assert review["max_quote_asset_usd_per_token"] == "150"
    assert review["median_absolute_deviation_usd"] == "25"
    assert review["range_spread_bps_of_median"] == "4000"
    assert review["oldest_reference_observed_at_unix_ms"] == AS_OF - 3_000
    assert review["newest_reference_observed_at_unix_ms"] == AS_OF - 1_000
    assert review["quote_evidence_observed_at_unix_ms"] == AS_OF - 3_000
    assert review["candidate_value_authority"] == "NOT_GRANTED"
    assert review["candidate_authoring_authority"] == "NOT_GRANTED"
    assert review["rotation_authority"] == "NOT_GRANTED"
    assert review["scoring_authority"] == "NOT_GRANTED"
    assert review["paper_promotion_authority"] == "BLOCKED"
    assert review["live_authority"] == "DISABLED"
    assert len(review["review_fingerprint_sha256"]) == 64
    assert len(review["references"]) == 3
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert decode_g1c_v2_quote_valuation_review(
        destination.read_text(encoding="utf-8")
    ) == review


def test_review_is_order_independent(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    first = review_g1c_v2_quote_valuation_references(
        reference_paths=references,
        destination=tmp_path / "first.json",
    )
    second = review_g1c_v2_quote_valuation_references(
        reference_paths=list(reversed(references)),
        destination=tmp_path / "second.json",
    )
    assert first == second


def test_review_rejects_duplicate_reference_identity(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    with pytest.raises(
        G1CV2QuoteValuationReviewError,
        match="duplicate|unique",
    ):
        review_g1c_v2_quote_valuation_references(
            reference_paths=[references[0], references[1], references[0]],
            destination=tmp_path / "review.json",
        )


def test_review_rejects_too_few_references(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    with pytest.raises(
        G1CV2QuoteValuationReviewError,
        match="at least three",
    ):
        review_g1c_v2_quote_valuation_references(
            reference_paths=references[:2],
            destination=tmp_path / "review.json",
        )


def test_review_rejects_tampered_reference(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    document = json.loads(references[0].read_text(encoding="utf-8"))
    document["quote_asset_usd_per_token"] = "999"
    references[0].write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        (G1CV2QuoteValuationReviewError, ValueError),
        match="fingerprint|reference",
    ):
        review_g1c_v2_quote_valuation_references(
            reference_paths=references,
            destination=tmp_path / "review.json",
        )


def test_review_is_write_once_and_decoder_rejects_authority_escalation(
    tmp_path: Path,
) -> None:
    references = _references(tmp_path)
    destination = tmp_path / "review.json"
    review = review_g1c_v2_quote_valuation_references(
        reference_paths=references,
        destination=destination,
    )

    with pytest.raises(FileExistsError):
        review_g1c_v2_quote_valuation_references(
            reference_paths=references,
            destination=destination,
        )

    tampered = dict(review)
    tampered["candidate_value_authority"] = "GRANTED"
    payload = (
        json.dumps(
            tampered,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
    with pytest.raises(
        G1CV2QuoteValuationReviewError,
        match="authority|fingerprint",
    ):
        decode_g1c_v2_quote_valuation_review(payload)


def test_review_cli_is_offline_and_grants_no_runtime_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_quote_valuation_review.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-quote-valuation-review = '
        '"shreks_brain.g1c_v2_quote_valuation_review:main"'
        in pyproject
    )
    for forbidden in (
        "sqlite3",
        "ObserverMarketStore",
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "author_g1c_v2_runtime_manifest_candidate",
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
