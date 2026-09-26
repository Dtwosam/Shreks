from __future__ import annotations

from pathlib import Path
import sqlite3
import stat

import pytest

from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import PaperFillPolicy
from shreks_brain.paper_validation import validate_fast_paper_restart_equivalence
from shreks_brain.fast_paper_runtime.shadow_ledger import (
    FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_NAME,
    FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_VERSION,
    build_fast_paper_shadow_ledger_binding,
    build_initial_fast_paper_shadow_ledger_state,
    initialize_fast_paper_shadow_ledger_database,
    load_latest_fast_paper_shadow_ledger_checkpoint,
    save_fast_paper_shadow_ledger_checkpoint,
)

from test_fast_paper_shadow_restart_orchestration import _manifest


def _fill_policy(version: str) -> PaperFillPolicy:
    return PaperFillPolicy(
        version=version,
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=50,
        network_fee_usd=0.05,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _position_policy(version: str) -> FastPaperPositionActionPolicy:
    return FastPaperPositionActionPolicy(
        version=version,
        max_slippage_bps=600,
    )


def test_shadow_ledger_binding_is_manifest_bound_and_deterministic(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    database = tmp_path / "shadow-ledger" / "runtime.sqlite3"

    first = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-run-1",
        database_path=database,
    )
    second = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-run-1",
        database_path=database,
    )

    assert first == second
    assert first.schema_name == FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_NAME
    assert first.schema_version == FAST_PAPER_SHADOW_LEDGER_BINDING_SCHEMA_VERSION
    assert first.release_source_sha == manifest.release_source_sha
    assert first.manifest_fingerprint_sha256 == manifest.manifest_fingerprint_sha256
    assert first.champion_fingerprint_sha256 == manifest.champion_fingerprint_sha256
    assert first.action_policy_version == manifest.action_policy.version
    assert first.risk_policy_version == manifest.risk_policy_version
    assert first.fill_policy_version == manifest.fill_policy_version
    assert (
        first.position_action_policy_version
        == manifest.position_action_policy_version
    )
    assert first.database_path == str(database.resolve())
    assert len(first.binding_fingerprint_sha256) == 64


@pytest.mark.parametrize(
    "attribute",
    ("observer_database_path", "paper_evidence_path", "checkpoint_path"),
)
def test_shadow_ledger_rejects_authoritative_or_decision_state_paths(
    tmp_path: Path,
    attribute: str,
) -> None:
    manifest = _manifest(tmp_path)

    with pytest.raises(ValueError, match="separate|shadow"):
        build_fast_paper_shadow_ledger_binding(
            manifest,
            run_id="shadow-run-1",
            database_path=Path(getattr(manifest, attribute)),
        )


def test_shadow_ledger_initial_state_reuses_existing_fast_paper_accounting(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-run-1",
        database_path=tmp_path / "shadow-ledger" / "runtime.sqlite3",
    )

    state = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=50_000,
        fill_policy=_fill_policy(manifest.fill_policy_version),
        position_action_policy=_position_policy(
            manifest.position_action_policy_version
        ),
    )

    assert state.ledger.starting_cash_usd == 20_000.0
    assert state.ledger.cash_balance_usd == 20_000.0
    assert state.ledger.positions == ()
    assert state.ledger.entries == ()
    assert state.ledger.processed_intent_keys == frozenset()
    assert state.event_loop_state.records == ()
    assert state.event_loop_state.market_cursors == ()
    assert state.pending_buy is None
    assert state.position_action_states == ()


def test_shadow_ledger_checkpoint_round_trip_is_private_and_restart_equivalent(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    database = tmp_path / "shadow-ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)

    state = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=50_000,
        fill_policy=_fill_policy(manifest.fill_policy_version),
        position_action_policy=_position_policy(
            manifest.position_action_policy_version
        ),
    )
    saved = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        state,
        sequence=0,
        created_at_unix_ms=50_000,
    )
    restored = load_latest_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
    )

    assert restored is not None
    assert restored == saved
    report = validate_fast_paper_restart_equivalence(
        state,
        restored.state,
    )
    assert report.equivalent
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700


def test_shadow_ledger_binding_tamper_fails_closed_before_checkpoint_load(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    database = tmp_path / "shadow-ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE fast_paper_shadow_ledger_bindings
            SET binding_fingerprint_sha256 = ?
            WHERE run_id = ?
            """,
            ("0" * 64, binding.run_id),
        )
        connection.commit()

    with pytest.raises(ValueError, match="binding|fingerprint"):
        load_latest_fast_paper_shadow_ledger_checkpoint(
            manifest,
            binding,
        )


def test_shadow_ledger_module_has_state_authority_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_ledger.py"
    ).read_text(encoding="utf-8")

    for required in (
        "FastPaperRuntimeState",
        "create_paper_ledger",
        "create_fast_paper_loop_state",
        "save_fast_paper_checkpoint",
        "load_latest_fast_paper_checkpoint",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in source
