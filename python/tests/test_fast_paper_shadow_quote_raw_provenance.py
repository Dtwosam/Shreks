from __future__ import annotations

import json
from pathlib import Path

import pytest

import shreks_brain.fast_paper_runtime.shadow as shadow
from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION,
    FastPaperShadowQuoteEvidence,
    FastPaperShadowReductionRead,
    read_fast_paper_shadow_decision_evidence,
    resolve_fast_paper_shadow_cycle_input,
    write_fast_paper_shadow_decision_evidence,
)

from test_fast_paper_shadow_decision import (
    _fake_champion,
    _manifest as _decision_manifest,
    _record as _decision_record,
)
from test_fast_paper_shadow_execution_input import _decision
from test_fast_paper_shadow_persisted_quotes import (
    _insert_quote,
    _manifest as _persisted_manifest,
    _read_policy,
    _record as _persisted_record,
)


def _raw_quote(
    record,
    *,
    observed_at: int,
    input_amount_raw: int,
    output_amount_raw: int | None,
    minimum_output_amount_raw: int | None,
    state: str = "EXECUTABLE",
    execution_price_quote: float | None = 1.0,
) -> FastPaperShadowQuoteEvidence:
    executable = state == "EXECUTABLE"
    return FastPaperShadowQuoteEvidence(
        provider="jupiter",
        mint=record.mint,
        quote_mint=record.quote_mint,
        observed_at_unix_ms=observed_at,
        state=state,
        reference_price_quote=(
            record.decision_executable_entry_price_quote
            if executable
            else None
        ),
        execution_price_quote=(
            execution_price_quote if executable else None
        ),
        quoted_base_quantity=2.0 if executable else None,
        available_base_quantity=2.0 if executable else None,
        input_amount_raw=input_amount_raw,
        output_amount_raw=output_amount_raw,
        minimum_output_amount_raw=minimum_output_amount_raw,
    )


def test_shadow_quote_raw_provenance_advances_decision_schema_v4() -> None:
    assert FAST_PAPER_SHADOW_DECISION_SCHEMA_VERSION == 4

    record = _decision_record()
    quote = _raw_quote(
        record,
        observed_at=20_010,
        input_amount_raw=1_000_000_000,
        output_amount_raw=2_000_000,
        minimum_output_amount_raw=1_900_000,
    )
    assert quote.input_amount_raw == 1_000_000_000
    assert quote.output_amount_raw == 2_000_000
    assert quote.minimum_output_amount_raw == 1_900_000

    unavailable = _raw_quote(
        record,
        observed_at=20_011,
        input_amount_raw=2_000_000,
        output_amount_raw=None,
        minimum_output_amount_raw=None,
        state="UNAVAILABLE",
        execution_price_quote=None,
    )
    assert unavailable.input_amount_raw == 2_000_000
    assert unavailable.output_amount_raw is None
    assert unavailable.minimum_output_amount_raw is None

    with pytest.raises(ValueError, match="raw|output|minimum"):
        _raw_quote(
            record,
            observed_at=20_012,
            input_amount_raw=1_000_000_000,
            output_amount_raw=1_900_000,
            minimum_output_amount_raw=2_000_000,
        )


def test_persisted_quote_resolver_preserves_exact_raw_entry_exit_and_reduction(
    tmp_path: Path,
) -> None:
    manifest = _persisted_manifest(tmp_path)
    record = _persisted_record()
    database = manifest.observer_database_path

    _insert_quote(
        database,
        row_id=1,
        purpose="entry",
        input_mint=manifest.quote_mint,
        output_mint=record.mint,
        input_amount=1_000_000_000,
        output_amount=20_000_000,
        minimum_output_amount=19_000_000,
        quoted_at=2_010,
    )
    _insert_quote(
        database,
        row_id=2,
        purpose="exit",
        input_mint=record.mint,
        output_mint=manifest.quote_mint,
        input_amount=20_000_000,
        output_amount=980_000_000,
        minimum_output_amount=970_000_000,
        quoted_at=2_015,
    )
    _insert_quote(
        database,
        row_id=3,
        purpose="exit",
        input_mint=record.mint,
        output_mint=manifest.quote_mint,
        input_amount=10_000_000,
        output_amount=495_000_000,
        minimum_output_amount=490_000_000,
        quoted_at=2_012,
    )

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        _read_policy(
            reductions=(
                FastPaperShadowReductionRead(
                    target_exposure_fraction=0.25,
                    input_amount_raw=10_000_000,
                ),
            )
        ),
        evaluated_at_unix_ms=2_020,
        max_exposure_fraction=0.75,
    )

    assert (
        cycle.entry_quote.input_amount_raw,
        cycle.entry_quote.output_amount_raw,
        cycle.entry_quote.minimum_output_amount_raw,
    ) == (1_000_000_000, 20_000_000, 19_000_000)
    assert (
        cycle.exit_quote.input_amount_raw,
        cycle.exit_quote.output_amount_raw,
        cycle.exit_quote.minimum_output_amount_raw,
    ) == (20_000_000, 980_000_000, 970_000_000)
    reduction = cycle.reduction_quotes[0].quote
    assert (
        reduction.input_amount_raw,
        reduction.output_amount_raw,
        reduction.minimum_output_amount_raw,
    ) == (10_000_000, 495_000_000, 490_000_000)


