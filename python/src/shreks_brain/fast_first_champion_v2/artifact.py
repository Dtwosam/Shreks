from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_champion import (
    read_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    read_fast_forecast_evaluation_report,
    write_fast_forecast_evaluation_report,
)
from shreks_brain.fast_learning import (
    FastForecastModelFamily,
    FastForecastTarget,
)

from .models import (
    FAST_FIRST_CHAMPION_V2_POLICY_VERSION,
    FAST_FIRST_CHAMPION_V2_SCHEMA_NAME,
    FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION,
    FastFirstChampionV2BuildResult,
    FastFirstChampionV2EvidenceArtifact,
    FastFirstChampionV2EvidenceManifest,
    FastFirstChampionV2MemberEvidence,
    FastFirstChampionV2Policy,
)


_MANIFEST = "manifest.json"
_CHAMPION = "champion.json"
_EVIDENCE = "v2-evidence.json"
_NATURAL_DIR = "natural-test"
_UNSEEN_DIR = "unseen-mint-test"


def write_fast_first_champion_v2_evidence(
    build: FastFirstChampionV2BuildResult,
    destination: str | Path,
    *,
    policy: FastFirstChampionV2Policy | None = None,
) -> FastFirstChampionV2EvidenceArtifact:
    active_policy = policy or FastFirstChampionV2Policy()
    if type(active_policy) is not FastFirstChampionV2Policy:
        raise ValueError(
            "policy must be exact FastFirstChampionV2Policy"
        )
    if type(build) is not FastFirstChampionV2BuildResult:
        raise ValueError(
            "build must be exact FastFirstChampionV2BuildResult"
        )
    _validate_build_against_policy(build, active_policy)

    target = Path(destination).expanduser()
    if target.exists() or target.is_symlink():
        raise FileExistsError(
            "V2 first-champion evidence destination already exists; "
            "overwrite is forbidden"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.staging-",
            dir=target.parent,
        )
    )
    committed = False
    try:
        natural_dir = staging / _NATURAL_DIR
        unseen_dir = staging / _UNSEEN_DIR
        natural_dir.mkdir()
        unseen_dir.mkdir()

        write_fast_forecast_champion(
            build.champion,
            staging / _CHAMPION,
        )
        for evidence, natural, unseen in zip(
            build.member_evidence,
            build.natural_test_reports,
            build.unseen_mint_test_reports,
            strict=True,
        ):
            key = _member_key(evidence)
            write_fast_forecast_evaluation_report(
                natural,
                natural_dir / f"{key}.json",
            )
            write_fast_forecast_evaluation_report(
                unseen,
                unseen_dir / f"{key}.json",
            )

        evidence_payload = _evidence_payload(
            build,
            active_policy,
            fingerprint="0" * 64,
        )
        evidence_fingerprint = _sha256_json(
            {
                key: value
                for key, value in evidence_payload.items()
                if key != "evidence_fingerprint_sha256"
            }
        )
        evidence_payload["evidence_fingerprint_sha256"] = (
            evidence_fingerprint
        )
        _write_json(staging / _EVIDENCE, evidence_payload)

        file_sha = tuple(
            sorted(
                (
                    path.relative_to(staging).as_posix(),
                    _sha256_file(path),
                )
                for path in staging.rglob("*")
                if path.is_file()
            )
        )
        provisional = FastFirstChampionV2EvidenceManifest(
            schema_name=FAST_FIRST_CHAMPION_V2_SCHEMA_NAME,
            schema_version=FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION,
            policy_version=FAST_FIRST_CHAMPION_V2_POLICY_VERSION,
            cohort_artifact_fingerprint_sha256=(
                build.cohort_artifact_fingerprint_sha256
            ),
            accepted_identity_fingerprint_sha256=(
                build.accepted_identity_fingerprint_sha256
            ),
            training_bundle_fingerprint_sha256=(
                build.training_bundle_fingerprint_sha256
            ),
            feature_identity_firewall_fingerprint_sha256=(
                active_policy.feature_identity_firewall_fingerprint_sha256
            ),
            selection_at_unix_ms=active_policy.selection_at_unix_ms,
            champion_fingerprint_sha256=(
                build.champion.champion_fingerprint_sha256
            ),
            member_evidence=build.member_evidence,
            file_sha256=file_sha,
            artifact_fingerprint_sha256="0" * 64,
        )
        manifest = replace(
            provisional,
            artifact_fingerprint_sha256=(
                _manifest_fingerprint(provisional)
            ),
        )
        _write_json(
            staging / _MANIFEST,
            _manifest_payload(manifest),
        )

        os.replace(staging, target)
        committed = True
        return read_fast_first_champion_v2_evidence(target)
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def read_fast_first_champion_v2_evidence(
    path: str | Path,
) -> FastFirstChampionV2EvidenceArtifact:
    root = Path(path).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "V2 first-champion evidence path must be a regular directory"
        )

    expected_files = _expected_relative_files()
    actual_files: set[str] = set()
    for item in root.rglob("*"):
        if item.is_symlink():
            raise ValueError(
                "V2 first-champion evidence cannot contain symlinks"
            )
        if item.is_file():
            actual_files.add(item.relative_to(root).as_posix())
        elif not item.is_dir():
            raise ValueError(
                "V2 first-champion evidence contains non-regular entry"
            )
    if actual_files != expected_files:
        raise ValueError(
            "V2 first-champion evidence file set is incompatible"
        )

    raw_manifest = _load_json(root / _MANIFEST)
    manifest = _manifest_from_payload(raw_manifest)
    if _manifest_fingerprint(manifest) != (
        manifest.artifact_fingerprint_sha256
    ):
        raise ValueError(
            "V2 first-champion artifact fingerprint is invalid"
        )

    recorded = dict(manifest.file_sha256)
    if set(recorded) != expected_files - {_MANIFEST}:
        raise ValueError(
            "V2 first-champion manifest file hash set is incompatible"
        )
    for relative, expected_sha in recorded.items():
        if _sha256_file(root / relative) != expected_sha:
            raise ValueError(
                f"V2 first-champion file hash mismatch: {relative}"
            )

    champion = read_fast_forecast_champion(root / _CHAMPION)
    if champion.champion_fingerprint_sha256 != (
        manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "V2 evidence champion fingerprint does not match manifest"
        )
    if champion.selection.decided_at_unix_ms != (
        manifest.selection_at_unix_ms
    ):
        raise ValueError(
            "V2 evidence champion selection timestamp does not match manifest"
        )
    if champion.training_bundle_fingerprint_sha256 != (
        manifest.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "V2 evidence champion training bundle does not match manifest"
        )

    natural_reports = []
    unseen_reports = []
    for evidence in manifest.member_evidence:
        key = _member_key(evidence)
        natural = read_fast_forecast_evaluation_report(
            root / _NATURAL_DIR / f"{key}.json"
        )
        unseen = read_fast_forecast_evaluation_report(
            root / _UNSEEN_DIR / f"{key}.json"
        )
        _validate_report_pair(
            evidence,
            natural,
            unseen,
            training_bundle_fingerprint_sha256=(
                manifest.training_bundle_fingerprint_sha256
            ),
        )
        _validate_champion_member(
            champion,
            evidence,
            natural,
        )
        natural_reports.append(natural)
        unseen_reports.append(unseen)

    raw_evidence = _load_json(root / _EVIDENCE)
    _validate_evidence_payload(
        raw_evidence,
        manifest,
    )

    return FastFirstChampionV2EvidenceArtifact(
        path=root,
        manifest=manifest,
        champion=champion,
        natural_test_reports=tuple(natural_reports),
        unseen_mint_test_reports=tuple(unseen_reports),
    )


