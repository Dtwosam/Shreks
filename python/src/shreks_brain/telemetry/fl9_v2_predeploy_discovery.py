from __future__ import annotations

import os
from pathlib import Path
import pwd
import sys
from typing import Final, Sequence

from .fl9_v2_discovery_control import (
    process_pending_fl9_v2_discovery_requests,
    publish_fl9_v2_discovery_control_result,
)


_PREDEPLOY_MARKER_DIRECTORY: Final = Path("/var/tmp")
_RESULT_MARKER_DIRECTORY: Final = Path("/dev/shm")
_RUNTIME_USER: Final = "shreks"


def _drop_to_runtime_identity() -> None:
    identity = pwd.getpwnam(_RUNTIME_USER)
    if identity.pw_uid <= 0 or identity.pw_gid <= 0:
        raise RuntimeError("runtime identity must be unprivileged")
    os.setgroups([])
    os.setgid(identity.pw_gid)
    os.setuid(identity.pw_uid)


def run_predeploy_discovery() -> int:
    if os.geteuid() != 0:
        print("fl9_v2_predeploy_discovery=requires-root-preflight", file=sys.stderr)
        return 1

    try:
        results = process_pending_fl9_v2_discovery_requests(
            marker_directory=_PREDEPLOY_MARKER_DIRECTORY,
            persist_receipts=False,
        )
    except Exception:
        print("fl9_v2_predeploy_discovery=processing-failed", file=sys.stderr)
        return 1

    if not results:
        return 0

    try:
        _drop_to_runtime_identity()
        for result in results:
            published = publish_fl9_v2_discovery_control_result(
                result,
                marker_directory=_RESULT_MARKER_DIRECTORY,
            )
            if not published:
                print(
                    "fl9_v2_predeploy_discovery=result-exchange-missing",
                    file=sys.stderr,
                )
                return 1
    except Exception:
        print("fl9_v2_predeploy_discovery=publish-failed", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args:
        return 2
    return run_predeploy_discovery()


if __name__ == "__main__":
    raise SystemExit(main())
