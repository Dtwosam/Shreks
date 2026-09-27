from __future__ import annotations

import argparse
from dataclasses import dataclass
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import tempfile
from typing import Mapping

from .fast_paper_shadow_commissioning_install import (
    FastPaperShadowCommissioningInstallPaths,
    preflight_release_bound_fast_paper_shadow_unit,
)
from .fast_paper_runtime.codec import (
    read_fast_paper_runtime_manifest,
    verify_fast_paper_runtime_bindings,
)
from .fast_paper_runtime.shadow_buy_writer_policy import (
    read_fast_paper_shadow_buy_writer_policy,
    verify_fast_paper_shadow_buy_writer_policy_bindings,
)
from .fast_paper_runtime.shadow_execution_input import (
    read_fast_paper_shadow_execution_policy,
)
from .fast_paper_runtime.shadow_provision import (
    FastPaperShadowProvisionConfig,
    load_fast_paper_shadow_provision_config,
    provision_fast_paper_shadow,
)
from .fast_paper_runtime.shadow_service import (
    read_fast_paper_shadow_service_policy,
)
from .fast_paper_runtime.shadow_supervisor import (
    bootstrap_fast_paper_shadow_supervisor,
)


_SCHEMA_VERSION = 1
_ROOT_UID = 0
_ROOT_GID = 0
_CONFIG_MODE = 0o640
_STATE_DIR_MODE = 0o700
_LEDGER_MODE = 0o600
_SERVICE_NAME = "shreks"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_KEY_RE = re.compile(r"^[A-Z0-9_]+$")

_AUTHORITY_NAMES = (
    "fast-paper-runtime-manifest.json",
    "fast-paper-shadow-service-policy.json",
    "fast-paper-shadow-execution-policy.json",
    "fast-paper-shadow-buy-writer-policy.json",
)

_ENV_KEYS = (
    "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH",
    "SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH",
    "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_INTERVAL_SECONDS",
    "SHREKS_FAST_PAPER_SHADOW_MAXIMUM_DECISIONS",
    "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH",
    "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH",
    "SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID",
    "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH",
    "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY",
    "SHREKS_FAST_PAPER_SHADOW_STARTING_CASH_USD",
)

_PRODUCTION_VALUES = {
    "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH": (
        "/etc/shreks/fast-paper-runtime-manifest.json"
    ),
    "SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH": (
        "/etc/shreks/fast-paper-shadow-service-policy.json"
    ),
    "SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/decision"
    ),
    "SHREKS_FAST_PAPER_SHADOW_EXECUTION_POLICY_PATH": (
        "/etc/shreks/fast-paper-shadow-execution-policy.json"
    ),
    "SHREKS_FAST_PAPER_SHADOW_EXECUTION_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/execution-sources"
    ),
    "SHREKS_FAST_PAPER_SHADOW_LEDGER_DATABASE_PATH": (
        "/var/lib/shreks/fast-paper-shadow/ledger.sqlite3"
    ),
    "SHREKS_FAST_PAPER_SHADOW_BUY_WRITER_POLICY_PATH": (
        "/etc/shreks/fast-paper-shadow-buy-writer-policy.json"
    ),
    "SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/buy-authority-sources"
    ),
    "SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/quote-usd-sources"
    ),
    "SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/reduction-sources"
    ),
    "SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY": (
        "/var/lib/shreks/fast-paper-shadow/pending-buy-retry-sources"
    ),
}

_SHELL_FORBIDDEN = ("$", "`", '"', "'", "\\", ";", "&", "|", "<", ">", "(", ")", "\x00")


class FastPaperShadowHostPrepareError(RuntimeError):
    """Raised when protected shadow host preparation fails closed."""


@dataclass(frozen=True, slots=True)
class _AuthenticatedAuthorityBundle:
    payloads: dict[str, bytes]
    manifest_fingerprint_sha256: str
    bundle_fingerprint_sha256: str


@dataclass(frozen=True, slots=True)
class FastPaperShadowHostPreparePaths:
    current_link: Path
    unit_destination: Path
    config_destination: Path
    shadow_root: Path
    target_path: Path

    def __post_init__(self) -> None:
        for name in (
            "current_link",
            "unit_destination",
            "config_destination",
            "shadow_root",
            "target_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise FastPaperShadowHostPrepareError(
                    f"{name} must be an absolute Path"
                )


