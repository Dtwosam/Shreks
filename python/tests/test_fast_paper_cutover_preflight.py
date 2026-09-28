from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_cutover_preflight as cutover
from shreks_brain.paper import PaperPositionState
from shreks_brain.paper_validation import AccountingValidationStatus


_RELEASE_SHA = "a" * 40
_FAST_MANIFEST = "b" * 64
_CHAMPION = "c" * 64
_REGISTRY = "d" * 64
_BINDING = "e" * 64
_RESTART = "f" * 64
_SHADOW_CHECKPOINT = "1" * 64
_LEGACY_MANIFEST = "2" * 64
_LEGACY_CHECKPOINT = "3" * 64
_AUTHORITATIVE_CHECKPOINT = "4" * 64
_AUTHORITATIVE_BINDING = "5" * 64
_AUTHORITATIVE_RUNTIME_STATE = "6" * 64
_AUTHORITATIVE_COMMISSIONING = "7" * 64


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _restart_receipt(**overrides) -> dict[str, object]:
    material: dict[str, object] = {
        "schema_name": "shreks.fast_paper_shadow_physical_restart",
        "schema_version": 1,
        "state": "RESTART_RECONSTRUCTION_PROVEN",
        "release_source_sha": _RELEASE_SHA,
        "release_directory": f"/opt/shreks/releases/{_RELEASE_SHA}",
        "pre_restart_main_pid": 100,
        "post_restart_main_pid": 101,
        "pre_restart_invocation_id": "before",
        "post_restart_invocation_id": "after",
        "automatic_restart_delta": 0,
        "pre_checkpoint_sequence": 10,
        "post_checkpoint_sequence": 11,
        "pre_last_processed_source_sequence": 20,
        "post_last_processed_source_sequence": 21,
        "run_id": "shadow-run-1",
        "binding_fingerprint_sha256": _BINDING,
        "observed_at_unix_ms": 1_000,
        "observation_seconds": 60,
        "main_pid": 101,
        "invocation_id": "after",
        "unit_file_state": "static",
        "n_restarts": 0,
        "exec_main_status": 0,
        "manifest_fingerprint_sha256": _FAST_MANIFEST,
        "champion_version": "fast-champion-v1",
        "champion_fingerprint_sha256": _CHAMPION,
        "action_policy_version": 7,
        "completed_cycles_start": 10,
        "completed_cycles_end": 12,
        "completed_cycles_delta": 2,
        "decisions_produced_delta": 2,
        "executions_committed_delta": 1,
        "decision_cursor_sequence_start": 20,
        "decision_cursor_sequence_end": 21,
        "execution_cursor_sequence_start": 10,
        "execution_cursor_sequence_end": 11,
        "paper_checkpoint_sequence_start": 10,
        "paper_checkpoint_sequence_end": 11,
        "pending_buy": False,
        "open_market_positions": 0,
        "cpu_ticks_delta": 1,
        "cpu_percent": 1.0,
        "rss_bytes_start": 1,
        "rss_bytes_end": 1,
        "rss_bytes_peak": 1,
        "shadow_storage_bytes_start": 1,
        "shadow_storage_bytes_end": 1,
        "shadow_storage_bytes_delta": 0,
        "private_network_interfaces": ["lo"],
        "private_network_non_loopback_interfaces": [],
        "private_network_rx_bytes_delta": 0,
        "private_network_tx_bytes_delta": 0,
        "shadow_runtime": "ACTIVE_DETACHED",
        "shadow_enable_authority": "NOT_GRANTED",
        "production_paper_cutover": "NOT_GRANTED",
        "authoritative_paper_runtime": "LEGACY_UNCHANGED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    material.update(overrides)
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _write_restart(path: Path, **overrides) -> Path:
    document = _restart_receipt(**overrides)
    path.write_text(_canonical(document), encoding="utf-8")
    return path


def _legacy_state(
    *,
    open_positions: int = 0,
    pending_entry: bool = False,
    pending_exits: int = 0,
):
    positions = tuple(
        SimpleNamespace(state=PaperPositionState.OPEN)
        for _ in range(open_positions)
    )
    managed = tuple(
        SimpleNamespace(
            pending_exit=(SimpleNamespace() if index < pending_exits else None)
        )
        for index in range(max(open_positions, pending_exits))
    )
    return SimpleNamespace(
        ledger=SimpleNamespace(positions=positions),
        pending_entry=(SimpleNamespace() if pending_entry else None),
        managed_positions=managed,
        last_cycle_at_unix_ms=2_000,
    )


def _patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    legacy_state=None,
    shadow_status=AccountingValidationStatus.RECONCILED,
    legacy_status=AccountingValidationStatus.RECONCILED,
    legacy_checkpoint_present: bool = True,
    registry_champion: str = _CHAMPION,
    binding_fingerprint: str = _BINDING,
    shadow_checkpoint_sequence: int = 12,
    authoritative_checkpoint_sequence: int = 0,
    authoritative_legacy_checkpoint_sha: str = _LEGACY_CHECKPOINT,
    authoritative_cursor_sequence: int | None = None,
    authoritative_open_positions: int = 0,
    authoritative_pending_buy: bool = False,
    authoritative_status=AccountingValidationStatus.RECONCILED,
) -> None:
    if legacy_state is None:
        legacy_state = _legacy_state()
    manifest = SimpleNamespace(
        release_source_sha=_RELEASE_SHA,
        manifest_fingerprint_sha256=_FAST_MANIFEST,
        champion_version="fast-champion-v1",
        champion_fingerprint_sha256=_CHAMPION,
        action_policy=SimpleNamespace(version=7),
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_runtime_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        cutover,
        "verify_fast_paper_runtime_bindings",
        lambda _manifest: None,
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_champion_registry",
        lambda _path: {
            "revision": 2,
            "current_champion_version": "fast-champion-v1",
            "current_champion_fingerprint_sha256": registry_champion,
            "registry_fingerprint_sha256": _REGISTRY,
        },
    )
    monkeypatch.setattr(
        cutover,
        "build_fast_paper_shadow_ledger_binding",
        lambda _manifest, run_id, database_path: SimpleNamespace(
            run_id=run_id,
            database_path=str(database_path),
            binding_fingerprint_sha256=binding_fingerprint,
        ),
    )
    monkeypatch.setattr(
        cutover,
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        lambda _manifest, _binding: SimpleNamespace(
            sequence=shadow_checkpoint_sequence,
            payload_sha256=_SHADOW_CHECKPOINT,
            state=SimpleNamespace(kind="shadow"),
        ),
    )
    monkeypatch.setattr(
        cutover,
        "validate_fast_paper_accounting",
        lambda state: SimpleNamespace(
            status=(
                authoritative_status
                if getattr(state, "kind", None) == "authoritative"
                else shadow_status
            )
        ),
    )
    monkeypatch.setattr(
        cutover,
        "decode_observer_paper_campaign_runtime_manifest",
        lambda _payload: SimpleNamespace(
            paper_run_id="legacy-run-1",
            manifest_fingerprint_sha256=_LEGACY_MANIFEST,
        ),
    )
    monkeypatch.setattr(
        cutover,
        "read_fast_paper_authoritative_cutover_environment",
        lambda _path: {"sealed": "environment"},
    )
    monkeypatch.setattr(
        cutover,
        "encode_fast_paper_authoritative_cutover_environment",
        lambda _env: "sealed=environment\n",
    )
    monkeypatch.setattr(
        cutover,
        "validate_fast_paper_authoritative_cutover_environment",
        lambda _env, _manifest, authoritative_database_path: (
            SimpleNamespace(database_path=str(authoritative_database_path))
        ),
    )
    monkeypatch.setattr(
        cutover,
        "verify_fast_paper_authoritative_commissioning_wheel",
        lambda _path, expected_source_sha, expected_platform: SimpleNamespace(
            source_sha=expected_source_sha,
            platform=expected_platform,
            manifest_fingerprint_sha256=_AUTHORITATIVE_COMMISSIONING,
        ),
    )
    authoritative_positions = tuple(
        SimpleNamespace(market_key=f"market-{index}")
        for index in range(authoritative_open_positions)
    )
    authoritative_state = SimpleNamespace(
        kind="authoritative",
        ledger=legacy_state.ledger,
        pending_buy=(SimpleNamespace() if authoritative_pending_buy else None),
    )
    authoritative_runtime_state = SimpleNamespace(
        market_positions=authoritative_positions,
        last_processed_source_sequence=authoritative_cursor_sequence,
        last_processed_source_event_id=(
            None if authoritative_cursor_sequence is None else "event"
        ),
        last_processed_decision_evidence_fingerprint_sha256=(
            None if authoritative_cursor_sequence is None else "a" * 64
        ),
        state_fingerprint_sha256=_AUTHORITATIVE_RUNTIME_STATE,
    )
    authoritative_execution = SimpleNamespace(
        binding=SimpleNamespace(
            fast_run_id="fast-authoritative-run-1",
            binding_fingerprint_sha256=_AUTHORITATIVE_BINDING,
            legacy_run_id="legacy-run-1",
            legacy_checkpoint_sequence=9,
            legacy_checkpoint_payload_sha256=(
                authoritative_legacy_checkpoint_sha
            ),
            legacy_runtime_manifest_fingerprint_sha256=_LEGACY_MANIFEST,
        ),
        checkpoint=SimpleNamespace(
            sequence=authoritative_checkpoint_sequence,
            payload_sha256=_AUTHORITATIVE_CHECKPOINT,
            state=authoritative_state,
        ),
        runtime_state=authoritative_runtime_state,
    )
    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        lambda _config: SimpleNamespace(
            decision_bootstrap=SimpleNamespace(
                state=SimpleNamespace(cursor=None)
            ),
            execution_bootstrap=authoritative_execution,
        ),
    )
    monkeypatch.setattr(
        cutover,
        "load_latest_paper_checkpoint",
        lambda _db, _run_id: (
            SimpleNamespace(
                sequence=9,
                payload_sha256=_LEGACY_CHECKPOINT,
                state=legacy_state,
            )
            if legacy_checkpoint_present
            else None
        ),
    )
    monkeypatch.setattr(
        cutover,
        "validate_paper_accounting",
        lambda _state: SimpleNamespace(status=legacy_status),
    )


