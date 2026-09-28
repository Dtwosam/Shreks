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
import subprocess
import sys
import time
from typing import Callable

from .fast_paper_authoritative_cutover_config import (
    read_fast_paper_authoritative_cutover_environment,
    validate_fast_paper_authoritative_cutover_environment,
)
from .fast_paper_runtime.codec import (
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_manifest,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
)


_SCHEMA_NAME = "shreks.fast_paper_authoritative_cutover_baseline"
_SCHEMA_VERSION = 1
_SHADOW_UNIT = "shreks-fast-paper-shadow.service"
_SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHOW_COMMAND = (
    "systemctl",
    "show",
    _SHADOW_UNIT,
    "--property=ActiveState,SubState,MainPID,NRestarts,InvocationID",
    "--no-pager",
)

_RECEIPT_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "state",
        "release_source_sha",
        "manifest_fingerprint_sha256",
        "shadow_unit",
        "shadow_active_state",
        "shadow_sub_state",
        "shadow_main_pid",
        "shadow_n_restarts",
        "shadow_invocation_id",
        "shadow_checkpoint_path",
        "shadow_checkpoint_file_sha256",
        "decision_state_fingerprint_sha256",
        "decision_cursor_sequence",
        "baseline_replayed",
        "authoritative_checkpoint_path",
        "observed_at_unix_ms",
        "production_fast_paper_runner",
        "production_paper_cutover",
        "service_control_authority",
        "authoritative_paper_mutation",
        "signing_submission_authority",
        "live_authority",
        "receipt_fingerprint_sha256",
    }
)


class FastPaperAuthoritativeCutoverBaselineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or type(self.returncode) is not int:
            raise ValueError("returncode must be an exact integer")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise ValueError("stdout/stderr must be exact strings")


@dataclass(frozen=True, slots=True)
class ShadowQuiescenceState:
    active_state: str
    sub_state: str
    main_pid: int
    n_restarts: int
    invocation_id: str


CommandRunner = Callable[[tuple[str, ...]], HostCommandResult]
Clock = Callable[[], int]


