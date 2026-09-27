from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import shreks_brain.fast_paper_shadow_decision_telemetry as telemetry


_SHA = "a" * 40
_MANIFEST = "b" * 64
_CHAMPION = "c" * 64


def _evidence(
    sequence: int,
    *,
    action: str = "SKIP",
    reason: str | None = None,
    as_of_unix_ms: int | None = None,
    lag_ms: int = 10,
    latency_ms: int = 2,
    horizon_ms: int | None = None,
    reward_bps: float = 10.0,
    risk_bps: float = 2.0,
    cost_bps: float = 1.0,
    value_bps: float = 7.0,
    release_sha: str = _SHA,
    manifest_fingerprint: str = _MANIFEST,
    champion_version: str = "champion-v1",
    champion_fingerprint: str = _CHAMPION,
    policy_version: int = 4,
    entry_state: str = "EXECUTABLE",
    exit_state: str = "EXECUTABLE",
    buy_allowed: bool = True,
    sell_executable: bool = True,
    force_sell: bool = False,
    source_event_id: str | None = None,
    evidence_fingerprint: str | None = None,
):
    as_of = (
        1_000 + (sequence * 100)
        if as_of_unix_ms is None
        else as_of_unix_ms
    )
    event_id = (
        f"event-{sequence}"
        if source_event_id is None
        else source_event_id
    )
    fingerprint = (
        hashlib.sha256(f"evidence-{sequence}".encode()).hexdigest()
        if evidence_fingerprint is None
        else evidence_fingerprint
    )
    return SimpleNamespace(
        release_source_sha=release_sha,
        manifest_fingerprint_sha256=manifest_fingerprint,
        champion_version=champion_version,
        champion_fingerprint_sha256=champion_fingerprint,
        action_policy_version=policy_version,
        source_event_id=event_id,
        source_sequence=sequence,
        as_of_unix_ms=as_of,
        evaluated_at_unix_ms=as_of + lag_ms,
        decision_latency_ns=latency_ms * 1_000_000,
        evidence_fingerprint_sha256=fingerprint,
        entry_quote=SimpleNamespace(state=entry_state),
        exit_quote=SimpleNamespace(state=exit_state),
        constraints=SimpleNamespace(
            buy_economically_allowed=buy_allowed,
            sell_executable=sell_executable,
            force_sell=force_sell,
        ),
        decision=SimpleNamespace(
            action=action,
            reason=reason or f"{action}_SELECTED",
            selected_horizon_ms=horizon_ms,
            selected_reward_bps=reward_bps,
            selected_risk_bps=risk_bps,
            selected_execution_cost_bps=cost_bps,
            selected_value_bps=value_bps,
        ),
    )


def test_collect_reuses_canonical_reader_and_enforces_visible_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    first = root / "shadow-00000000000000000001-aaaaaaaaaaaaaaaa.json"
    second = root / "shadow-00000000000000000002-bbbbbbbbbbbbbbbb.json"
    first.write_text("{}\n", encoding="utf-8")
    second.write_text("{}\n", encoding="utf-8")
    (root / ".shadow-00000000000000000003.tmp-abc").write_text(
        "partial",
        encoding="utf-8",
    )

    by_name = {
        first.name: _evidence(1, as_of_unix_ms=1_100),
        second.name: _evidence(2, as_of_unix_ms=1_200),
    }
    seen: list[str] = []

    def fake_reader(path):
        seen.append(Path(path).name)
        return by_name[Path(path).name]

    monkeypatch.setattr(
        telemetry,
        "read_fast_paper_shadow_decision_evidence",
        fake_reader,
    )

    result = telemetry.collect_fast_paper_shadow_decision_telemetry(
        evidence_directory=root,
        expected_release_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=2_000,
    )
    assert result["decision_evidence_count"] == 2
    assert seen == [first.name, second.name]

    (root / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="member",
    ):
        telemetry.collect_fast_paper_shadow_decision_telemetry(
            evidence_directory=root,
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )

    (root / "unexpected.txt").unlink()
    first.unlink()
    first.symlink_to(second)
    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="symlink",
    ):
        telemetry.collect_fast_paper_shadow_decision_telemetry(
            evidence_directory=root,
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )


