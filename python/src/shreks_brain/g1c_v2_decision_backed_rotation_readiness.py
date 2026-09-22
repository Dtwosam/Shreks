from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain.g1c_v2_decision_backed_candidate_authority import (
    G1CV2DecisionBackedCandidateAuthorityError,
    decode_g1c_v2_decision_backed_candidate_authority,
)
from shreks_brain.g1c_v2_paper_manifest_rotation_readiness import (
    PaperManifestRotationReadinessError,
    PaperManifestRotationReadinessPaths,
    _production_paths,
    prove_paper_manifest_rotation_readiness,
)
from shreks_brain.g1c_v2_runtime_manifest_transition_binding import (
    G1CV2RuntimeManifestTransitionBindingError,
    decode_g1c_v2_runtime_manifest_transition_binding,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_READINESS_SCHEMA = "shreks.g1c_v2_paper_manifest_rotation_readiness"
_READINESS_SCHEMA_VERSION = 1


class G1CV2DecisionBackedRotationReadinessError(RuntimeError):
    """Raised when decision-backed readiness provenance cannot be proven safely."""


def prove_decision_backed_paper_manifest_rotation_readiness(
    *,
    candidate_runtime_manifest_path: str | Path,
    transition_binding_path: str | Path,
    decision_backed_candidate_authority_path: str | Path,
    installation_proof_payload: bytes,
    expected_release_source_sha: str,
    paths: PaperManifestRotationReadinessPaths,
    runtime_executable: str | Path | None = None,
    service_runner=None,
    preflight_runner=None,
) -> dict[str, object]:
    candidate_path = _resolve_existing_regular_file(
        candidate_runtime_manifest_path,
        label="candidate runtime manifest",
    )
    binding_path = _resolve_existing_regular_file(
        transition_binding_path,
        label="transition binding",
    )
    authority_path = _resolve_existing_regular_file(
        decision_backed_candidate_authority_path,
        label="decision-backed candidate authority",
    )

    candidate_payload = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    binding_payload = _read_regular_file_stable(
        binding_path,
        label="transition binding",
    )
    authority_payload = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )

    try:
        candidate = decode_observer_paper_campaign_runtime_manifest(
            candidate_payload
        )
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2DecisionBackedRotationReadinessError(
            f"candidate runtime manifest authentication failed: {error}"
        ) from error
    if (
        candidate.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        raise G1CV2DecisionBackedRotationReadinessError(
            "candidate runtime manifest must be canonical v2"
        )

    try:
        binding = decode_g1c_v2_runtime_manifest_transition_binding(
            binding_payload.decode("utf-8")
        )
    except (
        G1CV2RuntimeManifestTransitionBindingError,
        UnicodeDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedRotationReadinessError(
            f"transition binding authentication failed: {error}"
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
        raise G1CV2DecisionBackedRotationReadinessError(
            "decision-backed candidate authority authentication failed: "
            f"{error}"
        ) from error

    _require_candidate_matches_authority(
        candidate_payload=candidate_payload,
        candidate=candidate,
        authority=authority,
    )
    _require_binding_matches_authority(binding, authority)

    try:
        receipt = prove_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=candidate_path,
            transition_binding_path=binding_path,
            installation_proof_payload=installation_proof_payload,
            expected_binding_fingerprint_sha256=binding[
                "binding_fingerprint_sha256"
            ],
            expected_release_source_sha=expected_release_source_sha,
            paths=paths,
            runtime_executable=runtime_executable,
            service_runner=service_runner,
            preflight_runner=preflight_runner,
        )
    except (
        PaperManifestRotationReadinessError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedRotationReadinessError(
            f"standard rotation readiness failed: {error}"
        ) from error

    _require_receipt_matches_authority(
        receipt=receipt,
        authority=authority,
        binding=binding,
        expected_release_source_sha=expected_release_source_sha,
    )

    candidate_after = _read_regular_file_stable(
        candidate_path,
        label="candidate runtime manifest",
    )
    binding_after = _read_regular_file_stable(
        binding_path,
        label="transition binding",
    )
    authority_after = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )
    if candidate_after != candidate_payload:
        raise G1CV2DecisionBackedRotationReadinessError(
            "candidate runtime manifest changed during readiness proof"
        )
    if binding_after != binding_payload:
        raise G1CV2DecisionBackedRotationReadinessError(
            "transition binding changed during readiness proof"
        )
    if authority_after != authority_payload:
        raise G1CV2DecisionBackedRotationReadinessError(
            "decision-backed candidate authority changed during readiness proof"
        )
    return receipt


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
            raise G1CV2DecisionBackedRotationReadinessError(
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
            raise G1CV2DecisionBackedRotationReadinessError(
                f"transition binding {field} does not match decision-backed authority"
            )

    downstream = {
        "installation_authority": "NOT_GRANTED",
        "activation_authority": "NOT_GRANTED",
        "rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for field, expected in downstream.items():
        if binding.get(field) != expected:
            raise G1CV2DecisionBackedRotationReadinessError(
                f"transition binding {field} is not allowed"
            )


def _require_receipt_matches_authority(
    *,
    receipt: dict[str, object],
    authority: dict[str, object],
    binding: dict[str, object],
    expected_release_source_sha: str,
) -> None:
    static = {
        "schema_name": _READINESS_SCHEMA,
        "schema_version": _READINESS_SCHEMA_VERSION,
        "status": "READY_EVIDENCE_ONLY",
        "release_source_sha": expected_release_source_sha,
        "binding_fingerprint_sha256": binding[
            "binding_fingerprint_sha256"
        ],
        "installation_authority": "PROVEN",
        "manifest_rotation_authority": "NOT_GRANTED",
        "scoring_authority": "NOT_GRANTED",
        "paper_promotion_authority": "BLOCKED",
        "live_authority": "DISABLED",
    }
    for field, expected in static.items():
        if receipt.get(field) != expected:
            raise G1CV2DecisionBackedRotationReadinessError(
                f"readiness receipt {field} does not match required authority"
            )

    provenance_fields = (
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
    )
    for field in provenance_fields:
        if receipt.get(field) != authority[field]:
            raise G1CV2DecisionBackedRotationReadinessError(
                f"readiness receipt {field} does not match decision-backed authority"
            )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedRotationReadinessError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2DecisionBackedRotationReadinessError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2DecisionBackedRotationReadinessError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2DecisionBackedRotationReadinessError(
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
        raise G1CV2DecisionBackedRotationReadinessError(
            f"{label} changed while being read"
        )
    return payload


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-decision-backed-rotation-readiness",
        description=(
            "Prove evidence-only G1C v2 rotation readiness for an exact "
            "decision-backed candidate/binding authority chain."
        ),
    )
    parser.add_argument("--candidate-runtime-manifest", required=True)
    parser.add_argument("--transition-binding", required=True)
    parser.add_argument("--decision-backed-candidate-authority", required=True)
    parser.add_argument("--installation-proof", required=True)
    parser.add_argument("--expected-release-source-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        proof_payload, _ = installer._read_regular_no_follow(
            Path(args.installation_proof),
            label="helper installation proof",
        )
        receipt = prove_decision_backed_paper_manifest_rotation_readiness(
            candidate_runtime_manifest_path=args.candidate_runtime_manifest,
            transition_binding_path=args.transition_binding,
            decision_backed_candidate_authority_path=(
                args.decision_backed_candidate_authority
            ),
            installation_proof_payload=proof_payload,
            expected_release_source_sha=args.expected_release_source_sha,
            paths=_production_paths(),
        )
    except (
        G1CV2DecisionBackedRotationReadinessError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.buffer.write(
            _canonical(
                {
                    "schema_name": _READINESS_SCHEMA,
                    "schema_version": _READINESS_SCHEMA_VERSION,
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "manifest_rotation_authority": "NOT_GRANTED",
                    "scoring_authority": "NOT_GRANTED",
                    "paper_promotion_authority": "BLOCKED",
                    "live_authority": "DISABLED",
                }
            )
        )
        return 1

    sys.stdout.buffer.write(_canonical(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
