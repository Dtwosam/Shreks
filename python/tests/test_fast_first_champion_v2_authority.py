from __future__ import annotations

from pathlib import Path

import shreks_brain.fast_first_champion_v2 as v2


_EXPECTED_PUBLIC_API = {
    "FAST_FIRST_CHAMPION_V2_SCHEMA_NAME",
    "FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION",
    "FAST_FIRST_CHAMPION_V2_POLICY_VERSION",
    "FastFirstChampionV2Policy",
    "FastFirstChampionV2MemberEvidence",
    "FastFirstChampionV2BuildResult",
    "FastFirstChampionV2EvidenceManifest",
    "FastFirstChampionV2EvidenceArtifact",
}


def test_v2_public_api_is_exact_and_intentionally_small() -> None:
    assert set(v2.__all__) == _EXPECTED_PUBLIC_API


def test_v2_core_source_has_no_trading_authority() -> None:
    package = (
        Path(v2.__file__).resolve().parent
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    ).lower()

    forbidden = (
        "paper_executor",
        "risk_intent",
        "sign_transaction",
        "submit_transaction",
        "live_trading",
        "enable_live",
        "model_registry",
        "promotion_state",
    )
    for token in forbidden:
        assert token not in source
