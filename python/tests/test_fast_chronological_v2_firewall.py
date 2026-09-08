from __future__ import annotations

import pytest

from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES
from shreks_brain.fast_validation_v2.firewall import (
    FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
    fast_forecast_identity_firewall_fingerprint_sha256,
    validate_fast_forecast_identity_firewall,
)


def _fingerprint(feature_names=FAST_FORECAST_FEATURE_NAMES) -> str:
    return fast_forecast_identity_firewall_fingerprint_sha256(feature_names)


def test_sealed_fl8_2_feature_schema_passes_identity_firewall() -> None:
    validate_fast_forecast_identity_firewall(
        feature_names=FAST_FORECAST_FEATURE_NAMES,
        expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
        expected_fingerprint_sha256=_fingerprint(),
    )


@pytest.mark.parametrize(
    "forbidden",
    (
        "decision.mint",
        "decision.quote_mint",
        "decision.actor",
        "decision.signature",
        "decision.sequence",
        "decision.ordinal",
        "decision.provider",
        "lifecycle.signature",
        "market.pool_address",
        "identity.mint_sha256",
    ),
)
def test_raw_or_derived_identity_feature_fails_closed(forbidden: str) -> None:
    changed = FAST_FORECAST_FEATURE_NAMES + (forbidden,)
    fingerprint = fast_forecast_identity_firewall_fingerprint_sha256(changed)

    with pytest.raises(ValueError, match="identity|feature|firewall"):
        validate_fast_forecast_identity_firewall(
            feature_names=changed,
            expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
            expected_fingerprint_sha256=fingerprint,
        )


def test_existing_actor_presence_and_aggregate_actor_features_are_allowed() -> None:
    assert "decision.actor_present" in FAST_FORECAST_FEATURE_NAMES
    assert any(
        name.endswith(".unique_buy_actors")
        for name in FAST_FORECAST_FEATURE_NAMES
    )
    assert any(
        name.endswith(".unique_sell_actors")
        for name in FAST_FORECAST_FEATURE_NAMES
    )
    validate_fast_forecast_identity_firewall(
        feature_names=FAST_FORECAST_FEATURE_NAMES,
        expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
        expected_fingerprint_sha256=_fingerprint(),
    )


def test_wrong_firewall_version_or_fingerprint_fails_closed() -> None:
    with pytest.raises(ValueError, match="version"):
        validate_fast_forecast_identity_firewall(
            feature_names=FAST_FORECAST_FEATURE_NAMES,
            expected_version="wrong",
            expected_fingerprint_sha256=_fingerprint(),
        )

    with pytest.raises(ValueError, match="fingerprint|SHA-256"):
        validate_fast_forecast_identity_firewall(
            feature_names=FAST_FORECAST_FEATURE_NAMES,
            expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
            expected_fingerprint_sha256="0" * 64,
        )


def test_non_exact_feature_schema_change_requires_explicit_review() -> None:
    changed = FAST_FORECAST_FEATURE_NAMES + ("market.new_numeric_feature",)
    with pytest.raises(ValueError, match="schema|feature|firewall"):
        validate_fast_forecast_identity_firewall(
            feature_names=changed,
            expected_version=FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
            expected_fingerprint_sha256=fast_forecast_identity_firewall_fingerprint_sha256(
                changed
            ),
        )
