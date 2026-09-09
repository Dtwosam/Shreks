from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from .builder import (
    _BuiltCohortAcceptance,
    _identity_fingerprint,
)
from .models import (
    FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION,
    FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
    Fl9V2AcceptedDecision,
    Fl9V2CohortAcceptanceArtifact,
    Fl9V2CohortAcceptanceManifest,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
    Fl9V2ConcentrationSummary,
    Fl9V2CoverageSessionCheckpoint,
    Fl9V2QuarantinedDecision,
)


_MANIFEST_FILE = "manifest.json"
_ACCEPTED_FILE = "accepted-decisions.jsonl"
_QUARANTINE_FILE = "signature-quarantine.jsonl"
_ROOT_ENTRIES = frozenset(
    {
        _MANIFEST_FILE,
        _ACCEPTED_FILE,
        _QUARANTINE_FILE,
    }
)


def write_fl9_v2_cohort_acceptance(
    semantic: _BuiltCohortAcceptance,
    destination: str | Path,
    *,
    policy: Fl9V2CohortAcceptancePolicy,
    floor_policy: Fl9V2CohortEvidenceFloorPolicy,
) -> Fl9V2CohortAcceptanceArtifact:
    if type(semantic) is not _BuiltCohortAcceptance:
        raise ValueError(
            "semantic must be exact _BuiltCohortAcceptance"
        )
    if type(policy) is not Fl9V2CohortAcceptancePolicy:
        raise ValueError(
            "policy must be exact Fl9V2CohortAcceptancePolicy"
        )
    if type(floor_policy) is not Fl9V2CohortEvidenceFloorPolicy:
        raise ValueError(
            "floor_policy must be exact Fl9V2CohortEvidenceFloorPolicy"
        )

    destination_path = Path(destination).expanduser()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "FL9 V2 cohort destination already exists; overwrite is forbidden"
        )
    destination_path = destination_path.resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.tmp-",
            dir=destination_path.parent,
        )
    )
    staging.chmod(0o700)

    try:
        accepted_path = staging / _ACCEPTED_FILE
        quarantine_path = staging / _QUARANTINE_FILE

        accepted_payload = "".join(
            _canonical_json(_accepted_document(value))
            for value in semantic.accepted_decisions
        )
        quarantine_payload = "".join(
            _canonical_json(_quarantine_document(value))
            for value in semantic.quarantined_decisions
        )

        accepted_path.write_text(accepted_payload, encoding="utf-8")
        quarantine_path.write_text(quarantine_payload, encoding="utf-8")
        accepted_path.chmod(0o600)
        quarantine_path.chmod(0o600)

        accepted_file_sha = _sha256_file_stable(accepted_path)
        quarantine_file_sha = _sha256_file_stable(quarantine_path)

        manifest_material = _manifest_material_from_semantic(
            semantic=semantic,
            policy=policy,
            floor_policy=floor_policy,
            accepted_file_sha256=accepted_file_sha,
            quarantine_file_sha256=quarantine_file_sha,
        )
        artifact_fingerprint = _sha256_canonical(manifest_material)
        manifest_document = dict(manifest_material)
        manifest_document["artifact_fingerprint_sha256"] = artifact_fingerprint

        manifest = _manifest_from_document(manifest_document)
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical_json(_manifest_document(manifest)),
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fl9_v2_cohort_acceptance(staging)
        if (
            verified.manifest != manifest
            or verified.accepted_decisions
            != semantic.accepted_decisions
            or verified.quarantined_decisions
            != semantic.quarantined_decisions
        ):
            raise ValueError(
                "staged FL9 V2 cohort artifact did not round-trip exactly"
            )

        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "FL9 V2 cohort destination appeared during write"
            )
        staging.rename(destination_path)
        return read_fl9_v2_cohort_acceptance(destination_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fl9_v2_cohort_acceptance(
    path: str | Path,
) -> Fl9V2CohortAcceptanceArtifact:
    raw_root = Path(path).expanduser()
    if raw_root.is_symlink():
        raise ValueError(
            "FL9 V2 cohort artifact root cannot be a symlink"
        )
    root = raw_root.resolve()
    if not root.is_dir():
        raise ValueError(
            "FL9 V2 cohort artifact must be an existing real directory"
        )

    entries: set[str] = set()
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "FL9 V2 cohort artifact members must be regular files, not symlinks"
            )
        entries.add(child.name)
    if entries != _ROOT_ENTRIES:
        raise ValueError(
            "FL9 V2 cohort artifact has unknown or missing entries"
        )

    manifest_path = root / _MANIFEST_FILE
    accepted_path = root / _ACCEPTED_FILE
    quarantine_path = root / _QUARANTINE_FILE

    document = _load_canonical_json(
        manifest_path.read_text(encoding="utf-8"),
        label="FL9 V2 cohort manifest",
    )
    manifest = _manifest_from_document(document)

    if _sha256_file_stable(accepted_path) != (
        manifest.accepted_decisions_file_sha256
    ):
        raise ValueError(
            "FL9 V2 cohort accepted-decisions file hash mismatch"
        )
    if _sha256_file_stable(quarantine_path) != (
        manifest.signature_quarantine_file_sha256
    ):
        raise ValueError(
            "FL9 V2 cohort signature-quarantine file hash mismatch"
        )

    claimed_fingerprint = manifest.artifact_fingerprint_sha256
    material = _manifest_document(manifest)
    material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed_fingerprint:
        raise ValueError(
            "FL9 V2 cohort artifact fingerprint mismatch"
        )

    accepted = _read_accepted_jsonl(accepted_path)
    quarantined = _read_quarantine_jsonl(quarantine_path)

    _validate_semantic_reconciliation(
        manifest=manifest,
        accepted=accepted,
        quarantined=quarantined,
    )

    return Fl9V2CohortAcceptanceArtifact(
        path=root,
        manifest=manifest,
        accepted_decisions=accepted,
        quarantined_decisions=quarantined,
    )