def preflight_fast_paper_shadow_host_authority(
    *,
    expected_release_source_sha: str,
    candidate_authority_directory: str | Path,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    _require_commissioned_unit(
        expected_sha,
        paths,
        runtime_executable,
    )
    bundle = _authenticate_authority_bundle(
        Path(candidate_authority_directory),
        expected_release_source_sha=expected_sha,
    )
    _require_safe_config_parent(
        paths.config_destination,
        service_gid=service_gid,
    )
    exact = 0
    for name in _AUTHORITY_NAMES:
        destination = paths.config_destination.parent / name
        if _inspect_config_destination(
            destination,
            expected_payload=bundle.payloads[name],
            service_gid=service_gid,
        ):
            exact += 1
    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_authority_preflight",
        state=(
            "READY_AUTHORITY_ALREADY_INSTALLED"
            if exact == len(_AUTHORITY_NAMES)
            else "READY_TO_INSTALL_AUTHORITY"
        ),
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=None,
        service_uid=service_uid,
        service_gid=service_gid,
        extra={
            "authority_manifest_fingerprint_sha256": (
                bundle.manifest_fingerprint_sha256
            ),
            "authority_bundle_fingerprint_sha256": (
                bundle.bundle_fingerprint_sha256
            ),
            "authority_files_exact": exact,
        },
    )


def install_fast_paper_shadow_host_authority(
    *,
    expected_release_source_sha: str,
    candidate_authority_directory: str | Path,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    _require_commissioned_unit(
        expected_sha,
        paths,
        runtime_executable,
    )
    bundle = _authenticate_authority_bundle(
        Path(candidate_authority_directory),
        expected_release_source_sha=expected_sha,
    )
    _require_safe_config_parent(
        paths.config_destination,
        service_gid=service_gid,
    )

    missing: list[tuple[Path, bytes]] = []
    for name in _AUTHORITY_NAMES:
        destination = paths.config_destination.parent / name
        payload = bundle.payloads[name]
        if not _inspect_config_destination(
            destination,
            expected_payload=payload,
            service_gid=service_gid,
        ):
            missing.append((destination, payload))

    created = 0
    for destination, payload in missing:
        if _require_current_release(paths.current_link, expected_sha) != release_dir:
            raise FastPaperShadowHostPrepareError(
                "current release changed before authority publication"
            )
        _publish_config_no_replace(
            destination,
            payload,
            service_gid=service_gid,
        )
        _require_config_destination(
            destination,
            expected_payload=payload,
            service_gid=service_gid,
        )
        created += 1

    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_authority_installation",
        state=(
            "AUTHORITY_INSTALLED"
            if created
            else "AUTHORITY_ALREADY_INSTALLED"
        ),
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=None,
        service_uid=service_uid,
        service_gid=service_gid,
        extra={
            "authority_manifest_fingerprint_sha256": (
                bundle.manifest_fingerprint_sha256
            ),
            "authority_bundle_fingerprint_sha256": (
                bundle.bundle_fingerprint_sha256
            ),
            "authority_files_published": created,
        },
    )