def provision_fast_paper_authoritative_cutover_baseline(
    *,
    fast_manifest_path: str | Path,
    authoritative_runtime_env_path: str | Path,
    receipt_path: str | Path,
    expected_release_sha: str,
    command_runner: CommandRunner | None = None,
    clock_unix_ms: Clock | None = None,
) -> dict[str, object]:
    _require_root()
    expected_sha = _require_source_sha(expected_release_sha)
    runner = _default_command_runner if command_runner is None else command_runner
    clock = _wall_clock_unix_ms if clock_unix_ms is None else clock_unix_ms

    try:
        manifest = read_fast_paper_runtime_manifest(fast_manifest_path)
        verify_fast_paper_runtime_bindings(manifest)
    except Exception as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "Fast PAPER runtime manifest authentication failed"
        ) from exc
    if manifest.release_source_sha != expected_sha:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "Fast PAPER runtime manifest release identity mismatch"
        )

    try:
        environment = read_fast_paper_authoritative_cutover_environment(
            authoritative_runtime_env_path
        )
        runtime_config = (
            validate_fast_paper_authoritative_cutover_environment(
                environment,
                manifest,
                authoritative_database_path=manifest.observer_database_path,
            )
        )
    except Exception as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative runtime environment authentication failed"
        ) from exc

    source = Path(manifest.checkpoint_path).expanduser()
    destination = runtime_config.decision_config.checkpoint_path
    if destination is None:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision checkpoint path is missing"
        )
    destination = destination.expanduser()
    decision_root = runtime_config.decision_config.evidence_directory.expanduser()
    receipt = Path(receipt_path).expanduser()

    _require_source_checkpoint(source)
    destination_preexisting = _require_authoritative_decision_root(
        decision_root,
        destination=destination,
    )
    _require_receipt_path(
        receipt,
        decision_root=decision_root,
    )

    before_systemd = _read_quiescence_state(runner)
    _require_quiescent(before_systemd)

    source_bytes_before = source.read_bytes()
    source_sha256_before = hashlib.sha256(source_bytes_before).hexdigest()
    try:
        source_state = read_fast_paper_runtime_state(source)
        expected_state = build_fast_paper_runtime_state(
            manifest,
            cursor=source_state.cursor,
        )
    except Exception as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow decision checkpoint authentication failed"
        ) from exc
    if source_state != expected_state:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow decision checkpoint does not authenticate against Fast manifest"
        )

    before_stat = source.stat()
    second_systemd = _read_quiescence_state(runner)
    _require_quiescent(second_systemd)
    if second_systemd != before_systemd:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow service state changed during cutover-baseline authentication"
        )

    source_bytes_after = source.read_bytes()
    after_stat = source.stat()
    if (
        source_bytes_after != source_bytes_before
        or _stable_file_identity(after_stat) != _stable_file_identity(before_stat)
    ):
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow decision checkpoint changed during cutover-baseline authentication"
        )

    _require_authoritative_decision_root(
        decision_root,
        destination=destination,
    )
    if destination_preexisting:
        if destination.read_bytes() != source_bytes_before:
            raise FastPaperAuthoritativeCutoverBaselineError(
                "preexisting authoritative decision baseline conflicts with shadow checkpoint"
            )
    else:
        uid, gid = _service_identity()
        _write_bytes_no_replace(
            destination,
            source_bytes_before,
            uid=uid,
            gid=gid,
        )
    try:
        restored = read_fast_paper_runtime_state(destination)
    except Exception as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision baseline read-back authentication failed"
        ) from exc
    if restored != source_state or destination.read_bytes() != source_bytes_before:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision baseline does not exactly match shadow checkpoint"
        )
    if {
        child.name for child in decision_root.iterdir()
    } != {destination.name}:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision root changed during baseline provisioning"
        )

    final_systemd = _read_quiescence_state(runner)
    _require_quiescent(final_systemd)
    if final_systemd != before_systemd:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow service state changed during cutover-baseline provisioning"
        )
    if source.read_bytes() != source_bytes_before:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow decision checkpoint changed during cutover-baseline provisioning"
        )

    observed_at_unix_ms = _clock_value(clock)
    cursor_sequence = (
        None
        if source_state.cursor is None
        else source_state.cursor.decision_sequence
    )
    material: dict[str, object] = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "state": "AUTHORITATIVE_DECISION_BASELINE_PROVISIONED",
        "release_source_sha": expected_sha,
        "manifest_fingerprint_sha256": manifest.manifest_fingerprint_sha256,
        "shadow_unit": _SHADOW_UNIT,
        "shadow_active_state": final_systemd.active_state,
        "shadow_sub_state": final_systemd.sub_state,
        "shadow_main_pid": final_systemd.main_pid,
        "shadow_n_restarts": final_systemd.n_restarts,
        "shadow_invocation_id": final_systemd.invocation_id,
        "shadow_checkpoint_path": str(source.resolve(strict=True)),
        "shadow_checkpoint_file_sha256": source_sha256_before,
        "decision_state_fingerprint_sha256": (
            source_state.state_fingerprint_sha256
        ),
        "decision_cursor_sequence": cursor_sequence,
        "baseline_replayed": destination_preexisting,
        "authoritative_checkpoint_path": str(
            destination.resolve(strict=True)
        ),
        "observed_at_unix_ms": observed_at_unix_ms,
        "production_fast_paper_runner": "SEALED_NOT_ACTIVE",
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "authoritative_paper_mutation": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    document = _finalize_receipt(material)
    _write_receipt_no_replace(receipt, document)
    return document



