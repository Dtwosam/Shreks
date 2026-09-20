from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifestError,
    ObserverPaperQuoteUsdValuationMode,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)

from test_observer_campaign_runtime_manifest import _manifest, _manifest_v2


WSOL = "So11111111111111111111111111111111111111112"
NEW_RUN_ID = "paper-v2-wsol-candidate-20260920"
START_AT_UNIX_MS = 2_000_000
ENTRY_INPUT_AMOUNT = 125_000_000


def _module():
    return import_module(
        "shreks_brain.g1c_v2_runtime_manifest_candidate_authoring"
    )


def _write_source(tmp_path: Path, manifest=None) -> tuple[Path, bytes]:
    source = _manifest() if manifest is None else manifest
    payload = encode_observer_paper_campaign_runtime_manifest(source)
    path = tmp_path / "source-runtime-manifest.json"
    path.write_bytes(payload)
    return path, payload


def _author(tmp_path: Path, **overrides):
    module = _module()
    source_path, source_bytes = _write_source(tmp_path)
    values = dict(
        source_runtime_manifest_path=source_path,
        paper_run_id=NEW_RUN_ID,
        start_at_unix_ms=START_AT_UNIX_MS,
        quote_asset_mint=WSOL,
        quote_asset_decimals=9,
        entry_input_amount=ENTRY_INPUT_AMOUNT,
    )
    values.update(overrides)
    candidate = module.author_g1c_v2_runtime_manifest_candidate(**values)
    return candidate, source_path, source_bytes


def test_authoring_builds_coherent_new_run_v2_candidate_without_mutating_source(
    tmp_path: Path,
) -> None:
    candidate, source_path, source_bytes = _author(tmp_path)
    source = decode_observer_paper_campaign_runtime_manifest(source_bytes)

    encoded = encode_observer_paper_campaign_runtime_manifest(candidate)
    decoded = decode_observer_paper_campaign_runtime_manifest(encoded)

    assert source_path.read_bytes() == source_bytes
    assert decoded == candidate
    assert candidate.schema_version == (
        OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    )
    assert candidate.paper_run_id == NEW_RUN_ID
    assert candidate.paper_run_id != source.paper_run_id
    assert candidate.quote_usd_valuation_policy is not None
    assert (
        candidate.quote_usd_valuation_policy.mode
        is ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO
    )

    assert candidate.candidate == source.candidate
    assert candidate.risk_environment == source.risk_environment
    assert candidate.selection_policy == source.selection_policy
    assert candidate.recent_performance == source.recent_performance
    assert candidate.global_risk_halt == source.global_risk_halt

    target = candidate.policy_bundle
    original = source.policy_bundle

    assert target.quote_asset.mint == WSOL
    assert target.quote_asset.decimals == 9
    assert target.quote_asset.usd_per_token == 1.0
    assert target.entry_quote_identity.input_mint == WSOL
    assert target.entry_quote_identity.input_amount == ENTRY_INPUT_AMOUNT
    assert target.regime_read_policy.quote_asset_mint == WSOL
    assert target.regime_read_policy.entry_input_amount == ENTRY_INPUT_AMOUNT
    assert target.safety_probe_identity.output_mint == WSOL

    assert replace(
        target.entry_quote_identity,
        input_mint=original.entry_quote_identity.input_mint,
        input_amount=original.entry_quote_identity.input_amount,
    ) == original.entry_quote_identity
    assert replace(
        target.regime_read_policy,
        quote_asset_mint=original.regime_read_policy.quote_asset_mint,
        entry_input_amount=original.regime_read_policy.entry_input_amount,
    ) == original.regime_read_policy
    assert replace(
        target.safety_probe_identity,
        output_mint=original.safety_probe_identity.output_mint,
    ) == original.safety_probe_identity

    for name in (
        "market_read_policy",
        "safety_policy",
        "regime_policy",
        "fresh_launch_policy",
        "score_policy",
        "decision_policy",
        "risk_policy",
        "exit_policy",
        "setup_name",
    ):
        assert getattr(target, name) == getattr(original, name)

    state = candidate.initial_state
    source_state = source.initial_state
    assert state.loop_policy == source_state.loop_policy
    assert state.paper_fill_policy == source_state.paper_fill_policy
    assert state.last_cycle_at_unix_ms == START_AT_UNIX_MS
    assert state.managed_positions == ()
    assert state.pending_entry is None
    assert state.ledger.as_of_unix_ms == START_AT_UNIX_MS
    assert (
        state.ledger.starting_cash_usd
        == source_state.ledger.starting_cash_usd
    )
    assert state.ledger.cash_balance_usd == state.ledger.starting_cash_usd
    assert state.ledger.realized_pnl_usd == 0.0
    assert state.ledger.unrealized_pnl_usd == 0.0
    assert state.ledger.accumulated_costs_usd == 0.0
    assert state.ledger.positions == ()
    assert state.ledger.entries == ()
    assert state.ledger.processed_intent_keys == frozenset()


