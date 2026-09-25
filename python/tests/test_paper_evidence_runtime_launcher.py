from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
    ObserverPaperQuoteUsdValuationMode,
    ObserverPaperQuoteUsdValuationPolicy,
    build_observer_paper_campaign_runtime_manifest_v2,
    encode_observer_paper_campaign_runtime_manifest,
)
from shreks_brain.paper_evidence_runtime_launcher import (
    PaperEvidenceRuntimeLauncherError,
    derive_paper_evidence_environment,
    launch_paper_evidence,
)

from test_observer_campaign_runtime_manifest import _manifest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIT = _REPO_ROOT / "deploy" / "systemd" / "shreks-paper-evidence.service"

WSOL = "So11111111111111111111111111111111111111112"
LEGACY_USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ENTRY_AMOUNT = 211_545_104
EXIT_AMOUNT = 7_654_321


def _v2_manifest_bytes() -> bytes:
    source = _manifest()
    bundle = source.policy_bundle
    entry = bundle.entry_quote_identity
    regime = bundle.regime_read_policy
    safety_probe = bundle.safety_probe_identity

    v2_bundle = replace(
        bundle,
        quote_asset=replace(
            bundle.quote_asset,
            mint=WSOL,
            decimals=9,
            usd_per_token=1.0,
        ),
        entry_quote_identity=replace(
            entry,
            input_mint=WSOL,
            input_amount=ENTRY_AMOUNT,
        ),
        regime_read_policy=replace(
            regime,
            quote_asset_mint=WSOL,
            entry_input_amount=ENTRY_AMOUNT,
        ),
        safety_probe_identity=replace(
            safety_probe,
            output_mint=WSOL,
            input_amount=EXIT_AMOUNT,
        ),
    )
    manifest = build_observer_paper_campaign_runtime_manifest_v2(
        paper_run_id="g1c-v2-wsol-launcher-test",
        candidate=source.candidate,
        initial_state=source.initial_state,
        policy_bundle=v2_bundle,
        risk_environment=source.risk_environment,
        selection_policy=source.selection_policy,
        recent_performance=source.recent_performance,
        global_risk_halt=source.global_risk_halt,
        quote_usd_valuation_policy=ObserverPaperQuoteUsdValuationPolicy(
            version=OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
            mode=ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO,
        ),
    )
    assert manifest.schema_version == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    return encode_observer_paper_campaign_runtime_manifest(manifest)


def _legacy_environment() -> dict[str, str]:
    return {
        "SHREKS_PAPER_QUOTE_ASSET_MINT": LEGACY_USDC,
        "SHREKS_PAPER_ENTRY_INPUT_AMOUNT": "25000000",
        "SHREKS_PAPER_EXIT_INPUT_AMOUNT": "1000000",
        "SHREKS_PAPER_PROBE_POLICY_VERSION": "probe-v2",
        "SHREKS_PAPER_QUOTE_TAKER": "TakerRunner111",
        "SHREKS_PAPER_SLIPPAGE_BPS": "75",
        "HELIUS_API_KEY": "test-helius-placeholder",
        "JUPITER_API_KEY": "test-jupiter-placeholder",
        "UNRELATED_RUNTIME_SETTING": "preserve-me",
    }


