from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.g1c_v2_entry_sizing_proposal import (
    decode_g1c_v2_entry_sizing_proposal,
)
from shreks_brain.g1c_v2_review_backed_entry_sizing import (
    G1CV2ReviewBackedEntrySizingError,
    propose_g1c_v2_entry_sizing_from_review,
)
from shreks_brain.g1c_v2_quote_valuation_review import (
    review_g1c_v2_quote_valuation_references,
)
from shreks_brain.g1c_v2_quote_valuation_reference import (
    capture_g1c_v2_quote_valuation_reference,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    encode_observer_paper_campaign_runtime_manifest,
)

from test_observer_campaign_runtime_manifest import _manifest
from test_observer_quote_asset_usd_evidence import (
    AS_OF,
    TOKEN,
    WSOL,
    _database,
    _snapshot,
)


def _review(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    database = tmp_path / "observer.sqlite3"
    candidate_id = _database(database)
    references: list[Path] = []
    for index, (venue, observed_at, price_usd) in enumerate(
        (
            ("pump_swap", AS_OF - 3_000, 0.20),
            ("other_solana", AS_OF - 2_000, 0.25),
            ("pump_fun_bonding_curve", AS_OF - 1_000, 0.30),
        ),
        start=1,
    ):
        row_id = _snapshot(
            database,
            candidate_id,
            observed_at_unix_ms=observed_at,
            venue=venue,
            price_native="0.002",
            price_usd=price_usd,
        )
        reference = tmp_path / f"reference-{index}.json"
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
            destination=reference,
        )
        references.append(reference)

    review_path = tmp_path / "review.json"
    review = review_g1c_v2_quote_valuation_references(
        reference_paths=references,
        destination=review_path,
    )
    return review_path, review


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "source.json"
    path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(_manifest())
    )
    return path


def test_review_backed_sizing_authenticates_review_and_marks_provenance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    review_path, review = _review(tmp_path)
    destination = tmp_path / "proposal.json"

    proposal = propose_g1c_v2_entry_sizing_from_review(
        source_runtime_manifest_path=source,
        review_path=review_path,
        target_quote_decimals=9,
        destination=destination,
    )

    assert proposal["schema_name"] == "shreks.g1c_v2_entry_sizing_proposal"
    assert proposal["status"] == "PROPOSAL_EVIDENCE_ONLY"
    assert proposal["quote_evidence_authority"] == "MULTI_REFERENCE_REVIEW"
    assert proposal["target_quote_mint"] == review["quote_mint"]
    assert proposal["target_quote_usd_per_token"] == (
        review["median_quote_asset_usd_per_token"]
    )
    assert proposal["quote_evidence_fingerprint_sha256"] == (
        review["review_fingerprint_sha256"]
    )
    assert proposal["quote_evidence_observed_at_unix_ms"] == (
        review["quote_evidence_observed_at_unix_ms"]
    )
    assert proposal["candidate_value_authority"] == "NOT_GRANTED"
    assert proposal["candidate_authoring_authority"] == "NOT_GRANTED"
    assert proposal["rotation_authority"] == "NOT_GRANTED"
    assert proposal["scoring_authority"] == "NOT_GRANTED"
    assert proposal["paper_promotion_authority"] == "BLOCKED"
    assert proposal["live_authority"] == "DISABLED"
    assert decode_g1c_v2_entry_sizing_proposal(
        destination.read_text(encoding="utf-8")
    ) == proposal


def test_review_backed_sizing_rejects_tampered_review(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    review_path, _ = _review(tmp_path)
    document = json.loads(review_path.read_text(encoding="utf-8"))
    document["median_quote_asset_usd_per_token"] = "999"
    review_path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        G1CV2ReviewBackedEntrySizingError,
        match="review|fingerprint",
    ):
        propose_g1c_v2_entry_sizing_from_review(
            source_runtime_manifest_path=source,
            review_path=review_path,
            target_quote_decimals=9,
            destination=tmp_path / "proposal.json",
        )


def test_review_backed_sizing_rejects_source_quote_equal_to_review_quote(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    review_path, _ = _review(tmp_path)

    # The underlying sizing contract must still enforce an actual quote rotation.
    document = json.loads(review_path.read_text(encoding="utf-8"))
    document["quote_mint"] = _manifest().policy_bundle.quote_asset.mint
    material = dict(document)
    material.pop("review_fingerprint_sha256")
    import hashlib
    document["review_fingerprint_sha256"] = hashlib.sha256(
        (
            json.dumps(
                material,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    review_path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        G1CV2ReviewBackedEntrySizingError,
        match="different|quote",
    ):
        propose_g1c_v2_entry_sizing_from_review(
            source_runtime_manifest_path=source,
            review_path=review_path,
            target_quote_decimals=6,
            destination=tmp_path / "proposal.json",
        )


def test_existing_explicit_reference_path_remains_backward_compatible(
    tmp_path: Path,
) -> None:
    from shreks_brain.g1c_v2_entry_sizing_proposal import (
        propose_g1c_v2_entry_sizing,
    )

    source = _source(tmp_path)
    proposal = propose_g1c_v2_entry_sizing(
        source_runtime_manifest_path=source,
        target_quote_mint=WSOL,
        target_quote_decimals=9,
        target_quote_usd_per_token="125",
        quote_evidence_fingerprint_sha256="a" * 64,
        quote_evidence_observed_at_unix_ms=AS_OF,
        destination=tmp_path / "proposal.json",
    )
    assert proposal["quote_evidence_authority"] == "EXPLICIT_REFERENCE_ONLY"


def test_review_backed_cli_has_no_runtime_or_candidate_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" / "g1c_v2_review_backed_entry_sizing.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-review-backed-entry-sizing = '
        '"shreks_brain.g1c_v2_review_backed_entry_sizing:main"'
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
        "bind_g1c_v2_runtime_manifest_candidate_authority",
        "author_g1c_v2_runtime_manifest_candidate",
        "rotate_paper_manifest",
        "score_candidate",
        "model_fit",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