def _authenticate_authority_bundle(
    candidate_directory: Path,
    *,
    expected_release_source_sha: str,
) -> _AuthenticatedAuthorityBundle:
    if candidate_directory.is_symlink() or not candidate_directory.is_dir():
        raise FastPaperShadowHostPrepareError(
            "shadow authority candidate must be a regular non-symlink directory"
        )
    children = tuple(candidate_directory.iterdir())
    if {child.name for child in children} != set(_AUTHORITY_NAMES):
        raise FastPaperShadowHostPrepareError(
            "shadow authority candidate member set must be exact"
        )

    payloads: dict[str, bytes] = {}
    for name in _AUTHORITY_NAMES:
        payload, _ = _read_regular_no_follow(
            candidate_directory / name,
            label=f"shadow authority candidate {name}",
        )
        payloads[name] = payload

    manifest_path = candidate_directory / _AUTHORITY_NAMES[0]
    service_path = candidate_directory / _AUTHORITY_NAMES[1]
    execution_path = candidate_directory / _AUTHORITY_NAMES[2]
    buy_writer_path = candidate_directory / _AUTHORITY_NAMES[3]
    try:
        manifest = read_fast_paper_runtime_manifest(manifest_path)
        if manifest.release_source_sha != expected_release_source_sha:
            raise ValueError(
                "runtime manifest release source SHA does not match active release"
            )
        verify_fast_paper_runtime_bindings(manifest)
        service_policy = read_fast_paper_shadow_service_policy(service_path)
        if (
            service_policy.route_evidence_version
            != manifest.route_evidence_version
        ):
            raise ValueError(
                "service policy route evidence version does not match runtime manifest"
            )
        read_fast_paper_shadow_execution_policy(
            manifest,
            execution_path,
        )
        buy_writer_policy = read_fast_paper_shadow_buy_writer_policy(
            buy_writer_path
        )
        verify_fast_paper_shadow_buy_writer_policy_bindings(
            manifest,
            service_policy,
            buy_writer_policy,
        )
    except Exception as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow authority candidate authentication failed closed"
        ) from exc

    digest_document = {
        name: hashlib.sha256(payloads[name]).hexdigest()
        for name in _AUTHORITY_NAMES
    }
    digest_document["manifest_fingerprint_sha256"] = (
        manifest.manifest_fingerprint_sha256
    )
    return _AuthenticatedAuthorityBundle(
        payloads=payloads,
        manifest_fingerprint_sha256=(
            manifest.manifest_fingerprint_sha256
        ),
        bundle_fingerprint_sha256=hashlib.sha256(
            _canonical(digest_document).encode("utf-8")
        ).hexdigest(),
    )


def read_fast_paper_shadow_host_environment(path: str | Path) -> dict[str, str]:
    source = Path(path)
    payload, _ = _read_regular_no_follow(
        source,
        label="shadow host environment candidate",
    )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow host environment must be UTF-8"
        ) from exc

    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        if raw_line != raw_line.strip():
            raise FastPaperShadowHostPrepareError(
                "shadow host environment lines must not have surrounding whitespace"
            )
        if raw_line.startswith("export "):
            raise FastPaperShadowHostPrepareError(
                "shadow host environment is data, not shell syntax"
            )
        key, separator, value = raw_line.partition("=")
        if not separator or not key or not value:
            raise FastPaperShadowHostPrepareError(
                "shadow host environment line must be KEY=VALUE"
            )
        if _KEY_RE.fullmatch(key) is None or any(
            character.isspace() for character in key
        ):
            raise FastPaperShadowHostPrepareError(
                "shadow host environment key is invalid"
            )
        if key in result:
            raise FastPaperShadowHostPrepareError(
                "shadow host environment contains duplicate keys"
            )
        if any(token in value for token in _SHELL_FORBIDDEN):
            raise FastPaperShadowHostPrepareError(
                "shadow host environment values may not contain shell syntax"
            )
        if any(character.isspace() for character in value):
            raise FastPaperShadowHostPrepareError(
                "shadow host environment values may not contain whitespace"
            )
        result[key] = value

    _require_exact_env_keys(result)
    return result


def encode_fast_paper_shadow_host_environment(
    environment: Mapping[str, str],
) -> str:
    if not isinstance(environment, Mapping):
        raise FastPaperShadowHostPrepareError(
            "shadow host environment must be a mapping"
        )
    normalized = dict(environment)
    _require_exact_env_keys(normalized)
    for key in _ENV_KEYS:
        value = normalized[key]
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(token in value for token in _SHELL_FORBIDDEN)
            or any(character.isspace() for character in value)
        ):
            raise FastPaperShadowHostPrepareError(
                f"shadow host environment value is invalid: {key}"
            )
    return "".join(f"{key}={normalized[key]}\n" for key in _ENV_KEYS)


