from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from shreks_brain import g1c_v2_paper_manifest_manager_install as installer
from shreks_brain import (
    g1c_v2_paper_manifest_manager_installation_proof as installation_proof,
)


class PaperManifestManagerInstallationProofRefreshError(RuntimeError):
    """Raised when an already-installed helper cannot be re-proven read-only."""


def refresh_release_bound_paper_manifest_manager_installation_proof(
    *,
    expected_release_source_sha: str,
    paths: installation_proof.ProofPaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    command_runner: installation_proof.CommandRunner | None = None,
) -> dict[str, object]:
    try:
        before = installation_proof.capture_preinstall_state(
            expected_release_source_sha=expected_release_source_sha,
            paths=paths,
            runtime_executable=runtime_executable,
            command_runner=command_runner,
        )

        receipt = installer.install_release_bound_paper_manifest_manager(
            expected_release_source_sha=expected_release_source_sha,
            paths=installer.PaperManifestManagerInstallPaths(
                current_link=paths.current_link,
                destination=paths.manager_destination,
            ),
            runtime_executable=runtime_executable,
            require_already_installed=True,
        )
        if receipt["status"] != "ALREADY_INSTALLED":
            raise PaperManifestManagerInstallationProofRefreshError(
                "proof refresh requires an ALREADY_INSTALLED helper receipt"
            )

        result = installation_proof.verify_postinstall_state(
            expected_release_source_sha=expected_release_source_sha,
            preinstall_payload=_canonical(before),
            installer_receipt_payload=_canonical(receipt),
            paths=paths,
            runtime_executable=runtime_executable,
            command_runner=command_runner,
        )
    except PaperManifestManagerInstallationProofRefreshError:
        raise
    except (
        installation_proof.PaperManifestManagerInstallationProofError,
        installer.PaperManifestManagerInstallError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperManifestManagerInstallationProofRefreshError(
            f"exact-release helper proof refresh failed: {error}"
        ) from error

    if result.get("status") != "VERIFIED":
        raise PaperManifestManagerInstallationProofRefreshError(
            "refreshed installation proof is not VERIFIED"
        )
    if result.get("installation_authority") != (
        "PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY"
    ):
        raise PaperManifestManagerInstallationProofRefreshError(
            "refreshed installation proof has unexpected installation authority"
        )
    for field, expected in (
        ("manifest_rotation_authority", "NOT_GRANTED"),
        ("scoring_authority", "NOT_GRANTED"),
        ("paper_promotion_authority", "BLOCKED"),
        ("live_authority", "DISABLED"),
    ):
        if result.get(field) != expected:
            raise PaperManifestManagerInstallationProofRefreshError(
                f"refreshed installation proof {field} is not allowed"
            )
    return result


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
        prog="shreks-g1c-v2-paper-manifest-manager-install-proof-refresh",
        description=(
            "Refresh the exact-release helper installation proof only when "
            "the sealed helper is already installed with exact bytes/metadata."
        ),
    )
    parser.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = refresh_release_bound_paper_manifest_manager_installation_proof(
            expected_release_source_sha=args.expected_release_source_sha,
            paths=installation_proof._production_paths(),
        )
    except (
        PaperManifestManagerInstallationProofRefreshError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.buffer.write(
            _canonical(
                {
                    "schema_name": installation_proof._PROOF_SCHEMA,
                    "schema_version": installation_proof._SCHEMA_VERSION,
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

    sys.stdout.buffer.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
