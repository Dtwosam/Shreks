from __future__ import annotations

from pathlib import Path

import pytest

from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
    Fl9V2ConcentrationSummary,
)
from shreks_brain.fl9_v2_cohort_acceptance.artifact import (
    _load_canonical_json,
    read_fl9_v2_cohort_acceptance,
    write_fl9_v2_cohort_acceptance,
)
from shreks_brain.fl9_v2_cohort_acceptance.builder import (
    _BuiltCohortAcceptance,
    _identity_fingerprint,
)


def _identity(signature: str, sequence: int, mint: str, observed: int):
    return (
        signature,
        0,
        sequence,
        mint,
        "quote-sol",
        "pump_swap",
        observed,
    )


def _semantic() -> _BuiltCohortAcceptance:
    training = _identity("sig-t", 1, "mint-a", 1_000)
    validation = _identity("sig-v", 2, "mint-b", 1_600)
    test = _identity("sig-x", 3, "mint-b", 1_800)
    accepted = (
        Fl9V2AcceptedDecision(
            decision_identity=training,
            partition="training",
            assessment_fingerprint_sha256="a" * 64,
            mint_novelty="not_applicable",
            actor_novelty="not_applicable",
        ),
        Fl9V2AcceptedDecision(
            decision_identity=validation,
            partition="validation",
            assessment_fingerprint_sha256="b" * 64,
            mint_novelty="unseen",
            actor_novelty="unseen",
        ),
        Fl9V2AcceptedDecision(
            decision_identity=test,
            partition="test",
            assessment_fingerprint_sha256="c" * 64,
            mint_novelty="unseen",
            actor_novelty="seen",
        ),
    )
    concentration = Fl9V2ConcentrationSummary(
        row_count=1,
        unique_mint_count=1,
        top1_share=1.0,
        top3_share=1.0,
        top5_share=1.0,
        top10_share=1.0,
        hhi=1.0,
        effective_mint_count=1.0,
    )
    return _BuiltCohortAcceptance(
        latest_session_id=123,
        raw_row_count=3,
        cross_session_duplicate_count=0,
        raw_unique_mint_count=2,
        eligibility_reason_counts=(("eligible", 3),),
        eligible_row_count=3,
        eligible_unique_mint_count=2,
        training_cut_unix_ms=1_600,
        validation_cut_unix_ms=1_800,
        training_raw_row_count=1,
        validation_raw_row_count=1,
        test_raw_row_count=1,
        shared_signature_count=0,
        training_quarantined_row_count=0,
        validation_quarantined_row_count=0,
        test_quarantined_row_count=0,
        training_row_count=1,
        validation_row_count=1,
        test_row_count=1,
        validation_unseen_mint_row_count=1,
        validation_unseen_mint_unique_mint_count=1,
        validation_seen_mint_row_count=0,
        validation_seen_mint_unique_mint_count=0,
        validation_seen_actor_row_count=0,
        validation_unseen_actor_row_count=1,
        validation_null_actor_row_count=0,
        test_unseen_mint_row_count=1,
        test_unseen_mint_unique_mint_count=1,
        test_seen_mint_row_count=0,
        test_seen_mint_unique_mint_count=0,
        test_seen_actor_row_count=1,
        test_unseen_actor_row_count=0,
        test_null_actor_row_count=0,
        structural_floor_passed=True,
        accepted_decisions=accepted,
        quarantined_decisions=(),
        concentration_summaries=(
            ("full_eligible", replace_concentration(concentration, row_count=3, unique_mint_count=2)),
            ("raw_training", concentration),
            ("raw_validation", concentration),
            ("raw_test", concentration),
            ("post_signature_training", concentration),
            ("post_signature_validation", concentration),
            ("post_signature_test", concentration),
            ("unseen_mint_validation", concentration),
            ("unseen_mint_test", concentration),
        ),
        accepted_identity_fingerprint_sha256=_identity_fingerprint(
            (training, validation, test)
        ),
        training_identity_fingerprint_sha256=_identity_fingerprint((training,)),
        validation_identity_fingerprint_sha256=_identity_fingerprint((validation,)),
        test_identity_fingerprint_sha256=_identity_fingerprint((test,)),
        validation_unseen_mint_identity_fingerprint_sha256=_identity_fingerprint((validation,)),
        validation_seen_mint_identity_fingerprint_sha256=_identity_fingerprint(()),
        test_unseen_mint_identity_fingerprint_sha256=_identity_fingerprint((test,)),
        test_seen_mint_identity_fingerprint_sha256=_identity_fingerprint(()),
        signature_quarantine_identity_fingerprint_sha256=_identity_fingerprint(()),
        assessment_evidence_fingerprint_sha256="d" * 64,
    )