def encode_manifest_for_stdout(
    manifest: Fl9V2CohortAcceptanceManifest,
) -> str:
    if type(manifest) is not Fl9V2CohortAcceptanceManifest:
        raise ValueError(
            "manifest must be exact Fl9V2CohortAcceptanceManifest"
        )
    return _canonical_json(_manifest_document(manifest))


def _manifest_material_from_semantic(
    *,
    semantic: _BuiltCohortAcceptance,
    policy: Fl9V2CohortAcceptancePolicy,
    floor_policy: Fl9V2CohortEvidenceFloorPolicy,
    accepted_file_sha256: str,
    quarantine_file_sha256: str,
) -> dict[str, object]:
    return {
        "schema_name": FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME,
        "schema_version": FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION,
        "policy_version": FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
        "floor_policy_version": FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
        "source_session_ids": list(policy.source_session_ids),
        "source_sessions": [
            _session_document(value)
            for value in policy.source_sessions
        ],
        "latest_session_id": semantic.latest_session_id,
        "horizon_ms": policy.horizon_ms,
        "minimum_decision_observed_at_unix_ms": (
            policy.minimum_decision_observed_at_unix_ms
        ),
        "test_end_unix_ms": policy.test_end_unix_ms,
        "selection_at_unix_ms": policy.selection_at_unix_ms,
        "training_cut_unix_ms": semantic.training_cut_unix_ms,
        "validation_cut_unix_ms": semantic.validation_cut_unix_ms,
        "raw_row_count": semantic.raw_row_count,
        "cross_session_duplicate_count": (
            semantic.cross_session_duplicate_count
        ),
        "raw_unique_mint_count": semantic.raw_unique_mint_count,
        "eligibility_reason_counts": [
            [reason, count]
            for reason, count in semantic.eligibility_reason_counts
        ],
        "eligible_row_count": semantic.eligible_row_count,
        "eligible_unique_mint_count": semantic.eligible_unique_mint_count,
        "training_raw_row_count": semantic.training_raw_row_count,
        "validation_raw_row_count": semantic.validation_raw_row_count,
        "test_raw_row_count": semantic.test_raw_row_count,
        "shared_signature_count": semantic.shared_signature_count,
        "training_quarantined_row_count": (
            semantic.training_quarantined_row_count
        ),
        "validation_quarantined_row_count": (
            semantic.validation_quarantined_row_count
        ),
        "test_quarantined_row_count": (
            semantic.test_quarantined_row_count
        ),
        "training_row_count": semantic.training_row_count,
        "validation_row_count": semantic.validation_row_count,
        "test_row_count": semantic.test_row_count,
        "validation_unseen_mint_row_count": (
            semantic.validation_unseen_mint_row_count
        ),
        "validation_unseen_mint_unique_mint_count": (
            semantic.validation_unseen_mint_unique_mint_count
        ),
        "validation_seen_mint_row_count": (
            semantic.validation_seen_mint_row_count
        ),
        "validation_seen_mint_unique_mint_count": (
            semantic.validation_seen_mint_unique_mint_count
        ),
        "validation_seen_actor_row_count": (
            semantic.validation_seen_actor_row_count
        ),
        "validation_unseen_actor_row_count": (
            semantic.validation_unseen_actor_row_count
        ),
        "validation_null_actor_row_count": (
            semantic.validation_null_actor_row_count
        ),
        "test_unseen_mint_row_count": semantic.test_unseen_mint_row_count,
        "test_unseen_mint_unique_mint_count": (
            semantic.test_unseen_mint_unique_mint_count
        ),
        "test_seen_mint_row_count": semantic.test_seen_mint_row_count,
        "test_seen_mint_unique_mint_count": (
            semantic.test_seen_mint_unique_mint_count
        ),
        "test_seen_actor_row_count": semantic.test_seen_actor_row_count,
        "test_unseen_actor_row_count": semantic.test_unseen_actor_row_count,
        "test_null_actor_row_count": semantic.test_null_actor_row_count,
        "structural_floor_passed": semantic.structural_floor_passed,
        "evidence_floor_policy": asdict(floor_policy),
        "concentration_summaries": [
            {
                "name": name,
                "summary": asdict(summary),
            }
            for name, summary in semantic.concentration_summaries
        ],
        "tradable_universe_policy_fingerprint_sha256": (
            policy.tradable_universe_policy_fingerprint_sha256
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            policy.feature_identity_firewall_fingerprint_sha256
        ),
        "accepted_decisions_file_sha256": accepted_file_sha256,
        "signature_quarantine_file_sha256": quarantine_file_sha256,
        "accepted_identity_fingerprint_sha256": (
            semantic.accepted_identity_fingerprint_sha256
        ),
        "training_identity_fingerprint_sha256": (
            semantic.training_identity_fingerprint_sha256
        ),
        "validation_identity_fingerprint_sha256": (
            semantic.validation_identity_fingerprint_sha256
        ),
        "test_identity_fingerprint_sha256": (
            semantic.test_identity_fingerprint_sha256
        ),
        "validation_unseen_mint_identity_fingerprint_sha256": (
            semantic.validation_unseen_mint_identity_fingerprint_sha256
        ),
        "validation_seen_mint_identity_fingerprint_sha256": (
            semantic.validation_seen_mint_identity_fingerprint_sha256
        ),
        "test_unseen_mint_identity_fingerprint_sha256": (
            semantic.test_unseen_mint_identity_fingerprint_sha256
        ),
        "test_seen_mint_identity_fingerprint_sha256": (
            semantic.test_seen_mint_identity_fingerprint_sha256
        ),
        "signature_quarantine_identity_fingerprint_sha256": (
            semantic.signature_quarantine_identity_fingerprint_sha256
        ),
        "assessment_evidence_fingerprint_sha256": (
            semantic.assessment_evidence_fingerprint_sha256
        ),
    }


