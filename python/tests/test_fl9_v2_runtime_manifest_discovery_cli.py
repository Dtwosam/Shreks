from __future__ import annotations

import shreks_brain.fl9_v2_runtime_manifest_discovery as discovery


def _base_args() -> list[str]:
    return [
        "--cohort",
        "/does/not/matter/cohort",
        "--active-runtime-manifest",
        "/does/not/matter/active.json",
        "--backup-root",
        "/does/not/matter/backups",
    ]


def test_cli_rejects_mixed_request_and_explicit_authority(capsys) -> None:
    result = discovery.main(
        _base_args()
        + [
            "--v2-host-request-authority",
            "/does/not/matter/request.json",
            "--hydration-policy-version",
            "must-not-mix",
        ]
    )

    assert result == 1
    stderr = capsys.readouterr().err
    assert "cannot be mixed with explicit" in stderr


def test_cli_rejects_incomplete_explicit_authority(capsys) -> None:
    result = discovery.main(_base_args())

    assert result == 1
    stderr = capsys.readouterr().err
    assert "explicit discovery authority requires" in stderr
