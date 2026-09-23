from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.g1c_v2_review_backed_entry_sizing as sizing
from shreks_brain.g1c_v2_review_backed_entry_sizing import (
    G1CV2ReviewBackedEntrySizingError,
    propose_g1c_v2_entry_sizing_from_review,
)

from test_g1c_v2_review_backed_entry_sizing import _review, _source


def test_review_change_after_derivation_never_publishes_final_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    review_path, _ = _review(tmp_path)
    destination = tmp_path / "proposal.json"

    original = sizing._propose_g1c_v2_entry_sizing_with_authority

    def mutate_review_after_derivation(**kwargs: object) -> dict[str, object]:
        proposal = original(**kwargs)
        review_path.write_bytes(review_path.read_bytes() + b" ")
        return proposal

    monkeypatch.setattr(
        sizing,
        "_propose_g1c_v2_entry_sizing_with_authority",
        mutate_review_after_derivation,
    )

    with pytest.raises(
        G1CV2ReviewBackedEntrySizingError,
        match="quote-valuation review changed while sizing was derived",
    ):
        propose_g1c_v2_entry_sizing_from_review(
            source_runtime_manifest_path=source,
            review_path=review_path,
            target_quote_decimals=9,
            destination=destination,
        )

    assert not destination.exists()


def test_source_change_after_derivation_never_publishes_final_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path)
    review_path, _ = _review(tmp_path)
    destination = tmp_path / "proposal.json"

    original = sizing._propose_g1c_v2_entry_sizing_with_authority

    def mutate_source_after_derivation(**kwargs: object) -> dict[str, object]:
        proposal = original(**kwargs)
        source.write_bytes(source.read_bytes() + b" ")
        return proposal

    monkeypatch.setattr(
        sizing,
        "_propose_g1c_v2_entry_sizing_with_authority",
        mutate_source_after_derivation,
    )

    with pytest.raises(
        G1CV2ReviewBackedEntrySizingError,
        match="source runtime manifest changed while sizing was derived",
    ):
        propose_g1c_v2_entry_sizing_from_review(
            source_runtime_manifest_path=source,
            review_path=review_path,
            target_quote_decimals=9,
            destination=destination,
        )

    assert not destination.exists()
