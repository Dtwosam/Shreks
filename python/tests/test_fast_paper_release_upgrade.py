from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_release_upgrade as upgrade


def _bootstrap(
    *,
    decision_sequence: int | None,
    execution_sequence: int | None,
    pending_buy: object | None = None,
):
    cursor = (
        None
        if decision_sequence is None
        else SimpleNamespace(decision_sequence=decision_sequence)
    )
    return SimpleNamespace(
        decision_bootstrap=SimpleNamespace(
            state=SimpleNamespace(cursor=cursor),
        ),
        execution_bootstrap=SimpleNamespace(
            checkpoint=SimpleNamespace(
                state=SimpleNamespace(pending_buy=pending_buy),
            ),
            runtime_state=SimpleNamespace(
                last_processed_source_sequence=execution_sequence,
            ),
        ),
    )


def test_clean_release_boundary_requires_equal_cursors_and_no_pending_buy() -> None:
    upgrade._require_clean_handoff_boundary(
        _bootstrap(
            decision_sequence=17,
            execution_sequence=17,
        )
    )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="equal decision/execution cursors",
    ):
        upgrade._require_clean_handoff_boundary(
            _bootstrap(
                decision_sequence=18,
                execution_sequence=17,
            )
        )

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="pending BUY",
    ):
        upgrade._require_clean_handoff_boundary(
            _bootstrap(
                decision_sequence=17,
                execution_sequence=17,
                pending_buy=object(),
            )
        )


def test_target_file_retargets_release_local_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / ("a" * 40)
    target = tmp_path / ("b" * 40)
    relative = Path("python/bin/fast-decision")
    (source / relative).parent.mkdir(parents=True)
    (target / relative).parent.mkdir(parents=True)
    (source / relative).write_text("same", encoding="utf-8")
    (target / relative).write_text("same", encoding="utf-8")

    resolved = upgrade._target_file(
        source / relative,
        source,
        target,
        allow_external=False,
    )

    assert resolved == (target / relative).resolve()


def test_target_file_rejects_external_binary_but_allows_external_champion(
    tmp_path: Path,
) -> None:
    source = tmp_path / ("a" * 40)
    target = tmp_path / ("b" * 40)
    source.mkdir()
    target.mkdir()
    external = tmp_path / "champion.json"
    external.write_text("{}", encoding="utf-8")

    with pytest.raises(
        upgrade.FastPaperReleaseUpgradeError,
        match="escaped current release",
    ):
        upgrade._target_file(
            external,
            source,
            target,
            allow_external=False,
        )

    assert (
        upgrade._target_file(
            external,
            source,
            target,
            allow_external=True,
        )
        == external.resolve()
    )


def test_archive_release_bound_sources_moves_everything_except_checkpoint(
    tmp_path: Path,
) -> None:
    roots = {}
    for name in (
        "decision",
        "execution",
        "buy",
        "usd",
        "reduction",
        "retry",
    ):
        root = tmp_path / "active" / name
        root.mkdir(parents=True)
        roots[name] = root
    checkpoint = roots["decision"] / "runtime-state.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    evidence = roots["decision"] / "shadow-1.json"
    evidence.write_text("{}\n", encoding="utf-8")
    source = roots["execution"] / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    config = SimpleNamespace(
        decision_config=SimpleNamespace(
            evidence_directory=roots["decision"],
            checkpoint_path=checkpoint,
        ),
        execution_config=SimpleNamespace(
            source_directory=roots["execution"],
        ),
        buy_authority_source_directory=roots["buy"],
        quote_usd_source_directory=roots["usd"],
        reduction_source_directory=roots["reduction"],
        pending_buy_retry_source_directory=roots["retry"],
    )
    archive = tmp_path / "history" / "run-1"

    moved = upgrade._archive_release_bound_sources(
        config,
        archive,
    )

    assert checkpoint.is_file()
    assert not evidence.exists()
    assert not source.exists()
    assert len(moved) == 2
    assert (archive / "decision" / evidence.name).is_file()
    assert (archive / "execution" / source.name).is_file()


def test_release_upgrade_command_runner_rejects_unreviewed_systemd_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    for forbidden in (
        ("systemctl", "restart", upgrade._UNIT),
        ("systemctl", "enable", upgrade._UNIT),
        ("systemctl", "stop", "other.service"),
        ("systemctl", "start", upgrade._UNIT),
        ("systemctl", "show", "other.service", "--property=MainPID", "--no-pager"),
    ):
        with pytest.raises(
            upgrade.FastPaperReleaseUpgradeError,
            match="allowlist",
        ):
            upgrade._default_command_runner(forbidden)


def test_release_upgrade_source_has_no_legacy_trade_or_live_authority() -> None:
    source = Path(upgrade.__file__).read_text(encoding="utf-8")

    for required in (
        "initialize_fast_paper_authoritative_release_handoff",
        "build_fast_paper_release_authorization",
        "REVOKED_MANUAL_RECOVERY",
        "signing_submission_authority",
        "live_authority",
    ):
        assert required in source

    for forbidden in (
        "shreks_brain.observer_campaign.runtime",
        "score_candidate",
        "decide_entry",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
        "LIVE_ENABLED",
        '("systemctl", "restart"',
        '("systemctl", "enable"',
        '("systemctl", "disable"',
    ):
        assert forbidden not in source
