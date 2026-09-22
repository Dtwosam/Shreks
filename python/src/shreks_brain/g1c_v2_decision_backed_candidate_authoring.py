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
from shreks_brain.g1c_v2_runtime_manifest_candidate_authoring import (
    G1CV2RuntimeManifestCandidateAuthoringError,
    author_g1c_v2_runtime_manifest_candidate,
)
from shreks_brain.observer_campaign.runtime_manifest import (
    ObserverPaperCampaignRuntimeManifest,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)


class G1CV2DecisionBackedCandidateAuthoringError(RuntimeError):
    """Raised when exact authority-backed candidate bytes cannot be authored safely."""


def author_g1c_v2_candidate_from_decision_backed_authority(
    *,
    source_runtime_manifest_path: str | Path,
    decision_backed_candidate_authority_path: str | Path,
    destination: str | Path,
) -> ObserverPaperCampaignRuntimeManifest:
    source_path = _resolve_existing_regular_file(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    authority_path = _resolve_existing_regular_file(
        decision_backed_candidate_authority_path,
        label="decision-backed candidate authority",
    )

    source_payload = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    authority_payload = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )

    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"source runtime manifest authentication failed: {error}"
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
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"decision-backed candidate authority authentication failed: {error}"
        ) from error

    source_sha256 = hashlib.sha256(source_payload).hexdigest()
    if source_sha256 != authority["source_manifest_sha256"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "source runtime manifest SHA does not match decision-backed authority"
        )
    if (
        source.manifest_fingerprint_sha256
        != authority["source_runtime_manifest_fingerprint_sha256"]
    ):
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "source runtime manifest fingerprint does not match decision-backed authority"
        )
    if source.paper_run_id != authority["source_paper_run_id"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "source paper_run_id does not match decision-backed authority"
        )

    try:
        candidate = author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=source_path,
            paper_run_id=authority["candidate_paper_run_id"],
            start_at_unix_ms=authority["candidate_start_at_unix_ms"],
            quote_asset_mint=authority["candidate_quote_asset_mint"],
            quote_asset_decimals=authority["candidate_quote_asset_decimals"],
            entry_input_amount=authority["candidate_entry_input_amount"],
        )
        candidate_payload = encode_observer_paper_campaign_runtime_manifest(candidate)
    except (
        G1CV2RuntimeManifestCandidateAuthoringError,
        ObserverPaperCampaignRuntimeManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"authority-backed candidate derivation failed: {error}"
        ) from error

    candidate_sha256 = hashlib.sha256(candidate_payload).hexdigest()
    if candidate_sha256 != authority["candidate_manifest_sha256"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate SHA does not match decision-backed authority"
        )
    if (
        candidate.manifest_fingerprint_sha256
        != authority["candidate_runtime_manifest_fingerprint_sha256"]
    ):
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate fingerprint does not match decision-backed authority"
        )

    _require_candidate_identity(candidate, authority)

    source_after = _read_regular_file_stable(
        source_path,
        label="source runtime manifest",
    )
    authority_after = _read_regular_file_stable(
        authority_path,
        label="decision-backed candidate authority",
    )
    if source_after != source_payload:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "source runtime manifest changed while candidate was derived"
        )
    if authority_after != authority_payload:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "decision-backed candidate authority changed while candidate was derived"
        )

    written_path = _write_once(destination, candidate_payload)
    try:
        written_payload = written_path.read_bytes()
        written_candidate = decode_observer_paper_campaign_runtime_manifest(
            written_payload
        )
    except (OSError, ObserverPaperCampaignRuntimeManifestError) as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"written candidate could not be authenticated: {error}"
        ) from error

    if written_payload != candidate_payload or written_candidate != candidate:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "written candidate did not preserve exact canonical bytes"
        )
    return candidate


def _require_candidate_identity(
    candidate: ObserverPaperCampaignRuntimeManifest,
    authority: dict[str, object],
) -> None:
    if candidate.paper_run_id != authority["candidate_paper_run_id"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate paper_run_id does not match authority"
        )
    if (
        candidate.initial_state.last_cycle_at_unix_ms
        != authority["candidate_start_at_unix_ms"]
    ):
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate start timestamp does not match authority"
        )
    quote_asset = candidate.policy_bundle.quote_asset
    if quote_asset.mint != authority["candidate_quote_asset_mint"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate quote mint does not match authority"
        )
    if quote_asset.decimals != authority["candidate_quote_asset_decimals"]:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate quote decimals do not match authority"
        )
    if (
        candidate.policy_bundle.entry_quote_identity.input_amount
        != authority["candidate_entry_input_amount"]
    ):
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "authored candidate entry amount does not match authority"
        )


def _resolve_existing_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"{label} path is invalid"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"{label} could not be resolved"
        ) from error


def _read_regular_file_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
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
        raise G1CV2DecisionBackedCandidateAuthoringError(
            f"{label} changed while being read"
        )
    return payload


def _write_once(raw_destination: str | Path, payload: bytes) -> Path:
    try:
        destination = Path(raw_destination).expanduser().resolve()
    except (TypeError, ValueError) as error:
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "candidate destination path is invalid"
        ) from error

    if destination.exists() or destination.is_symlink():
        raise FileExistsError("candidate destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise G1CV2DecisionBackedCandidateAuthoringError(
            "candidate destination parent must be a real directory"
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
                "candidate destination appeared during write"
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
        prog="shreks-g1c-v2-decision-backed-candidate-author",
        description=(
            "Author the exact canonical G1C v2 candidate already committed "
            "by an authenticated decision-backed candidate authority."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--decision-backed-candidate-authority", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    try:
        candidate = author_g1c_v2_candidate_from_decision_backed_authority(
            source_runtime_manifest_path=args.source_runtime_manifest,
            decision_backed_candidate_authority_path=(
                args.decision_backed_candidate_authority
            ),
            destination=args.destination,
        )
        payload = encode_observer_paper_campaign_runtime_manifest(candidate)
        result = {
            "status": "EXACT_CANDIDATE_AUTHORED",
            "candidate_manifest_sha256": hashlib.sha256(payload).hexdigest(),
            "candidate_runtime_manifest_fingerprint_sha256": (
                candidate.manifest_fingerprint_sha256
            ),
        }
    except (
        FileExistsError,
        G1CV2DecisionBackedCandidateAuthoringError,
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
