from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_buy_authority_writer as writer
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FastPaperShadowQuoteReadPolicy,
    FastPaperShadowServiceExecutionBootstrap,
    build_fast_paper_runtime_state,
    build_fast_paper_shadow_buy_authority_source_record,
    run_fast_paper_shadow_buy_authority_writer_cycle,
)
from shreks_brain.fast_paper_runtime.shadow import (
    write_fast_paper_shadow_decision_evidence,
)
from shreks_brain.fast_paper_runtime.shadow_service import (
    FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME,
    FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION,
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServicePolicy,
)
from shreks_brain.regime import MarketRegime

from test_fast_paper_shadow_buy_authority_evidence_adapter import (
    _execution_policy as _economics_policy,
    _market_policy,
    _regime_policy,
    _regime_read_policy,
    _safety_policy,
    _safety_probe,
)
from test_fast_paper_shadow_decision import _record
from test_fast_paper_shadow_execution_input import _entry, _risk
from test_fast_paper_shadow_executor import (
    _evidence_for,
    _record_at,
    _runtime_fixture,
)


def _service_policy(manifest) -> FastPaperShadowServicePolicy:
    return FastPaperShadowServicePolicy(
        schema_name=FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_NAME,
        schema_version=FAST_PAPER_SHADOW_SERVICE_POLICY_SCHEMA_VERSION,
        route_evidence_version=manifest.route_evidence_version,
        probe_policy_version="probe-v2",
        taker="Taker111",
        slippage_bps=75,
        entry_input_amount_raw=1_000_000_000,
        exit_input_amount_raw=2_000_000,
        max_quote_age_ms=2_000,
        max_exposure_fraction=0.75,
    )


def _bootstraps(tmp_path: Path):
    manifest, binding, execution_policy, checkpoint, runtime_state = (
        _runtime_fixture(tmp_path)
    )
    decision = FastPaperShadowServiceBootstrap(
        manifest=manifest,
        policy=_service_policy(manifest),
        state=build_fast_paper_runtime_state(manifest, cursor=None),
    )
    execution_sources = tmp_path / "execution-sources"
    execution_sources.mkdir()
    execution = FastPaperShadowServiceExecutionBootstrap(
        binding=binding,
        execution_policy=execution_policy,
        checkpoint=checkpoint,
        runtime_state=runtime_state,
        source_directory=execution_sources.resolve(),
    )
    decisions = tmp_path / "decision-evidence"
    decisions.mkdir()
    authorities = tmp_path / "buy-authority-sources"
    authorities.mkdir()
    usd = tmp_path / "quote-usd-sources"
    usd.mkdir()
    return decision, execution, decisions, authorities, usd


def _evidence(
    monkeypatch,
    manifest,
    *,
    action: str,
    sequence: int,
):
    feature = _record_at(
        _record(),
        signature=f"buy-authority-writer-{sequence}",
        sequence=sequence,
        at=20_000 + sequence,
    )
    position = (
        FastCampaignDecisionPosition(kind="FLAT")
        if action in {"BUY", "SKIP"}
        else FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        )
    )
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action=action,
        position=position,
        evaluated_at=20_020 + sequence,
        entry_observed_at=20_010 + sequence,
        exit_observed_at=20_015 + sequence,
        reduction_observed_at=(
            20_016 + sequence if action == "REDUCE" else None
        ),
    )
    assert evidence.feature_record == feature
    return feature, evidence


def _persist_decision(directory: Path, evidence, suffix: str) -> Path:
    path = directory / (
        f"shadow-{evidence.source_sequence:020d}-{suffix}.json"
    )
    write_fast_paper_shadow_decision_evidence(evidence, path)
    return path


def _quote_policy(decision_bootstrap, *, candidate_id: int):
    policy = decision_bootstrap.policy
    return FastPaperShadowQuoteReadPolicy(
        version=policy.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        exit_input_amount_raw=policy.exit_input_amount_raw,
        max_quote_age_ms=policy.max_quote_age_ms,
    )


