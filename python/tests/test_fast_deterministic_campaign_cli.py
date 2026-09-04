from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shreks_brain.fast_deterministic_campaign.cli import (
    FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_NAME,
    FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_VERSION,
    main,
)


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def test_console_launcher_accepts_one_request_and_prints_canonical_result(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    seal_path = tmp_path / "campaign.invocation"
    manifest = SimpleNamespace(
        request_fingerprint_sha256="a" * 64,
        source_snapshot_fingerprint_sha256="b" * 64,
        campaign_artifact_fingerprint_sha256="c" * 64,
        invocation_fingerprint_sha256="d" * 64,
    )
    captured = {}

    def fake_run(path):
        captured["path"] = path
        return SimpleNamespace(path=seal_path, manifest=manifest)

    monkeypatch.setattr(
        "shreks_brain.fast_deterministic_campaign.cli."
        "run_fast_deterministic_campaign_invocation_file",
        fake_run,
    )

    assert main([str(request)]) == 0

    assert captured["path"] == request
    output = capsys.readouterr().out
    expected = {
        "schema_name": FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_CAMPAIGN_CLI_RESULT_SCHEMA_VERSION,
        "request_fingerprint_sha256": "a" * 64,
        "source_snapshot_fingerprint_sha256": "b" * 64,
        "campaign_artifact_fingerprint_sha256": "c" * 64,
        "invocation_fingerprint_sha256": "d" * 64,
        "invocation_path": str(seal_path),
    }
    assert output == _canonical(expected) + "\n"


@pytest.mark.parametrize("argv", [[], ["a", "b"]])
def test_console_launcher_requires_exactly_one_request_argument(argv) -> None:
    with pytest.raises(SystemExit) as error:
        main(argv)
    assert error.value.code == 2


def test_console_launcher_is_registered_as_installable_script() -> None:
    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert '[project.scripts]' in pyproject
    assert (
        'shreks-fast-deterministic-campaign = '
        '"shreks_brain.fast_deterministic_campaign.cli:main"'
    ) in pyproject


def test_console_launcher_has_no_campaign_logic_or_authority_expansion() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_deterministic_campaign"
        / "cli.py"
    ).read_text(encoding="utf-8")

    assert "run_fast_deterministic_campaign_invocation_file(" in source
    for forbidden in (
        "write_fast_deterministic_campaign_artifact",
        "hydrate_fast_deterministic_comparison_evidence",
        "run_fast_deterministic_comparison_catalog_matrix",
        "evaluate_fast_policy_superiority",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "requests.",
        "httpx",
    ):
        assert forbidden not in source
