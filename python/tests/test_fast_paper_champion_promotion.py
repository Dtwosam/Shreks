from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_champion_promotion as promotion


_RELEASE_SHA = "a" * 40
_MANIFEST_1 = "b" * 64
_MANIFEST_2 = "c" * 64
_CHAMPION_1 = "d" * 64
_CHAMPION_2 = "e" * 64
_BINDING = "f" * 64
_POLICY = "1" * 64
_SAMPLE = "2" * 64
_ECONOMICS = "3" * 64
_MISSED = "4" * 64
_LATENCY = "5" * 64


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _finalize(material: dict[str, object]) -> dict[str, object]:
    return {
        **material,
        "report_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _readiness(
    *,
    champion_version: str = "fast-champion-v1",
    champion_fingerprint: str = _CHAMPION_1,
    manifest_fingerprint: str = _MANIFEST_1,
    decision: str = "PROMOTION_READY",
) -> dict[str, object]:
    return _finalize(
        {
            "schema_name": "shreks.fast_paper_shadow_promotion_readiness",
            "schema_version": 1,
            "policy_version": "fl11.4-policy-v1",
            "policy_fingerprint_sha256": _POLICY,
            "release_source_sha": _RELEASE_SHA,
            "manifest_fingerprint_sha256": manifest_fingerprint,
            "champion_version": champion_version,
            "champion_fingerprint_sha256": champion_fingerprint,
            "action_policy_version": "action-v1",
            "binding_fingerprint_sha256": _BINDING,
            "window_since_unix_ms": 1_000,
            "window_until_unix_ms": 2_000,
            "window_duration_ms": 1_000,
            "sample_proof_fingerprint_sha256": _SAMPLE,
            "trade_economics_report_fingerprint_sha256": _ECONOMICS,
            "missed_opportunity_report_fingerprint_sha256": _MISSED,
            "latency_proof_report_fingerprint_sha256": _LATENCY,
            "observed_metrics": {
                "net_expectancy_pct": 1.0,
            },
            "gate_results": [
                {
                    "code": "MIN_NET_EXPECTANCY_PCT",
                    "status": "PASS",
                    "observed_value": 1.0,
                    "threshold_value": 0.5,
                    "message": "pass",
                }
            ],
            "decision": decision,
            "promotion_authority": "NOT_GRANTED",
            "production_paper_cutover": "NOT_GRANTED",
            "signing_submission_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _write_readiness(path: Path, document: dict[str, object]) -> Path:
    path.write_text(_canonical(document), encoding="utf-8")
    return path


def _patch_manifest(
    monkeypatch: pytest.MonkeyPatch,
    *,
    champion_version: str = "fast-champion-v1",
    champion_fingerprint: str = _CHAMPION_1,
    manifest_fingerprint: str = _MANIFEST_1,
) -> None:
    manifest = SimpleNamespace(
        release_source_sha=_RELEASE_SHA,
        manifest_fingerprint_sha256=manifest_fingerprint,
        champion_version=champion_version,
        champion_fingerprint_sha256=champion_fingerprint,
        action_policy=SimpleNamespace(version="action-v1"),
    )
    monkeypatch.setattr(
        promotion,
        "read_fast_paper_runtime_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        promotion,
        "verify_fast_paper_runtime_bindings",
        lambda _manifest: None,
    )


def _promote_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, object]]:
    _patch_manifest(monkeypatch)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    readiness_path = _write_readiness(
        tmp_path / "readiness.json",
        _readiness(),
    )
    registry_path = tmp_path / "registry.json"
    receipt = promotion.promote_fast_paper_champion(
        manifest_path=manifest_path,
        readiness_path=readiness_path,
        registry_path=registry_path,
        expected_release_sha=_RELEASE_SHA,
        expected_current_champion_fingerprint=None,
        decided_at_unix_ms=3_000,
        reason="reviewed FL11.4 proof",
    )
    return readiness_path, registry_path, receipt


