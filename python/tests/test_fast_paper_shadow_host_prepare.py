from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_shadow_host_prepare as host_prepare


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "python" / "pyproject.toml"
_TARGET = _REPO_ROOT / "deploy" / "systemd" / "shreks.target"
_RELEASE_MANAGER = _REPO_ROOT / "deploy" / "release" / "release_manager.py"

_SHA = "a" * 40
_UID = os.getuid()
_GID = os.getgid()


def _environment(run_id: str = "shadow-run-prod-1") -> dict[str, str]:
    return {
        "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH": (
            "/etc/shreks/fast-paper-runtime-manifest.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH": (
            "/etc/shreks/fast-paper-shadow-service-policy.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/decision"
        ),
        "SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS": "2.0",
        "SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS": "1",
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH": (
            "/etc/shreks/fast-paper-shadow-execution-policy.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/execution-sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH": (
            "/var/lib/shreks/fast-paper-shadow/ledger.sqlite3"
        ),
        "SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID": run_id,
        "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH": (
            "/etc/shreks/fast-paper-shadow-buy-writer-policy.json"
        ),
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/buy-authority-sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/quote-usd-sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/reduction-sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-shadow/pending-buy-retry-sources"
        ),
        "SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD": "20000.0",
    }


def _candidate(tmp_path: Path, env: dict[str, str] | None = None) -> Path:
    path = tmp_path / "candidate.env"
    payload = host_prepare.encode_fast_paper_shadow_host_environment(
        _environment() if env is None else env
    )
    path.write_text(payload, encoding="utf-8")
    return path


def _layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    release = tmp_path / "opt" / "shreks" / "releases" / _SHA
    runtime = release / ".venv" / "bin" / "python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime.chmod(0o755)
    current = tmp_path / "opt" / "shreks" / "current"
    current.parent.mkdir(parents=True)
    current.symlink_to(release)

    etc_shreks = tmp_path / "etc" / "shreks"
    etc_shreks.mkdir(parents=True)
    etc_shreks.chmod(0o750)
    unit_parent = tmp_path / "etc" / "systemd" / "system"
    unit_parent.mkdir(parents=True)
    unit = unit_parent / "shreks-fast-paper-shadow.service"
    unit.write_text("[Service]\nPrivateNetwork=true\n", encoding="utf-8")
    unit.chmod(0o644)
    target = unit_parent / "shreks.target"
    target.write_text("[Unit]\nDescription=core\n", encoding="utf-8")
    target.chmod(0o644)

    shadow_root = tmp_path / "var" / "lib" / "shreks" / "fast-paper-shadow"
    shadow_root.mkdir(parents=True)
    shadow_root.chmod(0o700)

    config_destination = etc_shreks / "fast-paper-shadow.env"

    monkeypatch.setattr(host_prepare.os, "geteuid", lambda: 0)
    monkeypatch.setattr(host_prepare.os, "getegid", lambda: _GID)
    monkeypatch.setattr(host_prepare, "_ROOT_UID", _UID)
    monkeypatch.setattr(host_prepare, "_ROOT_GID", _GID)
    monkeypatch.setattr(
        host_prepare,
        "preflight_release_bound_fast_paper_shadow_unit",
        lambda **_kwargs: {"status": "READY_ALREADY_INSTALLED"},
    )

    paths = host_prepare.FastPaperShadowHostPreparePaths(
        current_link=current,
        unit_destination=unit,
        config_destination=config_destination,
        shadow_root=shadow_root,
        target_path=target,
    )
    return {
        "release": release,
        "runtime": runtime,
        "current": current,
        "unit": unit,
        "target": target,
        "shadow_root": shadow_root,
        "config": config_destination,
        "paths": paths,
    }