def _validate_build_against_policy(
    build: FastFirstChampionV2BuildResult,
    policy: FastFirstChampionV2Policy,
) -> None:
    if build.policy_version != policy.version:
        raise ValueError("V2 build policy version mismatch")
    if build.cohort_artifact_fingerprint_sha256 != (
        policy.expected_cohort_artifact_fingerprint_sha256
    ):
        raise ValueError("V2 build cohort artifact fingerprint mismatch")
    if build.accepted_identity_fingerprint_sha256 != (
        policy.expected_accepted_identity_fingerprint_sha256
    ):
        raise ValueError("V2 build accepted identity fingerprint mismatch")
    if build.champion.selection.decided_at_unix_ms != (
        policy.selection_at_unix_ms
    ):
        raise ValueError("V2 champion selection timestamp mismatch")
    if tuple(
        (value.target, value.model_family)
        for value in build.member_evidence
    ) != policy.required_members:
        raise ValueError("V2 build member evidence population mismatch")


def _member_key(evidence: FastFirstChampionV2MemberEvidence) -> str:
    return f"{evidence.target.value}@{evidence.horizon_ms}ms"


def _expected_relative_files() -> set[str]:
    policy = FastFirstChampionV2Policy()
    keys = tuple(
        f"{target.value}@{policy.horizon_ms}ms"
        for target, _ in policy.required_members
    )
    return {
        _MANIFEST,
        _CHAMPION,
        _EVIDENCE,
        *(f"{_NATURAL_DIR}/{key}.json" for key in keys),
        *(f"{_UNSEEN_DIR}/{key}.json" for key in keys),
    }


