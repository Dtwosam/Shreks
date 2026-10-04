from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_proof_workspace import (
    read_fast_proof_workspace_manifest_bounded,
)
from shreks_brain.fl9_tradable_universe import (
    FL9_TRADABLE_UNIVERSE_POLICY_VERSION,
    Fl9TradableUniversePolicy,
    Fl9TradableUniverseStore,
    fl9_tradable_universe_policy_fingerprint_sha256,
)
from shreks_brain.research.fast_training_features import (
    fast_training_feature_record_from_mapping,
)


FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_NAME = (
    "shreks.fast_first_champion_tradable_preselection"
)
FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_VERSION = 1

_ACCEPTED_FILE = "accepted.jsonl"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset({_ACCEPTED_FILE, _MANIFEST_FILE})

_ACCEPTED_KEYS = frozenset(
    {
        "decision_signature",
        "decision_ordinal",
        "decision_sequence",
        "mint",
        "quote_mint",
        "venue",
        "decision_observed_at_unix_ms",
        "candidate_id",
        "snapshot_row_id",
        "assessment_fingerprint_sha256",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy_version",
        "policy_fingerprint_sha256",
        "proof_workspace_artifact_fingerprint_sha256",
        "feature_source_jsonl_sha256",
        "minimum_decision_observed_at_unix_ms",
        "observer_database_sha256",
        "observer_database_wal_sha256",
        "assessed_row_count",
        "eligible_row_count",
        "eligibility_reason_counts",
        "accepted_identity_fingerprint_sha256",
        "candidate_binding_fingerprint_sha256",
        "assessment_evidence_fingerprint_sha256",
        "accepted_file_sha256",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionTradableAcceptedDecision:
    decision_signature: str
    decision_ordinal: int
    decision_sequence: int
    mint: str
    quote_mint: str
    venue: str
    decision_observed_at_unix_ms: int
    candidate_id: int
    snapshot_row_id: int
    assessment_fingerprint_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "decision_signature",
            "mint",
            "quote_mint",
            "venue",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_non_negative_int("decision_ordinal", self.decision_ordinal)
        _require_positive_int("decision_sequence", self.decision_sequence)
        _require_non_negative_int(
            "decision_observed_at_unix_ms",
            self.decision_observed_at_unix_ms,
        )
        _require_positive_int("candidate_id", self.candidate_id)
        _require_positive_int("snapshot_row_id", self.snapshot_row_id)
        _require_sha256(
            "assessment_fingerprint_sha256",
            self.assessment_fingerprint_sha256,
        )

    @property
    def decision_identity(self) -> tuple[object, ...]:
        return (
            self.decision_signature,
            self.decision_ordinal,
            self.decision_sequence,
            self.mint,
            self.quote_mint,
            self.venue,
            self.decision_observed_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class FastFirstChampionTradablePreselectionManifest:
    schema_name: str
    schema_version: int
    policy_version: str
    policy_fingerprint_sha256: str
    proof_workspace_artifact_fingerprint_sha256: str
    feature_source_jsonl_sha256: str
    minimum_decision_observed_at_unix_ms: int
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    assessed_row_count: int
    eligible_row_count: int
    eligibility_reason_counts: tuple[tuple[str, int], ...]
    accepted_identity_fingerprint_sha256: str
    candidate_binding_fingerprint_sha256: str
    assessment_evidence_fingerprint_sha256: str
    accepted_file_sha256: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_name
            != FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_NAME
        ):
            raise ValueError(
                "unsupported first-champion tradable preselection schema_name"
            )
        if (
            self.schema_version
            != FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported first-champion tradable preselection schema_version"
            )
        if self.policy_version != FL9_TRADABLE_UNIVERSE_POLICY_VERSION:
            raise ValueError(
                "unsupported first-champion tradable preselection policy"
            )
        for name in (
            "policy_fingerprint_sha256",
            "proof_workspace_artifact_fingerprint_sha256",
            "feature_source_jsonl_sha256",
            "observer_database_sha256",
            "accepted_identity_fingerprint_sha256",
            "candidate_binding_fingerprint_sha256",
            "assessment_evidence_fingerprint_sha256",
            "accepted_file_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.observer_database_wal_sha256 is not None:
            _require_sha256(
                "observer_database_wal_sha256",
                self.observer_database_wal_sha256,
            )
        _require_non_negative_int(
            "minimum_decision_observed_at_unix_ms",
            self.minimum_decision_observed_at_unix_ms,
        )
        _require_positive_int("assessed_row_count", self.assessed_row_count)
        _require_positive_int("eligible_row_count", self.eligible_row_count)
        if self.eligible_row_count > self.assessed_row_count:
            raise ValueError(
                "preselection eligible row count exceeds assessed row count"
            )
        if (
            not isinstance(self.eligibility_reason_counts, tuple)
            or not self.eligibility_reason_counts
        ):
            raise ValueError(
                "preselection eligibility reason counts must be non-empty tuple"
            )
        normalized = tuple(sorted(self.eligibility_reason_counts))
        if normalized != self.eligibility_reason_counts:
            raise ValueError(
                "preselection eligibility reason counts must be sorted"
            )
        if len({name for name, _ in normalized}) != len(normalized):
            raise ValueError(
                "preselection eligibility reason counts contain duplicate reason"
            )
        for reason, count in normalized:
            _require_non_empty("eligibility reason", reason)
            _require_positive_int(
                f"eligibility_reason_counts[{reason}]",
                count,
            )
        if sum(count for _, count in normalized) != self.assessed_row_count:
            raise ValueError(
                "preselection eligibility reason counts do not reconcile"
            )
        eligible_reason_count = dict(normalized).get("eligible", 0)
        if eligible_reason_count != self.eligible_row_count:
            raise ValueError(
                "preselection eligible reason count does not reconcile"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionTradablePreselectionArtifact:
    path: Path
    manifest: FastFirstChampionTradablePreselectionManifest
    accepted_decisions: tuple[
        FastFirstChampionTradableAcceptedDecision, ...
    ]

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("preselection path must be Path")
        if (
            type(self.manifest)
            is not FastFirstChampionTradablePreselectionManifest
        ):
            raise ValueError(
                "preselection manifest must be exact manifest type"
            )
        if (
            not isinstance(self.accepted_decisions, tuple)
            or not self.accepted_decisions
            or not all(
                type(value)
                is FastFirstChampionTradableAcceptedDecision
                for value in self.accepted_decisions
            )
        ):
            raise ValueError(
                "preselection accepted decisions must be non-empty exact tuple"
            )
        if len(self.accepted_decisions) != self.manifest.eligible_row_count:
            raise ValueError(
                "preselection accepted decision count contradicts manifest"
            )
        identities = tuple(
            value.decision_identity for value in self.accepted_decisions
        )
        if len(set(identities)) != len(identities):
            raise ValueError(
                "preselection accepted decision identities must be unique"
            )

    @property
    def decision_identities(self) -> tuple[tuple[object, ...], ...]:
        return tuple(
            value.decision_identity for value in self.accepted_decisions
        )

    def accepted_before(
        self,
        exclusive_unix_ms: int,
    ) -> tuple[FastFirstChampionTradableAcceptedDecision, ...]:
        _require_non_negative_int(
            "exclusive_unix_ms",
            exclusive_unix_ms,
        )
        return tuple(
            value
            for value in self.accepted_decisions
            if value.decision_observed_at_unix_ms < exclusive_unix_ms
        )

    def candidate_ids_by_identity(
        self,
    ) -> dict[tuple[object, ...], int]:
        return {
            value.decision_identity: value.candidate_id
            for value in self.accepted_decisions
        }


def build_fast_first_champion_tradable_preselection(
    *,
    proof_workspace_path: str | Path,
    observer_database_path: str | Path,
    minimum_decision_observed_at_unix_ms: int,
    destination: str | Path,
) -> FastFirstChampionTradablePreselectionArtifact:
    _require_non_negative_int(
        "minimum_decision_observed_at_unix_ms",
        minimum_decision_observed_at_unix_ms,
    )
    proof_path = Path(proof_workspace_path).expanduser().resolve()
    if proof_path.is_symlink() or not proof_path.is_dir():
        raise ValueError(
            "preselection proof workspace must be an existing real directory"
        )
    database = Path(observer_database_path).expanduser().resolve()
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "preselection observer database must be an existing regular file"
        )
    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "preselection destination already exists; overwrite is forbidden"
        )

    proof_before = read_fast_proof_workspace_manifest_bounded(proof_path)
    feature_path = proof_path / "features.jsonl"
    if feature_path.is_symlink() or not feature_path.is_file():
        raise ValueError(
            "preselection proof workspace feature source is missing"
        )

    database_before = _capture_database(database)
    policy = Fl9TradableUniversePolicy()
    policy_fingerprint = (
        fl9_tradable_universe_policy_fingerprint_sha256(policy)
    )
    tradable_store = Fl9TradableUniverseStore(database)

    accepted: list[FastFirstChampionTradableAcceptedDecision] = []
    reasons: Counter[str] = Counter()
    assessment_hasher = hashlib.sha256()
    feature_hasher = hashlib.sha256()
    seen: set[tuple[object, ...]] = set()
    assessed_row_count = 0

    with feature_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            feature_hasher.update(raw_line)
            if not raw_line.endswith(b"\n"):
                raise ValueError(
                    "preselection feature JSONL must be newline terminated"
                )
            payload = raw_line[:-1]
            if payload.endswith(b"\r"):
                payload = payload[:-1]
            if not payload.strip():
                raise ValueError(
                    f"preselection feature JSONL line {line_number} is blank"
                )
            try:
                mapping = json.loads(
                    payload.decode("utf-8"),
                    parse_constant=_reject_json_constant,
                    object_pairs_hook=_reject_duplicate_keys,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"preselection feature JSONL line {line_number} is invalid"
                ) from exc
            record = fast_training_feature_record_from_mapping(mapping)
            if (
                record.decision_observed_at_unix_ms
                < minimum_decision_observed_at_unix_ms
            ):
                continue
            identity = record.decision_identity
            if identity in seen:
                raise ValueError(
                    "preselection feature population contains duplicate decision identity"
                )
            seen.add(identity)
            assessed_row_count += 1
            assessment = tradable_store.assess(
                mint=record.mint,
                quote_mint=record.quote_mint,
                decision_venue=record.venue,
                decision_observed_at_unix_ms=(
                    record.decision_observed_at_unix_ms
                ),
                policy=policy,
            )
            if (
                assessment.mint != record.mint
                or assessment.quote_mint != record.quote_mint
                or assessment.decision_venue != record.venue
                or assessment.decision_observed_at_unix_ms
                != record.decision_observed_at_unix_ms
                or assessment.policy_version != policy.version
                or assessment.policy_fingerprint_sha256
                != policy_fingerprint
            ):
                raise ValueError(
                    "preselection assessment does not match feature identity"
                )
            reasons[assessment.reason] += 1
            material = {
                "decision_identity": list(identity),
                "assessment": asdict(assessment),
            }
            assessment_line = _canonical_json(material)
            assessment_hasher.update(
                (assessment_line + "\n").encode("utf-8")
            )
            if not assessment.eligible:
                continue
            if (
                assessment.candidate_id is None
                or assessment.snapshot_row_id is None
            ):
                raise ValueError(
                    "eligible preselection assessment is missing candidate/snapshot binding"
                )
            accepted.append(
                FastFirstChampionTradableAcceptedDecision(
                    decision_signature=record.decision_signature,
                    decision_ordinal=record.decision_ordinal,
                    decision_sequence=record.decision_sequence,
                    mint=record.mint,
                    quote_mint=record.quote_mint,
                    venue=record.venue,
                    decision_observed_at_unix_ms=(
                        record.decision_observed_at_unix_ms
                    ),
                    candidate_id=assessment.candidate_id,
                    snapshot_row_id=assessment.snapshot_row_id,
                    assessment_fingerprint_sha256=(
                        hashlib.sha256(
                            _canonical_json(
                                asdict(assessment)
                            ).encode("utf-8")
                        ).hexdigest()
                    ),
                )
            )

    if assessed_row_count == 0:
        raise ValueError(
            "preselection contains no decisions at or above minimum timestamp"
        )
    if not accepted:
        raise ValueError(
            "preselection contains no tradable-universe eligible decisions"
        )
    feature_sha = feature_hasher.hexdigest()
    if feature_sha != proof_before.manifest.feature_jsonl_sha256:
        raise ValueError(
            "preselection feature source fingerprint does not match proof workspace"
        )

    accepted_tuple = tuple(sorted(accepted, key=_accepted_sort_key))
    reason_counts = tuple(sorted(reasons.items()))
    database_after = _capture_database(database)
    if database_after != database_before:
        raise ValueError(
            "preselection observer database changed during construction"
        )
    proof_after = read_fast_proof_workspace_manifest_bounded(proof_path)
    if proof_after.manifest != proof_before.manifest:
        raise ValueError(
            "preselection proof workspace changed during construction"
        )

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
        accepted_hasher = hashlib.sha256()
        with accepted_path.open("wb") as handle:
            for value in accepted_tuple:
                raw = (
                    _canonical_json(_accepted_document(value))
                    + "\n"
                ).encode("utf-8")
                handle.write(raw)
                accepted_hasher.update(raw)
        accepted_path.chmod(0o600)

        material = {
            "schema_name": (
                FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_NAME
            ),
            "schema_version": (
                FAST_FIRST_CHAMPION_TRADABLE_PRESELECTION_SCHEMA_VERSION
            ),
            "policy_version": policy.version,
            "policy_fingerprint_sha256": policy_fingerprint,
            "proof_workspace_artifact_fingerprint_sha256": (
                proof_before.manifest.artifact_fingerprint_sha256
            ),
            "feature_source_jsonl_sha256": feature_sha,
            "minimum_decision_observed_at_unix_ms": (
                minimum_decision_observed_at_unix_ms
            ),
            "observer_database_sha256": (
                database_before.database_sha256
            ),
            "observer_database_wal_sha256": (
                database_before.wal_sha256
            ),
            "assessed_row_count": assessed_row_count,
            "eligible_row_count": len(accepted_tuple),
            "eligibility_reason_counts": [
                [name, count] for name, count in reason_counts
            ],
            "accepted_identity_fingerprint_sha256": (
                _accepted_identity_fingerprint(accepted_tuple)
            ),
            "candidate_binding_fingerprint_sha256": (
                _candidate_binding_fingerprint(accepted_tuple)
            ),
            "assessment_evidence_fingerprint_sha256": (
                assessment_hasher.hexdigest()
            ),
            "accepted_file_sha256": accepted_hasher.hexdigest(),
        }
        manifest_values = dict(material)
        manifest_values["eligibility_reason_counts"] = reason_counts
        manifest = FastFirstChampionTradablePreselectionManifest(
            **manifest_values,
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical_json(_manifest_document(manifest)) + "\n",
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fast_first_champion_tradable_preselection(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged preselection did not round-trip"
            )
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "preselection destination appeared during construction"
            )
        staging.rename(destination_path)
        return read_fast_first_champion_tradable_preselection(
            destination_path
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_first_champion_tradable_preselection(
    path: str | Path,
) -> FastFirstChampionTradablePreselectionArtifact:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "preselection must be an existing real directory"
        )
    if {child.name for child in root.iterdir()} != _ROOT_ENTRIES:
        raise ValueError(
            "preselection has unknown or missing entries"
        )
    accepted_path = root / _ACCEPTED_FILE
    manifest_path = root / _MANIFEST_FILE
    for source in (accepted_path, manifest_path):
        if source.is_symlink() or not source.is_file():
            raise ValueError(
                "preselection artifact members must be regular files"
            )

    manifest_document = _load_canonical_object(
        manifest_path.read_text(encoding="utf-8"),
        label="preselection manifest",
    )
    if frozenset(manifest_document) != _MANIFEST_KEYS:
        raise ValueError(
            "preselection manifest has unknown or missing fields"
        )
    raw_reason_counts = manifest_document["eligibility_reason_counts"]
    if (
        not isinstance(raw_reason_counts, list)
        or not raw_reason_counts
        or not all(
            isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
            and not isinstance(value[1], bool)
            for value in raw_reason_counts
        )
    ):
        raise ValueError(
            "preselection eligibility reason counts are incompatible"
        )
    reason_counts = tuple(
        (value[0], value[1]) for value in raw_reason_counts
    )
    try:
        manifest = FastFirstChampionTradablePreselectionManifest(
            schema_name=manifest_document["schema_name"],
            schema_version=manifest_document["schema_version"],
            policy_version=manifest_document["policy_version"],
            policy_fingerprint_sha256=manifest_document[
                "policy_fingerprint_sha256"
            ],
            proof_workspace_artifact_fingerprint_sha256=(
                manifest_document[
                    "proof_workspace_artifact_fingerprint_sha256"
                ]
            ),
            feature_source_jsonl_sha256=manifest_document[
                "feature_source_jsonl_sha256"
            ],
            minimum_decision_observed_at_unix_ms=manifest_document[
                "minimum_decision_observed_at_unix_ms"
            ],
            observer_database_sha256=manifest_document[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=manifest_document[
                "observer_database_wal_sha256"
            ],
            assessed_row_count=manifest_document["assessed_row_count"],
            eligible_row_count=manifest_document["eligible_row_count"],
            eligibility_reason_counts=reason_counts,
            accepted_identity_fingerprint_sha256=manifest_document[
                "accepted_identity_fingerprint_sha256"
            ],
            candidate_binding_fingerprint_sha256=manifest_document[
                "candidate_binding_fingerprint_sha256"
            ],
            assessment_evidence_fingerprint_sha256=manifest_document[
                "assessment_evidence_fingerprint_sha256"
            ],
            accepted_file_sha256=manifest_document[
                "accepted_file_sha256"
            ],
            artifact_fingerprint_sha256=manifest_document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"preselection manifest is invalid: {exc}"
        ) from exc

    material = dict(manifest_document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "preselection artifact fingerprint mismatch"
        )
    if _sha256_file_stable(accepted_path) != manifest.accepted_file_sha256:
        raise ValueError(
            "preselection accepted file fingerprint mismatch"
        )

    accepted: list[FastFirstChampionTradableAcceptedDecision] = []
    with accepted_path.open("rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.endswith("\n") or line.endswith("\n\n"):
                raise ValueError(
                    "preselection accepted JSONL must use one trailing newline per row"
                )
            document = _load_canonical_object(
                line,
                label=f"preselection accepted row {line_number}",
            )
            if frozenset(document) != _ACCEPTED_KEYS:
                raise ValueError(
                    "preselection accepted row has unknown or missing fields"
                )
            accepted.append(
                FastFirstChampionTradableAcceptedDecision(
                    decision_signature=document["decision_signature"],
                    decision_ordinal=document["decision_ordinal"],
                    decision_sequence=document["decision_sequence"],
                    mint=document["mint"],
                    quote_mint=document["quote_mint"],
                    venue=document["venue"],
                    decision_observed_at_unix_ms=document[
                        "decision_observed_at_unix_ms"
                    ],
                    candidate_id=document["candidate_id"],
                    snapshot_row_id=document["snapshot_row_id"],
                    assessment_fingerprint_sha256=document[
                        "assessment_fingerprint_sha256"
                    ],
                )
            )
    accepted_tuple = tuple(accepted)
    if tuple(sorted(accepted_tuple, key=_accepted_sort_key)) != accepted_tuple:
        raise ValueError(
            "preselection accepted rows are not in canonical order"
        )
    if len(accepted_tuple) != manifest.eligible_row_count:
        raise ValueError(
            "preselection accepted row count contradicts manifest"
        )
    if (
        _accepted_identity_fingerprint(accepted_tuple)
        != manifest.accepted_identity_fingerprint_sha256
    ):
        raise ValueError(
            "preselection accepted identity fingerprint mismatch"
        )
    if (
        _candidate_binding_fingerprint(accepted_tuple)
        != manifest.candidate_binding_fingerprint_sha256
    ):
        raise ValueError(
            "preselection candidate binding fingerprint mismatch"
        )
    return FastFirstChampionTradablePreselectionArtifact(
        path=root,
        manifest=manifest,
        accepted_decisions=accepted_tuple,
    )


def _accepted_document(
    value: FastFirstChampionTradableAcceptedDecision,
) -> dict[str, object]:
    return {
        "decision_signature": value.decision_signature,
        "decision_ordinal": value.decision_ordinal,
        "decision_sequence": value.decision_sequence,
        "mint": value.mint,
        "quote_mint": value.quote_mint,
        "venue": value.venue,
        "decision_observed_at_unix_ms": (
            value.decision_observed_at_unix_ms
        ),
        "candidate_id": value.candidate_id,
        "snapshot_row_id": value.snapshot_row_id,
        "assessment_fingerprint_sha256": (
            value.assessment_fingerprint_sha256
        ),
    }


def _manifest_document(
    value: FastFirstChampionTradablePreselectionManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "policy_version": value.policy_version,
        "policy_fingerprint_sha256": value.policy_fingerprint_sha256,
        "proof_workspace_artifact_fingerprint_sha256": (
            value.proof_workspace_artifact_fingerprint_sha256
        ),
        "feature_source_jsonl_sha256": (
            value.feature_source_jsonl_sha256
        ),
        "minimum_decision_observed_at_unix_ms": (
            value.minimum_decision_observed_at_unix_ms
        ),
        "observer_database_sha256": value.observer_database_sha256,
        "observer_database_wal_sha256": (
            value.observer_database_wal_sha256
        ),
        "assessed_row_count": value.assessed_row_count,
        "eligible_row_count": value.eligible_row_count,
        "eligibility_reason_counts": [
            [name, count]
            for name, count in value.eligibility_reason_counts
        ],
        "accepted_identity_fingerprint_sha256": (
            value.accepted_identity_fingerprint_sha256
        ),
        "candidate_binding_fingerprint_sha256": (
            value.candidate_binding_fingerprint_sha256
        ),
        "assessment_evidence_fingerprint_sha256": (
            value.assessment_evidence_fingerprint_sha256
        ),
        "accepted_file_sha256": value.accepted_file_sha256,
        "artifact_fingerprint_sha256": (
            value.artifact_fingerprint_sha256
        ),
    }


def _accepted_sort_key(
    value: FastFirstChampionTradableAcceptedDecision,
) -> tuple[object, ...]:
    return (
        value.decision_observed_at_unix_ms,
        value.decision_sequence,
        value.decision_signature,
        value.decision_ordinal,
        value.mint,
        value.quote_mint,
        value.venue,
    )


def _accepted_identity_fingerprint(
    values: tuple[FastFirstChampionTradableAcceptedDecision, ...],
) -> str:
    return _sha256_canonical(
        [list(value.decision_identity) for value in values]
    )


def _candidate_binding_fingerprint(
    values: tuple[FastFirstChampionTradableAcceptedDecision, ...],
) -> str:
    return _sha256_canonical(
        [
            {
                "decision_identity": list(value.decision_identity),
                "candidate_id": value.candidate_id,
                "snapshot_row_id": value.snapshot_row_id,
            }
            for value in values
        ]
    )


@dataclass(frozen=True, slots=True)
class _DatabaseSnapshot:
    database_sha256: str
    wal_sha256: str | None


def _capture_database(path: Path) -> _DatabaseSnapshot:
    wal = Path(str(path) + "-wal")
    return _DatabaseSnapshot(
        database_sha256=_sha256_file_stable(path),
        wal_sha256=(
            _sha256_file_stable(wal)
            if wal.is_file()
            else None
        ),
    )


def _load_canonical_object(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            f"{label} must contain exactly one trailing newline"
        )
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical_json(value) + "\n" != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"preselection source must be existing regular file: {path}"
        )
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(
            "preselection source changed while fingerprinting"
        )
    return digest.hexdigest()


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