def validate_fast_paper_shadow_production_environment(
    environment: Mapping[str, str],
) -> FastPaperShadowProvisionConfig:
    if not isinstance(environment, Mapping):
        raise FastPaperShadowHostPrepareError(
            "shadow host environment must be a mapping"
        )
    env = dict(environment)
    _require_exact_env_keys(env)
    for key, expected in _PRODUCTION_VALUES.items():
        if env[key] != expected:
            raise FastPaperShadowHostPrepareError(
                f"shadow host production path mismatch: {key}"
            )
    run_id = env["SHREKS_FAST_PAPER_SHADOW_LEDGER_RUN_ID"]
    if (
        _RUN_ID_RE.fullmatch(run_id) is None
        or run_id == "replace-with-provisioned-shadow-run-id"
        or run_id.lower().startswith("replace-with")
    ):
        raise FastPaperShadowHostPrepareError(
            "shadow host run id must be explicit non-placeholder text"
        )
    try:
        config = load_fast_paper_shadow_provision_config(env)
    except Exception as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow host environment is incompatible with runtime configuration"
        ) from exc
    return config


def preflight_fast_paper_shadow_host_config(
    *,
    expected_release_source_sha: str,
    candidate_env_path: str | Path,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    _require_commissioned_unit(
        expected_sha,
        paths,
        runtime_executable,
    )
    env = read_fast_paper_shadow_host_environment(candidate_env_path)
    validate_fast_paper_shadow_production_environment(env)
    canonical = encode_fast_paper_shadow_host_environment(env).encode("utf-8")
    _require_safe_config_parent(
        paths.config_destination,
        service_gid=service_gid,
    )
    installed = _inspect_config_destination(
        paths.config_destination,
        expected_payload=canonical,
        service_gid=service_gid,
    )
    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_config_preflight",
        state=(
            "READY_CONFIG_ALREADY_INSTALLED"
            if installed
            else "READY_TO_INSTALL_CONFIG"
        ),
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=hashlib.sha256(canonical).hexdigest(),
        service_uid=service_uid,
        service_gid=service_gid,
    )


def install_fast_paper_shadow_host_config(
    *,
    expected_release_source_sha: str,
    candidate_env_path: str | Path,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    _require_commissioned_unit(
        expected_sha,
        paths,
        runtime_executable,
    )
    env = read_fast_paper_shadow_host_environment(candidate_env_path)
    validate_fast_paper_shadow_production_environment(env)
    canonical = encode_fast_paper_shadow_host_environment(env).encode("utf-8")
    _require_safe_config_parent(
        paths.config_destination,
        service_gid=service_gid,
    )

    if _inspect_config_destination(
        paths.config_destination,
        expected_payload=canonical,
        service_gid=service_gid,
    ):
        return _receipt(
            schema_name="shreks.fast_paper_shadow_host_config_installation",
            state="CONFIG_ALREADY_INSTALLED",
            expected_sha=expected_sha,
            release_dir=release_dir,
            config_sha256=hashlib.sha256(canonical).hexdigest(),
            service_uid=service_uid,
            service_gid=service_gid,
        )

    if _require_current_release(paths.current_link, expected_sha) != release_dir:
        raise FastPaperShadowHostPrepareError(
            "current release changed before config publication"
        )
    _publish_config_no_replace(
        paths.config_destination,
        canonical,
        service_gid=service_gid,
    )
    _require_config_destination(
        paths.config_destination,
        expected_payload=canonical,
        service_gid=service_gid,
    )
    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_config_installation",
        state="CONFIG_INSTALLED",
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=hashlib.sha256(canonical).hexdigest(),
        service_uid=service_uid,
        service_gid=service_gid,
    )


def provision_fast_paper_shadow_host_state(
    *,
    expected_release_source_sha: str,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_service_identity(service_uid=service_uid, service_gid=service_gid)
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    env = _read_installed_environment(
        paths.config_destination,
        service_gid=service_gid,
    )
    config = validate_fast_paper_shadow_production_environment(env)
    _require_path_metadata(
        paths.shadow_root,
        label="shadow state root",
        expected_kind="directory",
        expected_uid=service_uid,
        expected_gid=service_gid,
        expected_mode=_STATE_DIR_MODE,
    )

    try:
        result = provision_fast_paper_shadow(config)
    except Exception as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow service-identity state provisioning failed closed"
        ) from exc
    _verify_state_metadata(
        config,
        service_uid=service_uid,
        service_gid=service_gid,
    )
    execution = result.supervisor_bootstrap.execution_bootstrap
    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_state_provision",
        state="STATE_CREATED" if result.created else "STATE_VERIFIED",
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=hashlib.sha256(
            encode_fast_paper_shadow_host_environment(env).encode("utf-8")
        ).hexdigest(),
        service_uid=service_uid,
        service_gid=service_gid,
        extra={
            "run_id": execution.binding.run_id,
            "binding_fingerprint_sha256": (
                execution.binding.binding_fingerprint_sha256
            ),
            "paper_checkpoint_sequence": execution.checkpoint.sequence,
        },
    )