def _member_payload(
    value: FastFirstChampionV2MemberEvidence,
) -> dict[str, object]:
    return {
        "target": value.target.value,
        "model_family": value.model_family.value,
        "horizon_ms": value.horizon_ms,
        "runtime_artifact_fingerprint_sha256": (
            value.runtime_artifact_fingerprint_sha256
        ),
        "generalization_run_fingerprint_sha256": (
            value.generalization_run_fingerprint_sha256
        ),
        "natural_test_report_fingerprint_sha256": (
            value.natural_test_report_fingerprint_sha256
        ),
        "natural_test_scored_observation_count": (
            value.natural_test_scored_observation_count
        ),
        "natural_test_target_unavailable_count": (
            value.natural_test_target_unavailable_count
        ),
        "unseen_mint_test_report_fingerprint_sha256": (
            value.unseen_mint_test_report_fingerprint_sha256
        ),
        "unseen_mint_test_scored_observation_count": (
            value.unseen_mint_test_scored_observation_count
        ),
        "unseen_mint_test_target_unavailable_count": (
            value.unseen_mint_test_target_unavailable_count
        ),
        "unseen_mint_test_identity_fingerprint_sha256": (
            value.unseen_mint_test_identity_fingerprint_sha256
        ),
    }


def _member_from_payload(
    payload: object,
) -> FastFirstChampionV2MemberEvidence:
    if not isinstance(payload, dict):
        raise ValueError("V2 member evidence must be an object")
    expected = set(_member_payload(_placeholder_member()))
    if set(payload) != expected:
        raise ValueError("V2 member evidence keys are incompatible")
    try:
        return FastFirstChampionV2MemberEvidence(
            target=FastForecastTarget(payload["target"]),
            model_family=FastForecastModelFamily(payload["model_family"]),
            horizon_ms=payload["horizon_ms"],
            runtime_artifact_fingerprint_sha256=payload[
                "runtime_artifact_fingerprint_sha256"
            ],
            generalization_run_fingerprint_sha256=payload[
                "generalization_run_fingerprint_sha256"
            ],
            natural_test_report_fingerprint_sha256=payload[
                "natural_test_report_fingerprint_sha256"
            ],
            natural_test_scored_observation_count=payload[
                "natural_test_scored_observation_count"
            ],
            natural_test_target_unavailable_count=payload[
                "natural_test_target_unavailable_count"
            ],
            unseen_mint_test_report_fingerprint_sha256=payload[
                "unseen_mint_test_report_fingerprint_sha256"
            ],
            unseen_mint_test_scored_observation_count=payload[
                "unseen_mint_test_scored_observation_count"
            ],
            unseen_mint_test_target_unavailable_count=payload[
                "unseen_mint_test_target_unavailable_count"
            ],
            unseen_mint_test_identity_fingerprint_sha256=payload[
                "unseen_mint_test_identity_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("V2 member evidence content is incompatible") from exc


def _placeholder_member() -> FastFirstChampionV2MemberEvidence:
    policy = FastFirstChampionV2Policy()
    target, family = policy.required_members[0]
    return FastFirstChampionV2MemberEvidence(
        target=target,
        model_family=family,
        horizon_ms=policy.horizon_ms,
        runtime_artifact_fingerprint_sha256="0" * 64,
        generalization_run_fingerprint_sha256="0" * 64,
        natural_test_report_fingerprint_sha256="0" * 64,
        natural_test_scored_observation_count=(
            policy.minimum_natural_test_scored_observations
        ),
        natural_test_target_unavailable_count=0,
        unseen_mint_test_report_fingerprint_sha256="0" * 64,
        unseen_mint_test_scored_observation_count=(
            policy.minimum_unseen_mint_test_scored_observations
        ),
        unseen_mint_test_target_unavailable_count=0,
        unseen_mint_test_identity_fingerprint_sha256=(
            policy.expected_test_unseen_mint_identity_fingerprint_sha256
        ),
    )


def _evidence_payload(
    build: FastFirstChampionV2BuildResult,
    policy: FastFirstChampionV2Policy,
    *,
    fingerprint: str,
) -> dict[str, object]:
    return {
        "schema_name": FAST_FIRST_CHAMPION_V2_SCHEMA_NAME,
        "schema_version": FAST_FIRST_CHAMPION_V2_SCHEMA_VERSION,
        "policy_version": policy.version,
        "cohort_artifact_fingerprint_sha256": (
            build.cohort_artifact_fingerprint_sha256
        ),
        "accepted_identity_fingerprint_sha256": (
            build.accepted_identity_fingerprint_sha256
        ),
        "training_bundle_fingerprint_sha256": (
            build.training_bundle_fingerprint_sha256
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            policy.feature_identity_firewall_fingerprint_sha256
        ),
        "selection_at_unix_ms": policy.selection_at_unix_ms,
        "champion_fingerprint_sha256": (
            build.champion.champion_fingerprint_sha256
        ),
        "members": [
            _member_payload(value) for value in build.member_evidence
        ],
        "evidence_fingerprint_sha256": fingerprint,
    }


def _manifest_payload(
    value: FastFirstChampionV2EvidenceManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "cohort_artifact_fingerprint_sha256": (
            value.cohort_artifact_fingerprint_sha256
        ),
        "accepted_identity_fingerprint_sha256": (
            value.accepted_identity_fingerprint_sha256
        ),
        "training_bundle_fingerprint_sha256": (
            value.training_bundle_fingerprint_sha256
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            value.feature_identity_firewall_fingerprint_sha256
        ),
        "selection_at_unix_ms": value.selection_at_unix_ms,
        "champion_fingerprint_sha256": (
            value.champion_fingerprint_sha256
        ),
        "member_evidence": [
            _member_payload(item) for item in value.member_evidence
        ],
        "file_sha256": [
            {"path": path, "sha256": digest}
            for path, digest in value.file_sha256
        ],
        "artifact_fingerprint_sha256": (
            value.artifact_fingerprint_sha256
        ),
    }


def _manifest_from_payload(
    payload: object,
) -> FastFirstChampionV2EvidenceManifest:
    if not isinstance(payload, dict):
        raise ValueError("V2 evidence manifest must be an object")
    keys = {
        "schema_name",
        "schema_version",
        "policy_version",
        "cohort_artifact_fingerprint_sha256",
        "accepted_identity_fingerprint_sha256",
        "training_bundle_fingerprint_sha256",
        "feature_identity_firewall_fingerprint_sha256",
        "selection_at_unix_ms",
        "champion_fingerprint_sha256",
        "member_evidence",
        "file_sha256",
        "artifact_fingerprint_sha256",
    }
    if set(payload) != keys:
        raise ValueError("V2 evidence manifest keys are incompatible")
    raw_members = payload["member_evidence"]
    raw_files = payload["file_sha256"]
    if not isinstance(raw_members, list) or not isinstance(raw_files, list):
        raise ValueError(
            "V2 evidence manifest populations are incompatible"
        )
    files = []
    for item in raw_files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or not isinstance(item["sha256"], str)
        ):
            raise ValueError(
                "V2 evidence manifest file hash entry is incompatible"
            )
        files.append((item["path"], item["sha256"]))
    try:
        return FastFirstChampionV2EvidenceManifest(
            schema_name=payload["schema_name"],
            schema_version=payload["schema_version"],
            policy_version=payload["policy_version"],
            cohort_artifact_fingerprint_sha256=payload[
                "cohort_artifact_fingerprint_sha256"
            ],
            accepted_identity_fingerprint_sha256=payload[
                "accepted_identity_fingerprint_sha256"
            ],
            training_bundle_fingerprint_sha256=payload[
                "training_bundle_fingerprint_sha256"
            ],
            feature_identity_firewall_fingerprint_sha256=payload[
                "feature_identity_firewall_fingerprint_sha256"
            ],
            selection_at_unix_ms=payload["selection_at_unix_ms"],
            champion_fingerprint_sha256=payload[
                "champion_fingerprint_sha256"
            ],
            member_evidence=tuple(
                _member_from_payload(value) for value in raw_members
            ),
            file_sha256=tuple(files),
            artifact_fingerprint_sha256=payload[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "V2 evidence manifest content is incompatible"
        ) from exc


def _manifest_fingerprint(
    manifest: FastFirstChampionV2EvidenceManifest,
) -> str:
    payload = _manifest_payload(manifest)
    payload.pop("artifact_fingerprint_sha256")
    return _sha256_json(payload)


def _validate_report_pair(
    evidence: FastFirstChampionV2MemberEvidence,
    natural,
    unseen,
    *,
    training_bundle_fingerprint_sha256: str,
) -> None:
    expected = (evidence.target, evidence.model_family, evidence.horizon_ms)
    for label, report, fingerprint, scored, unavailable in (
        (
            "natural",
            natural,
            evidence.natural_test_report_fingerprint_sha256,
            evidence.natural_test_scored_observation_count,
            evidence.natural_test_target_unavailable_count,
        ),
        (
            "unseen",
            unseen,
            evidence.unseen_mint_test_report_fingerprint_sha256,
            evidence.unseen_mint_test_scored_observation_count,
            evidence.unseen_mint_test_target_unavailable_count,
        ),
    ):
        if (
            report.evaluation_policy.partition
            is not FastForecastEvaluationPartition.TEST
        ):
            raise ValueError(
                f"V2 {label} TEST report partition must be TEST"
            )
        actual = (
            report.target,
            report.model_family,
            report.horizon_ms,
        )
        if actual != expected:
            raise ValueError(
                f"V2 {label} TEST report member identity mismatch"
            )
        if report.evaluation_report_fingerprint_sha256 != fingerprint:
            raise ValueError(
                f"V2 {label} TEST report fingerprint mismatch"
            )
        if (
            report.validation_run_fingerprint_sha256
            != evidence.generalization_run_fingerprint_sha256
        ):
            raise ValueError(
                f"V2 {label} TEST report generalization run mismatch"
            )
        if (
            report.training_bundle_fingerprint_sha256
            != training_bundle_fingerprint_sha256
        ):
            raise ValueError(
                f"V2 {label} TEST report training bundle mismatch"
            )
        if (
            report.overall.scored_observation_count != scored
            or report.overall.target_unavailable_count != unavailable
        ):
            raise ValueError(
                f"V2 {label} TEST report counts do not reconcile"
            )


def _validate_champion_member(
    champion,
    evidence: FastFirstChampionV2MemberEvidence,
    natural,
) -> None:
    try:
        member = champion.member_for(
            evidence.target,
            evidence.horizon_ms,
        )
    except KeyError as exc:
        raise ValueError(
            "V2 evidence champion is missing a required member"
        ) from exc
    if member.forecast_artifact.model_family is not evidence.model_family:
        raise ValueError(
            "V2 champion member model family does not match member evidence"
        )
    if (
        member.forecast_artifact.artifact_fingerprint_sha256
        != evidence.runtime_artifact_fingerprint_sha256
        or member.validation_run_fingerprint_sha256
        != evidence.generalization_run_fingerprint_sha256
        or member.test_evaluation_report_fingerprint_sha256
        != evidence.natural_test_report_fingerprint_sha256
        or member.test_scored_observation_count
        != evidence.natural_test_scored_observation_count
        or member.test_target_unavailable_count
        != evidence.natural_test_target_unavailable_count
        or member.test_evaluation_report_fingerprint_sha256
        != natural.evaluation_report_fingerprint_sha256
    ):
        raise ValueError(
            "V2 champion member does not reconcile to member evidence"
        )


def _validate_evidence_payload(
    payload: object,
    manifest: FastFirstChampionV2EvidenceManifest,
) -> None:
    if not isinstance(payload, dict):
        raise ValueError("V2 evidence wrapper must be an object")
    keys = {
        "schema_name",
        "schema_version",
        "policy_version",
        "cohort_artifact_fingerprint_sha256",
        "accepted_identity_fingerprint_sha256",
        "training_bundle_fingerprint_sha256",
        "feature_identity_firewall_fingerprint_sha256",
        "selection_at_unix_ms",
        "champion_fingerprint_sha256",
        "members",
        "evidence_fingerprint_sha256",
    }
    if set(payload) != keys:
        raise ValueError("V2 evidence wrapper keys are incompatible")
    provided = payload["evidence_fingerprint_sha256"]
    if not isinstance(provided, str):
        raise ValueError("V2 evidence fingerprint is incompatible")
    expected = _sha256_json(
        {
            key: value
            for key, value in payload.items()
            if key != "evidence_fingerprint_sha256"
        }
    )
    if provided != expected:
        raise ValueError("V2 evidence fingerprint is invalid")

    manifest_equivalent = {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "policy_version": manifest.policy_version,
        "cohort_artifact_fingerprint_sha256": (
            manifest.cohort_artifact_fingerprint_sha256
        ),
        "accepted_identity_fingerprint_sha256": (
            manifest.accepted_identity_fingerprint_sha256
        ),
        "training_bundle_fingerprint_sha256": (
            manifest.training_bundle_fingerprint_sha256
        ),
        "feature_identity_firewall_fingerprint_sha256": (
            manifest.feature_identity_firewall_fingerprint_sha256
        ),
        "selection_at_unix_ms": manifest.selection_at_unix_ms,
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "members": [
            _member_payload(value) for value in manifest.member_evidence
        ],
    }
    actual = {
        key: value
        for key, value in payload.items()
        if key != "evidence_fingerprint_sha256"
    }
    if actual != manifest_equivalent:
        raise ValueError(
            "V2 evidence wrapper does not reconcile to manifest"
        )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "V2 evidence JSON member must be a regular file"
        )
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("V2 evidence JSON is invalid") from exc


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("V2 evidence JSON contains duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