def _assess(tmp_path: Path):
    legacy_manifest = tmp_path / "legacy-manifest.json"
    legacy_manifest.write_text("{}\n", encoding="utf-8")
    return cutover.assess_fast_paper_cutover_preflight(
        fast_manifest_path=tmp_path / "fast-manifest.json",
        champion_registry_path=tmp_path / "champion-registry.json",
        shadow_restart_receipt_path=_write_restart(
            tmp_path / "restart.json"
        ),
        shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
        legacy_runtime_manifest_path=legacy_manifest,
        legacy_observer_database_path=tmp_path / "observer.sqlite3",
        authoritative_runtime_env_path=tmp_path / "fast-paper-authoritative.env",
        authoritative_release_wheel_path=tmp_path / "shreks-brain.whl",
        release_platform="x86_64-unknown-linux-gnu",
        expected_release_sha=_RELEASE_SHA,
    )


def _gate(report: dict[str, object], code: str) -> dict[str, object]:
    gates = report["gate_results"]
    assert isinstance(gates, list)
    return next(gate for gate in gates if gate["code"] == code)


def test_cutover_preflight_ready_when_all_handoff_state_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch)

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_READY"
    assert report["observed_state"] == {
        "shadow_accounting_status": "RECONCILED",
        "legacy_accounting_status": "RECONCILED",
        "legacy_open_position_count": 0,
        "legacy_pending_entry_count": 0,
        "legacy_deferred_execution_count": 0,
        "legacy_active_intent_count": 0,
        "authoritative_accounting_status": "RECONCILED",
        "authoritative_checkpoint_sequence": 0,
        "authoritative_pending_buy_count": 0,
        "authoritative_open_position_count": 0,
        "authoritative_learned_cursor_empty": True,
        "learned_decision_cursor_sequence": None,
        "authoritative_first_cycle_cursor_compatible": True,
        "authoritative_ledger_matches_legacy": True,
    }
    assert {gate["status"] for gate in report["gate_results"]} == {"PASS"}
    assert report["production_fast_paper_runner"] == "SEALED_NOT_ACTIVE"
    assert report["production_paper_cutover"] == "NOT_GRANTED"
    assert report["service_control_authority"] == "NOT_GRANTED"
    assert report["authoritative_paper_mutation"] == "NOT_GRANTED"
    assert report["signing_submission_authority"] == "NOT_GRANTED"
    assert report["live_authority"] == "DISABLED"