def preflight_fast_paper_shadow_host(
    *,
    expected_release_source_sha: str,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None = None,
    service_uid: int,
    service_gid: int,
) -> dict[str, object]:
    _require_root()
    _require_paths(paths)
    expected_sha = _validate_source_sha(expected_release_source_sha)
    release_dir = _require_release_runtime(
        paths.current_link,
        expected_sha,
        runtime_executable,
    )
    _require_commissioned_unit(
        expected_sha,
        paths,
        runtime_executable,
    )
    env = _read_installed_environment(
        paths.config_destination,
        service_gid=service_gid,
    )
    config = validate_fast_paper_shadow_production_environment(env)

    for authority_path in _authority_paths_from_config(config):
        _require_path_metadata(
            authority_path,
            label="shadow authority file",
            expected_kind="file",
            expected_uid=_ROOT_UID,
            expected_gid=service_gid,
            expected_mode=0o640,
        )

    _require_path_metadata(
        paths.shadow_root,
        label="shadow state root",
        expected_kind="directory",
        expected_uid=service_uid,
        expected_gid=service_gid,
        expected_mode=_STATE_DIR_MODE,
    )
    _verify_state_metadata(
        config,
        service_uid=service_uid,
        service_gid=service_gid,
    )
    _require_detached_target(paths.target_path)

    try:
        bootstrap = bootstrap_fast_paper_shadow_supervisor(
            config.supervisor_config
        )
    except Exception as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow host supervisor preflight failed closed"
        ) from exc

    decision = bootstrap.decision_bootstrap
    execution = bootstrap.execution_bootstrap
    return _receipt(
        schema_name="shreks.fast_paper_shadow_host_preflight",
        state="READY_FOR_DORMANT_SYSTEMD_LOAD_REVIEW",
        expected_sha=expected_sha,
        release_dir=release_dir,
        config_sha256=hashlib.sha256(
            encode_fast_paper_shadow_host_environment(env).encode("utf-8")
        ).hexdigest(),
        service_uid=service_uid,
        service_gid=service_gid,
        extra={
            "manifest_fingerprint_sha256": (
                decision.manifest.manifest_fingerprint_sha256
            ),
            "run_id": execution.binding.run_id,
            "paper_checkpoint_sequence": execution.checkpoint.sequence,
        },
    )


def _production_paths() -> FastPaperShadowHostPreparePaths:
    return FastPaperShadowHostPreparePaths(
        current_link=Path("/opt/shreks/current"),
        unit_destination=Path(
            "/etc/systemd/system/shreks-fast-paper-shadow.service"
        ),
        config_destination=Path("/etc/shreks/fast-paper-shadow.env"),
        shadow_root=Path("/var/lib/shreks/fast-paper-shadow"),
        target_path=Path("/etc/systemd/system/shreks.target"),
    )


def _resolve_service_identity() -> tuple[int, int]:
    try:
        account = pwd.getpwnam(_SERVICE_NAME)
        group = grp.getgrnam(_SERVICE_NAME)
    except KeyError as exc:
        raise FastPaperShadowHostPrepareError(
            "shreks service identity is unavailable"
        ) from exc
    if account.pw_gid != group.gr_gid:
        raise FastPaperShadowHostPrepareError(
            "shreks service user/group identity is inconsistent"
        )
    return account.pw_uid, group.gr_gid


def _require_exact_env_keys(environment: Mapping[str, str]) -> None:
    if set(environment) != set(_ENV_KEYS):
        raise FastPaperShadowHostPrepareError(
            "shadow host environment key set must be exact"
        )


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperShadowHostPrepareError(
            "shadow host root ceremony requires effective uid 0"
        )