def read_fast_paper_authoritative_cutover_baseline_receipt(
    path: str | Path,
) -> dict[str, object]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt must be a regular non-symlink file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt is malformed JSON"
        ) from exc
    if type(document) is not dict or frozenset(document) != _RECEIPT_FIELDS:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt has unknown or missing fields"
        )
    if payload != _canonical(document) + "\n":
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt must use canonical JSON"
        )
    claimed = document["receipt_fingerprint_sha256"]
    if (
        not isinstance(claimed, str)
        or len(claimed) != 64
        or any(character not in "0123456789abcdef" for character in claimed)
    ):
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt fingerprint is invalid"
        )
    material = dict(document)
    material.pop("receipt_fingerprint_sha256")
    expected = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed != expected:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt fingerprint mismatch"
        )
    expected_static = {
        "schema_name": _SCHEMA_NAME,
        "schema_version": _SCHEMA_VERSION,
        "state": "AUTHORITATIVE_DECISION_BASELINE_PROVISIONED",
        "shadow_unit": _SHADOW_UNIT,
        "shadow_active_state": "inactive",
        "shadow_sub_state": "dead",
        "shadow_main_pid": 0,
        "production_fast_paper_runner": "SEALED_NOT_ACTIVE",
        "production_paper_cutover": "NOT_GRANTED",
        "service_control_authority": "NOT_GRANTED",
        "authoritative_paper_mutation": "NOT_GRANTED",
        "signing_submission_authority": "NOT_GRANTED",
        "live_authority": "DISABLED",
    }
    for name, expected_value in expected_static.items():
        if document[name] != expected_value:
            raise FastPaperAuthoritativeCutoverBaselineError(
                f"cutover baseline receipt {name} is incompatible"
            )
    _require_source_sha(document["release_source_sha"])
    for name in (
        "manifest_fingerprint_sha256",
        "shadow_checkpoint_file_sha256",
        "decision_state_fingerprint_sha256",
    ):
        value = document[name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise FastPaperAuthoritativeCutoverBaselineError(
                f"cutover baseline receipt {name} is invalid"
            )
    for name in (
        "shadow_n_restarts",
        "observed_at_unix_ms",
    ):
        value = document[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FastPaperAuthoritativeCutoverBaselineError(
                f"cutover baseline receipt {name} must be non-negative"
            )
    cursor = document["decision_cursor_sequence"]
    if cursor is not None and (
        isinstance(cursor, bool)
        or not isinstance(cursor, int)
        or cursor <= 0
    ):
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt decision cursor must be positive or null"
        )
    if type(document["baseline_replayed"]) is not bool:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt baseline_replayed must be bool"
        )
    for name in (
        "shadow_checkpoint_path",
        "authoritative_checkpoint_path",
    ):
        value = document[name]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise FastPaperAuthoritativeCutoverBaselineError(
                f"cutover baseline receipt {name} must be an absolute path"
            )
    return document


def _require_source_checkpoint(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "shadow decision checkpoint must be an existing regular non-symlink file"
        )


def _require_authoritative_decision_root(
    root: Path,
    *,
    destination: Path,
) -> bool:
    if root.is_symlink() or not root.is_dir():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision root must be an existing regular non-symlink directory"
        )
    resolved_root = root.resolve(strict=True)
    if destination.parent.resolve(strict=False) != resolved_root:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision checkpoint must stay directly inside authoritative decision root"
        )
    if destination.is_symlink():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision checkpoint must not be a symlink"
        )
    members = tuple(resolved_root.iterdir())
    if not members:
        return False
    if len(members) != 1 or members[0] != destination or not destination.is_file():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision root must be empty or contain only the exact baseline checkpoint"
        )
    return True


def _require_receipt_path(path: Path, *, decision_root: Path) -> None:
    if not path.is_absolute():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt path must be absolute"
        )
    if path.exists() or path.is_symlink():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt path must not already exist"
        )
    root = decision_root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if resolved == root or root in resolved.parents:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt must stay outside the service-writable authoritative decision root"
        )


def _read_quiescence_state(runner: CommandRunner) -> ShadowQuiescenceState:
    result = runner(_SHOW_COMMAND)
    if result.returncode != 0 or result.stderr.strip():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "unable to authenticate detached-shadow systemd state"
        )
    values: dict[str, str] = {}
    for raw in result.stdout.splitlines():
        if not raw:
            continue
        if "=" not in raw:
            raise FastPaperAuthoritativeCutoverBaselineError(
                "detached-shadow systemd state is malformed"
            )
        key, value = raw.split("=", 1)
        if key in values:
            raise FastPaperAuthoritativeCutoverBaselineError(
                "detached-shadow systemd state contains duplicate properties"
            )
        values[key] = value
    expected = {
        "ActiveState",
        "SubState",
        "MainPID",
        "NRestarts",
        "InvocationID",
    }
    if set(values) != expected:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "detached-shadow systemd state has unknown or missing properties"
        )
    try:
        main_pid = int(values["MainPID"])
        n_restarts = int(values["NRestarts"])
    except ValueError as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "detached-shadow numeric systemd state is invalid"
        ) from exc
    if main_pid < 0 or n_restarts < 0:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "detached-shadow numeric systemd state must be non-negative"
        )
    return ShadowQuiescenceState(
        active_state=values["ActiveState"],
        sub_state=values["SubState"],
        main_pid=main_pid,
        n_restarts=n_restarts,
        invocation_id=values["InvocationID"],
    )


