from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    G1CV2DecisionBackedCandidateAuthorityError,
    decode_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    G1CV2RuntimeManifestTransitionBindingError,
    bind_g1c_v2_runtime_manifest_transition,
    decode_g1c_v2_runtime_manifest_transition_binding,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


class G1CV2DecisionBackedTransitionBindingError(RuntimeError):
    """Raised when decision-backed transition provenance cannot be bound safely."""


def bind_g1c_v2_transition_from_decision_backed_authority(
    *,
    source_runtime_manifest_path: str | Path,
    candidate_runtime_manifest_path: str | Path,
    decision_backed_candidate_authority_path: str | Path,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
    destination: str | Path,
) -> dict[str, object]:
    destination_path = _resolve_new_destination(destination)

    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    candidate_path = _resolve_existing_regular_file(
        candidate_runtime_manifest_path,
        label="candidate runtime manifest",
    )
    authority_path = _resolve_existing_regular_file(
        decision_backed_candidate_authority_path,
        label="decision-backed candidate authority",
    )
    cohort = _resolve_existing_directory(
        cohort_path,
        label="frozen V2 cohort",
    )
    request = _resolve_existing_regular_file(
        v2_host_request_authority_path,
        label="V2 host request authority",
    )

    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    candidate_payload = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    authority_payload = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )

    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
        candidate = decode_observer_paper_campaign_runtime_manifest(
            candidate_payload
        )
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"runtime manifest authentication failed: {error}"
        ) from error
    try:
        authority = decode_g1c_v2_decision_backed_candidate_authority(
            authority_payload.decode("utf-8")
        )
    except (
        G1CV2DecisionBackedCandidateAuthorityError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            "decision-backed candidate authority authentication failed: "
            f"{error}"
        ) from error

    _require_source_matches_authority(
        source_payload=source_payload,
        source=source,
        authority=authority,
    )
    _require_candidate_matches_authority(
        candidate_payload=candidate_payload,
        candidate=candidate,
        authority=authority,
    )

    with tempfile.TemporaryDirectory(
        prefix="shreks-g1c-v2-decision-backed-transition-"
    ) as temporary_directory:
        temporary_binding = (
            Path(temporary_directory) / "transition-binding.json"
        )
        try:
            binding = bind_g1c_v2_runtime_manifest_transition(
                source_runtime_manifest_path=source_path,
                candidate_runtime_manifest_path=candidate_path,
                cohort_path=cohort,
                v2_host_request_authority_path=request,
                destination=temporary_binding,
            )
        except (
            FileExistsError,
            G1CV2RuntimeManifestTransitionBindingError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"canonical transition binding failed: {error}"
            ) from error

        _require_binding_matches_authority(binding, authority)

        try:
            binding_payload = temporary_binding.read_bytes()
            verified_temporary = (
                decode_g1c_v2_runtime_manifest_transition_binding(
                    binding_payload.decode("utf-8")
                )
            )
        except (
            G1CV2RuntimeManifestTransitionBindingError,
            OSError,
            UnicodeDecodeError,
            TypeError,
            ValueError,
        ) as error:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"temporary transition binding authentication failed: {error}"
            ) from error
        if verified_temporary != binding:
            raise G1CV2DecisionBackedTransitionBindingError(
                "temporary transition binding did not round-trip"
            )

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    candidate_after = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    authority_after = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )
    if source_after != source_payload:
        raise G1CV2DecisionBackedTransitionBindingError(
            "source runtime manifest changed during transition binding"
        )
    if candidate_after != candidate_payload:
        raise G1CV2DecisionBackedTransitionBindingError(
            "candidate runtime manifest changed during transition binding"
        )
    if authority_after != authority_payload:
        raise G1CV2DecisionBackedTransitionBindingError(
            "decision-backed candidate authority changed during transition binding"
        )

    written = _write_once(destination_path, binding_payload)
    try:
        written_payload = written.read_bytes()
        verified_written = decode_g1c_v2_runtime_manifest_transition_binding(
            written_payload.decode("utf-8")
        )
    except (
        G1CV2RuntimeManifestTransitionBindingError,
        OSError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"written transition binding authentication failed: {error}"
        ) from error
    if written_payload != binding_payload or verified_written != binding:
        raise G1CV2DecisionBackedTransitionBindingError(
            "written transition binding did not preserve exact canonical bytes"
        )
    return binding


