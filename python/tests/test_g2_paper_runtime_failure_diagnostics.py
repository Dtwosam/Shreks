from __future__ import annotations

import json

from shreks_brain.observer_campaign.coordinator import ObserverCampaignCoordinatorError
from shreks_brain.observer_campaign.runtime import (
    ObserverPaperCampaignRuntimeError,
    _failure_status_document,
)


def test_failure_status_reports_bounded_internal_causal_chain_without_secret_fields() -> None:
    root = ValueError("no fresh observer market snapshot matches caller source priority")
    coordinator = ObserverCampaignCoordinatorError(
        "observer candidate 9267 assembly failed: "
        "no fresh observer market snapshot matches caller source priority"
    )
    coordinator.__cause__ = root
    runtime = ObserverPaperCampaignRuntimeError("paper campaign cycle failed closed")
    runtime.__cause__ = coordinator

    document = _failure_status_document(runtime)

    assert document == {
        "schema_version": "g1c-paper-runtime-status-v1",
        "mode": "PAPER",
        "state": "FAILED",
        "error_type": "ObserverPaperCampaignRuntimeError",
        "error_message": "paper campaign cycle failed closed",
        "cause_chain": [
            {
                "error_type": "ObserverCampaignCoordinatorError",
                "error_message": (
                    "observer candidate 9267 assembly failed: "
                    "no fresh observer market snapshot matches caller source priority"
                ),
            },
            {
                "error_type": "ValueError",
                "error_message": (
                    "no fresh observer market snapshot matches caller source priority"
                ),
            },
        ],
    }

    payload = json.dumps(document, sort_keys=True).lower()
    for forbidden in (
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "authorization",
        "bearer ",
    ):
        assert forbidden not in payload


def test_failure_status_bounds_cause_depth_and_message_length() -> None:
    current: BaseException = ValueError("x" * 1000)
    for index in range(10):
        wrapper = RuntimeError(f"layer-{index}")
        wrapper.__cause__ = current
        current = wrapper

    document = _failure_status_document(current)

    assert len(document["cause_chain"]) <= 4
    assert all(len(item["error_message"]) <= 240 for item in document["cause_chain"])
    assert len(document["error_message"]) <= 240