def test_persisted_unavailable_quote_preserves_raw_input_without_outputs(
    tmp_path: Path,
) -> None:
    manifest = _persisted_manifest(tmp_path)
    record = _persisted_record()
    database = manifest.observer_database_path

    _insert_quote(
        database,
        row_id=1,
        purpose="entry",
        input_mint=manifest.quote_mint,
        output_mint=record.mint,
        input_amount=1_000_000_000,
        output_amount=20_000_000,
        minimum_output_amount=19_000_000,
        quoted_at=2_010,
    )
    _insert_quote(
        database,
        row_id=2,
        purpose="exit",
        input_mint=record.mint,
        output_mint=manifest.quote_mint,
        input_amount=20_000_000,
        output_amount=0,
        minimum_output_amount=0,
        quoted_at=2_015,
        route_available=False,
    )

    cycle = resolve_fast_paper_shadow_cycle_input(
        manifest,
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        _read_policy(),
        evaluated_at_unix_ms=2_020,
        max_exposure_fraction=0.5,
    )

    assert cycle.exit_quote.state == "UNAVAILABLE"
    assert cycle.exit_quote.input_amount_raw == 20_000_000
    assert cycle.exit_quote.output_amount_raw is None
    assert cycle.exit_quote.minimum_output_amount_raw is None


def test_shadow_decision_raw_quote_provenance_round_trips_and_tamper_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = _decision_manifest(tmp_path)
    record = _decision_record()
    monkeypatch.setattr(
        shadow,
        "read_fast_forecast_champion",
        lambda _path: _fake_champion(manifest),
    )
    monkeypatch.setattr(
        shadow,
        "evaluate_fast_campaign_decision_batch_offline",
        lambda *, binary_path, champion_path, batch, timeout_seconds=None: (
            _decision(manifest, batch.decisions[0], action="BUY")
        ),
    )
    ticks = iter((1_000, 1_250))
    monkeypatch.setattr(shadow.time, "monotonic_ns", lambda: next(ticks))

    evidence = shadow.evaluate_fast_paper_shadow_decision(
        manifest,
        record,
        FastCampaignDecisionPosition(kind="FLAT"),
        evaluated_at_unix_ms=20_020,
        max_exposure_fraction=0.75,
        entry_quote=_raw_quote(
            record,
            observed_at=20_010,
            input_amount_raw=1_000_000_000,
            output_amount_raw=2_000_000,
            minimum_output_amount_raw=1_900_000,
            execution_price_quote=1.01,
        ),
        exit_quote=_raw_quote(
            record,
            observed_at=20_015,
            input_amount_raw=2_000_000,
            output_amount_raw=1_960_000_000,
            minimum_output_amount_raw=1_940_000_000,
            execution_price_quote=0.98,
        ),
    )
    path = tmp_path / "decision.json"
    write_fast_paper_shadow_decision_evidence(evidence, path)
    restored = read_fast_paper_shadow_decision_evidence(path)

    assert restored == evidence
    assert restored.entry_quote.input_amount_raw == 1_000_000_000
    assert restored.entry_quote.output_amount_raw == 2_000_000
    assert restored.exit_quote.input_amount_raw == 2_000_000

    document = json.loads(path.read_text(encoding="utf-8"))
    document["entry_quote"]["output_amount_raw"] += 1
    path.write_text(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fingerprint|canonical|quote"):
        read_fast_paper_shadow_decision_evidence(path)


def test_shadow_decision_source_does_not_reverse_convert_float_quantities() -> None:
    payload = Path(shadow.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "decimal_quantity_to_raw",
        "counterfactual_base_quantity",
        "round(",
        "* 10 **",
        "* (10 **",
    ):
        assert forbidden not in payload
