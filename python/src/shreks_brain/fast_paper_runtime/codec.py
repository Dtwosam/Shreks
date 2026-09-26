from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from shreks_brain.fast_campaign import FastCampaignContinuousActionPolicy
from shreks_brain.fast_champion import read_fast_forecast_champion
from shreks_brain.fast_paper import FAST_PAPER_EVENT_LOOP_VERSION

from .models import (
    FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME,
    FAST_PAPER_RUNTIME_SCHEMA_VERSION,
    FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME,
    FastPaperRuntimeCursor,
    FastPaperRuntimeManifest,
    FastPaperRuntimeState,
)


_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "release_source_sha",
        "runtime_mode",
        "champion_path",
        "champion_version",
        "champion_fingerprint_sha256",
        "champion_file_sha256",
        "decision_binary_path",
        "decision_binary_sha256",
        "feature_feed_binary_path",
        "feature_feed_binary_sha256",
        "action_policy",
        "feature_schema_version",
        "state_version",
        "fast_paper_event_loop_version",
        "risk_policy_version",
        "fill_policy_version",
        "position_action_policy_version",
        "strategy_family",
        "strategy_version",
        "assessment_version",
        "observer_database_path",
        "paper_evidence_path",
        "checkpoint_path",
        "quote_provider",
        "quote_mint",
        "quote_decimals",
        "route_evidence_version",
        "manifest_fingerprint_sha256",
    }
)
_POLICY_KEYS = frozenset(
    {
        "version",
        "horizons_ms",
        "entry_exposure_candidates",
        "reduce_target_exposure_candidates",
        "adverse_excursion_weight",
        "reversal_penalty_bps",
        "route_unavailability_penalty_bps",
        "horizon_disagreement_weight",
        "minimum_buy_value_bps",
        "minimum_hold_value_bps",
        "missing_forecast_open_action",
    }
)
_STATE_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "manifest_fingerprint_sha256",
        "release_source_sha",
        "champion_fingerprint_sha256",
        "action_policy_version",
        "cursor",
        "state_fingerprint_sha256",
    }
)
_CURSOR_KEYS = frozenset(
    {
        "decision_sequence",
        "decision_signature",
        "decision_ordinal",
        "decision_observed_at_unix_ms",
    }
)


def build_fast_paper_runtime_manifest(
    *,
    release_source_sha: str,
    champion_path: str | Path,
    decision_binary_path: str | Path,
    feature_feed_binary_path: str | Path,
    action_policy: FastCampaignContinuousActionPolicy,
    state_version: str,
    risk_policy_version: str,
    fill_policy_version: str,
    position_action_policy_version: str,
    strategy_family: str,
    strategy_version: str,
    assessment_version: str,
    observer_database_path: str | Path,
    paper_evidence_path: str | Path,
    checkpoint_path: str | Path,
    quote_provider: str,
    quote_mint: str,
    quote_decimals: int,
    route_evidence_version: str,
) -> FastPaperRuntimeManifest:
    champion_file = _existing_regular_file(
        champion_path,
        label="forecast champion",
        executable=False,
    )
    decision_binary = _existing_regular_file(
        decision_binary_path,
        label="Fast Lane decision binary",
        executable=True,
    )
    feature_feed_binary = _existing_regular_file(
        feature_feed_binary_path,
        label="Fast Lane feature feed binary",
        executable=True,
    )
    champion = read_fast_forecast_champion(champion_file)
    if type(action_policy) is not FastCampaignContinuousActionPolicy:
        raise ValueError(
            "action_policy must be an exact FastCampaignContinuousActionPolicy"
        )

    provisional = FastPaperRuntimeManifest(
        schema_name=FAST_PAPER_RUNTIME_MANIFEST_SCHEMA_NAME,
        schema_version=FAST_PAPER_RUNTIME_SCHEMA_VERSION,
        release_source_sha=release_source_sha,
        runtime_mode="PAPER",
        champion_path=str(champion_file),
        champion_version=champion.champion_version,
        champion_fingerprint_sha256=champion.champion_fingerprint_sha256,
        champion_file_sha256=_sha256_file(champion_file),
        decision_binary_path=str(decision_binary),
        decision_binary_sha256=_sha256_file(decision_binary),
        feature_feed_binary_path=str(feature_feed_binary),
        feature_feed_binary_sha256=_sha256_file(feature_feed_binary),
        action_policy=action_policy,
        feature_schema_version=champion.feature_schema_version,
        state_version=state_version,
        fast_paper_event_loop_version=FAST_PAPER_EVENT_LOOP_VERSION,
        risk_policy_version=risk_policy_version,
        fill_policy_version=fill_policy_version,
        position_action_policy_version=position_action_policy_version,
        strategy_family=strategy_family,
        strategy_version=strategy_version,
        assessment_version=assessment_version,
        observer_database_path=_absolute_path(observer_database_path),
        paper_evidence_path=_absolute_path(paper_evidence_path),
        checkpoint_path=_absolute_path(checkpoint_path),
        quote_provider=quote_provider,
        quote_mint=quote_mint,
        quote_decimals=quote_decimals,
        route_evidence_version=route_evidence_version,
        manifest_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        manifest_fingerprint_sha256=_manifest_fingerprint(provisional),
    )


