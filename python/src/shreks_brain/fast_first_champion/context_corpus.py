from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from shreks_brain.fast_evaluation import FastForecastEvaluationContext
from shreks_brain.fast_evaluation.models import (
    fast_forecast_context_fingerprint_sha256,
)


FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME = (
    "shreks.fast_forecast_evaluation_context_corpus"
)
FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "contexts",
        "context_fingerprint_sha256",
    }
)
_CONTEXT_KEYS = frozenset(
    {
        "decision_identity",
        "as_of_unix_ms",
        "market_regime",
        "strategy_families",
        "executable_exit_capacity_quote",
        "expected_round_trip_cost_bps",
    }
)


@dataclass(frozen=True, slots=True)
class FastForecastEvaluationContextCorpus:
    schema_name: str
    schema_version: int
    contexts: tuple[FastForecastEvaluationContext, ...]
    context_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME:
            raise ValueError("unsupported forecast context corpus schema_name")
        if self.schema_version != FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION:
            raise ValueError("unsupported forecast context corpus schema_version")
        _validate_contexts(self.contexts)
        _require_sha256(
            "context_fingerprint_sha256",
            self.context_fingerprint_sha256,
        )
        expected = fast_forecast_context_fingerprint_sha256(self.contexts)
        if self.context_fingerprint_sha256 != expected:
            raise ValueError("forecast context corpus fingerprint mismatch")


def build_fast_forecast_evaluation_context_corpus(
    contexts: tuple[FastForecastEvaluationContext, ...],
) -> FastForecastEvaluationContextCorpus:
    _validate_context_input(contexts)
    canonical = tuple(sorted(contexts, key=_context_sort_key))
    _validate_contexts(canonical)
    return FastForecastEvaluationContextCorpus(
        schema_name=FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME,
        schema_version=FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION,
        contexts=canonical,
        context_fingerprint_sha256=(
            fast_forecast_context_fingerprint_sha256(canonical)
        ),
    )


def encode_fast_forecast_evaluation_context_corpus(
    corpus: FastForecastEvaluationContextCorpus,
) -> str:
    if type(corpus) is not FastForecastEvaluationContextCorpus:
        raise ValueError(
            "corpus must be an exact FastForecastEvaluationContextCorpus"
        )
    expected = fast_forecast_context_fingerprint_sha256(corpus.contexts)
    if corpus.context_fingerprint_sha256 != expected:
        raise ValueError("forecast context corpus fingerprint mismatch before encode")
    document = {
        "schema_name": corpus.schema_name,
        "schema_version": corpus.schema_version,
        "contexts": [_context_document(value) for value in corpus.contexts],
        "context_fingerprint_sha256": corpus.context_fingerprint_sha256,
    }
    return _canonical(document) + "\n"