def _authority(decision_bootstrap, execution_bootstrap, evidence):
    feature = evidence.feature_record
    return build_fast_paper_shadow_buy_authority_source_record(
        decision_bootstrap.manifest,
        execution_bootstrap.binding,
        execution_bootstrap.execution_policy,
        execution_bootstrap.checkpoint,
        execution_bootstrap.runtime_state,
        evidence,
        _entry(feature),
        _risk(evidence.evaluated_at_unix_ms),
        MarketRegime.NORMAL,
        risk_day_started_at_unix_ms=0,
        source_observed_at_unix_ms=evidence.evaluated_at_unix_ms - 1,
        source_version="writer-fixture-v1",
        source_fingerprint_sha256="b" * 64,
    )


def _call(
    decision_bootstrap,
    execution_bootstrap,
    decisions,
    authorities,
    usd,
    *,
    operator_path: Path,
):
    expected_quote = _quote_policy(decision_bootstrap, candidate_id=7)
    manifest = decision_bootstrap.manifest
    return run_fast_paper_shadow_buy_authority_writer_cycle(
        decision_bootstrap,
        execution_bootstrap,
        decision_evidence_directory=decisions,
        buy_authority_source_directory=authorities,
        quote_usd_source_directory=usd,
        market_read_policy=_market_policy(),
        regime_read_policy=_regime_read_policy(
            manifest,
            expected_quote,
        ),
        regime_policy=_regime_policy(),
        safety_policy=_safety_policy(),
        safety_probe_identity=_safety_probe(
            manifest,
            expected_quote,
        ),
        execution_economics_policy=_economics_policy(
            _record()
        ),
        operator_risk_control_path=operator_path,
        entry_authority_binary_path=(
            operator_path.parent / "shreks-fast-entry-authority"
        ),
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )


def test_writer_uses_oldest_buy_embedded_feature_and_active_quote_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    feature, evidence = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action="BUY",
        sequence=1,
    )
    _persist_decision(decisions, evidence, "buy")
    (usd / f"{evidence.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}
    authority = _authority(
        decision_bootstrap,
        execution_bootstrap,
        evidence,
    )

    def resolve(path_value, **kwargs):
        captured["candidate_path"] = path_value
        captured["candidate_kwargs"] = kwargs
        return 7

    def produce(*args, **kwargs):
        captured["adapter_args"] = args
        captured["adapter_kwargs"] = kwargs
        return authority

    monkeypatch.setattr(writer, "_resolve_candidate_id", resolve)
    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        produce,
    )
    monkeypatch.setattr(
        writer,
        "write_fast_paper_shadow_buy_authority_source_record",
        lambda record, directory: captured.update(
            written_record=record,
            written_directory=directory,
        ),
    )

    assert _call(
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
        operator_path=tmp_path / "operator-control.json",
    ) == 1

    candidate = captured["candidate_kwargs"]
    assert captured["candidate_path"] == (
        decision_bootstrap.manifest.observer_database_path
    )
    assert candidate["mint"] == feature.mint
    assert candidate["quote_mint"] == feature.quote_mint
    assert candidate["decision_observed_at_unix_ms"] == (
        feature.decision_observed_at_unix_ms
    )
    assert candidate["evaluated_at_unix_ms"] == (
        evidence.evaluated_at_unix_ms
    )

    args = captured["adapter_args"]
    assert args[0] is decision_bootstrap.manifest
    assert args[1] == execution_bootstrap.binding
    assert args[2] == execution_bootstrap.execution_policy
    assert args[3] == execution_bootstrap.checkpoint
    assert args[4] == execution_bootstrap.runtime_state
    assert args[5] == evidence
    assert args[6] is args[5].feature_record
    assert args[6] == evidence.feature_record
    quote_policy = args[7]
    assert type(quote_policy) is FastPaperShadowQuoteReadPolicy
    assert quote_policy == _quote_policy(
        decision_bootstrap,
        candidate_id=7,
    )
    assert captured["written_record"] == authority
    assert captured["written_directory"] == authorities.resolve()