def test_first_ready_candidate_becomes_only_current_champion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_path, registry_path, receipt = _promote_first(
        tmp_path,
        monkeypatch,
    )

    assert receipt["state"] == "PROMOTED"
    assert receipt["paper_champion_authority"] == "RECORDED"
    assert receipt["production_paper_cutover"] == "NOT_GRANTED"
    assert receipt["signing_submission_authority"] == "NOT_GRANTED"
    assert receipt["live_authority"] == "DISABLED"

    registry = promotion.read_fast_paper_champion_registry(registry_path)
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert registry["revision"] == 1
    assert registry["current_champion_version"] == "fast-champion-v1"
    assert registry["current_champion_fingerprint_sha256"] == _CHAMPION_1
    assert len(registry["transitions"]) == 1
    transition = registry["transitions"][0]
    assert transition["sequence"] == 1
    assert transition["decision_reference"] == readiness[
        "report_fingerprint_sha256"
    ]
    assert transition["previous_champion_version"] is None
    assert transition["previous_champion_fingerprint_sha256"] is None
    assert transition["candidate_champion_version"] == "fast-champion-v1"
    assert transition["candidate_champion_fingerprint_sha256"] == _CHAMPION_1


def test_registry_and_transition_fingerprints_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    registry = promotion.read_fast_paper_champion_registry(registry_path)

    transition = dict(registry["transitions"][0])
    transition_fingerprint = transition.pop(
        "transition_fingerprint_sha256"
    )
    assert transition_fingerprint == hashlib.sha256(
        _canonical(transition).encode("utf-8")
    ).hexdigest()

    material = dict(registry)
    registry_fingerprint = material.pop("registry_fingerprint_sha256")
    assert registry_fingerprint == hashlib.sha256(
        promotion.canonical_fast_paper_champion_registry(material).encode(
            "utf-8"
        )
    ).hexdigest()


def test_already_current_candidate_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_path, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    before = registry_path.read_bytes()

    receipt = promotion.promote_fast_paper_champion(
        manifest_path=tmp_path / "manifest.json",
        readiness_path=readiness_path,
        registry_path=registry_path,
        expected_release_sha=_RELEASE_SHA,
        expected_current_champion_fingerprint=_CHAMPION_1,
        decided_at_unix_ms=4_000,
        reason="duplicate reviewed command",
    )

    assert receipt["state"] == "ALREADY_CURRENT"
    assert registry_path.read_bytes() == before
    assert promotion.read_fast_paper_champion_registry(
        registry_path
    )["revision"] == 1


def test_replacement_requires_exact_incumbent_compare_and_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    readiness_path = _write_readiness(
        tmp_path / "readiness-v2.json",
        _readiness(
            champion_version="fast-champion-v2",
            champion_fingerprint=_CHAMPION_2,
            manifest_fingerprint=_MANIFEST_2,
        ),
    )
    _patch_manifest(
        monkeypatch,
        champion_version="fast-champion-v2",
        champion_fingerprint=_CHAMPION_2,
        manifest_fingerprint=_MANIFEST_2,
    )

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="expected incumbent",
    ):
        promotion.promote_fast_paper_champion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=registry_path,
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint=None,
            decided_at_unix_ms=5_000,
            reason="replace incumbent",
        )

    receipt = promotion.promote_fast_paper_champion(
        manifest_path=tmp_path / "manifest.json",
        readiness_path=readiness_path,
        registry_path=registry_path,
        expected_release_sha=_RELEASE_SHA,
        expected_current_champion_fingerprint=_CHAMPION_1,
        decided_at_unix_ms=5_000,
        reason="replace incumbent",
    )

    assert receipt["state"] == "PROMOTED"
    registry = promotion.read_fast_paper_champion_registry(registry_path)
    assert registry["revision"] == 2
    assert registry["current_champion_fingerprint_sha256"] == _CHAMPION_2
    transition = registry["transitions"][-1]
    assert transition["previous_champion_version"] == "fast-champion-v1"
    assert transition["previous_champion_fingerprint_sha256"] == _CHAMPION_1


def test_stale_incumbent_expectation_fails_without_changing_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    before = registry_path.read_bytes()
    readiness_path = _write_readiness(
        tmp_path / "readiness-v2.json",
        _readiness(
            champion_version="fast-champion-v2",
            champion_fingerprint=_CHAMPION_2,
            manifest_fingerprint=_MANIFEST_2,
        ),
    )
    _patch_manifest(
        monkeypatch,
        champion_version="fast-champion-v2",
        champion_fingerprint=_CHAMPION_2,
        manifest_fingerprint=_MANIFEST_2,
    )

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="incumbent champion fingerprint mismatch",
    ):
        promotion.promote_fast_paper_champion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=registry_path,
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint="9" * 64,
            decided_at_unix_ms=5_000,
            reason="stale review",
        )

    assert registry_path.read_bytes() == before


