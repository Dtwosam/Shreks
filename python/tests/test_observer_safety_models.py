from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shreks_brain.observer_safety.models import (
    ObserverExitQuoteSafetyEvidence,
    ObserverHolderSafetyEvidence,
    ObserverMintSafetyEvidence,
    ObserverSafetyProbeIdentity,
)


def test_probe_identity_is_immutable_and_preserves_exact_quote_probe_contract():
    identity = ObserverSafetyProbeIdentity(
        probe_policy_version="probe-v1",
        output_mint="So11111111111111111111111111111111111111112",
        input_amount=2**64 - 1,
        taker="Taker111",
        slippage_bps=75,
    )

    assert identity.input_amount == 2**64 - 1
    with pytest.raises(FrozenInstanceError):
        identity.taker = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("probe_policy_version", ""),
        ("output_mint", "   "),
        ("input_amount", 0),
        ("input_amount", True),
        ("input_amount", 2**64),
        ("taker", ""),
        ("slippage_bps", -1),
        ("slippage_bps", 10_001),
        ("slippage_bps", True),
    ],
)
def test_probe_identity_rejects_invalid_fields(field, value):
    values = dict(
        probe_policy_version="probe-v1",
        output_mint="So11111111111111111111111111111111111111112",
        input_amount=1_000,
        taker="Taker111",
        slippage_bps=75,
    )
    values[field] = value
    with pytest.raises(ValueError, match=field):
        ObserverSafetyProbeIdentity(**values)


def test_evidence_models_are_frozen_and_validate_core_provenance():
    mint = ObserverMintSafetyEvidence(
        candidate_id=7,
        provider="helius",
        mint="Mint111",
        mint_authority="Authority111",
        freeze_authority=None,
        slot=2**64 - 1,
        observed_at_unix_ms=1_000,
    )
    holder = ObserverHolderSafetyEvidence(
        candidate_id=7,
        provider="helius",
        mint="Mint111",
        last_indexed_slot=2**64 - 1,
        observed_at_unix_ms=1_100,
        complete=True,
        top_holder_concentration_pct=60.0,
    )
    quote = ObserverExitQuoteSafetyEvidence(
        candidate_id=7,
        provider="jupiter",
        probe_policy_version="probe-v1",
        input_mint="Mint111",
        output_mint="So11111111111111111111111111111111111111112",
        taker="Taker111",
        input_amount=1_000,
        output_amount=900,
        minimum_output_amount=850,
        slippage_bps=75,
        route_available=True,
        price_impact_pct="0.25",
        quoted_at_unix_ms=1_200,
    )

    assert mint.slot == 2**64 - 1
    assert holder.last_indexed_slot == 2**64 - 1
    assert quote.price_impact_pct == "0.25"
    with pytest.raises(FrozenInstanceError):
        holder.complete = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ObserverMintSafetyEvidence(
            candidate_id=0,
            provider="helius",
            mint="Mint111",
            mint_authority=None,
            freeze_authority=None,
            slot=1,
            observed_at_unix_ms=1,
        ),
        lambda: ObserverMintSafetyEvidence(
            candidate_id=1,
            provider="",
            mint="Mint111",
            mint_authority=None,
            freeze_authority=None,
            slot=1,
            observed_at_unix_ms=1,
        ),
        lambda: ObserverHolderSafetyEvidence(
            candidate_id=1,
            provider="helius",
            mint="Mint111",
            last_indexed_slot=1,
            observed_at_unix_ms=1,
            complete=False,
            top_holder_concentration_pct=10.0,
        ),
        lambda: ObserverHolderSafetyEvidence(
            candidate_id=1,
            provider="helius",
            mint="Mint111",
            last_indexed_slot=1,
            observed_at_unix_ms=1,
            complete=True,
            top_holder_concentration_pct=101.0,
        ),
        lambda: ObserverExitQuoteSafetyEvidence(
            candidate_id=1,
            provider="jupiter",
            probe_policy_version="probe-v1",
            input_mint="Mint111",
            output_mint="Out111",
            taker="Taker111",
            input_amount=1_000,
            output_amount=900,
            minimum_output_amount=901,
            slippage_bps=75,
            route_available=True,
            price_impact_pct="0.25",
            quoted_at_unix_ms=1,
        ),
    ],
)
def test_evidence_models_fail_closed_on_invalid_invariants(factory):
    with pytest.raises(ValueError):
        factory()