def _require_service_identity(*, service_uid: int, service_gid: int) -> None:
    if (
        os.geteuid() != service_uid
        or os.getegid() != service_gid
        or service_uid == 0
    ):
        raise FastPaperShadowHostPrepareError(
            "shadow state provisioning requires exact service identity"
        )


def _require_paths(paths: FastPaperShadowHostPreparePaths) -> None:
    if type(paths) is not FastPaperShadowHostPreparePaths:
        raise FastPaperShadowHostPrepareError(
            "paths must be exact FastPaperShadowHostPreparePaths"
        )


def _validate_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperShadowHostPrepareError(
            "expected release source SHA must be exactly 40 lowercase hex characters"
        )
    return value


def _require_current_release(current_link: Path, expected_sha: str) -> Path:
    if not current_link.is_symlink():
        raise FastPaperShadowHostPrepareError(
            "current release must be an existing symlink"
        )
    try:
        release_dir = current_link.resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            "current release symlink could not be resolved"
        ) from exc
    if not release_dir.is_dir() or release_dir.name != expected_sha:
        raise FastPaperShadowHostPrepareError(
            "current release directory does not match expected release SHA"
        )
    return release_dir


def _require_release_runtime(
    current_link: Path,
    expected_sha: str,
    runtime_executable: str | os.PathLike[str] | None,
) -> Path:
    release_dir = _require_current_release(current_link, expected_sha)
    executable = Path(
        sys.executable if runtime_executable is None else runtime_executable
    )
    try:
        if executable.is_symlink():
            raise FastPaperShadowHostPrepareError(
                "host preparation runtime executable must not be a symlink"
            )
        resolved = executable.resolve(strict=True)
        expected_bin = (release_dir / ".venv" / "bin").resolve(strict=True)
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            "host preparation runtime executable could not be resolved"
        ) from exc
    if not resolved.is_file() or resolved.parent != expected_bin:
        raise FastPaperShadowHostPrepareError(
            "host preparation must execute from exact current release virtualenv"
        )
    return release_dir


def _require_commissioned_unit(
    expected_sha: str,
    paths: FastPaperShadowHostPreparePaths,
    runtime_executable: str | os.PathLike[str] | None,
) -> None:
    try:
        result = preflight_release_bound_fast_paper_shadow_unit(
            expected_release_source_sha=expected_sha,
            paths=FastPaperShadowCommissioningInstallPaths(
                current_link=paths.current_link,
                unit_destination=paths.unit_destination,
            ),
            runtime_executable=runtime_executable,
        )
    except Exception as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow unit commissioning authentication failed"
        ) from exc
    if result.get("status") != "READY_ALREADY_INSTALLED":
        raise FastPaperShadowHostPrepareError(
            "shadow unit must already be installed exactly before host preparation"
        )


def _require_safe_config_parent(
    destination: Path,
    *,
    service_gid: int,
) -> None:
    parent = destination.parent
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow config destination parent is unavailable"
        ) from exc
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != _ROOT_UID
        or metadata.st_gid not in (_ROOT_GID, service_gid)
        or mode & 0o022
    ):
        raise FastPaperShadowHostPrepareError(
            "shadow config destination parent is unsafe"
        )


def _inspect_config_destination(
    destination: Path,
    *,
    expected_payload: bytes,
    service_gid: int,
) -> bool:
    try:
        payload, metadata = _read_regular_no_follow(
            destination,
            label="shadow host config destination",
        )
    except FastPaperShadowHostPrepareError as exc:
        try:
            destination.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            raise
        raise exc
    if payload != expected_payload:
        raise FastPaperShadowHostPrepareError(
            "shadow host config destination already exists with different bytes"
        )
    _require_config_metadata(metadata, service_gid=service_gid)
    return True


def _require_config_destination(
    destination: Path,
    *,
    expected_payload: bytes,
    service_gid: int,
) -> None:
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed shadow host config",
    )
    if payload != expected_payload:
        raise FastPaperShadowHostPrepareError(
            "installed shadow host config bytes do not match candidate"
        )
    _require_config_metadata(metadata, service_gid=service_gid)


def _require_config_metadata(
    metadata: os.stat_result,
    *,
    service_gid: int,
) -> None:
    if (
        metadata.st_uid != _ROOT_UID
        or metadata.st_gid != service_gid
        or stat.S_IMODE(metadata.st_mode) != _CONFIG_MODE
    ):
        raise FastPaperShadowHostPrepareError(
            "shadow host config destination metadata is not exact"
        )