def _manifest_document(
    value: Fl9V2CohortAcceptanceManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "floor_policy_version": value.floor_policy_version,
        "source_session_ids": list(value.source_session_ids),
        "source_sessions": [
            _session_document(item)
            for item in value.source_sessions
        ],
        "latest_session_id": value.latest_session_id,
        "horizon_ms": value.horizon_ms,
        "minimum_decision_observed_at_unix_ms": (
            value.minimum_decision_observed_at_unix_ms
        ),
        "test_end_unix_ms": value.test_end_unix_ms,
        "selection_at_unix_ms": value.selection_at_unix_ms,
        "training_cut_unix_ms": value.training_cut_unix_ms,
        "validation_cut_unix_ms": value.validation_cut_unix_ms,
        "raw_row_count": value.raw_row_count,
        "cross_session_duplicate_count": (
            value.cross_session_duplicate_count
        ),
        "raw_unique_mint_count": value.raw_unique_mint_count,
        "eligibility_reason_counts": [
            [reason, count]
            for reason, count in value.eligibility_reason_counts
        ],
        "eligible_row_count": value.eligible_row_count,
        "eligible_unique_mint_count": value.eligible_unique_mint_count,
        "training_raw_row_count": value.training_raw_row_count,
        "validation_raw_row_count": value.validation_raw_row_count,
        "test_raw_row_count": value.test_raw_row_count,
        "shared_signature_count": value.shared_signature_count,
        "training_quarantined_row_count": (
            value.training_quarantined_row_count
        ),
        "validation_quarantined_row_count": (
            value.validation_quarantined_row_count
        ),
        "test_quarantined_row_count": value.test_quarantined_row_count,
        "training_row_count": value.training_row_count,
        "validation_row_count": value.validation_row_count,
        "test_row_count": value.test_row_count,
        "validation_unseen_mint_row_count": (
            value.validation_unseen_mint_row_count
        ),
        "validation_unseen_mint_unique_mint_count": (
            value.validation_unseen_mint_unique_mint_count
        ),
        "validation_seen_mint_row_count": (
            value.validation_seen_mint_row_count
        ),
        "validation_seen_mint_unique_mint_count": (
            value.validation_seen_mint_unique_mint_count
        ),
        "validation_seen_actor_row_count": (
            value.validation_seen_actor_row_count
        ),
        "validation_unseen_actor_row_count": (
            value.validation_unseen_actor_row_count
        ),
        "validation_null_actor_row_count": (
            value.validation_null_actor_row_count
        ),
        "test_unseen_mint_row_count": value.test_unseen_mint_row_count,
        "test_unseen_mint_unique_mint_count": (
            value.test_unseen_mint_unique_mint_count
        ),
        "test_seen_mint_row_count": value.test_seen_mint_row_count,
        "test_seen_mint_unique_mint_count": (
            value.test_seen_mint_unique_mint_count
        ),
        "test_seen_actor_row_count": value.test_seen_actor_row_count,
        "test_unseen_actor_row_count": value.test_unseen_actor_row_count,
        "test_null_actor_row_count": value.test_null_actor_row_count,
        "structural_floor_passed": value.structural_floor_passed,
        "evidence_floor_policy": asdict(value.evidence_floor_policy),
        "concentration_summaries": [
            {
                "name": name,
                "summary": asdict(summary),
            }
            for name, summary in value.concentration_summaries
        ],
        "tradable_universe_policy_fingerprint_sha256": (
            value.tradable_universe_policy_fingerprint_sha256
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            value.feature_identity_firewall_fingerprint_sha256
        ),
        "accepted_decisions_file_sha256": (
            value.accepted_decisions_file_sha256
        ),
        "signature_quarantine_file_sha256": (
            value.signature_quarantine_file_sha256
        ),
        "accepted_identity_fingerprint_sha256": (
            value.accepted_identity_fingerprint_sha256
        ),
        "training_identity_fingerprint_sha256": (
            value.training_identity_fingerprint_sha256
        ),
        "validation_identity_fingerprint_sha256": (
            value.validation_identity_fingerprint_sha256
        ),
        "test_identity_fingerprint_sha256": (
            value.test_identity_fingerprint_sha256
        ),
        "validation_unseen_mint_identity_fingerprint_sha256": (
            value.validation_unseen_mint_identity_fingerprint_sha256
        ),
        "validation_seen_mint_identity_fingerprint_sha256": (
            value.validation_seen_mint_identity_fingerprint_sha256
        ),
        "test_unseen_mint_identity_fingerprint_sha256": (
            value.test_unseen_mint_identity_fingerprint_sha256
        ),
        "test_seen_mint_identity_fingerprint_sha256": (
            value.test_seen_mint_identity_fingerprint_sha256
        ),
        "signature_quarantine_identity_fingerprint_sha256": (
            value.signature_quarantine_identity_fingerprint_sha256
        ),
        "assessment_evidence_fingerprint_sha256": (
            value.assessment_evidence_fingerprint_sha256
        ),
        "artifact_fingerprint_sha256": value.artifact_fingerprint_sha256,
    }


