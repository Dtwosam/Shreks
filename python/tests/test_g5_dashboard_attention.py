from __future__ import annotations

from shreks_brain.dashboard.page import render_dashboard_page


def test_dashboard_has_attention_summary_for_operator_problems() -> None:
    source = render_dashboard_page().decode("utf-8")

    assert 'id="attention-layer"' in source
    assert 'id="attention-status"' in source
    assert 'id="attention-list"' in source
    assert "Attention / Problems" in source
    assert "renderAttention" in source
    assert "unhealthy_provider_count" in source
    assert "global_risk_halt" in source
    assert "accounting_integrity" in source
    assert "kill_switch_active" in source
    assert "halt_new_entries" in source
    assert "No active problems detected" in source


def test_attention_summary_uses_existing_read_side_data_only() -> None:
    source = render_dashboard_page().decode("utf-8")

    assert 'fetch("/api/v1/snapshot", {credentials: "same-origin"})' in source
    assert 'fetch("/api/v1/operator-controls", {credentials: "same-origin"})' in source
    assert "/api/v1/alerts" not in source
    assert "SHREKS_ALERTS_TELEGRAM" not in source
    assert "sendMessage" not in source
