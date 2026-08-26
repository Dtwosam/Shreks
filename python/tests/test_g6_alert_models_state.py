from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path

import pytest

from shreks_brain.alerts import (
    AlertCode,
    AlertEvent,
    AlertSeverity,
    AlertState,
    G6_ALERT_STATE_SCHEMA_VERSION,
    decode_alert_state,
    encode_alert_state,
    load_alert_state,
    write_alert_state,
)
from shreks_brain.alerts.state import AlertStateError


def _event(event_id: str = "condition:CORE_RUNTIME_STOPPED") -> AlertEvent:
    return AlertEvent(
        event_id=event_id,
        code=AlertCode.CORE_RUNTIME_STOPPED,
        severity=AlertSeverity.CRITICAL,
        observed_at_unix_ms=1_000,
        title="PAPER runtime is not fully active.",
        lines=("Units: shreks-paper-campaign.service", "LIVE TRADING: DISABLED"),
    )


def _state() -> AlertState:
    return AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=7,
        last_proof_decision="INSUFFICIENT_EVIDENCE",
        active_condition_keys=("CORE_RUNTIME_STOPPED", "MARKET_DATA_STALE"),
        pending_events=(_event(),),
        last_observed_at_unix_ms=1_500,
    )


def test_alert_event_and_state_models_are_frozen_and_exact() -> None:
    event = _event()
    state = _state()

    assert event.code is AlertCode.CORE_RUNTIME_STOPPED
    assert event.severity is AlertSeverity.CRITICAL
    assert state.schema_version == "g6-alert-state-v1"
    assert tuple(code.value for code in AlertCode) == (
        "CORE_RUNTIME_STOPPED",
        "SYSTEMD_HEALTH_UNAVAILABLE",
        "TELEMETRY_SOURCE_UNAVAILABLE",
        "MARKET_DATA_STALE",
        "PROVIDER_FAILURE_PERSISTENT",
        "CHECKPOINT_UNAVAILABLE",
        "PAPER_SOURCE_UNAVAILABLE",
        "ACCOUNTING_NOT_RECONCILED",
        "GLOBAL_RISK_HALT_ACTIVE",
        "KILL_SWITCH_ACTIVE",
        "POSITION_OPENED",
        "POSITION_CLOSED",
        "EXECUTION_DEGRADED",
        "PAPER_PROOF_SUFFICIENT",
        "CHALLENGER_PROOF_FAILED",
        "ALERTING_STARTED",
    )
    assert tuple(severity.value for severity in AlertSeverity) == (
        "INFO",
        "WARNING",
        "CRITICAL",
    )

    with pytest.raises(FrozenInstanceError):
        event.title = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        state.initialized = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AlertEvent("", AlertCode.ALERTING_STARTED, AlertSeverity.INFO, 1, "x", ()),
        lambda: AlertEvent("x", AlertCode.ALERTING_STARTED, AlertSeverity.INFO, -1, "x", ()),
        lambda: AlertEvent("x", AlertCode.ALERTING_STARTED, AlertSeverity.INFO, 1, "", ()),
        lambda: AlertEvent("x", AlertCode.ALERTING_STARTED, AlertSeverity.INFO, 1, "x", ("",)),
        lambda: AlertState("wrong", True, 0, None, (), (), None),
        lambda: AlertState(G6_ALERT_STATE_SCHEMA_VERSION, True, -1, None, (), (), None),
        lambda: AlertState(
            G6_ALERT_STATE_SCHEMA_VERSION,
            True,
            0,
            None,
            ("B", "A"),
            (),
            None,
        ),
        lambda: AlertState(
            G6_ALERT_STATE_SCHEMA_VERSION,
            True,
            0,
            None,
            ("A", "A"),
            (),
            None,
        ),
        lambda: AlertState(
            G6_ALERT_STATE_SCHEMA_VERSION,
            True,
            0,
            None,
            (),
            (_event("duplicate"), _event("duplicate")),
            None,
        ),
    ],
)
def test_model_validation_fails_closed(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_alert_state_codec_is_canonical_and_round_trips() -> None:
    state = _state()
    payload = encode_alert_state(state)

    assert isinstance(payload, bytes)
    assert payload.endswith(b"\n")
    assert decode_alert_state(payload) == state
    assert decode_alert_state(payload.decode("utf-8")) == state
    document = json.loads(payload)
    assert set(document) == {
        "active_condition_keys",
        "highest_ledger_sequence",
        "initialized",
        "last_observed_at_unix_ms",
        "last_proof_decision",
        "pending_events",
        "schema_version",
    }
    assert "token" not in payload.decode("utf-8").lower()
    assert "secret" not in payload.decode("utf-8").lower()


def test_alert_state_decoder_rejects_noncanonical_unknown_or_invalid_payloads() -> None:
    payload = encode_alert_state(_state())
    document = json.loads(payload)

    with pytest.raises(AlertStateError, match="canonical"):
        decode_alert_state(payload.rstrip(b"\n"))

    pretty = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    with pytest.raises(AlertStateError, match="canonical"):
        decode_alert_state(pretty)

    unknown = dict(document)
    unknown["extra"] = True
    with pytest.raises(AlertStateError):
        decode_alert_state(
            (json.dumps(unknown, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )

    bad_code = dict(document)
    bad_code["pending_events"] = [dict(document["pending_events"][0], code="UNKNOWN")]
    with pytest.raises(AlertStateError):
        decode_alert_state(
            (json.dumps(bad_code, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )

    nonfinite = payload.decode("utf-8").replace('"observed_at_unix_ms":1000', '"observed_at_unix_ms":NaN')
    with pytest.raises(AlertStateError):
        decode_alert_state(nonfinite)

    with pytest.raises(AlertStateError):
        decode_alert_state(b"\xff")


def test_missing_state_is_first_install_but_corrupt_existing_state_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "alerts" / "state.json"
    assert load_alert_state(path) is None

    path.parent.mkdir()
    path.write_text("{broken\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(AlertStateError):
        load_alert_state(path)
    assert path.read_bytes() == before


def test_write_alert_state_is_atomic_private_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "alerts" / "state.json"
    path.parent.mkdir()

    write_alert_state(path, _state())

    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_alert_state(path) == _state()
    leftovers = tuple(path.parent.glob("*.tmp"))
    assert leftovers == ()


def test_failed_atomic_replace_preserves_existing_state(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "alerts" / "state.json"
    path.parent.mkdir()
    original = AlertState(
        schema_version=G6_ALERT_STATE_SCHEMA_VERSION,
        initialized=True,
        highest_ledger_sequence=1,
        last_proof_decision=None,
        active_condition_keys=(),
        pending_events=(),
        last_observed_at_unix_ms=10,
    )
    write_alert_state(path, original)
    before = path.read_bytes()

    import shreks_brain.alerts.state as state_module

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(state_module.os, "replace", fail_replace)
    with pytest.raises(AlertStateError, match="write"):
        write_alert_state(path, _state())

    assert path.read_bytes() == before
    assert tuple(path.parent.glob("*.tmp")) == ()


def test_state_rejects_nonfinite_observation_indirectly() -> None:
    # Alert/state timestamps are integers, so floats and NaN never enter canonical state.
    with pytest.raises(ValueError):
        AlertEvent(
            "x",
            AlertCode.ALERTING_STARTED,
            AlertSeverity.INFO,
            math.nan,  # type: ignore[arg-type]
            "started",
            (),
        )