def decode_fast_forecast_evaluation_context_corpus(
    payload: str,
) -> FastForecastEvaluationContextCorpus:
    if not isinstance(payload, str) or not payload:
        raise ValueError("forecast context corpus payload must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            "forecast context corpus must contain exactly one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("forecast context corpus is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("forecast context corpus must be a JSON object")
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "forecast context corpus has unknown or missing top-level fields"
        )
    if document["schema_name"] != FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_NAME:
        raise ValueError("unsupported forecast context corpus schema_name")
    if document["schema_version"] != FAST_FORECAST_CONTEXT_CORPUS_SCHEMA_VERSION:
        raise ValueError("unsupported forecast context corpus schema_version")

    raw_contexts = document["contexts"]
    if not isinstance(raw_contexts, list) or not raw_contexts:
        raise ValueError("forecast context corpus contexts must be a non-empty array")
    contexts = tuple(_context_from_document(value) for value in raw_contexts)

    try:
        corpus = FastForecastEvaluationContextCorpus(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            contexts=contexts,
            context_fingerprint_sha256=document[
                "context_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"forecast context corpus content is incompatible: {exc}"
        ) from exc

    canonical = encode_fast_forecast_evaluation_context_corpus(corpus)
    if payload != canonical:
        raise ValueError("forecast context corpus must use canonical JSON")
    return corpus


def write_fast_forecast_evaluation_context_corpus(
    corpus: FastForecastEvaluationContextCorpus,
    path: str | Path,
) -> None:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(
            "forecast context corpus destination already exists; overwrite is forbidden"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        encode_fast_forecast_evaluation_context_corpus(corpus),
        encoding="utf-8",
    )


def read_fast_forecast_evaluation_context_corpus(
    path: str | Path,
) -> FastForecastEvaluationContextCorpus:
    source = Path(path)
    if not source.is_file():
        raise ValueError(
            "forecast context corpus source must be an existing file"
        )
    try:
        payload = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("forecast context corpus source is unreadable") from exc
    return decode_fast_forecast_evaluation_context_corpus(payload)


def _validate_context_input(
    contexts: object,
) -> None:
    if (
        not isinstance(contexts, tuple)
        or not contexts
        or not all(
            type(value) is FastForecastEvaluationContext
            for value in contexts
        )
    ):
        raise ValueError(
            "contexts must be a non-empty tuple of exact FastForecastEvaluationContext values"
        )
    identities = tuple(value.decision_identity for value in contexts)
    if len(set(identities)) != len(identities):
        raise ValueError("forecast context corpus contains a duplicate decision identity")


def _validate_contexts(
    contexts: object,
) -> None:
    _validate_context_input(contexts)
    assert isinstance(contexts, tuple)
    if contexts != tuple(sorted(contexts, key=_context_sort_key)):
        raise ValueError("forecast context corpus contexts are not in canonical order")


def _context_sort_key(
    value: FastForecastEvaluationContext,
) -> tuple[object, ...]:
    identity = value.decision_identity
    return (
        value.as_of_unix_ms,
        identity[2],
        identity[0],
        identity[1],
    )


def _context_document(
    value: FastForecastEvaluationContext,
) -> dict[str, object]:
    return {
        "decision_identity": list(value.decision_identity),
        "as_of_unix_ms": value.as_of_unix_ms,
        "market_regime": value.market_regime,
        "strategy_families": list(value.strategy_families),
        "executable_exit_capacity_quote": _encode_optional_float(
            value.executable_exit_capacity_quote
        ),
        "expected_round_trip_cost_bps": _encode_optional_float(
            value.expected_round_trip_cost_bps
        ),
    }


def _context_from_document(
    value: object,
) -> FastForecastEvaluationContext:
    if not isinstance(value, dict):
        raise ValueError("forecast context corpus row must be an object")
    if frozenset(value) != _CONTEXT_KEYS:
        raise ValueError(
            "forecast context corpus row has unknown or missing fields"
        )
    raw_identity = value["decision_identity"]
    if not isinstance(raw_identity, list) or len(raw_identity) != 7:
        raise ValueError(
            "forecast context decision_identity must be a seven-item array"
        )
    if any(
        isinstance(item, (float, dict, list))
        for item in raw_identity
    ):
        raise ValueError(
            "forecast context decision_identity contains an unsupported value"
        )
    raw_families = value["strategy_families"]
    if not isinstance(raw_families, list):
        raise ValueError("forecast context strategy_families must be an array")
    if any(not isinstance(item, str) for item in raw_families):
        raise ValueError(
            "forecast context strategy_families must contain strings"
        )
    as_of = value["as_of_unix_ms"]
    if isinstance(as_of, bool) or not isinstance(as_of, int):
        raise ValueError("forecast context as_of_unix_ms must be an integer")
    market_regime = value["market_regime"]
    if not isinstance(market_regime, str):
        raise ValueError("forecast context market_regime must be text")

    try:
        return FastForecastEvaluationContext(
            decision_identity=tuple(raw_identity),
            as_of_unix_ms=as_of,
            market_regime=market_regime,
            strategy_families=tuple(raw_families),
            executable_exit_capacity_quote=_decode_optional_float(
                value["executable_exit_capacity_quote"],
                "executable_exit_capacity_quote",
            ),
            expected_round_trip_cost_bps=_decode_optional_float(
                value["expected_round_trip_cost_bps"],
                "expected_round_trip_cost_bps",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"forecast context corpus row is incompatible: {exc}"
        ) from exc


def _encode_optional_float(value: float | int | None) -> object:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("forecast context numeric values must be finite")
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise ValueError("forecast context float values must be finite")
    return {"$float": value.hex()}


def _decode_optional_float(
    value: object,
    name: str,
) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} boolean value is forbidden")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"{name} raw JSON float is forbidden; tagged float is required"
        )
    if not isinstance(value, dict) or frozenset(value) != {"$float"}:
        raise ValueError(
            f"{name} must be null, an integer, or an exact tagged float"
        )
    encoded = value["$float"]
    if not isinstance(encoded, str):
        raise ValueError(f"{name} tagged float payload must be text")
    try:
        decoded = float.fromhex(encoded)
    except ValueError as exc:
        raise ValueError(f"{name} tagged float is malformed") from exc
    if not math.isfinite(decoded):
        raise ValueError(f"{name} tagged float must be finite")
    return decoded


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
