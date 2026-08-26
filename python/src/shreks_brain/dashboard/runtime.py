from __future__ import annotations

from .config import load_dashboard_runtime_config
from .http import run_dashboard_server


def main() -> int:
    config = load_dashboard_runtime_config()
    run_dashboard_server(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
