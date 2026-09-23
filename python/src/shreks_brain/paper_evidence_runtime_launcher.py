from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from pathlib import Path
import sys

from shreks_brain.observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
    ObserverPaperCampaignRuntimeManifestError,
    decode_observer_paper_campaign_runtime_manifest,
)


_DEFAULT_BINARY_PATH = Path(
    "/opt/shreks/current/target/release/shreks-paper-evidence"
)
_MANIFEST_PATH_ENV = "SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH"

Execve = Callable[[str, tuple[str, ...], dict[str, str]], object]


class PaperEvidenceRuntimeLauncherError(RuntimeError):
    """Raised when PAPER evidence cannot start from trusted runtime authority."""


def derive_paper_evidence_environment(
    manifest_path: str | Path,
    *,
    environment: Mapping[str, str],
) -> dict[str, str]:
    payload = _read_stable_regular_file(
        manifest_path,
        label="campaign runtime manifest",
    )
    try:
        manifest = decode_observer_paper_campaign_runtime_manifest(payload)
    except (
        ObserverPaperCampaignRuntimeManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise PaperEvidenceRuntimeLauncherError(
            "campaign runtime manifest authentication failed"
        ) from error

    derived = dict(environment)
    if (
        manifest.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        return derived

    bundle = manifest.policy_bundle
    entry = bundle.entry_quote_identity
    safety_probe = bundle.safety_probe_identity

    derived.update(
        {
            "SHREKS_PAPER_QUOTE_ASSET_MINT": bundle.quote_asset.mint,
            "SHREKS_PAPER_ENTRY_INPUT_AMOUNT": str(entry.input_amount),
            "SHREKS_PAPER_EXIT_INPUT_AMOUNT": str(safety_probe.input_amount),
            "SHREKS_PAPER_PROBE_POLICY_VERSION": entry.probe_policy_version,
            "SHREKS_PAPER_QUOTE_TAKER": entry.taker,
            "SHREKS_PAPER_SLIPPAGE_BPS": str(entry.slippage_bps),
        }
    )
    return derived


def launch_paper_evidence(
    *,
    manifest_path: str | Path | None = None,
    binary_path: str | Path = _DEFAULT_BINARY_PATH,
    environment: Mapping[str, str] | None = None,
    execve: Execve = os.execve,
) -> None:
    source_environment = dict(os.environ if environment is None else environment)

    selected_manifest_path: str | Path
    if manifest_path is None:
        configured = source_environment.get(_MANIFEST_PATH_ENV)
        if configured is None or not configured.strip():
            raise PaperEvidenceRuntimeLauncherError(
                "campaign runtime manifest path is missing"
            )
        selected_manifest_path = configured
    else:
        selected_manifest_path = manifest_path

    derived_environment = derive_paper_evidence_environment(
        selected_manifest_path,
        environment=source_environment,
    )

    binary = _resolve_executable(binary_path)
    argv = (str(binary),)
    try:
        execve(str(binary), argv, derived_environment)
    except OSError as error:
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable could not be started"
        ) from error

    raise PaperEvidenceRuntimeLauncherError(
        "PAPER evidence executable returned unexpectedly"
    )


def _resolve_executable(raw_path: str | Path) -> Path:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable path is invalid"
        ) from error

    if not path.is_absolute():
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable path must be absolute"
        )
    if path.is_symlink() or not path.is_file():
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable must be a regular non-symlink file"
        )
    if not os.access(path, os.X_OK):
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable is not executable"
        )
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise PaperEvidenceRuntimeLauncherError(
            "PAPER evidence executable could not be resolved"
        ) from error


def _read_stable_regular_file(
    raw_path: str | Path,
    *,
    label: str,
) -> bytes:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise PaperEvidenceRuntimeLauncherError(
            f"{label} path is invalid"
        ) from error

    if not path.is_absolute():
        raise PaperEvidenceRuntimeLauncherError(
            f"{label} path must be absolute"
        )
    if path.is_symlink() or not path.is_file():
        raise PaperEvidenceRuntimeLauncherError(
            f"{label} must be a regular non-symlink file"
        )

    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise PaperEvidenceRuntimeLauncherError(
            f"{label} could not be read"
        ) from error

    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(payload) != before.st_size
    ):
        raise PaperEvidenceRuntimeLauncherError(
            f"{label} changed while being read"
        )
    return payload


def main() -> int:
    try:
        launch_paper_evidence()
    except PaperEvidenceRuntimeLauncherError:
        print("shreks-paper-evidence-launcher=failed", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