def _manifest_from_document(
    document: dict[str, object],
) -> Fl9V2CohortAcceptanceManifest:
    expected_keys = frozenset(
        _manifest_material_from_keys()
        | {"artifact_fingerprint_sha256"}
    )
    if frozenset(document) != expected_keys:
        raise ValueError(
            "FL9 V2 cohort manifest has unknown or missing fields"
        )
    try:
        source_sessions = tuple(
            Fl9V2CoverageSessionCheckpoint(
                session_id=item["session_id"],
                provider=item["provider"],
                process_session_sequence=item[
                    "process_session_sequence"
                ],
                first_notification_observed_at_unix_ms=item[
                    "first_notification_observed_at_unix_ms"
                ],
                last_notification_observed_at_unix_ms=item[
                    "last_notification_observed_at_unix_ms"
                ],
                notification_count=item["notification_count"],
            )
            for item in _require_list_of_dicts(
                "source_sessions",
                document["source_sessions"],
            )
        )
        floor_doc = _require_dict(
            "evidence_floor_policy",
            document["evidence_floor_policy"],
        )
        floor_policy = Fl9V2CohortEvidenceFloorPolicy(
            **floor_doc
        )
        concentrations = tuple(
            (
                item["name"],
                Fl9V2ConcentrationSummary(
                    **_require_dict(
                        "concentration summary",
                        item["summary"],
                    )
                ),
            )
            for item in _require_list_of_dicts(
                "concentration_summaries",
                document["concentration_summaries"],
            )
        )
        return Fl9V2CohortAcceptanceManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            policy_version=document["policy_version"],
            floor_policy_version=document["floor_policy_version"],
            source_session_ids=tuple(
                _require_list_of_ints(
                    "source_session_ids",
                    document["source_session_ids"],
                )
            ),
            source_sessions=source_sessions,
            latest_session_id=document["latest_session_id"],
            horizon_ms=document["horizon_ms"],
            minimum_decision_observed_at_unix_ms=document[
                "minimum_decision_observed_at_unix_ms"
            ],
            test_end_unix_ms=document["test_end_unix_ms"],
            selection_at_unix_ms=document["selection_at_unix_ms"],
            training_cut_unix_ms=document["training_cut_unix_ms"],
            validation_cut_unix_ms=document["validation_cut_unix_ms"],
            raw_row_count=document["raw_row_count"],
            cross_session_duplicate_count=document[
                "cross_session_duplicate_count"
            ],
            raw_unique_mint_count=document["raw_unique_mint_count"],
            eligibility_reason_counts=tuple(
                (item[0], item[1])
                for item in _require_reason_count_list(
                    document["eligibility_reason_counts"]
                )
            ),
            eligible_row_count=document["eligible_row_count"],
            eligible_unique_mint_count=document[
                "eligible_unique_mint_count"
            ],
            training_raw_row_count=document["training_raw_row_count"],
            validation_raw_row_count=document[
                "validation_raw_row_count"
            ],
            test_raw_row_count=document["test_raw_row_count"],
            shared_signature_count=document["shared_signature_count"],
            training_quarantined_row_count=document[
                "training_quarantined_row_count"
            ],
            validation_quarantined_row_count=document[
                "validation_quarantined_row_count"
            ],
            test_quarantined_row_count=document[
                "test_quarantined_row_count"
            ],
            training_row_count=document["training_row_count"],
            validation_row_count=document["validation_row_count"],
            test_row_count=document["test_row_count"],
            validation_unseen_mint_row_count=document[
                "validation_unseen_mint_row_count"
            ],
            validation_unseen_mint_unique_mint_count=document[
                "validation_unseen_mint_unique_mint_count"
            ],
            validation_seen_mint_row_count=document[
                "validation_seen_mint_row_count"
            ],
            validation_seen_mint_unique_mint_count=document[
                "validation_seen_mint_unique_mint_count"
            ],
            validation_seen_actor_row_count=document[
                "validation_seen_actor_row_count"
            ],
            validation_unseen_actor_row_count=document[
                "validation_unseen_actor_row_count"
            ],
            validation_null_actor_row_count=document[
                "validation_null_actor_row_count"
            ],
            test_unseen_mint_row_count=document[
                "test_unseen_mint_row_count"
            ],
            test_unseen_mint_unique_mint_count=document[
                "test_unseen_mint_unique_mint_count"
            ],
            test_seen_mint_row_count=document[
                "test_seen_mint_row_count"
            ],
            test_seen_mint_unique_mint_count=document[
                "test_seen_mint_unique_mint_count"
            ],
            test_seen_actor_row_count=document[
                "test_seen_actor_row_count"
            ],
            test_unseen_actor_row_count=document[
                "test_unseen_actor_row_count"
            ],
            test_null_actor_row_count=document[
                "test_null_actor_row_count"
            ],
            structural_floor_passed=document[
                "structural_floor_passed"
            ],
            evidence_floor_policy=floor_policy,
            concentration_summaries=concentrations,
            tradable_universe_policy_fingerprint_sha256=document[
                "tradable_universe_policy_fingerprint_sha256"
            ],
            feature_identity_firewall_fingerprint_sha256=document[
                "feature_identity_firewall_fingerprint_sha256"
            ],
            accepted_decisions_file_sha256=document[
                "accepted_decisions_file_sha256"
            ],
            signature_quarantine_file_sha256=document[
                "signature_quarantine_file_sha256"
            ],
            accepted_identity_fingerprint_sha256=document[
                "accepted_identity_fingerprint_sha256"
            ],
            training_identity_fingerprint_sha256=document[
                "training_identity_fingerprint_sha256"
            ],
            validation_identity_fingerprint_sha256=document[
                "validation_identity_fingerprint_sha256"
            ],
            test_identity_fingerprint_sha256=document[
                "test_identity_fingerprint_sha256"
            ],
            validation_unseen_mint_identity_fingerprint_sha256=document[
                "validation_unseen_mint_identity_fingerprint_sha256"
            ],
            validation_seen_mint_identity_fingerprint_sha256=document[
                "validation_seen_mint_identity_fingerprint_sha256"
            ],
            test_unseen_mint_identity_fingerprint_sha256=document[
                "test_unseen_mint_identity_fingerprint_sha256"
            ],
            test_seen_mint_identity_fingerprint_sha256=document[
                "test_seen_mint_identity_fingerprint_sha256"
            ],
            signature_quarantine_identity_fingerprint_sha256=document[
                "signature_quarantine_identity_fingerprint_sha256"
            ],
            assessment_evidence_fingerprint_sha256=document[
                "assessment_evidence_fingerprint_sha256"
            ],
            artifact_fingerprint_sha256=document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"FL9 V2 cohort manifest is invalid: {exc}"
        ) from exc


