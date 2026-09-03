from __future__ import annotations

import json
from pathlib import Path

import pytest

from fast_forecast_champion_fixtures import continuous_and_binary_sources
from shreks_brain.fast_champion import (
    build_fast_forecast_champion,
    read_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_learning import FastForecastTarget, predict_fast_forecast


def _champion():
    continuous, binary = continuous_and_binary_sources()
    champion = build_fast_forecast_champion(
        champion_version="forecast-champion-v1",
        decision_reference="selection-proof-001",
        decided_at_unix_ms=10_000,
        reason="explicit fixture selection",
        member_sources=(
            (continuous[1], continuous[2], continuous[3]),
            (binary[1], binary[2], binary[3]),
        ),
    )
    return champion, continuous[0]


def test_codec_round_trip_is_exact_and_refuses_overwrite(tmp_path: Path) -> None:
    champion, _ = _champion()
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    first_bytes = path.read_bytes()
    assert first_bytes.endswith(b"\n")
    assert read_fast_forecast_champion(path) == champion
    with pytest.raises(FileExistsError):
        write_fast_forecast_champion(champion, path)

    second_path = tmp_path / "champion-copy.json"
    write_fast_forecast_champion(champion, second_path)
    assert second_path.read_bytes() == first_bytes


def test_loaded_member_preserves_reference_python_inference(tmp_path: Path) -> None:
    champion, bundle = _champion()
    path = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, path)
    loaded = read_fast_forecast_champion(path)
    source_member = champion.member_for(FastForecastTarget.ENDPOINT_RETURN_BPS, 250)
    loaded_member = loaded.member_for(FastForecastTarget.ENDPOINT_RETURN_BPS, 250)
    record = bundle.features.records[0]
    assert predict_fast_forecast(loaded_member.forecast_artifact, record) == predict_fast_forecast(
        source_member.forecast_artifact,
        record,
    )


def test_codec_rejects_unknown_keys_and_fingerprint_tampering(tmp_path: Path) -> None:
    champion, _ = _champion()
    source = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, source)
    payload = json.loads(source.read_text(encoding="utf-8"))

    payload["unknown"] = True
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        read_fast_forecast_champion(unknown)

    payload.pop("unknown")
    payload["champion_fingerprint_sha256"] = "f" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        read_fast_forecast_champion(tampered)


def test_codec_rejects_embedded_model_artifact_tampering(tmp_path: Path) -> None:
    champion, _ = _champion()
    source = tmp_path / "champion.json"
    write_fast_forecast_champion(champion, source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["members"][0]["forecast_artifact"]["artifact_fingerprint_sha256"] = "a" * 64
    tampered = tmp_path / "embedded-tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact fingerprint"):
        read_fast_forecast_champion(tampered)
