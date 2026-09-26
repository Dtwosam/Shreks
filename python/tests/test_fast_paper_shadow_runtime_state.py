from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import PaperFillPolicy, PaperPositionState
from shreks_brain.paper_validation import (
    FAST_PAPER_RUNTIME_STATE_VERSION,
    FastPaperRuntimeState,
)
from shreks_brain.fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    build_initial_fast_paper_shadow_ledger_state,
    initialize_fast_paper_shadow_ledger_database,
    save_fast_paper_shadow_ledger_checkpoint,
)
from shreks_brain.fast_paper_runtime.shadow_runtime_state import (
    FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION,
    FastPaperShadowMarketPosition,
    build_fast_paper_shadow_runtime_state,
    fast_paper_shadow_decision_position,
    load_latest_fast_paper_shadow_runtime_state,
    save_fast_paper_shadow_runtime_state,
)

from test_fast_paper_accounting_reconciliation import (
    MARKET_KEY,
    _open_fast_position,
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


def _initial_state(manifest, binding, *, at: int = 50_000):
    return build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=at,
        fill_policy=_fill_policy(manifest.fill_policy_version),
        position_action_policy=_position_policy(
            manifest.position_action_policy_version
        ),
    )


def _open_state(manifest) -> FastPaperRuntimeState:
    loop_state, ledger, action_state, _ = _open_fast_position()
    return FastPaperRuntimeState(
        version=FAST_PAPER_RUNTIME_STATE_VERSION,
        as_of_unix_ms=ledger.as_of_unix_ms,
        event_loop_state=loop_state,
        ledger=ledger,
        fill_policy=_fill_policy(manifest.fill_policy_version),
        position_action_policy=_position_policy(
            manifest.position_action_policy_version
        ),
        pending_buy=None,
        position_action_states=(action_state,),
    )


def _database_fixture(tmp_path: Path, *, open_position: bool = False):
    manifest = _manifest(tmp_path)
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-runtime-run-1",
        database_path=tmp_path / "shadow-ledger" / "runtime.sqlite3",
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    state = _open_state(manifest) if open_position else _initial_state(
        manifest,
        binding,
    )
    checkpoint = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        state,
        sequence=0,
        created_at_unix_ms=state.as_of_unix_ms,
    )
    return manifest, binding, checkpoint


def test_shadow_runtime_state_binds_exact_latest_paper_checkpoint(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint = _database_fixture(tmp_path)

    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        last_processed_source_sequence=7,
        last_processed_source_event_id="sig-7:0",
        last_processed_decision_evidence_fingerprint_sha256="a" * 64,
    )

    assert state.schema_name == FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_NAME
    assert state.schema_version == FAST_PAPER_SHADOW_RUNTIME_STATE_SCHEMA_VERSION
    assert (
        state.binding_fingerprint_sha256
        == binding.binding_fingerprint_sha256
    )
    assert state.paper_checkpoint_sequence == checkpoint.sequence
    assert (
        state.paper_checkpoint_payload_sha256
        == checkpoint.payload_sha256
    )
    assert state.market_positions == ()
    assert state.last_processed_source_sequence == 7
    assert state.last_processed_source_event_id == "sig-7:0"
    assert (
        state.last_processed_decision_evidence_fingerprint_sha256
        == "a" * 64
    )
    assert len(state.state_fingerprint_sha256) == 64

    flat = fast_paper_shadow_decision_position(state, "pump:unknown:quote")
    assert flat.kind == "FLAT"
    assert flat.current_exposure_fraction is None


