from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime.persisted_quotes import (
    FastPaperShadowReductionRead,
)
import shreks_brain.fast_paper_runtime.shadow_service as service

from test_fast_paper_shadow_service import _config, _policy_document


def _fixture(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    policy = service.FastPaperShadowServicePolicy(**_policy_document())
    manifest = SimpleNamespace(
        observer_database_path=str(tmp_path / "observer.sqlite3"),
        quote_provider="jupiter",
    )
    state = object()
    next_state = object()
    record = SimpleNamespace(
        decision_observed_at_unix_ms=1_000,
        mint="Mint111",
        quote_mint="Quote111",
    )
    bootstrap = service.FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=policy,
        state=state,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        service,
        "_validate_service_paths",
        lambda _config, _manifest: None,
    )
    monkeypatch.setattr(
        service,
        "fetch_fast_paper_runtime_feature_batch",
        lambda *_args, **_kwargs: SimpleNamespace(
            records=(record,),
            next_state=next_state,
        ),
    )
    monkeypatch.setattr(
        service,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: 17,
    )

    def resolve(
        _manifest,
        _record,
        position,
        read_policy,
        **_kwargs,
    ):
        captured["position"] = position
        captured["read_policy"] = read_policy
        return object()

    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        resolve,
    )
    monkeypatch.setattr(
        service,
        "run_fast_paper_shadow_batch",
        lambda *_args, **_kwargs: next_state,
    )
    return config, bootstrap, record, captured


def _read(target: float, amount: int) -> FastPaperShadowReductionRead:
    return FastPaperShadowReductionRead(
        target_exposure_fraction=target,
        input_amount_raw=amount,
    )


def test_shadow_service_cycle_passes_explicit_open_reduction_reads(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, record, captured = _fixture(monkeypatch, tmp_path)
    position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )
    reads = (
        _read(0.25, 10_000_000),
        _read(0.50, 5_000_000),
    )
    calls: list[tuple[object, object]] = []

    updated, processed = service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
        position_resolver=lambda _record: position,
        reduction_read_resolver=lambda supplied_record, supplied_position: (
            calls.append((supplied_record, supplied_position)) or reads
        ),
    )

    assert processed == 1
    assert updated.state is not bootstrap.state
    assert calls == [(record, position)]
    assert captured["position"] == position
    assert captured["read_policy"].reduction_reads == reads


def test_shadow_service_cycle_default_reduction_reads_remain_empty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, captured = _fixture(monkeypatch, tmp_path)

    service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
    )

    assert captured["read_policy"].reduction_reads == ()


def test_shadow_service_cycle_rejects_reduction_reads_for_flat_posture(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, _captured = _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: pytest.fail(
            "FLAT reduction reads must fail before quote resolution"
        ),
    )

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="cycle failed closed|reduction",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
            reduction_read_resolver=lambda *_args: (
                _read(0.25, 10_000_000),
            ),
        )


def test_shadow_service_cycle_rejects_malformed_reduction_read_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, _captured = _fixture(monkeypatch, tmp_path)
    position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="cycle failed closed|reduction",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
            position_resolver=lambda _record: position,
            reduction_read_resolver=lambda *_args: (object(),),
        )


def test_shadow_service_cycle_wraps_reduction_read_resolver_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, _captured = _fixture(monkeypatch, tmp_path)
    position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.75,
    )

    def fail(*_args):
        raise RuntimeError("reduction authority unavailable")

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="reduction|cycle failed closed",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
            position_resolver=lambda _record: position,
            reduction_read_resolver=fail,
        )


def test_shadow_service_reduction_hook_does_not_derive_raw_units() -> None:
    source = Path(service.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "decimal_quantity_to_raw",
        "counterfactual_base_quantity",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
