from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_campaign import (
    FastCampaignActionConstraints,
    FastCampaignContinuousActionPolicy,
    FastCampaignDecisionPosition,
    build_fast_campaign_decision_batch,
    build_fast_campaign_decision_request,
    encode_fast_campaign_decision_batch,
)
from shreks_brain.fast_campaign_offline import (
    evaluate_fast_campaign_decision_batch_offline,
)
from fast_forecast_fixtures import feature_record


def _policy() -> FastCampaignContinuousActionPolicy:
    return FastCampaignContinuousActionPolicy(
        version=1,
        horizons_ms=(1_000,),
        entry_exposure_candidates=(0.5,),
        reduce_target_exposure_candidates=(0.25,),
        adverse_excursion_weight=1.0,
        reversal_penalty_bps=100.0,
        route_unavailability_penalty_bps=100.0,
        horizon_disagreement_weight=1.0,
        minimum_buy_value_bps=1.0,
        minimum_hold_value_bps=1.0,
        missing_forecast_open_action="SELL",
    )


def _constraints() -> FastCampaignActionConstraints:
    return FastCampaignActionConstraints(
        max_exposure_fraction=1.0,
        buy_economically_allowed=True,
        expected_future_exit_cost_bps=10.0,
        reduce_execution_costs=(),
        sell_executable=True,
        sell_now_cost_bps=10.0,
        force_sell=False,
    )


def test_offline_learned_prefix_runner_uses_exact_canonical_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "campaign-decision"
    champion = tmp_path / "champion.json"
    binary.write_text("binary", encoding="utf-8")
    champion.write_text("champion", encoding="utf-8")
    record = feature_record(0, 1.0, signature="learned-prefix")
    request = build_fast_campaign_decision_request(
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        _constraints(),
    )
    batch = build_fast_campaign_decision_batch(_policy(), (request,))
    payload = {
        "schema_name": "shreks.fast_campaign_decision_results",
        "schema_version": 1,
        "champion_version": "champion-v1",
        "champion_fingerprint_sha256": "b" * 64,
        "decisions": [
            {
                "source_event_id": request.source_event_id,
                "market_key": request.market_key,
                "source_sequence": request.source_sequence,
                "as_of_unix_ms": request.as_of_unix_ms,
                "policy_version": 1,
                "action": "SKIP",
                "reason": "SKIP_SELECTED",
                "selected_horizon_ms": None,
                "current_exposure_fraction": 0.0,
                "target_exposure_fraction": 0.0,
                "selected_reward_bps": 0.0,
                "selected_risk_bps": 0.0,
                "selected_execution_cost_bps": 0.0,
                "selected_value_bps": 0.0,
                "horizon_evidence": [],
                "candidates": [
                    {
                        "action": "SKIP",
                        "horizon_ms": None,
                        "target_exposure_fraction": 0.0,
                        "reward_bps": 0.0,
                        "risk_bps": 0.0,
                        "execution_cost_penalty_bps": 0.0,
                        "comparison_value_bps": 0.0,
                        "eligible": True,
                    }
                ],
            }
        ],
    }
    material = dict(payload)
    import hashlib
    canonical_material = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    payload["batch_fingerprint_sha256"] = hashlib.sha256(
        canonical_material.encode("utf-8")
    ).hexdigest()
    stdout = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        request_path = Path(argv[2])
        captured["request_payload"] = request_path.read_text(encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        "shreks_brain.fast_campaign_offline.runner.subprocess.run",
        fake_run,
    )

    result = evaluate_fast_campaign_decision_batch_offline(
        binary_path=binary,
        champion_path=champion,
        batch=batch,
    )

    assert captured["argv"][:2] == [str(binary), str(champion)]
    assert captured["request_payload"] == encode_fast_campaign_decision_batch(batch)
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["capture_output"] is True
    assert result.decisions[0].source_event_id == request.source_event_id


def test_offline_learned_prefix_runner_rejects_result_population_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "campaign-decision"
    champion = tmp_path / "champion.json"
    binary.write_text("binary", encoding="utf-8")
    champion.write_text("champion", encoding="utf-8")
    request = build_fast_campaign_decision_request(
        feature_record(0, 1.0),
        FastCampaignDecisionPosition(kind="FLAT"),
        _constraints(),
    )
    batch = build_fast_campaign_decision_batch(_policy(), (request,))

    monkeypatch.setattr(
        "shreks_brain.fast_campaign_offline.runner.decode_fast_campaign_decision_results",
        lambda payload: SimpleNamespace(
            decisions=(
                SimpleNamespace(
                    source_event_id="wrong:0",
                    market_key=request.market_key,
                    source_sequence=request.source_sequence,
                    as_of_unix_ms=request.as_of_unix_ms,
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "shreks_brain.fast_campaign_offline.runner.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="{}",
            stderr="",
        ),
    )

    with pytest.raises(ValueError, match="population|identity"):
        evaluate_fast_campaign_decision_batch_offline(
            binary_path=binary,
            champion_path=champion,
            batch=batch,
        )


def test_offline_learned_runner_source_has_no_provider_paper_superiority_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_campaign_offline"
        / "runner.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sqlite3",
        "requests.",
        "httpx",
        "execute_fast_paper",
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source
