from __future__ import annotations

import hashlib
import json
import string

from shreks_brain.fast_learning.features import FAST_FORECAST_FEATURE_NAMES


FAST_FORECAST_IDENTITY_FIREWALL_VERSION = (
    "fl8.3-feature-identity-firewall-v1"
)

_FORBIDDEN_IDENTITY_CLASSES = (
    "mint",
    "quote_mint",
    "pair_or_pool_address",
    "decision_actor_address",
    "transaction_signature",
    "decision_ordinal",
    "decision_sequence_identity",
    "provider_identity",
    "derived_identity_encoding",
)

_ALLOWED_ACTOR_FEATURES = frozenset(
    name
    for name in FAST_FORECAST_FEATURE_NAMES
    if (
        name == "decision.actor_present"
        or name.endswith(".unique_buy_actors")
        or name.endswith(".unique_sell_actors")
    )
)

_EXPLICIT_FORBIDDEN_FEATURE_NAMES = frozenset(
    {
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
    }
)


def fast_forecast_identity_firewall_fingerprint_sha256(
    feature_names: tuple[str, ...],
) -> str:
    _feature_names(feature_names)
    payload = {
        "version": FAST_FORECAST_IDENTITY_FIREWALL_VERSION,
        "approved_feature_names": list(feature_names),
        "forbidden_identity_classes": list(_FORBIDDEN_IDENTITY_CLASSES),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_fast_forecast_identity_firewall(
    *,
    feature_names: tuple[str, ...],
    expected_version: str,
    expected_fingerprint_sha256: str,
) -> None:
    _feature_names(feature_names)
    if expected_version != FAST_FORECAST_IDENTITY_FIREWALL_VERSION:
        raise ValueError("unsupported feature identity firewall version")
    _sha256(
        "expected_fingerprint_sha256",
        expected_fingerprint_sha256,
    )

    if feature_names != FAST_FORECAST_FEATURE_NAMES:
        forbidden = tuple(
            name
            for name in feature_names
            if (
                name in _EXPLICIT_FORBIDDEN_FEATURE_NAMES
                or _looks_like_identity_feature(name)
            )
        )
        if forbidden:
            raise ValueError(
                "feature identity firewall rejects raw or derived identity "
                f"features: {forbidden!r}"
            )
        raise ValueError(
            "feature identity firewall rejects unreviewed feature schema change"
        )

    actual = fast_forecast_identity_firewall_fingerprint_sha256(
        FAST_FORECAST_FEATURE_NAMES
    )
    if expected_fingerprint_sha256 != actual:
        raise ValueError("feature identity firewall fingerprint mismatch")

    if not _ALLOWED_ACTOR_FEATURES.issubset(
        frozenset(FAST_FORECAST_FEATURE_NAMES)
    ):
        raise ValueError(
            "feature identity firewall actor aggregate contract changed"
        )


def _looks_like_identity_feature(name: str) -> bool:
    lowered = name.lower()
    obvious_tokens = (
        ".mint",
        "mint_",
        ".actor",
        "actor_",
        ".signature",
        "signature_",
        ".ordinal",
        "ordinal_",
        ".sequence",
        "sequence_",
        ".provider",
        "provider_",
        "pool_address",
        "pair_address",
        "identity.",
        "_sha256",
        ".hash",
        "_hash",
        ".embedding",
        "_embedding",
    )
    if name in _ALLOWED_ACTOR_FEATURES:
        return False
    return any(token in lowered for token in obvious_tokens)


def _feature_names(value: object) -> None:
    if not isinstance(value, tuple) or not value:
        raise ValueError("feature names must be a non-empty tuple")
    if not all(
        isinstance(name, str) and name.strip()
        for name in value
    ):
        raise ValueError("feature names must contain non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError("feature names must be unique")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(
            f"{name} must be a 64-character lowercase SHA-256 digest"
        )
