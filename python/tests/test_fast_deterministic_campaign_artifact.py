from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_NAME,
    FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_VERSION,
    FastDeterministicCampaignArtifact,
    FastDeterministicCampaignArtifactManifest,
    read_fast_deterministic_campaign_artifact,
    write_fast_deterministic_campaign_artifact,
)
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_comparison_catalog,
)


CATALOG_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "fast_deterministic_comparison_catalog_v1.json"
)


def _catalog():
    return decode_fast_deterministic_comparison_catalog(
        CATALOG_FIXTURE.read_text(encoding="utf-8")
    )


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fake_pipeline(monkeypatch, *, fail_matrix: bool = False):
    calls: list[str] = []
    catalog = _catalog()
    hydrated = SimpleNamespace(rows=("row",), provenance=("proof",))
    assembly = SimpleNamespace(hydration_inputs=("hydration",))
    bundle_manifest = SimpleNamespace(
        bundle_fingerprint_sha256="a" * 64,
        catalog_fingerprint_sha256=catalog.catalog_fingerprint_sha256,
        row_count=1,
    )
    runs = tuple(
        SimpleNamespace(candidate_version=value.candidate_version)
        for value in catalog.candidates
    )
    matrix = SimpleNamespace(
        runs=runs,
        event_population_fingerprint_sha256="b" * 64,
    )

    def fake_assemble(**kwargs):
        calls.append("assemble")
        return assembly

    def fake_hydrate(**kwargs):
        calls.append("hydrate")
        assert kwargs["hydration_inputs"] == assembly.hydration_inputs
        return hydrated

    def fake_bundle(**kwargs):
        calls.append("bundle")
        destination = Path(kwargs["destination"])
        destination.mkdir()
        (destination / "fast_training_features.parquet").write_bytes(b"features")
        (destination / "comparison_evidence.jsonl").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (destination / "manifest.json").write_text(
            _canonical({"bundle_fingerprint_sha256": "a" * 64}),
            encoding="utf-8",
        )
        return bundle_manifest

    def fake_matrix(**kwargs):
        calls.append("matrix")
        assert kwargs["rows"] == hydrated.rows
        if fail_matrix:
            raise RuntimeError("matrix failed")
        return matrix

    run_document = {
        "schema_name": "shreks.fast_policy_run_evidence_batch",
        "schema_version": 1,
        "runs": [
            {"candidate_version": value.candidate_version}
            for value in catalog.candidates
        ],
        "batch_fingerprint_sha256": "c" * 64,
    }
    run_payload = _canonical(run_document)

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "assemble_fast_deterministic_comparison_hydration_inputs",
        fake_assemble,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "hydrate_fast_deterministic_comparison_evidence",
        fake_hydrate,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "write_fast_deterministic_comparison_evidence_bundle",
        fake_bundle,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "run_fast_deterministic_comparison_catalog_matrix",
        fake_matrix,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "encode_fast_policy_run_evidence_batch",
        lambda values: (
            calls.append("runs")
            or run_payload
        ),
    )
    fake_bundle = SimpleNamespace(manifest=bundle_manifest)
    fake_runs = tuple(
        SimpleNamespace(
            candidate_version=value.candidate_version,
            candidate_fingerprint_sha256=value.candidate_fingerprint_sha256,
            event_population_fingerprint_sha256=(
                matrix.event_population_fingerprint_sha256
            ),
        )
        for value in catalog.candidates
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "read_fast_deterministic_comparison_evidence_bundle",
        lambda path: fake_bundle,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "decode_fast_policy_run_evidence_batch",
        lambda payload: fake_runs,
    )
    return calls, bundle_manifest, matrix, run_payload


