from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_buy_writer_policy as writer_policy
import shreks_brain.fast_paper_runtime.shadow_supervisor as supervisor
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_NAME,
    FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_VERSION,
    FastPaperShadowBuyWriterPolicy,
    FastPaperShadowQuoteReadPolicy,
    build_fast_paper_shadow_buy_writer_policy,
    read_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
    write_fast_paper_shadow_buy_writer_policy,
)
from shreks_brain.fast_paper_runtime.shadow_service_coordinator import (
    FastPaperShadowServiceCoordinatorResult,
)
from shreks_brain.risk_control import initialize_operator_risk_control_state

from test_fast_paper_shadow_buy_authority_evidence_adapter import (
    _execution_policy as _economics_policy,
    _market_policy,
    _regime_policy,
    _regime_read_policy,
    _safety_policy,
    _safety_probe,
)
from test_fast_paper_shadow_buy_authority_writer import _service_policy
from test_fast_paper_shadow_decision import _executable, _manifest, _record
from test_fast_paper_shadow_supervisor import (
    _decision_config,
    _execution_config,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = (
    _REPO_ROOT
    / "deploy"
    / "systemd"
    / "shreks-fast-paper-shadow.env.example"
)


def _quote_policy(manifest):
    policy = _service_policy(manifest)
    return FastPaperShadowQuoteReadPolicy(
        version=policy.route_evidence_version,
        candidate_id=7,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        exit_input_amount_raw=policy.exit_input_amount_raw,
        max_quote_age_ms=policy.max_quote_age_ms,
    )


def _policy_fixture(tmp_path: Path):
    manifest = _manifest(tmp_path)
    service = _service_policy(manifest)
    quote = _quote_policy(manifest)
    operator = tmp_path / "risk" / "operator-control.json"
    operator.parent.mkdir()
    initialize_operator_risk_control_state(
        operator,
        observed_at_unix_ms=0,
    )
    authority_binary = _executable(
        tmp_path / "shreks-fast-entry-authority"
    )
    binary_sha = hashlib.sha256(authority_binary.read_bytes()).hexdigest()
    policy = build_fast_paper_shadow_buy_writer_policy(
        market_read_policy=_market_policy(),
        regime_read_policy=_regime_read_policy(manifest, quote),
        regime_policy=_regime_policy(),
        safety_policy=_safety_policy(),
        safety_probe_identity=_safety_probe(manifest, quote),
        execution_economics_policies=(
            _economics_policy(_record()),
        ),
        operator_risk_control_path=operator,
        entry_authority_binary_path=authority_binary,
        entry_authority_binary_sha256=binary_sha,
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )
    return manifest, service, policy, operator, authority_binary


def _supervisor_config(tmp_path: Path, policy_path: Path):
    return supervisor.FastPaperShadowSupervisorConfig(
        decision_config=_decision_config(tmp_path),
        execution_config=_execution_config(tmp_path),
        buy_authority_source_directory=(
            tmp_path / "buy-authority-sources"
        ).resolve(),
        quote_usd_source_directory=(
            tmp_path / "quote-usd-sources"
        ).resolve(),
        reduction_source_directory=(
            tmp_path / "reduction-sources"
        ).resolve(),
        pending_buy_retry_source_directory=(
            tmp_path / "retry-sources"
        ).resolve(),
        buy_writer_policy_path=policy_path.resolve(),
    )


def test_buy_writer_policy_round_trips_canonically_and_is_private(
    tmp_path: Path,
) -> None:
    manifest, service, policy, _operator, _binary = _policy_fixture(
        tmp_path
    )
    assert type(policy) is FastPaperShadowBuyWriterPolicy
    assert (
        policy.schema_name
        == FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_NAME
    )
    assert (
        policy.schema_version
        == FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_VERSION
    )
    assert len(policy.policy_fingerprint_sha256) == 64

    destination = tmp_path / "buy-writer-policy.json"
    write_fast_paper_shadow_buy_writer_policy(policy, destination)
    restored = read_fast_paper_shadow_buy_writer_policy(destination)

    assert restored == policy
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.read_text(encoding="utf-8").endswith("\n")
    verify_fast_paper_shadow_buy_writer_policy_bindings(
        manifest,
        service,
        restored,
    )
    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_buy_writer_policy(policy, destination)


def test_buy_writer_policy_rejects_tamper_symlink_and_runtime_drift(
    tmp_path: Path,
) -> None:
    manifest, service, policy, _operator, binary = _policy_fixture(
        tmp_path
    )
    destination = tmp_path / "buy-writer-policy.json"
    write_fast_paper_shadow_buy_writer_policy(policy, destination)

    document = json.loads(destination.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    destination.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing|canonical|fingerprint"):
        read_fast_paper_shadow_buy_writer_policy(destination)

    destination.unlink()
    write_fast_paper_shadow_buy_writer_policy(policy, destination)
    real = destination.with_suffix(".real")
    destination.rename(real)
    destination.symlink_to(real.name)
    with pytest.raises(ValueError, match="symlink|regular"):
        read_fast_paper_shadow_buy_writer_policy(destination)

    destination.unlink()
    real.rename(destination)
    with pytest.raises(ValueError, match="regime|ENTRY|identity|amount"):
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            manifest,
            replace(
                service,
                entry_input_amount_raw=service.entry_input_amount_raw + 1,
            ),
            policy,
        )

    binary.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="binary|SHA|digest"):
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            manifest,
            service,
            policy,
        )


