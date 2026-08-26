from __future__ import annotations

from shreks_brain.dashboard.page import render_dashboard_page


def _source() -> str:
    payload = render_dashboard_page()
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


def test_emergency_controls_card_is_static_prominent_and_safety_only() -> None:
    source = _source()

    assert "LIVE TRADING: DISABLED" in source
    assert 'id="emergency-controls"' in source
    assert "Emergency controls" in source
    assert 'id="control-availability"' in source
    assert 'id="control-revision"' in source
    assert 'id="control-entry-halt"' in source
    assert 'id="control-kill-switch"' in source
    assert 'id="control-last-command"' in source
    assert 'id="control-updated-at"' in source
    assert 'id="halt-new-entries"' in source
    assert 'id="emergency-kill"' in source
    assert ">HALT NEW ENTRIES<" in source
    assert ">EMERGENCY KILL SWITCH<" in source

    for forbidden in (
        ">BUY<",
        ">SELL<",
        "LIVE ENABLE",
        "PROMOTE STRATEGY",
        "RESET KILL SWITCH",
        "CLEAR ENTRY HALT",
        "RESTART SERVICE",
        "WALLET",
    ):
        assert forbidden not in source.upper()


def test_control_context_is_same_origin_and_drives_button_safety_state() -> None:
    source = _source()

    assert 'fetch("/api/v1/operator-controls", {credentials: "same-origin"})' in source
    assert 'setText("control-availability","AVAILABLE")' in source
    assert 'setText("control-revision",controlState.revision)' in source
    assert 'setText("control-entry-halt",yesNo(controlState.halt_new_entries))' in source
    assert 'setText("control-kill-switch",yesNo(controlState.kill_switch_active))' in source
    assert 'haltButton.disabled=!controlState||controlState.halt_new_entries||controlState.kill_switch_active' in source
    assert 'killButton.disabled=!controlState||controlState.kill_switch_active' in source
    assert 'setText("control-availability","SOURCE_UNAVAILABLE")' in source


def test_safety_actions_send_only_revision_csrf_and_exact_kill_confirmation() -> None:
    source = _source()

    assert 'method: "POST"' in source
    assert '"Content-Type":"application/json"' in source
    assert '"X-Shreks-CSRF":controlState.csrf_token' in source
    assert 'JSON.stringify({expected_revision:controlState.revision})' in source
    assert 'confirmation:"EMERGENCY KILL SWITCH"' in source
    assert '"/api/v1/operator-controls/halt-new-entries"' in source
    assert '"/api/v1/operator-controls/emergency-kill"' in source
    assert 'window.confirm("EMERGENCY KILL SWITCH will halt new entries and trigger the existing emergency exit path. Continue?")' in source

    for forbidden_payload_shape in (
        "JSON.stringify({amount:",
        "JSON.stringify({size:",
        "JSON.stringify({mint:",
        "JSON.stringify({slippage:",
        "JSON.stringify({wallet:",
        "live_enable:",
        "promotion:",
    ):
        assert forbidden_payload_shape not in source


def test_control_page_keeps_safe_dom_and_dependency_free_contract() -> None:
    source = _source()
    lowered = source.lower()

    assert ".textContent" in source
    assert "innerHTML" not in source
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "cdn" not in lowered
    assert "analytics" not in lowered
    assert "<link" not in lowered
    assert "src=\"" not in lowered