def test_v2_manifest_overrides_only_collector_quote_policy_environment(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "paper-campaign.json"
    manifest_path.write_bytes(_v2_manifest_bytes())
    original = _legacy_environment()

    derived = derive_paper_evidence_environment(
        manifest_path,
        environment=original,
    )

    assert original["SHREKS_PAPER_QUOTE_ASSET_MINT"] == LEGACY_USDC
    assert original["SHREKS_PAPER_ENTRY_INPUT_AMOUNT"] == "25000000"

    assert derived["SHREKS_PAPER_QUOTE_ASSET_MINT"] == WSOL
    assert derived["SHREKS_PAPER_ENTRY_INPUT_AMOUNT"] == str(ENTRY_AMOUNT)
    assert derived["SHREKS_PAPER_EXIT_INPUT_AMOUNT"] == str(EXIT_AMOUNT)
    assert derived["SHREKS_PAPER_PROBE_POLICY_VERSION"] == "probe-v2"
    assert derived["SHREKS_PAPER_QUOTE_TAKER"] == "TakerRunner111"
    assert derived["SHREKS_PAPER_SLIPPAGE_BPS"] == "75"
    assert derived["SHREKS_PAPER_MINT_STATE_MAX_AGE_MS"] == str(
        _manifest().policy_bundle.safety_policy.max_critical_data_age_ms
    )

    assert derived["HELIUS_API_KEY"] == "test-helius-placeholder"
    assert derived["JUPITER_API_KEY"] == "test-jupiter-placeholder"
    assert derived["UNRELATED_RUNTIME_SETTING"] == "preserve-me"


def test_v1_manifest_preserves_legacy_environment_and_derives_safety_freshness(tmp_path: Path) -> None:
    manifest_path = tmp_path / "paper-campaign.json"
    manifest_path.write_bytes(
        encode_observer_paper_campaign_runtime_manifest(_manifest())
    )
    original = _legacy_environment()

    derived = derive_paper_evidence_environment(
        manifest_path,
        environment=original,
    )

    for name, value in original.items():
        assert derived[name] == value
    assert derived["SHREKS_PAPER_MINT_STATE_MAX_AGE_MS"] == str(
        _manifest().policy_bundle.safety_policy.max_critical_data_age_ms
    )
    assert derived is not original


def test_launcher_binds_resolved_binary_to_immutable_release_sha(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "paper-campaign.json"
    manifest_path.write_bytes(_v2_manifest_bytes())
    source_sha = "1" * 40
    binary = (
        tmp_path
        / "opt"
        / "shreks"
        / "releases"
        / source_sha
        / "target"
        / "release"
        / "shreks-paper-evidence"
    )
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")
    binary.chmod(0o755)
    captured: dict[str, object] = {}

    def fake_execve(path: str, argv: tuple[str, ...], environment: dict[str, str]):
        captured["path"] = path
        captured["argv"] = argv
        captured["environment"] = environment
        return object()

    with pytest.raises(PaperEvidenceRuntimeLauncherError, match="returned unexpectedly"):
        launch_paper_evidence(
            manifest_path=manifest_path,
            binary_path=binary,
            environment=_legacy_environment(),
            execve=fake_execve,
        )

    assert captured["path"] == str(binary.resolve())
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment["SHREKS_PAPER_EVIDENCE_RELEASE_SOURCE_SHA"] == source_sha


def test_launcher_rejects_non_release_binary_before_exec(tmp_path: Path) -> None:
    manifest_path = tmp_path / "paper-campaign.json"
    manifest_path.write_bytes(_v2_manifest_bytes())
    binary = tmp_path / "shreks-paper-evidence"
    binary.write_bytes(b"binary")
    binary.chmod(0o755)

    with pytest.raises(PaperEvidenceRuntimeLauncherError, match="immutable release SHA"):
        launch_paper_evidence(
            manifest_path=manifest_path,
            binary_path=binary,
            environment=_legacy_environment(),
            execve=lambda *_args: pytest.fail("unbound binary must not execute"),
        )


def test_tampered_v2_manifest_fails_closed_before_exec(tmp_path: Path) -> None:
    manifest_path = tmp_path / "paper-campaign.json"
    document = json.loads(_v2_manifest_bytes())
    document["paper_run_id"] = "tampered-run"
    manifest_path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    binary = tmp_path / "shreks-paper-evidence"
    binary.write_bytes(b"binary")
    binary.chmod(0o755)

    executed = False

    def fake_execve(_path: str, _argv: tuple[str, ...], _environment: dict[str, str]):
        nonlocal executed
        executed = True
        raise AssertionError("execve must not be reached")

    with pytest.raises(PaperEvidenceRuntimeLauncherError, match="manifest"):
        launch_paper_evidence(
            manifest_path=manifest_path,
            binary_path=binary,
            environment=_legacy_environment(),
            execve=fake_execve,
        )

    assert executed is False


def test_paper_evidence_systemd_uses_manifest_authority_launcher() -> None:
    payload = _UNIT.read_text(encoding="utf-8")

    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in payload
    assert (
        "ExecStart=/opt/shreks/current/.venv/bin/python "
        "-m shreks_brain.paper_evidence_runtime_launcher"
    ) in payload
    assert (
        "ExecStart=/opt/shreks/current/target/release/shreks-paper-evidence"
        not in payload
    )
