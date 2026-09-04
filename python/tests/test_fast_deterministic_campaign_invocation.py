from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_deterministic_campaign import (
    FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_NAME,
    FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_VERSION,
    FastDeterministicCampaignInvocationSeal,
    read_fast_deterministic_campaign_invocation_seal,
    run_fast_deterministic_campaign_invocation_file,
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


def _prepare(monkeypatch, tmp_path: Path, *, mutate: str | None = None):
    request_dir = tmp_path / "request"
    request_dir.mkdir()
    request_path = request_dir / "campaign_request.json"
    request_payload = _canonical({"request": "canonical"})
    request_path.write_text(request_payload, encoding="utf-8")

    paths = {
        "observer_database_path": "evidence/observer.db",
        "feature_parquet_path": "evidence/features.parquet",
        "comparison_catalog_path": "evidence/catalog.json",
        "champion_path": "models/champion.json",
        "entry_authority_binary_path": "bin/entry-authority",
        "candidate_binary_path": "bin/candidate-row",
        "destination_path": "output/campaign",
    }
    for name, relative in paths.items():
        if name == "destination_path":
            continue
        path = request_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name}-bytes".encode("utf-8"))

    observer = request_dir / paths["observer_database_path"]
    observer_wal = Path(f"{observer}-wal")
    observer_wal.write_bytes(b"wal-evidence")
    Path(f"{observer}-shm").write_bytes(b"volatile-lock-state")

    request = SimpleNamespace(
        request_fingerprint_sha256="a" * 64,
        **paths,
    )
    campaign_manifest = SimpleNamespace(
        artifact_fingerprint_sha256="b" * 64,
    )
    campaign = (request_dir / paths["destination_path"]).resolve()

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.invocation."
        "decode_fast_deterministic_campaign_request",
        lambda payload: request,
    )

    def fake_run(path):
        campaign.mkdir(parents=True)
        (campaign / "placeholder").write_text("campaign", encoding="utf-8")
        if mutate is not None:
            target = (request_dir / paths[mutate]).resolve()
            target.write_bytes(target.read_bytes() + b"-changed")
        return campaign_manifest

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.invocation."
        "run_fast_deterministic_campaign_request_file",
        fake_run,
    )
    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.invocation."
        "read_fast_deterministic_campaign_artifact",
        lambda path: SimpleNamespace(manifest=campaign_manifest),
    )
    return (
        request_path,
        request_payload,
        request,
        campaign_manifest,
        campaign,
        observer,
        observer_wal,
    )


def test_invocation_seal_binds_request_sources_and_campaign(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (
        request_path,
        request_payload,
        request,
        campaign_manifest,
        campaign,
        observer,
        observer_wal,
    ) = _prepare(monkeypatch, tmp_path)

    seal = run_fast_deterministic_campaign_invocation_file(request_path)

    assert type(seal) is FastDeterministicCampaignInvocationSeal
    assert seal.manifest.schema_name == (
        FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_NAME
    )
    assert seal.manifest.schema_version == (
        FAST_DETERMINISTIC_CAMPAIGN_INVOCATION_SCHEMA_VERSION
    )
    assert seal.manifest.request_fingerprint_sha256 == (
        request.request_fingerprint_sha256
    )
    assert seal.manifest.request_file_sha256 == _sha256_bytes(
        request_payload.encode("utf-8")
    )
    assert seal.manifest.campaign_artifact_fingerprint_sha256 == (
        campaign_manifest.artifact_fingerprint_sha256
    )
    assert seal.manifest.source_count == 6
    assert len(seal.manifest.invocation_fingerprint_sha256) == 64

    seal_path = Path(f"{campaign}.invocation")
    assert seal.path == seal_path
    assert {value.name for value in seal_path.iterdir()} == {
        "request.json",
        "sources.json",
        "manifest.json",
    }
    assert (seal_path / "request.json").read_text(encoding="utf-8") == (
        request_payload
    )

    sources = json.loads(
        (seal_path / "sources.json").read_text(encoding="utf-8")
    )
    assert (
        (seal_path / "sources.json").read_text(encoding="utf-8")
        == _canonical(sources)
    )
    observer_source = next(
        value
        for value in sources["sources"]
        if value["label"] == "observer_database_path"
    )
    assert tuple(
        value["role"] for value in observer_source["components"]
    ) == ("database", "wal")
    assert observer_source["components"][0]["sha256"] == _sha256_bytes(
        observer.read_bytes()
    )
    assert observer_source["components"][1]["sha256"] == _sha256_bytes(
        observer_wal.read_bytes()
    )
    assert "shm" not in _canonical(observer_source)

    loaded = read_fast_deterministic_campaign_invocation_seal(seal_path)
    assert loaded.manifest == seal.manifest
    assert loaded.request_payload == request_payload
    assert loaded.sources == seal.sources


def test_source_mutation_invalidates_run_and_removes_campaign(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request_path, _, _, _, campaign, _, _ = _prepare(
        monkeypatch,
        tmp_path,
        mutate="champion_path",
    )

    with pytest.raises(ValueError, match="changed|source|fingerprint"):
        run_fast_deterministic_campaign_invocation_file(request_path)

    assert not campaign.exists()
    assert not Path(f"{campaign}.invocation").exists()
    assert not tuple(
        campaign.parent.glob(f".{campaign.name}.invocation-*")
    )


def test_existing_campaign_or_seal_refuses_to_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request_path, _, _, _, campaign, _, _ = _prepare(
        monkeypatch,
        tmp_path,
    )
    campaign.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="campaign"):
        run_fast_deterministic_campaign_invocation_file(request_path)

    campaign.rmdir()
    seal_path = Path(f"{campaign}.invocation")
    seal_path.mkdir(parents=True)
    with pytest.raises(FileExistsError, match="invocation|seal"):
        run_fast_deterministic_campaign_invocation_file(request_path)


def test_invocation_reader_rejects_manifest_tampering(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request_path, _, _, _, campaign, _, _ = _prepare(
        monkeypatch,
        tmp_path,
    )
    seal = run_fast_deterministic_campaign_invocation_file(request_path)
    manifest_path = seal.path / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["campaign_artifact_fingerprint_sha256"] = "c" * 64
    manifest_path.write_text(_canonical(document), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint"):
        read_fast_deterministic_campaign_invocation_seal(seal.path)

    assert campaign.exists()


def test_invocation_source_has_no_network_superiority_promotion_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "invocation.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "requests.",
        "httpx",
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "pickle",
        "eval(",
        "__import__(",
    ):
        assert forbidden not in source
