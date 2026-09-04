from __future__ import annotations

import json
from pathlib import Path

import pytest

from shreks_brain.fast_deterministic_lifecycle import (
    FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME,
    FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION,
    FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION,
    FastDeterministicComparisonCatalog,
    decode_fast_deterministic_comparison_catalog,
)


EXPECTED = (
    "fl9-baseline-graduation-flow-longer-runner-v1",
    "fl9-baseline-graduation-flow-wallet-cohort-v1",
    "fl9-baseline-impulse-scalp-longer-runner-v1",
    "fl9-baseline-impulse-scalp-wallet-cohort-v1",
    "fl9-baseline-micro-pullback-longer-runner-v1",
    "fl9-baseline-micro-pullback-wallet-cohort-v1",
    "fl9-baseline-pre-graduation-longer-runner-v1",
    "fl9-baseline-pre-graduation-wallet-cohort-v1",
)
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_comparison_catalog_v1.json"
)


def test_python_decodes_shared_rust_comparison_catalog_exactly() -> None:
    catalog = decode_fast_deterministic_comparison_catalog(
        FIXTURE.read_text(encoding="utf-8")
    )

    assert type(catalog) is FastDeterministicComparisonCatalog
    assert catalog.schema_name == FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME
    assert catalog.schema_version == FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION
    assert catalog.catalog_version == FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION
    assert tuple(value.candidate_version for value in catalog.candidates) == EXPECTED
    assert len({value.candidate_fingerprint_sha256 for value in catalog.candidates}) == 8
    assert len(catalog.catalog_fingerprint_sha256) == 64

    pairs = {
        (
            value.lifecycle_policy.entry_baseline_kind,
            value.lifecycle_policy.manager_baseline_kind,
        )
        for value in catalog.candidates
    }
    assert len(pairs) == 8


def test_catalog_rejects_noncanonical_or_tampered_payload() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    document = json.loads(raw)

    with pytest.raises(ValueError, match="canonical"):
        decode_fast_deterministic_comparison_catalog(
            json.dumps(document, indent=2)
        )

    document["catalog_version"] = "tampered"
    tampered = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(ValueError, match="fingerprint|version"):
        decode_fast_deterministic_comparison_catalog(tampered)


def test_catalog_decoder_source_contains_no_reference_policy_thresholds() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_lifecycle"
        / "comparison_catalog.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "min_buy_count",
        "min_reclaim_buy_count",
        "graduation_target_real_base_reserve_raw",
        "min_post_buy_count",
        "min_support_wallet_count_for_ride",
        "downside_risk_weight",
        "entry_target_exposure_fraction =",
        "reduce_remaining_fraction =",
    ):
        assert forbidden not in source