def test_open_legacy_position_fails_closed_as_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        legacy_state=_legacy_state(open_positions=1),
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert _gate(report, "LEGACY_OPEN_POSITIONS_ZERO")["status"] == "FAIL"


def test_pending_legacy_entry_fails_pending_and_active_intent_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        legacy_state=_legacy_state(pending_entry=True),
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert _gate(report, "LEGACY_PENDING_ENTRIES_ZERO")["status"] == "FAIL"
    assert _gate(report, "LEGACY_DEFERRED_EXECUTIONS_ZERO")["status"] == "FAIL"
    assert _gate(report, "LEGACY_ACTIVE_INTENTS_ZERO")["status"] == "FAIL"


def test_pending_legacy_exit_fails_deferred_execution_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        legacy_state=_legacy_state(open_positions=1, pending_exits=1),
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert _gate(report, "LEGACY_DEFERRED_EXECUTIONS_ZERO")["status"] == "FAIL"


@pytest.mark.parametrize(
    ("shadow_status", "legacy_status", "failed_gate"),
    (
        (
            AccountingValidationStatus.INVALID,
            AccountingValidationStatus.RECONCILED,
            "SHADOW_PAPER_ACCOUNTING_RECONCILED",
        ),
        (
            AccountingValidationStatus.RECONCILED,
            AccountingValidationStatus.INCOMPLETE,
            "LEGACY_PAPER_ACCOUNTING_RECONCILED",
        ),
    ),
)
def test_accounting_must_be_reconciled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shadow_status,
    legacy_status,
    failed_gate: str,
) -> None:
    _patch_dependencies(
        monkeypatch,
        shadow_status=shadow_status,
        legacy_status=legacy_status,
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert _gate(report, failed_gate)["status"] == "FAIL"


def test_missing_final_legacy_checkpoint_is_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        legacy_checkpoint_present=False,
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert _gate(report, "LEGACY_FINAL_CHECKPOINT_PRESENT")["status"] == "FAIL"


def test_promoted_champion_identity_drift_is_hard_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        registry_champion="9" * 64,
    )

    with pytest.raises(
        cutover.FastPaperCutoverPreflightError,
        match="approved champion",
    ):
        _assess(tmp_path)


