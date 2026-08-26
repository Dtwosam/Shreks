from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import TextIO

from .codec import decode_host_acceptance_record, encode_host_acceptance_record
from .collector import (
    HostAcceptanceCaptureConfig,
    ProtectedPathRequirement,
    collect_host_acceptance_record,
)
from .compare import (
    HostContinuityVerdict,
    compare_host_acceptance_records,
    encode_host_continuity_assessment,
)
from .models import HostAcceptanceStage, HostCheckStatus, ProtectedPathKind


Collector = Callable[[HostAcceptanceCaptureConfig], object]


def build_host_acceptance_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m shreks_brain.host_acceptance.runtime",
        description="Capture and compare secret-safe Phase G physical-host acceptance evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture", help="capture one read-only host evidence record")
    capture.add_argument("--stage", required=True, choices=tuple(item.value for item in HostAcceptanceStage))
    capture.add_argument("--host-label", required=True)
    capture.add_argument("--expected-release-sha", required=True, type=_source_sha)
    capture.add_argument("--observer-database", required=True, type=_absolute_path)
    capture.add_argument("--evidence", required=True, type=_absolute_path)
    capture.add_argument("--campaign-manifest", required=True, type=_absolute_path)
    capture.add_argument("--risk-control", required=True, type=_absolute_path)
    capture.add_argument("--backup-root", required=True, type=_absolute_path)
    capture.add_argument("--dashboard-port", required=True, type=_port)
    capture.add_argument("--paper-cycle-interval-seconds", required=True, type=_positive_float)
    capture.add_argument("--dashboard-password", required=True, type=_absolute_path)
    capture.add_argument("--telegram-token", required=True, type=_absolute_path)
    capture.add_argument("--current-release", type=_absolute_path, default=Path("/opt/shreks/current"))
    capture.add_argument("--managed-releases", type=_absolute_path, default=Path("/opt/shreks/releases"))
    capture.add_argument("--state-filesystem", type=_absolute_path, default=Path("/var/lib/shreks"))
    capture.add_argument("--output", required=True, type=_absolute_path)

    compare = subparsers.add_parser("compare", help="compare a baseline and after-drill evidence record")
    compare.add_argument("before", type=_absolute_path)
    compare.add_argument("after", type=_absolute_path)
    compare.add_argument("--output", required=True, type=_absolute_path)
    return parser


def run_host_acceptance_cli(
    argv: Sequence[str] | None = None,
    *,
    collector: Callable[[HostAcceptanceCaptureConfig], object] = collect_host_acceptance_record,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    parser = build_host_acceptance_parser()
    args = parser.parse_args(None if argv is None else list(argv))

    if args.command == "capture":
        return _run_capture(args, collector=collector, stdout=out, stderr=err)
    if args.command == "compare":
        return _run_compare(args, stdout=out, stderr=err)
    raise AssertionError("unreachable host acceptance command")


def _run_capture(
    args: argparse.Namespace,
    *,
    collector: Callable[[HostAcceptanceCaptureConfig], object],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        config = HostAcceptanceCaptureConfig(
            stage=HostAcceptanceStage(args.stage),
            host_label=_trimmed_text("host-label", args.host_label),
            expected_release_sha=args.expected_release_sha,
            observer_database_path=args.observer_database,
            evidence_path=args.evidence,
            campaign_manifest_path=args.campaign_manifest,
            risk_control_path=args.risk_control,
            backup_root=args.backup_root,
            dashboard_port=args.dashboard_port,
            paper_cycle_interval_seconds=args.paper_cycle_interval_seconds,
            current_release_path=args.current_release,
            managed_releases_path=args.managed_releases,
            state_filesystem_path=args.state_filesystem,
            protected_paths=(
                ProtectedPathRequirement(
                    role="dashboard_password",
                    path=args.dashboard_password,
                    expected_kind=ProtectedPathKind.FILE,
                    expected_mode=0o640,
                    secret=True,
                ),
                ProtectedPathRequirement(
                    role="telegram_bot_token",
                    path=args.telegram_token,
                    expected_kind=ProtectedPathKind.FILE,
                    expected_mode=0o640,
                    secret=True,
                ),
            ),
        )
        record = collector(config)
        payload = encode_host_acceptance_record(record)
        _write_private_text(args.output, payload)
    except Exception:
        _emit(stderr, {"error": "CAPTURE_FAILED", "reason_code": "HOST_EVIDENCE_UNAVAILABLE"})
        return 2

    _emit(
        stdout,
        {
            "evidence_fingerprint_sha256": record.evidence_fingerprint_sha256,
            "stage": record.stage.value,
            "status": record.overall_status.value,
        },
    )
    return 0 if record.overall_status is HostCheckStatus.PASS else 1


def _run_compare(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        before = decode_host_acceptance_record(_read_text_file(args.before))
        after = decode_host_acceptance_record(_read_text_file(args.after))
        assessment = compare_host_acceptance_records(before, after)
        _write_private_text(args.output, encode_host_continuity_assessment(assessment))
    except Exception:
        _emit(stderr, {"error": "COMPARE_FAILED", "reason_code": "INVALID_OR_UNAVAILABLE_EVIDENCE"})
        return 2

    _emit(
        stdout,
        {
            "after_fingerprint_sha256": assessment.after_fingerprint_sha256,
            "before_fingerprint_sha256": assessment.before_fingerprint_sha256,
            "status": assessment.verdict.value,
        },
    )
    return 0 if assessment.verdict is HostContinuityVerdict.PASS else 1


def _read_text_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("evidence input must be a regular non-symlink file")
    return path.read_text(encoding="utf-8")


def _write_private_text(path: Path, payload: str) -> None:
    if type(payload) is not str:
        raise ValueError("output payload must be text")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("output parent must be an existing non-symlink directory")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("output must be a regular file path")

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            file_descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _emit(stream: TextIO, document: dict[str, str]) -> None:
    stream.write(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    stream.flush()


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _source_sha(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("release SHA must be exactly 40 lowercase hex characters")
    return value


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive number") from exc
    if not parsed > 0 or parsed == float("inf") or parsed != parsed:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def _port(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def _trimmed_text(name: str, value: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name} must be non-empty trimmed text")
    return value


def main() -> None:
    raise SystemExit(run_host_acceptance_cli())


if __name__ == "__main__":
    main()