@pytest.mark.parametrize(
    ("overrides", "pattern"),
    (
        ({"paper_run_id": _manifest().paper_run_id}, "paper_run_id|new run|different"),
        (
            {"quote_asset_mint": _manifest().policy_bundle.quote_asset.mint},
            "quote asset|different|transition",
        ),
        ({"start_at_unix_ms": _manifest().initial_state.last_cycle_at_unix_ms}, "start"),
        ({"quote_asset_decimals": -1}, "decimal"),
        ({"entry_input_amount": 0}, "input|amount|positive"),
    ),
)
def test_authoring_rejects_ambiguous_or_inferred_transition_inputs(
    tmp_path: Path,
    overrides: dict[str, object],
    pattern: str,
) -> None:
    with pytest.raises(
        (ObserverPaperCampaignRuntimeManifestError, TypeError, ValueError),
        match=pattern,
    ):
        _author(tmp_path, **overrides)


def test_authoring_accepts_only_authenticated_canonical_v1_source(
    tmp_path: Path,
) -> None:
    module = _module()

    v2_path, _ = _write_source(tmp_path, _manifest_v2())
    with pytest.raises(
        (ObserverPaperCampaignRuntimeManifestError, TypeError, ValueError),
        match="v1|source",
    ):
        module.author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=v2_path,
            paper_run_id=NEW_RUN_ID,
            start_at_unix_ms=START_AT_UNIX_MS,
            quote_asset_mint=WSOL,
            quote_asset_decimals=9,
            entry_input_amount=ENTRY_INPUT_AMOUNT,
        )

    source_path, source_bytes = _write_source(tmp_path)
    source_path.write_bytes(source_bytes + b"\n")
    with pytest.raises(
        (ObserverPaperCampaignRuntimeManifestError, TypeError, ValueError),
        match="canonical|manifest",
    ):
        module.author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=source_path,
            paper_run_id=NEW_RUN_ID,
            start_at_unix_ms=START_AT_UNIX_MS,
            quote_asset_mint=WSOL,
            quote_asset_decimals=9,
            entry_input_amount=ENTRY_INPUT_AMOUNT,
        )


def test_cli_emits_only_canonical_candidate_manifest_to_stdout(
    tmp_path: Path,
    capsys,
) -> None:
    module = _module()
    source_path, source_bytes = _write_source(tmp_path)

    result = module.main(
        [
            "--source-runtime-manifest",
            str(source_path),
            "--paper-run-id",
            NEW_RUN_ID,
            "--start-at-unix-ms",
            str(START_AT_UNIX_MS),
            "--quote-asset-mint",
            WSOL,
            "--quote-asset-decimals",
            "9",
            "--entry-input-amount",
            str(ENTRY_INPUT_AMOUNT),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    decoded = decode_observer_paper_campaign_runtime_manifest(captured.out)
    assert decoded.paper_run_id == NEW_RUN_ID
    assert decoded.policy_bundle.quote_asset.mint == WSOL
    assert captured.out.encode("utf-8") == (
        encode_observer_paper_campaign_runtime_manifest(decoded)
    )
    assert source_path.read_bytes() == source_bytes


def test_cli_is_registered_and_source_has_no_install_scoring_or_live_authority() -> None:
    module = _module()
    source = Path(module.__file__).read_text(encoding="utf-8")
    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert (
        'shreks-g1c-v2-runtime-manifest-candidate-author = '
        '"shreks_brain.g1c_v2_runtime_manifest_candidate_authoring:main"'
    ) in pyproject

    for forbidden in (
        "/etc/shreks",
        "/opt/shreks",
        "/var/lib/shreks",
        "systemctl",
        "subprocess",
        "sqlite3",
        "shutil",
        "write_bytes",
        "write_text",
        "--output",
        "v2_host_request_authority",
        "cohort_path",
        "score_candidate",
        "model_fit",
        "promot",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
