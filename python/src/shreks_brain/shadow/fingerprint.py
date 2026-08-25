from __future__ import annotations

from dataclasses import fields
from enum import Enum
import hashlib
import json
import math
from typing import Mapping

from shreks_brain.research import RESEARCH_FEATURE_COLUMNS

from .models import ShadowDecisionRecord


def decision_feature_fingerprint(row: dict[str, object]) -> str:
    return sha256_canonical(
        {column: row[column] for column in RESEARCH_FEATURE_COLUMNS}
    )


def record_fingerprint(record: ShadowDecisionRecord) -> str:
    return sha256_canonical(
        {
            field.name: getattr(record, field.name)
            for field in fields(record)
            if field.name != "record_fingerprint_sha256"
        }
    )


def sha256_canonical(value: object) -> str:
    payload = json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("fingerprint material cannot contain non-finite floats")
        return {"__float_hex__": value.hex()}
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("fingerprint mappings must use string keys")
        return {key: _normalize(value[key]) for key in sorted(value)}
    raise ValueError(f"unsupported fingerprint material type: {type(value).__name__}")
