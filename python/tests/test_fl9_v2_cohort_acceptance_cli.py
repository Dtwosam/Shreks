from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fl9_v2_cohort_acceptance import cli


def test_cli_builds_with_only_database_and_destination(monkeypatch, capsys) -> None:
    calls = {}

    class Source:
        def __init__(self, path):
            calls["source_path"] = path

    class Store:
        def __init__(self, path):
            calls["store_path"] = path

    def build(**kwargs):
        calls["build"] = kwargs
        return "semantic"

    def write(semantic, destination, *, policy, floor_policy):
        calls["write"] = {
            "semantic": semantic,
            "destination": destination,
            "policy": policy,
            "floor_policy": floor_policy,
        }
        return SimpleNamespace(manifest="manifest")

    monkeypatch.setattr(cli, "SqliteFl9V2CohortSource", Source)
    monkeypatch.setattr(cli, "Fl9TradableUniverseStore", Store)
    monkeypatch.setattr(cli, "build_fl9_v2_cohort_acceptance", build)
    monkeypatch.setattr(cli, "write_fl9_v2_cohort_acceptance", write)
    monkeypatch.setattr(
        cli,
        "encode_manifest_for_stdout",
        lambda value: '{"artifact_fingerprint_sha256":"a"}\n',
    )

    assert cli.main(
        [
            "--database",
            "/var/lib/shreks/shreks.db",
            "--destination",
            "/var/lib/shreks/cohort",
        ]
    ) == 0

    assert calls["source_path"] == "/var/lib/shreks/shreks.db"
    assert calls["store_path"] == "/var/lib/shreks/shreks.db"
    assert calls["write"]["semantic"] == "semantic"
    assert calls["write"]["destination"] == "/var/lib/shreks/cohort"
    assert calls["write"]["policy"].horizon_ms == 30_000
    assert calls["write"]["floor_policy"].minimum_total_eligible_rows == 250_000
    assert capsys.readouterr().out == (
        '{"artifact_fingerprint_sha256":"a"}\n'
    )


@pytest.mark.parametrize(
    "flag,value",
    (
        ("--horizon-ms", "60000"),
        ("--selection-at-unix-ms", "1"),
        ("--source-session", "124"),
        ("--minimum-test-rows", "1"),
    ),
)
def test_cli_rejects_policy_override_flags(flag, value) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--database",
                "/tmp/db",
                "--destination",
                "/tmp/out",
                flag,
                value,
            ]
        )


def test_cli_source_is_wall_clock_free_and_entrypoint_is_registered() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fl9_v2_cohort_acceptance"
        / "cli.py"
    ).read_text(encoding="utf-8")
    assert "time.time" not in source
    assert "datetime" not in source

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (
        'shreks-fl9-v2-cohort-acceptance = '
        '"shreks_brain.fl9_v2_cohort_acceptance.cli:main"'
    ) in pyproject