def test_restart_receipt_fingerprint_drift_is_hard_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch)
    receipt = _restart_receipt()
    receipt["receipt_fingerprint_sha256"] = "0" * 64
    path = tmp_path / "restart.json"
    path.write_text(_canonical(receipt), encoding="utf-8")
    legacy_manifest = tmp_path / "legacy-manifest.json"
    legacy_manifest.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        cutover.FastPaperCutoverPreflightError,
        match="fingerprint",
    ):
        cutover.assess_fast_paper_cutover_preflight(
            fast_manifest_path=tmp_path / "fast-manifest.json",
            champion_registry_path=tmp_path / "champion-registry.json",
            shadow_restart_receipt_path=path,
            shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
            legacy_runtime_manifest_path=legacy_manifest,
            legacy_observer_database_path=tmp_path / "observer.sqlite3",
            authoritative_runtime_env_path=tmp_path / "fast-paper-authoritative.env",
            authoritative_release_wheel_path=tmp_path / "shreks-brain.whl",
            release_platform="x86_64-unknown-linux-gnu",
            expected_release_sha=_RELEASE_SHA,
        )


@pytest.mark.parametrize(
    ("overrides", "match"),
    (
        ({"release_source_sha": "9" * 40}, "release"),
        ({"manifest_fingerprint_sha256": "9" * 64}, "manifest"),
        ({"champion_fingerprint_sha256": "9" * 64}, "champion"),
    ),
)
def test_restart_receipt_identity_drift_is_hard_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides,
    match: str,
) -> None:
    _patch_dependencies(monkeypatch)
    path = _write_restart(tmp_path / "restart.json", **overrides)
    legacy_manifest = tmp_path / "legacy-manifest.json"
    legacy_manifest.write_text("{}\n", encoding="utf-8")

    with pytest.raises(cutover.FastPaperCutoverPreflightError, match=match):
        cutover.assess_fast_paper_cutover_preflight(
            fast_manifest_path=tmp_path / "fast-manifest.json",
            champion_registry_path=tmp_path / "champion-registry.json",
            shadow_restart_receipt_path=path,
            shadow_ledger_database_path=tmp_path / "shadow.sqlite3",
            legacy_runtime_manifest_path=legacy_manifest,
            legacy_observer_database_path=tmp_path / "observer.sqlite3",
            authoritative_runtime_env_path=tmp_path / "fast-paper-authoritative.env",
            authoritative_release_wheel_path=tmp_path / "shreks-brain.whl",
            release_platform="x86_64-unknown-linux-gnu",
            expected_release_sha=_RELEASE_SHA,
        )