@pytest.mark.parametrize("action", ("SKIP", "HOLD", "REDUCE", "SELL"))
def test_writer_never_leapfrogs_oldest_non_buy(
    monkeypatch,
    tmp_path: Path,
    action: str,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    _feature1, oldest = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action=action,
        sequence=1,
    )
    _feature2, later = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action="BUY",
        sequence=2,
    )
    _persist_decision(decisions, oldest, "oldest")
    _persist_decision(decisions, later, "later-buy")
    (usd / f"{later.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        writer,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: pytest.fail(
            "writer must not resolve candidate past oldest non-BUY"
        ),
    )
    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        lambda *_args, **_kwargs: pytest.fail(
            "writer must not derive authority past oldest non-BUY"
        ),
    )

    assert _call(
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
        operator_path=tmp_path / "operator-control.json",
    ) == 0


def test_writer_waits_for_exact_quote_usd_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    _feature, evidence = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action="BUY",
        sequence=1,
    )
    _persist_decision(decisions, evidence, "buy")

    monkeypatch.setattr(
        writer,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: pytest.fail(
            "missing quote/USD must wait before candidate hydration"
        ),
    )
    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        lambda *_args, **_kwargs: pytest.fail(
            "missing quote/USD must not derive BUY authority"
        ),
    )

    assert _call(
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
        operator_path=tmp_path / "operator-control.json",
    ) == 0


def test_writer_exact_write_collision_is_restart_safe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    _feature, evidence = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action="BUY",
        sequence=1,
    )
    _persist_decision(decisions, evidence, "buy")
    (usd / f"{evidence.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    authority = _authority(
        decision_bootstrap,
        execution_bootstrap,
        evidence,
    )

    monkeypatch.setattr(writer, "_resolve_candidate_id", lambda *_a, **_k: 7)
    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        lambda *_args, **_kwargs: authority,
    )
    monkeypatch.setattr(
        writer,
        "write_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("simulated race")
        ),
    )
    monkeypatch.setattr(
        writer,
        "read_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: authority,
    )

    assert _call(
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
        operator_path=tmp_path / "operator-control.json",
    ) == 0


def test_writer_rejects_collision_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    _feature, evidence = _evidence(
        monkeypatch,
        decision_bootstrap.manifest,
        action="BUY",
        sequence=1,
    )
    _persist_decision(decisions, evidence, "buy")
    (usd / f"{evidence.evidence_fingerprint_sha256}.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    authority = _authority(
        decision_bootstrap,
        execution_bootstrap,
        evidence,
    )

    monkeypatch.setattr(writer, "_resolve_candidate_id", lambda *_a, **_k: 7)
    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        lambda *_args, **_kwargs: authority,
    )
    monkeypatch.setattr(
        writer,
        "write_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("simulated race")
        ),
    )
    monkeypatch.setattr(
        writer,
        "read_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: object(),
    )

    with pytest.raises(ValueError, match="collision|read-back|mismatch"):
        _call(
            decision_bootstrap,
            execution_bootstrap,
            decisions,
            authorities,
            usd,
            operator_path=tmp_path / "operator-control.json",
        )


def test_writer_has_only_bounded_buy_authority_write_scope() -> None:
    payload = Path(writer.__file__).read_text(encoding="utf-8")

    for required in (
        "_resolve_candidate_id",
        "FastPaperShadowQuoteReadPolicy",
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        "write_fast_paper_shadow_buy_authority_source_record",
        "read_fast_paper_shadow_buy_authority_source_record",
    ):
        assert required in payload

    for forbidden in (
        "write_fast_paper_shadow_execution_input_source_record",
        "run_fast_paper_shadow_buy_source_publisher_cycle",
        "execute_fast_paper_buy",
        "execute_fast_paper_shadow_decision(",
        "sqlite3",
        "requests.",
        "httpx",
        "aiohttp",
        "shreks_brain.scoring",
        "score_candidate",
        "shreks_brain.decision",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "fast_future_path_labels",
        "counterfactual",
    ):
        assert forbidden not in payload