def _fake_provision_config(env: dict[str, str]):
    root = Path(env["SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY"]).parent
    decision = Path(env["SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY"])
    execution_sources = Path(
        env["SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY"]
    )
    buy = Path(
        env["SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY"]
    )
    quote = Path(env["SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY"])
    reduction = Path(
        env["SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY"]
    )
    retry = Path(
        env[
            "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY"
        ]
    )
    return SimpleNamespace(
        starting_cash_usd=float(
            env["SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD"]
        ),
        supervisor_config=SimpleNamespace(
            decision_config=SimpleNamespace(
                manifest_path=Path(
                    env["SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH"]
                ),
                policy_path=Path(
                    env["SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH"]
                ),
                evidence_directory=decision,
            ),
            execution_config=SimpleNamespace(
                execution_policy_path=Path(
                    env[
                        "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH"
                    ]
                ),
                source_directory=execution_sources,
                ledger_database_path=Path(
                    env[
                        "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH"
                    ]
                ),
                run_id=env["SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID"],
            ),
            buy_writer_policy_path=Path(
                env[
                    "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH"
                ]
            ),
            buy_authority_source_directory=buy,
            quote_usd_source_directory=quote,
            reduction_source_directory=reduction,
            pending_buy_retry_source_directory=retry,
        ),
    )


def test_environment_parser_is_closed_and_rejects_shell_syntax(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        host_prepare,
        "load_fast_paper_shadow_provision_config",
        _fake_provision_config,
    )
    candidate = _candidate(tmp_path)
    parsed = host_prepare.read_fast_paper_shadow_host_environment(candidate)
    assert parsed == _environment()

    for payload in (
        "export SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH=/tmp/x\n",
        "A=$(id)\n",
        "A=\"quoted\"\n",
        "A=$HOME\n",
        "A=x;id\n",
        "A=x\\\nB=y\n",
        "A=x\nA=y\n",
    ):
        candidate.write_text(payload, encoding="utf-8")
        with pytest.raises(
            host_prepare.FastPaperShadowHostPrepareError
        ):
            host_prepare.read_fast_paper_shadow_host_environment(candidate)


def test_environment_requires_exact_key_set_and_production_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        host_prepare,
        "load_fast_paper_shadow_provision_config",
        _fake_provision_config,
    )
    env = _environment()
    host_prepare.validate_fast_paper_shadow_production_environment(env)

    missing = dict(env)
    missing.pop("SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD")
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="key set",
    ):
        host_prepare.validate_fast_paper_shadow_production_environment(
            missing
        )

    wrong = dict(env)
    wrong["SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH"] = (
        "/tmp/ledger.sqlite3"
    )
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="production path",
    ):
        host_prepare.validate_fast_paper_shadow_production_environment(
            wrong
        )

    placeholder = _environment("replace-with-provisioned-shadow-run-id")
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="run id",
    ):
        host_prepare.validate_fast_paper_shadow_production_environment(
            placeholder
        )


def test_config_preflight_and_install_are_exact_no_replace_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    monkeypatch.setattr(
        host_prepare,
        "load_fast_paper_shadow_provision_config",
        _fake_provision_config,
    )
    candidate = _candidate(tmp_path)

    preflight = host_prepare.preflight_fast_paper_shadow_host_config(
        expected_release_source_sha=_SHA,
        candidate_env_path=candidate,
        paths=setup["paths"],
        runtime_executable=setup["runtime"],
        service_uid=_UID,
        service_gid=_GID,
    )
    assert preflight["state"] == "READY_TO_INSTALL_CONFIG"

    receipt = host_prepare.install_fast_paper_shadow_host_config(
        expected_release_source_sha=_SHA,
        candidate_env_path=candidate,
        paths=setup["paths"],
        runtime_executable=setup["runtime"],
        service_uid=_UID,
        service_gid=_GID,
    )
    assert receipt["state"] == "CONFIG_INSTALLED"
    assert setup["config"].read_text(encoding="utf-8") == (
        host_prepare.encode_fast_paper_shadow_host_environment(
            _environment()
        )
    )
    metadata = setup["config"].stat()
    assert metadata.st_uid == _UID
    assert metadata.st_gid == _GID
    assert stat.S_IMODE(metadata.st_mode) == 0o640

    again = host_prepare.install_fast_paper_shadow_host_config(
        expected_release_source_sha=_SHA,
        candidate_env_path=candidate,
        paths=setup["paths"],
        runtime_executable=setup["runtime"],
        service_uid=_UID,
        service_gid=_GID,
    )
    assert again["state"] == "CONFIG_ALREADY_INSTALLED"

    setup["config"].chmod(0o600)
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="metadata",
    ):
        host_prepare.preflight_fast_paper_shadow_host_config(
            expected_release_source_sha=_SHA,
            candidate_env_path=candidate,
            paths=setup["paths"],
            runtime_executable=setup["runtime"],
            service_uid=_UID,
            service_gid=_GID,
        )


