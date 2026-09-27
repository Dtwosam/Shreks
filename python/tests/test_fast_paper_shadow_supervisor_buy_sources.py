from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_provision as provision
import shreks_brain.fast_paper_runtime.shadow_supervisor as supervisor
from shreks_brain.fast_paper_runtime.shadow_service import (
    FastPaperShadowServiceConfig,
)
from shreks_brain.fast_paper_runtime.shadow_service_coordinator import (
    FastPaperShadowServiceCoordinatorResult,
)
from shreks_brain.fast_paper_runtime.shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionConfig,
)

from test_fast_paper_shadow_supervisor import _buy_writer_policy


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = (
    _REPO_ROOT
    / "deploy"
    / "systemd"
    / "shreks-fast-paper-shadow.env.example"
)


def _decision_config(tmp_path: Path) -> FastPaperShadowServiceConfig:
    return FastPaperShadowServiceConfig(
        manifest_path=(tmp_path / "manifest.json").resolve(),
        policy_path=(tmp_path / "service-policy.json").resolve(),
        evidence_directory=(tmp_path / "decision").resolve(),
        cycle_interval_seconds=2.0,
        maximum_decisions=1,
    )


def _execution_config(tmp_path: Path) -> FastPaperShadowServiceExecutionConfig:
    return FastPaperShadowServiceExecutionConfig(
        execution_policy_path=(tmp_path / "execution-policy.json").resolve(),
        source_directory=(tmp_path / "execution-sources").resolve(),
        ledger_database_path=(tmp_path / "ledger.sqlite3").resolve(),
        run_id="shadow-buy-source-run",
    )


def _config(tmp_path: Path):
    return supervisor.FastPaperShadowSupervisorConfig(
        decision_config=_decision_config(tmp_path),
        execution_config=_execution_config(tmp_path),
        buy_authority_source_directory=(
            tmp_path / "buy-authority-sources"
        ).resolve(),
        quote_usd_source_directory=(
            tmp_path / "quote-usd-sources"
        ).resolve(),
        reduction_source_directory=(tmp_path / "reduction-sources").resolve(),
        pending_buy_retry_source_directory=(
            tmp_path / "retry-sources"
        ).resolve(),
        buy_writer_policy_path=(tmp_path / "buy-writer-policy.json").resolve(),
    )


def _decision_bootstrap():
    return SimpleNamespace(
        manifest=SimpleNamespace(
            manifest_fingerprint_sha256="a" * 64,
            champion_version="champion-v1",
            champion_fingerprint_sha256="b" * 64,
            action_policy=SimpleNamespace(version=7),
        ),
        state=SimpleNamespace(cursor=None),
    )


def _execution_bootstrap():
    return SimpleNamespace(
        checkpoint=SimpleNamespace(sequence=0),
        runtime_state=SimpleNamespace(
            last_processed_source_sequence=None,
            pending_buy=None,
            market_positions=(),
        ),
    )


def test_supervisor_config_loader_requires_buy_authority_source_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    decision = _decision_config(tmp_path)
    execution = _execution_config(tmp_path)
    buy_authority = (tmp_path / "buy-authority-sources").resolve()
    quote_usd = (tmp_path / "quote-usd-sources").resolve()
    reduction = (tmp_path / "reduction-sources").resolve()
    retry = (tmp_path / "retry-sources").resolve()
    buy_writer_policy_path = (tmp_path / "buy-writer-policy.json").resolve()

    config = _config(tmp_path)
    assert config.buy_authority_source_directory == buy_authority

    env = {
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY": str(
            buy_authority
        ),
        "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY": str(quote_usd),
        "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY": str(reduction),
        "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY": str(
            retry
        ),
        "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH": str(
            buy_writer_policy_path
        ),
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

    loaded = supervisor.load_fast_paper_shadow_supervisor_config(env)
    assert loaded.buy_authority_source_directory == buy_authority


def test_supervisor_orders_skip_buy_open_then_coordinator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for name in (
        "decision",
        "execution-sources",
        "buy-authority-sources",
        "quote-usd-sources",
        "reduction-sources",
        "retry-sources",
    ):
        (tmp_path / name).mkdir()
    config = _config(tmp_path)
    before = supervisor.FastPaperShadowSupervisorBootstrap(
        decision_bootstrap=_decision_bootstrap(),
        execution_bootstrap=_execution_bootstrap(),
        buy_writer_policy=_buy_writer_policy(tmp_path),
    )
    events: list[object] = []

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_authority_writer_cycle",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )
    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_skip_source_publisher_cycle",
        lambda manifest, execution_bootstrap, *, decision_evidence_directory: (
            events.append(
                (
                    "skip",
                    manifest,
                    execution_bootstrap,
                    decision_evidence_directory,
                )
            )
            or 0
        ),
    )

    def publish_buy(
        manifest,
        execution_bootstrap,
        *,
        decision_evidence_directory,
        buy_authority_source_directory,
        quote_usd_source_directory,
    ):
        events.append(
            (
                "buy",
                manifest,
                execution_bootstrap,
                decision_evidence_directory,
                buy_authority_source_directory,
                quote_usd_source_directory,
            )
        )
        return 0

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        publish_buy,
        raising=False,
    )

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_open_source_publisher_cycle",
        lambda manifest, execution_bootstrap, *,
        decision_evidence_directory, quote_usd_source_directory: (
            events.append(
                (
                    "open",
                    manifest,
                    execution_bootstrap,
                    decision_evidence_directory,
                    quote_usd_source_directory,
                )
            )
            or 0
        ),
    )

    def coordinated(
        decision_bootstrap,
        decision_config,
        execution_config,
        **kwargs,
    ):
        events.append(("coordinator", kwargs))
        return FastPaperShadowServiceCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=before.execution_bootstrap,
            decisions_produced=0,
            executions_committed=0,
        )

    monkeypatch.setattr(
        supervisor,
        "run_fast_paper_shadow_service_coordinated_cycle",
        coordinated,
    )

    supervisor.run_fast_paper_shadow_supervisor_cycle(
        before,
        config,
        clock_unix_ms=lambda: 25_000,
    )

    assert [event[0] for event in events] == [
        "skip",
        "buy",
        "open",
        "coordinator",
    ]
    buy_event = events[1]
    assert buy_event[1] is before.decision_bootstrap.manifest
    assert buy_event[2] is before.execution_bootstrap
    assert buy_event[3] == config.decision_config.evidence_directory
    assert buy_event[4] == config.buy_authority_source_directory
    assert buy_event[5] == config.quote_usd_source_directory


def test_supervisor_provisioner_and_env_include_buy_authority_root_without_derivation() -> None:
    supervisor_source = Path(supervisor.__file__).read_text(encoding="utf-8")
    provision_source = Path(provision.__file__).read_text(encoding="utf-8")
    env = _ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "run_fast_paper_shadow_buy_source_publisher_cycle" in supervisor_source
    assert "buy_authority_source_directory" in supervisor_source
    assert "buy_authority_source_directory" in provision_source
    assert (
        "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY="
        in env
    )

    for payload in (supervisor_source, provision_source):
        for forbidden in (
            "FastCampaignPaperEntryAuthority(",
            "RiskContext(",
            "MarketRegime.",
            "derive_paper_risk_accounting_facts",
            "ObserverMarketStore",
            "quote_asset_usd_evidence",
            "requests.",
            "httpx",
            "aiohttp",
            "sign_transaction",
            "submit_transaction",
            "RuntimeMode.LIVE",
            "shreks_brain.scoring",
            "score_candidate",
        ):
            assert forbidden not in payload
