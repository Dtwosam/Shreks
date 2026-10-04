from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from fast_chronological_fixtures import chronological_bundle
import shreks_brain.fast_first_champion_preselection as preselection_module
from shreks_brain.fast_first_champion_preselection import (
    FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_VERSION,
    build_fast_first_champion_tradable_preselection,
    read_fast_first_champion_tradable_preselection,
)
from shreks_brain.fast_proof_workspace import (
    FAST_PROOF_WORKSPACE_SCHEMA_NAME,
    FAST_PROOF_WORKSPACE_SCHEMA_VERSION,
    FastProofWorkspaceManifest,
    _canonical as _proof_canonical,
    _manifest_document as _proof_manifest_document,
    _sha256_canonical as _proof_sha256_canonical,
)
from shreks_brain.fl9_tradable_universe import (
    FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME,
    FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION,
    Fl9TradableUniverseAssessment,
    fl9_tradable_universe_policy_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    _canonicalize,
    feature_logical_fingerprint_sha256,
)


_SHA = "1" * 64
_INCIDENT_SIGNATURE = (
    "5chWKZyjzvLtZiMtwrxQLmdr2sJ1TgtcK8T1DNnkNByXDZw6"
    "FnrKd8vKpUYGsHWD3SbkfgFEFeYiANwDoXmVDCpx"
)
_INCIDENT_MINT = "5VG4QtDFrYAkM9PFgSkmeU47ba13fb4bWqfTcPNXpump"


class _FakeTradableStore:
    calls: list[dict[str, object]] = []

    def __init__(self, _database_path) -> None:
        pass

    def assess(
        self,
        *,
        mint,
        quote_mint,
        decision_venue,
        decision_observed_at_unix_ms,
        policy,
    ):
        self.calls.append(
            {
                "mint": mint,
                "quote_mint": quote_mint,
                "decision_venue": decision_venue,
                "decision_observed_at_unix_ms": (
                    decision_observed_at_unix_ms
                ),
            }
        )
        policy_fingerprint = (
            fl9_tradable_universe_policy_fingerprint_sha256(policy)
        )
        if mint == _INCIDENT_MINT:
            return Fl9TradableUniverseAssessment(
                schema_name=(
                    FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME
                ),
                schema_version=(
                    FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION
                ),
                policy_version=policy.version,
                policy_fingerprint_sha256=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=(
                    decision_observed_at_unix_ms
                ),
                eligible=False,
                reason="candidate_identity_unavailable",
                graduation_detected_at_unix_ms=(
                    decision_observed_at_unix_ms - 100
                ),
                candidate_id=None,
                snapshot_row_id=None,
                snapshot_observed_at_unix_ms=None,
                snapshot_age_ms=None,
                selected_pair_address=None,
                liquidity_usd=None,
                volume_h24_usd=None,
            )
        candidate_id = 1000 + len(self.calls)
        return Fl9TradableUniverseAssessment(
            schema_name=FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME,
            schema_version=(
                FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION
            ),
            policy_version=policy.version,
            policy_fingerprint_sha256=policy_fingerprint,
            mint=mint,
            quote_mint=quote_mint,
            decision_venue=decision_venue,
            decision_observed_at_unix_ms=decision_observed_at_unix_ms,
            eligible=True,
            reason="eligible",
            graduation_detected_at_unix_ms=(
                decision_observed_at_unix_ms - 500
            ),
            candidate_id=candidate_id,
            snapshot_row_id=2000 + len(self.calls),
            snapshot_observed_at_unix_ms=(
                decision_observed_at_unix_ms - 25
            ),
            snapshot_age_ms=25,
            selected_pair_address=f"pair-{candidate_id}",
            liquidity_usd=10_000.0,
            volume_h24_usd=50_000.0,
        )


