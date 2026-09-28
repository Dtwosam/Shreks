from __future__ import annotations

from pathlib import Path

import pytest

import shreks_brain.fast_paper_authoritative_cutover_config as cutover_config

from test_fast_paper_shadow_decision import _manifest


def _environment(manifest) -> dict[str, str]:
    return {
        "SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH": (
            "/etc/shreks/fast-paper-runtime-manifest.json"
        ),
        "SHREKS_FAST_PAPER_SERVICE_POLICY_PATH": (
            "/etc/shreks/fast-paper-shadow-service-policy.json"
        ),
        "SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/decision"
        ),
        "SHREKS_FAST_PAPER_INTERVAL_SECONDS": "2.0",
        "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH": (
            "/etc/shreks/fast-paper-shadow-execution-policy.json"
        ),
        "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/execution-sources"
        ),
        "SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH": (
            str(Path(manifest.observer_database_path).resolve())
        ),
        "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID": "fast-authoritative-run-1",
        "SHREKS_FAST_PAPER_BUY_AUTHORITY_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/buy-authority-sources"
        ),
        "SHREKS_FAST_PAPER_QUOTE_USD_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/quote-usd-sources"
        ),
        "SHREKS_FAST_PAPER_REDUCTION_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/reduction-sources"
        ),
        "SHREKS_FAST_PAPER_PENDING_BUY_RETRY_SOURCE_DIRECTORY": (
            "/var/lib/shreks/fast-paper-authoritative/pending-buy-retry-sources"
        ),
    }


def test_authoritative_cutover_environment_round_trips_and_binds_database(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    environment = _environment(manifest)
    path = tmp_path / "fast-paper-authoritative.env"
    path.write_text(
        cutover_config.encode_fast_paper_authoritative_cutover_environment(
            environment
        ),
        encoding="utf-8",
    )

    restored = (
        cutover_config.read_fast_paper_authoritative_cutover_environment(path)
    )
    config = (
        cutover_config.validate_fast_paper_authoritative_cutover_environment(
            restored,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )
    )

    assert restored == environment
    assert config.execution_config.run_id == "fast-authoritative-run-1"
    assert (
        config.execution_config.database_path
        == Path(manifest.observer_database_path).resolve()
    )
    assert config.decision_config.maximum_decisions == 1


@pytest.mark.parametrize(
    "mutator",
    (
        lambda env: env.__setitem__(
            "SHREKS_FAST_PAPER_INTERVAL_SECONDS", "3.0"
        ),
        lambda env: env.__setitem__(
            "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID",
            "replace-with-authoritative-fast-run-id",
        ),
        lambda env: env.__setitem__(
            "SHREKS_FAST_PAPER_DECISION_EVIDENCE_DIRECTORY",
            "/tmp/not-production",
        ),
        lambda env: env.__setitem__(
            "SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH",
            "/tmp/not-observer.sqlite3",
        ),
    ),
)
def test_authoritative_cutover_environment_rejects_drift(
    tmp_path: Path,
    mutator,
) -> None:
    manifest = _manifest(tmp_path)
    environment = _environment(manifest)
    mutator(environment)
    with pytest.raises(
        cutover_config.FastPaperAuthoritativeCutoverConfigError
    ):
        cutover_config.validate_fast_paper_authoritative_cutover_environment(
            environment,
            manifest,
            authoritative_database_path=manifest.observer_database_path,
        )


def test_authoritative_cutover_environment_parser_rejects_shell_and_duplicates(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    environment = _environment(manifest)
    valid = (
        cutover_config.encode_fast_paper_authoritative_cutover_environment(
            environment
        )
    )
    for payload in (
        valid + "UNKNOWN=value\n",
        valid
        + "SHREKS_FAST_PAPER_INTERVAL_SECONDS=2.0\n",
        valid.replace(
            "SHREKS_FAST_PAPER_INTERVAL_SECONDS=2.0",
            "SHREKS_FAST_PAPER_INTERVAL_SECONDS=$(id)",
        ),
    ):
        path = tmp_path / "candidate.env"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(
            cutover_config.FastPaperAuthoritativeCutoverConfigError
        ):
            cutover_config.read_fast_paper_authoritative_cutover_environment(
                path
            )