def test_campaign_artifact_stages_full_pipeline_then_publishes_atomically(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls, bundle_manifest, matrix, run_payload = _fake_pipeline(monkeypatch)
    destination = tmp_path / "campaign"

    manifest = write_fast_deterministic_campaign_artifact(
        database_path=tmp_path / "observer.db",
        feature_dataset=object(),
        catalog=_catalog(),
        champion_path=tmp_path / "champion.json",
        execution_policy=object(),
        contexts=(object(),),
        entry_authority_binary_path=tmp_path / "entry-authority",
        candidate_binary_path=tmp_path / "candidate-row",
        paper_run_id_prefix="fl9-real",
        assessment_version="assessment-v1",
        starting_ledger=object(),
        fill_policy=object(),
        risk_policy=object(),
        position_policy=object(),
        evaluation_policy=object(),
        destination=destination,
    )

    assert calls == ["assemble", "hydrate", "bundle", "matrix", "runs"]
    assert type(manifest) is FastDeterministicCampaignArtifactManifest
    assert manifest.schema_name == FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_NAME
    assert manifest.schema_version == FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_VERSION
    assert manifest.catalog_fingerprint_sha256 == _catalog().catalog_fingerprint_sha256
    assert (
        manifest.comparison_bundle_fingerprint_sha256
        == bundle_manifest.bundle_fingerprint_sha256
    )
    assert (
        manifest.event_population_fingerprint_sha256
        == matrix.event_population_fingerprint_sha256
    )
    assert manifest.run_count == 8
    assert manifest.run_batch_fingerprint_sha256 == "c" * 64
    assert manifest.run_batch_file_sha256 == _sha256_bytes(
        run_payload.encode("utf-8")
    )

    assert {path.name for path in destination.iterdir()} == {
        "comparison_bundle",
        "comparison_catalog.json",
        "policy_runs.json",
        "manifest.json",
    }
    assert (
        (destination / "comparison_catalog.json").read_text(encoding="utf-8")
        == CATALOG_FIXTURE.read_text(encoding="utf-8")
    )
    assert (
        destination / "policy_runs.json"
    ).read_text(encoding="utf-8") == run_payload

    manifest_document = json.loads(
        (destination / "manifest.json").read_text(encoding="utf-8")
    )
    assert (
        (destination / "manifest.json").read_text(encoding="utf-8")
        == _canonical(manifest_document)
    )
    assert len(manifest.artifact_fingerprint_sha256) == 64


def test_campaign_artifact_failure_never_publishes_partial_destination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _fake_pipeline(monkeypatch, fail_matrix=True)
    destination = tmp_path / "campaign-failed"

    with pytest.raises(RuntimeError, match="matrix failed"):
        write_fast_deterministic_campaign_artifact(
            database_path=tmp_path / "observer.db",
            feature_dataset=object(),
            catalog=_catalog(),
            champion_path=tmp_path / "champion.json",
            execution_policy=object(),
            contexts=(object(),),
            entry_authority_binary_path=tmp_path / "entry-authority",
            candidate_binary_path=tmp_path / "candidate-row",
            paper_run_id_prefix="fl9-real",
            assessment_version="assessment-v1",
            starting_ledger=object(),
            fill_policy=object(),
            risk_policy=object(),
            position_policy=object(),
            evaluation_policy=object(),
            destination=destination,
        )

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".campaign-failed-*"))


def test_campaign_artifact_reader_authenticates_all_child_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls, bundle_manifest, matrix, run_payload = _fake_pipeline(monkeypatch)
    destination = tmp_path / "campaign-read"
    manifest = write_fast_deterministic_campaign_artifact(
        database_path=tmp_path / "observer.db",
        feature_dataset=object(),
        catalog=_catalog(),
        champion_path=tmp_path / "champion.json",
        execution_policy=object(),
        contexts=(object(),),
        entry_authority_binary_path=tmp_path / "entry-authority",
        candidate_binary_path=tmp_path / "candidate-row",
        paper_run_id_prefix="fl9-real",
        assessment_version="assessment-v1",
        starting_ledger=object(),
        fill_policy=object(),
        risk_policy=object(),
        position_policy=object(),
        evaluation_policy=object(),
        destination=destination,
    )

    fake_bundle = SimpleNamespace(manifest=bundle_manifest)
    fake_runs = tuple(
        SimpleNamespace(
            candidate_version=value.candidate_version,
            candidate_fingerprint_sha256=value.candidate_fingerprint_sha256,
            event_population_fingerprint_sha256=(
                matrix.event_population_fingerprint_sha256
            ),
        )
        for value in _catalog().candidates
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "read_fast_deterministic_comparison_evidence_bundle",
        lambda path: fake_bundle,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.artifact."
        "decode_fast_policy_run_evidence_batch",
        lambda payload: fake_runs,
    )

    artifact = read_fast_deterministic_campaign_artifact(destination)

    assert type(artifact) is FastDeterministicCampaignArtifact
    assert artifact.manifest == manifest
    assert artifact.catalog == _catalog()
    assert artifact.comparison_bundle is fake_bundle
    assert artifact.runs == fake_runs

    run_path = destination / "policy_runs.json"
    run_path.write_text(run_payload + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint|run|file"):
        read_fast_deterministic_campaign_artifact(destination)


def test_campaign_artifact_source_has_no_superiority_promotion_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "artifact.py"
    ).read_text(encoding="utf-8")

    assert "run_fast_deterministic_comparison_catalog_matrix(" in source
    for forbidden in (
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "requests.",
        "httpx",
    ):
        assert forbidden not in source
