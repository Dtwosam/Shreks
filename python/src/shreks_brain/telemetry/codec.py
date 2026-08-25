from __future__ import annotations

from dataclasses import asdict
import json

from .models import TelemetrySnapshot


def encode_telemetry_snapshot(snapshot: TelemetrySnapshot) -> str:
    if type(snapshot) is not TelemetrySnapshot:
        raise ValueError("snapshot must be an exact TelemetrySnapshot")
    return json.dumps(
        asdict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
