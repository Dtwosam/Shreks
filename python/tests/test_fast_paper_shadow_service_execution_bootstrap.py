from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_service_execution_bootstrap as execution_bootstrap
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowServiceExecutionBootstrap,
    FastPaperShadowServiceExecutionConfig,
    bootstrap_fast_paper_shadow_service_execution,
    load_fast_paper_shadow_service_execution_config,
)
from shreks_brain.fast_paper_runtime.shadow_execution_input import (
    write_fast_paper_shadow_execution_policy,
)
from shreks_brain.fast_paper_runtime.shadow_ledger import (
    build_fast_paper_shadow_ledger_binding,
    build_initial_fast_paper_shadow_ledger_state,
    initialize_fast_paper_shadow_ledger_database,
    save_fast_paper_shadow_ledger_checkpoint,
)
from shreks_brain.fast_paper_runtime.shadow_runtime_state import (
    build_fast_paper_shadow_runtime_state,
    save_fast_paper_shadow_runtime_state,
)

from test_fast_paper_shadow_execution_input import (
    _execution_policy,
    _manifest,
)


def _durable_fixture(
    tmp_path: Path,
    *,
    runtime_policy_fingerprint: str | None = None,
):
    manifest = _manifest(tmp_path)
    execution_policy = _execution_policy(manifest)
    policy_path = tmp_path / "authority" / "execution-policy.json"
    policy_path.parent.mkdir()
    write_fast_paper_shadow_execution_policy(
        execution_policy,
        policy_path,
    )

    database = tmp_path / "ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-service-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    initial = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=50_000,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=execution_policy.position_action_policy,
    )
    checkpoint = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        initial,
        sequence=0,
        created_at_unix_ms=50_000,
    )
    runtime_state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            execution_policy.policy_fingerprint_sha256
            if runtime_policy_fingerprint is None
            else runtime_policy_fingerprint
        ),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        runtime_state,
        created_at_unix_ms=50_000,
    )
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    config = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=policy_path.resolve(),
        source_directory=source_directory.resolve(),
        ledger_database_path=database.resolve(),
        run_id=binding.run_id,
    )
    return (
        manifest,
        execution_policy,
        binding,
        checkpoint,
        runtime_state,
        config,
    )


def test_execution_bootstrap_config_loader_requires_explicit_settings(
    tmp_path: Path,
) -> None:
    values = {
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH": str(
            tmp_path / "policy.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY": str(
            tmp_path / "sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH": str(
            tmp_path / "ledger.sqlite3"
        ),
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID": "shadow-run-a",
    }

    config = load_fast_paper_shadow_service_execution_config(values)

    assert type(config) is FastPaperShadowServiceExecutionConfig
    assert config.execution_policy_path == (tmp_path / "policy.json").resolve()
    assert config.source_directory == (tmp_path / "sources").resolve()
    assert config.ledger_database_path == (tmp_path / "ledger.sqlite3").resolve()
    assert config.run_id == "shadow-run-a"

    for name in tuple(values):
        incomplete = dict(values)
        incomplete.pop(name)
        with pytest.raises(ValueError, match=name):
            load_fast_paper_shadow_service_execution_config(incomplete)


def test_execution_bootstrap_authenticates_existing_durable_run(
    tmp_path: Path,
) -> None:
    (
        manifest,
        execution_policy,
        binding,
        checkpoint,
        runtime_state,
        config,
    ) = _durable_fixture(tmp_path)

    result = bootstrap_fast_paper_shadow_service_execution(
        manifest,
        config,
    )

    assert type(result) is FastPaperShadowServiceExecutionBootstrap
    assert result.binding == binding
    assert result.execution_policy == execution_policy
    assert result.checkpoint == checkpoint
    assert result.runtime_state == runtime_state
    assert result.source_directory == config.source_directory


def test_execution_bootstrap_requires_existing_checkpoint(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    execution_policy = _execution_policy(manifest)
    policy_path = tmp_path / "authority" / "execution-policy.json"
    policy_path.parent.mkdir()
    write_fast_paper_shadow_execution_policy(execution_policy, policy_path)
    database = tmp_path / "ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-service-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()

    config = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=policy_path.resolve(),
        source_directory=source_directory.resolve(),
        ledger_database_path=database.resolve(),
        run_id=binding.run_id,
    )
    with pytest.raises(ValueError, match="checkpoint"):
        bootstrap_fast_paper_shadow_service_execution(manifest, config)


def test_execution_bootstrap_requires_existing_runtime_state(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    execution_policy = _execution_policy(manifest)
    policy_path = tmp_path / "authority" / "execution-policy.json"
    policy_path.parent.mkdir()
    write_fast_paper_shadow_execution_policy(execution_policy, policy_path)
    database = tmp_path / "ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-service-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    initial = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=50_000,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=execution_policy.position_action_policy,
    )
    save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        initial,
        sequence=0,
        created_at_unix_ms=50_000,
    )
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    config = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=policy_path.resolve(),
        source_directory=source_directory.resolve(),
        ledger_database_path=database.resolve(),
        run_id=binding.run_id,
    )

    with pytest.raises(ValueError, match="runtime state"):
        bootstrap_fast_paper_shadow_service_execution(manifest, config)