def _publish_config_no_replace(
    destination: Path,
    payload: bytes,
    *,
    service_gid: int,
) -> None:
    _require_safe_config_parent(destination, service_gid=service_gid)
    parent = destination.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.install-",
        dir=parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchown(handle.fileno(), _ROOT_UID, service_gid)
            os.fchmod(handle.fileno(), _CONFIG_MODE)
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
            linked = True
        except FileExistsError as exc:
            raise FastPaperShadowHostPrepareError(
                "shadow host config destination appeared during publication"
            ) from exc
        except OSError as exc:
            raise FastPaperShadowHostPrepareError(
                "shadow host config could not be published"
            ) from exc
        temporary.unlink()
        _fsync_directory(parent)
    except Exception:
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass
        if linked:
            try:
                _fsync_directory(parent)
            except FastPaperShadowHostPrepareError:
                pass
        raise


def _read_installed_environment(
    destination: Path,
    *,
    service_gid: int,
) -> dict[str, str]:
    payload, metadata = _read_regular_no_follow(
        destination,
        label="installed shadow host config",
    )
    _require_config_metadata(metadata, service_gid=service_gid)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastPaperShadowHostPrepareError(
            "installed shadow host config must be UTF-8"
        ) from exc
    temporary_env = _parse_environment_text(text)
    if encode_fast_paper_shadow_host_environment(temporary_env).encode(
        "utf-8"
    ) != payload:
        raise FastPaperShadowHostPrepareError(
            "installed shadow host config is not canonical"
        )
    return temporary_env


def _parse_environment_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        key, separator, value = raw_line.partition("=")
        if (
            not separator
            or not key
            or not value
            or raw_line != raw_line.strip()
            or _KEY_RE.fullmatch(key) is None
            or key in result
            or any(token in value for token in _SHELL_FORBIDDEN)
            or any(character.isspace() for character in value)
        ):
            raise FastPaperShadowHostPrepareError(
                "installed shadow host config is invalid"
            )
        result[key] = value
    _require_exact_env_keys(result)
    return result


def _authority_paths_from_config(
    config: FastPaperShadowProvisionConfig,
) -> tuple[Path, ...]:
    supervisor = config.supervisor_config
    return (
        supervisor.decision_config.manifest_path,
        supervisor.decision_config.policy_path,
        supervisor.execution_config.execution_policy_path,
        supervisor.buy_writer_policy_path,
    )


def _state_paths_from_config(
    config: FastPaperShadowProvisionConfig,
) -> tuple[tuple[Path, ...], Path]:
    supervisor = config.supervisor_config
    return (
        (
            supervisor.decision_config.evidence_directory,
            supervisor.execution_config.source_directory,
            supervisor.buy_authority_source_directory,
            supervisor.quote_usd_source_directory,
            supervisor.reduction_source_directory,
            supervisor.pending_buy_retry_source_directory,
        ),
        supervisor.execution_config.ledger_database_path,
    )


def _verify_state_metadata(
    config: FastPaperShadowProvisionConfig,
    *,
    service_uid: int,
    service_gid: int,
) -> None:
    directories, ledger = _state_paths_from_config(config)
    try:
        for directory in directories:
            _require_path_metadata(
                directory,
                label="shadow state directory",
                expected_kind="directory",
                expected_uid=service_uid,
                expected_gid=service_gid,
                expected_mode=_STATE_DIR_MODE,
            )
        _require_path_metadata(
            ledger,
            label="shadow ledger",
            expected_kind="file",
            expected_uid=service_uid,
            expected_gid=service_gid,
            expected_mode=_LEDGER_MODE,
        )
    except FastPaperShadowHostPrepareError as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow state metadata is not exact"
        ) from exc


def _require_path_metadata(
    path: Path,
    *,
    label: str,
    expected_kind: str,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int,
) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            f"{label} is unavailable"
        ) from exc
    kind_ok = (
        stat.S_ISDIR(metadata.st_mode)
        if expected_kind == "directory"
        else stat.S_ISREG(metadata.st_mode)
    )
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not kind_ok
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
        or stat.S_IMODE(metadata.st_mode) != expected_mode
    ):
        raise FastPaperShadowHostPrepareError(
            f"{label} metadata is not exact"
        )


