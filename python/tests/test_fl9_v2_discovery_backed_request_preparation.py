from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

import shreks_brain.fl9_v2_discovery_backed_request_preparation as preparation
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
)
from shreks_brain.fast_first_champion_v2.host_request import (
    decode_fast_first_champion_v2_host_request,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
)

from test_fl9_v2_discovery_authority_binding import (
    COHORT_FP,
    HYDRATION_FP,
    RUNTIME_FP,
    SOURCE_SHA,
    WSOL,
    _result,
)
from test_fast_first_champion_v2_host_request_writer import (
    COHORT_FP as FROZEN_COHORT_FP,
    COST_FP,
    OVERLAY_FP,
    _sources,
)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _evaluation_policy() -> FastForecastEvaluationPolicy:
    return FastForecastEvaluationPolicy(
        version="fl9-v2-host-test-eval-v1",
        partition=FastForecastEvaluationPartition.TEST,
        probability_bucket_count=10,
        liquidity_capacity_quote_boundaries=(10.0, 100.0),
        round_trip_cost_bps_boundaries=(25.0, 50.0),
        binary_log_loss_clip_epsilon=1e-12,
    )


def _cost_policy() -> FastTrainingExecutionCostPolicy:
    return FastTrainingExecutionCostPolicy(
        version="fl9-v2-host-cost-v1",
        additional_entry_slippage_bps=10,
        additional_exit_slippage_bps=20,
        entry_latency_bps=5,
        exit_latency_bps=5,
        entry_network_fee_quote=0.0,
        exit_network_fee_quote=0.0,
        entry_priority_fee_quote=0.0,
        exit_priority_fee_quote=0.0,
        entry_expected_failure_cost_quote=0.0,
        exit_expected_failure_cost_quote=0.0,
    )


