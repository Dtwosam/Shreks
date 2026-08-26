from __future__ import annotations

import json

import pytest

from shreks_brain.telemetry import (
    decode_telemetry_snapshot,
    encode_telemetry_snapshot,
)

from test_g4_telemetry_models import _snapshot


def _document() -> dict[str, object]:
    return json.loads(encode_telemetry_snapshot(_snapshot()))


def _canonical(document: object) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def test_decoder_round_trips_canonical_text_and_utf8_bytes() -> None:
    expected = _snapshot()
    payload = encode_telemetry_snapshot(expected)

    assert decode_telemetry_snapshot(payload) == expected
    assert decode_telemetry_snapshot(payload.encode("utf-8")) == expected


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: {**document, "extra": True},
        lambda document: {**document, "schema_version": "g4-telemetry-snapshot-v999"},
        lambda document: {**document, "mode": "LIVE"},
        lambda document: {**document, "overall_status": "UNKNOWN"},
        lambda document: {
            **document,
            "system": {**document["system"], "extra": True},
        },
        lambda document: {
            **document,
            "trading": {**document["trading"], "candidate_count": "12"},
        },
        lambda document: {
            **document,
            "proof_risk": {**document["proof_risk"], "live_state": "ENABLED"},
        },
    ],
)
def test_decoder_rejects_schema_drift_unknown_fields_and_wrong_types(mutate) -> None:
    document = _document()
    mutated = mutate(document)

    with pytest.raises(ValueError):
        decode_telemetry_snapshot(_canonical(mutated))


def test_decoder_requires_canonical_json_and_trailing_newline() -> None:
    payload = encode_telemetry_snapshot(_snapshot())
    document = json.loads(payload)

    with pytest.raises(ValueError, match="canonical"):
        decode_telemetry_snapshot(payload.rstrip("\n"))

    pretty = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    with pytest.raises(ValueError, match="canonical"):
        decode_telemetry_snapshot(pretty)


def test_decoder_rejects_non_utf8_non_json_and_nonfinite_constants() -> None:
    with pytest.raises(ValueError):
        decode_telemetry_snapshot(b"\xff")
    with pytest.raises(ValueError):
        decode_telemetry_snapshot("not-json\n")

    document = _document()
    payload = _canonical(document).replace('"market_age_ms":1000', '"market_age_ms":NaN')
    with pytest.raises(ValueError):
        decode_telemetry_snapshot(payload)


def test_decoder_rejects_non_exact_payload_input_type() -> None:
    with pytest.raises(ValueError):
        decode_telemetry_snapshot(123)  # type: ignore[arg-type]
