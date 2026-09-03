from __future__ import annotations

import json
from pathlib import Path

import pytest

from fast_forecast_evaluation_fixtures import (
    build_run,
    evaluation_contexts,
    evaluation_policy,
)
from shreks_brain.fast_evaluation import (
    evaluate_fast_forecasts,
    read_fast_forecast_evaluation_report,
    write_fast_forecast_evaluation_report,
)


def report_fixture():
    bundle, run = build_run()
    return evaluate_fast_forecasts(
        bundle,
        run,
        evaluation_contexts(run),
        evaluation_policy(),
    )


def test_report_codec_is_canonical_immutable_and_round_trips(tmp_path: Path) -> None:
    report = report_fixture()
    path = tmp_path / "report.json"
    write_fast_forecast_evaluation_report(report, path)
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    assert read_fast_forecast_evaluation_report(path) == report
    with pytest.raises(FileExistsError):
        write_fast_forecast_evaluation_report(report, path)


def test_report_codec_rejects_fingerprint_tamper_and_unknown_keys(tmp_path: Path) -> None:
    report = report_fixture()
    source = tmp_path / "source.json"
    write_fast_forecast_evaluation_report(report, source)
    payload = json.loads(source.read_text(encoding="utf-8"))

    tampered = dict(payload)
    tampered["evaluation_report_fingerprint_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint|tamper"):
        read_fast_forecast_evaluation_report(tampered_path)

    unknown = dict(payload)
    unknown["unexpected"] = True
    unknown_path = tmp_path / "unknown.json"
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown|key|schema"):
        read_fast_forecast_evaluation_report(unknown_path)
