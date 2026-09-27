from __future__ import annotations

from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_provision as provision
import shreks_brain.fast_paper_runtime.shadow_supervisor as supervisor
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    write_fast_paper_shadow_execution_policy,
)
from shreks_brain.fast_paper_runtime.shadow_ledger import (
    load_latest_fast_paper_shadow_ledger_checkpoint,
)
from shreks_brain.fast_paper_runtime.shadow_runtime_state import (
    load_latest_fast_paper_shadow_runtime_state,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceConfig,
)
from shreks_brain.fast_paper_runtime.shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionConfig,
)

from test_fast_paper_shadow_execution_input import (
    _execution_policy,
    _manifest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = (
    _REPO_ROOT
    / "deploy"
    / "systemd"
    / "shreks-fast-paper-shadow.env.example"
)


def _configs(tmp_path: Path):
    manifest = _manifest(tmp_path)
    execution_policy = _execution_policy(manifest)
    authority = tmp_path / "authority"
    authority.mkdir()
    execution_policy_path = authority / "execution-policy.json"
    write_fast_paper_shadow_execution_policy(
        execution_policy,
        execution_policy_path,
    )

    root = tmp_path / "shadow"
    root.mkdir()
    supervisor_config = supervisor.FastPaperShadowSupervisorConfig(
        decision_config=FastPaperShadowServiceConfig(
            manifest_path=(authority / "manifest.json").resolve(),
            policy_path=(authority / "service-policy.json").resolve(),
            evidence_directory=(root / "decision").resolve(),
            cycle_interval_seconds=2.0,
            maximum_decisions=1,
        ),
        execution_config=FastPaperShadowServiceExecutionConfig(
            execution_policy_path=execution_policy_path.resolve(),
            source_directory=(root / "execution-sources").resolve(),
            ledger_database_path=(root / "ledger.sqlite3").resolve(),
            run_id="shadow-provision-run-1",
        ),
        buy_authority_source_directory=(root / "buy-authority-sources").resolve(),
        quote_usd_source_directory=(root / "quote-usd-sources").resolve(),
        reduction_source_directory=(root / "reduction-sources").resolve(),
        pending_buy_retry_source_directory=(
            root / "pending-buy-retry-sources"
        ).resolve(),
        buy_writer_policy_path=(
            authority / "buy-writer-policy.json"
        ).resolve(),
    )
    config = provision.FastPaperShadowProvisionConfig(
        supervisor_config=supervisor_config,
        starting_cash_usd=20_000.0,
    )
    return manifest, execution_policy, config


def _patch_authority(monkeypatch, manifest):
    buy_writer_policy = object()
    monkeypatch.setattr(
        provision,
        "read_fast_paper_shadow_buy_writer_policy",
        lambda _path: buy_writer_policy,
    )
    monkeypatch.setattr(
        provision,
        "verify_fast_paper_shadow_buy_writer_policy_bindings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        provision,
        "read_fast_paper_runtime_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        provision,
        "read_fast_paper_shadow_service_policy",
        lambda _path: SimpleNamespace(
            route_evidence_version=manifest.route_evidence_version,
        ),
    )
    decision_bootstrap = SimpleNamespace(
        manifest=manifest,
        policy=object(),
        state=SimpleNamespace(cursor=None),
    )
    monkeypatch.setattr(
        provision,
        "bootstrap_fast_paper_shadow_service",
        lambda _config: decision_bootstrap,
    )
    return decision_bootstrap


def test_provision_config_reuses_supervisor_settings_and_requires_starting_cash(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _manifest_value, _policy, config = _configs(tmp_path)
    env = {
        "SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD": "20000.5",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        provision,
        "load_fast_paper_shadow_supervisor_config",
        lambda supplied: (
            captured.update(environment=supplied)
            or config.supervisor_config
        ),
    )

    loaded = provision.load_fast_paper_shadow_provision_config(env)

    assert loaded.supervisor_config is config.supervisor_config
    assert loaded.starting_cash_usd == 20_000.5
    assert captured["environment"] == env

    with pytest.raises(
        provision.FastPaperShadowProvisionError,
        match="STARTING_CASH|starting cash",
    ):
        provision.load_fast_paper_shadow_provision_config({})


def test_provision_creates_initial_isolated_pair_and_private_directories(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, execution_policy, config = _configs(tmp_path)
    decision_bootstrap = _patch_authority(monkeypatch, manifest)

    result = provision.provision_fast_paper_shadow(
        config,
        clock_unix_ms=lambda: 50_000,
    )

    assert result.created is True
    assert result.supervisor_bootstrap.decision_bootstrap is decision_bootstrap
    execution = result.supervisor_bootstrap.execution_bootstrap
    assert execution.checkpoint.sequence == 0
    assert execution.checkpoint.state.ledger.starting_cash_usd == 20_000.0
    assert execution.checkpoint.state.ledger.cash_balance_usd == 20_000.0
    assert execution.runtime_state.market_positions == ()
    assert execution.runtime_state.pending_buy is None
    assert execution.runtime_state.last_processed_source_sequence is None
    assert (
        execution.runtime_state.execution_policy_fingerprint_sha256
        == execution_policy.policy_fingerprint_sha256
    )

    for directory in (
        config.supervisor_config.decision_config.evidence_directory,
        config.supervisor_config.execution_config.source_directory,
        config.supervisor_config.buy_authority_source_directory,
        config.supervisor_config.quote_usd_source_directory,
        config.supervisor_config.reduction_source_directory,
        config.supervisor_config.pending_buy_retry_source_directory,
    ):
        assert directory.is_dir()
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700

    assert stat.S_IMODE(
        config.supervisor_config.execution_config.ledger_database_path.stat().st_mode
    ) == 0o600

    binding = execution.binding
    assert (
        load_latest_fast_paper_shadow_ledger_checkpoint(manifest, binding)
        == execution.checkpoint
    )
    assert (
        load_latest_fast_paper_shadow_runtime_state(manifest, binding)
        == execution.runtime_state
    )


def test_provision_existing_complete_run_is_verify_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, _execution_policy, config = _configs(tmp_path)
    _patch_authority(monkeypatch, manifest)
    first = provision.provision_fast_paper_shadow(
        config,
        clock_unix_ms=lambda: 50_000,
    )

    monkeypatch.setattr(
        provision,
        "initialize_fast_paper_shadow_ledger_database",
        lambda *_args, **_kwargs: pytest.fail(
            "existing complete run must not be reinitialized"
        ),
    )
    monkeypatch.setattr(
        provision,
        "save_fast_paper_shadow_ledger_checkpoint",
        lambda *_args, **_kwargs: pytest.fail(
            "existing complete run must not write checkpoint"
        ),
    )
    monkeypatch.setattr(
        provision,
        "save_fast_paper_shadow_runtime_state",
        lambda *_args, **_kwargs: pytest.fail(
            "existing complete run must not write runtime state"
        ),
    )

    second = provision.provision_fast_paper_shadow(
        config,
        clock_unix_ms=lambda: 60_000,
    )

    assert second.created is False
    assert (
        second.supervisor_bootstrap.execution_bootstrap.checkpoint
        == first.supervisor_bootstrap.execution_bootstrap.checkpoint
    )


def test_provision_existing_partial_database_fails_closed_without_repair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, _execution_policy, config = _configs(tmp_path)
    _patch_authority(monkeypatch, manifest)
    database = config.supervisor_config.execution_config.ledger_database_path
    database.write_bytes(b"")

    monkeypatch.setattr(
        provision,
        "initialize_fast_paper_shadow_ledger_database",
        lambda *_args, **_kwargs: pytest.fail(
            "existing partial database must not be repaired"
        ),
    )

    with pytest.raises(
        provision.FastPaperShadowProvisionError,
        match="existing|bootstrap|provision",
    ):
        provision.provision_fast_paper_shadow(
            config,
            clock_unix_ms=lambda: 50_000,
        )


def test_provision_requires_host_owned_parent_before_creating_leaf(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, _execution_policy, config = _configs(tmp_path)
    _patch_authority(monkeypatch, manifest)
    bad = provision.FastPaperShadowProvisionConfig(
        supervisor_config=supervisor.FastPaperShadowSupervisorConfig(
            decision_config=FastPaperShadowServiceConfig(
                manifest_path=config.supervisor_config.decision_config.manifest_path,
                policy_path=config.supervisor_config.decision_config.policy_path,
                evidence_directory=(
                    tmp_path / "missing-parent" / "decision"
                ).resolve(),
                cycle_interval_seconds=2.0,
                maximum_decisions=1,
            ),
            execution_config=config.supervisor_config.execution_config,
            buy_authority_source_directory=(
                config.supervisor_config.buy_authority_source_directory
            ),
            quote_usd_source_directory=(
                config.supervisor_config.quote_usd_source_directory
            ),
            reduction_source_directory=(
                config.supervisor_config.reduction_source_directory
            ),
            pending_buy_retry_source_directory=(
                config.supervisor_config.pending_buy_retry_source_directory
            ),
            buy_writer_policy_path=(
                config.supervisor_config.buy_writer_policy_path
            ),
        ),
        starting_cash_usd=20_000.0,
    )

    with pytest.raises(
        provision.FastPaperShadowProvisionError,
        match="parent|directory|provision",
    ):
        provision.provision_fast_paper_shadow(
            bad,
            clock_unix_ms=lambda: 50_000,
        )


def test_supervisor_preflight_remains_read_verify_only() -> None:
    payload = Path(supervisor.__file__).read_text(encoding="utf-8")
    assert "provision_fast_paper_shadow" not in payload
    assert "initialize_fast_paper_shadow_ledger_database" not in payload
    assert "save_fast_paper_shadow_ledger_checkpoint" not in payload
    assert "save_fast_paper_shadow_runtime_state" not in payload


def test_provisioner_source_has_initialization_authority_only() -> None:
    payload = Path(provision.__file__).read_text(encoding="utf-8")
    for required in (
        "initialize_fast_paper_shadow_ledger_database",
        "build_initial_fast_paper_shadow_ledger_state",
        "save_fast_paper_shadow_ledger_checkpoint",
        "build_fast_paper_shadow_runtime_state",
        "save_fast_paper_shadow_runtime_state",
        "bootstrap_fast_paper_shadow_service_execution",
    ):
        assert required in payload

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "produce_fast_paper_shadow_execution_input_source_record",
        "consume_fast_paper_shadow_service_execution_source_record",
        "execute_fast_paper_shadow_decision(",
        "retry_fast_paper_shadow_pending_buy(",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload


def test_shadow_env_example_includes_explicit_starting_cash() -> None:
    payload = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD=" in payload