def _binding(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    document = _result()
    selected = document["discovery_report"]["candidates"][0]
    material = {
        "schema_name": "shreks.fl9_v2_discovery_authority_binding",
        "schema_version": 1,
        "request_id": document["request_id"],
        "release_source_sha": SOURCE_SHA,
        "cohort_artifact_fingerprint_sha256": FROZEN_COHORT_FP,
        "cohort_quote_mint": WSOL,
        "authority_group_fingerprint_sha256": document["authority_groups"][0][
            "authority_group_fingerprint_sha256"
        ],
        "selected_request_fingerprint_sha256": document[
            "selected_request_fingerprint_sha256"
        ],
        "discovery_result_sha256": "7" * 64,
        "runtime_manifest_source_kind": selected["source_kind"],
        "runtime_manifest_source_path": str(tmp_path / "runtime-manifest.json"),
        "backup_bundle_path": None,
        "backup_created_at_unix_ms": None,
        "runtime_manifest_fingerprint_sha256": RUNTIME_FP,
        "hydration_policy_fingerprint_sha256": HYDRATION_FP,
        "regime_quote_asset_mint": WSOL,
        "safety_probe_output_mint": WSOL,
        "quote_asset_mint": WSOL,
        "quote_asset_decimals": 9,
        "quote_provider": "jupiter",
    }
    import shreks_brain.fl9_v2_discovery_authority_binding as binder
    binding = {
        **material,
        "binding_fingerprint_sha256": binder._sha256_canonical(material),
    }
    path = tmp_path / "discovery-binding.json"
    path.write_text(_canonical(binding), encoding="utf-8")
    return path, binding


def _install_sources(monkeypatch, *, runtime_fp=RUNTIME_FP):
    proof = SimpleNamespace(
        manifest=SimpleNamespace(release_source_sha=SOURCE_SHA)
    )
    cohort = SimpleNamespace(
        manifest=SimpleNamespace(
            artifact_fingerprint_sha256=FROZEN_COHORT_FP,
            accepted_identity_fingerprint_sha256="5" * 64,
        ),
        accepted_decisions=(
            SimpleNamespace(
                decision_identity=(
                    "signature-1", 0, 1, "mint-1", WSOL,
                    "pump_swap", 1_788_878_663_298,
                )
            ),
        ),
    )
    runtime_manifest = SimpleNamespace(
        manifest_fingerprint_sha256=runtime_fp,
        policy_bundle=SimpleNamespace(
            quote_asset=SimpleNamespace(mint=WSOL, decimals=9)
        ),
    )
    cost_policy = _cost_policy()
    overlay = SimpleNamespace(manifest_fingerprint_sha256=OVERLAY_FP)

    monkeypatch.setattr(preparation, "read_fast_proof_workspace", lambda _path: proof)
    monkeypatch.setattr(preparation, "read_fl9_v2_cohort_acceptance", lambda _path: cohort)
    monkeypatch.setattr(
        preparation,
        "decode_observer_paper_campaign_runtime_manifest",
        lambda _payload: runtime_manifest,
    )
    monkeypatch.setattr(
        preparation,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: SimpleNamespace(),
    )
    monkeypatch.setattr(
        preparation,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: HYDRATION_FP,
    )

    import shreks_brain.fast_first_champion_v2.host_request as request_module
    monkeypatch.setattr(request_module, "read_fast_proof_workspace", lambda _path: proof)
    monkeypatch.setattr(request_module, "read_fl9_v2_cohort_acceptance", lambda _path: cohort)
    monkeypatch.setattr(
        request_module,
        "decode_fast_forecast_context_hydration_policy",
        lambda _payload: SimpleNamespace(),
    )
    monkeypatch.setattr(
        request_module,
        "require_fast_first_champion_v2_hydration_policy_matches_identities",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        request_module,
        "fast_forecast_context_hydration_policy_fingerprint_sha256",
        lambda _policy: HYDRATION_FP,
    )
    monkeypatch.setattr(
        request_module,
        "validate_fast_training_economics_overlay",
        lambda _path: overlay,
    )
    monkeypatch.setattr(
        request_module,
        "decode_fast_training_execution_cost_policy",
        lambda _payload: cost_policy,
    )
    monkeypatch.setattr(
        request_module,
        "fast_training_execution_cost_policy_fingerprint_sha256",
        lambda _policy: COST_FP,
    )


def test_preparation_writes_request_and_discovery_bound_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = _sources(tmp_path)
    binding_path, binding = _binding(tmp_path)
    runtime_path = Path(binding["runtime_manifest_source_path"])
    runtime_path.write_text("{}\n", encoding="utf-8")
    _install_sources(monkeypatch)

    request_path = tmp_path / "request.json"
    evidence_path = tmp_path / "evidence"
    receipt_path = tmp_path / "preparation.json"

    receipt = preparation.prepare_discovery_backed_v2_request(
        discovery_authority_binding_path=binding_path,
        proof_workspace_path=sources["proof"],
        observer_database_path=sources["database"],
        cohort_artifact_path=sources["cohort"],
        hydration_policy_path=sources["hydration"],
        training_economics_overlay_path=sources["overlay"],
        training_execution_cost_policy_path=sources["cost"],
        request_destination=request_path,
        evidence_destination=evidence_path,
        preparation_destination=receipt_path,
        future_path_label_version=1,
        counterfactual_base_quantity=1.0,
        evaluation_policy=_evaluation_policy(),
        champion_version="fl9-v2-runtime-v1",
        model_version_prefix="fl9-v2",
        training_policy_version="fl9-v2-training-v1",
        reason="fresh discovery-backed V2 evidence request",
    )

    request = decode_fast_first_champion_v2_host_request(
        request_path.read_text(encoding="utf-8")
    )
    assert request.expected_release_source_sha == binding["release_source_sha"]
    assert request.expected_cohort_artifact_fingerprint_sha256 == binding[
        "cohort_artifact_fingerprint_sha256"
    ]
    assert request.expected_hydration_policy_fingerprint_sha256 == binding[
        "hydration_policy_fingerprint_sha256"
    ]

    assert receipt["schema_name"] == "shreks.fl9_v2_discovery_backed_request_preparation"
    assert receipt["schema_version"] == 1
    assert receipt["discovery_binding_fingerprint_sha256"] == binding[
        "binding_fingerprint_sha256"
    ]
    assert receipt["runtime_manifest_fingerprint_sha256"] == RUNTIME_FP
    assert receipt["request_fingerprint_sha256"] == request.request_fingerprint_sha256
    assert receipt["request_sha256"] == hashlib.sha256(request_path.read_bytes()).hexdigest()
    assert receipt["request_preparation_authority"] == "DISCOVERY_BOUND_REQUEST_ONLY"
    assert receipt["scoring_authority"] == "NOT_GRANTED"
    assert receipt["champion_publication_authority"] == "NOT_GRANTED"
    assert receipt["paper_promotion_authority"] == "BLOCKED"
    assert receipt["live_authority"] == "DISABLED"
    assert stat.S_IMODE(request_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600


def test_preparation_rejects_runtime_manifest_not_selected_by_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = _sources(tmp_path)
    binding_path, binding = _binding(tmp_path)
    Path(binding["runtime_manifest_source_path"]).write_text("{}\n", encoding="utf-8")
    _install_sources(monkeypatch, runtime_fp="8" * 64)

    with pytest.raises(
        preparation.DiscoveryBackedRequestPreparationError,
        match="runtime manifest.*fingerprint|discovery",
    ):
        preparation.prepare_discovery_backed_v2_request(
            discovery_authority_binding_path=binding_path,
            proof_workspace_path=sources["proof"],
            observer_database_path=sources["database"],
            cohort_artifact_path=sources["cohort"],
            hydration_policy_path=sources["hydration"],
            training_economics_overlay_path=sources["overlay"],
            training_execution_cost_policy_path=sources["cost"],
            request_destination=tmp_path / "request.json",
            evidence_destination=tmp_path / "evidence",
            preparation_destination=tmp_path / "preparation.json",
            future_path_label_version=1,
            counterfactual_base_quantity=1.0,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-v2-runtime-v1",
            model_version_prefix="fl9-v2",
            training_policy_version="fl9-v2-training-v1",
            reason="fresh discovery-backed V2 evidence request",
        )
    assert not (tmp_path / "request.json").exists()


def test_preparation_rejects_stale_release_or_hydration_before_request_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = _sources(tmp_path)
    binding_path, binding = _binding(tmp_path)
    Path(binding["runtime_manifest_source_path"]).write_text("{}\n", encoding="utf-8")
    _install_sources(monkeypatch)

    monkeypatch.setattr(
        preparation,
        "read_fast_proof_workspace",
        lambda _path: SimpleNamespace(
            manifest=SimpleNamespace(release_source_sha="9" * 40)
        ),
    )

    with pytest.raises(
        preparation.DiscoveryBackedRequestPreparationError,
        match="release",
    ):
        preparation.prepare_discovery_backed_v2_request(
            discovery_authority_binding_path=binding_path,
            proof_workspace_path=sources["proof"],
            observer_database_path=sources["database"],
            cohort_artifact_path=sources["cohort"],
            hydration_policy_path=sources["hydration"],
            training_economics_overlay_path=sources["overlay"],
            training_execution_cost_policy_path=sources["cost"],
            request_destination=tmp_path / "request.json",
            evidence_destination=tmp_path / "evidence",
            preparation_destination=tmp_path / "preparation.json",
            future_path_label_version=1,
            counterfactual_base_quantity=1.0,
            evaluation_policy=_evaluation_policy(),
            champion_version="fl9-v2-runtime-v1",
            model_version_prefix="fl9-v2",
            training_policy_version="fl9-v2-training-v1",
            reason="fresh discovery-backed V2 evidence request",
        )
    assert not (tmp_path / "request.json").exists()


def test_cli_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "shreks_brain" /
        "fl9_v2_discovery_backed_request_preparation.py"
    ).read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-fl9-v2-discovery-backed-request-prepare = '
        '"shreks_brain.fl9_v2_discovery_backed_request_preparation:main"'
        in pyproject
    )

    for forbidden in (
        "run_fast_first_champion_v2_host_request",
        "build_fast_first_champion_v2(",
        "write_fast_first_champion_v2_evidence",
        "score_candidate",
        "promote_candidate",
        "sign_transaction",
        "send_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source

    for authority in (
        '"scoring_authority": "NOT_GRANTED"',
        '"champion_publication_authority": "NOT_GRANTED"',
        '"paper_promotion_authority": "BLOCKED"',
        '"live_authority": "DISABLED"',
    ):
        assert authority in source