def _write_proof_workspace(
    root: Path,
    records,
) -> Path:
    root.mkdir()
    feature_path = root / "features.jsonl"
    with feature_path.open("wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    _canonicalize(asdict(record)),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )
    feature_sha = hashlib.sha256(feature_path.read_bytes()).hexdigest()
    logical = feature_logical_fingerprint_sha256(tuple(records))
    material = {
        "schema_name": FAST_PROOF_WORKSPACE_SCHEMA_NAME,
        "schema_version": FAST_PROOF_WORKSPACE_SCHEMA_VERSION,
        "release_source_sha": "a" * 40,
        "platform": "linux-aarch64",
        "proof_tools_manifest_fingerprint_sha256": "b" * 64,
        "exporter_sha256": "c" * 64,
        "observer_database_sha256": "d" * 64,
        "observer_database_wal_sha256": None,
        "feature_jsonl_sha256": feature_sha,
        "feature_logical_fingerprint_sha256": logical,
        "row_count": len(records),
        "min_decision_sequence": min(
            value.decision_sequence for value in records
        ),
        "max_decision_sequence": max(
            value.decision_sequence for value in records
        ),
        "min_decision_observed_at_unix_ms": min(
            value.decision_observed_at_unix_ms for value in records
        ),
        "max_decision_observed_at_unix_ms": max(
            value.decision_observed_at_unix_ms for value in records
        ),
    }
    manifest = FastProofWorkspaceManifest(
        **material,
        artifact_fingerprint_sha256=_proof_sha256_canonical(material),
    )
    (root / "manifest.json").write_text(
        _proof_canonical(_proof_manifest_document(manifest)),
        encoding="utf-8",
    )
    return root


def _records():
    source = chronological_bundle().features.records[:3]
    first = replace(
        source[0],
        decision_signature="accepted-a",
        decision_sequence=101,
        mint="AcceptedMintA",
        venue="pump_swap",
        decision_observed_at_unix_ms=10_000,
        snapshot_as_of_unix_ms=10_000,
    )
    incident = replace(
        source[1],
        decision_signature=_INCIDENT_SIGNATURE,
        decision_sequence=102,
        mint=_INCIDENT_MINT,
        venue="pump_swap",
        decision_observed_at_unix_ms=10_100,
        snapshot_as_of_unix_ms=10_100,
    )
    third = replace(
        source[2],
        decision_signature="accepted-b",
        decision_sequence=103,
        mint="AcceptedMintB",
        venue="pump_swap",
        decision_observed_at_unix_ms=10_200,
        snapshot_as_of_unix_ms=10_200,
    )
    return (first, incident, third)


def test_preselection_rejects_incident_shape_before_training(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeTradableStore.calls = []
    monkeypatch.setattr(
        preselection_module,
        "Fl9TradableUniverseStore",
        _FakeTradableStore,
    )
    proof = _write_proof_workspace(tmp_path / "proof", _records())
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"stable-observer-fixture")

    artifact = build_fast_first_champion_tradable_preselection(
        proof_workspace_path=proof,
        observer_database_path=database,
        minimum_decision_observed_at_unix_ms=10_000,
        destination=tmp_path / "preselection",
    )

    assert artifact.manifest.schema_name == (
        FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_NAME
    )
    assert artifact.manifest.schema_version == (
        FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_VERSION
    )
    assert artifact.manifest.assessed_row_count == 3
    assert artifact.manifest.eligible_row_count == 2
    assert artifact.manifest.eligibility_reason_counts == (
        ("candidate_identity_unavailable", 1),
        ("eligible", 2),
    )
    assert _INCIDENT_SIGNATURE not in {
        value.decision_signature
        for value in artifact.accepted_decisions
    }
    assert all(
        value.candidate_id > 0 and value.snapshot_row_id > 0
        for value in artifact.accepted_decisions
    )
    assert len(_FakeTradableStore.calls) == 3


def test_preselection_ignores_rows_below_fixed_floor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeTradableStore.calls = []
    monkeypatch.setattr(
        preselection_module,
        "Fl9TradableUniverseStore",
        _FakeTradableStore,
    )
    records = _records()
    proof = _write_proof_workspace(tmp_path / "proof", records)
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"stable-observer-fixture")

    artifact = build_fast_first_champion_tradable_preselection(
        proof_workspace_path=proof,
        observer_database_path=database,
        minimum_decision_observed_at_unix_ms=10_150,
        destination=tmp_path / "preselection",
    )

    assert artifact.manifest.assessed_row_count == 1
    assert artifact.manifest.eligible_row_count == 1
    assert tuple(
        value.decision_signature
        for value in artifact.accepted_decisions
    ) == ("accepted-b",)
    assert len(_FakeTradableStore.calls) == 1


def test_preselection_round_trip_and_candidate_binding_are_strict(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeTradableStore.calls = []
    monkeypatch.setattr(
        preselection_module,
        "Fl9TradableUniverseStore",
        _FakeTradableStore,
    )
    proof = _write_proof_workspace(tmp_path / "proof", _records())
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"stable-observer-fixture")
    destination = tmp_path / "preselection"

    written = build_fast_first_champion_tradable_preselection(
        proof_workspace_path=proof,
        observer_database_path=database,
        minimum_decision_observed_at_unix_ms=10_000,
        destination=destination,
    )
    reopened = read_fast_first_champion_tradable_preselection(
        destination
    )

    assert reopened == written
    assert reopened.candidate_ids_by_identity() == {
        value.decision_identity: value.candidate_id
        for value in reopened.accepted_decisions
    }
    assert len(
        reopened.manifest.accepted_identity_fingerprint_sha256
    ) == 64
    assert len(
        reopened.manifest.candidate_binding_fingerprint_sha256
    ) == 64


def test_preselection_rejects_accepted_file_tamper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeTradableStore.calls = []
    monkeypatch.setattr(
        preselection_module,
        "Fl9TradableUniverseStore",
        _FakeTradableStore,
    )
    proof = _write_proof_workspace(tmp_path / "proof", _records())
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"stable-observer-fixture")
    destination = tmp_path / "preselection"

    build_fast_first_champion_tradable_preselection(
        proof_workspace_path=proof,
        observer_database_path=database,
        minimum_decision_observed_at_unix_ms=10_000,
        destination=destination,
    )
    accepted = destination / "accepted.jsonl"
    accepted.write_text(
        accepted.read_text(encoding="utf-8").replace(
            "AcceptedMintA",
            "TamperedMint",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fingerprint"):
        read_fast_first_champion_tradable_preselection(destination)


def test_preselection_refuses_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeTradableStore.calls = []
    monkeypatch.setattr(
        preselection_module,
        "Fl9TradableUniverseStore",
        _FakeTradableStore,
    )
    proof = _write_proof_workspace(tmp_path / "proof", _records())
    database = tmp_path / "observer.sqlite3"
    database.write_bytes(b"stable-observer-fixture")
    destination = tmp_path / "preselection"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="overwrite|exists"):
        build_fast_first_champion_tradable_preselection(
            proof_workspace_path=proof,
            observer_database_path=database,
            minimum_decision_observed_at_unix_ms=10_000,
            destination=destination,
        )


def test_preselection_source_has_no_target_model_execution_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion_preselection.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "future_return",
        "target_value",
        "model_performance",
        "FastForecastTarget",
        "build_fast_first_champion(",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
    ):
        assert forbidden not in source