def test_supervisor_config_requires_buy_writer_policy_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision = _decision_config(tmp_path)
    execution = _execution_config(tmp_path)
    policy_path = (tmp_path / "buy-writer-policy.json").resolve()
    env = {
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY": str(
            (tmp_path / "buy-authority-sources").resolve()
        ),
        "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY": str(
            (tmp_path / "quote-usd-sources").resolve()
        ),
        "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY": str(
            (tmp_path / "reduction-sources").resolve()
        ),
        "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY": str(
            (tmp_path / "retry-sources").resolve()
        ),
        "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH": str(policy_path),
    }
    monkeypatch.setattr(
        supervisor,
        "load_fast_paper_shadow_service_config",
        lambda _env: decision,
    )
    monkeypatch.setattr(
        supervisor,
        "load_fast_paper_shadow_service_execution_config",
        lambda _env: execution,
    )

    config = supervisor.load_fast_paper_shadow_supervisor_config(env)
    assert config.buy_writer_policy_path == policy_path

    missing = dict(env)
    missing.pop("SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH")
    with pytest.raises(
        supervisor.FastPaperShadowSupervisorError,
        match="BUY_WRITER_POLICY_PATH",
    ):
        supervisor.load_fast_paper_shadow_supervisor_config(missing)