def test_shadow_checkpoint_cannot_regress_behind_restart_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        shadow_checkpoint_sequence=10,
    )

    report = _assess(tmp_path)

    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert (
        _gate(report, "SHADOW_CHECKPOINT_NOT_BEFORE_RESTART_PROOF")["status"]
        == "FAIL"
    )


def test_shadow_binding_drift_is_hard_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        binding_fingerprint="9" * 64,
    )

    with pytest.raises(
        cutover.FastPaperCutoverPreflightError,
        match="binding fingerprint",
    ):
        _assess(tmp_path)


def test_report_fingerprint_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch)

    report = _assess(tmp_path)
    material = dict(report)
    claimed = material.pop("report_fingerprint_sha256")

    assert claimed == hashlib.sha256(
        cutover.canonical_fast_paper_cutover_preflight(material).encode(
            "utf-8"
        )
    ).hexdigest()




def test_advanced_learned_cursor_requires_durable_cutover_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch)
    original = cutover.bootstrap_fast_paper_authoritative_runtime

    def with_advanced_cursor(config):
        bootstrap = original(config)
        return SimpleNamespace(
            decision_bootstrap=SimpleNamespace(
                state=SimpleNamespace(
                    cursor=SimpleNamespace(decision_sequence=41)
                )
            ),
            execution_bootstrap=bootstrap.execution_bootstrap,
        )

    monkeypatch.setattr(
        cutover,
        "bootstrap_fast_paper_authoritative_runtime",
        with_advanced_cursor,
    )
    report = _assess(tmp_path)
    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert (
        _gate(
            report,
            "AUTHORITATIVE_FIRST_CYCLE_CURSOR_COMPATIBLE",
        )["status"]
        == "FAIL"
    )

def test_authoritative_handoff_must_bind_exact_final_legacy_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        authoritative_legacy_checkpoint_sha="9" * 64,
    )
    report = _assess(tmp_path)
    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert (
        _gate(report, "AUTHORITATIVE_HANDOFF_MATCHES_FINAL_LEGACY")["status"]
        == "FAIL"
    )


def test_authoritative_runtime_must_remain_unexecuted_before_cutover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        authoritative_checkpoint_sequence=1,
        authoritative_cursor_sequence=1,
        authoritative_open_positions=1,
        authoritative_pending_buy=True,
    )
    report = _assess(tmp_path)
    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    for code in (
        "AUTHORITATIVE_CHECKPOINT_INITIAL",
        "AUTHORITATIVE_PENDING_BUY_ZERO",
        "AUTHORITATIVE_OPEN_POSITIONS_ZERO",
        "AUTHORITATIVE_LEARNED_CURSOR_EMPTY",
    ):
        assert _gate(report, code)["status"] == "FAIL"


def test_authoritative_runtime_accounting_must_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        authoritative_status=AccountingValidationStatus.INVALID,
    )
    report = _assess(tmp_path)
    assert report["decision"] == "CUTOVER_PREFLIGHT_NOT_READY"
    assert (
        _gate(report, "AUTHORITATIVE_PAPER_ACCOUNTING_RECONCILED")["status"]
        == "FAIL"
    )

def test_packaging_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_paper_cutover_preflight.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert (
        'shreks-fast-paper-cutover-preflight = '
        '"shreks_brain.fast_paper_cutover_preflight:main"'
    ) in pyproject

    forbidden = (
        "score_candidate",
        "decide_entry",
        "run_paper_cycle",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "save_paper_checkpoint",
        "save_fast_paper_checkpoint",
        "commit_fast_paper_shadow_transition_atomically",
        "record_fast_paper",
        "systemctl",
        "subprocess",
        "RegistryStore",
        "promote_fast_paper_champion",
        "sign_transaction",
        "submit_transaction",
        "LIVE_ENABLED",
    )
    for token in forbidden:
        assert token not in source