def test_execution_bootstrap_rejects_execution_policy_drift(
    tmp_path: Path,
) -> None:
    manifest, _policy, _binding, _checkpoint, _runtime, config = (
        _durable_fixture(
            tmp_path,
            runtime_policy_fingerprint="e" * 64,
        )
    )

    with pytest.raises(ValueError, match="execution policy|fingerprint"):
        bootstrap_fast_paper_shadow_service_execution(manifest, config)


def test_execution_bootstrap_rejects_source_directory_symlink(
    tmp_path: Path,
) -> None:
    manifest, _policy, _binding, _checkpoint, _runtime, config = (
        _durable_fixture(tmp_path)
    )
    real = config.source_directory
    link = tmp_path / "execution-sources-link"
    link.symlink_to(real, target_is_directory=True)
    bad = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=config.execution_policy_path,
        source_directory=link,
        ledger_database_path=config.ledger_database_path,
        run_id=config.run_id,
    )

    with pytest.raises(ValueError, match="source directory|symlink"):
        bootstrap_fast_paper_shadow_service_execution(manifest, bad)


def test_execution_bootstrap_rejects_policy_inside_writable_source_directory(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    execution_policy = _execution_policy(manifest)
    source_directory = tmp_path / "execution-sources"
    source_directory.mkdir()
    policy_path = source_directory / "execution-policy.json"
    write_fast_paper_shadow_execution_policy(execution_policy, policy_path)

    database = tmp_path / "ledger" / "runtime.sqlite3"
    binding = build_fast_paper_shadow_ledger_binding(
        manifest,
        run_id="shadow-service-run-1",
        database_path=database,
    )
    initialize_fast_paper_shadow_ledger_database(manifest, binding)
    initial = build_initial_fast_paper_shadow_ledger_state(
        manifest,
        binding,
        starting_cash_usd=20_000.0,
        as_of_unix_ms=50_000,
        fill_policy=execution_policy.fill_policy,
        position_action_policy=execution_policy.position_action_policy,
    )
    checkpoint = save_fast_paper_shadow_ledger_checkpoint(
        manifest,
        binding,
        initial,
        sequence=0,
        created_at_unix_ms=50_000,
    )
    runtime_state = build_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        checkpoint,
        market_positions=(),
        execution_policy_fingerprint_sha256=(
            execution_policy.policy_fingerprint_sha256
        ),
    )
    save_fast_paper_shadow_runtime_state(
        manifest,
        binding,
        runtime_state,
        created_at_unix_ms=50_000,
    )

    config = FastPaperShadowServiceExecutionConfig(
        execution_policy_path=policy_path.resolve(),
        source_directory=source_directory.resolve(),
        ledger_database_path=database.resolve(),
        run_id=binding.run_id,
    )
    with pytest.raises(ValueError, match="policy|source directory"):
        bootstrap_fast_paper_shadow_service_execution(manifest, config)


def test_execution_bootstrap_module_has_read_verify_authority_only() -> None:
    source = Path(execution_bootstrap.__file__).read_text(encoding="utf-8")
    required = (
        "read_fast_paper_shadow_execution_policy",
        "build_fast_paper_shadow_ledger_binding",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "initialize_fast_paper_shadow_ledger_database",
        "save_fast_paper_shadow_ledger_checkpoint",
        "save_fast_paper_shadow_runtime_state",
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "consume_fast_paper_shadow_service_execution_source_record",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "shreks_brain.scoring",
        "score_candidate",
        "requests",
        "httpx",
        "urllib",
        "RuntimeMode.LIVE",
    )
    for marker in forbidden:
        assert marker not in source
