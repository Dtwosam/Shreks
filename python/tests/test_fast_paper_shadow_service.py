from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_runtime.shadow_service as service


def _policy_document() -> dict[str, object]:
    return {
        "schema_name": service.FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME,
        "schema_version": service.FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION,
        "route_evidence_version": "observer-paper-quote-v1",
        "probe_policy_version": "probe-v1",
        "taker": "Taker111",
        "slippage_bps": 75,
        "entry_input_amount_raw": 100_000,
        "exit_input_amount_raw": 200_000,
        "max_quote_age_ms": 5_000,
        "max_exposure_fraction": 0.5,
    }


def _write_policy(path: Path, document: dict[str, object] | None = None) -> None:
    value = _policy_document() if document is None else document
    path.write_text(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _config(tmp_path: Path) -> service.FastPaperShadowServiceConfig:
    root = tmp_path / "shadow"
    root.mkdir()
    return service.FastPaperShadowServiceConfig(
        manifest_path=tmp_path / "manifest.json",
        policy_path=tmp_path / "policy.json",
        evidence_directory=root,
        cycle_interval_seconds=1.0,
        maximum_decisions=8,
    )


def test_shadow_service_policy_is_canonical_and_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    _write_policy(path)

    policy = service.read_fast_paper_shadow_service_policy(path)

    assert policy.route_evidence_version == "observer-paper-quote-v1"
    assert policy.max_exposure_fraction == 0.5

    unknown = _policy_document()
    unknown["price"] = 1.0
    _write_policy(path, unknown)
    with pytest.raises(ValueError, match="unknown or missing"):
        service.read_fast_paper_shadow_service_policy(path)


def test_shadow_service_cycle_composes_feed_quotes_and_restart_safe_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    policy = service.FastPaperShadowServicePolicy(**_policy_document())
    manifest = SimpleNamespace(
        observer_database_path=str(tmp_path / "observer.sqlite3"),
    )
    state = object()
    next_state = object()
    record = SimpleNamespace(
        decision_observed_at_unix_ms=1_000,
        mint="Mint111",
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
        lambda _manifest, supplied_state, maximum_decisions: (
            captured.update(
                fetch_state=supplied_state,
                maximum_decisions=maximum_decisions,
            )
            or SimpleNamespace(
                records=(record,),
                next_state=next_state,
            )
        ),
    )
    def candidate_id(_path, **identity):
        captured.update(candidate_identity=identity)
        return 17

    monkeypatch.setattr(
        service,
        "_resolve_candidate_id",
        candidate_id,
    )

    cycle_input = object()

    def resolve(
        _manifest,
        supplied_record,
        position,
        read_policy,
        *,
        evaluated_at_unix_ms,
        max_exposure_fraction,
        force_sell,
    ):
        captured.update(
            record=supplied_record,
            position=position,
            read_policy=read_policy,
            evaluated_at_unix_ms=evaluated_at_unix_ms,
            max_exposure_fraction=max_exposure_fraction,
            force_sell=force_sell,
        )
        return cycle_input

    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        resolve,
    )

    def commit(
        _manifest,
        supplied_state,
        inputs,
        *,
        evidence_directory,
    ):
        captured.update(
            commit_state=supplied_state,
            inputs=inputs,
            evidence_directory=evidence_directory,
        )
        return next_state

    monkeypatch.setattr(
        service,
        "run_fast_paper_shadow_batch",
        commit,
    )

    updated, processed = service.run_fast_paper_shadow_service_cycle(
        bootstrap,
        config,
        clock_unix_ms=lambda: 1_050,
    )

    assert processed == 1
    assert updated.state is next_state
    assert captured["fetch_state"] is state
    assert captured["maximum_decisions"] == 8
    identity = captured["candidate_identity"]
    assert identity["mint"] == "Mint111"
    assert identity["provider"] is manifest.quote_provider
    assert identity["probe_policy_version"] == "probe-v1"
    assert identity["entry_input_amount_raw"] == 100_000
    assert identity["decision_observed_at_unix_ms"] == 1_000
    assert identity["evaluated_at_unix_ms"] == 1_050
    assert captured["position"].kind == "FLAT"
    read_policy = captured["read_policy"]
    assert read_policy.candidate_id == 17
    assert read_policy.reduction_reads == ()
    assert captured["evaluated_at_unix_ms"] == 1_050
    assert captured["max_exposure_fraction"] == 0.5
    assert captured["force_sell"] is False
    assert captured["commit_state"] is state
    assert captured["inputs"] == (cycle_input,)
    assert captured["evidence_directory"] == config.evidence_directory


def test_shadow_service_failed_resolution_does_not_commit_row(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    policy = service.FastPaperShadowServicePolicy(**_policy_document())
    manifest = SimpleNamespace(
        observer_database_path=str(tmp_path / "observer.sqlite3"),
    )
    state = object()
    record = SimpleNamespace(
        decision_observed_at_unix_ms=1_000,
        mint="Mint111",
    )
    bootstrap = service.FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=policy,
        state=state,
    )

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
            next_state=object(),
        ),
    )
    monkeypatch.setattr(
        service,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: 17,
    )
    monkeypatch.setattr(
        service,
        "resolve_fast_paper_shadow_cycle_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("missing persisted quote")
        ),
    )
    monkeypatch.setattr(
        service,
        "run_fast_paper_shadow_batch",
        lambda *_args, **_kwargs: pytest.fail(
            "failed row must not advance through the commit boundary"
        ),
    )

    with pytest.raises(
        service.FastPaperShadowServiceError,
        match="cycle failed closed",
    ):
        service.run_fast_paper_shadow_service_cycle(
            bootstrap,
            config,
            clock_unix_ms=lambda: 1_050,
        )