def _require_detached_target(path: Path) -> None:
    payload, metadata = _read_regular_no_follow(
        path,
        label="installed shreks target",
    )
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise FastPaperShadowHostPrepareError(
            "installed shreks target is writable by group/world"
        )
    if b"shreks-fast-paper-shadow.service" in payload:
        raise FastPaperShadowHostPrepareError(
            "shadow service must remain detached from shreks.target"
        )


def _read_regular_no_follow(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            f"{label} must be an existing regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise FastPaperShadowHostPrepareError(
                f"{label} must be a regular file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(payload) != before.st_size
        ):
            raise FastPaperShadowHostPrepareError(
                f"{label} changed while being read"
            )
        return payload, after
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise FastPaperShadowHostPrepareError(
            "shadow host directory could not be synced"
        ) from exc


def _receipt(
    *,
    schema_name: str,
    state: str,
    expected_sha: str,
    release_dir: Path,
    config_sha256: str | None,
    service_uid: int,
    service_gid: int,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    material: dict[str, object] = {
        "schema_name": schema_name,
        "schema_version": _SCHEMA_VERSION,
        "state": state,
        "release_source_sha": expected_sha,
        "release_dir": str(release_dir),
        "service_uid": service_uid,
        "service_gid": service_gid,
        "daemon_reload_authority": "NOT_GRANTED",
        "service_start_authority": "NOT_GRANTED",
        "paper_cutover_authority": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    if config_sha256 is not None:
        material["config_sha256"] = config_sha256
    if extra is not None:
        material.update(dict(extra))
    return {
        **material,
        "receipt_fingerprint_sha256": hashlib.sha256(
            _canonical(material).encode("utf-8")
        ).hexdigest(),
    }


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _failure_document(error: BaseException) -> str:
    return _canonical(
        {
            "schema_name": "shreks.fast_paper_shadow_host_prepare_failure",
            "schema_version": _SCHEMA_VERSION,
            "state": "FAILED",
            "error_type": type(error).__name__,
            "daemon_reload_authority": "NOT_GRANTED",
            "service_start_authority": "NOT_GRANTED",
            "paper_cutover_authority": "NOT_GRANTED",
            "live_authority": "DISABLED",
        }
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shreks-fast-paper-shadow-host-prepare"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("authority-preflight", "install-authority"):
        sub = commands.add_parser(command)
        sub.add_argument("expected_release_source_sha")
        sub.add_argument("candidate_authority_directory")
    for command in ("config-preflight", "install-config"):
        sub = commands.add_parser(command)
        sub.add_argument("expected_release_source_sha")
        sub.add_argument("candidate_env")
    for command in ("provision-state", "host-preflight"):
        sub = commands.add_parser(command)
        sub.add_argument("expected_release_source_sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = _production_paths()
    try:
        service_uid, service_gid = _resolve_service_identity()
        common = {
            "expected_release_source_sha": args.expected_release_source_sha,
            "paths": paths,
            "service_uid": service_uid,
            "service_gid": service_gid,
        }
        if args.command == "authority-preflight":
            result = preflight_fast_paper_shadow_host_authority(
                candidate_authority_directory=Path(
                    args.candidate_authority_directory
                ),
                **common,
            )
        elif args.command == "install-authority":
            result = install_fast_paper_shadow_host_authority(
                candidate_authority_directory=Path(
                    args.candidate_authority_directory
                ),
                **common,
            )
        elif args.command == "config-preflight":
            result = preflight_fast_paper_shadow_host_config(
                candidate_env_path=Path(args.candidate_env),
                **common,
            )
        elif args.command == "install-config":
            result = install_fast_paper_shadow_host_config(
                candidate_env_path=Path(args.candidate_env),
                **common,
            )
        elif args.command == "provision-state":
            result = provision_fast_paper_shadow_host_state(**common)
        else:
            result = preflight_fast_paper_shadow_host(**common)
    except FastPaperShadowHostPrepareError as exc:
        print(_failure_document(exc), end="", file=sys.stderr)
        return 1
    print(_canonical(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