def _manifest_material_from_keys() -> set[str]:
    return {
        "schema_name",
        "schema_version",
        "policy_version",
        "floor_policy_version",
        "source_session_ids",
        "source_sessions",
        "latest_session_id",
        "horizon_ms",
        "minimum_decision_observed_at_unix_ms",
        "test_end_unix_ms",
        "selection_at_unix_ms",
        "training_cut_unix_ms",
        "validation_cut_unix_ms",
        "raw_row_count",
        "cross_session_duplicate_count",
        "raw_unique_mint_count",
        "eligibility_reason_counts",
        "eligible_row_count",
        "eligible_unique_mint_count",
        "training_raw_row_count",
        "validation_raw_row_count",
        "test_raw_row_count",
        "shared_signature_count",
        "training_quarantined_row_count",
        "validation_quarantined_row_count",
        "test_quarantined_row_count",
        "training_row_count",
        "validation_row_count",
        "test_row_count",
        "validation_unseen_mint_row_count",
        "validation_unseen_mint_unique_mint_count",
        "validation_seen_mint_row_count",
        "validation_seen_mint_unique_mint_count",
        "validation_seen_actor_row_count",
        "validation_unseen_actor_row_count",
        "validation_null_actor_row_count",
        "test_unseen_mint_row_count",
        "test_unseen_mint_unique_mint_count",
        "test_seen_mint_row_count",
        "test_seen_mint_unique_mint_count",
        "test_seen_actor_row_count",
        "test_unseen_actor_row_count",
        "test_null_actor_row_count",
        "structural_floor_passed",
        "evidence_floor_policy",
        "concentration_summaries",
        "tradable_universe_policy_fingerprint_sha256",
        "feature_identity_firewall_fingerprint_sha256",
        "accepted_decisions_file_sha256",
        "signature_quarantine_file_sha256",
        "accepted_identity_fingerprint_sha256",
        "training_identity_fingerprint_sha256",
        "validation_identity_fingerprint_sha256",
        "test_identity_fingerprint_sha256",
        "validation_unseen_mint_identity_fingerprint_sha256",
        "validation_seen_mint_identity_fingerprint_sha256",
        "test_unseen_mint_identity_fingerprint_sha256",
        "test_seen_mint_identity_fingerprint_sha256",
        "signature_quarantine_identity_fingerprint_sha256",
        "assessment_evidence_fingerprint_sha256",
    }