def test_rollup_metrics_are_deterministic_and_action_complete() -> None:
    actions = ("BUY", "SKIP", "HOLD", "REDUCE", "SELL")
    records = tuple(
        _evidence(
            index,
            action=action,
            as_of_unix_ms=1_000 + index * 100,
            lag_ms=index * 10,
            latency_ms=index,
            horizon_ms=None if action == "SKIP" else index * 1_000,
            reward_bps=float(index * 10),
            risk_bps=float(index),
            cost_bps=float(index * 2),
            value_bps=float(index * 7),
            entry_state="UNAVAILABLE" if index == 2 else "EXECUTABLE",
            exit_state="UNAVAILABLE" if index == 3 else "EXECUTABLE",
            buy_allowed=index != 4,
            sell_executable=index != 5,
            force_sell=index == 5,
        )
        for index, action in enumerate(actions, start=1)
    )

    result = telemetry.summarize_fast_paper_shadow_decision_evidence(
        records,
        expected_release_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=3_000,
    )

    assert result["decision_evidence_count"] == 5
    assert result["decision_evidence_rate_per_second"] == 2.5
    assert result["action_counts"] == {
        "BUY": 1,
        "SKIP": 1,
        "HOLD": 1,
        "REDUCE": 1,
        "SELL": 1,
    }
    assert result["event_to_evaluation_lag_ms"] == {
        "p50": 30.0,
        "p95": 50.0,
        "p99": 50.0,
        "max": 50.0,
    }
    assert result["decision_latency_ms"] == {
        "p50": 3.0,
        "p95": 5.0,
        "p99": 5.0,
        "max": 5.0,
    }
    assert result["selected_reward_bps"]["mean"] == 30.0
    assert result["selected_risk_bps"]["mean"] == 3.0
    assert result["selected_execution_cost_bps"]["mean"] == 6.0
    assert result["selected_value_bps"]["mean"] == 21.0
    assert result["reason_counts"] == {
        "BUY_SELECTED": 1,
        "HOLD_SELECTED": 1,
        "REDUCE_SELECTED": 1,
        "SELL_SELECTED": 1,
        "SKIP_SELECTED": 1,
    }
    assert result["selected_horizon_counts"] == {
        "1000": 1,
        "3000": 1,
        "4000": 1,
        "5000": 1,
        "NONE": 1,
    }
    assert result["entry_quote_unavailable_count"] == 1
    assert result["exit_quote_unavailable_count"] == 1
    assert result["buy_economically_disallowed_count"] == 1
    assert result["sell_non_executable_count"] == 1
    assert result["force_sell_count"] == 1
    assert result["release_source_sha"] == _SHA
    assert result["manifest_fingerprint_sha256"] == _MANIFEST
    assert result["champion_fingerprint_sha256"] == _CHAMPION

    fingerprint = result["telemetry_fingerprint_sha256"]
    material = dict(result)
    material.pop("telemetry_fingerprint_sha256")
    assert fingerprint == hashlib.sha256(
        telemetry.canonical_fast_paper_shadow_decision_telemetry(
            material
        ).encode("utf-8")
    ).hexdigest()


def test_source_gaps_are_reported_and_duplicates_fail_closed() -> None:
    records = (
        _evidence(1, as_of_unix_ms=1_100),
        _evidence(3, as_of_unix_ms=1_300),
        _evidence(7, as_of_unix_ms=1_700),
    )
    result = telemetry.summarize_fast_paper_shadow_decision_evidence(
        records,
        expected_release_sha=_SHA,
        since_unix_ms=1_000,
        until_unix_ms=2_000,
    )
    assert result["source_sequence_gap_count"] == 2
    assert result["source_sequence_gap_total"] == 4
    assert result["first_source_sequence"] == 1
    assert result["last_source_sequence"] == 7

    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="source sequence",
    ):
        telemetry.summarize_fast_paper_shadow_decision_evidence(
            (records[0], _evidence(1, as_of_unix_ms=1_200)),
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )

    duplicate_event = _evidence(
        2,
        as_of_unix_ms=1_200,
        source_event_id=records[0].source_event_id,
    )
    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="source event",
    ):
        telemetry.summarize_fast_paper_shadow_decision_evidence(
            (records[0], duplicate_event),
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )

    duplicate_fingerprint = _evidence(
        2,
        as_of_unix_ms=1_200,
        evidence_fingerprint=records[0].evidence_fingerprint_sha256,
    )
    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="fingerprint",
    ):
        telemetry.summarize_fast_paper_shadow_decision_evidence(
            (records[0], duplicate_fingerprint),
            expected_release_sha=_SHA,
            since_unix_ms=1_000,
            until_unix_ms=2_000,
        )


