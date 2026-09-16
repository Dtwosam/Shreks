from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

import shreks_brain.fast_first_champion_v2.bounded_host_run as bounded_host_module
import shreks_brain.fast_first_champion_v2.host_request as request_module
from fast_forecast_fixtures import WSOL
from shreks_brain.fast_first_champion_v2.hydration_policy import (
    require_fast_first_champion_v2_hydration_policy_matches_identities,
)
from test_fast_context_hydration import _policy


USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _identity(*, quote_mint: str, sequence: int = 1) -> tuple[object, ...]:
    return (
        f"signature-{sequence}",
        0,
        sequence,
        f"mint-{sequence}",
        quote_mint,
        "pump_swap",
        1_788_878_663_297 + sequence,
    )


def test_v2_hydration_quote_binding_accepts_exact_single_quote_population() -> None:
    result = require_fast_first_champion_v2_hydration_policy_matches_identities(
        hydration_policy=_policy(),
        accepted_decision_identities=(
            _identity(quote_mint=WSOL, sequence=1),
            _identity(quote_mint=WSOL, sequence=2),
        ),
    )
    assert result == WSOL


def test_v2_hydration_quote_binding_rejects_policy_quote_mismatch() -> None:
    source = _policy()
    mismatched = replace(
        source,
        regime_read_policy=replace(
            source.regime_read_policy,
            quote_asset_mint=USDC,
        ),
        safety_probe_identity=replace(
            source.safety_probe_identity,
            output_mint=USDC,
        ),
        quote_asset_decimals=6,
    )

    with pytest.raises(ValueError, match="hydration.*quote.*cohort|cohort.*quote.*hydration"):
        require_fast_first_champion_v2_hydration_policy_matches_identities(
            hydration_policy=mismatched,
            accepted_decision_identities=(
                _identity(quote_mint=WSOL, sequence=1),
            ),
        )


def test_v2_hydration_quote_binding_rejects_multi_quote_cohort() -> None:
    with pytest.raises(ValueError, match="single.*quote|one.*quote|multiple.*quote"):
        require_fast_first_champion_v2_hydration_policy_matches_identities(
            hydration_policy=_policy(),
            accepted_decision_identities=(
                _identity(quote_mint=WSOL, sequence=1),
                _identity(quote_mint=USDC, sequence=2),
            ),
        )


def test_v2_request_writer_checks_hydration_quote_binding_before_publish() -> None:
    source = inspect.getsource(
        request_module.write_fast_first_champion_v2_host_request_from_sources
    )
    assert (
        "require_fast_first_champion_v2_hydration_policy_matches_identities"
        in source
    )
    assert source.index(
        "require_fast_first_champion_v2_hydration_policy_matches_identities"
    ) < source.index("write_fast_first_champion_v2_host_request(")


def test_v2_bounded_host_checks_hydration_quote_binding_before_bundle_build() -> None:
    source = inspect.getsource(
        bounded_host_module.run_fast_first_champion_v2_host_request
    )
    assert (
        "require_fast_first_champion_v2_hydration_policy_matches_identities"
        in source
    )
    assert source.index(
        "require_fast_first_champion_v2_hydration_policy_matches_identities"
    ) < source.index("build_fast_first_champion_v2_bundle(")
