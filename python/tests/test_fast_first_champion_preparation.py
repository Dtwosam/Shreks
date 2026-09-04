from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_first_champion_preparation as preparation_module
from fast_chronological_fixtures import (
    HORIZON_MS,
    TEST_END,
    chronological_bundle,
)
from fast_forecast_evaluation_fixtures import (
    chronological_policy,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPartition
from shreks_brain.fast_first_champion import (
    decode_fast_first_champion_file_request,
)
from shreks_brain.research.fast_training_bundle import (
    bundle_logical_fingerprint_sha256,
)
from shreks_brain.fast_first_champion_preparation import (
    FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_VERSION,
    FastFirstChampionPreparationArtifact,
    prepare_fast_first_champion_evidence,
    read_fast_first_champion_preparation,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bundle_for_source(source_sha: str):
    bundle = chronological_bundle()
    features = replace(bundle.features, source_sha256=source_sha)
    provisional = replace(
        bundle.manifest,
        feature_source_jsonl_sha256=source_sha,
        bundle_fingerprint_sha256="0" * 64,
    )
    manifest = replace(
        provisional,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(
            provisional
        ),
    )
    return replace(bundle, features=features, manifest=manifest)


def _install_component_fakes(
    monkeypatch,
    *,
    proof_source: Path,
    database: Path,
    wal: Path,
    mutate_database: bool = False,
    mismatch_bundle: bool = False,
):
    feature_bytes = (proof_source / "features.jsonl").read_bytes()
    feature_sha = _sha(feature_bytes)
    bundle = _bundle_for_source(feature_sha)
    feature_logical = bundle.features.logical_fingerprint_sha256
    proof_manifest = SimpleNamespace(
        release_source_sha="1eba5696ed1dc5921c55b5f32e4c0d559cb24d83",
        artifact_fingerprint_sha256="2" * 64,
        feature_jsonl_sha256=feature_sha,
        feature_logical_fingerprint_sha256=feature_logical,
        observer_database_sha256="3" * 64,
        observer_database_wal_sha256=None,
    )

    def _read_workspace(path):
        return SimpleNamespace(
            path=Path(path),
            manifest=proof_manifest,
            features=SimpleNamespace(
                source_sha256=feature_sha,
                logical_fingerprint_sha256=feature_logical,
            ),
        )

    monkeypatch.setattr(
        preparation_module,
        "read_fast_proof_workspace",
        _read_workspace,
    )

    monkeypatch.setattr(
        preparation_module,
        "build_fast_training_bundle_from_runtime_sources",
        lambda **_kwargs: bundle,
    )

    hydration_holder = {}

    def _write_hydration_artifact(
        *,
        bundle,
        observer_database_path,
        validation_policy,
        horizon_ms,
        hydration_policy,
        destination,
    ):
        root = Path(destination)
        root.mkdir()
        contexts = root / "contexts.json"
        policy = root / "policy.json"
        manifest_file = root / "manifest.json"
        contexts.write_text('{"sealed":"contexts"}\n', encoding="utf-8")
        policy.write_text('{"sealed":"policy"}\n', encoding="utf-8")
        manifest_file.write_text('{"sealed":"manifest"}\n', encoding="utf-8")
        db_sha = _sha(Path(observer_database_path).read_bytes())
        wal_path = Path(str(observer_database_path) + "-wal")
        wal_sha = _sha(wal_path.read_bytes()) if wal_path.is_file() else None
        manifest = SimpleNamespace(
            validation_policy=validation_policy,
            horizon_ms=horizon_ms,
            training_bundle_fingerprint_sha256=(
                bundle.manifest.bundle_fingerprint_sha256
            ),
            feature_source_jsonl_sha256=feature_sha,
            observer_database_sha256=db_sha,
            observer_database_wal_sha256=wal_sha,
            hydration_policy_fingerprint_sha256="4" * 64,
            population_validation_run_fingerprint_sha256="5" * 64,
            context_fingerprint_sha256="6" * 64,
            contexts_file_sha256=_sha(contexts.read_bytes()),
            artifact_fingerprint_sha256="7" * 64,
        )
        artifact = SimpleNamespace(
            path=root,
            manifest=manifest,
            policy=hydration_policy,
            context_corpus=SimpleNamespace(
                context_fingerprint_sha256="6" * 64
            ),
            population_validation_run_fingerprint_sha256="5" * 64,
        )
        hydration_holder["artifact"] = artifact
        return manifest

    monkeypatch.setattr(
        preparation_module,
        "write_fast_forecast_context_hydration_artifact",
        _write_hydration_artifact,
    )
    monkeypatch.setattr(
        preparation_module,
        "read_fast_forecast_context_hydration_artifact",
        lambda _path: hydration_holder["artifact"],
    )

    champion_holder = {}

    def _run_first_champion(request_path):
        request_path = Path(request_path)
        request = decode_fast_first_champion_file_request(
            request_path.read_text(encoding="utf-8")
        )
        root = request_path.parent / request.destination_path
        root.mkdir()
        (root / "placeholder").write_bytes(b"sealed-first-champion")
        db_sha = _sha(database.read_bytes())
        wal_sha = _sha(wal.read_bytes()) if wal.is_file() else None
        hydration = hydration_holder["artifact"]
        bundle_fingerprint = (
            "f" * 64
            if mismatch_bundle
            else bundle.manifest.bundle_fingerprint_sha256
        )
        manifest = SimpleNamespace(
            request_fingerprint_sha256=request.request_fingerprint_sha256,
            feature_jsonl_sha256=feature_sha,
            observer_database_sha256=db_sha,
            observer_database_wal_sha256=wal_sha,
            context_corpus_file_sha256=(
                hydration.manifest.contexts_file_sha256
            ),
            context_fingerprint_sha256="6" * 64,
            training_bundle_fingerprint_sha256=bundle_fingerprint,
            champion_fingerprint_sha256="8" * 64,
            artifact_fingerprint_sha256="9" * 64,
        )
        artifact = SimpleNamespace(
            path=root,
            manifest=manifest,
            request=request,
            champion=SimpleNamespace(
                champion_version=request.champion_version,
                champion_fingerprint_sha256="8" * 64,
            ),
            context_corpus=SimpleNamespace(
                context_fingerprint_sha256="6" * 64
            ),
            evaluation_reports=(),
        )
        champion_holder["artifact"] = artifact
        if mutate_database:
            database.write_bytes(database.read_bytes() + b"mutation")
        return artifact

    monkeypatch.setattr(
        preparation_module,
        "run_fast_first_champion_file_request",
        _run_first_champion,
    )
    monkeypatch.setattr(
        preparation_module,
        "read_fast_first_champion_artifact",
        lambda _path: champion_holder["artifact"],
    )

    return bundle, proof_manifest


def _prepare(monkeypatch, tmp_path: Path, **fake_overrides):
    proof = tmp_path / "proof-workspace-source"
    proof.mkdir()
    (proof / "features.jsonl").write_bytes(b"sealed-feature-jsonl\n")
    (proof / "manifest.json").write_bytes(b"sealed-proof-manifest\n")
    database = tmp_path / "shreks.db"
    database.write_bytes(b"stable-observer-database")
    wal = Path(str(database) + "-wal")
    wal.write_bytes(b"stable-observer-wal")

    bundle, proof_manifest = _install_component_fakes(
        monkeypatch,
        proof_source=proof,
        database=database,
        wal=wal,
        **fake_overrides,
    )
    destination = tmp_path / "first-champion-preparation"
    artifact = prepare_fast_first_champion_evidence(
        proof_workspace_path=proof,
        observer_database_path=database,
        destination=destination,
        hydration_policy=object(),
        validation_policy=chronological_policy(),
        evaluation_policy=evaluation_policy(
            FastForecastEvaluationPartition.TEST
        ),
        future_path_label_version=1,
        counterfactual_base_quantity=2.0,
        champion_version="fl9-prepared-first-v1",
        decision_reference="operator-selection:prepared-first-v1",
        decided_at_unix_ms=TEST_END + HORIZON_MS + 1,
        reason="explicit prepared first champion selection",
        horizon_ms=HORIZON_MS,
        model_version_prefix="fl9-prepared-first",
        training_policy_version="fl9-prepared-naive-v1",
        minimum_test_scored_observations=1,
    )
    return artifact, destination, database, wal, bundle, proof_manifest


def test_preparation_atomically_cross_links_sealed_components(
    monkeypatch,
    tmp_path: Path,
) -> None:
    artifact, destination, database, wal, bundle, proof_manifest = _prepare(
        monkeypatch,
        tmp_path,
    )
    reopened = read_fast_first_champion_preparation(destination)

    assert type(artifact) is FastFirstChampionPreparationArtifact
    assert reopened.manifest == artifact.manifest
    assert artifact.manifest.schema_name == FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_NAME
    assert artifact.manifest.schema_version == FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_VERSION
    assert artifact.manifest.proof_workspace_artifact_fingerprint_sha256 == (
        proof_manifest.artifact_fingerprint_sha256
    )
    assert artifact.manifest.training_bundle_fingerprint_sha256 == (
        bundle.manifest.bundle_fingerprint_sha256
    )
    assert artifact.manifest.context_fingerprint_sha256 == "6" * 64
    assert artifact.manifest.champion_fingerprint_sha256 == "8" * 64
    assert artifact.manifest.observer_database_sha256 == _sha(
        database.read_bytes()
    )
    assert artifact.manifest.observer_database_wal_sha256 == _sha(
        wal.read_bytes()
    )
    assert {value.name for value in destination.iterdir()} == {
        "proof-workspace",
        "context-hydration",
        "first-champion-request.json",
        "first-champion",
        "manifest.json",
    }

    request = decode_fast_first_champion_file_request(
        (destination / "first-champion-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request.feature_jsonl_path == "proof-workspace/features.jsonl"
    assert request.context_corpus_path == "context-hydration/contexts.json"
    assert request.destination_path == "first-champion"
    assert request.validation_policy == chronological_policy()


def test_preparation_rejects_db_race_and_publishes_nothing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="database.*changed|source.*changed"):
        _prepare(
            monkeypatch,
            tmp_path,
            mutate_database=True,
        )
    assert not (tmp_path / "first-champion-preparation").exists()


def test_preparation_rejects_cross_chain_bundle_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="bundle.*fingerprint|training.*bundle"):
        _prepare(
            monkeypatch,
            tmp_path,
            mismatch_bundle=True,
        )
    assert not (tmp_path / "first-champion-preparation").exists()


def test_preparation_reader_rejects_manifest_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, destination, *_ = _prepare(monkeypatch, tmp_path)
    manifest = destination / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="canonical|JSON|fingerprint"):
        read_fast_first_champion_preparation(destination)


def test_preparation_source_has_no_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_preparation.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
    ):
        assert forbidden not in source