def test_mixed_runtime_identity_or_release_fails_closed() -> None:
    first = _evidence(1, as_of_unix_ms=1_100)
    for changed in (
        _evidence(2, as_of_unix_ms=1_200, release_sha="d" * 40),
        _evidence(
            2,
            as_of_unix_ms=1_200,
            manifest_fingerprint="e" * 64,
        ),
        _evidence(
            2,
            as_of_unix_ms=1_200,
            champion_version="champion-v2",
        ),
        _evidence(
            2,
            as_of_unix_ms=1_200,
            champion_fingerprint="f" * 64,
        ),
        _evidence(2, as_of_unix_ms=1_200, policy_version=5),
    ):
        with pytest.raises(
            telemetry.FastPaperShadowDecisionTelemetryError,
            match="identity|release",
        ):
            telemetry.summarize_fast_paper_shadow_decision_evidence(
                (first, changed),
                expected_release_sha=_SHA,
                since_unix_ms=1_000,
                until_unix_ms=2_000,
            )


def test_empty_window_is_safe_canonical_zero_telemetry() -> None:
    result = telemetry.summarize_fast_paper_shadow_decision_evidence(
        (),
        expected_release_sha=_SHA,
        since_unix_ms=10_000,
        until_unix_ms=20_000,
    )
    assert result["decision_evidence_count"] == 0
    assert result["decision_evidence_rate_per_second"] == 0.0
    assert result["action_counts"] == {
        "BUY": 0,
        "SKIP": 0,
        "HOLD": 0,
        "REDUCE": 0,
        "SELL": 0,
    }
    assert result["event_to_evaluation_lag_ms"] == {
        "p50": None,
        "p95": None,
        "p99": None,
        "max": None,
    }
    assert result["decision_latency_ms"]["p50"] is None
    assert result["selected_value_bps"]["mean"] is None
    assert result["manifest_fingerprint_sha256"] is None
    assert result["champion_version"] is None
    assert result["first_source_sequence"] is None
    assert result["last_source_sequence"] is None
    payload = telemetry.canonical_fast_paper_shadow_decision_telemetry(
        result
    )
    assert payload.endswith("\n")
    assert json.loads(payload)["decision_evidence_count"] == 0


@pytest.mark.parametrize(
    ("since", "until"),
    (
        (-1, 10),
        (10, 10),
        (11, 10),
        (0, 86_400_001),
        (True, 10),
    ),
)
def test_window_validation_is_explicit_and_bounded(since, until) -> None:
    with pytest.raises(
        telemetry.FastPaperShadowDecisionTelemetryError,
        match="window",
    ):
        telemetry.summarize_fast_paper_shadow_decision_evidence(
            (),
            expected_release_sha=_SHA,
            since_unix_ms=since,
            until_unix_ms=until,
        )


def test_packaging_and_authority_firewall() -> None:
    repo = Path(__file__).resolve().parents[2]
    pyproject = (repo / "python" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    source = Path(telemetry.__file__).read_text(encoding="utf-8")

    assert (
        'shreks-fast-paper-shadow-decision-telemetry = '
        '"shreks_brain.fast_paper_shadow_decision_telemetry:main"'
    ) in pyproject

    for forbidden in (
        "shreks_brain.scoring",
        "score_candidate",
        "PaperLedger(",
        "write_fast_paper",
        "provision_fast_paper",
        "systemctl",
        "subprocess",
        "requests.",
        "httpx",
        "aiohttp",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in source