def test_non_ready_evidence_cannot_promote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_manifest(monkeypatch)
    readiness_path = _write_readiness(
        tmp_path / "not-ready.json",
        _readiness(decision="PROMOTION_NOT_READY"),
    )

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="PROMOTION_READY",
    ):
        promotion.promote_fast_paper_champion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=tmp_path / "registry.json",
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint=None,
            decided_at_unix_ms=3_000,
            reason="must fail",
        )

    assert not (tmp_path / "registry.json").exists()


def test_readiness_fingerprint_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_manifest(monkeypatch)
    readiness = _readiness()
    readiness["report_fingerprint_sha256"] = "0" * 64
    readiness_path = _write_readiness(tmp_path / "bad.json", readiness)

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="fingerprint",
    ):
        promotion.preflight_fast_paper_champion_promotion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=tmp_path / "registry.json",
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint=None,
        )


def test_manifest_champion_identity_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_manifest(
        monkeypatch,
        champion_fingerprint=_CHAMPION_2,
    )
    readiness_path = _write_readiness(
        tmp_path / "readiness.json",
        _readiness(),
    )

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="champion_fingerprint_sha256 mismatch",
    ):
        promotion.preflight_fast_paper_champion_promotion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=tmp_path / "registry.json",
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint=None,
        )


def test_unknown_registry_field_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["unknown"] = True
    registry_path.write_text(_canonical(registry), encoding="utf-8")

    with pytest.raises(
        promotion.FastPaperChampionPromotionError,
        match="unknown or missing",
    ):
        promotion.read_fast_paper_champion_registry(registry_path)


def test_atomic_publish_failure_preserves_previous_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registry_path, _ = _promote_first(tmp_path, monkeypatch)
    before = registry_path.read_bytes()
    readiness_path = _write_readiness(
        tmp_path / "readiness-v2.json",
        _readiness(
            champion_version="fast-champion-v2",
            champion_fingerprint=_CHAMPION_2,
            manifest_fingerprint=_MANIFEST_2,
        ),
    )
    _patch_manifest(
        monkeypatch,
        champion_version="fast-champion-v2",
        champion_fingerprint=_CHAMPION_2,
        manifest_fingerprint=_MANIFEST_2,
    )

    def fail_replace(_source, _destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr(promotion.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        promotion.promote_fast_paper_champion(
            manifest_path=tmp_path / "manifest.json",
            readiness_path=readiness_path,
            registry_path=registry_path,
            expected_release_sha=_RELEASE_SHA,
            expected_current_champion_fingerprint=_CHAMPION_1,
            decided_at_unix_ms=5_000,
            reason="replace incumbent",
        )

    assert registry_path.read_bytes() == before
    assert not tuple(tmp_path.glob(".registry.json.tmp-*"))


def test_preflight_reports_ready_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_manifest(monkeypatch)
    readiness_path = _write_readiness(
        tmp_path / "readiness.json",
        _readiness(),
    )
    registry_path = tmp_path / "registry.json"

    result = promotion.preflight_fast_paper_champion_promotion(
        manifest_path=tmp_path / "manifest.json",
        readiness_path=readiness_path,
        registry_path=registry_path,
        expected_release_sha=_RELEASE_SHA,
        expected_current_champion_fingerprint=None,
    )

    assert result["state"] == "READY_TO_PROMOTE"
    assert result["registry_revision"] == 0
    assert result["production_paper_cutover"] == "NOT_GRANTED"
    assert result["live_authority"] == "DISABLED"
    assert not registry_path.exists()


def test_packaging_and_authority_firewall() -> None:
    root = Path(__file__).resolve().parents[2]
    source_path = (
        root
        / "python"
        / "src"
        / "shreks_brain"
        / "fast_paper_champion_promotion.py"
    )
    source = source_path.read_text(encoding="utf-8")
    pyproject = (root / "python" / "pyproject.toml").read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-champion-promotion = '
        '"shreks_brain.fast_paper_champion_promotion:main"'
    ) in pyproject

    forbidden = (
        "shreks_brain.scoring",
        "score_candidate",
        "decide_entry",
        "execute_fast_paper_buy",
        "apply_fast_paper_position_action",
        "commit_fast_paper_shadow_transition_atomically",
        "systemctl",
        "subprocess",
        "sign_transaction",
        "submit_transaction",
        "LIVE_ENABLED",
        "RegistryStore",
        "ChampionChallengerRegistry",
    )
    for token in forbidden:
        assert token not in source
