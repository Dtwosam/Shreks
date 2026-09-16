from __future__ import annotations

from collections.abc import Iterable

from shreks_brain.fast_context_hydration import (
    FastForecastContextHydrationPolicy,
)


def require_fast_first_champion_v2_hydration_policy_matches_identities(
    *,
    hydration_policy: FastForecastContextHydrationPolicy,
    accepted_decision_identities: Iterable[tuple[object, ...]],
) -> str:
    """Require one cohort quote mint and exact hydration-policy compatibility.

    V2 cohort membership is already sealed. This guard does not rewrite quote
    identity, decimals, or raw probe amounts. A compatible hydration policy
    must come from an authority that already uses the cohort's quote asset.
    """
    if type(hydration_policy) is not FastForecastContextHydrationPolicy:
        raise ValueError(
            "hydration_policy must be exact FastForecastContextHydrationPolicy"
        )

    cohort_quote_mint: str | None = None
    identity_count = 0
    for index, identity in enumerate(accepted_decision_identities):
        identity_count += 1
        if not isinstance(identity, tuple) or len(identity) != 7:
            raise ValueError(
                f"accepted decision identity at index {index} must have seven fields"
            )
        quote_mint = identity[4]
        if not isinstance(quote_mint, str) or not quote_mint.strip():
            raise ValueError(
                f"accepted decision quote mint at index {index} must be non-empty text"
            )
        if cohort_quote_mint is None:
            cohort_quote_mint = quote_mint
        elif quote_mint != cohort_quote_mint:
            raise ValueError(
                "V2 accepted cohort must use one single quote mint for context hydration"
            )

    if identity_count == 0 or cohort_quote_mint is None:
        raise ValueError(
            "accepted_decision_identities must contain at least one identity"
        )

    regime_quote_mint = hydration_policy.regime_read_policy.quote_asset_mint
    probe_quote_mint = hydration_policy.safety_probe_identity.output_mint
    if (
        regime_quote_mint != cohort_quote_mint
        or probe_quote_mint != cohort_quote_mint
    ):
        raise ValueError(
            "V2 hydration quote policy does not match frozen cohort quote mint: "
            f"cohort={cohort_quote_mint}, "
            f"regime={regime_quote_mint}, probe={probe_quote_mint}"
        )

    return cohort_quote_mint