def test_state_provisioning_requires_exact_service_identity_and_reuses_provisioner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    monkeypatch.setattr(
        host_prepare,
        "load_fast_paper_shadow_provision_config",
        _fake_provision_config,
    )
    env = _environment()
    setup["config"].write_text(
        host_prepare.encode_fast_paper_shadow_host_environment(env),
        encoding="utf-8",
    )
    setup["config"].chmod(0o640)

    monkeypatch.setattr(host_prepare.os, "geteuid", lambda: _UID + 1)
    monkeypatch.setattr(host_prepare.os, "getegid", lambda: _GID)
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="service identity",
    ):
        host_prepare.provision_fast_paper_shadow_host_state(
            expected_release_source_sha=_SHA,
            paths=setup["paths"],
            runtime_executable=setup["runtime"],
            service_uid=_UID,
            service_gid=_GID,
        )

    monkeypatch.setattr(host_prepare.os, "geteuid", lambda: _UID)
    captured: dict[str, object] = {}

    def provision(config):
        captured["config"] = config
        for path in (
            config.supervisor_config.decision_config.evidence_directory,
            config.supervisor_config.execution_config.source_directory,
            config.supervisor_config.buy_authority_source_directory,
            config.supervisor_config.quote_usd_source_directory,
            config.supervisor_config.reduction_source_directory,
            config.supervisor_config.pending_buy_retry_source_directory,
        ):
            mapped = setup["shadow_root"] / path.name
            path = mapped
            path.mkdir(exist_ok=True)
            path.chmod(0o700)
        ledger = setup["shadow_root"] / "ledger.sqlite3"
        ledger.write_bytes(b"sqlite")
        ledger.chmod(0o600)
        return SimpleNamespace(
            created=True,
            supervisor_bootstrap=SimpleNamespace(
                execution_bootstrap=SimpleNamespace(
                    binding=SimpleNamespace(
                        run_id="shadow-run-prod-1",
                        binding_fingerprint_sha256="b" * 64,
                    ),
                    checkpoint=SimpleNamespace(sequence=0),
                )
            ),
        )

    monkeypatch.setattr(
        host_prepare,
        "provision_fast_paper_shadow",
        provision,
    )
    monkeypatch.setattr(
        host_prepare,
        "_state_paths_from_config",
        lambda _config: (
            (
                setup["shadow_root"] / "decision",
                setup["shadow_root"] / "execution-sources",
                setup["shadow_root"] / "buy-authority-sources",
                setup["shadow_root"] / "quote-usd-sources",
                setup["shadow_root"] / "reduction-sources",
                setup["shadow_root"] / "pending-buy-retry-sources",
            ),
            setup["shadow_root"] / "ledger.sqlite3",
        ),
    )

    result = host_prepare.provision_fast_paper_shadow_host_state(
        expected_release_source_sha=_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime"],
        service_uid=_UID,
        service_gid=_GID,
    )
    assert result["state"] == "STATE_CREATED"
    assert captured["config"] is not None
    assert result["service_start_authority"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"


def test_host_preflight_verifies_authority_state_and_stays_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _layout(tmp_path, monkeypatch)
    monkeypatch.setattr(
        host_prepare,
        "load_fast_paper_shadow_provision_config",
        _fake_provision_config,
    )
    env = _environment()
    setup["config"].write_text(
        host_prepare.encode_fast_paper_shadow_host_environment(env),
        encoding="utf-8",
    )
    setup["config"].chmod(0o640)

    authority_files = []
    for name in (
        "fast-paper-runtime-manifest.json",
        "fast-paper-shadow-service-policy.json",
        "fast-paper-shadow-execution-policy.json",
        "fast-paper-shadow-buy-writer-policy.json",
    ):
        path = setup["config"].parent / name
        path.write_text("{}\n", encoding="utf-8")
        path.chmod(0o640)
        authority_files.append(path)

    state_dirs = []
    for name in (
        "decision",
        "execution-sources",
        "buy-authority-sources",
        "quote-usd-sources",
        "reduction-sources",
        "pending-buy-retry-sources",
    ):
        path = setup["shadow_root"] / name
        path.mkdir()
        path.chmod(0o700)
        state_dirs.append(path)
    ledger = setup["shadow_root"] / "ledger.sqlite3"
    ledger.write_bytes(b"sqlite")
    ledger.chmod(0o600)

    monkeypatch.setattr(
        host_prepare,
        "_authority_paths_from_config",
        lambda _config: tuple(authority_files),
    )
    monkeypatch.setattr(
        host_prepare,
        "_state_paths_from_config",
        lambda _config: (tuple(state_dirs), ledger),
    )
    monkeypatch.setattr(
        host_prepare,
        "bootstrap_fast_paper_shadow_supervisor",
        lambda _config: SimpleNamespace(
            decision_bootstrap=SimpleNamespace(
                manifest=SimpleNamespace(
                    manifest_fingerprint_sha256="c" * 64,
                )
            ),
            execution_bootstrap=SimpleNamespace(
                binding=SimpleNamespace(run_id="shadow-run-prod-1"),
                checkpoint=SimpleNamespace(sequence=0),
            ),
        ),
    )

    receipt = host_prepare.preflight_fast_paper_shadow_host(
        expected_release_source_sha=_SHA,
        paths=setup["paths"],
        runtime_executable=setup["runtime"],
        service_uid=_UID,
        service_gid=_GID,
    )
    assert receipt["state"] == "READY_FOR_DORMANT_SYSTEMD_LOAD_REVIEW"
    assert receipt["daemon_reload_authority"] == "NOT_GRANTED"
    assert receipt["service_start_authority"] == "NOT_GRANTED"
    assert receipt["paper_cutover_authority"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"

    ledger.chmod(0o644)
    with pytest.raises(
        host_prepare.FastPaperShadowHostPrepareError,
        match="state metadata",
    ):
        host_prepare.preflight_fast_paper_shadow_host(
            expected_release_source_sha=_SHA,
            paths=setup["paths"],
            runtime_executable=setup["runtime"],
            service_uid=_UID,
            service_gid=_GID,
        )


def test_host_prepare_authority_firewall_and_packaging() -> None:
    source = (
        _REPO_ROOT
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_paper_shadow_host_prepare.py"
    ).read_text(encoding="utf-8")
    pyproject = _PYPROJECT.read_text(encoding="utf-8")
    target = _TARGET.read_text(encoding="utf-8")
    release_manager = _RELEASE_MANAGER.read_text(encoding="utf-8")

    for forbidden in (
        "subprocess",
        "systemctl",
        "daemon-reload",
        " enable ",
        " start ",
        " restart ",
        " stop ",
        "shreks_brain.scoring",
        "score_candidate",
        "requests.",
        "httpx",
        "aiohttp",
        "wallet",
        "private_key",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    assert "provision_fast_paper_shadow" in source
    assert (
        'shreks-fast-paper-shadow-host-prepare = '
        '"shreks_brain.fast_paper_shadow_host_prepare:main"'
    ) in pyproject
    assert "shreks-fast-paper-shadow.service" not in target
    assert "shreks-fast-paper-shadow.service" not in release_manager
