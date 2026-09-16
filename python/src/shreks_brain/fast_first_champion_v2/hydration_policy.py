from __future__ import annotations

from shreks_brain.fast_context_hydration import (
    FastForecastContextHydrationPolicy,
)


def require_fast_first_champion_v2_hydration_policy_matches_identities(
    *,
    hydration_policy: FastForecastContextHydrationPolicy,
    accepted_decision_identities: tuple[tuple[object, ...], ...],
) -> str:
    """Require one cohort quote mint and exact hydration-policy compatibility.

    V2 cohort membership is already sealed.  This guard does not rewrite quote
    identity, decimals, or raw probe amounts.  A compatible hydration policy
    must come from an authority that already uses the cohort's quote asset.
    """
    if type(hydration_policy) is not FastForecastContextHydrationPolicy:
        raise ValueError(
            "hydration_policy must be exact FastForecastContextHydrationPolicy"
        )
    if (
        not isinstance(accepted_decision_identities, tuple)
        or not accepted_decision_identities
    ):
        raise ValueError(
            "accepted_decision_identities must be a non-empty tuple"
        )

    quote_mints: set[str] = set()
    for index, identity in enumerate(accepted_decision_identities):
        if not isinstance(identity, tuple) or len(identity) != 7:
            raise ValueError(
                f"accepted decision identity at index {index} must have seven fields"
            )
        quote_mint = identity[4]
        if not isinstance(quote_mint, str) or not quote_mint.strip():
            raise ValueError(
                f"accepted decision quote mint at index {index} must be non-empty text"
            )
        quote_mints.add(quote_mint)

    if len(quote_mints) != 1:
        raise ValueError(
            "V2 accepted cohort must use one single quote mint for context hydration"
        )
    cohort_quote_mint = next(iter(quote_mints))

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