def _require_source_matches_authority(
    *,
    source_payload: bytes,
    source,
    authority: dict[str, object],
) -> None:
    expected = {
        "source_manifest_sha256": hashlib.sha256(source_payload).hexdigest(),
        "source_runtime_manifest_fingerprint_sha256": (
            source.manifest_fingerprint_sha256
        ),
        "source_paper_run_id": source.paper_run_id,
        "source_quote_asset_mint": source.policy_bundle.quote_asset.mint,
    }
    for field, actual in expected.items():
        if authority[field] != actual:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"{field} does not match decision-backed authority"
            )


def _require_candidate_matches_authority(
    *,
    candidate_payload: bytes,
    candidate,
    authority: dict[str, object],
) -> None:
    bundle = candidate.policy_bundle
    expected = {
        "candidate_manifest_sha256": hashlib.sha256(
            candidate_payload
        ).hexdigest(),
        "candidate_runtime_manifest_fingerprint_sha256": (
            candidate.manifest_fingerprint_sha256
        ),
        "candidate_paper_run_id": candidate.paper_run_id,
        "candidate_start_at_unix_ms": (
            candidate.initial_state.last_cycle_at_unix_ms
        ),
        "candidate_quote_asset_mint": bundle.quote_asset.mint,
        "candidate_quote_asset_decimals": bundle.quote_asset.decimals,
        "candidate_entry_input_amount": (
            bundle.entry_quote_identity.input_amount
        ),
        "candidate_quote_usd_valuation_mode": (
            candidate.quote_usd_valuation_policy.mode.value
        ),
    }
    for field, actual in expected.items():
        if authority[field] != actual:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"{field} does not match decision-backed authority"
            )


def _require_binding_matches_authority(
    binding: dict[str, object],
    authority: dict[str, object],
) -> None:
    fields = (
        "source_manifest_sha256",
        "source_runtime_manifest_fingerprint_sha256",
        "source_paper_run_id",
        "source_quote_asset_mint",
        "candidate_manifest_sha256",
        "candidate_runtime_manifest_fingerprint_sha256",
        "candidate_paper_run_id",
        "candidate_start_at_unix_ms",
        "candidate_quote_asset_mint",
        "candidate_quote_asset_decimals",
        "candidate_quote_usd_valuation_mode",
        "cohort_artifact_fingerprint_sha256",
        "cohort_quote_mint",
        "request_fingerprint_sha256",
        "request_release_source_sha",
        "request_hydration_policy_fingerprint_sha256",
    )
    for field in fields:
        if binding.get(field) != authority[field]:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"transition binding {field} does not match decision-backed authority provenance"
            )

    expected_downstream = {
        "installation_authority": "NOT_GRANTED",
        "activation_authority": "NOT_GRANTED",
        "rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for field, expected in expected_downstream.items():
        if binding.get(field) != expected:
            raise G1CV2DecisionBackedTransitionBindingError(
                f"transition binding {field} is not allowed"
            )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} could not be resolved"
        ) from error


def _resolve_existing_directory(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_dir():
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} must be an existing non-symlink directory"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} could not be resolved"
        ) from error


def _resolve_new_destination(raw_path: str | Path) -> Path:
    try:
        destination = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            "transition binding destination path is invalid"
        ) from error
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("transition binding destination already exists")
    return destination


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} could not be read"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise G1CV2DecisionBackedTransitionBindingError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(destination: Path, payload: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise G1CV2DecisionBackedTransitionBindingError(
            "transition binding destination parent must be a real directory"
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.tmp-",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(
                "transition binding destination appeared during write"
            )
        temporary.rename(destination)
        destination.chmod(0o600)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-decision-backed-transition-bind",
        description=(
            "Bind the exact authority-backed G1C v2 candidate through the "
            "existing frozen cohort/request transition assessment."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--candidate-runtime-manifest", required=True)
    parser.add_argument("--decision-backed-candidate-authority", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--v2-host-request-authority", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        binding = bind_g1c_v2_transition_from_decision_backed_authority(
            source_runtime_manifest_path=args.source_runtime_manifest,
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            decision_backed_candidate_authority_path=(
                args.decision_backed_candidate_authority
            ),
            cohort_path=args.cohort,
            v2_host_request_authority_path=args.v2_host_request_authority,
            destination=args.destination,
        )
        result = {
            "status": "DECISION_BACKED_TRANSITION_BOUND",
            "binding_fingerprint_sha256": binding[
                "binding_fingerprint_sha256"
            ],
            "candidate_manifest_sha256": binding[
                "candidate_manifest_sha256"
            ],
        }
    except (
        FileExistsError,
        G1CV2DecisionBackedTransitionBindingError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        result = {"status": "FAILED", "error": str(error)}
        print(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