def test_shadow_runtime_state_requires_exact_open_ledger_mapping(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint = _database_fixture(
        tmp_path,
        open_position=True,
    )
    open_positions = tuple(
        position
        for position in checkpoint.state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )
    assert len(open_positions) == 1
    position = open_positions[0]
    mapping = FastPaperShadowMarketPosition(
        market_key=MARKET_KEY,
        position_id=position.position_id,
        mint=position.mint,
        current_exposure_fraction=0.5,
    )

    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(mapping,),
    )
    posture = fast_paper_shadow_decision_position(state, MARKET_KEY)
    assert posture.kind == "OPEN"
    assert posture.current_exposure_fraction == 0.5

    with pytest.raises(ValueError, match="OPEN|mapping|position"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(),
        )

    wrong_position = FastPaperShadowMarketPosition(
        market_key=MARKET_KEY,
        position_id="missing-position",
        mint=position.mint,
        current_exposure_fraction=0.5,
    )
    with pytest.raises(ValueError, match="OPEN|mapping|position"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(wrong_position,),
        )

    wrong_mint = FastPaperShadowMarketPosition(
        market_key=MARKET_KEY,
        position_id=position.position_id,
        mint="wrong-mint",
        current_exposure_fraction=0.5,
    )
    with pytest.raises(ValueError, match="mint|mapping|position"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(wrong_mint,),
        )


def test_shadow_runtime_state_rejects_partial_or_noncanonical_identity(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint = _database_fixture(tmp_path)

    with pytest.raises(ValueError, match="all|decision|identity"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(),
            last_processed_source_sequence=1,
        )

    with pytest.raises(ValueError, match="SHA|fingerprint"):
        build_fast_paper_shadow_runtime_state(
            manifest,
            binding,
            checkpoint,
            market_positions=(),
            last_processed_source_sequence=1,
            last_processed_source_event_id="event-1",
            last_processed_decision_evidence_fingerprint_sha256="not-a-sha",
        )


def test_shadow_runtime_state_round_trip_is_idempotent_and_checkpoint_bound(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint = _database_fixture(tmp_path)
    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        last_processed_source_sequence=3,
        last_processed_source_event_id="sig-3:0",
        last_processed_decision_evidence_fingerprint_sha256="b" * 64,
    )

    first = save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )
    repeated = save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )
    restored = load_latest_fast_paper_shadow_runtime_state(
        manifest,
        binding,
    )

    assert first == state
    assert repeated == state
    assert restored == state

    with sqlite3.connect(binding.database_path) as connection:
        row_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM fast_paper_shadow_runtime_states
            WHERE run_id = ?
            """,
            (binding.run_id,),
        ).fetchone()[0]
    assert row_count == 1


def test_shadow_runtime_state_fails_closed_on_torn_paper_checkpoint(
    tmp_path: Path,
) -> None:
    manifest, binding, checkpoint = _database_fixture(tmp_path)
    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )

    advanced = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        checkpoint.state,
        sequence=1,
        created_at_unix_ms=checkpoint.created_at_unix_ms + 1,
    )
    assert advanced.sequence == 1

    with pytest.raises(ValueError, match="checkpoint|torn|latest|advanced"):
        load_latest_fast_paper_shadow_runtime_state(
            manifest,
            binding,
        )


def test_shadow_runtime_state_detects_payload_tamper(tmp_path: Path) -> None:
    manifest, binding, checkpoint = _database_fixture(tmp_path)
    state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        state,
        created_at_unix_ms=checkpoint.created_at_unix_ms,
    )

    with sqlite3.connect(binding.database_path) as connection:
        connection.execute(
            """
            UPDATE fast_paper_shadow_runtime_states
            SET payload_sha256 = ?
            WHERE run_id = ?
            """,
            ("0" * 64, binding.run_id),
        )
        connection.commit()

    with pytest.raises(ValueError, match="checksum|fingerprint|payload"):
        load_latest_fast_paper_shadow_runtime_state(
            manifest,
            binding,
        )


def test_shadow_runtime_state_module_has_state_authority_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_paper_runtime"
        / "shadow_runtime_state.py"
    ).read_text(encoding="utf-8")

    for required in (
        "FastCampaignDecisionPosition",
        "FastPaperCheckpointRecord",
        "PaperPositionState",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
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