def verify_fast_paper_runtime_bindings(
    manifest: FastPaperRuntimeManifest,
) -> None:
    _require_manifest_fingerprint(manifest)

    champion_path = _existing_regular_file(
        manifest.champion_path,
        label="forecast champion",
        executable=False,
    )
    champion_file_sha256 = _sha256_file(champion_path)
    if champion_file_sha256 != manifest.champion_file_sha256:
        raise ValueError("forecast champion file SHA-256 does not match runtime manifest")
    champion = read_fast_forecast_champion(champion_path)
    if champion.champion_version != manifest.champion_version:
        raise ValueError("forecast champion version does not match runtime manifest")
    if (
        champion.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError("forecast champion fingerprint does not match runtime manifest")
    if champion.feature_schema_version != manifest.feature_schema_version:
        raise ValueError("forecast champion feature schema does not match runtime manifest")

    binary_path = _existing_regular_file(
        manifest.decision_binary_path,
        label="Fast Lane decision binary",
        executable=True,
    )
    if _sha256_file(binary_path) != manifest.decision_binary_sha256:
        raise ValueError("Fast Lane decision binary SHA-256 does not match runtime manifest")

    feature_feed_path = _existing_regular_file(
        manifest.feature_feed_binary_path,
        label="Fast Lane feature feed binary",
        executable=True,
    )
    if _sha256_file(feature_feed_path) != manifest.feature_feed_binary_sha256:
        raise ValueError(
            "Fast Lane feature feed binary SHA-256 does not match runtime manifest"
        )


def write_fast_paper_runtime_manifest(
    manifest: FastPaperRuntimeManifest,
    path: str | Path,
) -> None:
    _require_manifest_fingerprint(manifest)
    verify_fast_paper_runtime_bindings(manifest)

    destination = Path(path).expanduser()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Fast PAPER runtime manifest destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(_manifest_document(manifest))
    created = False
    try:
        with destination.open("x", encoding="utf-8") as handle:
            created = True
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        destination.chmod(0o600)
    except Exception:
        if created and destination.exists() and not destination.is_dir():
            destination.unlink(missing_ok=True)
        raise


def read_fast_paper_runtime_manifest(
    path: str | Path,
) -> FastPaperRuntimeManifest:
    source = _readable_regular_file(path, "Fast PAPER runtime manifest")
    document = _load_canonical_document(source, "Fast PAPER runtime manifest")
    _require_exact_keys("Fast PAPER runtime manifest", document, _MANIFEST_KEYS)
    policy = _policy_from_document(document["action_policy"])

    try:
        manifest = FastPaperRuntimeManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            release_source_sha=document["release_source_sha"],
            runtime_mode=document["runtime_mode"],
            champion_path=document["champion_path"],
            champion_version=document["champion_version"],
            champion_fingerprint_sha256=document["champion_fingerprint_sha256"],
            champion_file_sha256=document["champion_file_sha256"],
            decision_binary_path=document["decision_binary_path"],
            decision_binary_sha256=document["decision_binary_sha256"],
            feature_feed_binary_path=document["feature_feed_binary_path"],
            feature_feed_binary_sha256=document["feature_feed_binary_sha256"],
            action_policy=policy,
            feature_schema_version=document["feature_schema_version"],
            state_version=document["state_version"],
            fast_paper_event_loop_version=document[
                "fast_paper_event_loop_version"
            ],
            risk_policy_version=document["risk_policy_version"],
            fill_policy_version=document["fill_policy_version"],
            position_action_policy_version=document[
                "position_action_policy_version"
            ],
            strategy_family=document["strategy_family"],
            strategy_version=document["strategy_version"],
            assessment_version=document["assessment_version"],
            observer_database_path=document["observer_database_path"],
            paper_evidence_path=document["paper_evidence_path"],
            checkpoint_path=document["checkpoint_path"],
            quote_provider=document["quote_provider"],
            quote_mint=document["quote_mint"],
            quote_decimals=document["quote_decimals"],
            route_evidence_version=document["route_evidence_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Fast PAPER runtime manifest content is incompatible") from exc

    _require_manifest_fingerprint(manifest)
    return manifest


def build_fast_paper_runtime_state(
    manifest: FastPaperRuntimeManifest,
    *,
    cursor: FastPaperRuntimeCursor | None,
) -> FastPaperRuntimeState:
    _require_manifest_fingerprint(manifest)
    if cursor is not None and type(cursor) is not FastPaperRuntimeCursor:
        raise ValueError("cursor must be an exact FastPaperRuntimeCursor or None")

    provisional = FastPaperRuntimeState(
        schema_name=FAST_PAPER_RUNTIME_STATE_SCHEMA_NAME,
        schema_version=FAST_PAPER_RUNTIME_SCHEMA_VERSION,
        manifest_fingerprint_sha256=manifest.manifest_fingerprint_sha256,
        release_source_sha=manifest.release_source_sha,
        champion_fingerprint_sha256=manifest.champion_fingerprint_sha256,
        action_policy_version=manifest.action_policy.version,
        cursor=cursor,
        state_fingerprint_sha256="0" * 64,
    )
    return replace(
        provisional,
        state_fingerprint_sha256=_state_fingerprint(provisional),
    )


def write_fast_paper_runtime_state(
    state: FastPaperRuntimeState,
    path: str | Path,
) -> None:
    _require_state_fingerprint(state)

    destination = Path(path).expanduser()
    if destination.is_symlink():
        raise ValueError("Fast PAPER runtime state destination must not be a symlink")
    if destination.exists() and not destination.is_file():
        raise ValueError("Fast PAPER runtime state destination must be a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)

    encoded = _canonical(_state_document(state)).encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.is_symlink():
            raise ValueError("Fast PAPER runtime state destination became a symlink")
        os.replace(temporary, destination)
        destination.chmod(0o600)
        _fsync_directory(destination.parent)
    except Exception:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)
        raise


def read_fast_paper_runtime_state(
    path: str | Path,
) -> FastPaperRuntimeState:
    source = _readable_regular_file(path, "Fast PAPER runtime state")
    document = _load_canonical_document(source, "Fast PAPER runtime state")
    _require_exact_keys("Fast PAPER runtime state", document, _STATE_KEYS)

    cursor_value = document["cursor"]
    cursor: FastPaperRuntimeCursor | None
    if cursor_value is None:
        cursor = None
    else:
        cursor_mapping = _exact_mapping(
            "Fast PAPER runtime cursor",
            cursor_value,
            _CURSOR_KEYS,
        )
        try:
            cursor = FastPaperRuntimeCursor(
                decision_sequence=cursor_mapping["decision_sequence"],
                decision_signature=cursor_mapping["decision_signature"],
                decision_ordinal=cursor_mapping["decision_ordinal"],
                decision_observed_at_unix_ms=cursor_mapping[
                    "decision_observed_at_unix_ms"
                ],
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Fast PAPER runtime cursor is incompatible") from exc

    try:
        state = FastPaperRuntimeState(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            manifest_fingerprint_sha256=document[
                "manifest_fingerprint_sha256"
            ],
            release_source_sha=document["release_source_sha"],
            champion_fingerprint_sha256=document[
                "champion_fingerprint_sha256"
            ],
            action_policy_version=document["action_policy_version"],
            cursor=cursor,
            state_fingerprint_sha256=document["state_fingerprint_sha256"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Fast PAPER runtime state content is incompatible") from exc

    _require_state_fingerprint(state)
    return state


def _manifest_fingerprint(manifest: FastPaperRuntimeManifest) -> str:
    document = _manifest_document(manifest)
    document.pop("manifest_fingerprint_sha256")
    return _sha256_canonical(document)


def _state_fingerprint(state: FastPaperRuntimeState) -> str:
    document = _state_document(state)
    document.pop("state_fingerprint_sha256")
    return _sha256_canonical(document)


def _require_manifest_fingerprint(manifest: FastPaperRuntimeManifest) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be an exact FastPaperRuntimeManifest")
    if _manifest_fingerprint(manifest) != manifest.manifest_fingerprint_sha256:
        raise ValueError("Fast PAPER runtime manifest fingerprint mismatch")


def _require_state_fingerprint(state: FastPaperRuntimeState) -> None:
    if type(state) is not FastPaperRuntimeState:
        raise ValueError("state must be an exact FastPaperRuntimeState")
    if _state_fingerprint(state) != state.state_fingerprint_sha256:
        raise ValueError("Fast PAPER runtime state fingerprint mismatch")


def _manifest_document(manifest: FastPaperRuntimeManifest) -> dict[str, Any]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "release_source_sha": manifest.release_source_sha,
        "runtime_mode": manifest.runtime_mode,
        "champion_path": manifest.champion_path,
        "champion_version": manifest.champion_version,
        "champion_fingerprint_sha256": manifest.champion_fingerprint_sha256,
        "champion_file_sha256": manifest.champion_file_sha256,
        "decision_binary_path": manifest.decision_binary_path,
        "decision_binary_sha256": manifest.decision_binary_sha256,
        "feature_feed_binary_path": manifest.feature_feed_binary_path,
        "feature_feed_binary_sha256": manifest.feature_feed_binary_sha256,
        "action_policy": _policy_document(manifest.action_policy),
        "feature_schema_version": manifest.feature_schema_version,
        "state_version": manifest.state_version,
        "fast_paper_event_loop_version": manifest.fast_paper_event_loop_version,
        "risk_policy_version": manifest.risk_policy_version,
        "fill_policy_version": manifest.fill_policy_version,
        "position_action_policy_version": manifest.position_action_policy_version,
        "strategy_family": manifest.strategy_family,
        "strategy_version": manifest.strategy_version,
        "assessment_version": manifest.assessment_version,
        "observer_database_path": manifest.observer_database_path,
        "paper_evidence_path": manifest.paper_evidence_path,
        "checkpoint_path": manifest.checkpoint_path,
        "quote_provider": manifest.quote_provider,
        "quote_mint": manifest.quote_mint,
        "quote_decimals": manifest.quote_decimals,
        "route_evidence_version": manifest.route_evidence_version,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
    }


def _state_document(state: FastPaperRuntimeState) -> dict[str, Any]:
    cursor = None
    if state.cursor is not None:
        cursor = {
            "decision_sequence": state.cursor.decision_sequence,
            "decision_signature": state.cursor.decision_signature,
            "decision_ordinal": state.cursor.decision_ordinal,
            "decision_observed_at_unix_ms": (
                state.cursor.decision_observed_at_unix_ms
            ),
        }
    return {
        "schema_name": state.schema_name,
        "schema_version": state.schema_version,
        "manifest_fingerprint_sha256": state.manifest_fingerprint_sha256,
        "release_source_sha": state.release_source_sha,
        "champion_fingerprint_sha256": state.champion_fingerprint_sha256,
        "action_policy_version": state.action_policy_version,
        "cursor": cursor,
        "state_fingerprint_sha256": state.state_fingerprint_sha256,
    }


def _policy_document(
    policy: FastCampaignContinuousActionPolicy,
) -> dict[str, Any]:
    return {
        "version": policy.version,
        "horizons_ms": list(policy.horizons_ms),
        "entry_exposure_candidates": list(policy.entry_exposure_candidates),
        "reduce_target_exposure_candidates": list(
            policy.reduce_target_exposure_candidates
        ),
        "adverse_excursion_weight": policy.adverse_excursion_weight,
        "reversal_penalty_bps": policy.reversal_penalty_bps,
        "route_unavailability_penalty_bps": (
            policy.route_unavailability_penalty_bps
        ),
        "horizon_disagreement_weight": policy.horizon_disagreement_weight,
        "minimum_buy_value_bps": policy.minimum_buy_value_bps,
        "minimum_hold_value_bps": policy.minimum_hold_value_bps,
        "missing_forecast_open_action": policy.missing_forecast_open_action,
    }


def _policy_from_document(value: object) -> FastCampaignContinuousActionPolicy:
    mapping = _exact_mapping(
        "Fast PAPER runtime action policy",
        value,
        _POLICY_KEYS,
    )
    horizons = mapping["horizons_ms"]
    entries = mapping["entry_exposure_candidates"]
    reductions = mapping["reduce_target_exposure_candidates"]
    if not isinstance(horizons, list):
        raise ValueError("action policy horizons_ms must be a list")
    if not isinstance(entries, list):
        raise ValueError("action policy entry_exposure_candidates must be a list")
    if not isinstance(reductions, list):
        raise ValueError(
            "action policy reduce_target_exposure_candidates must be a list"
        )
    try:
        return FastCampaignContinuousActionPolicy(
            version=mapping["version"],
            horizons_ms=tuple(horizons),
            entry_exposure_candidates=tuple(entries),
            reduce_target_exposure_candidates=tuple(reductions),
            adverse_excursion_weight=mapping["adverse_excursion_weight"],
            reversal_penalty_bps=mapping["reversal_penalty_bps"],
            route_unavailability_penalty_bps=mapping[
                "route_unavailability_penalty_bps"
            ],
            horizon_disagreement_weight=mapping[
                "horizon_disagreement_weight"
            ],
            minimum_buy_value_bps=mapping["minimum_buy_value_bps"],
            minimum_hold_value_bps=mapping["minimum_hold_value_bps"],
            missing_forecast_open_action=mapping[
                "missing_forecast_open_action"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Fast PAPER runtime action policy is incompatible") from exc


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_canonical_document(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} JSON is unreadable or invalid") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    if payload != _canonical(document):
        raise ValueError(f"{label} must use canonical JSON")
    return document


def _readable_regular_file(path: str | Path, label: str) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{label} source must be a regular non-symlink file")
    return source


def _existing_regular_file(
    path: str | Path,
    *,
    label: str,
    executable: bool,
) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    resolved = source.resolve()
    if executable and not os.access(resolved, os.X_OK):
        raise ValueError(f"{label} must be executable")
    return resolved


def _absolute_path(path: str | Path) -> str:
    if not isinstance(path, (str, Path)):
        raise ValueError("runtime path must be a string or Path")
    if isinstance(path, str) and not path.strip():
        raise ValueError("runtime path must be non-empty")
    return str(Path(path).expanduser().resolve(strict=False))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _exact_mapping(
    label: str,
    value: object,
    expected: frozenset[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    _require_exact_keys(label, value, expected)
    return value


def _require_exact_keys(
    label: str,
    value: dict[str, Any],
    expected: frozenset[str],
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ValueError(
            f"{label} has unknown or missing fields: "
            f"missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")