def replace_concentration(value, **changes):
    from dataclasses import replace
    result = replace(value, **changes)
    if result.row_count == 3:
        return replace(
            result,
            top1_share=2 / 3,
            top3_share=1.0,
            top5_share=1.0,
            top10_share=1.0,
            hhi=(2 / 3) ** 2 + (1 / 3) ** 2,
            effective_mint_count=1 / ((2 / 3) ** 2 + (1 / 3) ** 2),
        )
    return result


def _write(tmp_path: Path, name: str = "cohort"):
    return write_fl9_v2_cohort_acceptance(
        _semantic(),
        tmp_path / name,
        policy=Fl9V2CohortAcceptancePolicy(),
        floor_policy=Fl9V2CohortEvidenceFloorPolicy(),
    )


def test_artifact_round_trips_exact_three_files(tmp_path) -> None:
    artifact = _write(tmp_path)
    assert {path.name for path in artifact.path.iterdir()} == {
        "manifest.json",
        "accepted-decisions.jsonl",
        "signature-quarantine.jsonl",
    }

    reread = read_fl9_v2_cohort_acceptance(artifact.path)
    assert reread.manifest == artifact.manifest
    assert reread.accepted_decisions == artifact.accepted_decisions
    assert reread.quarantined_decisions == ()
    assert artifact.manifest.structural_floor_passed is True


def test_artifact_bytes_are_deterministic_and_wall_clock_free(tmp_path, monkeypatch) -> None:
    first = _write(tmp_path, "one")

    import time
    monkeypatch.setattr(time, "time", lambda: 9_999_999_999.0)
    second = _write(tmp_path, "two")

    for name in (
        "manifest.json",
        "accepted-decisions.jsonl",
        "signature-quarantine.jsonl",
    ):
        assert (first.path / name).read_bytes() == (
            second.path / name
        ).read_bytes()


def test_artifact_refuses_existing_destination(tmp_path) -> None:
    destination = tmp_path / "cohort"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="exists|overwrite"):
        write_fl9_v2_cohort_acceptance(
            _semantic(),
            destination,
            policy=Fl9V2CohortAcceptancePolicy(),
            floor_policy=Fl9V2CohortEvidenceFloorPolicy(),
        )


def test_reader_rejects_file_hash_tamper_and_unknown_entries(tmp_path) -> None:
    artifact = _write(tmp_path, "tamper")
    accepted = artifact.path / "accepted-decisions.jsonl"
    accepted.write_text(
        accepted.read_text(encoding="utf-8") + "{}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash|fingerprint|canonical"):
        read_fl9_v2_cohort_acceptance(artifact.path)

    clean = _write(tmp_path, "unknown")
    (clean.path / "extra.txt").write_text("no", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown|entries"):
        read_fl9_v2_cohort_acceptance(clean.path)


def test_reader_rejects_symlink_member(tmp_path) -> None:
    artifact = _write(tmp_path)
    target = artifact.path / "accepted-decisions.jsonl"
    payload = target.read_bytes()
    target.unlink()
    external = tmp_path / "external"
    external.write_bytes(payload)
    target.symlink_to(external)

    with pytest.raises(ValueError, match="symlink|regular file"):
        read_fl9_v2_cohort_acceptance(artifact.path)


def test_canonical_json_rejects_raw_json_float_and_duplicate_key() -> None:
    with pytest.raises(ValueError, match="float|canonical"):
        _load_canonical_json('{"x":0.5}\n', label="test")
    with pytest.raises(ValueError, match="duplicate|malformed"):
        _load_canonical_json('{"x":1,"x":1}\n', label="test")