def _session_document(
    value: Fl9V2CoverageSessionCheckpoint,
) -> dict[str, object]:
    return {
        "session_id": value.session_id,
        "provider": value.provider,
        "process_session_sequence": value.process_session_sequence,
        "first_notification_observed_at_unix_ms": (
            value.first_notification_observed_at_unix_ms
        ),
        "last_notification_observed_at_unix_ms": (
            value.last_notification_observed_at_unix_ms
        ),
        "notification_count": value.notification_count,
    }


def _accepted_document(
    value: Fl9V2AcceptedDecision,
) -> dict[str, object]:
    if type(value) is not Fl9V2AcceptedDecision:
        raise ValueError(
            "accepted JSONL values must be exact accepted decisions"
        )
    return {
        "decision_identity": list(value.decision_identity),
        "partition": value.partition,
        "assessment_fingerprint_sha256": (
            value.assessment_fingerprint_sha256
        ),
        "mint_novelty": value.mint_novelty,
        "actor_novelty": value.actor_novelty,
    }


def _quarantine_document(
    value: Fl9V2QuarantinedDecision,
) -> dict[str, object]:
    if type(value) is not Fl9V2QuarantinedDecision:
        raise ValueError(
            "quarantine JSONL values must be exact quarantined decisions"
        )
    return {
        "decision_identity": list(value.decision_identity),
        "partition": value.partition,
        "shared_signature": value.shared_signature,
    }


