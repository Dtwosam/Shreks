from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shreks_brain.shadow import (
    ShadowDecisionPolicy,
    ShadowEvidenceStore,
    evaluate_shadow_challenger,
)

from test_shadow_engine import model, registered_candidate, registry_with, row


def decision(
    *,
    candidate_version: str = "challenger-v1",
    mint: str = "mint-a",
    as_of: int = 5_000,
    policy_version: str = "shadow-policy-v1",
):
    artifact = model(version=f"{candidate_version}-model")
    candidate = registered_candidate(
        artifact,
        candidate_version=candidate_version,
        registered_at=4_500,
    )
    registry = registry_with(candidate)
    input_row = row(as_of=as_of)
    input_row["candidate_mint"] = mint
    return evaluate_shadow_challenger(
        registry,
        candidate.candidate_version,
        artifact,
        input_row,
        ShadowDecisionPolicy(policy_version, 0.8),
    )


def test_missing_store_loads_empty_valid_ledger_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "shadow" / "ledger.json"
    ledger = ShadowEvidenceStore(path).load()

    assert ledger.records == ()
    assert len(ledger.ledger_fingerprint_sha256) == 64
    assert not path.exists()


def test_append_round_trip_is_canonical_ordered_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "shadow.json"
    store = ShadowEvidenceStore(path)

    later = decision(candidate_version="challenger-v2", mint="mint-b", as_of=6_000)
    earlier = decision(candidate_version="challenger-v1", mint="mint-a", as_of=5_000)
    first = store.append(later)
    second = store.append(earlier)
    loaded = ShadowEvidenceStore(path).load()

    assert loaded == second
    assert first.ledger_fingerprint_sha256 != second.ledger_fingerprint_sha256
    assert tuple(record.candidate_version for record in loaded.records) == (
        "challenger-v1",
        "challenger-v2",
    )
    assert not path.with_name(path.name + ".tmp").exists()

    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert raw == json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ) + "\n"


def test_identical_append_is_byte_for_byte_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "shadow.json"
    store = ShadowEvidenceStore(path)
    item = decision()

    first = store.append(item)
    before = path.read_bytes()
    second = store.append(item)

    assert second == first
    assert path.read_bytes() == before


def test_same_decision_identity_with_different_material_fails_closed(tmp_path: Path) -> None:
    store = ShadowEvidenceStore(tmp_path / "shadow.json")
    item = decision()
    store.append(item)

    conflict = replace(
        item,
        strategy_version="different-strategy",
        record_fingerprint_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="record fingerprint"):
        store.append(conflict)


def test_validly_fingerprinted_conflicting_identity_fails_closed(tmp_path: Path) -> None:
    from shreks_brain.shadow.fingerprint import record_fingerprint

    store = ShadowEvidenceStore(tmp_path / "shadow.json")
    item = decision()
    store.append(item)

    draft = replace(
        item,
        strategy_version="different-strategy",
        record_fingerprint_sha256="0" * 64,
    )
    conflict = replace(
        draft,
        record_fingerprint_sha256=record_fingerprint(draft),
    )
    with pytest.raises(ValueError, match="decision identity"):
        store.append(conflict)


def test_load_rejects_invalid_json_unknown_fields_and_tampered_record(tmp_path: Path) -> None:
    path = tmp_path / "shadow.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="shadow evidence file"):
        ShadowEvidenceStore(path).load()

    path.unlink()
    ShadowEvidenceStore(path).append(decision())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unknown"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        ShadowEvidenceStore(path).load()

    path.unlink()
    ShadowEvidenceStore(path).append(decision())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"][0]["strategy_version"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="record fingerprint"):
        ShadowEvidenceStore(path).load()


def test_load_rejects_tampered_ledger_fingerprint_and_invalid_schema(tmp_path: Path) -> None:
    path = tmp_path / "shadow.json"
    ShadowEvidenceStore(path).append(decision())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["ledger_fingerprint_sha256"] = "f" * 64
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="ledger fingerprint"):
        ShadowEvidenceStore(path).load()

    path.unlink()
    ShadowEvidenceStore(path).append(decision())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = "wrong"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        ShadowEvidenceStore(path).load()


def test_store_rejects_wrong_record_type_and_has_no_history_rewrite_surface(tmp_path: Path) -> None:
    store = ShadowEvidenceStore(tmp_path / "shadow.json")
    with pytest.raises(ValueError, match="ShadowDecisionRecord"):
        store.append(object())  # type: ignore[arg-type]

    assert not hasattr(store, "delete")
    assert not hasattr(store, "rewrite_history")
    assert not hasattr(store, "promote")