def _require_quiescent(state: ShadowQuiescenceState) -> None:
    if (
        state.active_state != "inactive"
        or state.sub_state != "dead"
        or state.main_pid != 0
    ):
        raise FastPaperAuthoritativeCutoverBaselineError(
            "detached shadow must already be inactive/dead with MainPID=0"
        )


def _write_bytes_no_replace(
    destination: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
) -> None:
    if destination.is_symlink() or destination.exists():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative decision baseline destination must not exist"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = -1
    created = False
    try:
        fd = os.open(destination, flags, 0o600)
        created = True
        os.fchown(fd, uid, gid)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(destination, 0o600)
        _fsync_directory(destination.parent)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if created:
            destination.unlink(missing_ok=True)
        raise


def _write_receipt_no_replace(
    destination: Path,
    document: dict[str, object],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink() or destination.exists():
        raise FastPaperAuthoritativeCutoverBaselineError(
            "cutover baseline receipt already exists"
        )
    payload = (_canonical(document) + "\n").encode("utf-8")
    fd = -1
    created = False
    try:
        fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        created = True
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(destination.parent)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if created:
            destination.unlink(missing_ok=True)
        raise


def _service_identity() -> tuple[int, int]:
    try:
        return (
            pwd.getpwnam("shreks").pw_uid,
            grp.getgrnam("shreks").gr_gid,
        )
    except KeyError as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "required shreks service identity is unavailable"
        ) from exc


def _default_command_runner(command: tuple[str, ...]) -> HostCommandResult:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "host command invocation failed"
        ) from exc
    return HostCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _stable_file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )


def _finalize_receipt(material: dict[str, object]) -> dict[str, object]:
    fingerprint = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    return {
        **material,
        "receipt_fingerprint_sha256": fingerprint,
    }


def _require_source_sha(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "expected release SHA must be exactly 40 lowercase hex characters"
        )
    return value


def _clock_value(clock: Clock) -> int:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "clock must return a non-negative integer unix-ms timestamp"
        )
    return value


def _wall_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


def _require_root() -> None:
    if os.geteuid() != 0:
        raise FastPaperAuthoritativeCutoverBaselineError(
            "authoritative cutover-baseline provisioning requires root"
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)



def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Provision the exact detached-shadow learned decision state as the "
            "write-once authoritative Fast PAPER cutover baseline."
        )
    )
    parser.add_argument("--fast-manifest-path", required=True)
    parser.add_argument("--authoritative-runtime-env-path", required=True)
    parser.add_argument("--receipt-path", required=True)
    parser.add_argument("--expected-release-sha", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        document = provision_fast_paper_authoritative_cutover_baseline(
            fast_manifest_path=args.fast_manifest_path,
            authoritative_runtime_env_path=(
                args.authoritative_runtime_env_path
            ),
            receipt_path=args.receipt_path,
            expected_release_sha=args.expected_release_sha,
        )
    except (
        FastPaperAuthoritativeCutoverBaselineError,
        OSError,
        ValueError,
    ) as exc:
        print(
            _canonical(
                {
                    "schema_name": _SCHEMA_NAME,
                    "schema_version": _SCHEMA_VERSION,
                    "state": "FAILED",
                    "error": str(exc),
                    "production_paper_cutover": "NOT_GRANTED",
                    "service_control_authority": "NOT_GRANTED",
                    "signing_submission_authority": "NOT_GRANTED",
                    "live_authority": "DISABLED",
                }
            ),
            file=sys.stderr,
        )
        return 1

    print(_canonical(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