def _read_accepted_jsonl(
    path: Path,
) -> tuple[Fl9V2AcceptedDecision, ...]:
    payload = path.read_text(encoding="utf-8")
    if not payload:
        raise ValueError(
            "FL9 V2 cohort accepted-decisions JSONL cannot be empty"
        )
    values: list[Fl9V2AcceptedDecision] = []
    for index, line in enumerate(payload.splitlines(keepends=True), start=1):
        document = _load_canonical_json(
            line,
            label=f"accepted-decisions line {index}",
        )
        if frozenset(document) != {
            "decision_identity",
            "partition",
            "assessment_fingerprint_sha256",
            "mint_novelty",
            "actor_novelty",
        }:
            raise ValueError(
                "accepted-decisions JSONL has unknown or missing fields"
            )
        try:
            values.append(
                Fl9V2AcceptedDecision(
                    decision_identity=tuple(
                        _require_list(
                            "decision_identity",
                            document["decision_identity"],
                        )
                    ),
                    partition=document["partition"],
                    assessment_fingerprint_sha256=document[
                        "assessment_fingerprint_sha256"
                    ],
                    mint_novelty=document["mint_novelty"],
                    actor_novelty=document["actor_novelty"],
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"accepted-decisions JSONL line {index} is invalid: {exc}"
            ) from exc
    result = tuple(values)
    if result != tuple(
        sorted(result, key=lambda item: _identity_sort_key(item.decision_identity))
    ):
        raise ValueError(
            "accepted-decisions JSONL is not in canonical identity order"
        )
    if len({value.decision_identity for value in result}) != len(result):
        raise ValueError(
            "accepted-decisions JSONL contains duplicate identities"
        )
    return result


def _read_quarantine_jsonl(
    path: Path,
) -> tuple[Fl9V2QuarantinedDecision, ...]:
    payload = path.read_text(encoding="utf-8")
    if not payload:
        return ()
    values: list[Fl9V2QuarantinedDecision] = []
    for index, line in enumerate(payload.splitlines(keepends=True), start=1):
        document = _load_canonical_json(
            line,
            label=f"signature-quarantine line {index}",
        )
        if frozenset(document) != {
            "decision_identity",
            "partition",
            "shared_signature",
        }:
            raise ValueError(
                "signature-quarantine JSONL has unknown or missing fields"
            )
        try:
            values.append(
                Fl9V2QuarantinedDecision(
                    decision_identity=tuple(
                        _require_list(
                            "decision_identity",
                            document["decision_identity"],
                        )
                    ),
                    partition=document["partition"],
                    shared_signature=document["shared_signature"],
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"signature-quarantine JSONL line {index} is invalid: {exc}"
            ) from exc
    result = tuple(values)
    if result != tuple(
        sorted(result, key=lambda item: _identity_sort_key(item.decision_identity))
    ):
        raise ValueError(
            "signature-quarantine JSONL is not in canonical identity order"
        )
    if len({value.decision_identity for value in result}) != len(result):
        raise ValueError(
            "signature-quarantine JSONL contains duplicate identities"
        )
    return result


def _validate_semantic_reconciliation(
    *,
    manifest: Fl9V2CohortAcceptanceManifest,
    accepted: tuple[Fl9V2AcceptedDecision, ...],
    quarantined: tuple[Fl9V2QuarantinedDecision, ...],
) -> None:
    accepted_identities = tuple(
        value.decision_identity for value in accepted
    )
    if _identity_fingerprint(accepted_identities) != (
        manifest.accepted_identity_fingerprint_sha256
    ):
        raise ValueError(
            "accepted identity fingerprint does not reconcile"
        )

    by_partition = {
        role: tuple(
            value.decision_identity
            for value in accepted
            if value.partition == role
        )
        for role in ("training", "validation", "test")
    }
    expected_partition_fingerprints = {
        "training": manifest.training_identity_fingerprint_sha256,
        "validation": manifest.validation_identity_fingerprint_sha256,
        "test": manifest.test_identity_fingerprint_sha256,
    }
    for role, identities in by_partition.items():
        if _identity_fingerprint(identities) != (
            expected_partition_fingerprints[role]
        ):
            raise ValueError(
                f"{role} identity fingerprint does not reconcile"
            )

    validation_unseen = tuple(
        value.decision_identity
        for value in accepted
        if (
            value.partition == "validation"
            and value.mint_novelty == "unseen"
        )
    )
    validation_seen = tuple(
        value.decision_identity
        for value in accepted
        if (
            value.partition == "validation"
            and value.mint_novelty == "seen"
        )
    )
    test_unseen = tuple(
        value.decision_identity
        for value in accepted
        if value.partition == "test" and value.mint_novelty == "unseen"
    )
    test_seen = tuple(
        value.decision_identity
        for value in accepted
        if value.partition == "test" and value.mint_novelty == "seen"
    )
    fingerprint_checks = (
        (
            validation_unseen,
            manifest.validation_unseen_mint_identity_fingerprint_sha256,
            "validation unseen-mint",
        ),
        (
            validation_seen,
            manifest.validation_seen_mint_identity_fingerprint_sha256,
            "validation seen-mint",
        ),
        (
            test_unseen,
            manifest.test_unseen_mint_identity_fingerprint_sha256,
            "TEST unseen-mint",
        ),
        (
            test_seen,
            manifest.test_seen_mint_identity_fingerprint_sha256,
            "TEST seen-mint",
        ),
        (
            tuple(value.decision_identity for value in quarantined),
            manifest.signature_quarantine_identity_fingerprint_sha256,
            "signature quarantine",
        ),
    )
    for identities, claimed, label in fingerprint_checks:
        if _identity_fingerprint(identities) != claimed:
            raise ValueError(
                f"{label} identity fingerprint does not reconcile"
            )

    partition_counts = {
        role: sum(1 for value in accepted if value.partition == role)
        for role in ("training", "validation", "test")
    }
    if partition_counts != {
        "training": manifest.training_row_count,
        "validation": manifest.validation_row_count,
        "test": manifest.test_row_count,
    }:
        raise ValueError(
            "accepted partition counts do not reconcile to manifest"
        )

    quarantine_counts = {
        role: sum(1 for value in quarantined if value.partition == role)
        for role in ("training", "validation", "test")
    }
    if quarantine_counts != {
        "training": manifest.training_quarantined_row_count,
        "validation": manifest.validation_quarantined_row_count,
        "test": manifest.test_quarantined_row_count,
    }:
        raise ValueError(
            "quarantine partition counts do not reconcile to manifest"
        )
    if len(accepted) + len(quarantined) != manifest.eligible_row_count:
        raise ValueError(
            "accepted/quarantined identity counts do not reconcile to eligible rows"
        )

    _reconcile_novelty_counts(manifest, accepted)


def _reconcile_novelty_counts(
    manifest: Fl9V2CohortAcceptanceManifest,
    accepted: tuple[Fl9V2AcceptedDecision, ...],
) -> None:
    for partition in ("validation", "test"):
        rows = tuple(
            value for value in accepted
            if value.partition == partition
        )
        unseen = tuple(
            value for value in rows
            if value.mint_novelty == "unseen"
        )
        seen = tuple(
            value for value in rows
            if value.mint_novelty == "seen"
        )
        counts = {
            "unseen_rows": len(unseen),
            "unseen_mints": len(
                {value.decision_identity[3] for value in unseen}
            ),
            "seen_rows": len(seen),
            "seen_mints": len(
                {value.decision_identity[3] for value in seen}
            ),
            "seen_actor": sum(
                1 for value in rows
                if value.actor_novelty == "seen"
            ),
            "unseen_actor": sum(
                1 for value in rows
                if value.actor_novelty == "unseen"
            ),
            "null_actor": sum(
                1 for value in rows
                if value.actor_novelty == "null"
            ),
        }
        prefix = (
            "validation"
            if partition == "validation"
            else "test"
        )
        expected = {
            "unseen_rows": getattr(
                manifest,
                f"{prefix}_unseen_mint_row_count",
            ),
            "unseen_mints": getattr(
                manifest,
                f"{prefix}_unseen_mint_unique_mint_count",
            ),
            "seen_rows": getattr(
                manifest,
                f"{prefix}_seen_mint_row_count",
            ),
            "seen_mints": getattr(
                manifest,
                f"{prefix}_seen_mint_unique_mint_count",
            ),
            "seen_actor": getattr(
                manifest,
                f"{prefix}_seen_actor_row_count",
            ),
            "unseen_actor": getattr(
                manifest,
                f"{prefix}_unseen_actor_row_count",
            ),
            "null_actor": getattr(
                manifest,
                f"{prefix}_null_actor_row_count",
            ),
        }
        if counts != expected:
            raise ValueError(
                f"{partition} novelty counts do not reconcile to manifest"
            )


def _load_canonical_json(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            f"{label} must have exactly one trailing newline"
        )
    try:
        value = json.loads(
            payload,
            parse_float=_reject_raw_json_float,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed or noncanonical JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    decoded = _decode_canonical_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    if _canonical_json(decoded) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return decoded


def _canonical_json(value: object) -> str:
    return (
        json.dumps(
            _encode_canonical_value(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _encode_canonical_value(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "canonical JSON rejects non-finite float"
            )
        return {"__float_hex__": value.hex()}
    if isinstance(value, dict):
        return {
            key: _encode_canonical_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [
            _encode_canonical_value(item)
            for item in value
        ]
    if isinstance(value, list):
        return [
            _encode_canonical_value(item)
            for item in value
        ]
    return value


def _decode_canonical_value(value: object) -> object:
    if isinstance(value, dict):
        if frozenset(value) == {"__float_hex__"}:
            raw = value["__float_hex__"]
            if not isinstance(raw, str):
                raise ValueError(
                    "tagged float hex value must be text"
                )
            try:
                result = float.fromhex(raw)
            except ValueError as exc:
                raise ValueError(
                    "tagged float hex value is invalid"
                ) from exc
            if not math.isfinite(result) or result.hex() != raw:
                raise ValueError(
                    "tagged float hex value is noncanonical"
                )
            return result
        return {
            key: _decode_canonical_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _decode_canonical_value(item)
            for item in value
        ]
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"duplicate JSON key is forbidden: {key}"
            )
        result[key] = value
    return result


def _reject_raw_json_float(value: str) -> None:
    raise ValueError(
        f"raw JSON float is forbidden; use tagged hex encoding: {value}"
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"artifact member must be an existing regular file: {path}"
        )
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "artifact member changed while fingerprinting"
        )
    return digest.hexdigest()


def _identity_sort_key(
    identity: tuple[object, ...],
) -> tuple[object, ...]:
    return (
        identity[6],
        identity[2],
        identity[0],
        identity[1],
    )


def _require_dict(
    name: str,
    value: object,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(
    name: str,
    value: object,
) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _require_list_of_dicts(
    name: str,
    value: object,
) -> list[dict[str, object]]:
    rows = _require_list(name, value)
    if not all(isinstance(item, dict) for item in rows):
        raise ValueError(f"{name} must contain objects")
    return rows  # type: ignore[return-value]


def _require_list_of_ints(
    name: str,
    value: object,
) -> list[int]:
    rows = _require_list(name, value)
    if not all(
        isinstance(item, int) and not isinstance(item, bool)
        for item in rows
    ):
        raise ValueError(f"{name} must contain integers")
    return rows  # type: ignore[return-value]


def _require_reason_count_list(
    value: object,
) -> list[list[object]]:
    rows = _require_list("eligibility_reason_counts", value)
    if not all(
        isinstance(item, list)
        and len(item) == 2
        and isinstance(item[0], str)
        and isinstance(item[1], int)
        and not isinstance(item[1], bool)
        for item in rows
    ):
        raise ValueError(
            "eligibility_reason_counts is malformed"
        )
    return rows  # type: ignore[return-value]
