from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow_buy_authority_writer as writer
from shreks_brain.fast_paper_runtime import (
    run_fast_paper_shadow_buy_authority_writer_cycle,
)

from test_fast_paper_shadow_buy_authority_evidence_adapter import (
    _execution_policy as _economics_policy,
    _market_policy,
    _regime_policy,
    _regime_read_policy,
    _safety_policy,
    _safety_probe,
)
from test_fast_paper_shadow_buy_authority_writer import (
    _authority,
    _bootstraps,
    _evidence,
    _persist_decision,
    _quote_policy,
)
from test_fast_paper_shadow_decision import _record


def _call(
    decision_bootstrap,
    execution_bootstrap,
    decisions: Path,
    authorities: Path,
    usd: Path,
    *,
    policies,
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
        execution_economics_policies=policies,
        operator_risk_control_path=operator_path,
        entry_authority_binary_path=(
            operator_path.parent / "shreks-fast-entry-authority"
        ),
        day_started_at_unix_ms=0,
        data_healthy=True,
        execution_healthy=True,
        global_risk_halt=False,
    )


def test_writer_requires_exact_action_policy_horizon_coverage(
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    base = _economics_policy(_record())
    wrong = replace(base, horizon_ms=500)

    with pytest.raises(ValueError, match="horizon|coverage|missing"):
        _call(
            decision_bootstrap,
            execution_bootstrap,
            decisions,
            authorities,
            usd,
            policies=(wrong,),
            operator_path=tmp_path / "operator-control.json",
        )

    with pytest.raises(ValueError, match="horizon|coverage|extra"):
        _call(
            decision_bootstrap,
            execution_bootstrap,
            decisions,
            authorities,
            usd,
            policies=(base, wrong),
            operator_path=tmp_path / "operator-control.json",
        )


def test_writer_rejects_duplicate_economics_horizon(
    tmp_path: Path,
) -> None:
    (
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
    ) = _bootstraps(tmp_path)
    base = _economics_policy(_record())

    with pytest.raises(ValueError, match="duplicate|horizon"):
        _call(
            decision_bootstrap,
            execution_bootstrap,
            decisions,
            authorities,
            usd,
            policies=(base, base),
            operator_path=tmp_path / "operator-control.json",
        )


def test_writer_delegates_only_matching_learned_horizon_policy(
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
    policy = _economics_policy(_record())
    authority = _authority(
        decision_bootstrap,
        execution_bootstrap,
        evidence,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        writer,
        "_resolve_candidate_id",
        lambda *_args, **_kwargs: 7,
    )

    def produce(*args, **_kwargs):
        captured["execution_economics_policy"] = args[13]
        return authority

    monkeypatch.setattr(
        writer,
        "produce_fast_paper_shadow_buy_authority_from_persisted_evidence",
        produce,
    )
    monkeypatch.setattr(
        writer,
        "write_fast_paper_shadow_buy_authority_source_record",
        lambda *_args, **_kwargs: None,
    )

    assert _call(
        decision_bootstrap,
        execution_bootstrap,
        decisions,
        authorities,
        usd,
        policies=(policy,),
        operator_path=tmp_path / "operator-control.json",
    ) == 1
    assert captured["execution_economics_policy"] is policy
    assert policy.horizon_ms == evidence.decision.selected_horizon_ms


def test_writer_api_has_no_singular_economics_policy_authority() -> None:
    parameters = inspect.signature(
        run_fast_paper_shadow_buy_authority_writer_cycle
    ).parameters

    assert "execution_economics_policies" in parameters
    assert "execution_economics_policy" not in parameters