def test_supervisor_bootstrap_authenticates_and_retains_buy_writer_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, service, policy, _operator, _binary = _policy_fixture(
        tmp_path
    )
    policy_path = tmp_path / "buy-writer-policy.json"
    for name in (
        "decision",
        "execution-sources",
        "buy-authority-sources",
        "quote-usd-sources",
        "reduction-sources",
        "retry-sources",
    ):
        (tmp_path / name).mkdir(exist_ok=True)
    config = _supervisor_config(tmp_path, policy_path)
    decision = SimpleNamespace(manifest=manifest, policy=service)
    execution = SimpleNamespace()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        supervisor,
        "bootstrap_fast_paper_shadow_service",
        lambda supplied: (
            captured.update(decision_config=supplied) or decision
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "bootstrap_fast_paper_shadow_service_execution",
        lambda supplied_manifest, supplied: (
            captured.update(
                manifest=supplied_manifest,
                execution_config=supplied,
            )
            or execution
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "read_fast_paper_shadow_buy_writer_policy",
        lambda supplied: (
            captured.update(policy_path=supplied) or policy
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "verify_fast_paper_shadow_buy_writer_policy_bindings",
        lambda supplied_manifest, supplied_service, supplied_policy: (
            captured.update(
                verified_manifest=supplied_manifest,
                verified_service=supplied_service,
                verified_policy=supplied_policy,
            )
        ),
    )

    bootstrap = supervisor.bootstrap_fast_paper_shadow_supervisor(config)

    assert bootstrap.buy_writer_policy is policy
    assert captured["policy_path"] == policy_path.resolve()
    assert captured["verified_manifest"] is manifest
    assert captured["verified_service"] is service
    assert captured["verified_policy"] is policy


def test_supervisor_orders_buy_writer_before_buy_source_and_forwards_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, service, policy, _operator, _binary = _policy_fixture(
        tmp_path
    )
    policy_path = tmp_path / "buy-writer-policy.json"
    for name in (
        "decision",
        "execution-sources",
        "buy-authority-sources",
        "quote-usd-sources",
        "reduction-sources",
        "retry-sources",
    ):
        (tmp_path / name).mkdir(exist_ok=True)
    config = _supervisor_config(tmp_path, policy_path)
    decision = SimpleNamespace(manifest=manifest, policy=service)
    execution = SimpleNamespace()
    before = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=decision,
        execution_bootstrap=execution,
        buy_writer_policy=policy,
    )
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_skip_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("skip", None)) or 0,
    )

    def write_authority(*args, **kwargs):
        events.append(("writer", (args, kwargs)))
        return 0

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_authority_writer_cycle",
        write_authority,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("buy", None)) or 0,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_open_source_publisher_cycle",
        lambda *_args, **_kwargs: events.append(("open", None)) or 0,
    )

    def coordinated(decision_bootstrap, *_args, **_kwargs):
        events.append(("coordinator", None))
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=execution,
            decisions_produced=0,
            executions_committed=0,
        )

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        coordinated,
    )

    updated, _produced, _committed = (
        supervisor.run_fast_paper_shadow_supervisor_cycle(
            before,
            config,
            clock_unix_ms=lambda: 25_000,
        )
    )

    assert [name for name, _value in events] == [
        "skip",
        "writer",
        "buy",
        "open",
        "coordinator",
    ]
    writer_args, writer_kwargs = events[1][1]
    assert writer_args[0] is decision
    assert writer_args[1] is execution
    assert writer_kwargs["market_read_policy"] is policy.market_read_policy
    assert writer_kwargs["regime_read_policy"] is policy.regime_read_policy
    assert writer_kwargs["regime_policy"] is policy.regime_policy
    assert writer_kwargs["safety_policy"] is policy.safety_policy
    assert (
        writer_kwargs["safety_probe_identity"]
        is policy.safety_probe_identity
    )
    assert (
        writer_kwargs["execution_economics_policies"]
        is policy.execution_economics_policies
    )
    assert writer_kwargs["operator_risk_control_path"] == (
        policy.operator_risk_control_path
    )
    assert writer_kwargs["entry_authority_binary_path"] == (
        policy.entry_authority_binary_path
    )
    assert writer_kwargs["day_started_at_unix_ms"] == (
        policy.day_started_at_unix_ms
    )
    assert writer_kwargs["data_healthy"] is policy.data_healthy
    assert writer_kwargs["execution_healthy"] is policy.execution_healthy
    assert writer_kwargs["global_risk_halt"] is policy.global_risk_halt
    assert updated.buy_writer_policy is policy


def test_packaged_env_and_sources_remain_score_free() -> None:
    env = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH=" in env

    policy_source = Path(writer_policy.__file__).read_text(encoding="utf-8")
    supervisor_source = Path(supervisor.__file__).read_text(encoding="utf-8")
    for payload in (policy_source, supervisor_source):
        for forbidden in (
            "shreks_brain.scoring",
            "ScorePolicy",
            "score_candidate",
            "required_score_threshold",
            "shreks_brain.decision",
            "decide_entry",
            "requests.",
            "httpx",
            "aiohttp",
            "sign_transaction",
            "submit_transaction",
            "RuntimeMode.LIVE",
        ):
            assert forbidden not in payload
