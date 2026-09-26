from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
import shreks_brain.fast_paper_runtime.shadow_service as service

from test_fast_paper_shadow_service import (
    _config,
    _policy_document,
)


def _cycle_fixture(monkeypatch, tmp_path: Path):
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
        _read_policy,
        **_kwargs,
    ):
        captured["position"] = position
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


def test_shadow_service_cycle_accepts_explicit_open_posture(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, record, captured = _cycle_fixture(
        monkeypatch,
        tmp_path,
    )
    calls: list[object] = []
    open_position = FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=0.5,
    )

    updated, processed = service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
        position_resolver=lambda supplied: (
            calls.append(supplied) or open_position
        ),
    )

    assert processed == 1
    assert calls == [record]
    assert captured["position"] == open_position
    assert updated.state is not bootstrap.state


def test_shadow_service_cycle_rejects_invalid_explicit_posture_before_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, _captured = _cycle_fixture(
        monkeypatch,
        tmp_path,
    )
    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid posture must fail before quote-cycle resolution"
        ),
    )
    monkeypatch.setattr(
        service,
        "run_fast_paper_shadow_batch",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid posture must fail before decision commit"
        ),
    )

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="cycle failed closed|posture|position",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
            position_resolver=lambda _record: object(),
        )


def test_shadow_service_cycle_wraps_posture_resolver_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, bootstrap, _record, _captured = _cycle_fixture(
        monkeypatch,
        tmp_path,
    )

    def fail(_record):
        raise RuntimeError("posture source unavailable")

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="posture|cycle failed closed",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
            position_resolver=fail,
        )


def test_shadow_service_posture_hook_adds_no_ledger_or_execution_authority() -> None:
    source = Path(service.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "load_latest_fast_paper_shadow_ledger_checkpoint",
        "load_latest_fast_paper_shadow_runtime_state",
        "execute_fast_paper_shadow_decision",
        "commit_fast_paper_shadow_transition_atomically",
        "shreks_brain.scoring",
        "score_candidate",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
