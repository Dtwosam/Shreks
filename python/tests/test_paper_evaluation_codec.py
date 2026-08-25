from __future__ import annotations

import json
from dataclasses import replace

import pytest

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.paper_evaluation.codec import (
    build_paper_evaluation_document,
    build_paper_evaluation_ledger,
    canonical_json,
    decode_paper_evaluation_document,
    encode_paper_evaluation_ledger,
)
from shreks_brain.paper_evaluation.models import (
    PAPER_EVALUATION_SCHEMA_VERSION,
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide


ZERO_SHA = "0" * 64
SHA = "a" * 64


def _entry(**overrides: object) -> PaperEntryProvenance:
    values: dict[str, object] = dict(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA,
        strategy_version="fresh-v1",
        intent_idempotency_key="buy-1",
        mint="MintA",
        decision_as_of_unix_ms=1_000,
        setup_name="fresh_launch_continuation",
        market_regime=MarketRegime.NORMAL,
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        paper_execution_policy_version="paper-v1",
    )
    values.update(overrides)
    return PaperEntryProvenance(**values)  # type: ignore[arg-type]


def _execution(**overrides: object) -> PaperPositionExecutionEvidence:
    values: dict[str, object] = dict(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA,
        strategy_version="fresh-v1",
        position_id="position-a",
        ledger_sequence=1,
        intent_idempotency_key="buy-1",
        mint="MintA",
        side=TradeSide.BUY,
        execution_state=PaperExecutionState.FILLED,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_OPENED,
        booked_at_unix_ms=1_001,
        evaluated_at_unix_ms=1_001,
        requested_notional_usd=100.0,
        explicit_cost_usd=1.0,
        filled_notional_usd=100.0,
        filled_quantity=100.0,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        signed_slippage_usd=0.0,
        quote_provider="paper-test",
        executed_at_unix_ms=1_001,
    )
    values.update(overrides)
    return PaperPositionExecutionEvidence(**values)  # type: ignore[arg-type]


def _closure(**overrides: object) -> PaperClosedPositionEvidence:
    values: dict[str, object] = dict(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA,
        strategy_version="fresh-v1",
        position_id="position-a",
        mint="MintA",
        opened_at_unix_ms=1_001,
        closed_at_unix_ms=2_000,
        realized_pnl_usd=10.0,
        accumulated_costs_usd=2.0,
        buy_fill_count=1,
        sell_fill_count=1,
        closing_ledger_sequence=2,
    )
    values.update(overrides)
    return PaperClosedPositionEvidence(**values)  # type: ignore[arg-type]


def _orphan(**overrides: object) -> PaperOrphanCostEvidence:
    values: dict[str, object] = dict(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=SHA,
        strategy_version="fresh-v1",
        intent_idempotency_key="failed-entry",
        mint="MintFailed",
        explicit_cost_usd=0.01,
        evaluated_at_unix_ms=900,
    )
    values.update(overrides)
    return PaperOrphanCostEvidence(**values)  # type: ignore[arg-type]


def _ledger():
    sell = _execution(
        ledger_sequence=2,
        intent_idempotency_key="sell-1",
        side=TradeSide.SELL,
        ledger_reason_code=PaperLedgerReasonCode.POSITION_CLOSED,
        booked_at_unix_ms=2_000,
        evaluated_at_unix_ms=2_000,
        requested_notional_usd=110.0,
        filled_notional_usd=110.0,
        filled_quantity=100.0,
        reference_price_usd=1.1,
        execution_price_usd=1.1,
        executed_at_unix_ms=2_000,
    )
    return build_paper_evaluation_ledger(
        (_entry(),),
        (_execution(), sell),
        (_closure(),),
        (_orphan(),),
    )


def test_codec_round_trip_uses_exact_schema_and_enum_values() -> None:
    ledger = _ledger()
    document = build_paper_evaluation_document(ledger)
    assert tuple(sorted(document)) == tuple(
        sorted(
            (
                "schema_version",
                "entry_provenance",
                "executions",
                "closures",
                "orphan_costs",
                "document_fingerprint_sha256",
            )
        )
    )
    assert document["schema_version"] == PAPER_EVALUATION_SCHEMA_VERSION
    assert document["executions"][0]["side"] == TradeSide.BUY.value
    assert document["executions"][0]["execution_state"] == PaperExecutionState.FILLED.value
    assert document["executions"][0]["ledger_reason_code"] == PaperLedgerReasonCode.POSITION_OPENED.value
    assert document["entry_provenance"][0]["market_regime"] == MarketRegime.NORMAL.value
    assert decode_paper_evaluation_document(document) == ledger


def test_encoder_is_compact_sorted_and_has_exactly_one_trailing_newline() -> None:
    payload = encode_paper_evaluation_ledger(_ledger())
    assert payload.endswith("\n")
    assert not payload.endswith("\n\n")
    assert payload[:-1] == canonical_json(json.loads(payload))
    assert ": " not in payload
    assert ", " not in payload


def test_document_fingerprint_is_deterministic_and_content_sensitive() -> None:
    first = _ledger()
    second = _ledger()
    assert first.document_fingerprint_sha256 == second.document_fingerprint_sha256
    changed = build_paper_evaluation_ledger(
        (replace(_entry(), setup_name="changed-setup"),),
        first.executions,
        first.closures,
        first.orphan_costs,
    )
    assert changed.document_fingerprint_sha256 != first.document_fingerprint_sha256
    assert first.document_fingerprint_sha256 != ZERO_SHA


def test_decoder_rejects_unknown_or_missing_top_level_fields() -> None:
    document = build_paper_evaluation_document(_ledger())
    with pytest.raises(ValueError, match="fields"):
        decode_paper_evaluation_document({**document, "unknown": 1})
    missing = dict(document)
    missing.pop("closures")
    with pytest.raises(ValueError, match="fields"):
        decode_paper_evaluation_document(missing)


def test_decoder_rejects_unknown_nested_fields() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["entry_provenance"][0]["unknown"] = 1
    with pytest.raises(ValueError, match="fields"):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_invalid_enum_values() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["executions"][0]["side"] = "NOT_A_SIDE"
    with pytest.raises(ValueError):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_non_finite_numeric_values() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["executions"][0]["requested_notional_usd"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_malformed_candidate_sha() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["closures"][0]["candidate_fingerprint_sha256"] = "bad"
    with pytest.raises(ValueError, match="SHA-256"):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_stale_document_fingerprint() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["entry_provenance"][0]["setup_name"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_noncanonical_execution_order() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["executions"] = list(reversed(document["executions"]))
    with pytest.raises(ValueError, match="canonical"):
        decode_paper_evaluation_document(document)


def test_decoder_rejects_duplicate_identity() -> None:
    document = build_paper_evaluation_document(_ledger())
    document["entry_provenance"].append(dict(document["entry_provenance"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        decode_paper_evaluation_document(document)


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})
