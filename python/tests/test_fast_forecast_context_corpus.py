from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from fast_forecast_evaluation_fixtures import (
    build_run,
    evaluation_contexts,
)
from shreks_brain.fast_evaluation.models import (
    fast_forecast_context_fingerprint_sha256,
)
from shreks_brain.fast_first_champion import (
    FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME,
    FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION,
    FastForecastEvaluationContextCorpus,
    build_fast_forecast_evaluation_context_corpus,
    decode_fast_forecast_evaluation_context_corpus,
    encode_fast_forecast_evaluation_context_corpus,
    read_fast_forecast_evaluation_context_corpus,
    write_fast_forecast_evaluation_context_corpus,
)


def _contexts():
    _, run = build_run()
    return evaluation_contexts(run)


def test_context_corpus_is_canonical_authenticated_and_order_independent() -> None:
    contexts = _contexts()
    corpus = build_fast_forecast_evaluation_context_corpus(
        tuple(reversed(contexts))
    )

    assert type(corpus) is FastForecastEvaluationContextCorpus
    assert corpus.schema_name == FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME
    assert corpus.schema_version == FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION
    assert tuple(value.decision_identity for value in corpus.contexts) == tuple(
        value.decision_identity
        for value in sorted(
            contexts,
            key=lambda value: (
                value.as_of_unix_ms,
                value.decision_identity[2],
                value.decision_identity[0],
                value.decision_identity[1],
            ),
        )
    )
    assert corpus.context_fingerprint_sha256 == (
        fast_forecast_context_fingerprint_sha256(corpus.contexts)
    )

    payload = encode_fast_forecast_evaluation_context_corpus(corpus)
    assert payload.endswith("\n")
    assert payload[:-1] == json.dumps(
        json.loads(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert '"$float"' in payload
    assert decode_fast_forecast_evaluation_context_corpus(payload) == corpus
    assert encode_fast_forecast_evaluation_context_corpus(
        decode_fast_forecast_evaluation_context_corpus(payload)
    ) == payload


def test_context_corpus_preserves_integer_numeric_scalar_fingerprint() -> None:
    contexts = _contexts()
    first = replace(
        contexts[0],
        executable_exit_capacity_quote=5,
        expected_round_trip_cost_bps=0,
    )
    corpus = build_fast_forecast_evaluation_context_corpus(
        (first, *contexts[1:])
    )

    payload = encode_fast_forecast_evaluation_context_corpus(corpus)
    document = json.loads(payload)
    assert document["contexts"][0]["executable_exit_capacity_quote"] == 5
    assert document["contexts"][0]["expected_round_trip_cost_bps"] == 0

    decoded = decode_fast_forecast_evaluation_context_corpus(payload)
    assert decoded == corpus
    assert decoded.context_fingerprint_sha256 == (
        corpus.context_fingerprint_sha256
    )


def test_context_corpus_file_round_trip_refuses_overwrite(tmp_path: Path) -> None:
    corpus = build_fast_forecast_evaluation_context_corpus(_contexts())
    destination = tmp_path / "contexts.json"

    write_fast_forecast_evaluation_context_corpus(corpus, destination)
    assert read_fast_forecast_evaluation_context_corpus(destination) == corpus

    with pytest.raises(FileExistsError, match="exists|overwrite"):
        write_fast_forecast_evaluation_context_corpus(corpus, destination)


def test_context_corpus_rejects_tampering_unknown_fields_and_raw_floats() -> None:
    corpus = build_fast_forecast_evaluation_context_corpus(_contexts())
    payload = encode_fast_forecast_evaluation_context_corpus(corpus)

    tampered = json.loads(payload)
    tampered["context_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        decode_fast_forecast_evaluation_context_corpus(
            json.dumps(
                tampered,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

    unknown = json.loads(payload)
    unknown["contexts"][0]["future_pnl"] = 999
    with pytest.raises(ValueError, match="unknown|missing|fields"):
        decode_fast_forecast_evaluation_context_corpus(
            json.dumps(
                unknown,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

    raw_float = json.loads(payload)
    raw_float["contexts"][0]["executable_exit_capacity_quote"] = 1.5
    with pytest.raises(ValueError, match="float|tag"):
        decode_fast_forecast_evaluation_context_corpus(
            json.dumps(
                raw_float,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def test_context_corpus_rejects_duplicate_identity() -> None:
    contexts = _contexts()
    with pytest.raises(ValueError, match="duplicate"):
        build_fast_forecast_evaluation_context_corpus(
            (*contexts, contexts[0])
        )


def test_context_corpus_source_has_no_db_network_trading_or_live_authority() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fast_first_champion"
        / "context_corpus.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sqlite3",
        "requests.",
        "httpx",
        "TradeIntent",
        "RuntimeMode.LIVE",
        "sign_transaction",
        "submit_transaction",
        "promotion",
        "registry",
    ):
        assert forbidden not in source
